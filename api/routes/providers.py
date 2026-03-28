"""Provider discovery routes."""

from fastapi import APIRouter

from api.engine.providers import (
    CLIAgentProvider,
    _load_providers_yaml,
    load_provider_config,
)

router = APIRouter(prefix="/api/providers", tags=["providers"])


@router.get("")
async def list_providers():
    """Return providers with availability status and model lists."""
    raw = _load_providers_yaml()
    result = []
    for key, cfg in raw.items():
        available = False
        try:
            config = load_provider_config(key)
            provider = CLIAgentProvider(config)
            available = await provider.is_available()
        except Exception:
            pass
        result.append({
            "id": key,
            "name": cfg.get("name", key),
            "available": available,
            "models": cfg.get("models", []),
        })
    return result
