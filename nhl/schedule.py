"""Live schedule helpers for defaults, upcoming games, and featured players."""

import pandas as pd
import requests
import streamlit as st
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from nhl.constants import ACTIVE_TEAMS, CURRENT_SEASON_YEAR
from nhl.data_loaders import get_team_season_game_log, load_win_prob_weights
from nhl.win_prob import (
    MIN_GAMES_FOR_ESTIMATE,
    WIN_PROB_FEATURE_LABELS,
    build_matchup_snapshot,
    get_top_feature_driver,
    score_home_win_probability,
)

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
        trimmed_games = upcoming_games[:limit]
        for game in trimmed_games:
            game["pregame_win_prob"] = get_game_win_probabilities(
                game["away_abbr"],
                game["home_abbr"],
            )
        return trimmed_games
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

            stats = _get_cached_club_stats(abbr)
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


@st.cache_data(ttl=300)
def get_game_win_probabilities(away_abbr: str, home_abbr: str) -> dict | None:
    """Return one runtime-only pregame win-probability estimate for a matchup."""
    clean_away_abbr = str(away_abbr or "").strip().upper()
    clean_home_abbr = str(home_abbr or "").strip().upper()
    if not clean_away_abbr or not clean_home_abbr:
        return None

    artifact = load_win_prob_weights()
    if not artifact:
        return None

    try:
        away_games = get_team_season_game_log(clean_away_abbr, CURRENT_SEASON_YEAR)
        home_games = get_team_season_game_log(clean_home_abbr, CURRENT_SEASON_YEAR)
        away_regular = _filter_regular_season_games(away_games)
        home_regular = _filter_regular_season_games(home_games)
        matchup_snapshot = build_matchup_snapshot(
            home_regular,
            away_regular,
            min_games=int(artifact.get("min_games", MIN_GAMES_FOR_ESTIMATE)),
        )
        if matchup_snapshot is None:
            return None

        scored_probability = score_home_win_probability(
            matchup_snapshot["feature_values"],
            artifact,
        )
        base_home_prob = float(scored_probability["home_win_prob"])
        model_label = _build_model_label(
            clean_away_abbr,
            clean_home_abbr,
            scored_probability,
        )

        away_club_stats = _get_cached_club_stats(clean_away_abbr) or {}
        home_club_stats = _get_cached_club_stats(clean_home_abbr) or {}
        goalie_adjustment, goalie_data_available = _compute_goalie_probability_adjustment(
            home_goalies=home_club_stats.get("goalies", []),
            away_goalies=away_club_stats.get("goalies", []),
        )
        final_home_prob = min(max(base_home_prob + goalie_adjustment, 0.0), 1.0)
        home_pct = int(round(final_home_prob * 100.0))
        home_pct = min(max(home_pct, 0), 100)
        away_pct = 100 - home_pct

        return {
            "away_pct": away_pct,
            "home_pct": home_pct,
            "model_label": model_label,
            "goalie_label": _build_goalie_label(
                away_abbr=clean_away_abbr,
                home_abbr=clean_home_abbr,
                adjustment=goalie_adjustment,
                goalie_data_available=goalie_data_available,
            ),
            "base_home_pct": int(round(base_home_prob * 100.0)),
            "base_away_pct": 100 - int(round(base_home_prob * 100.0)),
        }
    except Exception:
        return None


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
        """Return one game's parsed UTC start time for stable descending sorting."""
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
                "game_type": int(game.get("gameType", 0) or 0),
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
    """Pick the franchise starter from a team goalie list.

    Sorting priority: minimum 6 GP (filters tourist call-ups), then wins
    (identifies the workhorse starter), then save percentage as a tiebreaker,
    then playerId for a stable final ordering.

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
            int(goalie.get("gamesPlayed", 0)) > 5,
            int(goalie.get("wins", 0)),
            _coerce_save_percentage(goalie.get("savePercentage", 0.0)),
            int(goalie.get("playerId", 0)),
        ),
    )


def _filter_regular_season_games(team_games: pd.DataFrame | None) -> pd.DataFrame:
    """Return only regular-season rows from a team game-log DataFrame."""
    if team_games is None or team_games.empty:
        return pd.DataFrame()
    d = team_games.copy()
    if "GameType" in d.columns:
        d = d[d["GameType"].astype(str).str.strip().eq("Regular")]
    return d.reset_index(drop=True)


def _build_model_label(away_abbr: str, home_abbr: str, scored_probability: dict) -> str:
    """Build one short runtime label from the strongest model contribution."""
    base_home_prob = float(scored_probability.get("home_win_prob", 0.5))
    if abs(base_home_prob - 0.5) < 0.02:
        return "Base model: near toss-up."

    top_feature, contribution = get_top_feature_driver(scored_probability)
    if not top_feature or abs(contribution) < 0.01:
        return "Base model: modest edge from team form."

    feature_label = WIN_PROB_FEATURE_LABELS.get(top_feature, top_feature.replace("_", " "))
    edge_abbr = home_abbr if contribution >= 0 else away_abbr
    return f"Base model: {edge_abbr} edge from {feature_label}."


def _build_goalie_label(
    away_abbr: str,
    home_abbr: str,
    adjustment: float,
    goalie_data_available: bool,
) -> str:
    """Describe the goalie overlay in a short, honest label."""
    if not goalie_data_available:
        return "Goalie proxy unavailable."
    if abs(float(adjustment)) < 0.005:
        return "Goalie proxy: no material goalie edge."
    edge_abbr = home_abbr if adjustment > 0 else away_abbr
    return f"Goalie proxy: {edge_abbr} +{abs(adjustment) * 100.0:.1f} pts from save% edge."


def _coerce_save_percentage(value: object) -> float:
    """Normalize save percentage values to 0-1 scale."""
    try:
        numeric_value = float(value or 0.0)
    except Exception:
        return 0.0
    if numeric_value > 1.5:
        numeric_value = numeric_value / 100.0
    return max(0.0, min(numeric_value, 1.0))


def _aggregate_team_save_percentage(goalies: list[dict]) -> float | None:
    """Return the aggregate team save percentage from club-stats goalie rows."""
    if not goalies:
        return None

    total_saves = 0.0
    total_shots_against = 0.0
    weighted_total = 0.0
    weighted_games = 0.0
    for goalie in goalies:
        saves = float(goalie.get("saves", 0.0) or 0.0)
        shots_against = float(goalie.get("shotsAgainst", 0.0) or 0.0)
        save_percentage = _coerce_save_percentage(goalie.get("savePercentage", 0.0))
        games_played = float(goalie.get("gamesPlayed", 0.0) or 0.0)
        if shots_against > 0 and saves >= 0:
            total_saves += saves
            total_shots_against += shots_against
        elif save_percentage > 0 and games_played > 0:
            weighted_total += save_percentage * games_played
            weighted_games += games_played

    if total_shots_against > 0:
        return total_saves / total_shots_against
    if weighted_games > 0:
        return weighted_total / weighted_games
    return None


def _build_goalie_proxy_save_percentage(goalies: list[dict]) -> float | None:
    """Shrink the selected goalie toward the team aggregate save percentage."""
    selected_goalie = _select_best_goalie(goalies)
    if selected_goalie is None:
        return None

    selected_save_pct = _coerce_save_percentage(selected_goalie.get("savePercentage", 0.0))
    team_save_pct = _aggregate_team_save_percentage(goalies)
    games_played = max(float(selected_goalie.get("gamesPlayed", 0.0) or 0.0), 0.0)
    shrink_weight = min(games_played / 25.0, 1.0)
    baseline = team_save_pct if team_save_pct is not None else selected_save_pct
    return baseline + (selected_save_pct - baseline) * shrink_weight


def _compute_goalie_probability_adjustment(home_goalies: list[dict], away_goalies: list[dict]) -> tuple[float, bool]:
    """Convert goalie proxy save-percentage edge into a capped probability delta."""
    home_proxy = _build_goalie_proxy_save_percentage(home_goalies)
    away_proxy = _build_goalie_proxy_save_percentage(away_goalies)
    if home_proxy is None or away_proxy is None:
        return 0.0, False
    return max(-0.04, min(0.04, (home_proxy - away_proxy) * 4.0)), True


@st.cache_data(ttl=3600)
def _get_cached_club_stats(abbr: str) -> dict | None:
    """Cached wrapper around the current club-stats endpoint."""
    return _fetch_club_stats(abbr)


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
                "savePercentage": _coerce_save_percentage(raw.get("savePercentage", 0.0)),
                "saves":       float(raw.get("saves", 0.0) or 0.0),
                "shotsAgainst": float(raw.get("shotsAgainst", 0.0) or 0.0),
            })

    return {"skaters": skaters, "goalies": goalies}
