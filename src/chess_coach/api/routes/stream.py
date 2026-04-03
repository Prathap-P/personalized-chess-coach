"""WebSocket streaming analysis endpoint."""

import asyncio
import json
import logging
import time
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from jose import JWTError, jwt

from ..auth import ALGORITHM
from ...config import settings

logger = logging.getLogger(__name__)
router = APIRouter(tags=["stream"])

# ── Concurrency cap ───────────────────────────────────────────────────────────
# Max simultaneous Stockfish analyses. Each spawns an OS process so 3 is safe
# on most laptops; raise if you have more cores to spare.
_ANALYSIS_SEMAPHORE: Optional[asyncio.Semaphore] = None
_active_analyses: int = 0
ANALYSIS_TIMEOUT_SECONDS = 600  # 10-minute hard ceiling


def _get_semaphore() -> asyncio.Semaphore:
    """Return (lazily creating) the module-level semaphore on the running loop."""
    global _ANALYSIS_SEMAPHORE
    if _ANALYSIS_SEMAPHORE is None:
        _ANALYSIS_SEMAPHORE = asyncio.Semaphore(3)
    return _ANALYSIS_SEMAPHORE


def get_active_analyses() -> int:
    return _active_analyses


async def _send(ws: WebSocket, msg: dict) -> None:
    """Send a JSON message over the WebSocket, silently ignoring closed sockets."""
    try:
        await ws.send_text(json.dumps(msg))
    except Exception:
        pass


def _validate_ws_token(token: str) -> Optional[str]:
    """Return the username if the token is valid, else None."""
    if not settings.api_secret_key:
        return None
    try:
        payload = jwt.decode(token, settings.api_secret_key, algorithms=[ALGORITHM])
        return payload.get("sub")
    except JWTError:
        return None


