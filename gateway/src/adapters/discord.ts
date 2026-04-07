/** Discord adapter using discord.js. Handles DMs and bot mentions. */

import { Client, GatewayIntentBits, Message, Partials } from "discord.js";
import type { ChannelAdapter, MessageHandler, SessionChecker } from "./base.js";
import type { OutboundMessage } from "../models.js";
import { MessageType, type InboundMessage } from "../models.js";

export interface DiscordConfig {
  botToken: string;
  botId?: string; // optional, auto-detected on connect
}

export class DiscordAdapter implements ChannelAdapter {
  readonly name = "discord";
  private client: Client;
  private config: DiscordConfig;
  private handler: MessageHandler | null = null;
  private resolvedBotId: string = "";
  private hasActiveSession: SessionChecker = () => false;

  constructor(config: DiscordConfig) {
    this.config = config;
    this.client = new Client({
      intents: [
        GatewayIntentBits.Guilds,
        GatewayIntentBits.GuildMessages,
        GatewayIntentBits.DirectMessages,
        GatewayIntentBits.MessageContent,
      ],
      partials: [Partials.Channel], // needed for DMs
    });
  }

  async connect(): Promise<void> {
    return new Promise((resolve, reject) => {
      this.client.once("ready", () => {
        this.resolvedBotId = this.client.user?.id || this.config.botId || "";
        console.log(`[Discord] Connected as ${this.client.user?.tag} (${this.resolvedBotId})`);
        resolve();
      });

      this.client.on("messageCreate", async (msg: Message) => {
        if (!this.handler) return;
        const parsed = this.parseMessage(msg);
        if (parsed) await this.handler(parsed);
      });

      this.client.login(this.config.botToken).catch(reject);
    });
  }

  async disconnect(): Promise<void> {
    await this.client.destroy();
  }

  async sendMessage(message: OutboundMessage): Promise<void> {
    const channel = await this.client.channels.fetch(message.chatId);
    if (channel && channel.isTextBased() && "send" in channel) {
      // Split long messages (Discord limit: 2000 chars)
      const text = message.text;
      if (text.length <= 2000) {
        await (channel as any).send(text);
      } else {
        const chunks = text.match(/.{1,2000}/gs) || [];
        for (const chunk of chunks) {
          await (channel as any).send(chunk);
        }
      }
    }
  }

  registerHandler(handler: MessageHandler): void {
    this.handler = handler;
  }

  setSessionChecker(checker: SessionChecker): void {
    this.hasActiveSession = checker;
  }

  private parseMessage(msg: Message): InboundMessage | null {
    // Skip bot messages (including our own)
    if (msg.author.bot) return null;

    const isDM = !msg.guild;
    const isMentioned = msg.mentions.has(this.resolvedBotId);
    const hasSession = this.hasActiveSession(msg.author.id);

    // Respond to DMs, mentions, or follow-ups from users in active sessions
    if (!isDM && !isMentioned && !hasSession) return null;

    // Strip bot mention from text
    let text = msg.content;
    if (isMentioned && this.resolvedBotId) {
      text = text.replace(new RegExp(`<@!?${this.resolvedBotId}>`, "g"), "").trim();
    }

    if (!text) return null;

    return {
      channel: "discord",
      chatId: msg.channel.id,
      senderId: msg.author.id,
      senderName: msg.author.displayName || msg.author.username,
      text,
      messageType: MessageType.TEXT,
      timestamp: msg.createdAt,
      raw: {},
    };
  }
}
