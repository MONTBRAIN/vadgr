"""The headline provider: Anthropic via the Claude Code OAuth token.

Dev runs bill against a Claude Pro/Max subscription instead of API credit -- the
first version where you stop paying for API while debugging. It is gray-area per
Anthropic's ToS and dev-only, so it refuses to start under
``VADGR_MODE=production`` (the production API-key sibling,
``native_anthropic_api``, is 0.5.0).
"""

from __future__ import annotations

import os

from engine.auth.oauth import OAuthStrategy
from engine.providers._anthropic_base import CLAUDE_CODE_SYSTEM_PREFIX, AnthropicBase

# The public Claude Code OAuth client id + refresh endpoint (§4.6).
CLAUDE_CODE_CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"
CLAUDE_OAUTH_REFRESH_URL = "https://platform.claude.com/oauth/token"
CLAUDE_CREDENTIALS_PATH = "~/.claude/.credentials.json"


class AnthropicOAuthProvider(AnthropicBase):
    name = "anthropic_oauth"
    auth_mode = "oauth"
    default_model = "claude-sonnet-4-6"
    user_agent = "claude-cli/2.1.2 (external, cli)"
    extra_headers = {
        "anthropic-beta": "oauth-2025-04-20,interleaved-thinking-2025-05-14"
    }
    system_prompt_prefix = CLAUDE_CODE_SYSTEM_PREFIX

    def __init__(self, **kwargs):
        # Compose the OAuth strategy unless a test injected one.
        if "auth_strategy" not in kwargs:
            kwargs["auth_strategy"] = OAuthStrategy(
                credentials_path=CLAUDE_CREDENTIALS_PATH,
                refresh_url=CLAUDE_OAUTH_REFRESH_URL,
                client_id=CLAUDE_CODE_CLIENT_ID,
            )
        super().__init__(**kwargs)

    async def setup(self) -> None:
        """Refuse production (subscription auth is dev-only), then fail fast on
        the credentials."""
        if os.environ.get("VADGR_MODE") == "production":
            raise RuntimeError(
                "native_anthropic_oauth is dev-only (subscription billing, "
                "gray-area ToS). Use native_anthropic_api under VADGR_MODE=production."
            )
        await super().setup()
