"""
nhl.data_loaders — Cached data-fetch functions for the NHL Age Curves app.

All external API calls and the parquet load live here.  Every function is decorated
with @st.cache_data (permanent or ttl=3600) so the app never hammers the APIs on
each Streamlit rerun.

Try/except fallbacks are intentional — the NHL APIs are undocumented and occasionally
return unexpected payloads.  Never remove the fallback returns.

Imports from project:
    nhl.constants  — URL strings and NHLE_MULTIPLIERS / TEAM_METRICS
"""

import os

import pandas as pd
import requests
import streamlit as st

from nhl.constants import (
    NHLE_MULTIPLIERS,
    SEARCH_URL,
    STATS_URL,
    ROSTER_URL,
    TEAM_LIST_URL,
    TEAM_STATS_URL,
    TEAM_METRICS,
)


# ---------------------------------------------------------------------------
# Parquet / historical data
# ---------------------------------------------------------------------------

@st.cache_data
def load_historical_data() -> pd.DataFrame:
    """Load the local NHL historical seasons parquet file.

    Adds PPG (Points/GP) and Save% (alias of SavePct) columns so downstream
    functions don't have to recompute them.

    Returns:
        DataFrame with one row per player-season, or an empty DataFrame if
        the parquet file is missing or unreadable.
    """
    try:
        if os.path.exists("nhl_historical_seasons.parquet"):
            df = pd.read_parquet("nhl_historical_seasons.parquet")
            df['PPG'] = df['Points'] / df['GP']
            df['Save %'] = df['SavePct']
            return df
    except Exception:
        pass
    return pd.DataFrame()


@st.cache_data
def load_all_team_seasons() -> pd.DataFrame:
    """Fetch all team-season records from the NHL stats REST API.

    The summary endpoint returns regular-season data with powerPlayPct included.
    teamAbbrev (triCode) is joined from the separate team-list endpoint.
    Permanently cached — historical records don't change.

    Returns:
        DataFrame with one row per team-season, or an empty DataFrame on failure.
    """
    try:
        # Build teamId -> triCode map from team list
        team_list = requests.get(TEAM_LIST_URL, timeout=15).json().get("data", [])
        id_to_tricode = {
            t["id"]: t["triCode"]
            for t in team_list
            if "id" in t and "triCode" in t
        }

        # Fetch all team-season summary rows
        resp = requests.get(TEAM_STATS_URL, params={"limit": -1}, timeout=30)
        resp.raise_for_status()
        summary_rows = resp.json().get("data", [])
        if not summary_rows:
            return pd.DataFrame()
        df = pd.DataFrame(summary_rows)

        # Attach teamAbbrev from the triCode map
        df["teamAbbrev"] = df["teamId"].map(id_to_tricode)
        # Tag as regular season (this endpoint serves regular-season data by default)
        df["gameTypeId"] = 2

        # Derive columns
        df["SeasonYear"] = df["seasonId"] // 10000
        df["GP"]     = df["gamesPlayed"]
        df["Wins"]   = df["wins"]
        df["Points"] = df["points"]
        if "pointPct" in df.columns:
            df["Win%"] = (df["pointPct"] * 100).round(1)
        else:
            df["Win%"] = (df["points"] / (df["gamesPlayed"] * 2) * 100).round(1)
        df["GF/G"]  = df["goalsForPerGame"].round(3)
        df["GA/G"]  = df["goalsAgainstPerGame"].round(3)
        df["Goals"] = df["goalsFor"]
        df["PPG"]   = (df["goalsFor"] / df["gamesPlayed"] * 2.7).round(3)
        df["PP%"]   = (
            (df["powerPlayPct"] * 100).round(1)
            if "powerPlayPct" in df.columns
            else float("nan")
        )

        keep = [
            "teamId", "teamFullName", "teamAbbrev", "seasonId", "gameTypeId",
            "SeasonYear", "GP", "Wins", "Points", "Win%",
            "Goals", "GF/G", "GA/G", "PPG", "PP%",
        ]
        return df[[c for c in keep if c in df.columns]].reset_index(drop=True)
    except Exception:
        return pd.DataFrame()


