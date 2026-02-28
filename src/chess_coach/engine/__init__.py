"""Stockfish chess engine interface."""

import logging
from pathlib import Path
from typing import Optional, List
import shutil

import chess
import chess.engine

from ..config import settings
from ..models import PositionEvaluation

logger = logging.getLogger(__name__)


class StockfishEngine:
    """Interface to Stockfish chess engine."""

    def __init__(
        self,
        stockfish_path: Optional[str] = None,
        depth: Optional[int] = None,
        time_limit: Optional[float] = None,
    ):
        """
        Initialize Stockfish engine.

        Args:
            stockfish_path: Path to Stockfish binary (auto-detect if None)
            depth: Search depth (uses config default if None)
            time_limit: Time limit in seconds (uses config default if None)
        """
        self.depth = depth or settings.stockfish_depth
        self.time_limit = time_limit or settings.stockfish_time_limit
        self.engine: Optional[chess.engine.SimpleEngine] = None
        self.stockfish_path = self._find_stockfish(stockfish_path)

    def _find_stockfish(self, path: Optional[str] = None) -> Path:
        """Find Stockfish binary."""
        if path and path != "auto":
            binary_path = Path(path)
            if binary_path.exists():
                return binary_path
            raise FileNotFoundError(f"Stockfish not found at: {path}")

        # Auto-detect Stockfish
        stockfish_names = ["stockfish", "stockfish-18", "stockfish.exe"]
        for name in stockfish_names:
            found = shutil.which(name)
            if found:
                logger.info(f"Found Stockfish at: {found}")
                return Path(found)

        raise FileNotFoundError(
            "Stockfish not found. Please install Stockfish or specify path in .env"
        )

    def start(self):
        """Start the Stockfish engine."""
        if self.engine is None:
            logger.info(f"Starting Stockfish from: {self.stockfish_path}")
            self.engine = chess.engine.SimpleEngine.popen_uci(str(self.stockfish_path))

    def stop(self):
        """Stop the Stockfish engine."""
        if self.engine:
            self.engine.quit()
            self.engine = None

    def __enter__(self):
        """Context manager entry."""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.stop()

    def evaluate_position(
        self,
        board: chess.Board,
        depth: Optional[int] = None,
        time_limit: Optional[float] = None,
    ) -> PositionEvaluation:
        """
        Evaluate a chess position.

        Args:
            board: Chess board position
            depth: Search depth (uses instance default if None)
            time_limit: Time limit in seconds (uses instance default if None)

        Returns:
            PositionEvaluation with score and best move
        """
        if not self.engine:
            raise RuntimeError("Engine not started. Call start() or use context manager.")

        limit = chess.engine.Limit(
            depth=depth or self.depth,
            time=time_limit or self.time_limit,
        )

        info = self.engine.analyse(board, limit)

        eval_obj = PositionEvaluation(depth=info.get("depth", 0))

        # Extract score
        score = info.get("score")
        if score:
            # Adjust score perspective (always from white's POV)
            white_score = score.white()

            if white_score.is_mate():
                eval_obj.mate_score = white_score.mate()
            else:
                eval_obj.cp_score = white_score.score()

        # Extract best move
        pv = info.get("pv")
        if pv:
            eval_obj.best_move = board.san(pv[0])
            eval_obj.pv_line = [board.variation_san(pv)]

        return eval_obj

    def get_best_move(
        self,
        board: chess.Board,
        depth: Optional[int] = None,
        time_limit: Optional[float] = None,
    ) -> Optional[chess.Move]:
        """
        Get the best move for a position.

        Args:
            board: Chess board position
            depth: Search depth (uses instance default if None)
            time_limit: Time limit in seconds (uses instance default if None)

        Returns:
            Best move or None
        """
        if not self.engine:
            raise RuntimeError("Engine not started. Call start() or use context manager.")

        limit = chess.engine.Limit(
            depth=depth or self.depth,
            time=time_limit or self.time_limit,
        )

        result = self.engine.play(board, limit)
        return result.move

    def analyze_variation(
        self,
        board: chess.Board,
        moves: List[str],
        depth: Optional[int] = None,
    ) -> List[PositionEvaluation]:
        """
        Analyze a sequence of moves.

        Args:
            board: Starting position
            moves: List of moves in UCI format
            depth: Search depth (uses instance default if None)

        Returns:
            List of evaluations for each position
        """
        evaluations = []
        temp_board = board.copy()

        for move_uci in moves:
            try:
                move = chess.Move.from_uci(move_uci)
                temp_board.push(move)
                eval_obj = self.evaluate_position(temp_board, depth=depth)
                evaluations.append(eval_obj)
            except ValueError as e:
                logger.warning(f"Invalid move {move_uci}: {e}")
                break

        return evaluations
