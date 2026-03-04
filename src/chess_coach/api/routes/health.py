"""Health check endpoint."""

import logging
import time

from fastapi import APIRouter

from ...config import settings
from ...engine import StockfishEngine
from ...storage import GameStorage

logger = logging.getLogger(__name__)
router = APIRouter(tags=["health"])

_start_time = time.time()


@router.get("/health")
async def health_check() -> dict:
    """
    Returns server health status.

    Checks Stockfish availability and LLM configuration without requiring auth.
    """
    stockfish_status = "unavailable"
    try:
        with StockfishEngine() as _:
            stockfish_status = "ok"
    except Exception as exc:
        logger.debug(f"Stockfish health check failed: {exc}")

    # Active WebSocket analyses (imported lazily to avoid circular import)
    try:
        from .stream import get_active_analyses
        active_analyses = get_active_analyses()
    except Exception:
        active_analyses = 0

    # Cached game count from SQLite
    try:
        cache_entries = GameStorage().count_analyses()
    except Exception:
        cache_entries = 0

    return {
        "status": "ok",
        "stockfish": stockfish_status,
        "llm_configured": bool(settings.llm_base_url or settings.openai_api_key),
        "llm_model": settings.default_llm_model,
        "llm_provider": settings.default_llm_provider,
        "active_analyses": active_analyses,
        "cache_entries": cache_entries,
        "uptime_seconds": round(time.time() - _start_time, 1),
    }
