import { describe, it, expect, vi, beforeEach } from "vitest";
import { VadgrAPIClient } from "../src/api-client.js";

describe("VadgrAPIClient", () => {
  let client: VadgrAPIClient;

  beforeEach(() => {
    client = new VadgrAPIClient("http://localhost:8000");
  });

  describe("validateId", () => {
    it("accepts valid UUID-style IDs", async () => {
      const mockFetch = vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({ id: "abc-123", status: "running" }),
      });
      vi.stubGlobal("fetch", mockFetch);

      await client.getRun("abc-123-def-456");
      expect(mockFetch).toHaveBeenCalled();
      vi.unstubAllGlobals();
    });

    it("accepts alphanumeric IDs", async () => {
      const mockFetch = vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({}),
      });
      vi.stubGlobal("fetch", mockFetch);

      await client.getRun("run123");
      expect(mockFetch).toHaveBeenCalled();
      vi.unstubAllGlobals();
    });

    it("rejects IDs with semicolons (command injection)", async () => {
      await expect(client.getRun("run;rm -rf /")).rejects.toThrow("Invalid ID");
    });

    it("rejects IDs with pipe (command injection)", async () => {
      await expect(client.cancelRun("run|cat /etc/passwd")).rejects.toThrow("Invalid ID");
    });

    it("rejects IDs with backticks (command injection)", async () => {
      await expect(client.resumeRun("`whoami`")).rejects.toThrow("Invalid ID");
    });

    it("rejects IDs with dollar sign (shell expansion)", async () => {
      await expect(client.getRun("$(whoami)")).rejects.toThrow("Invalid ID");
    });

    it("rejects IDs with path traversal", async () => {
      await expect(client.getRun("../../../etc/passwd")).rejects.toThrow("Invalid ID");
    });

    it("rejects empty IDs", async () => {
      await expect(client.getRun("")).rejects.toThrow("Invalid ID");
    });

    it("truncates long IDs in error message", async () => {
      const longId = "a".repeat(50) + ";evil";
      try {
        await client.getRun(longId);
      } catch (e: any) {
        expect(e.message.length).toBeLessThan(100);
      }
    });

    it("validates on runAgent", async () => {
      await expect(client.runAgent("id;evil", {})).rejects.toThrow("Invalid ID");
    });

    it("validates on getRunLogs", async () => {
      await expect(client.getRunLogs("id|evil")).rejects.toThrow("Invalid ID");
    });
  });

  describe("retry on server error", () => {
    it("retries on 500 and succeeds", async () => {
      let calls = 0;
      const mockFetch = vi.fn().mockImplementation(() => {
        calls++;
        if (calls < 3) return Promise.resolve({ ok: false, status: 500, text: () => "error" });
        return Promise.resolve({ ok: true, json: () => Promise.resolve([]) });
      });
      vi.stubGlobal("fetch", mockFetch);

      const result = await client.listAgents();
      expect(result).toEqual([]);
      expect(calls).toBe(3);
      vi.unstubAllGlobals();
    });

    it("throws on non-500 errors without retry", async () => {
      const mockFetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 404,
        text: () => Promise.resolve("not found"),
      });
      vi.stubGlobal("fetch", mockFetch);

      await expect(client.listAgents()).rejects.toThrow("API error 404");
      expect(mockFetch).toHaveBeenCalledTimes(1);
      vi.unstubAllGlobals();
    });
  });
});
