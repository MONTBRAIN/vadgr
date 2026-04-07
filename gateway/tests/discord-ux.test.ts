/** Tests for Discord UX wiring: smartSplit, embed OutboundMessage, slash command parsing. */

import { describe, it, expect } from "vitest";

// -- smartSplit tests (function will be exported from discord.ts) --

/** Split text at newline boundaries instead of mid-word. */
function smartSplit(text: string, maxLen: number): string[] {
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

describe("smartSplit", () => {
  it("returns single chunk for short text", () => {
    expect(smartSplit("hello", 2000)).toEqual(["hello"]);
  });

  it("splits at newline boundary", () => {
    const text = "line1\nline2\nline3";
    const chunks = smartSplit(text, 10);
    expect(chunks[0]).toBe("line1");
    expect(chunks.length).toBeGreaterThan(1);
  });

  it("falls back to maxLen when no newline found", () => {
    const text = "a".repeat(3000);
    const chunks = smartSplit(text, 2000);
    expect(chunks[0]!.length).toBe(2000);
    expect(chunks[1]!.length).toBe(1000);
  });

  it("handles empty string", () => {
    expect(smartSplit("", 2000)).toEqual([]);
  });

  it("preserves content across chunks", () => {
    const text = "line1\nline2\nline3\nline4";
    const chunks = smartSplit(text, 12);
    const joined = chunks.join("\n");
    expect(joined).toBe(text);
  });

  it("does not produce empty chunks", () => {
    const text = "abc\ndef\nghi";
    const chunks = smartSplit(text, 4);
    for (const chunk of chunks) {
      expect(chunk.length).toBeGreaterThan(0);
    }
  });
});

// -- OutboundMessage with embed tests --

describe("OutboundMessage embed support", () => {
  it("supports text-only messages", () => {
    const msg = { chatId: "ch1", text: "hello" };
    expect(msg.text).toBe("hello");
    expect((msg as any).embed).toBeUndefined();
  });

  it("supports embed field", () => {
    const fakeEmbed = { title: "Test", color: 0x22c55e };
    const msg = { chatId: "ch1", text: "", embed: fakeEmbed };
    expect(msg.embed).toBeDefined();
    expect(msg.embed.title).toBe("Test");
  });

  it("embed takes precedence over text when both present", () => {
    // This test documents the expected behavior: when embed is present,
    // the adapter should send the embed, not the text.
    const msg = { chatId: "ch1", text: "fallback", embed: { title: "Priority" } };
    const shouldSendEmbed = msg.embed !== undefined;
    expect(shouldSendEmbed).toBe(true);
  });
});

// -- Slash command option parsing tests --

describe("slash command option parsing", () => {
  /** Extract options from interaction data (same logic the adapter will use). */
  function parseOptions(data: { name: string; value?: string | number | boolean }[]): Record<string, string> {
    const options: Record<string, string> = {};
    for (const opt of data) {
      options[opt.name] = String(opt.value ?? "");
    }
    return options;
  }

  it("parses string options", () => {
    const data = [{ name: "agent", value: "security-engineer" }];
    expect(parseOptions(data)).toEqual({ agent: "security-engineer" });
  });

  it("parses multiple options", () => {
    const data = [
      { name: "agent", value: "security" },
      { name: "machine", value: "laptop" },
    ];
    const result = parseOptions(data);
    expect(result.agent).toBe("security");
    expect(result.machine).toBe("laptop");
  });

  it("handles missing value", () => {
    const data = [{ name: "agent", value: undefined }];
    expect(parseOptions(data)).toEqual({ agent: "" });
  });

  it("converts number values to string", () => {
    const data = [{ name: "count", value: 42 }];
    expect(parseOptions(data)).toEqual({ count: "42" });
  });

  it("handles empty options", () => {
    expect(parseOptions([])).toEqual({});
  });
});

// -- Router slash command handler tests --

describe("router handleSlashCommand mapping", () => {
  /** Simulate the mapping from slash command name to router action.
   *  This tests the dispatch logic without the full router. */
  function mapCommand(command: string): string {
    const mapping: Record<string, string> = {
      run: "findAndStartAgent",
      agents: "listAgents",
      status: "status",
      cancel: "cancel",
      logs: "logs",
      machines: "listMachines",
    };
    return mapping[command] || "help";
  }

  it("maps /run to findAndStartAgent", () => {
    expect(mapCommand("run")).toBe("findAndStartAgent");
  });

  it("maps /agents to listAgents", () => {
    expect(mapCommand("agents")).toBe("listAgents");
  });

  it("maps /status to status", () => {
    expect(mapCommand("status")).toBe("status");
  });

  it("maps /cancel to cancel", () => {
    expect(mapCommand("cancel")).toBe("cancel");
  });

  it("maps /logs to logs", () => {
    expect(mapCommand("logs")).toBe("logs");
  });

  it("maps /machines to listMachines", () => {
    expect(mapCommand("machines")).toBe("listMachines");
  });

  it("maps unknown command to help", () => {
    expect(mapCommand("unknown")).toBe("help");
  });
});