@router.websocket("/api/v1/analyze/stream")
async def analyze_stream(websocket: WebSocket) -> None:
    """
    WebSocket endpoint for streaming analysis progress.

    Protocol (client sends JSON messages in order):

    1. Auth message:
       {"token": "<jwt>"}

    2. Analysis request:
       {
         "type": "game",          // or "profile"
         "payload": {
           // For type=game:
           "data": "<pgn or url>",
           "player": "<optional name>",
           "options": {"depth": 20, "include_llm": false}

           // For type=profile:
           "username": "hikaru",
           "platform": "lichess",
           "num_games": 10,
           "color": null,
           "options": {"include_coaching": false}
         }
       }

    Server sends:
    - {"type": "ping"}                                          -- keepalive every 15 s
    - {"type": "progress", "percent": 45.0, "current": 9, "total": 20}
    - {"type": "result", "analysis": {...}}
    - {"type": "error", "message": "..."}
    """
    await websocket.accept()
    client = websocket.client
    client_addr = f"{client.host}:{client.port}" if client else "unknown"
    logger.info(f"ws: CONNECT from {client_addr}")
    loop = asyncio.get_event_loop()
    queue: asyncio.Queue = asyncio.Queue()
    _DONE = object()  # sentinel

    try:
        # ── Step 1: authenticate ──────────────────────────────────────────────
        try:
            auth_msg = await asyncio.wait_for(websocket.receive_json(), timeout=10.0)
        except asyncio.TimeoutError:
            await _send(websocket, {"type": "error", "message": "Auth timeout"})
            await websocket.close(code=4000)
            return

        token = auth_msg.get("token", "")
        username = _validate_ws_token(token)
        if not username:
            logger.warning(f"ws: AUTH FAILED from {client_addr} — invalid/missing token")
            await _send(websocket, {"type": "error", "message": "Invalid or missing token"})
            await websocket.close(code=4001)
            return

        logger.info(f"ws: AUTH OK user={username} from {client_addr}")

        # ── Heartbeat task ────────────────────────────────────────────────────
        async def heartbeat() -> None:
            while True:
                await asyncio.sleep(15)
                await _send(websocket, {"type": "ping"})

        heartbeat_task = asyncio.ensure_future(heartbeat())

        # ── Persistent message loop ───────────────────────────────────────────
        # The socket stays open; client can send multiple requests:
        #   - {"type": "game", "payload": {...}}
        #   - {"type": "profile", "payload": {...}}
        #   - {"type": "move_analysis", "payload": {...}}
        try:
            while True:
                try:
                    request_msg = await asyncio.wait_for(websocket.receive_json(), timeout=300.0)
                except asyncio.TimeoutError:
                    await _send(websocket, {"type": "ping"})
                    continue

                msg_type = request_msg.get("type", "game")
                payload = request_msg.get("payload", {})
                logger.info(f"ws: MESSAGE user={username} type={msg_type}")

                # ── Per-move analysis (async, on-demand, cached) ──────────────
                if msg_type == "move_analysis":
                    from .move_analysis import handle_move_analysis
                    await handle_move_analysis(
                        payload=payload,
                        user_id=username,
                        send_fn=lambda m: _send(websocket, m),
                    )
                    continue

                # ── Full game / profile analysis ──────────────────────────────
                if msg_type not in ("game", "profile"):
                    logger.warning(f"ws: unknown message type={msg_type} user={username}")
                    await _send(websocket, {"type": "error", "message": f"Unknown type: {msg_type}"})
                    continue

                semaphore = _get_semaphore()
                if semaphore._value == 0:  # type: ignore[attr-defined]
                    logger.warning(f"ws: server busy, rejecting {msg_type} for user={username}")
                    await _send(websocket, {
                        "type": "error",
                        "message": "Server busy — too many analyses running simultaneously. Try again shortly.",
                    })
                    continue

                # ── Progress callback (thread-safe) ───────────────────────────
                def on_progress(current: int, total: int) -> None:
                    pct = round((current / total) * 100, 1) if total else 0.0
                    loop.call_soon_threadsafe(
                        queue.put_nowait,
                        {"type": "progress", "percent": pct, "current": current, "total": total},
                    )

                # ── Background analysis worker ────────────────────────────────
                def run_analysis() -> None:
                    global _active_analyses
                    _active_analyses += 1
                    t_start = time.perf_counter()
                    logger.info(f"ws: analysis START type={msg_type} user={username} active={_active_analyses}")
                    try:
                        if msg_type == "game":
                            from .analyze import _run_game_analysis, _serialize_game_analysis
                            from ...utils import download_game

                            data = payload.get("data", "")
                            if data.startswith("http"):
                                data = download_game(data)

                            analysis = _run_game_analysis(
                                pgn=data,
                                player=payload.get("player"),
                                depth=payload.get("options", {}).get("depth"),
                                include_llm=payload.get("options", {}).get("include_llm", False),
                                skill_level=payload.get("options", {}).get("skill_level"),
                                progress_callback=on_progress,
                            )
                            result = _serialize_game_analysis(analysis).model_dump()

                        else:  # profile
                            from .analyze import _run_profile_analysis, _player_stats_to_response
                            from ..schemas import PatternResponse, ProfileAnalysisResponse

                            raw = _run_profile_analysis(
                                username=payload.get("username", ""),
                                platform=payload.get("platform", "lichess"),
                                num_games=payload.get("num_games", 10),
                                color=payload.get("color"),
                                include_coaching=payload.get("options", {}).get("include_coaching", False),
                                skill_level=payload.get("options", {}).get("skill_level"),
                                progress_callback=on_progress,
                            )
                            patterns = [
                                PatternResponse(
                                    pattern_type=p.pattern_type,
                                    description=p.description,
                                    occurrences=p.occurrences,
                                    severity=p.severity,
                                    examples=p.examples,
                                ).model_dump()
                                for p in raw["patterns"]
                            ]
                            result = ProfileAnalysisResponse(
                                username=raw["username"],
                                platform=raw["platform"],
                                num_games_analyzed=raw["num_games_analyzed"],
                                average_accuracy=raw["average_accuracy"],
                                aggregated_stats=_player_stats_to_response(raw["aggregated_stats"]),
                                patterns=patterns,
                                opening_analysis=raw["opening_analysis"],
                                phase_analysis=raw["phase_analysis"],
                            ).model_dump()

                        loop.call_soon_threadsafe(
                            queue.put_nowait,
                            {"type": "result", "analysis": result},
                        )
                        logger.info(
                            f"ws: analysis DONE type={msg_type} user={username} "
                            f"elapsed={time.perf_counter()-t_start:.1f}s"
                        )

                    except Exception as exc:
                        logger.exception(f"ws: analysis ERROR type={msg_type} user={username} — {exc}")
                        loop.call_soon_threadsafe(
                            queue.put_nowait,
                            {"type": "error", "message": str(exc)},
                        )
                    finally:
                        _active_analyses -= 1
                        loop.call_soon_threadsafe(queue.put_nowait, _DONE)

                # Run full analysis with semaphore + timeout, drain queue
                async with semaphore:
                    analysis_future = loop.run_in_executor(None, run_analysis)
                    try:
                        await asyncio.wait_for(
                            asyncio.shield(analysis_future),
                            timeout=ANALYSIS_TIMEOUT_SECONDS,
                        )
                    except asyncio.TimeoutError:
                        loop.call_soon_threadsafe(
                            queue.put_nowait,
                            {"type": "error", "message": f"Analysis timed out after {ANALYSIS_TIMEOUT_SECONDS // 60} minutes"},
                        )
                        loop.call_soon_threadsafe(queue.put_nowait, _DONE)
                        await analysis_future

                while True:
                    msg = await queue.get()
                    if msg is _DONE:
                        break
                    await _send(websocket, msg)

        finally:
            heartbeat_task.cancel()
            try:
                await heartbeat_task
            except asyncio.CancelledError:
                pass

    except WebSocketDisconnect:
        logger.info(f"ws: DISCONNECT user={username if 'username' in dir() else 'unauthenticated'} from {client_addr}")
    except Exception as exc:
        logger.error(f"ws: HANDLER ERROR user={username if 'username' in dir() else 'unauthenticated'} from {client_addr} — {exc}", exc_info=True)
        await _send(websocket, {"type": "error", "message": str(exc)})
