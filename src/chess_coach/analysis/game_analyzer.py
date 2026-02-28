"""Single game analysis."""

import logging
import time
from typing import Optional

import chess
import chess.pgn
from io import StringIO

from ..engine import StockfishEngine
from ..models import (
    GameAnalysis,
    GameMetadata,
    MoveAnalysis,
    PlayerStats,
    PositionEvaluation,
    MoveClassification,
)
from .evaluator import MoveEvaluator

logger = logging.getLogger(__name__)


class GameAnalyzer:
    """Analyzes individual chess games."""

    def __init__(self, engine: StockfishEngine):
        """
        Initialize game analyzer.

        Args:
            engine: Stockfish engine instance
        """
        self.engine = engine
        self.evaluator = MoveEvaluator()

    def analyze_game(
        self,
        pgn: str,
        game_id: Optional[str] = None,
        target_player: Optional[str] = None,
    ) -> GameAnalysis:
        """
        Analyze a complete chess game.

        Args:
            pgn: PGN string of the game
            game_id: Unique identifier for the game
            target_player: Name of player to analyze (if None, analyze both)

        Returns:
            Complete game analysis
        """
        start_time = time.time()

        # Parse PGN
        game = chess.pgn.read_game(StringIO(pgn))
        if not game:
            raise ValueError("Invalid PGN")

        # Extract metadata
        metadata = self._extract_metadata(game)

        # Determine target color if player name provided
        target_color = None
        if target_player:
            if target_player.lower() in metadata.white_player.lower():
                target_color = chess.WHITE
            elif target_player.lower() in metadata.black_player.lower():
                target_color = chess.BLACK

        # Analyze all moves (always both colors for per-player stats)
        move_analyses = self._analyze_moves(game)

        # Calculate per-player stats
        white_stats = self._calculate_player_stats(move_analyses, chess.WHITE)
        black_stats = self._calculate_player_stats(move_analyses, chess.BLACK)

        # Aggregate stats for target color (or all moves if no target)
        target_moves = [
            m for m in move_analyses
            if target_color is None or m.player_color == target_color
        ]
        blunders = sum(1 for m in target_moves if m.is_blunder)
        mistakes = sum(1 for m in target_moves if m.is_mistake)
        inaccuracies = sum(1 for m in target_moves if m.is_inaccuracy)
        avg_loss = sum(m.eval_loss for m in target_moves) / len(target_moves) if target_moves else 0.0

        # Create analysis object
        analysis = GameAnalysis(
            game_id=game_id or self._generate_game_id(game),
            metadata=metadata,
            pgn=pgn,
            moves=move_analyses,
            total_moves=len(target_moves),
            blunders=blunders,
            mistakes=mistakes,
            inaccuracies=inaccuracies,
            average_eval_loss=avg_loss,
            white_stats=white_stats,
            black_stats=black_stats,
            analysis_time=time.time() - start_time,
        )

        logger.info(
            f"Analyzed game {analysis.game_id}: "
            f"{len(move_analyses)} moves, "
            f"{blunders} blunders, "
            f"{mistakes} mistakes, "
            f"{inaccuracies} inaccuracies"
        )

        return analysis

    def _extract_metadata(self, game: chess.pgn.Game) -> GameMetadata:
        """Extract metadata from PGN game."""
        headers = game.headers

        metadata = GameMetadata(
            white_player=headers.get("White", "Unknown"),
            black_player=headers.get("Black", "Unknown"),
            event=headers.get("Event", ""),
            site=headers.get("Site", ""),
            date=headers.get("Date", ""),
            result=headers.get("Result", "*"),
            opening=headers.get("Opening", ""),
            eco=headers.get("ECO", ""),
        )

        # Parse ELO ratings
        try:
            metadata.white_elo = int(headers.get("WhiteElo", 0)) or None
        except (ValueError, TypeError):
            metadata.white_elo = None

        try:
            metadata.black_elo = int(headers.get("BlackElo", 0)) or None
        except (ValueError, TypeError):
            metadata.black_elo = None

        return metadata

    def _analyze_moves(
        self, game: chess.pgn.Game
    ) -> list[MoveAnalysis]:
        """
        Analyze all moves in the game (both colors).

        Args:
            game: PGN game object

        Returns:
            List of move analyses
        """
        analyses = []
        board = game.board()
        node = game

        move_number = 0

        while node.variations:
            node = node.variation(0)
            move = node.move
            move_number += 1

            player_color = board.turn

            # Get SAN before making any move changes
            move_san = board.san(move)

            # Evaluate position before move
            eval_before = self.engine.evaluate_position(board)

            # Make the move
            board.push(move)

            # Evaluate position after move
            eval_after = self.engine.evaluate_position(board)

            # Get best move for the position before this move
            board.pop()
            best_move = self.engine.get_best_move(board)
            was_best_move = move == best_move
            board.push(move)

            # Calculate evaluation loss
            eval_loss = self.evaluator.calculate_eval_loss(
                eval_before, eval_after, player_color
            )

            # Calculate move accuracy (chess.com formula)
            move_accuracy = self.evaluator.calculate_move_accuracy(
                eval_before, eval_after, player_color
            )

            # Classify move
            classification = self.evaluator.classify_move(
                eval_loss, eval_before, eval_after, was_best_move
            )

            # Identify mistake type if applicable
            mistake_type = None
            if classification in [
                MoveClassification.BLUNDER,
                MoveClassification.MISTAKE,
                MoveClassification.INACCURACY,
            ]:
                mistake_type = self.evaluator.identify_mistake_type(
                    move_number, board, eval_loss
                )

            move_analysis = MoveAnalysis(
                move_number=move_number,
                move_san=move_san,
                move_uci=move.uci(),
                player_color=player_color,
                eval_before=eval_before,
                eval_after=eval_after,
                classification=classification,
                eval_loss=eval_loss,
                move_accuracy=move_accuracy,
                is_blunder=classification == MoveClassification.BLUNDER,
                is_mistake=classification == MoveClassification.MISTAKE,
                is_inaccuracy=classification == MoveClassification.INACCURACY,
                mistake_type=mistake_type,
            )

            analyses.append(move_analysis)

        return analyses

    def _calculate_player_stats(
        self, moves: list[MoveAnalysis], color: chess.Color
    ) -> PlayerStats:
        """Calculate stats for a single player."""
        player_moves = [m for m in moves if m.player_color == color]

        if not player_moves:
            return PlayerStats()

        # Count each classification
        counts = {c: 0 for c in MoveClassification}
        for m in player_moves:
            counts[m.classification] += 1

        avg_accuracy = sum(m.move_accuracy for m in player_moves) / len(player_moves)
        avg_loss = sum(m.eval_loss for m in player_moves) / len(player_moves)

        return PlayerStats(
            accuracy=round(avg_accuracy, 1),
            brilliant=counts[MoveClassification.BRILLIANT],
            great=counts[MoveClassification.GREAT],
            best=counts[MoveClassification.BEST],
            excellent=counts[MoveClassification.EXCELLENT],
            good=counts[MoveClassification.GOOD],
            inaccuracy=counts[MoveClassification.INACCURACY],
            mistake=counts[MoveClassification.MISTAKE],
            blunder=counts[MoveClassification.BLUNDER],
            forced=counts[MoveClassification.FORCED],
            total_moves=len(player_moves),
            average_eval_loss=round(avg_loss, 1),
        )

    def _generate_game_id(self, game: chess.pgn.Game) -> str:
        """Generate a unique game ID from headers."""
        headers = game.headers
        white = headers.get("White", "unknown")
        black = headers.get("Black", "unknown")
        date = headers.get("Date", "unknown")
        site = headers.get("Site", "unknown")

        # Simple hash-like ID
        game_id = f"{white}_{black}_{date}_{site}".replace(" ", "_").replace(".", "_")
        return game_id[:64]  # Limit length
