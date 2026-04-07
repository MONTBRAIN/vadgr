/** Conversational command router -- maps natural language to agent runs. */

import type { InboundMessage, CommandResult } from "./models.js";
import type { VadgrAPIClient } from "./api-client.js";

enum State {
  IDLE = "idle",
  AWAITING_AGENT = "awaiting_agent",
  AWAITING_INPUTS = "awaiting_inputs",
  CONFIRMING = "confirming",
}

interface Session {
  state: State;
  selectedAgent: Record<string, any> | null;
  collectedInputs: Record<string, string>;
  pendingInput: string | null;
}

export class MessageRouter {
  private api: VadgrAPIClient;
  private sanitize: (v: string) => string;
  private sessions = new Map<string, Session>();

  constructor(api: VadgrAPIClient, sanitize: (v: string) => string = (v) => v) {
    this.api = api;
    this.sanitize = sanitize;
  }

  /** Returns true if the sender has an active conversational session (not idle). */
  hasActiveSession(senderId: string): boolean {
    const session = this.sessions.get(senderId);
    return session !== undefined && session.state !== State.IDLE;
  }

  private getSession(senderId: string): Session {
    if (!this.sessions.has(senderId)) {
      this.sessions.set(senderId, {
        state: State.IDLE,
        selectedAgent: null,
        collectedInputs: {},
        pendingInput: null,
      });
    }
    return this.sessions.get(senderId)!;
  }

  async handle(message: InboundMessage): Promise<CommandResult> {
    const text = message.text.trim();
    const session = this.getSession(message.senderId);
    const lower = text.toLowerCase();

    // Global commands
    if (["help", "?", "commands"].includes(lower)) return this.help();
    if (["hi", "hey", "hello", "hola", "que hay", "buenas"].includes(lower)) {
      session.state = State.AWAITING_AGENT;
      return this.greet(message.senderName);
    }
    if (["agents", "list agents", "what agents"].includes(lower)) return this.listAgents();
    if (["status", "runs", "what's running"].includes(lower)) return this.status();
    if (lower.startsWith("cancel ")) return this.cancel(lower.slice(7));
    if (lower.startsWith("resume ")) return this.resume(lower.slice(7));
    if (lower.startsWith("logs ")) return this.logs(lower.slice(5));

    // State-dependent
    if (session.state === State.AWAITING_AGENT) return this.selectAgent(session, text);
    if (session.state === State.AWAITING_INPUTS) return this.collectInput(session, text);
    if (session.state === State.CONFIRMING) return this.confirm(session, text);

    return this.parseRunIntent(session, text, message.senderName);
  }

  private async greet(name: string): Promise<CommandResult> {
    const agents = await this.api.listAgents();
    const list = agents
      .map((a: any, i: number) => `  ${i + 1}. ${a.name} (${(a.steps || []).length} steps)`)
      .join("\n");
    return {
      response: `Hey ${name}! You have ${agents.length} agents ready:\n${list}\n\nWhat do you want to do?`,
      isAsync: false,
    };
  }

  private help(): CommandResult {
    return {
      response: [
        "Available commands:",
        "  hey/hi -- see your agents",
        "  run <agent> -- start an agent run",
        "  status -- show active runs",
        "  resume <id> -- resume a failed run",
        "  cancel <id> -- cancel a running run",
        "  logs <id> -- show recent logs",
        "  help -- this message",
        "",
        "Or just describe what you want and I'll figure it out.",
      ].join("\n"),
      isAsync: false,
    };
  }

  private async listAgents(): Promise<CommandResult> {
    const agents = await this.api.listAgents();
    if (!agents.length) return { response: "No agents registered.", isAsync: false };
    const lines = agents.map((a: any) => `  ${a.name} -- ${(a.description || "").slice(0, 60)}`);
    return { response: "Your agents:\n" + lines.join("\n"), isAsync: false };
  }

  private async status(): Promise<CommandResult> {
    const runs = await this.api.listRuns();
    if (!runs.length) return { response: "No runs. Everything is idle.", isAsync: false };
    const lines = runs.slice(0, 10).map((r: any) => {
      const id = (r.id || "").slice(0, 8);
      return `  ${id} | ${r.agent_name || "-"} | ${r.status || "?"}`;
    });
    return { response: "Recent runs:\n" + lines.join("\n"), isAsync: false };
  }

  private async cancel(runId: string): Promise<CommandResult> {
    try {
      await this.api.cancelRun(runId.trim());
      return { response: `Cancelled run ${runId}.`, isAsync: false };
    } catch (e: any) {
      return { response: `Failed to cancel: ${e.message}`, isAsync: false };
    }
  }

  private async resume(runId: string): Promise<CommandResult> {
    try {
      const result: any = await this.api.resumeRun(runId.trim());
      return { response: result.message || "Resuming...", runId: runId.trim(), isAsync: true };
    } catch (e: any) {
      return { response: `Failed to resume: ${e.message}`, isAsync: false };
    }
  }

