"""WhatsApp adapter using Evolution API.

Evolution API is a self-hosted REST wrapper around Baileys (WhatsApp Web).
It handles QR code auth, session management, and exposes webhooks for
incoming messages + REST endpoints for sending.

This adapter:
1. Receives webhook POSTs from Evolution API on incoming messages
2. Normalizes them into InboundMessage
3. Sends responses back via Evolution API's REST endpoint
"""

from __future__ import annotations

import logging
from typing import Optional

import httpx

from gateway.base import ChannelAdapter, MessageHandler
from gateway.models import InboundMessage, OutboundMessage, MessageType

logger = logging.getLogger(__name__)

_TIMEOUT = 15


class WhatsAppAdapter(ChannelAdapter):
    """WhatsApp integration via Evolution API."""

    def __init__(
        self,
        evolution_url: str,
        instance_name: str,
        api_key: str = "",
    ):
        self._evolution_url = evolution_url.rstrip("/")
        self._instance = instance_name
        self._api_key = api_key
        self._handler: Optional[MessageHandler] = None

    @property
    def name(self) -> str:
        return "whatsapp"

    async def connect(self) -> None:
        """Check that the Evolution API instance is connected."""
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(
                f"{self._evolution_url}/instance/connectionState/{self._instance}",
                headers=self._headers(),
            )
            resp.raise_for_status()
            data = resp.json()
            state = data.get("instance", {}).get("state", "unknown")
            if state != "open":
                logger.warning("WhatsApp instance '%s' state: %s", self._instance, state)
            else:
                logger.info("WhatsApp instance '%s' connected", self._instance)

    async def disconnect(self) -> None:
        """Logout from the Evolution API instance."""
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            await client.delete(
                f"{self._evolution_url}/instance/logout/{self._instance}",
                headers=self._headers(),
            )

    async def send_message(self, message: OutboundMessage) -> None:
        """Send a text message via Evolution API."""
        # Ensure the chat_id has the WhatsApp suffix
        number = message.chat_id
        if not number.endswith("@s.whatsapp.net"):
            # Strip non-digits and add suffix
            digits = "".join(c for c in number if c.isdigit())
            number = f"{digits}@s.whatsapp.net"

        payload = {
            "number": number,
            "textMessage": {"text": message.text},
        }

        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(
                f"{self._evolution_url}/message/sendText/{self._instance}",
                json=payload,
                headers=self._headers(),
            )
            if resp.status_code >= 400:
                logger.error(
                    "Failed to send WhatsApp message: %s %s",
                    resp.status_code,
                    resp.text[:200],
                )
            resp.raise_for_status()

    async def register_handler(self, handler: MessageHandler) -> None:
        """Register the message handler. Called by the gateway on startup."""
        self._handler = handler

    def parse_webhook(self, payload: dict) -> InboundMessage | None:
        """Parse an Evolution API webhook payload.

        Expected format (messages.upsert event):
        {
            "event": "messages.upsert",
            "instance": "vadgr",
            "data": {
                "key": {
                    "remoteJid": "5731200000@s.whatsapp.net",
                    "fromMe": false,
                    "id": "ABC123"
                },
                "pushName": "Santiago",
                "message": {
                    "conversation": "hey"
                },
                "messageTimestamp": 1712345678
            }
        }
        """
        event = payload.get("event", "")
        if event != "messages.upsert":
            return None

        data = payload.get("data", {})
        key = data.get("key", {})

        # Skip messages sent by us
        if key.get("fromMe", False):
            return None

        remote_jid = key.get("remoteJid", "")
        # Skip group messages (groups end with @g.us)
        if remote_jid.endswith("@g.us"):
            return None

        # Extract text from various message formats
        msg = data.get("message", {})
        text = (
            msg.get("conversation")
            or msg.get("extendedTextMessage", {}).get("text")
            or ""
        )

        if not text.strip():
            # Could be image, audio, etc. -- we only handle text for now
            msg_type = MessageType.UNKNOWN
            if msg.get("imageMessage"):
                msg_type = MessageType.IMAGE
            elif msg.get("audioMessage"):
                msg_type = MessageType.AUDIO
            elif msg.get("documentMessage"):
                msg_type = MessageType.DOCUMENT
            return InboundMessage(
                channel="whatsapp",
                chat_id=remote_jid,
                sender_id=remote_jid.split("@")[0],
                sender_name=data.get("pushName", "Unknown"),
                text="",
                message_type=msg_type,
                raw=payload,
            )

        return InboundMessage(
            channel="whatsapp",
            chat_id=remote_jid,
            sender_id=remote_jid.split("@")[0],
            sender_name=data.get("pushName", "Unknown"),
            text=text.strip(),
            raw=payload,
        )

    async def handle_webhook(self, payload: dict) -> None:
        """Called by the webhook endpoint. Parses and dispatches to handler."""
        message = self.parse_webhook(payload)
        if message and self._handler:
            await self._handler(message)

    def _headers(self) -> dict:
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["apikey"] = self._api_key
        return headers
