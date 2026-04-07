/** Discord embed builders for rich message formatting. */

import { EmbedBuilder } from "discord.js";

const COLORS = {
  success: 0x22c55e,
  running: 0xeab308,
  error: 0xef4444,
  info: 0x3b82f6,
  neutral: 0x6b7280,
} as const;

export function greetingEmbed(
  userName: string,
  agents: { name: string; machineName?: string; steps?: { name: string }[]; description?: string }[],
  machines: { name: string; agentCount: number }[],
): EmbedBuilder {
  const embed = new EmbedBuilder()
    .setColor(COLORS.info)
    .setTitle(`Hey ${userName}!`);

  if (machines.length > 0) {
    const machineLines = machines.map(
      (m) => `\u{1F7E2} **${m.name}** -- ${m.agentCount} agent${m.agentCount === 1 ? "" : "s"}`,
    );
    embed.addFields({ name: "Machines", value: machineLines.join("\n"), inline: false });
  }

  if (agents.length > 0) {
    const agentLines = agents.map((a, i) => {
      const machine = a.machineName ? ` *(${a.machineName})*` : "";
      const steps = a.steps?.length ? ` -- ${a.steps.length} steps` : "";
      return `**${i + 1}.** ${a.name}${steps}${machine}`;
    });
    embed.addFields({ name: "Agents", value: agentLines.join("\n"), inline: false });
  } else {
    embed.setDescription("No agents registered yet.");
  }

  embed.setFooter({ text: "/run \u00B7 /status \u00B7 /agents \u00B7 /machines" });
  return embed;
}

export function agentListEmbed(
  agents: { name: string; description?: string; machineName?: string; steps?: { name: string }[] }[],
): EmbedBuilder {
  const embed = new EmbedBuilder()
    .setColor(COLORS.info)
    .setTitle("Agents");

  if (agents.length === 0) {
    embed.setDescription("No agents registered.");
    return embed;
  }

  for (const agent of agents.slice(0, 25)) {
    const desc = agent.description?.slice(0, 100) || "No description";
    const machine = agent.machineName ? ` (${agent.machineName})` : "";
    const steps = agent.steps?.length ? ` -- ${agent.steps.length} steps` : "";
    embed.addFields({ name: `${agent.name}${machine}`, value: `${desc}${steps}`, inline: false });
  }

  return embed;
}

export function runStartedEmbed(agentName: string, runId: string, machineName?: string): EmbedBuilder {
  const machine = machineName ? `on **${machineName}**` : "";
  return new EmbedBuilder()
    .setColor(COLORS.running)
    .setTitle(`Starting ${agentName}`)
    .setDescription(`${machine}\nRun ID: \`${runId.slice(0, 8)}\`\n${progressBar(0, 1)}`)
    .setTimestamp();
}

export function progressEmbed(
  agentName: string,
  runId: string,
  stepIndex: number,
  stepTotal: number,
  stepName: string,
  machineName?: string,
): EmbedBuilder {
  const machine = machineName ? `on **${machineName}**` : "";
  return new EmbedBuilder()
    .setColor(COLORS.running)
    .setTitle(`Running ${agentName}`)
    .setDescription(
      `${machine}\nRun ID: \`${runId.slice(0, 8)}\`\n${progressBar(stepIndex, stepTotal)} ${stepIndex}/${stepTotal} ${stepName}`,
    )
    .setTimestamp();
}

export function runCompletedEmbed(
  agentName: string,
  runId: string,
  outputs: Record<string, unknown>,
  machineName?: string,
): EmbedBuilder {
  const machine = machineName ? `on **${machineName}**` : "";
  const embed = new EmbedBuilder()
    .setColor(COLORS.success)
    .setTitle(`${agentName} finished!`)
    .setDescription(`${machine}\nRun ID: \`${runId.slice(0, 8)}\``)
    .setTimestamp();

  for (const [key, val] of Object.entries(outputs)) {
    if (typeof val === "string" && val.length < 500) {
      embed.addFields({ name: key, value: val || "(empty)", inline: false });
    }
  }

  return embed;
}

export function runFailedEmbed(
  agentName: string,
  runId: string,
  error: string,
  machineName?: string,
): EmbedBuilder {
  const machine = machineName ? `on **${machineName}**` : "";
  return new EmbedBuilder()
    .setColor(COLORS.error)
    .setTitle(`${agentName} failed`)
    .setDescription(
      `${machine}\nRun ID: \`${runId.slice(0, 8)}\`\n\n**Error:** ${error.slice(0, 500)}\n\nResume: \`/resume run_id:${runId.slice(0, 8)}\``,
    )
    .setTimestamp();
}

export function statusEmbed(runs: Record<string, unknown>[]): EmbedBuilder {
  const embed = new EmbedBuilder()
    .setColor(COLORS.info)
    .setTitle("Recent Runs");

  if (runs.length === 0) {
    embed.setDescription("No runs. Everything is idle.");
    return embed;
  }

  const lines = runs.slice(0, 15).map((r: any) => {
    const id = (r.id || "").slice(0, 8);
    const icon = r.status === "completed" ? "\u{2705}" : r.status === "failed" ? "\u{274C}" : "\u{1F7E1}";
    const machine = r.machine_name ? ` (${r.machine_name})` : "";
    return `${icon} \`${id}\` **${r.agent_name || "-"}**${machine} -- ${r.status || "?"}`;
  });

  embed.setDescription(lines.join("\n"));
  return embed;
}

export function machinesEmbed(
  machines: { name: string; agentCount: number; connectedAt: Date; activeRuns: number }[],
): EmbedBuilder {
  const embed = new EmbedBuilder()
    .setColor(COLORS.info)
    .setTitle("Connected Machines");

  if (machines.length === 0) {
    embed.setDescription("No machines connected. Run `vadgr gateway connect` on your machines.");
    return embed;
  }

  for (const m of machines) {
    const uptime = Math.floor((Date.now() - m.connectedAt.getTime()) / 60_000);
    embed.addFields({
      name: `\u{1F7E2} ${m.name}`,
      value: `${m.agentCount} agents | ${m.activeRuns} active runs | up ${uptime}m`,
      inline: false,
    });
  }

  return embed;
}

export function helpEmbed(): EmbedBuilder {
  return new EmbedBuilder()
    .setColor(COLORS.neutral)
    .setTitle("Vadgr Commands")
    .addFields(
      { name: "/run <agent>", value: "Run an agent", inline: true },
      { name: "/agents", value: "List all agents", inline: true },
      { name: "/status", value: "Show recent runs", inline: true },
      { name: "/cancel <id>", value: "Cancel a run", inline: true },
      { name: "/logs <id>", value: "Show run logs", inline: true },
      { name: "/machines", value: "Show connected machines", inline: true },
    )
    .setFooter({ text: "Or just say hey and describe what you want." });
}

export function errorEmbed(title: string, message: string): EmbedBuilder {
  return new EmbedBuilder()
    .setColor(COLORS.error)
    .setTitle(title)
    .setDescription(message);
}

/** Unicode progress bar. */
export function progressBar(current: number, total: number, length = 10): string {
  if (total <= 0) return "\u2591".repeat(length);
  const filled = Math.round((current / total) * length);
  return "\u2588".repeat(filled) + "\u2591".repeat(length - filled);
}
