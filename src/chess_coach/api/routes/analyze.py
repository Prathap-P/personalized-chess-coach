"""Game and profile analysis REST endpoints."""

import asyncio
import hashlib
import logging
from typing import Callable, Optional

import chess
from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..auth import get_current_user
from ..schemas import (
    AnalyzeGameRequest,
    AnalyzeProfileRequest,
    GameAnalysisResponse,
    GameMetadataResponse,
    MoveAnalysisResponse,
    PatternResponse,
    PlayerStatsResponse,
    ProfileAnalysisResponse,
)
from ...analysis.game_analyzer import GameAnalyzer
from ...analysis.pattern_analyzer import PatternAnalyzer
from ...config import settings
from ...engine import StockfishEngine
from ...llm import LLMClient
from ...models import GameAnalysis, PlayerStats
from ...storage import GameStorage
from ...utils import download_game, fetch_user_games

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["analyze"])


def _pgn_cache_key(pgn: str, depth: int, include_llm: bool) -> str:
    """Stable SHA-256 key for (pgn, depth, include_llm) — used for result caching."""
    normalized = pgn.strip() + f"|depth={depth}|llm={include_llm}"
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


# ── Serialization helpers ─────────────────────────────────────────────────────

def _player_stats_to_response(s: PlayerStats) -> PlayerStatsResponse:
    return PlayerStatsResponse(
        accuracy=s.accuracy,
        brilliant=s.brilliant,
        great=s.great,
        best=s.best,
        excellent=s.excellent,
        good=s.good,
        inaccuracy=s.inaccuracy,
        mistake=s.mistake,
        blunder=s.blunder,
        forced=s.forced,
        total_moves=s.total_moves,
        average_eval_loss=s.average_eval_loss,
    )


def _serialize_game_analysis(analysis: GameAnalysis) -> GameAnalysisResponse:
    """Convert a GameAnalysis domain object to a JSON-serializable response model."""
    moves = [
        MoveAnalysisResponse(
            move_number=m.move_number,
            move_san=m.move_san,
            move_uci=m.move_uci,
            player_color="white" if m.player_color == chess.WHITE else "black",
            classification=m.classification.value,
            eval_loss=m.eval_loss,
            move_accuracy=m.move_accuracy,
            is_blunder=m.is_blunder,
            is_mistake=m.is_mistake,
            is_inaccuracy=m.is_inaccuracy,
            mistake_type=m.mistake_type.value if m.mistake_type else None,
            comment=m.comment,
        )
        for m in analysis.moves
    ]

    metadata = GameMetadataResponse(
        white_player=analysis.metadata.white_player,
        black_player=analysis.metadata.black_player,
        white_elo=analysis.metadata.white_elo,
        black_elo=analysis.metadata.black_elo,
        event=analysis.metadata.event,
        site=analysis.metadata.site,
        date=analysis.metadata.date,
        result=analysis.metadata.result,
        opening=analysis.metadata.opening,
        eco=analysis.metadata.eco,
    )

    return GameAnalysisResponse(
        game_id=analysis.game_id,
        metadata=metadata,
        moves=moves,
        white_stats=_player_stats_to_response(analysis.white_stats),
        black_stats=_player_stats_to_response(analysis.black_stats),
        total_moves=analysis.total_moves,
        blunders=analysis.blunders,
        mistakes=analysis.mistakes,
        inaccuracies=analysis.inaccuracies,
        average_eval_loss=analysis.average_eval_loss,
        ai_summary=analysis.ai_summary,
        ai_strengths=analysis.ai_strengths,
        ai_weaknesses=analysis.ai_weaknesses,
        ai_recommendations=analysis.ai_recommendations,
        analysis_time=analysis.analysis_time,
    )


# ── Blocking analysis workers (run in thread pool) ────────────────────────────

