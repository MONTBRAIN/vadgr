import { describe, it, expect, vi, beforeEach } from "vitest";
import { MessageRouter } from "../src/router.js";
import { MessageType, type InboundMessage } from "../src/models.js";

function msg(text: string, senderId = "user-1", senderName = "Santiago"): InboundMessage {
  return {
    channel: "discord",
    chatId: "ch-1",
    senderId,
    senderName,
    text,
    messageType: MessageType.TEXT,
    timestamp: new Date(),
    raw: {},
  };
}

function mockApi() {
  return {
    listAgents: vi.fn().mockResolvedValue([
      {
        id: "agent-1",
        name: "QA Engineer",
        steps: [{ name: "Analyze" }, { name: "Test" }],
        input_schema: [
          { name: "repo_path", type: "text", required: true, label: "Repository Path", description: "Path to repo" },
        ],
      },
      {
        id: "agent-2",
        name: "Software Engineer",
        steps: [{ name: "Analyze" }, { name: "Fix" }],
        input_schema: [
          { name: "task", type: "text", required: true, label: "Task", description: "What to fix" },
          { name: "repo_path", type: "text", required: false, label: "Repo", description: "Path" },
        ],
      },
    ]),
    listRuns: vi.fn().mockResolvedValue([]),
    runAgent: vi.fn().mockResolvedValue({ run_id: "run-abc-123" }),
    cancelRun: vi.fn().mockResolvedValue({ status: "cancelled" }),
    resumeRun: vi.fn().mockResolvedValue({ message: "Resuming..." }),
    getRunLogs: vi.fn().mockResolvedValue([
      { message: "Step 1 started" },
      { message: "Step 1 done" },
    ]),
    getRun: vi.fn().mockResolvedValue({}),
  };
}

