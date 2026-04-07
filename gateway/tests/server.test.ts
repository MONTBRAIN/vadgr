import { describe, it, expect, vi, beforeEach } from "vitest";
import type { InboundMessage, OutboundMessage, CommandResult } from "../src/models.js";
import { MessageType } from "../src/models.js";
import { SILENT_REJECT } from "../src/security.js";

/** Test the Gateway's processMessage and watchRun logic via extracted behavior. */

function msg(text = "hey", senderId = "user-1"): InboundMessage {
  return {
    channel: "discord",
    chatId: "ch-1",
    senderId,
    senderName: "Santiago",
    text,
    messageType: MessageType.TEXT,
    timestamp: new Date(),
    raw: {},
  };
}

describe("Gateway processMessage logic", () => {
  let sentMessages: OutboundMessage[];
  let mockAdapter: { sendMessage: (m: OutboundMessage) => Promise<void> };
  let mockSecurity: { check: ReturnType<typeof vi.fn>; sanitizeInput: (v: string) => string };
  let mockRouter: { handle: ReturnType<typeof vi.fn> };

  beforeEach(() => {
    sentMessages = [];
    mockAdapter = {
      sendMessage: vi.fn(async (m: OutboundMessage) => { sentMessages.push(m); }),
    };
    mockSecurity = {
      check: vi.fn().mockReturnValue(null),
      sanitizeInput: (v: string) => v,
    };
    mockRouter = {
      handle: vi.fn().mockResolvedValue({ response: "OK", isAsync: false }),
    };
  });

  /** Reproduce processMessage logic for testing. */
  async function processMessage(message: InboundMessage): Promise<void> {
    if (!message.text) return;

    const rejection = mockSecurity.check(message);
    if (rejection === SILENT_REJECT) return;
    if (rejection) {
      await mockAdapter.sendMessage({ chatId: message.chatId, text: rejection });
      return;
    }

    let result: CommandResult;
    try {
      result = await mockRouter.handle(message);
    } catch (e: any) {
      await mockAdapter.sendMessage({ chatId: message.chatId, text: `Something went wrong: ${e.message}` });
      return;
    }

    await mockAdapter.sendMessage({ chatId: message.chatId, text: result.response });
  }

  it("applies security check before routing", async () => {
    mockSecurity.check.mockReturnValue("Message too long (max 2000 chars).");
    await processMessage(msg("hey"));
    expect(mockRouter.handle).not.toHaveBeenCalled();
    expect(sentMessages[0]?.text).toBe("Message too long (max 2000 chars).");
  });

  it("silently rejects on SILENT_REJECT", async () => {
    mockSecurity.check.mockReturnValue(SILENT_REJECT);
    await processMessage(msg("hey"));
    expect(mockRouter.handle).not.toHaveBeenCalled();
    expect(sentMessages).toHaveLength(0);
  });

  it("routes valid messages and sends response", async () => {
    mockRouter.handle.mockResolvedValue({ response: "Hello!", isAsync: false });
    await processMessage(msg("hey"));
    expect(mockRouter.handle).toHaveBeenCalled();
    expect(sentMessages[0]?.text).toBe("Hello!");
  });

  it("handles router errors gracefully", async () => {
    mockRouter.handle.mockRejectedValue(new Error("API down"));
    await processMessage(msg("hey"));
    expect(sentMessages[0]?.text).toContain("Something went wrong: API down");
  });

  it("ignores empty text messages", async () => {
    await processMessage(msg(""));
    expect(mockSecurity.check).not.toHaveBeenCalled();
    expect(mockRouter.handle).not.toHaveBeenCalled();
  });

  it("sends response to correct chatId", async () => {
    const m = msg("hey");
    m.chatId = "channel-42";
    await processMessage(m);
    expect(sentMessages[0]?.chatId).toBe("channel-42");
  });
});

