"""
WebSocket endpoint for on-demand per-move analysis.

Protocol:
    Client sends (after auth on the main /analyze/stream socket):
        {"type": "move_analysis", "payload": {
            "fen": "<fen>",
            "move_san": "<san>",
            "move_uci": "<uci>",
            "recent_moves": ["e4", "e5", "Nf3"],   # last 5 SANs for context
            "mode": "pgn"                           # or "interactive"
        }}

    Server streams back on the same socket:
        {"type": "move_explanation_chunk", "move_san": "...", "chunk": "..."}
        {"type": "move_explanation_done",  "move_san": "...", "data": {
            "move_intent": "...",
            "why_bad": "...",
            "better_move_san": "...",
            "better_move_explanation": "...",
            "tactical_motif": "...",
            "followup_line": [...],
            "best_followup_line": [...],
            "game_phase": "...",
            "is_fallback": false
        }}
        {"type": "move_explanation_error", "move_san": "...", "message": "..."}
"""

import asyncio
import hashlib
import logging
import time
from typing import Any, Dict, List, Optional

import chess

from ...engine import StockfishEngine, get_engine_pool, describe_position, get_game_phase, normalize_fen
from ...analysis.pattern_analyzer import detect_motif
from ...llm import LLMClient
from ...storage import GameStorage

logger = logging.getLogger(__name__)

# ── In-flight dedup: same position, two users → share one LLM task ───────────
# key: cache_key  →  value: asyncio.Task producing the explanation dict
_in_flight: Dict[str, "asyncio.Task[Dict[str, Any]]"] = {}

# ── Per-user debounce: cancel old request if same user sends a new one quickly ─
# key: user_id  →  value: asyncio.Task currently running for that user
_user_tasks: Dict[str, "asyncio.Task[None]"] = {}


def _make_cache_key(norm_fen: str, move_san: str) -> str:
    """Position-based cache key (FEN stripped of halfmove/fullmove + move SAN)."""
    raw = f"{norm_fen}|{move_san}"
    return hashlib.sha256(raw.encode()).hexdigest()


async def handle_move_analysis(
    payload: Dict[str, Any],
    user_id: str,
    send_fn,                         # async callable(dict) — writes to WS
) -> None:
    """
    Entry point called from stream.py when a "move_analysis" message arrives.

    Debounces per user (cancels previous task if still running), then
    orchestrates: cache → Stockfish → motif → LLM → cache write → send.
    """
    move_san = payload.get("move_san", "")
    logger.info(f"move_analysis: user={user_id} move={move_san}")

    # Cancel any in-progress task for this user (they navigated away)
    old_task = _user_tasks.get(user_id)
    if old_task and not old_task.done():
        old_task.cancel()
        logger.debug(f"move_analysis: cancelled previous task for user={user_id} (new move={move_san})")

    task = asyncio.ensure_future(
        _run_move_analysis(payload, user_id, send_fn)
    )
    _user_tasks[user_id] = task

    try:
        await task
    except asyncio.CancelledError:
        pass  # silently dropped — a newer move was requested


