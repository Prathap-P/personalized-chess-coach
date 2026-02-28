"""Storage layer for game analyses."""

import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional, List

from ..config import settings
from ..models import GameAnalysis, GameMetadata, MoveAnalysis, Pattern, PlayerStats

logger = logging.getLogger(__name__)


class GameStorage:
    """SQLite-based storage for game analyses."""

    def __init__(self, db_path: Optional[Path] = None):
        """
        Initialize storage.

        Args:
            db_path: Path to SQLite database (uses default if None)
        """
        self.db_path = db_path or settings.cache_dir / "analyses.db"
        self._init_db()

    def _init_db(self):
        """Initialize database schema."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS game_analyses (
                    game_id TEXT PRIMARY KEY,
                    pgn TEXT NOT NULL,
                    metadata TEXT NOT NULL,
                    moves TEXT NOT NULL,
                    patterns TEXT NOT NULL,
                    statistics TEXT NOT NULL,
                    ai_feedback TEXT,
                    analyzed_at TIMESTAMP NOT NULL,
                    analysis_time REAL NOT NULL
                )
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_analyzed_at
                ON game_analyses(analyzed_at)
            """)

    def save_analysis(self, analysis: GameAnalysis) -> None:
        """
        Save game analysis to database.

        Args:
            analysis: Game analysis to save
        """
        with sqlite3.connect(self.db_path) as conn:
            # Serialize data
            metadata_json = json.dumps({
                'white_player': analysis.metadata.white_player,
                'black_player': analysis.metadata.black_player,
                'white_elo': analysis.metadata.white_elo,
                'black_elo': analysis.metadata.black_elo,
                'event': analysis.metadata.event,
                'site': analysis.metadata.site,
                'date': analysis.metadata.date,
                'result': analysis.metadata.result,
                'opening': analysis.metadata.opening,
                'eco': analysis.metadata.eco,
            })

            moves_json = json.dumps([
                {
                    'move_number': m.move_number,
                    'move_san': m.move_san,
                    'move_uci': m.move_uci,
                    'player_color': m.player_color,
                    'classification': m.classification.value,
                    'eval_loss': m.eval_loss,
                    'move_accuracy': m.move_accuracy,
                    'is_blunder': m.is_blunder,
                    'is_mistake': m.is_mistake,
                    'is_inaccuracy': m.is_inaccuracy,
                    'mistake_type': m.mistake_type.value if m.mistake_type else None,
                    'comment': m.comment,
                }
                for m in analysis.moves
            ])

            patterns_json = json.dumps([
                {
                    'pattern_type': p.pattern_type,
                    'description': p.description,
                    'occurrences': p.occurrences,
                    'severity': p.severity,
                    'examples': p.examples,
                }
                for p in analysis.patterns
            ])

            def _stats_to_dict(s: PlayerStats) -> dict:
                return {
                    'accuracy': s.accuracy,
                    'brilliant': s.brilliant, 'great': s.great, 'best': s.best,
                    'excellent': s.excellent, 'good': s.good,
                    'inaccuracy': s.inaccuracy, 'mistake': s.mistake,
                    'blunder': s.blunder, 'forced': s.forced,
                    'total_moves': s.total_moves,
                    'average_eval_loss': s.average_eval_loss,
                }

            statistics_json = json.dumps({
                'total_moves': analysis.total_moves,
                'blunders': analysis.blunders,
                'mistakes': analysis.mistakes,
                'inaccuracies': analysis.inaccuracies,
                'average_eval_loss': analysis.average_eval_loss,
                'white_stats': _stats_to_dict(analysis.white_stats),
                'black_stats': _stats_to_dict(analysis.black_stats),
            })

            ai_feedback_json = json.dumps({
                'summary': analysis.ai_summary,
                'strengths': analysis.ai_strengths,
                'weaknesses': analysis.ai_weaknesses,
                'recommendations': analysis.ai_recommendations,
            })

            # Insert or replace
            conn.execute(
                """
                INSERT OR REPLACE INTO game_analyses
                (game_id, pgn, metadata, moves, patterns, statistics, ai_feedback, analyzed_at, analysis_time)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    analysis.game_id,
                    analysis.pgn,
                    metadata_json,
                    moves_json,
                    patterns_json,
                    statistics_json,
                    ai_feedback_json,
                    analysis.analyzed_at.isoformat(),
                    analysis.analysis_time,
                )
            )

        logger.info(f"Saved analysis for game {analysis.game_id}")

    def load_analysis(self, game_id: str) -> Optional[GameAnalysis]:
        """
        Load game analysis from database.

        Args:
            game_id: Game ID to load

        Returns:
            GameAnalysis or None if not found
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM game_analyses WHERE game_id = ?",
                (game_id,)
            )
            row = cursor.fetchone()

            if not row:
                return None

            # Deserialize data
            metadata_data = json.loads(row['metadata'])
            metadata = GameMetadata(**metadata_data)

            moves_data = json.loads(row['moves'])
            # Note: Full deserialization would require recreating PositionEvaluation objects
            # For now, we'll skip full move reconstruction

            patterns_data = json.loads(row['patterns'])
            patterns = [Pattern(**p) for p in patterns_data]

            statistics = json.loads(row['statistics'])
            ai_feedback_raw = json.loads(row['ai_feedback']) if row['ai_feedback'] else {}

            # Reconstruct PlayerStats from stored dicts (fall back gracefully)
            def _dict_to_stats(d: dict) -> PlayerStats:
                return PlayerStats(
                    accuracy=d.get('accuracy', 0.0),
                    brilliant=d.get('brilliant', 0), great=d.get('great', 0),
                    best=d.get('best', 0), excellent=d.get('excellent', 0),
                    good=d.get('good', 0), inaccuracy=d.get('inaccuracy', 0),
                    mistake=d.get('mistake', 0), blunder=d.get('blunder', 0),
                    forced=d.get('forced', 0),
                    total_moves=d.get('total_moves', 0),
                    average_eval_loss=d.get('average_eval_loss', 0.0),
                )

            white_stats = _dict_to_stats(statistics.pop('white_stats', {}))
            black_stats = _dict_to_stats(statistics.pop('black_stats', {}))

            analysis = GameAnalysis(
                game_id=row['game_id'],
                metadata=metadata,
                pgn=row['pgn'],
                patterns=patterns,
                analyzed_at=datetime.fromisoformat(row['analyzed_at']),
                analysis_time=row['analysis_time'],
                white_stats=white_stats,
                black_stats=black_stats,
                ai_summary=ai_feedback_raw.get('summary', ''),
                ai_strengths=ai_feedback_raw.get('strengths', []),
                ai_weaknesses=ai_feedback_raw.get('weaknesses', []),
                ai_recommendations=ai_feedback_raw.get('recommendations', []),
                **statistics,
            )

            return analysis

    def list_analyses(self, limit: int = 100) -> List[str]:
        """
        List recent game analyses.

        Args:
            limit: Maximum number of results

        Returns:
            List of game IDs
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT game_id FROM game_analyses ORDER BY analyzed_at DESC LIMIT ?",
                (limit,)
            )
            return [row[0] for row in cursor.fetchall()]

    def delete_analysis(self, game_id: str) -> bool:
        """
        Delete game analysis.

        Args:
            game_id: Game ID to delete

        Returns:
            True if deleted, False if not found
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "DELETE FROM game_analyses WHERE game_id = ?",
                (game_id,)
            )
            return cursor.rowcount > 0
