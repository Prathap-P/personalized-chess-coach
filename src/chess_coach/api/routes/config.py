"""Configuration read/write endpoints."""

import logging
import re
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status

from ..auth import get_current_user
from ..schemas import ConfigUpdateRequest
from ...config import _find_env_file, settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["config"])

# Mapping of dot-notation keys → .env variable names
ENV_KEY_MAP: dict[str, str] = {
    "llm.model": "DEFAULT_LLM_MODEL",
    "llm.provider": "DEFAULT_LLM_PROVIDER",
    "llm.base_url": "LLM_BASE_URL",
    "stockfish.depth": "STOCKFISH_DEPTH",
    "stockfish.time_limit": "STOCKFISH_TIME_LIMIT",
    "stockfish.path": "STOCKFISH_PATH",
}


@router.get("/config")
async def get_config(_user: str = Depends(get_current_user)) -> dict:
    """Return current runtime configuration (read from loaded settings)."""
    return {
        "llm": {
            "provider": settings.default_llm_provider,
            "model": settings.default_llm_model,
            "base_url": settings.llm_base_url,
        },
        "stockfish": {
            "path": settings.stockfish_path,
            "depth": settings.stockfish_depth,
            "time_limit": settings.stockfish_time_limit,
        },
        "data": {
            "data_dir": str(settings.data_dir),
            "cache_dir": str(settings.cache_dir),
            "logs_dir": str(settings.logs_dir),
        },
        "api": {
            "username": settings.api_username,
        },
    }


@router.put("/config")
async def update_config(
    request: ConfigUpdateRequest,
    _user: str = Depends(get_current_user),
) -> dict:
    """
    Update configuration values and persist them to .env.

    Changes take effect after the server is restarted.
    Supported keys: llm.model, llm.provider, llm.base_url,
    stockfish.depth, stockfish.time_limit, stockfish.path
    """
    unknown = [k for k in request.settings if k not in ENV_KEY_MAP]
    if unknown:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown config key(s): {unknown}. "
            f"Supported: {list(ENV_KEY_MAP.keys())}",
        )

    env_path = Path(_find_env_file())
    content = env_path.read_text(encoding="utf-8") if env_path.exists() else ""
    lines = content.splitlines()

    for dot_key, value in request.settings.items():
        env_key = ENV_KEY_MAP[dot_key]
        new_line = f"{env_key}={value}"
        replaced = False
        for i, line in enumerate(lines):
            if re.match(rf"^{env_key}\s*=", line):
                lines[i] = new_line
                replaced = True
                break
        if not replaced:
            lines.append(new_line)

    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    logger.info(f"Config updated: {list(request.settings.keys())}")

    return {
        "updated": list(request.settings.keys()),
        "message": "Changes saved to .env. Restart the server to apply.",
    }