# ---------------------------------------------------------------------------
# NHL records API helpers
# ---------------------------------------------------------------------------

def _paginate_records(base_url: str) -> list:
    """Fetch all pages from an NHL records endpoint.

    The default page size for records.nhl.com is ~25 rows; this function uses
    page_size=500 to minimise round-trips.

    Args:
        base_url: Records endpoint URL without query parameters.

    Returns:
        List of raw record dicts from all pages combined.
    """
    all_data = []
    start = 0
    page_size = 500
    while True:
        try:
            page = requests.get(
                f"{base_url}?start={start}&limit={page_size}", timeout=15
            ).json().get('data', [])
            all_data.extend(page)
            if len(page) < page_size:
                break
            start += page_size
        except Exception:
            break
    return all_data


@st.cache_data(ttl=3600)
def fetch_all_time_records(category: str, s_type: str) -> list:
    """Fetch career records for skaters or goalies from records.nhl.com.

    Combines regular-season and playoff data when s_type == 'Both' by summing
    numeric fields per player.

    Args:
        category: 'Skater' or 'Goalie'.
        s_type:   'Regular', 'Playoffs', or 'Both'.

    Returns:
        List of record dicts, each containing playerId and career stat fields.
        Returns [] on network failure.
    """
    try:
        if category == "Skater":
            reg_url = "https://records.nhl.com/site/api/skater-career-scoring-regular-season"
            ply_url = "https://records.nhl.com/site/api/skater-career-scoring-playoff"
        else:
            reg_url = "https://records.nhl.com/site/api/goalie-career-stats"
            ply_url = "https://records.nhl.com/site/api/goalie-career-playoff-stats"

        reg_data = _paginate_records(reg_url)
        if s_type == "Regular":
            return reg_data

        ply_data = _paginate_records(ply_url)
        if s_type == "Playoffs":
            return ply_data

        # s_type == "Both" — combine by summing numeric fields per player
        combined = {}
        for r in reg_data:
            combined[r['playerId']] = r.copy()
        for p in ply_data:
            pid = p['playerId']
            if pid in combined:
                for k in ['points', 'goals', 'assists', 'gamesPlayed',
                          'penaltyMinutes', 'wins', 'shutouts', 'saves', 'plusMinus']:
                    if k in p and k in combined[pid]:
                        combined[pid][k] += p[k]
            else:
                combined[pid] = p.copy()
        return list(combined.values())
    except Exception:
        return []


@st.cache_data
def get_top_50(metric: str = "Points") -> dict:
    """Fetch the top 50 all-time NHL skaters ranked by the specified career counting stat.

    Only Points, Goals, and Assists are supported sort keys. All other metric values
    fall back to Points ranking as the least-surprising default.

    Args:
        metric: Stat label to sort by. One of 'Points', 'Goals', 'Assists', or any
            other skater metric string (non-matching values default to 'Points').

    Returns:
        Dict mapping display label (e.g. '1. Wayne Gretzky (2857 P)') to playerId int.
        Falls back to a hardcoded 4-player dict (no stat suffix) if the API call fails.
    """
    _SORT_MAP   = {"Points": "points", "Goals": "goals", "Assists": "assists"}
    _SUFFIX_MAP = {"Points": "P",      "Goals": "G",     "Assists": "A"}
    sort_key = _SORT_MAP.get(metric, "points")
    suffix   = _SUFFIX_MAP.get(metric, "P")
    try:
        url = (
            "https://records.nhl.com/site/api/skater-career-scoring-regular-season"
            f"?sort={sort_key}&dir=DESC&limit=100"
        )
        res = requests.get(url, timeout=5).json()
        players = {}
        added_ids = set()
        count = 1
        for p in res.get('data', []):
            pid = int(p['playerId'])
            if pid not in added_ids:
                stat_val = p.get(sort_key, 0)
                base     = f"{count}. {p.get('firstName', '')} {p.get('lastName', '')}".strip()
                name     = f"{base} ({stat_val} {suffix})"
                players[name] = pid
                added_ids.add(pid)
                count += 1
                if count > 50:
                    break
        if players:
            return players
    except Exception:
        pass
    return {
        "1. Wayne Gretzky": 8447400,
        "2. Jaromir Jagr":  8448208,
        "3. Sidney Crosby": 8471675,
        "4. Alexander Ovechkin": 8471214,
    }


