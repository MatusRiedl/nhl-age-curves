"""Live schedule helpers for defaults, upcoming games, and featured players."""

import streamlit as st
import requests
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

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
_CENTRAL_EUROPE_TZ  = ZoneInfo("Europe/Prague")
_WEEKDAY_ABBR       = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
_MONTH_ABBR         = (
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

@st.cache_data(ttl=300)
def get_live_or_recent_game() -> tuple[str, str] | None:
    """Return the current or most recent NHL matchup, or `None` on failure."""
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


@st.cache_data(ttl=300)
def get_upcoming_games(limit: int = 4, days_ahead: int = 14) -> list[dict]:
    """Return the next few upcoming games for the Live games tab."""
    if limit <= 0:
        return []

    try:
        now_utc = datetime.now(timezone.utc)
        upcoming_games: list[dict] = []

        for day_offset in range(max(days_ahead, 0) + 1):
            date_str = (now_utc + timedelta(days=day_offset)).strftime("%Y-%m-%d")
            resp = requests.get(_SCORE_DATE_URL.format(date=date_str), timeout=5)
            if resp.status_code != 200:
                continue

            data = resp.json()
            upcoming_games.extend(_extract_upcoming_games(data.get("games", []), now_utc))

            if len(upcoming_games) >= limit:
                break

        upcoming_games.sort(key=lambda game: game["sort_ts"])
        return upcoming_games[:limit]
    except Exception:
        return []


@st.cache_data(ttl=300)
def get_game_details(game_date: str, game_id: int) -> dict:
    """Return normalized score details for one exact NHL game.

    Args:
        game_date: Date string in ``YYYY-MM-DD`` form.
        game_id: Exact NHL game identifier.

    Returns:
        Normalized game detail dict, or ``{}`` if lookup fails.
    """
    clean_date = str(game_date or '').strip()
    if not clean_date or not game_id:
        return {}

    try:
        resp = requests.get(_SCORE_DATE_URL.format(date=clean_date), timeout=5)
        if resp.status_code != 200:
            return {}
        return _extract_game_details_from_payload(resp.json(), int(game_id), clean_date)
    except Exception:
        return {}


@st.cache_data(ttl=3600)
def get_featured_players(home_abbr: str, away_abbr: str) -> dict:
    """Return featured skaters, goalies, and team names for a matchup pair."""
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

            skaters = stats["skaters"]
            goalies = stats["goalies"]

            best = _select_best_skater(skaters)
            if best:
                players[best["playerId"]] = best["name"]

            best_goalie = _select_best_goalie(goalies)
            if best_goalie:
                players[best_goalie["playerId"]] = best_goalie["name"]

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

    # Sort games by start time (most recent first) to ensure we pick the latest game
    # even if multiple games are live or finished on the same day
    def _get_start_time(game: dict) -> datetime:
        start_time_utc = game.get("startTimeUTC")
        if start_time_utc:
            try:
                return datetime.fromisoformat(start_time_utc.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                pass
        return datetime.min.replace(tzinfo=timezone.utc)

    valid.sort(key=_get_start_time, reverse=True)

    # Priority: live first, finished second
    for state_set in (_LIVE_STATES, _FINAL_STATES):
        for game in valid:
            if game.get("gameState") in state_set:
                home = game.get("homeTeam", {}).get("abbrev", "")
                away = game.get("awayTeam", {}).get("abbrev", "")
                if home and away:
                    return (home, away)

    return None


def _extract_game_details_from_payload(payload: dict, game_id: int, fallback_date: str = '') -> dict:
    """Normalize one exact game from an NHL score payload.

    Args:
        payload: Raw score endpoint JSON payload.
        game_id: Exact NHL game identifier to match.
        fallback_date: Date string to keep when the payload omits it.

    Returns:
        Normalized detail dict, or ``{}`` when the game is not found.
    """
    games = payload.get('games', []) if isinstance(payload, dict) else []
    if not games and isinstance(payload, dict):
        for day in payload.get('gamesByDate', []) or []:
            games.extend(day.get('games', []))

    for game in games:
        try:
            current_game_id = int(game.get('id', 0) or 0)
        except Exception:
            continue
        if current_game_id != int(game_id):
            continue

        away_team = game.get('awayTeam', {})
        home_team = game.get('homeTeam', {})
        away_abbr = str(away_team.get('abbrev', '') or '').strip().upper()
        home_abbr = str(home_team.get('abbrev', '') or '').strip().upper()
        away_name = ACTIVE_TEAMS.get(away_abbr) or str(away_team.get('name', {}).get('default', away_abbr)).strip()
        home_name = ACTIVE_TEAMS.get(home_abbr) or str(home_team.get('name', {}).get('default', home_abbr)).strip()
        venue_name = str(game.get('venue', {}).get('default', '') or '').strip()
        start_time_utc = str(game.get('startTimeUTC', '') or '')
        game_state = str(game.get('gameState', '') or '').strip().upper()
        period_type = str(game.get('periodDescriptor', {}).get('periodType', '') or '').strip().upper()

        try:
            away_score = int(away_team.get('score')) if away_team.get('score') is not None else None
        except Exception:
            away_score = None
        try:
            home_score = int(home_team.get('score')) if home_team.get('score') is not None else None
        except Exception:
            home_score = None

        if game_state in _FINAL_STATES:
            if period_type == 'SO':
                status_label = 'Final/SO'
            elif period_type == 'OT':
                status_label = 'Final/OT'
            else:
                status_label = 'Final'
        elif game_state in _LIVE_STATES:
            status_label = 'Live'
        elif game_state == 'FUT':
            status_label = 'Scheduled'
        else:
            status_label = game_state.title() if game_state else ''

        return {
            'game_id': current_game_id,
            'game_date': str(game.get('gameDate', '') or fallback_date),
            'game_type': int(game.get('gameType', 0) or 0),
            'away_abbr': away_abbr,
            'away_name': away_name,
            'away_score': away_score,
            'home_abbr': home_abbr,
            'home_name': home_name,
            'home_score': home_score,
            'matchup': f'{away_name} at {home_name}',
            'venue': venue_name,
            'start_time_utc': start_time_utc,
            'start_label_cest': _format_game_time_cest(start_time_utc),
            'status_label': status_label,
        }

    return {}


def _parse_utc_timestamp(value: str | None) -> datetime | None:
    """Parse an NHL API UTC timestamp string into an aware datetime.

    Args:
        value: Timestamp string such as ``2026-03-07T17:30:00Z``.

    Returns:
        A timezone-aware UTC datetime, or None if parsing fails.
    """
    if not value:
        return None

    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def _format_game_time_cest(start_time_utc: str | None) -> str:
    """Format a UTC puck-drop timestamp in Central European local time.

    Args:
        start_time_utc: UTC timestamp string from the NHL score API.

    Returns:
        A deterministic display string such as ``Sat 07 Mar, 18:30 CET``.
        Returns ``Time TBD`` if the timestamp is missing or invalid.
    """
    start_dt_utc = _parse_utc_timestamp(start_time_utc)
    if start_dt_utc is None:
        return "Time TBD"

    local_dt = start_dt_utc.astimezone(_CENTRAL_EUROPE_TZ)
    weekday = _WEEKDAY_ABBR[local_dt.weekday()]
    month = _MONTH_ABBR[local_dt.month - 1]
    tz_label = local_dt.tzname() or "CET"
    return f"{weekday} {local_dt.day:02d} {month}, {local_dt:%H:%M} {tz_label}"


def _extract_upcoming_games(games: list[dict], now_utc: datetime) -> list[dict]:
    """Filter one score payload down to valid future games.

    Args:
        games: Raw ``games`` list from the NHL score endpoint.
        now_utc: Current time used to discard stale future-state rows.

    Returns:
        A list of normalized game dicts sorted by start time.
    """
    upcoming_games: list[dict] = []

    for game in games:
        if game.get("gameType") not in _VALID_GAME_TYPES:
            continue
        if game.get("gameState") != "FUT":
            continue

        start_dt_utc = _parse_utc_timestamp(game.get("startTimeUTC"))
        if start_dt_utc is None or start_dt_utc < now_utc:
            continue

        away_team = game.get("awayTeam", {})
        home_team = game.get("homeTeam", {})
        away_abbr = str(away_team.get("abbrev", "")).strip().upper()
        home_abbr = str(home_team.get("abbrev", "")).strip().upper()
        if not away_abbr or not home_abbr:
            continue

        away_name = ACTIVE_TEAMS.get(away_abbr) or str(away_team.get("name", {}).get("default", away_abbr)).strip()
        home_name = ACTIVE_TEAMS.get(home_abbr) or str(home_team.get("name", {}).get("default", home_abbr)).strip()
        venue_name = str(game.get("venue", {}).get("default", "")).strip()

        upcoming_games.append(
            {
                "game_id": int(game.get("id", 0) or 0),
                "away_abbr": away_abbr,
                "away_name": away_name,
                "home_abbr": home_abbr,
                "home_name": home_name,
                "matchup": f"{away_name} at {home_name}",
                "venue": venue_name,
                "start_time_utc": game.get("startTimeUTC", ""),
                "start_label_cest": _format_game_time_cest(game.get("startTimeUTC")),
                "sort_ts": start_dt_utc.timestamp(),
            }
        )

    upcoming_games.sort(key=lambda game: game["sort_ts"])
    return upcoming_games


def _select_best_skater(skaters: list[dict]) -> dict | None:
    """Pick the current-season points leader from a team skater list.

    Args:
        skaters: List of normalized skater rows from ``_fetch_club_stats()``.

    Returns:
        The selected skater dict, or None if no valid skaters exist.
    """
    if not skaters:
        return None

    return max(
        skaters,
        key=lambda player: (
            int(player.get("points", 0)),
            int(player.get("playerId", 0)),
        ),
    )


def _select_best_goalie(goalies: list[dict]) -> dict | None:
    """Pick the best-save-percentage goalie with sane fallbacks.

    Args:
        goalies: List of normalized goalie rows from ``_fetch_club_stats()``.

    Returns:
        The selected goalie dict, or None if no valid goalies exist.
    """
    if not goalies:
        return None

    return max(
        goalies,
        key=lambda goalie: (
            float(goalie.get("savePercentage", 0.0)) > 0.0,
            float(goalie.get("savePercentage", 0.0)),
            int(goalie.get("gamesPlayed", 0)),
            int(goalie.get("wins", 0)),
            int(goalie.get("playerId", 0)),
        ),
    )


def _fetch_club_stats(abbr: str) -> dict | None:
    """Fetches current-season stats for all players on a team.

    Args:
        abbr: Three-letter team abbreviation (e.g. 'PIT').

    Returns:
        A dict with 'skaters' and 'goalies' lists, each containing dicts with
        keys 'playerId' (int), 'name' (str), 'points' (int, skaters only),
        'gamesPlayed' (int), 'wins' (int), and 'savePercentage' (float for
        goalies). Returns None on network or parse error.
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
                "wins":        int(raw.get("wins", 0)),
                "savePercentage": float(raw.get("savePercentage", 0.0) or 0.0),
            })

    return {"skaters": skaters, "goalies": goalies}
