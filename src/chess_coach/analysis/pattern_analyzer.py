"""Multi-game pattern analysis."""

import logging
from collections import defaultdict
from typing import List, Dict, Optional

import chess

from ..models import GameAnalysis, Pattern, MistakeType

logger = logging.getLogger(__name__)


class PatternAnalyzer:
    """Analyzes patterns across multiple games."""

    def __init__(self):
        """Initialize pattern analyzer."""
        pass

    def analyze_games(
        self, games: List[GameAnalysis], player_color: Optional[chess.Color] = None
    ) -> Dict:
        """
        Analyze patterns across multiple games.

        Args:
            games: List of analyzed games
            player_color: Color to analyze (None = both)

        Returns:
            Dict with pattern analysis results
        """
        if not games:
            return {
                "num_games": 0,
                "patterns": [],
                "opening_analysis": {},
                "phase_analysis": {},
                "tactical_analysis": {},
            }

        patterns = []

        # Analyze openings
        opening_patterns = self._analyze_openings(games, player_color)
        patterns.extend(opening_patterns)

        # Analyze game phases
        phase_patterns = self._analyze_phases(games, player_color)
        patterns.extend(phase_patterns)

        # Analyze tactical mistakes
        tactical_patterns = self._analyze_tactical_mistakes(games, player_color)
        patterns.extend(tactical_patterns)

        # Analyze mistake types
        mistake_patterns = self._analyze_mistake_types(games, player_color)
        patterns.extend(mistake_patterns)

        return {
            "num_games": len(games),
            "patterns": patterns,
            "opening_analysis": self._summarize_openings(games, player_color),
            "phase_analysis": self._summarize_phases(games, player_color),
            "tactical_analysis": self._summarize_tactical(games, player_color),
        }

    def _analyze_openings(
        self, games: List[GameAnalysis], player_color: Optional[chess.Color]
    ) -> List[Pattern]:
        """Analyze opening performance."""
        patterns = []
        opening_stats = defaultdict(lambda: {"games": 0, "errors": 0})

        for game in games:
            opening = game.metadata.opening or "Unknown"

            # Get early game errors (first 15 moves)
            early_errors = [
                m
                for m in game.moves
                if m.move_number <= 15
                and m.is_error
                and (player_color is None or m.player_color == player_color)
            ]

            opening_stats[opening]["games"] += 1
            opening_stats[opening]["errors"] += len(early_errors)

        # Find problematic openings
        for opening, stats in opening_stats.items():
            if stats["games"] >= 2 and stats["errors"] >= stats["games"]:
                patterns.append(
                    Pattern(
                        pattern_type="opening_weakness",
                        description=f"Frequent errors in {opening} opening",
                        occurrences=stats["errors"],
                        severity="medium" if stats["errors"] < 5 else "high",
                        examples=[],
                    )
                )

        return patterns

    def _analyze_phases(
        self, games: List[GameAnalysis], player_color: Optional[chess.Color]
    ) -> List[Pattern]:
        """Analyze performance by game phase."""
        patterns = []

        phase_errors = {
            "opening": defaultdict(int),  # moves 1-15
            "middlegame": defaultdict(int),  # moves 16-40
            "endgame": defaultdict(int),  # moves 40+
        }

        for game in games:
            for move in game.moves:
                if player_color is not None and move.player_color != player_color:
                    continue

                if not move.is_error:
                    continue

                # Determine phase
                if move.move_number <= 15:
                    phase = "opening"
                elif move.move_number <= 40:
                    phase = "middlegame"
                else:
                    phase = "endgame"

                # Count error types
                if move.is_blunder:
                    phase_errors[phase]["blunders"] += 1
                elif move.is_mistake:
                    phase_errors[phase]["mistakes"] += 1
                elif move.is_inaccuracy:
                    phase_errors[phase]["inaccuracies"] += 1

        # Identify weak phases
        for phase, errors in phase_errors.items():
            total_errors = sum(errors.values())
            if total_errors >= 5:
                severity = "high" if total_errors >= 10 else "medium"
                patterns.append(
                    Pattern(
                        pattern_type=f"{phase}_weakness",
                        description=f"Frequent errors in {phase} phase",
                        occurrences=total_errors,
                        severity=severity,
                        examples=[],
                    )
                )

        return patterns

    def _analyze_tactical_mistakes(
        self, games: List[GameAnalysis], player_color: Optional[chess.Color]
    ) -> List[Pattern]:
        """Analyze tactical mistake patterns."""
        patterns = []
        tactical_errors = 0

        for game in games:
            for move in game.moves:
                if player_color is not None and move.player_color != player_color:
                    continue

                if (
                    move.mistake_type == MistakeType.TACTICAL
                    and move.eval_loss >= 100
                ):
                    tactical_errors += 1

        if tactical_errors >= 5:
            severity = "high" if tactical_errors >= 10 else "medium"
            patterns.append(
                Pattern(
                    pattern_type="tactical_oversight",
                    description="Frequent tactical oversights (hanging pieces, missed tactics)",
                    occurrences=tactical_errors,
                    severity=severity,
                    examples=[],
                )
            )

        return patterns

    def _analyze_mistake_types(
        self, games: List[GameAnalysis], player_color: Optional[chess.Color]
    ) -> List[Pattern]:
        """Analyze distribution of mistake types."""
        patterns = []
        mistake_counts = defaultdict(int)

        for game in games:
            for move in game.moves:
                if player_color is not None and move.player_color != player_color:
                    continue

                if move.mistake_type:
                    mistake_counts[move.mistake_type.value] += 1

        # Identify dominant mistake types
        for mistake_type, count in mistake_counts.items():
            if count >= 5:
                severity = "high" if count >= 10 else "medium"
                patterns.append(
                    Pattern(
                        pattern_type=f"{mistake_type}_mistakes",
                        description=f"Recurring {mistake_type} mistakes",
                        occurrences=count,
                        severity=severity,
                        examples=[],
                    )
                )

        return patterns

    def _summarize_openings(
        self, games: List[GameAnalysis], player_color: Optional[chess.Color]
    ) -> Dict:
        """Summarize opening performance."""
        opening_stats = defaultdict(
            lambda: {"games": 0, "wins": 0, "losses": 0, "draws": 0, "avg_errors": 0.0}
        )

        for game in games:
            opening = game.metadata.opening or "Unknown"
            opening_stats[opening]["games"] += 1

            # Count result
            result = game.metadata.result
            if result == "1-0":
                opening_stats[opening]["wins"] += 1
            elif result == "0-1":
                opening_stats[opening]["losses"] += 1
            else:
                opening_stats[opening]["draws"] += 1

            # Count early errors
            early_errors = len(
                [
                    m
                    for m in game.moves
                    if m.move_number <= 15
                    and m.is_error
                    and (player_color is None or m.player_color == player_color)
                ]
            )
            opening_stats[opening]["avg_errors"] += early_errors

        # Calculate averages
        for opening, stats in opening_stats.items():
            stats["avg_errors"] /= stats["games"]

        return dict(opening_stats)

    def _summarize_phases(
        self, games: List[GameAnalysis], player_color: Optional[chess.Color]
    ) -> Dict:
        """Summarize phase performance."""
        phase_stats = {
            "opening": {"moves": 0, "errors": 0, "avg_loss": 0.0},
            "middlegame": {"moves": 0, "errors": 0, "avg_loss": 0.0},
            "endgame": {"moves": 0, "errors": 0, "avg_loss": 0.0},
        }

        for game in games:
            for move in game.moves:
                if player_color is not None and move.player_color != player_color:
                    continue

                # Determine phase
                if move.move_number <= 15:
                    phase = "opening"
                elif move.move_number <= 40:
                    phase = "middlegame"
                else:
                    phase = "endgame"

                phase_stats[phase]["moves"] += 1
                if move.is_error:
                    phase_stats[phase]["errors"] += 1
                phase_stats[phase]["avg_loss"] += move.eval_loss

        # Calculate averages
        for phase, stats in phase_stats.items():
            if stats["moves"] > 0:
                stats["avg_loss"] /= stats["moves"]
                stats["error_rate"] = stats["errors"] / stats["moves"]

        return phase_stats

    def _summarize_tactical(
        self, games: List[GameAnalysis], player_color: Optional[chess.Color]
    ) -> Dict:
        """Summarize tactical performance."""
        tactical_stats = {
            "total_tactical_errors": 0,
            "blunders": 0,
            "mistakes": 0,
            "inaccuracies": 0,
            "avg_tactical_loss": 0.0,
        }

        tactical_errors = []

        for game in games:
            for move in game.moves:
                if player_color is not None and move.player_color != player_color:
                    continue

                if move.mistake_type == MistakeType.TACTICAL:
                    tactical_errors.append(move)
                    tactical_stats["total_tactical_errors"] += 1

                    if move.is_blunder:
                        tactical_stats["blunders"] += 1
                    elif move.is_mistake:
                        tactical_stats["mistakes"] += 1
                    elif move.is_inaccuracy:
                        tactical_stats["inaccuracies"] += 1

        if tactical_errors:
            tactical_stats["avg_tactical_loss"] = sum(
                m.eval_loss for m in tactical_errors
            ) / len(tactical_errors)

        return tactical_stats


