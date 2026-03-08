"""API configuration via environment variables."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    host: str = "127.0.0.1"
    port: int = 8000
    cors_origins: list[str] = ["http://localhost:3000"]
    database_path: str = "data/agent_forge.db"
    computer_use_enabled: bool = True
    default_provider: str = "claude_code"
    provider_timeout: int = 300
    anthropic_api_key: str = ""
    anthropic_default_model: str = "claude-sonnet-4-6"
    openai_api_key: str = ""
    openai_default_model: str = "gpt-4o"
    version: str = "0.1.0"

    model_config = {"env_prefix": "AGENT_FORGE_"}


settings = Settings()
