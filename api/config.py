"""API configuration via environment variables."""

from pydantic_settings import BaseSettings

DEFAULT_API_PORT = 8000


class Settings(BaseSettings):
    host: str = "127.0.0.1"
    port: int = DEFAULT_API_PORT
    database_path: str = "data/agent_forge.db"
    computer_use_enabled: bool = True
    default_provider: str = "claude_code"
    provider_timeout: int = 300
    version: str = "0.4.3"

    model_config = {"env_prefix": "AGENT_FORGE_"}


settings = Settings()