async def _run_move_analysis(
    payload: Dict[str, Any],
    user_id: str,
    send_fn,
) -> None:
    fen: str = payload.get("fen", "")
    move_san: str = payload.get("move_san", "")
    move_uci: str = payload.get("move_uci", "")
    recent_moves: List[str] = payload.get("recent_moves", [])
    mode: str = payload.get("mode", "pgn")

    if not fen or not move_san:
        await send_fn({"type": "move_explanation_error", "move_san": move_san,
                       "message": "Missing fen or move_san"})
        return

    norm_fen = normalize_fen(fen)
    cache_key = _make_cache_key(norm_fen, move_san)
    t0 = time.perf_counter()

    logger.debug(f"move_analysis: fen='{norm_fen}' key={cache_key[:12]}…")

    storage = GameStorage()

    # ── 1. Cache check ────────────────────────────────────────────────────────
    cached = storage.get_move_explanation(cache_key)
    if cached and not cached.get("is_fallback"):
        logger.info(f"move_analysis: cache HIT move={move_san} key={cache_key[:12]}… ({(time.perf_counter()-t0)*1000:.0f}ms)")
        data = cached["explanation"]
        data["move_san"] = move_san
        data["norm_fen"] = norm_fen
        data["tactical_motif"] = cached["tactical_motif"]
        data["followup_line"] = data.get("followup_line", [])
        data["best_followup_line"] = data.get("best_followup_line", [])
        data["game_phase"] = data.get("game_phase", "")
        data["is_fallback"] = False
        await send_fn({"type": "move_explanation_done", "move_san": move_san, "data": data})
        # Pre-fetch next moves if in PGN mode (fire-and-forget — caller handles)
        return

    logger.debug(f"move_analysis: cache MISS move={move_san} key={cache_key[:12]}…")

    # ── 2. Dedup: subscribe to existing in-flight task if any ─────────────────
    if cache_key in _in_flight:
        logger.info(f"move_analysis: dedup — joining in-flight task for move={move_san} key={cache_key[:12]}…")
        existing = _in_flight[cache_key]
        try:
            explanation = await existing
            explanation["move_san"] = move_san
            explanation["norm_fen"] = norm_fen
            await send_fn({"type": "move_explanation_done", "move_san": move_san, "data": explanation})
        except Exception as e:
            await send_fn({"type": "move_explanation_error", "move_san": move_san, "message": str(e)})
        return

    # ── 3. Parse board ────────────────────────────────────────────────────────
    try:
        board = chess.Board(fen)
        move = chess.Move.from_uci(move_uci) if move_uci else board.parse_san(move_san)
    except Exception as e:
        await send_fn({"type": "move_explanation_error", "move_san": move_san,
                       "message": f"Invalid position or move: {e}"})
        return

    # ── 4. Spawn detached LLM task (deduped) ─────────────────────────────────
    llm_task: asyncio.Task[Dict[str, Any]] = asyncio.ensure_future(
        _compute_explanation(board, move, move_san, norm_fen, recent_moves, storage, cache_key)
    )
    _in_flight[cache_key] = llm_task

    try:
        explanation = await llm_task
        elapsed = (time.perf_counter() - t0) * 1000
        logger.info(
            f"move_analysis: done move={move_san} classification={explanation.get('classification','?')} "
            f"fallback={explanation.get('is_fallback', False)} elapsed={elapsed:.0f}ms"
        )
        explanation["move_san"] = move_san
        explanation["norm_fen"] = norm_fen
        await send_fn({"type": "move_explanation_done", "move_san": move_san, "data": explanation})
    except asyncio.CancelledError:
        logger.debug(f"move_analysis: task cancelled for move={move_san} (user navigated away)")
        raise  # propagate so handle_move_analysis can clean up
    except Exception as e:
        logger.error(f"move_analysis: error move={move_san} — {e}", exc_info=True)
        await send_fn({"type": "move_explanation_error", "move_san": move_san, "message": str(e)})
    finally:
        _in_flight.pop(cache_key, None)


