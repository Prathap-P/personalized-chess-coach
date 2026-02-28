"""Move evaluation logic."""

import logging
import math
from typing import Optional

import chess

from ..models import (
    MoveClassification,
    MistakeType,
    PositionEvaluation,
)

logger = logging.getLogger(__name__)


class MoveEvaluator:
    """Evaluates chess moves based on engine analysis."""

    # Centipawn loss thresholds (aligned with chess.com)
    BRILLIANT_THRESHOLD = -50    # Gains significant advantage in non-obvious way
    GREAT_THRESHOLD = -20        # Gains advantage
    INACCURACY_THRESHOLD = 50    # Moderate loss
    MISTAKE_THRESHOLD = 100      # Significant loss
    BLUNDER_THRESHOLD = 200      # Large loss

    @staticmethod
    def win_percentage(cp: float) -> float:
        """
        Convert centipawn score to win percentage (chess.com formula).
        Returns a value between 0 and 100.
        """
        return 50 + 50 * (2 / (1 + math.exp(-0.00368208 * cp)) - 1)

    @staticmethod
    def calculate_move_accuracy(
        eval_before: PositionEvaluation,
        eval_after: PositionEvaluation,
        player_color: chess.Color,
    ) -> float:
        """
        Calculate accuracy for a single move (0-100), using chess.com formula.

        accuracy = 103.1668 * exp(-0.04354 * win%_loss) - 3.1669
        Clamped to [0, 100].
        """
        # Get centipawn scores from the player's perspective
        if eval_before.is_mate:
            cp_before = 10000 if (eval_before.mate_score > 0) == (player_color == chess.WHITE) else -10000
        else:
            cp_before = (eval_before.cp_score or 0) if player_color == chess.WHITE else -(eval_before.cp_score or 0)

        if eval_after.is_mate:
            cp_after = 10000 if (eval_after.mate_score > 0) == (player_color == chess.WHITE) else -10000
        else:
            cp_after = (eval_after.cp_score or 0) if player_color == chess.WHITE else -(eval_after.cp_score or 0)

        win_before = MoveEvaluator.win_percentage(cp_before)
        win_after = MoveEvaluator.win_percentage(cp_after)

        win_loss = max(0.0, win_before - win_after)
        accuracy = 103.1668 * math.exp(-0.04354 * win_loss) - 3.1669
        return round(max(0.0, min(100.0, accuracy)), 2)

    @staticmethod
    def calculate_eval_loss(
        eval_before: PositionEvaluation,
        eval_after: PositionEvaluation,
        player_color: chess.Color,
    ) -> float:
        """
        Calculate evaluation loss from player's perspective.

        Args:
            eval_before: Position evaluation before move
            eval_after: Position evaluation after move
            player_color: Color of player who made the move

        Returns:
            Centipawn loss (positive = worse position)
        """
        # Handle mate scores
        if eval_before.is_mate or eval_after.is_mate:
            return MoveEvaluator._calculate_mate_loss(
                eval_before, eval_after, player_color
            )

        # Convert to player's perspective
        score_before = (
            eval_before.cp_score or 0
            if player_color == chess.WHITE
            else -(eval_before.cp_score or 0)
        )
        score_after = (
            eval_after.cp_score or 0
            if player_color == chess.WHITE
            else -(eval_after.cp_score or 0)
        )

        # Loss is negative change in evaluation
        loss = score_before - score_after
        return max(0.0, loss)  # Only count losses, not gains

    @staticmethod
    def _calculate_mate_loss(
        eval_before: PositionEvaluation,
        eval_after: PositionEvaluation,
        player_color: chess.Color,
    ) -> float:
        """Calculate loss when mate scores are involved."""
        # Converting mate to winning: huge loss
        if eval_before.is_mate and not eval_after.is_mate:
            mate_in = eval_before.mate_score
            if (mate_in > 0 and player_color == chess.WHITE) or (
                mate_in < 0 and player_color == chess.BLACK
            ):
                return 1000.0  # Lost a mate - huge blunder

        # Converting winning to mate: very good
        if not eval_before.is_mate and eval_after.is_mate:
            return -200.0  # Negative loss = gain

        # Both mates: compare mate distances
        if eval_before.is_mate and eval_after.is_mate:
            # Longer mate is worse
            mate_diff = abs(eval_after.mate_score) - abs(eval_before.mate_score)
            if player_color == chess.WHITE:
                return mate_diff * 100.0
            else:
                return -mate_diff * 100.0

        return 0.0

    @classmethod
    def classify_move(
        cls,
        eval_loss: float,
        eval_before: PositionEvaluation,
        eval_after: PositionEvaluation,
        was_best_move: bool,
    ) -> MoveClassification:
        """
        Classify move quality based on evaluation loss.

        Args:
            eval_loss: Centipawn loss
            eval_before: Evaluation before move
            eval_after: Evaluation after move
            was_best_move: Whether the move played was the best move

        Returns:
            Move classification
        """
        # Check for forced moves (only legal move)
        # This would need board context, so we skip for now

        # Brilliant move: gained significant advantage in non-obvious way
        if eval_loss < -cls.BRILLIANT_THRESHOLD and not was_best_move:
            return MoveClassification.BRILLIANT

        # Great move: significant improvement
        if eval_loss < -cls.GREAT_THRESHOLD:
            return MoveClassification.GREAT

        # Best move
        if was_best_move and eval_loss <= 0:
            return MoveClassification.BEST

        # Excellent move (no loss)
        if eval_loss <= 0:
            return MoveClassification.EXCELLENT

        # Good move (minimal loss)
        if eval_loss < cls.INACCURACY_THRESHOLD:
            return MoveClassification.GOOD

        # Blunder (huge loss)
        if eval_loss >= cls.BLUNDER_THRESHOLD:
            return MoveClassification.BLUNDER

        # Mistake (significant loss)
        if eval_loss >= cls.MISTAKE_THRESHOLD:
            return MoveClassification.MISTAKE

        # Inaccuracy (moderate loss)
        return MoveClassification.INACCURACY

    @staticmethod
    def identify_mistake_type(
        move_number: int,
        position: chess.Board,
        eval_loss: float,
    ) -> Optional[MistakeType]:
        """
        Identify the type of mistake based on context.

        Args:
            move_number: Move number in game
            position: Board position
            eval_loss: Centipawn loss

        Returns:
            Type of mistake or None if not a mistake
        """
        # Not a significant mistake
        if eval_loss < 25:
            return None

        # Opening phase (first 15 moves)
        if move_number <= 15:
            return MistakeType.OPENING

        # Endgame (few pieces left)
        piece_count = len(position.piece_map())
        if piece_count <= 10:
            return MistakeType.ENDGAME

        # Large eval loss suggests tactical oversight
        if eval_loss >= 300:
            return MistakeType.TACTICAL

        # Default to positional for moderate mistakes
        return MistakeType.POSITIONAL
