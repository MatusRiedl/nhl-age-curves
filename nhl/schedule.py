"""
nhl.schedule — Live game detection and featured player selection.

Fetches the current or most recently completed NHL game and identifies the
highest-scoring skater and starting goalie for each team, enabling the app to
pre-populate the chart on first open without requiring manual player selection.

All functions are wrapped in try/except with graceful empty-dict fallbacks so
that any network failure leaves the app in its normal empty state.
"""

import streamlit as st
import requests
from datetime import datetime, timedelta

from nhl.constants import ACTIVE_TEAMS

# ---------------------------------------------------------------------------
# Internal constants
# ---------------------------------------------------------------------------

_SCOREBOARD_URL  = "https://api-web.nhle.com/v1/scoreboard/now"
_SCORE_DATE_URL  = "https://api-web.nhle.com/v1/score/{date}"
_CLUB_STATS_URL  = "https://api-web.nhle.com/v1/club-stats/{}/now"

_LIVE_STATES        = {"LIVE", "CRIT"}
_FINAL_STATES       = {"FINAL", "OVER", "OFF"}
_VALID_GAME_TYPES   = {2, 3}   # 2 = regular season, 3 = playoffs


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

@st.cache_data(ttl=300)
def get_live_or_recent_game() -> tuple[str, str] | None:
    """Returns (home_abbr, away_abbr) for the current or most recent NHL game.

    Tries the scoreboard endpoint first (returns ~11 days in one reliable call,
    searched newest-to-oldest). Falls back to single-day score endpoints if the
    scoreboard returns no qualifying game.

    Args:
        None

    Returns:
        A (home_abbr, away_abbr) string tuple, or None if no game is found or
        the NHL score API is unreachable.
    """
    try:
        # Scoreboard is more reliable and covers ~11 days in one request.
        # reverse_dates=True so we find the most recent FINAL game first.
        result = _find_game_from_url(_SCOREBOARD_URL, reverse_dates=True)
        if result:
            return result

        for days_back in range(0, 8):
            date_str = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")
            result = _find_game_from_url(_SCORE_DATE_URL.format(date=date_str))
            if result:
                return result

        return None
    except Exception:
        return None


@st.cache_data(ttl=3600)
def get_featured_players(home_abbr: str, away_abbr: str) -> dict:
    """Returns best skater, starting goalie, and team metadata for two teams.

    For each team fetches the current-season club stats and identifies:
    - The skater with the most points this season.
    - The goalie with the most games played this season (the starter).

    Args:
        home_abbr: Three-letter abbreviation of the home team (e.g. 'PIT').
        away_abbr: Three-letter abbreviation of the away team (e.g. 'VGK').

    Returns:
        A dict with two keys:
            'players': {player_id (int): player_name (str), ...}
            'teams':   {team_abbr (str): full_name (str), ...}
        Both inner dicts may be empty if the API is unreachable.
    """
    try:
        players: dict[int, str] = {}
        teams:   dict[str, str] = {}

        for abbr in (home_abbr, away_abbr):
            if abbr not in ACTIVE_TEAMS:
                continue

            stats = _fetch_club_stats(abbr)
            if not stats:
                continue

            teams[abbr] = ACTIVE_TEAMS[abbr]

            skaters = stats["skaters"]  # [{playerId, name, points}, ...]
            goalies  = stats["goalies"]  # [{playerId, name, gamesPlayed}, ...]

            # Best skater: highest current-season point total
            if skaters:
                best = max(skaters, key=lambda p: p["points"])
                players[best["playerId"]] = best["name"]

            # Starter goalie: most games played this season
            if goalies:
                starter = max(goalies, key=lambda g: g["gamesPlayed"])
                players[starter["playerId"]] = starter["name"]

        return {"players": players, "teams": teams}

    except Exception:
        return {"players": {}, "teams": {}}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _find_game_from_url(url: str, reverse_dates: bool = False) -> tuple[str, str] | None:
    """Fetches a NHL score endpoint and returns (home_abbr, away_abbr) of a
    live or recently finished regular/playoff game, or None if none found.

    Args:
        url: Full NHL score API URL to fetch.
        reverse_dates: If True, reverses the gamesByDate list before scanning so
            the most recent date is searched first (used for multi-day endpoints).

    Returns:
        A (home_abbr, away_abbr) string tuple, or None.
    """
    resp = requests.get(url, timeout=5)
    if resp.status_code != 200:
        return None

    data = resp.json()
    games_by_date = data.get("gamesByDate", [])
    if not games_by_date:
        return None

    if reverse_dates:
        games_by_date = list(reversed(games_by_date))

    all_games: list[dict] = []
    for day in games_by_date:
        all_games.extend(day.get("games", []))

    valid = [g for g in all_games if g.get("gameType") in _VALID_GAME_TYPES]

    # Priority: live first, finished second
    for state_set in (_LIVE_STATES, _FINAL_STATES):
        for game in valid:
            if game.get("gameState") in state_set:
                home = game.get("homeTeam", {}).get("abbrev", "")
                away = game.get("awayTeam", {}).get("abbrev", "")
                if home and away:
                    return (home, away)

    return None


def _fetch_club_stats(abbr: str) -> dict | None:
    """Fetches current-season stats for all players on a team.

    Args:
        abbr: Three-letter team abbreviation (e.g. 'PIT').

    Returns:
        A dict with 'skaters' and 'goalies' lists, each containing dicts with
        keys 'playerId' (int), 'name' (str), 'points' (int, skaters only), and
        'gamesPlayed' (int). Returns None on network or parse error.
    """
    try:
        resp = requests.get(_CLUB_STATS_URL.format(abbr), timeout=5)
        if resp.status_code != 200:
            return None
        data = resp.json()
    except Exception:
        return None

    skaters: list[dict] = []
    goalies:  list[dict] = []

    for raw in data.get("skaters", []):
        pid  = int(raw.get("playerId", 0))
        name = (
            f"{raw.get('firstName', {}).get('default', '')}"
            f" {raw.get('lastName', {}).get('default', '')}"
        ).strip()
        if pid and name:
            skaters.append({
                "playerId": pid,
                "name":     name,
                "points":   int(raw.get("points", 0)),
            })

    for raw in data.get("goalies", []):
        pid  = int(raw.get("playerId", 0))
        name = (
            f"{raw.get('firstName', {}).get('default', '')}"
            f" {raw.get('lastName', {}).get('default', '')}"
        ).strip()
        if pid and name:
            goalies.append({
                "playerId":    pid,
                "name":        name,
                "gamesPlayed": int(raw.get("gamesPlayed", 0)),
            })

    return {"skaters": skaters, "goalies": goalies}
