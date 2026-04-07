/** Discord slash command definitions and registration. */

import { REST, Routes, SlashCommandBuilder } from "discord.js";

export function buildSlashCommands(): SlashCommandBuilder[] {
  return [
    new SlashCommandBuilder()
      .setName("run")
      .setDescription("Run an agent")
      .addStringOption((opt) =>
        opt.setName("agent").setDescription("Agent name or number").setRequired(true),
      )
      .addStringOption((opt) =>
        opt.setName("machine").setDescription("Machine to run on (if agent exists on multiple)").setRequired(false),
      ) as SlashCommandBuilder,

    new SlashCommandBuilder()
      .setName("agents")
      .setDescription("List all available agents"),

    new SlashCommandBuilder()
      .setName("status")
      .setDescription("Show active and recent runs"),

    new SlashCommandBuilder()
      .setName("cancel")
      .setDescription("Cancel a running agent")
      .addStringOption((opt) =>
        opt.setName("run_id").setDescription("Run ID to cancel").setRequired(true),
      ) as SlashCommandBuilder,

    new SlashCommandBuilder()
      .setName("logs")
      .setDescription("Show recent logs for a run")
      .addStringOption((opt) =>
        opt.setName("run_id").setDescription("Run ID").setRequired(true),
      ) as SlashCommandBuilder,

    new SlashCommandBuilder()
      .setName("machines")
      .setDescription("Show connected machines"),
  ];
}

export async function registerSlashCommands(botToken: string, clientId: string): Promise<void> {
  const rest = new REST().setToken(botToken);
  const commands = buildSlashCommands().map((c) => c.toJSON());

  try {
    await rest.put(Routes.applicationCommands(clientId), { body: commands });
    console.log(`[Slash] Registered ${commands.length} commands`);
  } catch (err: any) {
    console.error(`[Slash] Failed to register commands: ${err.message}`);
  }
}

export function getCommandNames(): string[] {
  return buildSlashCommands().map((c) => c.name);
}
