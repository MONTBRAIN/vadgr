"""Gateway webhook server.

Runs as a separate FastAPI service that receives webhooks from
messaging platforms, routes them through security + router,
and sends responses back via the adapters.
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from gateway.adapters.discord import DiscordAdapter
from gateway.adapters.whatsapp import WhatsAppAdapter
from gateway.api_client import VadgrAPIClient
from gateway.config import GatewayConfig, load_config
from gateway.models import InboundMessage, OutboundMessage
from gateway.router import MessageRouter
from gateway.security import SecurityGuard

logger = logging.getLogger(__name__)


def create_app(config: GatewayConfig | None = None) -> FastAPI:
    """Create the gateway FastAPI app."""
    config = config or load_config()

    app = FastAPI(title="Vadgr Gateway", version="0.1.0")

    # Wire up components
    api_client = VadgrAPIClient(config.api_url)
    router = MessageRouter(api_client)
    security = SecurityGuard(config.security)

    # WhatsApp adapter
    wa_adapter = WhatsAppAdapter(
        evolution_url=config.whatsapp.evolution_url,
        instance_name=config.whatsapp.instance_name,
        api_key=config.whatsapp.api_key,
    )

    # Discord adapter (optional -- only wired when bot_token is configured)
    discord_adapter: DiscordAdapter | None = None
    if config.discord.bot_token:
        discord_adapter = DiscordAdapter(
            bot_token=config.discord.bot_token,
            bot_id=config.discord.bot_id or None,
            guild_id=config.discord.guild_id or None,
        )

    # Store on app state for access in routes
    app.state.config = config
    app.state.router = router
    app.state.security = security
    app.state.adapters = {"whatsapp": wa_adapter}
    if discord_adapter is not None:
        app.state.adapters["discord"] = discord_adapter
    app.state.api_client = api_client
    app.state.run_watchers = {}  # run_id -> (chat_id, adapter) for async notifications

    @app.on_event("startup")
    async def startup():
        try:
            await wa_adapter.connect()
        except Exception as e:
            logger.warning("WhatsApp adapter failed to connect: %s", e)

        # Register the message handler
        async def handle_message(message: InboundMessage):
            await _process_message(app, message, wa_adapter)

        await wa_adapter.register_handler(handle_message)

        if discord_adapter is not None:
            async def handle_discord_message(message: InboundMessage):
                await _process_message(app, message, discord_adapter)

            await discord_adapter.register_handler(handle_discord_message)

    @app.post("/webhook/whatsapp")
    async def whatsapp_webhook(request: Request):
        """Receive webhooks from Evolution API."""
        payload = await request.json()
        wa = app.state.adapters["whatsapp"]
        # Process async -- return 200 immediately (best practice for webhooks)
        asyncio.create_task(wa.handle_webhook(payload))
        return JSONResponse(content={"status": "ok"})

    if discord_adapter is not None:
        @app.post("/webhook/discord")
        async def discord_webhook(request: Request):
            """Receive webhooks from Discord."""
            payload = await request.json()
            disc = app.state.adapters["discord"]
            asyncio.create_task(disc.handle_webhook(payload))
            return JSONResponse(content={"status": "ok"})

    @app.get("/health")
    async def health():
        return {"status": "ok", "adapters": list(app.state.adapters.keys())}

    return app


async def _process_message(
    app: FastAPI,
    message: InboundMessage,
    adapter: WhatsAppAdapter,
) -> None:
    """Full pipeline: security check → route → respond → watch if async."""
    security: SecurityGuard = app.state.security
    router: MessageRouter = app.state.router

    # Skip non-text messages
    if not message.text:
        return

    # Security check
    rejection = security.check(message)
    if rejection is None and message.sender_id not in (
        app.state.config.security.allowed_senders or [message.sender_id]
    ):
        # Silent reject for unknown senders (don't reveal bot exists)
        return
    if rejection:
        await adapter.send_message(OutboundMessage(
            chat_id=message.chat_id,
            text=rejection,
        ))
        return

    # Sanitize input values that will be passed to agents
    # (the text itself is natural language commands, sanitization
    # happens in the router when extracting input values)

    # Route the message
    try:
        result = await router.handle(message)
    except Exception as e:
        logger.exception("Router error for message from %s", message.sender_id)
        await adapter.send_message(OutboundMessage(
            chat_id=message.chat_id,
            text=f"Something went wrong: {e}",
        ))
        return

    # Send response
    await adapter.send_message(OutboundMessage(
        chat_id=message.chat_id,
        text=result.response,
    ))

    # If the command started an async run, watch it for completion
    if result.is_async and result.run_id:
        asyncio.create_task(
            _watch_run(app, result.run_id, result.agent_name, message.chat_id, adapter)
        )


async def _watch_run(
    app: FastAPI,
    run_id: str,
    agent_name: str | None,
    chat_id: str,
    adapter: WhatsAppAdapter,
) -> None:
    """Poll a run until completion and send the result back."""
    api: VadgrAPIClient = app.state.api_client
    poll_interval = 30  # seconds
    max_polls = 120  # 1 hour max

    for _ in range(max_polls):
        await asyncio.sleep(poll_interval)
        try:
            run = await api.get_run(run_id)
        except Exception:
            continue

        status = run.get("status", "")
        if status in ("completed", "failed"):
            # Build summary
            name = agent_name or run.get("agent_name", "Agent")
            outputs = run.get("outputs", {})

            if status == "completed":
                # Try to extract meaningful output
                summary_parts = [f"{name} finished!"]
                for key, val in outputs.items():
                    if isinstance(val, str) and len(val) < 500:
                        summary_parts.append(f"\n{key}: {val}")
                text = "\n".join(summary_parts)
            else:
                error = outputs.get("error", "Unknown error") if isinstance(outputs, dict) else str(outputs)
                text = (
                    f"{name} failed.\n"
                    f"Error: {error}\n\n"
                    f"Resume with: resume {run_id[:8]}"
                )

            await adapter.send_message(OutboundMessage(chat_id=chat_id, text=text))
            return

    # Timed out watching
    await adapter.send_message(OutboundMessage(
        chat_id=chat_id,
        text=f"Run {run_id[:8]} is still going after 1 hour. Check with: status",
    ))
