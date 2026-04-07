/** Gateway server -- connects adapters, security, router, and optional WS server. */

import { VadgrAPIClient } from "./api-client.js";
import { MessageRouter } from "./router.js";
import { SecurityGuard, SILENT_REJECT, defaultSecurityConfig, type SecurityConfig } from "./security.js";
import type { ChannelAdapter } from "./adapters/base.js";
import type { InboundMessage, OutboundMessage, AgentAPI } from "./models.js";
import { DiscordAdapter, type DiscordConfig } from "./adapters/discord.js";
import { GatewayWsServer, type WsServerConfig } from "./ws-server.js";
import { MultiMachineAPI } from "./multi-machine-api.js";
import {
  greetingEmbed,
  agentListEmbed,
  runStartedEmbed,
  statusEmbed,
  machinesEmbed,
  helpEmbed,
  runCompletedEmbed,
  runFailedEmbed,
  errorEmbed,
} from "./embeds.js";

/** Safely extract a string from any error type (Error, string, JSON object). */
function safeErrorMessage(err: unknown): string {
  if (err instanceof Error) return err.message;
  if (typeof err === "string") return err;
  if (err == null) return "Unknown error";
  try { return JSON.stringify(err); } catch { return "Unknown error"; }
}

/** Safely extract displayable text from a log entry. */
function formatLogEntry(entry: any): string {
  // Log entries from the API have { type, data: { message?, ... }, timestamp }
  const data = entry?.data;
  const message = data?.message ?? data?.summary ?? entry?.message ?? entry?.summary;
  if (typeof message === "string" && message) return message.slice(0, 120);
  // For events without a message, show the event type
  const type = entry?.type;
  if (typeof type === "string") return type;
  return "";
}

export interface GatewayConfig {
  apiUrl: string;
  discord?: DiscordConfig | undefined;
  security?: SecurityConfig | undefined;
  ws?: WsServerConfig | undefined;
}

export class Gateway {
  private config: GatewayConfig;
  private localApi: VadgrAPIClient;
  private api: AgentAPI;
  private router: MessageRouter;
  private security: SecurityGuard;
  private adapters: ChannelAdapter[] = [];
  private wsServer?: GatewayWsServer;
  private multiMachineApi?: MultiMachineAPI;

  /** Maps runId -> { chatId, adapter } for sending progress/completion to Discord. */
  private runTracking = new Map<string, {
    chatId: string;
    adapter: ChannelAdapter;
    agentName: string;
    machineName?: string;
  }>();

  constructor(config: GatewayConfig) {
    this.config = config;
    this.localApi = new VadgrAPIClient(config.apiUrl);
    this.security = new SecurityGuard(config.security || defaultSecurityConfig());

    // Multi-machine mode: use WebSocket server + aggregation API
    if (config.ws) {
      this.wsServer = new GatewayWsServer(config.ws);
      this.multiMachineApi = new MultiMachineAPI(
        this.wsServer.getRegistry(),
        this.wsServer,
      );
      this.api = this.multiMachineApi;
    } else {
      this.api = this.localApi;
    }

    this.router = new MessageRouter(this.api, (v) => this.security.sanitizeInput(v));
  }

  async start(): Promise<void> {
    // Start WebSocket server for multi-machine
    if (this.wsServer) {
      await this.wsServer.start();
      this.wireProgressEvents();
      console.log("[Gateway] Multi-machine mode enabled");
    }

    // Discord
    if (this.config.discord?.botToken) {
      const discord = new DiscordAdapter(this.config.discord);
      discord.registerHandler((msg) => this.processMessage(msg, discord));
      discord.setSessionChecker((senderId) => this.router.hasActiveSession(senderId));
      discord.onSlashCommand = (cmd, opts, senderId, senderName, chatId) =>
        this.handleSlashCommand(cmd, opts, senderId, senderName, chatId, discord);
      await discord.connect();
      this.adapters.push(discord);
    }

    if (this.adapters.length === 0 && !this.wsServer) {
      console.warn("[Gateway] No adapters configured. Set DISCORD_BOT_TOKEN or configure gateway.yaml");
    } else {
      const parts: string[] = [];
      if (this.adapters.length) parts.push(`${this.adapters.length} adapter(s): ${this.adapters.map((a) => a.name).join(", ")}`);
      if (this.wsServer) parts.push("WebSocket server");
      console.log(`[Gateway] Running with ${parts.join(" + ")}`);
    }
  }