# ── Per-move tactical motif detection ────────────────────────────────────────

def detect_motif(board_before: chess.Board, move: chess.Move) -> Optional[str]:
    """
    Detect the primary tactical motif of *move* played on *board_before*.

    Uses pure python-chess attack / pin detection — no Stockfish, no LLM.
    Returns one of: "fork", "pin", "skewer", "discovered_attack",
    "back_rank", "removal_of_defender", or None.
    """
    board = board_before.copy()
    moving_piece = board.piece_at(move.from_square)
    if moving_piece is None:
        return None

    attacker_color = moving_piece.color
    defender_color = not attacker_color

    board.push(move)

    # ── Back-rank mate threat ─────────────────────────────────────────────────
    back_rank = chess.BB_RANK_1 if defender_color == chess.WHITE else chess.BB_RANK_8
    king_sq = board.king(defender_color)
    if king_sq is not None and (chess.BB_SQUARES[king_sq] & back_rank):
        # Check if a rook or queen now threatens the back rank
        for sq in chess.SquareSet(back_rank):
            if board.is_attacked_by(attacker_color, sq):
                return "back_rank"

    # ── Fork — landing square attacks 2+ valuable pieces ─────────────────────
    attacked_values: List[int] = []
    _value = {chess.QUEEN: 9, chess.ROOK: 5, chess.BISHOP: 3,
              chess.KNIGHT: 3, chess.PAWN: 1, chess.KING: 100}
    for sq in board.attacks(move.to_square):
        victim = board.piece_at(sq)
        if victim and victim.color == defender_color:
            attacked_values.append(_value.get(victim.piece_type, 0))
    if len(attacked_values) >= 2 and sum(sorted(attacked_values)[-2:]) >= 6:
        return "fork"

    # ── Pin — moving piece now pins a defender to their king ─────────────────
    for sq in chess.SQUARES:
        piece = board.piece_at(sq)
        if piece and piece.color == defender_color and piece.piece_type != chess.KING:
            if board.is_pinned(defender_color, sq):
                return "pin"

    # ── Skewer — moving piece X-rays through a high-value piece ─────────────
    if moving_piece.piece_type in (chess.QUEEN, chess.ROOK, chess.BISHOP):
        for sq in board.attacks(move.to_square):
            victim = board.piece_at(sq)
            if victim and victim.color == defender_color:
                if _value.get(victim.piece_type, 0) >= 5:  # rook or queen
                    # Check there is something behind it on the ray
                    direction = chess.square_file(sq) - chess.square_file(move.to_square), \
                                chess.square_rank(sq) - chess.square_rank(move.to_square)
                    if direction != (0, 0):
                        return "skewer"

    # ── Discovered attack — piece that moved reveals an attack behind it ─────
    prev_attacks = board_before.attacks(move.from_square)
    for sq in prev_attacks:
        if board.is_attacked_by(attacker_color, sq) and not board_before.is_attacked_by(attacker_color, sq):
            victim = board.piece_at(sq)
            if victim and victim.color == defender_color and _value.get(victim.piece_type, 0) >= 3:
                return "discovered_attack"

    # ── Removal of defender ───────────────────────────────────────────────────
    captured = board_before.piece_at(move.to_square)
    if captured:
        # Was the captured piece defending something valuable?
        for sq in board_before.attacks(move.to_square):
            defended = board_before.piece_at(sq)
            if defended and defended.color == defender_color:
                was_defended_by_captured = move.to_square in board_before.attackers(
                    defender_color, sq
                )
                if was_defended_by_captured and _value.get(defended.piece_type, 0) >= 3:
                    return "removal_of_defender"

    return None
