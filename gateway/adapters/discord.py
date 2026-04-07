"""Discord adapter using webhook receive + REST API send."""

from __future__ import annotations

import logging
from typing import Optional

import httpx

from gateway.base import ChannelAdapter, MessageHandler
from gateway.models import InboundMessage, OutboundMessage, MessageType

logger = logging.getLogger(__name__)

_DISCORD_API_BASE = "https://discord.com/api/v10"
_TIMEOUT = 15


class DiscordAdapter(ChannelAdapter):
    """Discord integration via webhook receive and REST API send."""

    def __init__(
        self,
        bot_token: str,
        bot_id: Optional[str] = None,
        guild_id: Optional[str] = None,
    ):
        self._bot_token = bot_token
        self._bot_id = bot_id
        self._guild_id = guild_id
        self._handler: Optional[MessageHandler] = None

    @property
    def name(self) -> str:
        return "discord"

    async def connect(self) -> None:
        """No-op in webhook mode -- Discord pushes events to our endpoint."""
        pass

    async def disconnect(self) -> None:
        """No-op in webhook mode."""
        pass

    async def send_message(self, message: OutboundMessage) -> None:
        """Send a text message via Discord REST API."""
        url = f"{_DISCORD_API_BASE}/channels/{message.chat_id}/messages"
        headers = {
            "Authorization": f"Bot {self._bot_token}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(url, json={"content": message.text}, headers=headers)
            if resp.status_code >= 400:
                logger.error(
                    "Failed to send Discord message: %s %s",
                    resp.status_code,
                    resp.text[:200],
                )
            resp.raise_for_status()

    async def register_handler(self, handler: MessageHandler) -> None:
        """Register the message handler. Called by the gateway on startup."""
        self._handler = handler

    def parse_webhook(self, payload: dict) -> InboundMessage | None:
        """Parse a Discord Gateway dispatch payload (MESSAGE_CREATE).

        Expected format:
        {
            "t": "MESSAGE_CREATE",
            "d": {
                "id": "...",
                "channel_id": "...",
                "guild_id": "...",   # absent for DMs
                "author": {"id": "...", "username": "...", "bot": false},
                "content": "hello",
                "type": 0
            }
        }
        """
        if payload.get("t") != "MESSAGE_CREATE":
            return None

        d = payload.get("d", {})
        if not d:
            return None

        if d.get("author", {}).get("bot", False):
            return None

        if d.get("type", 0) != 0:
            return None

        content = d.get("content", "").strip()
        if not content:
            return None

        if self._bot_id:
            prefix = f"<@{self._bot_id}>"
            if content.startswith(prefix):
                content = content[len(prefix):].strip()

        return InboundMessage(
            channel="discord",
            chat_id=d["channel_id"],
            sender_id=d["author"]["id"],
            sender_name=d["author"]["username"],
            text=content,
            message_type=MessageType.TEXT,
            raw=payload,
        )

    async def handle_webhook(self, payload: dict) -> None:
        """Called by the webhook endpoint. Parses and dispatches to handler."""
        message = self.parse_webhook(payload)
        if message and self._handler:
            await self._handler(message)
