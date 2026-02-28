"""Utility functions for Chess Coach."""

import logging
import re
from typing import Optional, List
from urllib.parse import urlparse

import requests

logger = logging.getLogger(__name__)


def download_game(url: str) -> str:
    """
    Download a chess game PGN from a URL.

    Supports:
    - Lichess: https://lichess.org/{game_id}
    - Chess.com: https://www.chess.com/game/live/{game_id}

    Args:
        url: URL to the game

    Returns:
        PGN string

    Raises:
        ValueError: If URL is not supported
        requests.RequestException: If download fails
    """
    parsed = urlparse(url)

    # Lichess
    if 'lichess.org' in parsed.netloc:
        game_id = parsed.path.strip('/').split('/')[-1]
        pgn_url = f"https://lichess.org/game/export/{game_id}"

        response = requests.get(pgn_url, headers={'Accept': 'application/x-chess-pgn'})
        response.raise_for_status()

        return response.text

    # Chess.com
    elif 'chess.com' in parsed.netloc:
        # Extract game ID from URL
        match = re.search(r'/live/game/(\d+)', url)
        if not match:
            match = re.search(r'/game/live/(\d+)', url)

        if not match:
            raise ValueError("Could not extract game ID from Chess.com URL")

        game_id = match.group(1)

        # Chess.com API endpoint
        api_url = f"https://api.chess.com/pub/game/{game_id}"

        response = requests.get(api_url)
        response.raise_for_status()

        data = response.json()
        pgn = data.get('pgn')

        if not pgn:
            raise ValueError("No PGN found in Chess.com response")

        return pgn

    else:
        raise ValueError(f"Unsupported URL: {url}")


def fetch_user_games(
    username: str,
    platform: str = 'lichess',
    limit: int = 10,
    time_class: Optional[str] = None,
) -> List[str]:
    """
    Fetch recent games for a user.

    Args:
        username: Username on the platform
        platform: 'lichess' or 'chess.com'
        limit: Maximum number of games to fetch
        time_class: Filter by time class (e.g., 'rapid', 'blitz')

    Returns:
        List of PGN strings

    Raises:
        ValueError: If platform is not supported
        requests.RequestException: If API request fails
    """
    pgns = []

    if platform == 'lichess':
        pgns = _fetch_lichess_games(username, limit, time_class)
    elif platform in ['chess.com', 'chesscom']:
        pgns = _fetch_chesscom_games(username, limit, time_class)
    else:
        raise ValueError(f"Unsupported platform: {platform}")

    return pgns


def _fetch_lichess_games(
    username: str,
    limit: int,
    time_class: Optional[str] = None,
) -> List[str]:
    """Fetch games from Lichess API."""
    url = f"https://lichess.org/api/games/user/{username}"

    params = {
        'max': limit,
        'pgnInJson': 'false',
        'clocks': 'false',
        'evals': 'false',
        'opening': 'true',
    }

    if time_class:
        params['perfType'] = time_class

    headers = {'Accept': 'application/x-ndjson'}

    try:
        response = requests.get(url, params=params, headers=headers, stream=True)
        response.raise_for_status()

        pgns = []
        current_pgn = []

        for line in response.iter_lines(decode_unicode=True):
            if not line:
                # Empty line separates games
                if current_pgn:
                    pgns.append('\n'.join(current_pgn))
                    current_pgn = []
            else:
                current_pgn.append(line)

        # Add last game
        if current_pgn:
            pgns.append('\n'.join(current_pgn))

        return pgns[:limit]

    except requests.RequestException as e:
        logger.error(f"Failed to fetch Lichess games: {e}")
        raise


def _fetch_chesscom_games(
    username: str,
    limit: int,
    time_class: Optional[str] = None,
) -> List[str]:
    """Fetch games from Chess.com API."""
    # First, get archives list
    archives_url = f"https://api.chess.com/pub/player/{username}/games/archives"

    try:
        response = requests.get(archives_url)
        response.raise_for_status()

        archives = response.json().get('archives', [])

        if not archives:
            logger.warning(f"No archives found for user {username}")
            return []

        # Fetch games from most recent archive
        pgns = []

        for archive_url in reversed(archives):
            if len(pgns) >= limit:
                break

            response = requests.get(archive_url)
            response.raise_for_status()

            games = response.json().get('games', [])

            for game in games:
                if len(pgns) >= limit:
                    break

                # Filter by time class if specified
                if time_class:
                    game_time_class = game.get('time_class', '')
                    if game_time_class != time_class:
                        continue

                pgn = game.get('pgn')
                if pgn:
                    pgns.append(pgn)

        return pgns[:limit]

    except requests.RequestException as e:
        logger.error(f"Failed to fetch Chess.com games: {e}")
        raise


def format_move_comment(
    move_san: str,
    classification: str,
    eval_loss: float,
    best_move: Optional[str] = None,
) -> str:
    """
    Format a move comment for PGN.

    Args:
        move_san: Move in SAN notation
        classification: Move classification
        eval_loss: Evaluation loss in centipawns
        best_move: Best move according to engine

    Returns:
        Formatted comment string
    """
    parts = [f"{classification}"]

    if eval_loss > 0:
        parts.append(f"-{eval_loss:.0f}cp")

    if best_move and best_move != move_san:
        parts.append(f"Better: {best_move}")

    return " | ".join(parts)


def parse_time_control(time_control: str) -> Optional[str]:
    """
    Parse time control string to time class.

    Args:
        time_control: Time control string (e.g., "600+0", "180+2")

    Returns:
        Time class ('bullet', 'blitz', 'rapid', 'classical') or None
    """
    if not time_control or time_control == '-':
        return None

    # Parse base time in seconds
    parts = time_control.split('+')
    if not parts:
        return None

    try:
        base_time = int(parts[0])
        increment = int(parts[1]) if len(parts) > 1 else 0

        # Approximate game length
        estimated_time = base_time + 40 * increment

        if estimated_time < 180:
            return 'bullet'
        elif estimated_time < 600:
            return 'blitz'
        elif estimated_time < 1500:
            return 'rapid'
        else:
            return 'classical'

    except (ValueError, IndexError):
        return None
