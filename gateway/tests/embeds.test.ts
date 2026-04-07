import { describe, it, expect } from "vitest";
import {
  greetingEmbed,
  agentListEmbed,
  runStartedEmbed,
  progressEmbed,
  runCompletedEmbed,
  runFailedEmbed,
  statusEmbed,
  machinesEmbed,
  helpEmbed,
  errorEmbed,
  progressBar,
} from "../src/embeds.js";

describe("embeds", () => {
  describe("progressBar", () => {
    it("shows empty bar for 0 progress", () => {
      expect(progressBar(0, 5)).toBe("\u2591".repeat(10));
    });

    it("shows full bar for complete", () => {
      expect(progressBar(5, 5)).toBe("\u2588".repeat(10));
    });

    it("shows partial bar", () => {
      const bar = progressBar(3, 6);
      expect(bar).toContain("\u2588");
      expect(bar).toContain("\u2591");
      expect(bar).toHaveLength(10);
    });

    it("handles zero total", () => {
      expect(progressBar(0, 0)).toBe("\u2591".repeat(10));
    });

    it("supports custom length", () => {
      expect(progressBar(5, 5, 20)).toBe("\u2588".repeat(20));
    });
  });

  describe("greetingEmbed", () => {
    it("creates embed with agents and machines", () => {
      const embed = greetingEmbed(
        "Santiago",
        [{ name: "security", machineName: "laptop", steps: [{ name: "s1" }] }],
        [{ name: "laptop", agentCount: 1 }],
      );
      const json = embed.toJSON();
      expect(json.title).toBe("Hey Santiago!");
      expect(json.fields).toHaveLength(2); // Machines + Agents
    });

    it("shows 'no agents' when empty", () => {
      const embed = greetingEmbed("Santiago", [], []);
      expect(embed.toJSON().description).toContain("No agents");
    });
  });

  describe("agentListEmbed", () => {
    it("lists agents with descriptions", () => {
      const embed = agentListEmbed([
        { name: "security", description: "Audits code", machineName: "laptop", steps: [{ name: "s1" }] },
        { name: "data", description: "Analyzes data" },
      ]);
      expect(embed.toJSON().fields).toHaveLength(2);
    });

    it("handles empty list", () => {
      const embed = agentListEmbed([]);
      expect(embed.toJSON().description).toContain("No agents");
    });

    it("limits to 25 agents (Discord embed field limit)", () => {
      const agents = Array.from({ length: 30 }, (_, i) => ({ name: `agent-${i}` }));
      const embed = agentListEmbed(agents);
      expect(embed.toJSON().fields!.length).toBeLessThanOrEqual(25);
    });
  });

  describe("runStartedEmbed", () => {
    it("shows agent name and run ID", () => {
      const embed = runStartedEmbed("security", "abcdef1234567890", "laptop");
      const json = embed.toJSON();
      expect(json.title).toBe("Starting security");
      expect(json.description).toContain("abcdef12");
      expect(json.description).toContain("laptop");
      expect(json.color).toBe(0xeab308); // yellow
    });

    it("works without machine name", () => {
      const embed = runStartedEmbed("security", "abcdef12");
      expect(embed.toJSON().title).toBe("Starting security");
    });
  });

  describe("progressEmbed", () => {
    it("shows step progress", () => {
      const embed = progressEmbed("security", "abc123", 3, 5, "Scanning deps", "laptop");
      const json = embed.toJSON();
      expect(json.description).toContain("3/5");
      expect(json.description).toContain("Scanning deps");
      expect(json.color).toBe(0xeab308);
    });
  });

  describe("runCompletedEmbed", () => {
    it("shows outputs as fields", () => {
      const embed = runCompletedEmbed("security", "abc123", {
        findings: "2 critical, 5 warnings",
        report: "output/report.pdf",
      });
      const json = embed.toJSON();
      expect(json.title).toContain("finished");
      expect(json.color).toBe(0x22c55e); // green
      expect(json.fields).toHaveLength(2);
    });

    it("skips long outputs", () => {
      const embed = runCompletedEmbed("security", "abc123", {
        short: "ok",
        long: "x".repeat(600),
      });
      expect(embed.toJSON().fields).toHaveLength(1); // only short
    });
  });

  describe("runFailedEmbed", () => {
    it("shows error and resume hint", () => {
      const embed = runFailedEmbed("security", "abc123", "Timeout in step 3");
      const json = embed.toJSON();
      expect(json.title).toContain("failed");
      expect(json.color).toBe(0xef4444); // red
      expect(json.description).toContain("Timeout");
      expect(json.description).toContain("resume");
    });
  });

  describe("statusEmbed", () => {
    it("shows runs with status icons", () => {
      const embed = statusEmbed([
        { id: "run1abc", agent_name: "security", status: "completed" },
        { id: "run2def", agent_name: "data", status: "failed" },
        { id: "run3ghi", agent_name: "software", status: "running" },
      ]);
      const json = embed.toJSON();
      expect(json.description).toContain("\u{2705}"); // green check
      expect(json.description).toContain("\u{274C}"); // red x
      expect(json.description).toContain("\u{1F7E1}"); // yellow circle
    });

    it("shows idle message when no runs", () => {
      const embed = statusEmbed([]);
      expect(embed.toJSON().description).toContain("idle");
    });
  });

  describe("machinesEmbed", () => {
    it("shows connected machines", () => {
      const embed = machinesEmbed([
        { name: "laptop", agentCount: 3, connectedAt: new Date(), activeRuns: 1 },
      ]);
      const json = embed.toJSON();
      expect(json.fields).toHaveLength(1);
      expect(json.fields![0]!.name).toContain("laptop");
    });

    it("shows message when no machines", () => {
      const embed = machinesEmbed([]);
      expect(embed.toJSON().description).toContain("No machines");
    });
  });

  describe("helpEmbed", () => {
    it("lists all commands", () => {
      const embed = helpEmbed();
      const json = embed.toJSON();
      expect(json.fields!.length).toBeGreaterThanOrEqual(6);
    });
  });

  describe("errorEmbed", () => {
    it("shows error with red color", () => {
      const embed = errorEmbed("Oops", "Something went wrong");
      const json = embed.toJSON();
      expect(json.color).toBe(0xef4444);
      expect(json.title).toBe("Oops");
    });
  });
});