  async stop(): Promise<void> {
    if (this.wsServer) await this.wsServer.stop();
    for (const adapter of this.adapters) {
      await adapter.disconnect();
    }
    console.log("[Gateway] Stopped");
  }

  /** Handle slash commands from Discord with embed responses. */
  private async handleSlashCommand(
    command: string,
    options: Record<string, string>,
    senderId: string,
    senderName: string,
    chatId: string,
    adapter: ChannelAdapter,
  ): Promise<{ text?: string; embed?: any }> {
    try {
      switch (command) {
        case "agents": {
          const agents = await this.api.listAgents();
          return { embed: agentListEmbed(agents as any[]) };
        }
        case "status": {
          const runs = await this.api.listRuns();
          return { embed: statusEmbed(runs as any[]) };
        }
        case "machines": {
          if (this.wsServer) {
            const machines = this.wsServer.getRegistry().getAllMachines().map((m) => ({
              name: m.name,
              agentCount: m.agents.length,
              connectedAt: m.connectedAt,
              activeRuns: m.activeRuns,
            }));
            return { embed: machinesEmbed(machines) };
          }
          return { text: "Multi-machine mode not enabled. Run on a single machine." };
        }
        case "run": {
          const agentQuery = options["agent"] || "";
          // Use the router's existing agent matching logic via a synthetic message
          const fakeMessage = {
            channel: "discord",
            chatId,
            senderId,
            senderName,
            text: `run ${agentQuery}`,
            messageType: "text" as any,
            timestamp: new Date(),
            raw: {},
          };
          const result = await this.router.handle(fakeMessage);

          if (result.isAsync && result.runId) {
            if (this.wsServer) {
              this.runTracking.set(result.runId, {
                chatId, adapter, agentName: result.agentName || "Agent", machineName: result.machineName,
              });
            } else {
              this.watchRun(result.runId, result.agentName || "Agent", chatId, adapter);
            }
            return { embed: runStartedEmbed(result.agentName || "Agent", result.runId, result.machineName) };
          }

          return { text: result.response };
        }
        case "cancel": {
          const runId = options["run_id"] || "";
          try {
            await this.api.cancelRun(runId.trim());
            return { text: `Cancelled run ${runId}.` };
          } catch (e: unknown) {
            return { embed: errorEmbed("Cancel failed", safeErrorMessage(e)) };
          }
        }
        case "logs": {
          const runId = options["run_id"] || "";
          try {
            const logs = await this.api.getRunLogs(runId.trim());
            if (!logs.length) return { text: "No logs yet." };
            const lines = logs.slice(-5).map((entry: any) => formatLogEntry(entry));
            return { text: "```\n" + lines.join("\n") + "\n```" };
          } catch (e: unknown) {
            return { embed: errorEmbed("Logs failed", safeErrorMessage(e)) };
          }
        }
        default:
          return { embed: helpEmbed() };
      }
    } catch (err: unknown) {
      return { embed: errorEmbed("Error", safeErrorMessage(err)) };
    }
  }