async def _compute_explanation(
    board: chess.Board,
    move: chess.Move,
    move_san: str,
    norm_fen: str,
    recent_moves: List[str],
    storage: GameStorage,
    cache_key: str,
) -> Dict[str, Any]:
    """
    CPU-heavy work: Stockfish eval + motif detection + LLM.
    Runs in executor threads where needed to avoid blocking the event loop.
    """
    loop = asyncio.get_event_loop()
    pool = get_engine_pool()

    t_sf = time.perf_counter()
    # ── Stockfish: eval before, best move, continuations ─────────────────────
    async with pool.acquire_ctx() as engine:
        # Run synchronous Stockfish calls in a thread
        sf_result = await loop.run_in_executor(
            None, _stockfish_work, engine, board, move, move_san
        )

    eval_before_cp: float = sf_result["eval_before_cp"]
    eval_after_cp: float = sf_result["eval_after_cp"]
    best_move_san: Optional[str] = sf_result["best_move_san"]
    followup_line: List[str] = sf_result["followup_line"]
    best_followup_line: List[str] = sf_result["best_followup_line"]
    logger.debug(
        f"move_analysis: stockfish move={move_san} eval_before={eval_before_cp:.0f} "
        f"eval_after={eval_after_cp:.0f} best={best_move_san} "
        f"followup={followup_line} sf_time={(time.perf_counter()-t_sf)*1000:.0f}ms"
    )

    eval_loss_cp = max(0.0, eval_before_cp - eval_after_cp)

    # Classify move quality (simplified — matches game_analyzer thresholds)
    if eval_loss_cp < 10:
        classification = "best" if best_move_san == move_san else "excellent"
    elif eval_loss_cp < 50:
        classification = "inaccuracy"
    elif eval_loss_cp < 150:
        classification = "mistake"
    else:
        classification = "blunder"

    is_good_move = best_move_san is None or best_move_san == move_san
    if is_good_move:
        best_move_san = None

    # ── Motif detection (pure python-chess, fast) ──────────────────────────
    tactical_motif = await loop.run_in_executor(None, detect_motif, board, move)

    # ── Game phase ────────────────────────────────────────────────────────────
    game_phase = get_game_phase(board)

    # ── Position description for LLM ──────────────────────────────────────────
    board_after = board.copy()
    board_after.push(move)
    position_description = await loop.run_in_executor(None, describe_position, board_after)

    # ── LLM explanation ───────────────────────────────────────────────────────
    t_llm = time.perf_counter()
    logger.debug(
        f"move_analysis: starting LLM for move={move_san} phase={game_phase} "
        f"motif={tactical_motif} classification={classification} loss={eval_loss_cp:.0f}cp"
    )
    llm = LLMClient()
    explanation = await loop.run_in_executor(
        None,
        lambda: llm.explain_move_detailed(
            move_san=move_san,
            best_move_san=best_move_san,
            position_description=position_description,
            eval_loss_cp=eval_loss_cp,
            classification=classification,
            followup_line=followup_line,
            best_followup_line=best_followup_line,
            tactical_motif=tactical_motif,
            game_phase=game_phase,
            recent_moves=recent_moves,
        ),
    )

    logger.debug(f"move_analysis: LLM done move={move_san} llm_time={(time.perf_counter()-t_llm)*1000:.0f}ms")

    # Attach engine data to explanation
    explanation["followup_line"] = followup_line
    explanation["best_followup_line"] = best_followup_line
    explanation["game_phase"] = game_phase
    explanation["tactical_motif"] = tactical_motif or ""
    is_fallback = explanation.pop("is_fallback", False)

    # ── Cache result ──────────────────────────────────────────────────────────
    storage.set_move_explanation(
        cache_key=cache_key,
        fen=norm_fen,
        move_san=move_san,
        best_move_san=best_move_san,
        explanation=explanation,
        tactical_motif=tactical_motif,
        is_fallback=is_fallback,
    )

    explanation["is_fallback"] = is_fallback
    return explanation


def _stockfish_work(
    engine: StockfishEngine,
    board: chess.Board,
    move: chess.Move,
    move_san: str,
) -> Dict[str, Any]:
    """
    Synchronous Stockfish work — runs in a thread via run_in_executor.

    Returns eval_before_cp, eval_after_cp, best_move_san,
    followup_line (after user's move), best_followup_line (after best move).
    """
    # Eval before move (from mover's perspective)
    eval_before = engine.evaluate_position(board)
    mover_is_white = board.turn == chess.WHITE
    eval_before_cp = (eval_before.cp_score or 0) * (1 if mover_is_white else -1)
    best_move_san_raw = eval_before.best_move  # SAN of Stockfish best

    # Play user's move
    board_after_user = board.copy()
    board_after_user.push(move)
    eval_after = engine.evaluate_position(board_after_user)
    eval_after_cp = (eval_after.cp_score or 0) * (1 if mover_is_white else -1)

    # 3-move continuation after user's move
    followup_line = engine.get_continuation(board_after_user, num_moves=3)

    # 3-move continuation after best move (if different)
    best_followup_line: List[str] = []
    if best_move_san_raw and best_move_san_raw != move_san:
        try:
            board_after_best = board.copy()
            best_uci_move = board.parse_san(best_move_san_raw)
            board_after_best.push(best_uci_move)
            best_followup_line = engine.get_continuation(board_after_best, num_moves=3)
        except Exception:
            pass

    return {
        "eval_before_cp": float(eval_before_cp),
        "eval_after_cp": float(eval_after_cp),
        "best_move_san": best_move_san_raw,
        "followup_line": followup_line,
        "best_followup_line": best_followup_line,
    }