@st.cache_data
def get_top_50_goalies() -> dict:
    """Fetch the top 50 all-time NHL goalies ranked by career regular-season wins.

    Returns:
        Dict mapping display label ('1. Martin Brodeur') to playerId int.
        Falls back to a hardcoded 4-player dict if the API call fails.
    """
    try:
        url = (
            "https://records.nhl.com/site/api/goalie-career-stats"
            "?sort=wins&dir=DESC&limit=100"
        )
        res = requests.get(url, timeout=5).json()
        players = {}
        added_ids = set()
        count = 1
        for p in res.get('data', []):
            pid = int(p['playerId'])
            if pid not in added_ids:
                name = f"{count}. {p.get('firstName', '')} {p.get('lastName', '')}".strip()
                players[name] = pid
                added_ids.add(pid)
                count += 1
                if count > 50:
                    break
        if players:
            return players
    except Exception:
        pass
    return {
        "1. Martin Brodeur":    8455710,
        "2. Patrick Roy":       8451033,
        "3. Marc-Andre Fleury": 8471679,
        "4. Roberto Luongo":    8466141,
    }


# ---------------------------------------------------------------------------
# Player search
# ---------------------------------------------------------------------------

@st.cache_data(ttl=3600)
def search_player(query: str) -> list:
    """Search for players by name using the D3 NHL search API.

    Cached for 1 hour so mid-season trades (which change teamAbbrev) expire
    automatically without a full restart.

    Args:
        query: Partial or full player name string.

    Returns:
        List of player dicts from the D3 API (each has 'name', 'playerId',
        'teamAbbrev').  Returns [] on empty query or network failure.
    """
    if not query:
        return []
    try:
        return requests.get(
            SEARCH_URL, params={"culture": "en-us", "limit": 40, "q": query}
        ).json()
    except Exception:
        return []


def search_local_players(query: str, category: str) -> dict:
    """Supplement D3 API results with first- or last-name matches from local records.

    The D3 search API does full-name prefix matching, so 'Bedard' won't find
    Connor Bedard (his name starts with 'Connor', not 'Bedard').  This function
    fills that gap by matching the query against both first and last names in
    the id_to_name_map.

    Args:
        query:    Partial name string (minimum 2 characters).
        category: 'Skater' or 'Goalie' — selects the correct records pool.

    Returns:
        Dict mapping display label ('[TEAM] Full Name') to playerId int.
        Returns {} if query is too short or no matches found.
    """
    q = query.lower().strip()
    if len(q) < 2:
        return {}
    id_map = get_id_to_name_map(category)
    details = get_clone_details_map(category)
    results = {}
    for pid, full_name in id_map.items():
        parts = full_name.lower().split()
        if len(parts) < 2:
            continue
        first, last = parts[0], parts[-1]
        if first.startswith(q) or last.startswith(q):
            team = (details.get(pid) or {}).get('team', '') or ''
            if not team:
                # clone_details_map often has no team for active players because
                # the records API omits activeTeamAbbrevs.  Fall back to a D3
                # search by last name — search_player() is cached so no extra
                # latency on repeats.
                last_name = full_name.split()[-1]
                for r in search_player(last_name):
                    if int(r.get('playerId', 0)) == pid:
                        team = r.get('teamAbbrev', '') or ''
                        break
            label = f"[{team}] {full_name}" if team else full_name
            results[label] = pid
        if len(results) >= 20:
            break
    return results


# ---------------------------------------------------------------------------
# Roster & headshot
# ---------------------------------------------------------------------------

