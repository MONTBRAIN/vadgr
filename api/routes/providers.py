"""Provider discovery routes."""

from fastapi import APIRouter

from api.engine.providers import _load_providers_yaml

router = APIRouter(prefix="/api/providers", tags=["providers"])


@router.get("")
async def list_providers():
    """Return available providers with their display names and model lists."""
    raw = _load_providers_yaml()
    result = []
    for key, cfg in raw.items():
        result.append({
            "id": key,
            "name": cfg.get("name", key),
            "models": cfg.get("models", []),
        })
    return result
