"""FastAPI application for the Chess Coach API."""

import logging
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .auth import router as auth_router
from .routes.analyze import router as analyze_router
from .routes.config import router as config_router
from .routes.health import router as health_router
from .routes.stream import router as stream_router
from ..config import settings

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Chess Coach API",
    description=(
        "Local API server for Personalized Chess Coach. "
        "Powered by Stockfish + LLM analysis."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# ── CORS ──────────────────────────────────────────────────────────────────────
# Permissive for localhost-only use; the static frontend can be hosted anywhere.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request ID + access logging middleware ────────────────────────────────────
@app.middleware("http")
async def request_middleware(request: Request, call_next):
    request_id = str(uuid.uuid4())[:8]
    request.state.request_id = request_id
    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = round((time.perf_counter() - start) * 1000)
    logger.info(
        f"{request.method} {request.url.path} "
        f"status={response.status_code} "
        f"duration={duration_ms}ms "
        f"req_id={request_id}"
    )
    response.headers["X-Request-ID"] = request_id
    return response


# ── Global unhandled-exception handler ───────────────────────────────────────
@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    request_id = getattr(request.state, "request_id", "unknown")
    logger.exception(f"Unhandled error [req_id={request_id}]: {exc}")
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "request_id": request_id},
    )


# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(health_router)    # GET /health           (no auth required)
app.include_router(auth_router)      # POST /auth/token      (no auth required)
app.include_router(analyze_router)   # POST /api/v1/analyze/*
app.include_router(config_router)    # GET/PUT /api/v1/config
app.include_router(stream_router)    # WS /api/v1/analyze/stream


@app.on_event("startup")
async def on_startup() -> None:
    import sys
    from pathlib import Path

    # Configure logging: write to stderr + a rotating file in the data/logs dir
    log_dir = settings.logs_dir if hasattr(settings, "logs_dir") else Path("data/logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "chess_coach.log"

    root_logger = logging.getLogger()
    if not root_logger.handlers:
        fmt = logging.Formatter(
            "%(asctime)s %(levelname)-8s %(name)s │ %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        # Console handler
        sh = logging.StreamHandler(sys.stderr)
        sh.setFormatter(fmt)
        root_logger.addHandler(sh)
        # Rotating file handler (10 MB × 5 backups)
        from logging.handlers import RotatingFileHandler
        fh = RotatingFileHandler(log_file, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8")
        fh.setFormatter(fmt)
        root_logger.addHandler(fh)

    root_logger.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))
    # Quiet noisy third-party loggers
    for noisy in ("httpx", "httpcore", "uvicorn.access", "chess"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    logger.info(f"Logging configured: level={settings.log_level.upper()} file={log_file}")

    issues = []
    if not settings.api_secret_key:
        issues.append("API_SECRET_KEY not set")
    if not settings.api_password_hash:
        issues.append("API_PASSWORD_HASH not set")
    if not settings.api_username:
        issues.append("API_USERNAME not set")

    stockfish_ok = settings.stockfish_path != "auto" and Path(settings.stockfish_path).exists()
    llm_ok = bool(settings.llm_base_url or settings.openai_api_key)

    banner_lines = [
        "",
        "  ╔" + "═" * 44 + "╗",
        "  ║  Chess Coach API v1.0.0" + " " * 19 + "║",
        f"  ║  Stockfish : {'ok' if stockfish_ok else 'auto-detect':<29}║",
        f"  ║  LLM       : {(settings.default_llm_provider + '/' + settings.default_llm_model):<29}║",
        f"  ║  LLM ready : {'yes' if llm_ok else 'no — set LLM_BASE_URL':<29}║",
        "  ╚" + "═" * 44 + "╝",
        "",
    ]
    for line in banner_lines:
        logger.info(line)

    for issue in issues:
        logger.warning(f"Auth config warning: {issue}. Run 'chess-coach api-setup' to fix.")

    logger.info("Visit http://localhost:8000/docs for interactive API docs.")

