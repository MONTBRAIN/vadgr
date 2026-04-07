/** Gateway entry point. */

import * as fs from "fs";
import * as path from "path";
import { Gateway, type GatewayConfig } from "./server.js";

const DEFAULT_API_PORT = 8000;
const PID_DIR = path.join(process.env.HOME || "~", ".forge", "pids");

/** Resolve API URL: ~/.forge/pids/api.port → AGENT_FORGE_PORT env → default 8000 */
function resolveApiUrl(): string {
  const host = process.env.AGENT_FORGE_HOST || "127.0.0.1";

  // 1. Check running service port file (written by `vadgr start`)
  const portFile = path.join(PID_DIR, "api.port");
  try {
    const port = parseInt(fs.readFileSync(portFile, "utf-8").trim(), 10);
    if (port > 0) return `http://${host}:${port}`;
  } catch {
    // Port file doesn't exist -- service may not be started via CLI
  }

  // 2. Environment variable (same as api/config.py)
  const envPort = process.env.AGENT_FORGE_PORT;
  if (envPort) return `http://${host}:${envPort}`;

  // 3. Default
  return `http://${host}:${DEFAULT_API_PORT}`;
}

const config: GatewayConfig = {
  apiUrl: resolveApiUrl(),
  discord: process.env.DISCORD_BOT_TOKEN
    ? { botToken: process.env.DISCORD_BOT_TOKEN }
    : undefined,
};

const gateway = new Gateway(config);

process.on("SIGINT", async () => {
  await gateway.stop();
  process.exit(0);
});

process.on("SIGTERM", async () => {
  await gateway.stop();
  process.exit(0);
});

gateway.start().catch((err) => {
  console.error("[Gateway] Failed to start:", err);
  process.exit(1);
});
