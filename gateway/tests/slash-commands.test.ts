import { describe, it, expect } from "vitest";
import { buildSlashCommands, getCommandNames } from "../src/slash-commands.js";

describe("slash-commands", () => {
  it("builds all expected commands", () => {
    const commands = buildSlashCommands();
    const names = commands.map((c) => c.name);
    expect(names).toContain("run");
    expect(names).toContain("agents");
    expect(names).toContain("status");
    expect(names).toContain("cancel");
    expect(names).toContain("logs");
    expect(names).toContain("machines");
  });

  it("run command has required agent option", () => {
    const run = buildSlashCommands().find((c) => c.name === "run")!;
    const json = run.toJSON();
    const agentOpt = json.options?.find((o: any) => o.name === "agent");
    expect(agentOpt).toBeDefined();
    expect(agentOpt!.required).toBe(true);
  });

  it("run command has optional machine option", () => {
    const run = buildSlashCommands().find((c) => c.name === "run")!;
    const json = run.toJSON();
    const machineOpt = json.options?.find((o: any) => o.name === "machine");
    expect(machineOpt).toBeDefined();
    expect(machineOpt!.required).toBeFalsy();
  });

  it("cancel command has required run_id option", () => {
    const cancel = buildSlashCommands().find((c) => c.name === "cancel")!;
    const json = cancel.toJSON();
    const opt = json.options?.find((o: any) => o.name === "run_id");
    expect(opt).toBeDefined();
    expect(opt!.required).toBe(true);
  });

  it("all commands have descriptions", () => {
    for (const cmd of buildSlashCommands()) {
      expect(cmd.description).toBeTruthy();
    }
  });

  it("all command names are lowercase", () => {
    for (const cmd of buildSlashCommands()) {
      expect(cmd.name).toBe(cmd.name.toLowerCase());
    }
  });

  it("getCommandNames returns all names", () => {
    const names = getCommandNames();
    expect(names).toHaveLength(6);
    expect(names).toContain("run");
    expect(names).toContain("machines");
  });

  it("commands serialize to valid JSON", () => {
    for (const cmd of buildSlashCommands()) {
      expect(() => cmd.toJSON()).not.toThrow();
    }
  });
});
