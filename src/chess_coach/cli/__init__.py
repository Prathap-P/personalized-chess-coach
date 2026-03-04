"""CLI interface for Chess Coach."""

import logging
from pathlib import Path
from typing import Dict, Optional
from enum import Enum

import typer
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
import chess

from ..config import settings, _find_env_file
from ..engine import StockfishEngine
from ..llm import LLMClient
from ..analysis.game_analyzer import GameAnalyzer
from ..analysis.pattern_analyzer import PatternAnalyzer
from ..storage import GameStorage
from ..utils import download_game, fetch_user_games

logger = logging.getLogger(__name__)

app = typer.Typer(help="Personalized Chess Coach - AI-powered game analysis")
analyze_app = typer.Typer(help="Analyze chess games")
config_app = typer.Typer(help="Manage configuration")

app.add_typer(analyze_app, name="analyze")
app.add_typer(config_app, name="config")

console = Console()


def get_project_root() -> Path:
    """Find project root by looking for pyproject.toml."""
    current = Path(__file__).resolve()
    for parent in [current, *current.parents]:
        if (parent / "pyproject.toml").exists():
            return parent
    # Fallback to current working directory
    return Path.cwd()


# Set project root once at module load
PROJECT_ROOT = get_project_root()


class Platform(str, Enum):
    """Supported chess platforms."""
    LICHESS = "lichess"
    CHESSCOM = "chess.com"


class ColorFilter(str, Enum):
    """Color filter for analysis."""
    WHITE = "white"
    BLACK = "black"
    BOTH = "both"


def configure_logging(verbose: bool = False):
    """Configure logging."""
    log_level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )


@app.callback()
def main_callback(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose logging")
):
    """Personalized Chess Coach - AI-powered game analysis."""
    configure_logging(verbose)


@app.command()
def setup():
    """Setup Chess Coach (download Stockfish, verify LLM connection)."""
    console.print("🔧 Setting up Chess Coach...", style="bold blue")

    # Test Stockfish
    try:
        with StockfishEngine() as engine:
            console.print(f"✅ Stockfish found at: {engine.stockfish_path}", style="green")
    except Exception as e:
        console.print(f"❌ Stockfish setup failed: {e}", style="red")
        raise typer.Exit(1)

    # Test LLM
    try:
        llm = LLMClient()
        console.print(f"✅ LLM configured: {llm.provider}/{llm.model}", style="green")
    except Exception as e:
        console.print(f"⚠️  LLM not configured: {e}", style="yellow")
        console.print("   You can still use the tool, but AI feedback will be limited.")

    console.print("\n✅ Setup complete!", style="bold green")


