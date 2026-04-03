"""Stockfish chess engine interface."""

import asyncio
import logging
from pathlib import Path
from typing import Optional, List
import shutil

import chess
import chess.engine

from ..config import settings
from ..models import PositionEvaluation

logger = logging.getLogger(__name__)


# ── Helpers ────────────────────────────────────────────────────────────────────

def normalize_fen(fen: str) -> str:
    """Strip halfmove clock and fullmove counters from FEN for cache-key use.

    FEN format: pieces side castling en-passant halfmove fullmove
    We keep the first 4 fields so positions reached via different move orders
    still share the same cache key.
    """
    return " ".join(fen.split()[:4])


def describe_position(board: chess.Board) -> str:
    """Convert a board position to natural language for LLM prompts.

    LLMs cannot reliably interpret raw FEN strings, so we describe:
    - Material balance
    - King safety / castling state
    - Active threats
    - Recent piece activity (piece counts by type)
    """
    lines: List[str] = []

    # Material count
    piece_names = {
        chess.QUEEN: "queen", chess.ROOK: "rook", chess.BISHOP: "bishop",
        chess.KNIGHT: "knight", chess.PAWN: "pawn",
    }
    for color, label in [(chess.WHITE, "White"), (chess.BLACK, "Black")]:
        parts = []
        for ptype, name in piece_names.items():
            count = len(board.pieces(ptype, color))
            if count:
                parts.append(f"{count} {name}{'s' if count > 1 else ''}")
        lines.append(f"{label}: {', '.join(parts) if parts else 'king only'}")

    # King safety
    wk_sq = board.king(chess.WHITE)
    bk_sq = board.king(chess.BLACK)
    wk_castled = wk_sq is not None and chess.square_file(wk_sq) in (6, 2)
    bk_castled = bk_sq is not None and chess.square_file(bk_sq) in (6, 2)
    wk_can_castle = board.has_castling_rights(chess.WHITE)
    bk_can_castle = board.has_castling_rights(chess.BLACK)
    lines.append(
        f"White king: {'castled' if wk_castled else 'can castle' if wk_can_castle else 'centralised/uncastled'}"
    )
    lines.append(
        f"Black king: {'castled' if bk_castled else 'can castle' if bk_can_castle else 'centralised/uncastled'}"
    )

    # Check / in-check
    if board.is_check():
        side = "White" if board.turn == chess.WHITE else "Black"
        lines.append(f"{side} is in check")

    # Hanging pieces (attacked but not defended)
    hanging = []
    for sq in chess.SQUARES:
        piece = board.piece_at(sq)
        if piece and piece.color != board.turn:
            attackers = board.attackers(board.turn, sq)
            defenders = board.attackers(piece.color, sq)
            if attackers and not defenders:
                hanging.append(f"{piece.symbol().upper()} on {chess.square_name(sq)}")
    if hanging:
        lines.append(f"Hanging pieces: {', '.join(hanging[:3])}")

    return "\n".join(lines)


def get_game_phase(board: chess.Board) -> str:
    """Infer game phase from move number and remaining major pieces."""
    total_pieces = len(board.pieces(chess.QUEEN, chess.WHITE)) + \
                   len(board.pieces(chess.QUEEN, chess.BLACK)) + \
                   len(board.pieces(chess.ROOK, chess.WHITE)) + \
                   len(board.pieces(chess.ROOK, chess.BLACK))
    fullmove = board.fullmove_number
    if fullmove <= 10:
        return "opening"
    if total_pieces <= 2:
        return "endgame"
    return "middlegame"


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

    def get_continuation(
        self,
        board: chess.Board,
        num_moves: int = 3,
        depth: Optional[int] = None,
    ) -> List[str]:
        """
        Get Stockfish's best continuation from a position as SAN strings.

        Plays the engine's top move repeatedly for *num_moves* half-moves.
        Returns a list like ['Qxh7+', 'Kf1', 'Qh1#'].
        """
        if not self.engine:
            raise RuntimeError("Engine not started.")

        temp_board = board.copy()
        sans: List[str] = []
        limit = chess.engine.Limit(depth=depth or max(self.depth - 4, 8))

        for _ in range(num_moves):
            if temp_board.is_game_over():
                break
            result = self.engine.play(temp_board, limit)
            if result.move is None:
                break
            san = temp_board.san(result.move)
            sans.append(san)
            temp_board.push(result.move)

        return sans

    def ping(self) -> bool:
        """Return True if the engine process is alive."""
        if not self.engine:
            return False
        try:
            # SimpleEngine exposes the underlying process via .transport
            return self.engine.transport is not None and \
                   self.engine.transport.get_pid() is not None  # type: ignore[attr-defined]
        except Exception:
            return False