@st.cache_data
def get_team_roster(team_abbr: str) -> dict:
    """Fetch the current NHL roster for a team.

    Args:
        team_abbr: Three-letter team abbreviation (e.g. 'EDM').

    Returns:
        Dict mapping '[POS] First Last #NN' to int playerId, sorted alphabetically.
        Jersey number is omitted only if the API does not return it.
        Returns {} on failure.
    """
    try:
        res = requests.get(ROSTER_URL.format(team_abbr)).json()
        players = {}
        pos_map = {'C': 'C', 'L': 'LW', 'R': 'RW', 'D': 'D', 'G': 'G'}
        for pos_group in ['forwards', 'defensemen', 'goalies']:
            for p in res.get(pos_group, []):
                raw_pos   = p.get('positionCode', '?')
                clean_pos = pos_map.get(raw_pos, raw_pos)
                num       = p.get('sweaterNumber', '')
                base      = f"[{clean_pos}] {p['firstName']['default']} {p['lastName']['default']}"
                name      = f"{base} #{num}" if num else base
                players[name] = int(p['id'])
        return dict(sorted(players.items()))
    except Exception:
        return {}


@st.cache_data
def get_player_headshot(player_id: int) -> str:
    """Return the headshot URL for a player from the NHL stats API.

    Args:
        player_id: Numeric NHL player ID.

    Returns:
        URL string, or '' if the API call fails or no headshot is available.
    """
    try:
        res = requests.get(STATS_URL.format(player_id), timeout=5).json()
        return res.get('headshot', '')
    except Exception:
        return ''


@st.cache_data
def get_player_current_team(player_id: int) -> str:
    """Return the current team abbreviation for an active NHL player.

    Fetches the player landing page and returns the currentTeamAbbrev field.
    Active players return a tricode (e.g. 'EDM'). Retired players and free
    agents return an empty string, which callers should treat as "no logo".

    Args:
        player_id: Numeric NHL player ID.

    Returns:
        Three-letter team abbreviation string, or '' if inactive/unavailable.
    """
    try:
        res = requests.get(STATS_URL.format(player_id), timeout=5).json()
        return res.get('currentTeamAbbrev', '') or ''
    except Exception:
        return ''


@st.cache_data
def get_player_hero_image(player_id: int) -> str:
    """Return the full-body hero image URL for a player from the NHL stats API.

    The heroImage field is a full-body action render with transparent background,
    available for current and recent players. Falls back to the headshot URL if
    heroImage is absent (common for retired players).

    Args:
        player_id: Numeric NHL player ID.

    Returns:
        URL string for heroImage or headshot fallback, or '' on failure.
    """
    try:
        res = requests.get(STATS_URL.format(player_id), timeout=5).json()
        return res.get('heroImage', res.get('headshot', ''))
    except Exception:
        return ''


# ---------------------------------------------------------------------------
# Per-player raw stats
# ---------------------------------------------------------------------------

