/** Discord adapter using discord.js. Handles DMs, mentions, and slash commands. */

import {
  Client,
  GatewayIntentBits,
  Message,
  Partials,
  type ChatInputCommandInteraction,
  type EmbedBuilder,
} from "discord.js";
import type { ChannelAdapter, MessageHandler, SessionChecker } from "./base.js";
import type { OutboundMessage } from "../models.js";
import { MessageType, type InboundMessage } from "../models.js";
import { registerSlashCommands } from "../slash-commands.js";

export interface DiscordConfig {
  botToken: string;
  botId?: string;
}

export class DiscordAdapter implements ChannelAdapter {
  readonly name = "discord";
  private client: Client;
  private config: DiscordConfig;
  private handler: MessageHandler | null = null;
  private resolvedBotId: string = "";
  private hasActiveSession: SessionChecker = () => false;

  /** Slash command interaction handler (set by Gateway). */
  onSlashCommand?: (
    command: string,
    options: Record<string, string>,
    senderId: string,
    senderName: string,
    chatId: string,
  ) => Promise<{ text?: string; embed?: EmbedBuilder }>;

  constructor(config: DiscordConfig) {
    this.config = config;
    this.client = new Client({
      intents: [
        GatewayIntentBits.Guilds,
        GatewayIntentBits.GuildMessages,
        GatewayIntentBits.DirectMessages,
        GatewayIntentBits.MessageContent,
      ],
      partials: [Partials.Channel],
    });
  }

  async connect(): Promise<void> {
    return new Promise((resolve, reject) => {
      this.client.once("ready", async () => {
        this.resolvedBotId = this.client.user?.id || this.config.botId || "";
        console.log(`[Discord] Connected as ${this.client.user?.tag} (${this.resolvedBotId})`);

        // Register slash commands
        try {
          await registerSlashCommands(this.config.botToken, this.resolvedBotId);
        } catch (err: any) {
          console.error(`[Discord] Failed to register slash commands: ${err.message}`);
        }

        resolve();
      });

      // Text message handler
      this.client.on("messageCreate", async (msg: Message) => {
        if (!this.handler) return;
        const parsed = this.parseMessage(msg);
        if (parsed) await this.handler(parsed);
      });

      // Slash command handler
      this.client.on("interactionCreate", async (interaction) => {
        if (!interaction.isChatInputCommand()) return;
        await this.handleSlashCommand(interaction);
      });

      this.client.login(this.config.botToken).catch(reject);
    });
  }

  async disconnect(): Promise<void> {
    await this.client.destroy();
  }

  async sendMessage(message: OutboundMessage): Promise<void> {
    const channel = await this.client.channels.fetch(message.chatId);
    if (!channel || !channel.isTextBased() || !("send" in channel)) return;

    const sendable = channel as any;

    // Send embed if provided
    if (message.embed) {
      await sendable.send({ embeds: [message.embed] });
      return;
    }

    // Plain text with smart splitting at newlines
    const text = message.text;
    if (text.length <= 2000) {
      await sendable.send(text);
    } else {
      for (const chunk of smartSplit(text, 2000)) {
        await sendable.send(chunk);
      }
    }
  }

  registerHandler(handler: MessageHandler): void {
    this.handler = handler;
  }

  setSessionChecker(checker: SessionChecker): void {
    this.hasActiveSession = checker;
  }

  private async handleSlashCommand(interaction: ChatInputCommandInteraction): Promise<void> {
    if (!this.onSlashCommand) {
      await interaction.reply({ content: "Commands not ready yet.", ephemeral: true });
      return;
    }

    const options: Record<string, string> = {};
    for (const opt of interaction.options.data) {
      options[opt.name] = String(opt.value ?? "");
    }

    try {
      await interaction.deferReply();

      const result = await this.onSlashCommand(
        interaction.commandName,
        options,
        interaction.user.id,
        interaction.user.displayName || interaction.user.username,
        interaction.channelId,
      );

      if (result.embed) {
        await interaction.editReply({ embeds: [result.embed] });
      } else {
        await interaction.editReply({ content: result.text || "Done." });
      }
    } catch (err: any) {
      const content = `Error: ${err.message}`;
      try {
        await interaction.editReply({ content });
      } catch {
        // Interaction may have expired
      }
    }
  }

  private parseMessage(msg: Message): InboundMessage | null {
    if (msg.author.bot) return null;

    const isDM = !msg.guild;
    const isMentioned = msg.mentions.has(this.resolvedBotId);
    const hasSession = this.hasActiveSession(msg.author.id);


    // Also treat literal @BotName as a mention (typed manually, not via picker)
    const botName = this.client.user?.displayName || this.client.user?.username || "";
    const isLiteralMention = botName
      ? new RegExp(`^@${botName}\\b`, "i").test(msg.content)
      : false;

    if (!isDM && !isMentioned && !isLiteralMention && !hasSession) return null;

    let text = msg.content;
    // Strip Discord mention format: <@botId>, <@!botId>, and <@&roleId>
    if (isMentioned) {
      text = text.replace(/<@[!&]?[\w-]+>/g, "").trim();
    }
    // Strip literal @BotName prefix (typed manually, not via mention picker)
    if (botName) {
      text = text.replace(new RegExp(`^@${botName}\\b`, "i"), "").trim();
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

/** Split text at newline boundaries instead of mid-word. Exported for testing. */
export function smartSplit(text: string, maxLen: number): string[] {
  const chunks: string[] = [];
  let remaining = text;

  while (remaining.length > maxLen) {
    let splitAt = remaining.lastIndexOf("\n", maxLen);
    if (splitAt <= 0) splitAt = maxLen;
    chunks.push(remaining.slice(0, splitAt));
    remaining = remaining.slice(splitAt).replace(/^\n/, "");
  }

  if (remaining) chunks.push(remaining);
  return chunks;
}
