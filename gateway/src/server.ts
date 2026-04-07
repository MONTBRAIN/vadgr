/** Gateway server -- connects adapters, security, router. */

import { VadgrAPIClient } from "./api-client.js";
import { MessageRouter } from "./router.js";
import { SecurityGuard, SILENT_REJECT, defaultSecurityConfig, type SecurityConfig } from "./security.js";
import type { ChannelAdapter } from "./adapters/base.js";
import type { InboundMessage, OutboundMessage } from "./models.js";
import { DiscordAdapter, type DiscordConfig } from "./adapters/discord.js";

export interface GatewayConfig {
  apiUrl: string;
  discord?: DiscordConfig | undefined;
  security?: SecurityConfig | undefined;
}

export class Gateway {
  private config: GatewayConfig;
  private api: VadgrAPIClient;
  private router: MessageRouter;
  private security: SecurityGuard;
  private adapters: ChannelAdapter[] = [];

  constructor(config: GatewayConfig) {
    this.config = config;
    this.api = new VadgrAPIClient(config.apiUrl);
    this.security = new SecurityGuard(config.security || defaultSecurityConfig());
    this.router = new MessageRouter(this.api, (v) => this.security.sanitizeInput(v));
  }

  async start(): Promise<void> {
    // Discord
    if (this.config.discord?.botToken) {
      const discord = new DiscordAdapter(this.config.discord);
      discord.registerHandler((msg) => this.processMessage(msg, discord));
      discord.setSessionChecker((senderId) => this.router.hasActiveSession(senderId));
      await discord.connect();
      this.adapters.push(discord);
    }

    if (this.adapters.length === 0) {
      console.warn("[Gateway] No adapters configured. Set DISCORD_BOT_TOKEN or configure gateway.yaml");
    } else {
      console.log(`[Gateway] Running with ${this.adapters.length} adapter(s): ${this.adapters.map((a) => a.name).join(", ")}`);
    }
  }

  async stop(): Promise<void> {
    for (const adapter of this.adapters) {
      await adapter.disconnect();
    }
    console.log("[Gateway] Stopped");
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
      this.watchRun(result.runId, result.agentName || "Agent", message.chatId, adapter);
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
