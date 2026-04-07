import { describe, it, expect, vi, beforeEach } from "vitest";
import { MessageType, type InboundMessage } from "../src/models.js";

/**
 * Tests for the Discord adapter's parseMessage logic.
 * We test the parsing logic directly since discord.js Client is hard to mock.
 * The parseMessage logic is extracted into a testable helper.
 */

interface MockMessage {
  author: { id: string; bot: boolean; displayName: string; username: string };
  guild: boolean | null;
  mentions: { has: (id: string) => boolean };
  content: string;
  channel: { id: string };
  createdAt: Date;
}

/** Reproduce parseMessage logic for testing without requiring discord.js Client. */
function parseMessage(
  msg: MockMessage,
  resolvedBotId: string,
  hasActiveSession: (senderId: string) => boolean,
): InboundMessage | null {
  if (msg.author.bot) return null;

  const isDM = !msg.guild;
  const isMentioned = msg.mentions.has(resolvedBotId);
  const hasSession = hasActiveSession(msg.author.id);

  if (!isDM && !isMentioned && !hasSession) return null;

  let text = msg.content;
  if (isMentioned && resolvedBotId) {
    text = text.replace(new RegExp(`<@!?${resolvedBotId}>`, "g"), "").trim();
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

function mockMsg(overrides: Partial<MockMessage> = {}): MockMessage {
  return {
    author: { id: "user-1", bot: false, displayName: "Santiago", username: "santiago_md11" },
    guild: { id: "guild-1" } as any,
    mentions: { has: () => false },
    content: "hello",
    channel: { id: "ch-1" },
    createdAt: new Date(),
    ...overrides,
  };
}

describe("Discord parseMessage logic", () => {
  const botId = "bot-123";
  const noSession = () => false;
  const withSession = () => true;

  it("filters bot messages", () => {
    const msg = mockMsg({ author: { id: "bot-1", bot: true, displayName: "Bot", username: "bot" } });
    expect(parseMessage(msg, botId, noSession)).toBeNull();
  });

  it("accepts DMs without mention", () => {
    const msg = mockMsg({ guild: null });
    const result = parseMessage(msg, botId, noSession);
    expect(result).not.toBeNull();
    expect(result!.text).toBe("hello");
  });

  it("accepts mentions in guild channels", () => {
    const msg = mockMsg({
      content: `<@${botId}> hey`,
      mentions: { has: (id: string) => id === botId },
    });
    const result = parseMessage(msg, botId, noSession);
    expect(result).not.toBeNull();
    expect(result!.text).toBe("hey");
  });

  it("strips bot mention with ! format", () => {
    const msg = mockMsg({
      content: `<@!${botId}> run agent`,
      mentions: { has: (id: string) => id === botId },
    });
    const result = parseMessage(msg, botId, noSession);
    expect(result!.text).toBe("run agent");
  });

  it("rejects guild messages without mention or session", () => {
    const msg = mockMsg();
    expect(parseMessage(msg, botId, noSession)).toBeNull();
  });

  it("accepts guild messages from users with active sessions", () => {
    const msg = mockMsg({ content: "2" });
    const result = parseMessage(msg, botId, withSession);
    expect(result).not.toBeNull();
    expect(result!.text).toBe("2");
  });

  it("returns null for empty text after stripping mention", () => {
    const msg = mockMsg({
      content: `<@${botId}>`,
      mentions: { has: (id: string) => id === botId },
    });
    expect(parseMessage(msg, botId, noSession)).toBeNull();
  });

  it("session checker receives correct sender ID", () => {
    const checker = vi.fn().mockReturnValue(true);
    const msg = mockMsg({ author: { id: "user-42", bot: false, displayName: "Test", username: "test" } });
    parseMessage(msg, botId, checker);
    expect(checker).toHaveBeenCalledWith("user-42");
  });

  it("preserves sender info in parsed message", () => {
    const msg = mockMsg({
      guild: null,
      author: { id: "user-99", bot: false, displayName: "Santiago", username: "santiago_md11" },
    });
    const result = parseMessage(msg, botId, noSession)!;
    expect(result.senderId).toBe("user-99");
    expect(result.senderName).toBe("Santiago");
    expect(result.channel).toBe("discord");
  });

  it("falls back to username when displayName is empty", () => {
    const msg = mockMsg({
      guild: null,
      author: { id: "user-1", bot: false, displayName: "", username: "fallback_user" },
    });
    const result = parseMessage(msg, botId, noSession)!;
    expect(result.senderName).toBe("fallback_user");
  });

  it("handles multiple mentions in same message", () => {
    const msg = mockMsg({
      content: `<@${botId}> hello <@${botId}>`,
      mentions: { has: (id: string) => id === botId },
    });
    const result = parseMessage(msg, botId, noSession)!;
    expect(result.text).toBe("hello");
  });
});