  private async logs(runId: string): Promise<CommandResult> {
    try {
      const logs = await this.api.getRunLogs(runId.trim());
      if (!logs.length) return { response: "No logs yet.", isAsync: false };
      const lines = logs.slice(-5).map((e: any) => `  ${(e.message || e.data || "").slice(0, 100)}`);
      return { response: "Recent logs:\n" + lines.join("\n"), isAsync: false };
    } catch (e: any) {
      return { response: `Failed to get logs: ${e.message}`, isAsync: false };
    }
  }

  private async parseRunIntent(session: Session, text: string, senderName: string): Promise<CommandResult> {
    const lower = text.toLowerCase();

    if (lower.startsWith("run ")) return this.findAndStartAgent(session, text.slice(4).trim());

    // Fuzzy: check if user mentioned an agent name
    const agents = await this.api.listAgents();
    for (const agent of agents) {
      if (lower.includes((agent as any).name.toLowerCase())) {
        session.selectedAgent = agent as any;
        return this.askForInputs(session);
      }
    }

    // Can't figure it out
    session.state = State.AWAITING_AGENT;
    const list = agents.map((a: any, i: number) => `  ${i + 1}. ${a.name}`).join("\n");
    return {
      response: `Which agent do you want to run?\n${list}\n\nReply with the name or number.`,
      isAsync: false,
    };
  }

  private async findAndStartAgent(session: Session, query: string): Promise<CommandResult> {
    const agents = await this.api.listAgents();

    // Match by number
    if (/^\d+$/.test(query)) {
      const idx = parseInt(query, 10) - 1;
      if (idx >= 0 && idx < agents.length) {
        session.selectedAgent = agents[idx] as any;
        return this.askForInputs(session);
      }
    }

    // Match by name (fuzzy)
    const q = query.toLowerCase();
    for (const agent of agents) {
      if ((agent as any).name.toLowerCase().includes(q)) {
        session.selectedAgent = agent as any;
        return this.askForInputs(session);
      }
    }

    return { response: `No agent matching '${query}'. Try 'agents' to see the list.`, isAsync: false };
  }

  private async selectAgent(session: Session, text: string): Promise<CommandResult> {
    const cleaned = text.trim().toLowerCase().startsWith("run ")
      ? text.trim().slice(4).trim()
      : text.trim();
    return this.findAndStartAgent(session, cleaned);
  }

  private async askForInputs(session: Session): Promise<CommandResult> {
    const agent = session.selectedAgent!;
    const schema: any[] = agent.input_schema || [];

    // Find first required input not yet collected
    for (const inp of schema) {
      if (inp.required && !(inp.name in session.collectedInputs)) {
        session.state = State.AWAITING_INPUTS;
        session.pendingInput = inp.name;
        const label = inp.label || inp.name;
        const desc = inp.description || "";
        return { response: desc ? `${label}?\n(${desc})` : `${label}?`, isAsync: false };
      }
    }

    // Check for optional
    const optional = schema.filter((inp) => !inp.required && !(inp.name in session.collectedInputs));
    if (optional.length) {
      const labels = optional.map((inp) => inp.label || inp.name).join(", ");
      session.state = State.CONFIRMING;
      return {
        response: `Optional: ${labels}\nWant to set any, or should I start?`,
        isAsync: false,
      };
    }

    return this.startRun(session);
  }

  private async collectInput(session: Session, text: string): Promise<CommandResult> {
    if (session.pendingInput) {
      session.collectedInputs[session.pendingInput] = this.sanitize(text.trim());
      session.pendingInput = null;
    }
    return this.askForInputs(session);
  }

  private async confirm(session: Session, text: string): Promise<CommandResult> {
    const lower = text.toLowerCase();
    if (["yes", "start", "run", "go", "dale", "si", "ya", "no", "nah", "skip", "na"].includes(lower)) {
      return this.startRun(session);
    }

    if (text.includes("=")) {
      const parts = text.split("=");
      const key = parts[0] ?? "";
      const rest = parts.slice(1);
      session.collectedInputs[key.trim()] = this.sanitize(rest.join("=").trim());
      return this.askForInputs(session);
    }

    const schema: any[] = session.selectedAgent?.input_schema || [];
    const optional = schema.filter((inp) => !inp.required && !(inp.name in session.collectedInputs));
    if (optional.length) {
      session.collectedInputs[optional[0].name] = this.sanitize(text.trim());
      return this.askForInputs(session);
    }

    return this.startRun(session);
  }

  private async startRun(session: Session): Promise<CommandResult> {
    const agent = session.selectedAgent!;
    const inputs = { ...session.collectedInputs };

    // Reset session
    session.state = State.IDLE;
    session.selectedAgent = null;
    session.collectedInputs = {};
    session.pendingInput = null;

    try {
      const result: any = await this.api.runAgent(agent.id, inputs);
      const runId = result.run_id || "?";
      return {
        response: `Starting ${agent.name}...\nRun ID: ${runId.slice(0, 8)}\nI'll message you when it's done.`,
        runId,
        agentName: agent.name,
        isAsync: true,
      };
    } catch (e: any) {
      return { response: `Failed to start: ${e.message}`, isAsync: false };
    }
  }
}
