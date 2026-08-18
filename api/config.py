"""API configuration via environment variables."""

from pydantic_settings import BaseSettings

DEFAULT_API_PORT = 8000


class Settings(BaseSettings):
    host: str = "127.0.0.1"
    port: int = DEFAULT_API_PORT
    database_path: str = "data/agent_forge.db"
    computer_use_enabled: bool = True
    # No default_provider here: the machine's default is providers.yaml's
    # top-level `default_provider`, which is the file an owner edits. A second
    # default in code answered `claude_code`, so a run that named no provider
    # would have gone to a deprecated subprocess CLI instead of the native loop.
    provider_timeout: int = 300
    # Kept equal to the crate's version by `test_version_consistency.py`. The two
    # daemons serve the same product during the migration, so a client cannot be
    # asked to work out which half answered it.
    version: str = "0.4.7"

    model_config = {"env_prefix": "AGENT_FORGE_"}


settings = Settings()
