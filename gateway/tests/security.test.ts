import { describe, it, expect, beforeEach } from "vitest";
import { SecurityGuard, SILENT_REJECT, defaultSecurityConfig, type SecurityConfig } from "../src/security.js";
import { MessageType, type InboundMessage } from "../src/models.js";

function msg(overrides: Partial<InboundMessage> = {}): InboundMessage {
  return {
    channel: "discord",
    chatId: "ch-1",
    senderId: "user-1",
    senderName: "Test",
    text: "hello",
    messageType: MessageType.TEXT,
    timestamp: new Date(),
    raw: {},
    ...overrides,
  };
}

describe("SecurityGuard", () => {
  describe("allowlist", () => {
    it("allows known sender", () => {
      const guard = new SecurityGuard({ ...defaultSecurityConfig(), allowedSenders: ["user-1"] });
      expect(guard.check(msg())).toBeNull();
    });

    it("silently rejects unknown sender", () => {
      const guard = new SecurityGuard({ ...defaultSecurityConfig(), allowedSenders: ["user-1"] });
      expect(guard.check(msg({ senderId: "stranger" }))).toBe(SILENT_REJECT);
    });

    it("allows everyone when allowlist empty", () => {
      const guard = new SecurityGuard(defaultSecurityConfig());
      expect(guard.check(msg({ senderId: "anyone" }))).toBeNull();
    });
  });

  describe("rate limiting", () => {
    it("passes under limit", () => {
      const guard = new SecurityGuard({ ...defaultSecurityConfig(), rateLimit: 3 });
      expect(guard.check(msg())).toBeNull();
      expect(guard.check(msg())).toBeNull();
      expect(guard.check(msg())).toBeNull();
    });

    it("rejects over limit", () => {
      const guard = new SecurityGuard({ ...defaultSecurityConfig(), rateLimit: 2, rateWindow: 3600 });
      guard.check(msg());
      guard.check(msg());
      const result = guard.check(msg());
      expect(result).toBeTypeOf("string");
      expect(result).toContain("Slow down");
    });

    it("isolates per sender", () => {
      const guard = new SecurityGuard({ ...defaultSecurityConfig(), rateLimit: 1 });
      expect(guard.check(msg({ senderId: "a" }))).toBeNull();
      expect(guard.check(msg({ senderId: "b" }))).toBeNull();
      expect(guard.check(msg({ senderId: "a" }))).toContain("Slow down");
    });
  });

  describe("message length", () => {
    it("rejects long messages", () => {
      const guard = new SecurityGuard(defaultSecurityConfig());
      const result = guard.check(msg({ text: "x".repeat(3000) }));
      expect(result).toContain("too long");
    });
  });

  describe("sanitization", () => {
    it("strips shell chars", () => {
      const guard = new SecurityGuard(defaultSecurityConfig());
      expect(guard.sanitizeInput("path; rm -rf /")).toBe("path rm -rf /");
      expect(guard.sanitizeInput("hello | cat")).toBe("hello  cat");
      expect(guard.sanitizeInput("$(whoami)")).toBe("whoami");
    });

    it("leaves clean input unchanged", () => {
      const guard = new SecurityGuard(defaultSecurityConfig());
      expect(guard.sanitizeInput("/home/user/repo")).toBe("/home/user/repo");
    });
  });

  describe("audit log", () => {
    it("writes audit entries", async () => {
      const fs = await import("fs");
      const path = "/tmp/test-audit-" + Date.now() + ".jsonl";
      const guard = new SecurityGuard({ ...defaultSecurityConfig(), auditLogPath: path });
      guard.check(msg({ text: "run qa" }));
      const content = fs.readFileSync(path, "utf-8");
      const entry = JSON.parse(content.trim());
      expect(entry.senderId).toBe("user-1");
      expect(entry.text).toBe("run qa");
      fs.unlinkSync(path);
    });
  });

  describe("sanitizeInput hardening", () => {
    it("strips shell metacharacters", () => {
      const guard = new SecurityGuard(defaultSecurityConfig());
      expect(guard.sanitizeInput("hello;world")).toBe("helloworld");
      expect(guard.sanitizeInput("$(whoami)")).toBe("whoami");
      expect(guard.sanitizeInput("a|b&c")).toBe("abc");
      expect(guard.sanitizeInput("test`cmd`")).toBe("testcmd");
    });

    it("strips angle brackets (XSS prevention)", () => {
      const guard = new SecurityGuard(defaultSecurityConfig());
      expect(guard.sanitizeInput("<script>alert(1)</script>")).toBe("scriptalert1/script");
    });

    it("strips backslashes (escape sequences)", () => {
      const guard = new SecurityGuard(defaultSecurityConfig());
      expect(guard.sanitizeInput("path\\to\\file")).toBe("pathtofile");
    });

    it("preserves safe characters", () => {
      const guard = new SecurityGuard(defaultSecurityConfig());
      expect(guard.sanitizeInput("hello world 123")).toBe("hello world 123");
      expect(guard.sanitizeInput("/home/user/repo")).toBe("/home/user/repo");
      expect(guard.sanitizeInput("key=value")).toBe("key=value");
      expect(guard.sanitizeInput("https://github.com/org/repo")).toBe("https://github.com/org/repo");
    });

    it("trims whitespace", () => {
      const guard = new SecurityGuard(defaultSecurityConfig());
      expect(guard.sanitizeInput("  hello  ")).toBe("hello");
    });
  });
});
