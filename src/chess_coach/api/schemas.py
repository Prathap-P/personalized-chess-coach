"""Pydantic request/response schemas for the Chess Coach API."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ── Auth ──────────────────────────────────────────────────────────────────────

class TokenRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


# ── Analysis requests ─────────────────────────────────────────────────────────

class AnalysisOptions(BaseModel):
    depth: Optional[int] = None
    include_llm: bool = False
    skill_level: Optional[int] = None


class AnalyzeGameRequest(BaseModel):
    source: str = Field(..., description="'url' or 'pgn'")
    data: str = Field(..., description="Game URL or raw PGN text")
    player: Optional[str] = None
    options: AnalysisOptions = Field(default_factory=AnalysisOptions)


class ProfileOptions(BaseModel):
    depth: Optional[int] = None
    include_coaching: bool = False
    skill_level: Optional[int] = None


class AnalyzeProfileRequest(BaseModel):
    username: str
    platform: str = "lichess"
    num_games: int = Field(default=10, ge=1, le=100)
    color: Optional[str] = Field(default=None, description="'white', 'black', or null for both")
    options: ProfileOptions = Field(default_factory=ProfileOptions)


# ── Response sub-models ───────────────────────────────────────────────────────

class PlayerStatsResponse(BaseModel):
    accuracy: float
    brilliant: int
    great: int
    best: int
    excellent: int
    good: int
    inaccuracy: int
    mistake: int
    blunder: int
    forced: int
    total_moves: int
    average_eval_loss: float


class MoveAnalysisResponse(BaseModel):
    move_number: int
    move_san: str
    move_uci: str
    player_color: str          # "white" | "black"
    classification: str        # enum value as plain string
    eval_loss: float
    move_accuracy: float
    is_blunder: bool
    is_mistake: bool
    is_inaccuracy: bool
    mistake_type: Optional[str]
    comment: str


class GameMetadataResponse(BaseModel):
    white_player: str
    black_player: str
    white_elo: Optional[int]
    black_elo: Optional[int]
    event: str
    site: str
    date: Optional[str]
    result: str
    opening: str
    eco: str


class GameAnalysisResponse(BaseModel):
    game_id: str
    metadata: GameMetadataResponse
    moves: List[MoveAnalysisResponse]
    white_stats: PlayerStatsResponse
    black_stats: PlayerStatsResponse
    total_moves: int
    blunders: int
    mistakes: int
    inaccuracies: int
    average_eval_loss: float
    ai_summary: str
    ai_strengths: List[str]
    ai_weaknesses: List[str]
    ai_recommendations: List[str]
    analysis_time: float


class PatternResponse(BaseModel):
    pattern_type: str
    description: str
    occurrences: int
    severity: str
    examples: List[int]


class ProfileAnalysisResponse(BaseModel):
    username: str
    platform: str
    num_games_analyzed: int
    average_accuracy: float
    aggregated_stats: PlayerStatsResponse
    patterns: List[PatternResponse]
    opening_analysis: Dict[str, Any]
    phase_analysis: Dict[str, Any]


# ── Config ────────────────────────────────────────────────────────────────────

class ConfigUpdateRequest(BaseModel):
    settings: Dict[str, Any] = Field(
        ...,
        description=(
            "Key-value pairs to update. Supported keys: "
            "llm.model, llm.provider, llm.base_url, "
            "stockfish.depth, stockfish.time_limit, stockfish.path"
        ),
    )