describe("MessageRouter", () => {
  describe("greetings", () => {
    it("lists agents on hey", async () => {
      const router = new MessageRouter(mockApi() as any);
      const result = await router.handle(msg("hey"));
      expect(result.response).toContain("QA Engineer");
      expect(result.response).toContain("Software Engineer");
      expect(result.response).toContain("Santiago");
    });

    it("responds to hola", async () => {
      const router = new MessageRouter(mockApi() as any);
      const result = await router.handle(msg("hola"));
      expect(result.response).toContain("QA Engineer");
    });
  });

  describe("help", () => {
    it("shows commands", async () => {
      const router = new MessageRouter(mockApi() as any);
      const result = await router.handle(msg("help"));
      expect(result.response).toContain("run");
      expect(result.response).toContain("status");
      expect(result.response).toContain("resume");
    });
  });

  describe("status", () => {
    it("shows idle when no runs", async () => {
      const router = new MessageRouter(mockApi() as any);
      const result = await router.handle(msg("status"));
      expect(result.response.toLowerCase()).toMatch(/idle|no runs/);
    });

    it("shows runs when active", async () => {
      const api = mockApi();
      api.listRuns.mockResolvedValue([{ id: "run-abc-123", agent_name: "QA Engineer", status: "running" }]);
      const router = new MessageRouter(api as any);
      const result = await router.handle(msg("status"));
      expect(result.response).toContain("QA Engineer");
      expect(result.response).toContain("running");
    });
  });

  describe("run agent", () => {
    it("asks for input when running by name", async () => {
      const router = new MessageRouter(mockApi() as any);
      const result = await router.handle(msg("run QA Engineer"));
      expect(result.response).toContain("Repository Path");
    });

    it("starts run after providing input", async () => {
      const api = mockApi();
      const router = new MessageRouter(api as any);
      await router.handle(msg("run QA Engineer"));
      const result = await router.handle(msg("/home/santiago/repo"));
      expect(result.response).toContain("Starting");
      expect(result.isAsync).toBe(true);
      expect(result.runId).toBe("run-abc-123");
      expect(api.runAgent).toHaveBeenCalled();
    });

    it("matches by number", async () => {
      const router = new MessageRouter(mockApi() as any);
      await router.handle(msg("hey"));
      const result = await router.handle(msg("run 1"));
      expect(result.response).toContain("Repository Path");
    });

    it("fuzzy matches", async () => {
      const router = new MessageRouter(mockApi() as any);
      const result = await router.handle(msg("run qa"));
      expect(result.response).toContain("Repository Path");
    });

    it("reports unknown agent", async () => {
      const router = new MessageRouter(mockApi() as any);
      const result = await router.handle(msg("run NonexistentAgent"));
      expect(result.response.toLowerCase()).toContain("no agent");
    });
  });

  describe("sanitization", () => {
    it("sanitizes collected inputs", async () => {
      const api = mockApi();
      const sanitize = (v: string) => v.replace(/[;&|]/g, "");
      const router = new MessageRouter(api as any, sanitize);
      await router.handle(msg("run QA Engineer"));
      await router.handle(msg("/home/repo; rm -rf /"));
      expect(api.runAgent).toHaveBeenCalled();
      const inputs = api.runAgent.mock.calls[0][1];
      expect(inputs.repo_path).not.toContain(";");
    });
  });

  describe("global commands", () => {
    it("cancels a run", async () => {
      const router = new MessageRouter(mockApi() as any);
      const result = await router.handle(msg("cancel abc123"));
      expect(result.response.toLowerCase()).toContain("cancel");
    });

    it("resumes a run", async () => {
      const router = new MessageRouter(mockApi() as any);
      const result = await router.handle(msg("resume abc123"));
      expect(result.response.toLowerCase()).toContain("resum");
    });

    it("shows logs", async () => {
      const router = new MessageRouter(mockApi() as any);
      const result = await router.handle(msg("logs abc123"));
      expect(result.response).toContain("Step 1");
    });
  });

  describe("session isolation", () => {
    it("isolates users", async () => {
      const router = new MessageRouter(mockApi() as any);
      await router.handle(msg("run QA Engineer", "user-a"));
      const result = await router.handle(msg("status", "user-b"));
      expect(result.response.toLowerCase()).toMatch(/idle|no runs/);
    });
  });

  describe("hasActiveSession", () => {
    it("returns false for unknown sender", () => {
      const router = new MessageRouter(mockApi() as any);
      expect(router.hasActiveSession("never-seen")).toBe(false);
    });

    it("returns true after greeting (AWAITING_AGENT)", async () => {
      const router = new MessageRouter(mockApi() as any);
      await router.handle(msg("hey"));
      expect(router.hasActiveSession("user-1")).toBe(true);
    });

    it("returns true while collecting inputs (AWAITING_INPUTS)", async () => {
      const router = new MessageRouter(mockApi() as any);
      await router.handle(msg("hey"));
      await router.handle(msg("1")); // select QA Engineer -> asks for repo_path
      expect(router.hasActiveSession("user-1")).toBe(true);
    });

    it("returns false after run starts (back to IDLE)", async () => {
      const router = new MessageRouter(mockApi() as any);
      await router.handle(msg("hey"));
      await router.handle(msg("1"));          // select agent
      await router.handle(msg("/home/repo")); // provide repo_path -> starts run
      expect(router.hasActiveSession("user-1")).toBe(false);
    });

    it("isolates session state between users", async () => {
      const router = new MessageRouter(mockApi() as any);
      await router.handle(msg("hey", "user-a"));
      expect(router.hasActiveSession("user-a")).toBe(true);
      expect(router.hasActiveSession("user-b")).toBe(false);
    });
  });

  describe("selectAgent with run prefix", () => {
    it("strips 'run ' prefix in AWAITING_AGENT state", async () => {
      const router = new MessageRouter(mockApi() as any);
      await router.handle(msg("hey"));
      const result = await router.handle(msg("run 1"));
      expect(result.response).toContain("Repository Path");
    });

    it("handles 'RUN' case-insensitive", async () => {
      const router = new MessageRouter(mockApi() as any);
      await router.handle(msg("hey"));
      const result = await router.handle(msg("RUN QA Engineer"));
      expect(result.response).toContain("Repository Path");
    });

    it("works without run prefix", async () => {
      const router = new MessageRouter(mockApi() as any);
      await router.handle(msg("hey"));
      const result = await router.handle(msg("1"));
      expect(result.response).toContain("Repository Path");
    });

    it("handles agent name without number", async () => {
      const router = new MessageRouter(mockApi() as any);
      await router.handle(msg("hey"));
      const result = await router.handle(msg("QA Engineer"));
      expect(result.response).toContain("Repository Path");
    });
  });

  describe("sanitization", () => {
    it("applies sanitize function to collected inputs", async () => {
      const sanitize = vi.fn((v: string) => v.replace(/[;&]/g, ""));
      const router = new MessageRouter(mockApi() as any, sanitize);
      await router.handle(msg("hey"));
      await router.handle(msg("1"));
      await router.handle(msg("/home/repo;rm -rf /"));
      expect(sanitize).toHaveBeenCalledWith("/home/repo;rm -rf /");
    });
  });
});
