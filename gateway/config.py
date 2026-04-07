"""Gateway configuration.

Loads from environment variables and/or a config file.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from gateway.security import SecurityConfig


@dataclass
class WhatsAppConfig:
    evolution_url: str = "http://localhost:8080"
    instance_name: str = "vadgr"
    api_key: str = ""


@dataclass
class DiscordConfig:
    bot_token: str = ""
    bot_id: str = ""
    guild_id: str = ""


@dataclass
class GatewayConfig:
    """Top-level gateway configuration."""

    api_url: str = "http://localhost:8000"
    webhook_port: int = 8585
    whatsapp: WhatsAppConfig = field(default_factory=WhatsAppConfig)
    discord: DiscordConfig = field(default_factory=DiscordConfig)
    security: SecurityConfig = field(default_factory=SecurityConfig)


def load_config(config_path: str | None = None) -> GatewayConfig:
    """Load gateway config from file or environment.

    Priority: env vars > config file > defaults.
    """
    config = GatewayConfig()

    # Try config file
    path = config_path or os.environ.get("GATEWAY_CONFIG")
    if path and Path(path).exists():
        with open(path) as f:
            data = yaml.safe_load(f) or {}

        if "api_url" in data:
            config.api_url = data["api_url"]
        if "webhook_port" in data:
            config.webhook_port = int(data["webhook_port"])

        wa = data.get("whatsapp", {})
        if wa:
            config.whatsapp = WhatsAppConfig(
                evolution_url=wa.get("evolution_url", config.whatsapp.evolution_url),
                instance_name=wa.get("instance_name", config.whatsapp.instance_name),
                api_key=wa.get("api_key", config.whatsapp.api_key),
            )

        disc = data.get("discord", {})
        if disc:
            config.discord = DiscordConfig(
                bot_token=disc.get("bot_token", config.discord.bot_token),
                bot_id=disc.get("bot_id", config.discord.bot_id),
                guild_id=disc.get("guild_id", config.discord.guild_id),
            )

        sec = data.get("security", {})
        if sec:
            config.security = SecurityConfig(
                allowed_senders=sec.get("allowed_senders", []),
                rate_limit=sec.get("rate_limit", 10),
                rate_window=sec.get("rate_window", 3600),
                audit_log_path=sec.get("audit_log_path"),
            )

    # Env var overrides
    if os.environ.get("VADGR_API_URL"):
        config.api_url = os.environ["VADGR_API_URL"]
    if os.environ.get("GATEWAY_WEBHOOK_PORT"):
        config.webhook_port = int(os.environ["GATEWAY_WEBHOOK_PORT"])
    if os.environ.get("EVOLUTION_URL"):
        config.whatsapp.evolution_url = os.environ["EVOLUTION_URL"]
    if os.environ.get("EVOLUTION_INSTANCE"):
        config.whatsapp.instance_name = os.environ["EVOLUTION_INSTANCE"]
    if os.environ.get("EVOLUTION_API_KEY"):
        config.whatsapp.api_key = os.environ["EVOLUTION_API_KEY"]
    if os.environ.get("DISCORD_BOT_TOKEN"):
        config.discord.bot_token = os.environ["DISCORD_BOT_TOKEN"]
    if os.environ.get("DISCORD_BOT_ID"):
        config.discord.bot_id = os.environ["DISCORD_BOT_ID"]

    return config
