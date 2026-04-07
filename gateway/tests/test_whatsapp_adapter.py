"""Tests for WhatsApp adapter webhook parsing and message sending."""

import pytest
from unittest.mock import AsyncMock, patch

from gateway.adapters.whatsapp import WhatsAppAdapter
from gateway.models import MessageType, OutboundMessage


def _adapter():
    return WhatsAppAdapter(
        evolution_url="http://localhost:8080",
        instance_name="vadgr",
        api_key="test-key",
    )


class TestParseWebhook:
    def test_parse_text_message(self):
        payload = {
            "event": "messages.upsert",
            "instance": "vadgr",
            "data": {
                "key": {
                    "remoteJid": "5731200000@s.whatsapp.net",
                    "fromMe": False,
                    "id": "MSG001",
                },
                "pushName": "Santiago",
                "message": {"conversation": "hey"},
                "messageTimestamp": 1712345678,
            },
        }
        msg = _adapter().parse_webhook(payload)
        assert msg is not None
        assert msg.channel == "whatsapp"
        assert msg.chat_id == "5731200000@s.whatsapp.net"
        assert msg.sender_id == "5731200000"
        assert msg.sender_name == "Santiago"
        assert msg.text == "hey"
        assert msg.message_type == MessageType.TEXT

    def test_parse_extended_text_message(self):
        payload = {
            "event": "messages.upsert",
            "data": {
                "key": {"remoteJid": "111@s.whatsapp.net", "fromMe": False},
                "pushName": "Test",
                "message": {"extendedTextMessage": {"text": "run qa"}},
            },
        }
        msg = _adapter().parse_webhook(payload)
        assert msg is not None
        assert msg.text == "run qa"

    def test_skip_from_me(self):
        payload = {
            "event": "messages.upsert",
            "data": {
                "key": {"remoteJid": "111@s.whatsapp.net", "fromMe": True},
                "pushName": "Me",
                "message": {"conversation": "response"},
            },
        }
        assert _adapter().parse_webhook(payload) is None

    def test_skip_group_messages(self):
        payload = {
            "event": "messages.upsert",
            "data": {
                "key": {"remoteJid": "123456@g.us", "fromMe": False},
                "pushName": "Someone",
                "message": {"conversation": "hello group"},
            },
        }
        assert _adapter().parse_webhook(payload) is None

    def test_skip_non_message_events(self):
        payload = {"event": "connection.update", "data": {"state": "open"}}
        assert _adapter().parse_webhook(payload) is None

    def test_skip_qrcode_events(self):
        payload = {"event": "qrcode.updated", "data": {"qrcode": "base64..."}}
        assert _adapter().parse_webhook(payload) is None

    def test_image_message_type(self):
        payload = {
            "event": "messages.upsert",
            "data": {
                "key": {"remoteJid": "111@s.whatsapp.net", "fromMe": False},
                "pushName": "Test",
                "message": {"imageMessage": {"caption": "photo"}},
            },
        }
        msg = _adapter().parse_webhook(payload)
        assert msg is not None
        assert msg.message_type == MessageType.IMAGE
        assert msg.text == ""

    def test_empty_payload(self):
        assert _adapter().parse_webhook({}) is None

    def test_missing_message(self):
        payload = {
            "event": "messages.upsert",
            "data": {
                "key": {"remoteJid": "111@s.whatsapp.net", "fromMe": False},
                "pushName": "Test",
                "message": {},
            },
        }
        msg = _adapter().parse_webhook(payload)
        assert msg is not None
        assert msg.text == ""
        assert msg.message_type == MessageType.UNKNOWN


class TestSendMessage:
    @pytest.mark.asyncio
    async def test_send_message_uses_textMessage_wrapper(self):
        """send_message must wrap text in textMessage object (Evolution API v1.7.1)."""
        adapter = _adapter()
        outbound = OutboundMessage(chat_id="5731200000@s.whatsapp.net", text="hello")

        captured = {}

        async def fake_post(url, *, json=None, headers=None):
            captured["json"] = json
            mock_resp = AsyncMock()
            mock_resp.status_code = 200
            mock_resp.raise_for_status = lambda: None
            return mock_resp

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.post = AsyncMock(side_effect=fake_post)
            mock_client_cls.return_value = mock_client

            await adapter.send_message(outbound)

        payload = captured["json"]
        assert "textMessage" in payload, "payload must have 'textMessage' key"
        assert payload["textMessage"] == {"text": "hello"}
        assert "text" not in payload, "top-level 'text' key must not be present"

    @pytest.mark.asyncio
    async def test_send_message_number_normalisation(self):
        """Numbers without the WA suffix are normalised before sending."""
        adapter = _adapter()
        outbound = OutboundMessage(chat_id="5731200000", text="hi")

        captured = {}

        async def fake_post(url, *, json=None, headers=None):
            captured["json"] = json
            mock_resp = AsyncMock()
            mock_resp.status_code = 200
            mock_resp.raise_for_status = lambda: None
            return mock_resp

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.post = AsyncMock(side_effect=fake_post)
            mock_client_cls.return_value = mock_client

            await adapter.send_message(outbound)

        assert captured["json"]["number"] == "5731200000@s.whatsapp.net"
