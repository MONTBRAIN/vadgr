/** Gateway entry point. */

import { Gateway, type GatewayConfig } from "./server.js";

const config: GatewayConfig = {
  apiUrl: process.env.VADGR_API_URL || "http://localhost:8000",
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
