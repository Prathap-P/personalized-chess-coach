#!/usr/bin/env python3
"""Quick test script to verify the chess coach setup."""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

def test_imports():
    """Test that all modules can be imported."""
    print("Testing imports...")

    try:
        from chess_coach import __version__
        print(f"✅ chess_coach version: {__version__}")
    except ImportError as e:
        print(f"❌ Failed to import chess_coach: {e}")
        return False

    try:
        from chess_coach.models import GameAnalysis, MoveAnalysis, Pattern
        print("✅ models imported")
    except ImportError as e:
        print(f"❌ Failed to import models: {e}")
        return False

    try:
        from chess_coach.config import settings
        print(f"✅ config imported (LLM: {settings.default_llm_provider}/{settings.default_llm_model})")
    except ImportError as e:
        print(f"❌ Failed to import config: {e}")
        return False

    try:
        from chess_coach.engine import StockfishEngine
        print("✅ engine imported")
    except ImportError as e:
        print(f"❌ Failed to import engine: {e}")
        return False

    try:
        from chess_coach.llm import LLMClient
        print("✅ LLM client imported")
    except ImportError as e:
        print(f"❌ Failed to import LLM client: {e}")
        return False

    try:
        from chess_coach.analysis import GameAnalyzer, PatternAnalyzer, MoveEvaluator
        print("✅ analysis modules imported")
    except ImportError as e:
        print(f"❌ Failed to import analysis: {e}")
        return False

    try:
        from chess_coach.storage import GameStorage
        print("✅ storage imported")
    except ImportError as e:
        print(f"❌ Failed to import storage: {e}")
        return False

    try:
        from chess_coach.utils import download_game, fetch_user_games
        print("✅ utils imported")
    except ImportError as e:
        print(f"❌ Failed to import utils: {e}")
        return False

    try:
        from chess_coach.cli import app
        print("✅ CLI imported")
    except ImportError as e:
        print(f"❌ Failed to import CLI: {e}")
        return False

    return True


def test_stockfish():
    """Test Stockfish engine."""
    print("\nTesting Stockfish...")

    try:
        from chess_coach.engine import StockfishEngine
        import chess

        # Try to find Stockfish
        try:
            engine = StockfishEngine()
            print(f"✅ Stockfish path: {engine.stockfish_path}")

            # Test basic functionality
            with engine:
                board = chess.Board()
                eval_obj = engine.evaluate_position(board)
                print(f"✅ Starting position eval: {eval_obj.cp_score} cp")

        except FileNotFoundError as e:
            print(f"⚠️  Stockfish not found: {e}")
            print("   Install Stockfish: brew install stockfish (macOS) or see README")
            return False

    except Exception as e:
        print(f"❌ Stockfish test failed: {e}")
        return False

    return True


def test_storage():
    """Test storage."""
    print("\nTesting storage...")

    try:
        from chess_coach.storage import GameStorage
        storage = GameStorage()
        print(f"✅ Storage initialized: {storage.db_path}")

        # List analyses
        analyses = storage.list_analyses()
        print(f"✅ Found {len(analyses)} saved analyses")

    except Exception as e:
        print(f"❌ Storage test failed: {e}")
        return False

    return True


def main():
    """Run all tests."""
    print("=" * 60)
    print("Chess Coach Setup Test")
    print("=" * 60)

    results = []

    results.append(("Imports", test_imports()))
    results.append(("Stockfish", test_stockfish()))
    results.append(("Storage", test_storage()))

    print("\n" + "=" * 60)
    print("Test Results:")
    print("=" * 60)

    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{name:20s} {status}")

    all_passed = all(result for _, result in results)

    print("\n" + "=" * 60)
    if all_passed:
        print("✅ All tests passed!")
        print("\nYou can now use the chess-coach CLI:")
        print("  poetry run chess-coach setup")
        print("  poetry run chess-coach analyze game <pgn-file-or-url>")
    else:
        print("⚠️  Some tests failed. Please check the errors above.")
    print("=" * 60)

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
