"""Data models for chess analysis."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any

import chess


class MoveClassification(str, Enum):
    """Classification of chess moves based on quality."""

    BRILLIANT = "brilliant"
    GREAT = "great"
    BEST = "best"
    EXCELLENT = "excellent"
    GOOD = "good"
    INACCURACY = "inaccuracy"
    MISTAKE = "mistake"
    BLUNDER = "blunder"
    FORCED = "forced"


class MistakeType(str, Enum):
    """Types of chess mistakes."""

    TACTICAL = "tactical"
    POSITIONAL = "positional"
    OPENING = "opening"
    ENDGAME = "endgame"
    TIME_MANAGEMENT = "time_management"
    CALCULATION = "calculation"


@dataclass
class PositionEvaluation:
    """Stockfish evaluation of a position."""

    cp_score: Optional[int] = None  # Centipawn score
    mate_score: Optional[int] = None  # Mate in N moves
    best_move: Optional[str] = None
    pv_line: List[str] = field(default_factory=list)  # Principal variation
    depth: int = 0

    @property
    def is_mate(self) -> bool:
        """Check if position has mate score."""
        return self.mate_score is not None

    @property
    def normalized_score(self) -> float:
        """Get normalized score (-1 to 1, or ±∞ for mate)."""
        if self.mate_score is not None:
            return float("inf") if self.mate_score > 0 else float("-inf")
        if self.cp_score is not None:
            # Normalize using tanh-like function
            return max(-1.0, min(1.0, self.cp_score / 500.0))
        return 0.0


@dataclass
class MoveAnalysis:
    """Analysis of a single move."""

    move_number: int
    move_san: str  # Standard Algebraic Notation
    move_uci: str  # UCI notation
    player_color: chess.Color

    eval_before: PositionEvaluation
    eval_after: PositionEvaluation

    classification: MoveClassification
    eval_loss: float = 0.0       # Centipawn loss
    move_accuracy: float = 100.0 # Accuracy for this move (0-100)

    is_blunder: bool = False
    is_mistake: bool = False
    is_inaccuracy: bool = False

    mistake_type: Optional[MistakeType] = None
    comment: str = ""

    @property
    def is_error(self) -> bool:
        """Check if move is an error (blunder, mistake, or inaccuracy)."""
        return self.is_blunder or self.is_mistake or self.is_inaccuracy


@dataclass
class GameMetadata:
    """Metadata about a chess game."""

    white_player: str = "Unknown"
    black_player: str = "Unknown"
    white_elo: Optional[int] = None
    black_elo: Optional[int] = None
    event: str = ""
    site: str = ""
    date: Optional[str] = None
    result: str = "*"
    opening: str = ""
    eco: str = ""  # Encyclopedia of Chess Openings code


@dataclass
class Pattern:
    """Identified pattern in gameplay."""

    pattern_type: str
    description: str
    occurrences: int
    severity: str  # "low", "medium", "high"
    examples: List[int] = field(default_factory=list)  # Move numbers


@dataclass
class PlayerStats:
    """Per-player move classification counts and accuracy."""

    # Accuracy score (0-100), chess.com style
    accuracy: float = 0.0

    # Move classification counts
    brilliant: int = 0
    great: int = 0
    best: int = 0
    excellent: int = 0
    good: int = 0
    inaccuracy: int = 0
    mistake: int = 0
    blunder: int = 0
    forced: int = 0

    total_moves: int = 0
    average_eval_loss: float = 0.0

    def classification_counts(self) -> Dict[str, int]:
        """Return all classification counts as a dict."""
        return {
            "brilliant": self.brilliant,
            "great": self.great,
            "best": self.best,
            "excellent": self.excellent,
            "good": self.good,
            "inaccuracy": self.inaccuracy,
            "mistake": self.mistake,
            "blunder": self.blunder,
        }


@dataclass
class GameAnalysis:
    """Complete analysis of a chess game."""

    game_id: str
    metadata: GameMetadata
    pgn: str

    moves: List[MoveAnalysis] = field(default_factory=list)
    patterns: List[Pattern] = field(default_factory=list)

    analyzed_at: datetime = field(default_factory=datetime.now)
    analysis_time: float = 0.0

    # Aggregate statistics (all moves / target player)
    total_moves: int = 0
    blunders: int = 0
    mistakes: int = 0
    inaccuracies: int = 0
    average_eval_loss: float = 0.0

    # Per-player stats (chess.com style)
    white_stats: PlayerStats = field(default_factory=PlayerStats)
    black_stats: PlayerStats = field(default_factory=PlayerStats)

    # AI Feedback
    ai_summary: str = ""
    ai_strengths: List[str] = field(default_factory=list)
    ai_weaknesses: List[str] = field(default_factory=list)
    ai_recommendations: List[str] = field(default_factory=list)

    def get_player_moves(self, color: chess.Color) -> List[MoveAnalysis]:
        """Get all moves for a specific player."""
        return [m for m in self.moves if m.player_color == color]

    def get_errors(self, color: Optional[chess.Color] = None) -> List[MoveAnalysis]:
        """Get all error moves, optionally filtered by color."""
        errors = [m for m in self.moves if m.is_error]
        if color is not None:
            errors = [m for m in errors if m.player_color == color]
        return errors


@dataclass
class PlayerProfile:
    """Player profile with historical statistics."""

    player_name: str
    elo_rating: Optional[int] = None

    # Historical stats
    total_games: int = 0
    total_blunders: int = 0
    total_mistakes: int = 0
    total_inaccuracies: int = 0

    # Pattern history
    common_patterns: Dict[str, int] = field(default_factory=dict)
    improvement_areas: List[str] = field(default_factory=list)

    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