@analyze_app.command(name='game')
def analyze_game(
    source: str = typer.Argument(..., help="URL to game or path to PGN file"),
    player: Optional[str] = typer.Option(None, "--player", "-p", help="Player name to analyze"),
    skill_level: Optional[int] = typer.Option(None, "--skill-level", "-s", help="Player skill level (ELO)"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Output file for analysis"),
    no_llm: bool = typer.Option(True, "--no-llm", help="Skip LLM analysis")
):
    """Analyze a single chess game.

    SOURCE can be:
    - URL to a chess.com or Lichess game
    - Path to a PGN file
    """
    console.print(f"🔍 Analyzing game: [cyan]{source}[/cyan]")

    # Get PGN
    if source.startswith('http'):
        console.print("📥 Downloading game...")
        try:
            pgn = download_game(source)
        except Exception as e:
            console.print(f"❌ Failed to download game: {e}", style="red")
            raise typer.Exit(1)
    else:
        # All relative paths are from project root
        pgn_path = Path(source).expanduser()
        if not pgn_path.is_absolute():
            pgn_path = PROJECT_ROOT / pgn_path
        
        if not pgn_path.exists():
            console.print(f"❌ File not found: {pgn_path}", style="red")
            raise typer.Exit(1)
        pgn = pgn_path.read_text()

    # Analyze with Stockfish
    console.print("🔎 Analyzing with Stockfish...")
    try:
        with StockfishEngine() as engine:
            analyzer = GameAnalyzer(engine)
            analysis = analyzer.analyze_game(pgn, target_player=player)
    except Exception as e:
        console.print(f"❌ Analysis failed: {e}", style="red")
        raise typer.Exit(1)

    # ── Analysis Results ──────────────────────────────────────
    from rich.table import Table

    ws = analysis.white_stats
    bs = analysis.black_stats
    wname = analysis.metadata.white_player
    bname = analysis.metadata.black_player

    # Accuracy banner
    console.print()
    console.print(f"  [bold white]{wname}[/bold white]  vs  [bold white]{bname}[/bold white]")
    console.print(
        f"  Accuracy  "
        f"[bold green]{ws.accuracy}%[/bold green]"
        f"  ·  "
        f"[bold green]{bs.accuracy}%[/bold green]"
    )
    console.print()

    # Move classification table
    table = Table(title="Move Classification Breakdown", show_header=True, header_style="bold cyan")
    table.add_column("Classification", style="bold")
    table.add_column(wname, justify="center")
    table.add_column(bname, justify="center")

    rows = [
        ("✨ Brilliant",  "bright_magenta", ws.brilliant,   bs.brilliant),
        ("🎯 Great",      "cyan",           ws.great,       bs.great),
        ("⭐ Best",       "green",          ws.best,        bs.best),
        ("👍 Excellent",  "bright_green",   ws.excellent,   bs.excellent),
        ("✅ Good",       "white",          ws.good,        bs.good),
        ("⚠️  Inaccuracy","yellow",         ws.inaccuracy,  bs.inaccuracy),
        ("❌ Mistake",    "bright_red",     ws.mistake,     bs.mistake),
        ("💥 Blunder",    "red",            ws.blunder,     bs.blunder),
    ]

    for label, color, wval, bval in rows:
        w_str = f"[{color}]{wval}[/{color}]" if wval > 0 else "[dim]0[/dim]"
        b_str = f"[{color}]{bval}[/{color}]" if bval > 0 else "[dim]0[/dim]"
        table.add_row(label, w_str, b_str)

    table.add_section()
    table.add_row(
        "Total Moves",
        str(ws.total_moves),
        str(bs.total_moves),
    )
    table.add_row(
        "Avg Eval Loss",
        f"{ws.average_eval_loss:.1f} cp",
        f"{bs.average_eval_loss:.1f} cp",
    )

    console.print(table)
    console.print()

    # Get LLM feedback
    if not no_llm:
        try:
            console.print("\n🤖 Generating AI feedback...")
            llm = LLMClient()

            # Prepare data for LLM
            errors = [
                {
                    'move_number': m.move_number,
                    'move': m.move_san,
                    'classification': m.classification.value,
                    'eval_loss': m.eval_loss,
                }
                for m in analysis.get_errors()[:5]
            ]

            patterns = [
                {
                    'description': p.description,
                    'occurrences': p.occurrences,
                    'severity': p.severity,
                }
                for p in analysis.patterns
            ]

            game_summary = (
                f"{analysis.metadata.white_player} vs {analysis.metadata.black_player}\n"
                f"Result: {analysis.metadata.result}\n"
                f"Opening: {analysis.metadata.opening}"
            )

            # Build per-player stats for the LLM prompt
            player_stats = {
                "white": {
                    "accuracy": ws.accuracy,
                    "best": ws.best,
                    "excellent": ws.excellent,
                    "good": ws.good,
                    "inaccuracy": ws.inaccuracy,
                    "mistake": ws.mistake,
                    "blunder": ws.blunder,
                },
                "black": {
                    "accuracy": bs.accuracy,
                    "best": bs.best,
                    "excellent": bs.excellent,
                    "good": bs.good,
                    "inaccuracy": bs.inaccuracy,
                    "mistake": bs.mistake,
                    "blunder": bs.blunder,
                },
            }

            ai_feedback = llm.generate_game_analysis(
                game_summary,
                errors,
                patterns,
                skill_level or analysis.metadata.white_elo,
                player_stats=player_stats,
            )

            # Store feedback in analysis
            analysis.ai_summary = ai_feedback.get('summary', '')
            analysis.ai_strengths = ai_feedback.get('strengths', [])
            analysis.ai_weaknesses = ai_feedback.get('weaknesses', [])
            analysis.ai_recommendations = ai_feedback.get('recommendations', [])

            # Display AI feedback
            console.print("\n🎯 [bold]AI Feedback:[/bold]")
            if analysis.ai_summary:
                console.print(f"\n{analysis.ai_summary}")

            if analysis.ai_strengths:
                console.print("\n💪 [bold green]Strengths:[/bold green]")
                for s in analysis.ai_strengths:
                    console.print(f"  • {s}")

            if analysis.ai_weaknesses:
                console.print("\n📉 [bold yellow]Weaknesses:[/bold yellow]")
                for w in analysis.ai_weaknesses:
                    console.print(f"  • {w}")

            if analysis.ai_recommendations:
                console.print("\n💡 [bold blue]Recommendations:[/bold blue]")
                for r in analysis.ai_recommendations:
                    console.print(f"  • {r}")

        except Exception as e:
            console.print(f"\n⚠️  AI feedback failed: {e}", style="yellow")
            logger.exception("LLM analysis failed")

    # Save analysis
    storage = GameStorage()
    storage.save_analysis(analysis)
    console.print(f"\n💾 Analysis saved (ID: [cyan]{analysis.game_id}[/cyan])")

    # Export to file if requested
    if output:
        output_path = Path(output).expanduser()
        if not output_path.is_absolute():
            output_path = PROJECT_ROOT / output_path
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(analysis.pgn)
        console.print(f"📄 Exported to: {output_path}")


@analyze_app.command(name='profile')
def analyze_profile(
    username: str = typer.Argument(..., help="Username on the platform"),
    platform: Platform = typer.Option(Platform.LICHESS, "--platform", "-p", help="Chess platform"),
    games: int = typer.Option(10, "--games", "-n", help="Number of recent games to analyze"),
    color: ColorFilter = typer.Option(ColorFilter.BOTH, "--color", "-c", help="Filter by color"),
    no_llm: bool = typer.Option(False, "--no-llm", help="Skip LLM analysis")
):
    """Analyze a player's recent games for patterns.

    USERNAME is the player's username on the platform.
    """
    console.print(f"🔍 Analyzing {games} games for [cyan]{username}[/cyan] on {platform.value}...")

    # Fetch games
    console.print("📥 Fetching games...")
    try:
        pgns = fetch_user_games(username, platform.value, limit=games)
    except Exception as e:
        console.print(f"❌ Failed to fetch games: {e}", style="red")
        raise typer.Exit(1)

    if not pgns:
        console.print("❌ No games found", style="red")
        raise typer.Exit(1)

    console.print(f"✅ Found {len(pgns)} games", style="green")

    # Analyze each game
    console.print("\n🔎 Analyzing games with Stockfish...")
    analyses = []

    with StockfishEngine() as engine:
        analyzer = GameAnalyzer(engine)

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            task = progress.add_task(f"Analyzing {len(pgns)} games...", total=len(pgns))

            for pgn in pgns:
                try:
                    analysis = analyzer.analyze_game(pgn, target_player=username)
                    analyses.append(analysis)
                except Exception as e:
                    logger.error(f"Failed to analyze game: {e}")
                finally:
                    progress.advance(task)

    if not analyses:
        console.print("❌ No games could be analyzed", style="red")
        raise typer.Exit(1)

    # Determine player color filter
    player_color = None
    if color == ColorFilter.WHITE:
        player_color = chess.WHITE
    elif color == ColorFilter.BLACK:
        player_color = chess.BLACK

    # Pattern analysis
    console.print("\n📊 Analyzing patterns...")
    pattern_analyzer = PatternAnalyzer()
    pattern_results = pattern_analyzer.analyze_games(analyses, player_color)

    # Aggregate accuracy across all games for the target player
    target_accuracies = []
    agg_counts: Dict[str, int] = {
        'brilliant': 0, 'great': 0, 'best': 0, 'excellent': 0,
        'good': 0, 'inaccuracy': 0, 'mistake': 0, 'blunder': 0,
    }
    for a in analyses:
        if username.lower() in a.metadata.white_player.lower():
            s = a.white_stats
        elif username.lower() in a.metadata.black_player.lower():
            s = a.black_stats
        else:
            continue
        target_accuracies.append(s.accuracy)
        for key in agg_counts:
            agg_counts[key] += getattr(s, key)

    # Display results
    console.print("\n📈 [bold]Pattern Analysis Results:[/bold]")
    console.print(f"   Games analyzed: {pattern_results['num_games']}")

    if target_accuracies:
        from rich.table import Table as RichTable
        avg_acc = sum(target_accuracies) / len(target_accuracies)
        console.print()
        console.print(f"  [bold cyan]{username}[/bold cyan]  —  Avg Accuracy: [bold green]{avg_acc:.1f}%[/bold green]")

        acc_table = RichTable(title=f"{username} — Move Quality ({len(target_accuracies)} games)", show_header=True, header_style="bold cyan")
        acc_table.add_column("Classification", style="bold")
        acc_table.add_column("Total", justify="center")

        acc_rows = [
            ("✨ Brilliant",  "bright_magenta", 'brilliant'),
            ("🎯 Great",      "cyan",           'great'),
            ("⭐ Best",       "green",          'best'),
            ("👍 Excellent",  "bright_green",   'excellent'),
            ("✅ Good",       "white",          'good'),
            ("⚠️  Inaccuracy","yellow",         'inaccuracy'),
            ("❌ Mistake",    "bright_red",     'mistake'),
            ("💥 Blunder",    "red",            'blunder'),
        ]
        for label, color, key in acc_rows:
            val = agg_counts[key]
            val_str = f"[{color}]{val}[/{color}]" if val > 0 else "[dim]0[/dim]"
            acc_table.add_row(label, val_str)
        console.print(acc_table)
        console.print()

    if pattern_results['patterns']:
        console.print("\n🔍 [bold]Identified Patterns:[/bold]")
        for pattern in pattern_results['patterns']:
            severity_emoji = {'high': '🔴', 'medium': '🟡', 'low': '🟢'}.get(pattern.severity, '⚪')
            console.print(f"   {severity_emoji} {pattern.description}")
            console.print(f"      Occurrences: {pattern.occurrences}")

    # Opening analysis
    if pattern_results['opening_analysis']:
        console.print("\n♟️  [bold]Opening Analysis:[/bold]")
        for opening, stats in list(pattern_results['opening_analysis'].items())[:5]:
            console.print(f"   [cyan]{opening}[/cyan]:")
            console.print(f"      Games: {stats['games']}")
            console.print(f"      Avg errors: {stats['avg_errors']:.1f}")

    # Phase analysis
    if pattern_results['phase_analysis']:
        console.print("\n⏱️  [bold]Phase Performance:[/bold]")
        for phase, stats in pattern_results['phase_analysis'].items():
            if stats['moves'] > 0:
                console.print(f"   [cyan]{phase.capitalize()}[/cyan]:")
                console.print(f"      Error rate: {stats.get('error_rate', 0):.1%}")
                console.print(f"      Avg loss: {stats['avg_loss']:.1f} cp")

    # Save analyses
    storage = GameStorage()
    for analysis in analyses:
        storage.save_analysis(analysis)

    console.print(f"\n💾 Saved {len(analyses)} analyses", style="green")


@config_app.command(name='show')
def config_show():
    """Show current configuration."""
    console.print("⚙️  [bold]Current Configuration:[/bold]")
    console.print("\n[bold]LLM:[/bold]")
    console.print(f"  Provider: [cyan]{settings.default_llm_provider}[/cyan]")
    console.print(f"  Model: [cyan]{settings.default_llm_model}[/cyan]")
    console.print("\n[bold]Stockfish:[/bold]")
    console.print(f"  Path: [cyan]{settings.stockfish_path}[/cyan]")
    console.print(f"  Depth: {settings.stockfish_depth}")
    console.print(f"  Time limit: {settings.stockfish_time_limit}s")
    console.print("\n[bold]Data:[/bold]")
    console.print(f"  Data dir: [cyan]{settings.data_dir}[/cyan]")
    console.print(f"  Cache dir: [cyan]{settings.cache_dir}[/cyan]")
    console.print(f"  Logs dir: [cyan]{settings.logs_dir}[/cyan]")
    console.print("\n[bold]API:[/bold]")
    console.print(f"  Username: [cyan]{settings.api_username}[/cyan]")
    console.print(f"  Auth configured: {'[green]yes[/green]' if settings.api_password_hash else '[yellow]no — run chess-coach api-setup[/yellow]'}")


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host", help="Host to bind to"),
    port: int = typer.Option(8000, "--port", help="Port to listen on"),
    reload: bool = typer.Option(False, "--reload", help="Enable auto-reload (dev mode)"),
    daemon: bool = typer.Option(False, "--daemon", "-d", help="Run as background daemon"),
):
    """Start the Chess Coach API server."""
    if not settings.api_password_hash or not settings.api_secret_key:
        console.print(
            "⚠️  API auth not configured. Run [cyan]chess-coach api-setup[/cyan] first.",
            style="yellow",
        )
        raise typer.Exit(1)

    if daemon:
        import subprocess
        import sys

        pid_file = PROJECT_ROOT / "data" / "server.pid"
        pid_file.parent.mkdir(parents=True, exist_ok=True)

        proc = subprocess.Popen(
            [
                sys.executable, "-m", "uvicorn",
                "chess_coach.api:app",
                "--host", host,
                "--port", str(port),
                "--ws-ping-interval", "20",
                "--ws-ping-timeout", "60",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        pid_file.write_text(str(proc.pid))
        console.print(f"✅ Chess Coach API daemon started (PID: [cyan]{proc.pid}[/cyan])")
        console.print(f"   API:  http://{host}:{port}")
        console.print(f"   Docs: http://{host}:{port}/docs")
        console.print(f"   Stop: [cyan]chess-coach stop[/cyan]")
    else:
        import uvicorn
        from ..api import app as fastapi_app

        console.print(f"🚀 Chess Coach API running at [cyan]http://{host}:{port}[/cyan]")
        console.print(f"   Docs: [cyan]http://{host}:{port}/docs[/cyan]")
        console.print("   Press Ctrl+C to stop.")
        uvicorn.run(
            fastapi_app,
            host=host,
            port=port,
            reload=reload,
            ws_ping_interval=20,   # protocol-level WS ping every 20 s
            ws_ping_timeout=60,    # close if no pong within 60 s
        )


@app.command(name="stop")
def stop_server():
    """Stop the Chess Coach API daemon."""
    pid_file = PROJECT_ROOT / "data" / "server.pid"
    if not pid_file.exists():
        console.print("⚠️  No server PID file found. Is the daemon running?", style="yellow")
        raise typer.Exit(1)

    import os
    import signal

    pid = int(pid_file.read_text().strip())
    try:
        os.kill(pid, signal.SIGTERM)
        pid_file.unlink(missing_ok=True)
        console.print(f"✅ Server stopped (PID: [cyan]{pid}[/cyan])", style="green")
    except ProcessLookupError:
        pid_file.unlink(missing_ok=True)
        console.print(f"⚠️  Process {pid} not found (already stopped?)", style="yellow")
    except PermissionError:
        console.print(f"❌ Permission denied to stop process {pid}", style="red")
        raise typer.Exit(1)


@app.command(name="api-setup")
def api_setup(
    username: str = typer.Option("admin", "--username", "-u", help="API username"),
    password: Optional[str] = typer.Option(
        None, "--password", "-p", help="Password (auto-generated if not provided)"
    ),
):
    """Set up API authentication credentials and write them to .env."""
    import re
    import secrets as _secrets

    import bcrypt as _bcrypt

    if not password:
        password = _secrets.token_urlsafe(16)
        console.print(f"\n🔑 Generated password: [bold yellow]{password}[/bold yellow]")
        console.print("   [dim]Save this — it won't be shown again.[/dim]")

    pw_bytes = password.encode("utf-8")[:72]
    hashed = _bcrypt.hashpw(pw_bytes, _bcrypt.gensalt()).decode("utf-8")
    secret_key = _secrets.token_hex(32)

    env_path = Path(_find_env_file())
    content = env_path.read_text(encoding="utf-8") if env_path.exists() else ""
    lines = content.splitlines()

    updates = {
        "API_USERNAME": username,
        "API_PASSWORD_HASH": hashed,
        "API_SECRET_KEY": secret_key,
    }

    for env_key, value in updates.items():
        new_line = f"{env_key}={value}"
        replaced = False
        for i, line in enumerate(lines):
            if re.match(rf"^{env_key}\s*=", line):
                lines[i] = new_line
                replaced = True
                break
        if not replaced:
            lines.append(new_line)

    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    console.print(f"\n✅ API credentials saved to [cyan]{env_path}[/cyan]")
    console.print(f"   Username:   [cyan]{username}[/cyan]")
    console.print(f"   Secret key: [dim]generated[/dim]")
    console.print("\n[bold]Next steps:[/bold]")
    console.print("  1. Start the server: [cyan]chess-coach serve[/cyan]")
    console.print("  2. Get a token:      [cyan]POST /auth/token[/cyan]")
    console.print("  3. View API docs:    [cyan]http://localhost:8000/docs[/cyan]")


def main():
    """Entry point for CLI."""
    app()


if __name__ == '__main__':
    main()