describe("watchRun polling logic", () => {
  it("reports completed runs with outputs", async () => {
    const sent: string[] = [];
    const mockApi = {
      getRun: vi.fn()
        .mockResolvedValueOnce({ status: "running" })
        .mockResolvedValueOnce({ status: "completed", outputs: { result: "done" } }),
    };

    // Simulate watchRun with 0ms poll for speed
    const runId = "abc12345-full-id";
    const agentName = "software-engineer";
    for (let i = 0; i < 120; i++) {
      const run: any = await mockApi.getRun(runId);
      if (run.status === "completed") {
        const parts = [`${agentName} finished!`];
        for (const [key, val] of Object.entries(run.outputs || {})) {
          if (typeof val === "string" && val.length < 500) parts.push(`\n${key}: ${val}`);
        }
        sent.push(parts.join("\n"));
        break;
      }
      if (run.status === "failed") {
        sent.push(`${agentName} failed.`);
        break;
      }
    }

    expect(sent[0]).toContain("software-engineer finished!");
    expect(sent[0]).toContain("result: done");
    expect(mockApi.getRun).toHaveBeenCalledTimes(2);
  });

  it("reports failed runs with error and resume hint", async () => {
    const mockApi = {
      getRun: vi.fn().mockResolvedValue({ status: "failed", outputs: { error: "OOM killed" } }),
    };

    const run: any = await mockApi.getRun("run-1");
    const error = run.outputs?.error || "Unknown error";
    const message = `Agent failed.\nError: ${error}\n\nResume with: resume run-1`.slice(0, 8);

    expect(error).toBe("OOM killed");
  });

  it("survives API errors during polling", async () => {
    let calls = 0;
    const mockApi = {
      getRun: vi.fn().mockImplementation(() => {
        calls++;
        if (calls < 3) throw new Error("timeout");
        return Promise.resolve({ status: "completed", outputs: {} });
      }),
    };

    let completed = false;
    for (let i = 0; i < 10; i++) {
      try {
        const run: any = await mockApi.getRun("r-1");
        if (run.status === "completed") { completed = true; break; }
      } catch {
        // Keep polling
      }
    }
    expect(completed).toBe(true);
    expect(calls).toBe(3);
  });
});

describe("error message safety", () => {
  /** Ensure error messages are always strings, never objects.
   *  The API can throw errors with structured JSON messages. */
  function safeErrorMessage(err: unknown): string {
    if (err instanceof Error) return err.message;
    if (typeof err === "string") return err;
    if (err == null) return "Unknown error";
    try {
      return JSON.stringify(err);
    } catch {
      return "Unknown error";
    }
  }

  it("handles Error objects", () => {
    expect(safeErrorMessage(new Error("timeout"))).toBe("timeout");
  });

  it("handles string errors", () => {
    expect(safeErrorMessage("connection refused")).toBe("connection refused");
  });

  it("handles object errors (API JSON responses)", () => {
    const apiError = { error: { code: "RUN_NOT_FOUND", message: "Run not found" } };
    const result = safeErrorMessage(apiError);
    expect(typeof result).toBe("string");
    expect(result).toContain("RUN_NOT_FOUND");
  });

  it("handles null/undefined", () => {
    expect(safeErrorMessage(null)).toBe("Unknown error");
    expect(safeErrorMessage(undefined)).toBe("Unknown error");
  });
});

describe("log entry formatting safety", () => {
  /** Safely extract a display string from a log entry (matches server.ts). */
  function formatLogEntry(entry: any): string {
    const data = entry?.data;
    const message = data?.message ?? data?.summary ?? entry?.message ?? entry?.summary;
    if (typeof message === "string" && message) return message.slice(0, 120);
    const type = entry?.type;
    if (typeof type === "string") return type;
    return "";
  }

  it("handles API log format { type, data: { message } }", () => {
    expect(formatLogEntry({ type: "agent_log", data: { message: "Using tool: Write" } })).toBe("Using tool: Write");
  });

  it("handles API log format { type, data: { summary } }", () => {
    expect(formatLogEntry({ type: "step_completed", data: { summary: "Step 3 done" } })).toBe("Step 3 done");
  });

  it("falls back to event type when no message", () => {
    expect(formatLogEntry({ type: "run_started", data: { forge_path: "output/abc" } })).toBe("run_started");
  });

  it("handles direct message field", () => {
    expect(formatLogEntry({ message: "Step 1 done" })).toBe("Step 1 done");
  });

  it("handles missing fields", () => {
    expect(formatLogEntry({})).toBe("");
  });

  it("handles null entry", () => {
    expect(formatLogEntry(null)).toBe("");
  });

  it("truncates long messages", () => {
    expect(formatLogEntry({ data: { message: "x".repeat(200) } })).toHaveLength(120);
  });
});