def _run_game_analysis(
    pgn: str,
    player: Optional[str],
    depth: Optional[int],
    include_llm: bool,
    skill_level: Optional[int],
    progress_callback: Optional[Callable] = None,
) -> GameAnalysis:
    """Run Stockfish game analysis synchronously (called via asyncio.to_thread)."""
    effective_depth = depth or settings.stockfish_depth

    # ── Cache lookup ──────────────────────────────────────────────────────────
    storage = GameStorage()
    cache_key = _pgn_cache_key(pgn, effective_depth, include_llm)
    cached = storage.get_cached_analysis(cache_key)
    if cached is not None:
        logger.info(f"Cache hit for game {cached.game_id} (depth={effective_depth})")
        # Still fire synthetic progress so the UI bar fills quickly
        if progress_callback:
            total = cached.total_moves
            progress_callback(total, total)
        return cached

    # ── Full analysis ─────────────────────────────────────────────────────────
    with StockfishEngine(depth=effective_depth) as engine:
        analyzer = GameAnalyzer(engine)
        analysis = analyzer.analyze_game(
            pgn,
            target_player=player,
            progress_callback=progress_callback,
        )

    if include_llm:
        try:
            llm = LLMClient()
            ws, bs = analysis.white_stats, analysis.black_stats
            errors = [
                {
                    "move_number": m.move_number,
                    "move": m.move_san,
                    "classification": m.classification.value,
                    "eval_loss": m.eval_loss,
                }
                for m in analysis.get_errors()[:5]
            ]
            patterns = [
                {"description": p.description, "occurrences": p.occurrences, "severity": p.severity}
                for p in analysis.patterns
            ]
            game_summary = (
                f"{analysis.metadata.white_player} vs {analysis.metadata.black_player}\n"
                f"Result: {analysis.metadata.result}\n"
                f"Opening: {analysis.metadata.opening}"
            )
            player_stats = {
                "white": {
                    "accuracy": ws.accuracy,
                    "best": ws.best, "excellent": ws.excellent, "good": ws.good,
                    "inaccuracy": ws.inaccuracy, "mistake": ws.mistake, "blunder": ws.blunder,
                },
                "black": {
                    "accuracy": bs.accuracy,
                    "best": bs.best, "excellent": bs.excellent, "good": bs.good,
                    "inaccuracy": bs.inaccuracy, "mistake": bs.mistake, "blunder": bs.blunder,
                },
            }
            ai = llm.generate_game_analysis(
                game_summary, errors, patterns,
                skill_level or analysis.metadata.white_elo,
                player_stats=player_stats,
            )
            analysis.ai_summary = ai.get("summary", "")
            analysis.ai_strengths = ai.get("strengths", [])
            analysis.ai_weaknesses = ai.get("weaknesses", [])
            analysis.ai_recommendations = ai.get("recommendations", [])
        except Exception as exc:
            logger.warning(f"LLM analysis failed (non-fatal): {exc}")

    GameStorage().save_analysis(analysis)
    storage.set_cache_entry(cache_key, analysis.game_id)
    return analysis


