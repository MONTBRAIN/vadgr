"""API configuration via environment variables."""

from pydantic import model_validator
from pydantic_settings import BaseSettings

DEFAULT_API_PORT = 8000
DEFAULT_FRONTEND_PORT = 3000


class Settings(BaseSettings):
    # Host is no longer hard-coded -- it comes from transport.bind_host() at
    # startup (main.py). This default is only a fallback for legacy callers.
    host: str = "127.0.0.1"
    port: int = DEFAULT_API_PORT
    frontend_port: int = DEFAULT_FRONTEND_PORT
    cors_origins: list[str] = ["http://localhost:3000"]
    database_path: str = "data/agent_forge.db"
    computer_use_enabled: bool = True
    default_provider: str = "claude_code"
    provider_timeout: int = 300
    version: str = "0.4.1"

    model_config = {"env_prefix": "AGENT_FORGE_"}

    @model_validator(mode="after")
    def _ensure_frontend_cors(self) -> "Settings":
        """Auto-add frontend port origin to CORS list if not already present."""
        origin = f"http://localhost:{self.frontend_port}"
        if origin not in self.cors_origins:
            self.cors_origins = [*self.cors_origins, origin]
        return self


settings = Settings()