@st.cache_data
def get_player_raw_stats(
    player_id: int,
    base_name: str,
) -> tuple:
    """Fetch raw season-by-season stats for a player from the NHL API.

    Covers regular season (gameTypeId=2) and playoffs (gameTypeId=3) for all
    leagues in NHLE_MULTIPLIERS.  NHLe multipliers are NOT applied here —
    they are applied downstream in player_pipeline.py so the raw parquet-level
    values are preserved.

    Saves calculation (FIX #5): prefers the 'saves' field; falls back to
    shotsAgainst - goalsAgainst only when shotsAgainst > 0, preventing
    false goalie identification from 0-0=0 calculations.

    Args:
        player_id: Numeric NHL player ID.
        base_name: Display name used as the BaseName column in the returned DataFrame.

    Returns:
        Tuple of (DataFrame, base_name, position_code).
        DataFrame has one row per season with columns: League, Age, SeasonYear,
        GameType, GP, Points, Goals, Assists, PIM, +/-, Shots, TotalTOIMins,
        Wins, Shutouts, Saves, WeightedSV, WeightedGAA.
        Returns (empty DataFrame, base_name, 'S') on failure.
    """
    try:
        res = requests.get(STATS_URL.format(player_id)).json()
        birth_date = str(res.get('birthDate', '2000'))
        birth_year = int(birth_date[:4]) if len(birth_date) >= 4 else 2000
        position   = res.get('position', 'S')
        data = []

        for s in res.get('seasonTotals', []):
            league    = str(s.get('leagueAbbrev', '')).strip().upper()
            game_type = str(s.get('gameTypeId', ''))
            if league in NHLE_MULTIPLIERS and game_type in ['2', '3']:
                season_str = str(s.get('season', ''))
                season_year = int(season_str[:4]) if len(season_str) >= 4 else 2000
                age = season_year - birth_year
                gp  = max(s.get('gamesPlayed', 1), 1)

                toi_str = str(s.get('avgToi', '0:00'))
                try:
                    parts   = toi_str.split(':')
                    toi_val = int(parts[0]) + int(parts[1]) / 60.0 if len(parts) == 2 else 0
                except Exception:
                    toi_val = 0

                # FIX #5: Robust Saves calculation.
                raw_saves = s.get('saves')
                if raw_saves is not None and raw_saves > 0:
                    calc_saves = raw_saves
                else:
                    sa = s.get('shotsAgainst', 0) or 0
                    ga = s.get('goalsAgainst', 0) or 0
                    calc_saves = max(0, sa - ga) if sa > 0 else 0

                data.append({
                    "League":     league,
                    "Age":        age,
                    "SeasonYear": season_year,
                    "GameType":   "Regular" if game_type == '2' else "Playoffs",
                    "GP":         gp,
                    "Points":     s.get('points', 0),
                    "Goals":      s.get('goals', 0),
                    "Assists":    s.get('assists', 0),
                    "PIM":        s.get('pim', 0) or s.get('penaltyMinutes', 0),
                    "+/-":        s.get('plusMinus', 0),
                    "Shots":      s.get('shots', 0),
                    "TotalTOIMins": toi_val * gp,
                    "Wins":       s.get('wins', 0),
                    "Shutouts":   s.get('shutouts', 0),
                    "Saves":      calc_saves,
                    "WeightedSV": float(s.get('savePctg', 0.0)) * 100 * gp,
                    "WeightedGAA": float(s.get('goalsAgainstAvg', 0.0)) * gp,
                })
        return pd.DataFrame(data), base_name, position
    except Exception:
        return pd.DataFrame(), base_name, 'S'


# ---------------------------------------------------------------------------
# Records-based lookup maps
# ---------------------------------------------------------------------------

@st.cache_data(ttl=3600)
def get_id_to_name_map(category: str) -> dict:
    """Build a player ID -> full name map from the records API.

    Cached for 1 hour so newly active players appear without a restart.

    Args:
        category: 'Skater' or 'Goalie'.

    Returns:
        Dict mapping int playerId to 'First Last' name string.
    """
    records = fetch_all_time_records(category, "Regular")
    return {
        int(r['playerId']): f"{r.get('firstName', '')} {r.get('lastName', '')}".strip()
        for r in records
    }


@st.cache_data(ttl=3600)
def get_clone_details_map(category: str) -> dict:
    """Build a player ID -> career stats dict from the records API.

    Used to populate the KNN clone table shown in the projection dialog.
    Handles franchise sub-totals by keeping only the row with the highest GP.

    Args:
        category: 'Skater' or 'Goalie'.

    Returns:
        Dict mapping int playerId to a stats dict.
        Skater keys: name, team, gp, pts, g, a, pm.
        Goalie keys:  name, team, gp, w, sv, so.
    """
    records = fetch_all_time_records(category, "Regular")
    details = {}
    for r in records:
        pid  = int(r['playerId'])
        team = r.get('lastTeamAbbrev', '') or r.get('activeTeamAbbrevs', '') or ''
        if ',' in str(team):
            team = str(team).split(',')[-1].strip()
        gp = int(r.get('gamesPlayed', 0) or 0)

        # Only overwrite if this row has more games played (filters out franchise fragments)
        if pid not in details or gp > details[pid]['gp']:
            if category == "Skater":
                details[pid] = {
                    'name': f"{r.get('firstName', '')} {r.get('lastName', '')}".strip(),
                    'team': team,
                    'gp':   gp,
                    'pts':  int(r.get('points', 0) or 0),
                    'g':    int(r.get('goals', 0) or 0),
                    'a':    int(r.get('assists', 0) or 0),
                    'pm':   int(r.get('plusMinus', 0) or 0),
                }
            else:
                details[pid] = {
                    'name': f"{r.get('firstName', '')} {r.get('lastName', '')}".strip(),
                    'team': team,
                    'gp':   gp,
                    'w':    int(r.get('wins', 0) or 0),
                    'sv':   int(r.get('saves', 0) or 0),
                    'so':   int(r.get('shutouts', 0) or 0),
                }
    return details