def _run_profile_analysis(
    username: str,
    platform: str,
    num_games: int,
    color: Optional[str],
    include_coaching: bool,
    skill_level: Optional[int],
    progress_callback: Optional[Callable] = None,
) -> dict:
    """Run multi-game profile analysis synchronously (called via asyncio.to_thread)."""
    pgns = fetch_user_games(username, platform, limit=num_games)
    if not pgns:
        raise ValueError("No games found for this user")

    analyses = []
    storage = GameStorage()

    with StockfishEngine() as engine:
        analyzer = GameAnalyzer(engine)
        total = len(pgns)
        for idx, pgn in enumerate(pgns, start=1):
            try:
                analysis = analyzer.analyze_game(pgn, target_player=username)
                analyses.append(analysis)
                storage.save_analysis(analysis)
            except Exception as exc:
                logger.error(f"Failed to analyze game {idx}/{total}: {exc}")
            finally:
                if progress_callback:
                    progress_callback(idx, total)

    if not analyses:
        raise ValueError("No games could be analyzed")

    # Color filter
    player_color = None
    if color == "white":
        player_color = chess.WHITE
    elif color == "black":
        player_color = chess.BLACK

    # Pattern analysis
    pattern_analyzer = PatternAnalyzer()
    pattern_results = pattern_analyzer.analyze_games(analyses, player_color)

    # Aggregate per-player stats
    target_accuracies = []
    agg = {
        "brilliant": 0, "great": 0, "best": 0, "excellent": 0,
        "good": 0, "inaccuracy": 0, "mistake": 0, "blunder": 0,
        "forced": 0, "total_moves": 0,
    }
    total_loss = 0.0
    for a in analyses:
        if username.lower() in a.metadata.white_player.lower():
            s = a.white_stats
        elif username.lower() in a.metadata.black_player.lower():
            s = a.black_stats
        else:
            continue
        target_accuracies.append(s.accuracy)
        for key in agg:
            agg[key] += getattr(s, key)
        total_loss += s.average_eval_loss

    avg_accuracy = round(sum(target_accuracies) / len(target_accuracies), 1) if target_accuracies else 0.0
    avg_loss = round(total_loss / len(target_accuracies), 1) if target_accuracies else 0.0

    aggregated_stats = PlayerStats(
        accuracy=avg_accuracy,
        average_eval_loss=avg_loss,
        **agg,
    )

    return {
        "username": username,
        "platform": platform,
        "num_games_analyzed": len(analyses),
        "average_accuracy": avg_accuracy,
        "aggregated_stats": aggregated_stats,
        "patterns": pattern_results.get("patterns", []),
        "opening_analysis": pattern_results.get("opening_analysis", {}),
        "phase_analysis": pattern_results.get("phase_analysis", {}),
    }


# ── REST endpoints ────────────────────────────────────────────────────────────

@router.post("/analyze/game", response_model=GameAnalysisResponse)
async def analyze_game(
    request: AnalyzeGameRequest,
    _user: str = Depends(get_current_user),
) -> GameAnalysisResponse:
    """
    Analyze a single chess game.

    `data` can be a Lichess/Chess.com URL or raw PGN text.
    """
    # Resolve PGN
    if request.data.startswith("http"):
        try:
            pgn = await asyncio.to_thread(download_game, request.data)
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to download game: {exc}",
            ) from exc
    else:
        pgn = request.data

    try:
        analysis = await asyncio.to_thread(
            _run_game_analysis,
            pgn,
            request.player,
            request.options.depth,
            request.options.include_llm,
            request.options.skill_level,
        )
    except Exception as exc:
        logger.exception("Game analysis failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Analysis failed: {exc}",
        ) from exc

    return _serialize_game_analysis(analysis)


@router.get("/analyze/prefetch")
async def prefetch_pgn(
    url: str = Query(..., description="chess.com or lichess game URL to fetch PGN from"),
) -> dict:
    """
    Download and return the raw PGN for a game URL without running analysis.

    Used by the frontend to show the board preview immediately after a URL is pasted,
    before the user clicks Analyze. No authentication required.
    """
    try:
        pgn = await asyncio.to_thread(download_game, url)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Could not fetch game: {exc}",
        ) from exc
    return {"pgn": pgn}


@router.post("/analyze/profile", response_model=ProfileAnalysisResponse)
async def analyze_profile(
    request: AnalyzeProfileRequest,
    _user: str = Depends(get_current_user),
) -> ProfileAnalysisResponse:
    """
    Analyze a player's recent games across multiple games for patterns.
    """
    try:
        result = await asyncio.to_thread(
            _run_profile_analysis,
            request.username,
            request.platform,
            request.num_games,
            request.color,
            request.options.include_coaching,
            request.options.skill_level,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Profile analysis failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Analysis failed: {exc}",
        ) from exc

    patterns = [
        PatternResponse(
            pattern_type=p.pattern_type,
            description=p.description,
            occurrences=p.occurrences,
            severity=p.severity,
            examples=p.examples,
        )
        for p in result["patterns"]
    ]

    return ProfileAnalysisResponse(
        username=result["username"],
        platform=result["platform"],
        num_games_analyzed=result["num_games_analyzed"],
        average_accuracy=result["average_accuracy"],
        aggregated_stats=_player_stats_to_response(result["aggregated_stats"]),
        patterns=patterns,
        opening_analysis=result["opening_analysis"],
        phase_analysis=result["phase_analysis"],
    )