# ── StockfishPool ─────────────────────────────────────────────────────────────

class StockfishPool:
    """
    Async pool of StockfishEngine instances.

    Solves two problems:
    1. One Stockfish process is not concurrency-safe — games + per-move requests
       collide on a single process.
    2. Per-user rate limiting: each acquire() wins an engine slot; release()
       returns it so other tasks don't starve.

    Usage (as async context manager)::

        async with pool.acquire() as engine:
            result = engine.get_continuation(board)
    """

    def __init__(self, min_size: int = 1, max_size: int = 3):
        self._max = max_size
        self._queue: asyncio.Queue["StockfishEngine"] = asyncio.Queue(maxsize=max_size)
        self._created = 0
        self._lock = asyncio.Lock()
        # Eagerly start min_size engines
        for _ in range(min_size):
            engine = StockfishEngine()
            engine.start()
            self._queue.put_nowait(engine)
            self._created += 1

    async def acquire(self) -> "StockfishEngine":
        """Get a live engine, spawning a new one if pool not at max."""
        # Try non-blocking first
        try:
            engine = self._queue.get_nowait()
            if not engine.ping():
                logger.warning("StockfishPool: dead engine detected, replacing")
                try:
                    engine.stop()
                except Exception:
                    pass
                engine = StockfishEngine()
                engine.start()
            logger.debug(f"StockfishPool: acquired (from queue) pool_size={self._queue.qsize()}")
            return engine
        except asyncio.QueueEmpty:
            pass

        # Spawn a new one if under max
        async with self._lock:
            if self._created < self._max:
                engine = StockfishEngine()
                engine.start()
                self._created += 1
                logger.debug(f"StockfishPool: spawned engine #{self._created}")
                return engine

        # At max — wait for one to be returned
        logger.debug(f"StockfishPool: at max ({self._max}), waiting for available engine")
        engine = await self._queue.get()
        if not engine.ping():
            try:
                engine.stop()
            except Exception:
                pass
            engine = StockfishEngine()
            engine.start()
        logger.debug(f"StockfishPool: acquired (after wait) pool_size={self._queue.qsize()}")
        return engine

    def release(self, engine: "StockfishEngine") -> None:
        """Return an engine to the pool."""
        try:
            self._queue.put_nowait(engine)
            logger.debug(f"StockfishPool: released engine pool_size={self._queue.qsize()}")
        except asyncio.QueueFull:
            logger.debug("StockfishPool: pool full on release, stopping extra engine")
            engine.stop()

    async def close(self) -> None:
        """Stop all pooled engines."""
        while not self._queue.empty():
            try:
                engine = self._queue.get_nowait()
                engine.stop()
            except Exception:
                pass

    class _EngineContext:
        """Async context manager returned by acquire_ctx()."""
        def __init__(self, pool: "StockfishPool"):
            self._pool = pool
            self._engine: Optional[StockfishEngine] = None

        async def __aenter__(self) -> "StockfishEngine":
            self._engine = await self._pool.acquire()
            return self._engine

        async def __aexit__(self, *_):
            if self._engine:
                self._pool.release(self._engine)

    def acquire_ctx(self) -> "_EngineContext":
        """Use as: `async with pool.acquire_ctx() as engine:`"""
        return self._EngineContext(self)


# Module-level singleton pool — lazily initialised on first use
_pool: Optional[StockfishPool] = None


def get_engine_pool() -> StockfishPool:
    """Return (lazily creating) the singleton StockfishPool."""
    global _pool
    if _pool is None:
        _pool = StockfishPool(min_size=1, max_size=3)
    return _pool