  /** Wire WebSocket progress/completion events to Discord run tracking. */
  private wireProgressEvents(): void {
    if (!this.wsServer) return;

    this.wsServer.onProgress = (_machineId, payload) => {
      const tracking = this.runTracking.get(payload.runId);
      if (!tracking) return;
      const progress = `${payload.agentName}: Step ${payload.stepIndex}/${payload.stepTotal} -- ${payload.stepName}`;
      tracking.adapter.sendMessage({ chatId: tracking.chatId, text: progress });
    };

    this.wsServer.onRunCompleted = (_machineId, payload) => {
      const tracking = this.runTracking.get(payload.runId);
      if (!tracking) return;
      this.runTracking.delete(payload.runId);
      this.multiMachineApi?.untrackRun(payload.runId);

      const parts = [`${payload.agentName} finished!`];
      for (const [key, val] of Object.entries(payload.outputs)) {
        if (typeof val === "string" && val.length < 500) parts.push(`${key}: ${val}`);
      }
      tracking.adapter.sendMessage({ chatId: tracking.chatId, text: parts.join("\n") });
    };

    this.wsServer.onRunFailed = (_machineId, payload) => {
      const tracking = this.runTracking.get(payload.runId);
      if (!tracking) return;
      this.runTracking.delete(payload.runId);
      this.multiMachineApi?.untrackRun(payload.runId);

      tracking.adapter.sendMessage({
        chatId: tracking.chatId,
        text: `${payload.agentName} failed.\nError: ${payload.error}\n\nResume with: resume ${payload.runId.slice(0, 8)}`,
      });
    };

    this.wsServer.onMachineConnected = (machine) => {
      console.log(`[Gateway] Machine connected: ${machine.name}`);
    };

    this.wsServer.onMachineDisconnected = (machine) => {
      console.log(`[Gateway] Machine disconnected: ${machine.name}`);
    };
  }

  private async processMessage(message: InboundMessage, adapter: ChannelAdapter): Promise<void> {
    if (!message.text) return;

    // Security check
    const rejection = this.security.check(message);
    if (rejection === SILENT_REJECT) return;
    if (rejection) {
      await adapter.sendMessage({ chatId: message.chatId, text: rejection });
      return;
    }

    // Route
    let result;
    try {
      result = await this.router.handle(message);
    } catch (e: any) {
      console.error(`[Gateway] Router error for ${message.senderId}:`, e);
      await adapter.sendMessage({ chatId: message.chatId, text: `Something went wrong: ${e.message}` });
      return;
    }

    // Respond
    await adapter.sendMessage({ chatId: message.chatId, text: result.response });

    // Watch async runs
    if (result.isAsync && result.runId) {
      if (this.wsServer) {
        // Multi-machine: progress comes via WebSocket events (wireProgressEvents)
        this.runTracking.set(result.runId, {
          chatId: message.chatId,
          adapter,
          agentName: result.agentName || "Agent",
          machineName: result.machineName,
        });
      } else {
        // Single-machine: poll the local API
        this.watchRun(result.runId, result.agentName || "Agent", message.chatId, adapter);
      }
    }
  }

  private async watchRun(runId: string, agentName: string, chatId: string, adapter: ChannelAdapter): Promise<void> {
    const POLL_INTERVAL = 30_000;
    const MAX_POLLS = 120;

    for (let i = 0; i < MAX_POLLS; i++) {
      await new Promise((r) => setTimeout(r, POLL_INTERVAL));
      try {
        const run: any = await this.api.getRun(runId);
        if (run.status === "completed") {
          const outputs = run.outputs || {};
          const parts = [`${agentName} finished!`];
          for (const [key, val] of Object.entries(outputs)) {
            if (typeof val === "string" && val.length < 500) parts.push(`\n${key}: ${val}`);
          }
          await adapter.sendMessage({ chatId, text: parts.join("\n") });
          return;
        }
        if (run.status === "failed") {
          const error = typeof run.outputs === "object" ? run.outputs?.error || "Unknown error" : String(run.outputs);
          await adapter.sendMessage({
            chatId,
            text: `${agentName} failed.\nError: ${error}\n\nResume with: resume ${runId.slice(0, 8)}`,
          });
          return;
        }
      } catch {
        // API might be temporarily unreachable, keep polling
      }
    }

    await adapter.sendMessage({ chatId, text: `Run ${runId.slice(0, 8)} still going after 1 hour. Check with: status` });
  }
}