# ---------------------------------------------------------------------------
# All-time ranking
# ---------------------------------------------------------------------------

def get_all_time_rank(
    category: str,
    s_type: str,
    metric: str,
    value: float,
) -> int | None:
    """Estimate a stat value's all-time career rank among NHL players.

    Args:
        category: 'Skater' or 'Goalie'.
        s_type:   'Regular', 'Playoffs', or 'Both'.
        metric:   Stat name (e.g. 'Points', 'Wins').
        value:    The career total to rank.

    Returns:
        Integer rank (1 = all-time leader), or None if the metric has no
        matching records key or the records list is empty.
    """
    records = fetch_all_time_records(category, s_type)
    if not records:
        return None
    key_map = {
        "Points":  "points",
        "Goals":   "goals",
        "Assists": "assists",
        "+/-":     "plusMinus",
        "GP":      "gamesPlayed",
        "PIM":     "penaltyMinutes",
        "Wins":    "wins",
        "Shutouts":"shutouts",
        "Saves":   "saves",
    }
    key = key_map.get(metric)
    if not key:
        return None
    records = sorted(
        [r for r in records if r.get(key) is not None],
        key=lambda x: x.get(key, 0),
        reverse=True,
    )
    for i, record in enumerate(records):
        if value >= record.get(key, 0):
            return i + 1
    return len(records) + 1


def get_player_career_rank(pid: int, category: str, s_type: str, metric: str = "Points") -> int | None:
    """Return a player's exact all-time career rank looked up by player ID.

    Unlike get_all_time_rank (value comparison), this matches the player's
    record by playerId in the sorted list, eliminating float drift and API
    ordering discrepancies that cause off-by-N errors.

    Args:
        pid:      Numeric NHL player ID.
        category: 'Skater' or 'Goalie'.
        s_type:   'Regular', 'Playoffs', or 'Both'.
        metric:   Stat to rank by: 'Points', 'Goals', or 'Assists' for skaters;
            other values default to Points. Ignored for Goalies (always Wins).

    Returns:
        1-based integer rank (1 = all-time leader), or None if the player is
        not found in the records list (rookie, non-NHL career, etc.).
    """
    records = fetch_all_time_records(category, s_type)
    if not records:
        return None
    _RANK_KEY_MAP = {"Points": "points", "Goals": "goals", "Assists": "assists"}
    rank_key = "wins" if category == "Goalie" else _RANK_KEY_MAP.get(metric, "points")
    sorted_records = sorted(
        [r for r in records if r.get(rank_key) is not None],
        key=lambda x: x.get(rank_key, 0),
        reverse=True,
    )
    # Deduplicate by playerId (API may return multiple stints per player);
    # keep first (highest-value) occurrence so rank matches the Top 50 dropdown.
    seen_ids: set = set()
    deduped: list = []
    for r in sorted_records:
        pid_r = int(r.get('playerId', -1))
        if pid_r not in seen_ids:
            seen_ids.add(pid_r)
            deduped.append(r)
    for i, r in enumerate(deduped):
        if int(r.get('playerId', -1)) == pid:
            return i + 1
    return None
