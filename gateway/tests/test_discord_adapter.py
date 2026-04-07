"""Tests for Discord adapter webhook parsing."""

import pytest

from gateway.adapters.discord import DiscordAdapter
from gateway.models import MessageType


def _adapter():
    return DiscordAdapter(bot_token="test-token")


def _message_payload(
    content="hello",
    author_id="111222333",
    author_name="Santiago",
    channel_id="9876543210",
    guild_id="5555555555",
    is_bot=False,
    msg_type=0,
):
    return {
        "t": "MESSAGE_CREATE",
        "d": {
            "id": "1234567890",
            "channel_id": channel_id,
            "guild_id": guild_id,
            "author": {
                "id": author_id,
                "username": author_name,
                "bot": is_bot,
            },
            "content": content,
            "type": msg_type,
        },
    }


class TestDiscordAdapterName:
    def test_name_is_discord(self):
        assert _adapter().name == "discord"


class TestParseWebhook:
    def test_parse_text_message(self):
        payload = _message_payload(
            content="hey",
            author_name="Santiago",
            channel_id="9876543210",
            author_id="111222333",
        )
        msg = _adapter().parse_webhook(payload)
        assert msg is not None
        assert msg.channel == "discord"
        assert msg.chat_id == "9876543210"
        assert msg.sender_id == "111222333"
        assert msg.sender_name == "Santiago"
        assert msg.text == "hey"
        assert msg.message_type == MessageType.TEXT

    def test_skip_bot_messages(self):
        payload = _message_payload(content="I am a bot", is_bot=True)
        assert _adapter().parse_webhook(payload) is None

    def test_skip_non_message_create_events(self):
        payload = {"t": "GUILD_CREATE", "d": {}}
        assert _adapter().parse_webhook(payload) is None

    def test_skip_empty_content(self):
        payload = _message_payload(content="")
        assert _adapter().parse_webhook(payload) is None

    def test_skip_whitespace_only_content(self):
        payload = _message_payload(content="   ")
        assert _adapter().parse_webhook(payload) is None

    def test_skip_system_messages(self):
        # Discord system messages (e.g., pin notifications) have type != 0
        payload = _message_payload(content="Santiago pinned a message.", msg_type=6)
        assert _adapter().parse_webhook(payload) is None

    def test_bot_mention_stripped_from_text(self):
        adapter = DiscordAdapter(bot_token="test-token", bot_id="99999")
        payload = _message_payload(content="<@99999> run qa")
        msg = adapter.parse_webhook(payload)
        assert msg is not None
        assert msg.text == "run qa"

    def test_mention_without_bot_id_not_stripped(self):
        # If bot_id is not set, mentions are preserved as-is
        payload = _message_payload(content="<@99999> hello")
        msg = _adapter().parse_webhook(payload)
        assert msg is not None
        assert msg.text == "<@99999> hello"

    def test_empty_payload_returns_none(self):
        assert _adapter().parse_webhook({}) is None

    def test_dm_message_no_guild_id(self):
        payload = {
            "t": "MESSAGE_CREATE",
            "d": {
                "id": "1234567890",
                "channel_id": "DMCHANNEL",
                "author": {
                    "id": "111",
                    "username": "Santiago",
                    "bot": False,
                },
                "content": "hello dm",
                "type": 0,
            },
        }
        msg = _adapter().parse_webhook(payload)
        assert msg is not None
        assert msg.chat_id == "DMCHANNEL"
        assert msg.text == "hello dm"
