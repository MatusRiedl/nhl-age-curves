"""Cached parquet and NHL API loaders.

Keep the silent fallback behavior. The APIs are undocumented and occasionally
weird.
"""

import os

import pandas as pd
import requests
import streamlit as st

from nhl.constants import (
    NHLE_DEFAULT_MULTIPLIER,
    NHLE_MULTIPLIERS,
    SEARCH_URL,
    STATS_URL,
    ROSTER_URL,
    TEAM_LIST_URL,
    TEAM_STATS_URL,
    TEAM_METRICS,
    normalize_league_abbrev,
)


def _normalize_historical_goalie_rates(df: pd.DataFrame) -> pd.DataFrame:
    """Coerce historical goalie `SavePct` values into sane 0-1 scale."""
    if df.empty or 'SavePct' not in df.columns or 'Position' not in df.columns:
        return df

    d = df.copy()
    goalie_mask = d['Position'].astype(str).str.upper().eq('G')
    if not goalie_mask.any():
        return d

    save_pct = pd.to_numeric(d.loc[goalie_mask, 'SavePct'], errors='coerce')
    over_one = save_pct > 1.5
    if over_one.any():
        save_pct.loc[over_one] = save_pct.loc[over_one] / 100.0

    d.loc[goalie_mask, 'SavePct'] = save_pct.clip(lower=0.0, upper=1.0).fillna(0.0)
    return d


# ---------------------------------------------------------------------------
# Parquet / historical data
# ---------------------------------------------------------------------------

@st.cache_data
def load_historical_data() -> pd.DataFrame:
    """Load the historical parquet and add the derived columns the app expects."""
    try:
        if os.path.exists("nhl_historical_seasons.parquet"):
            df = pd.read_parquet("nhl_historical_seasons.parquet")
            if "Position" not in df.columns:
                df["Position"] = "S"

            # Some historical parquet variants label all rows as skaters.
            # When no explicit goalie rows exist, infer goalies from
            # goalie-only counting stats so downstream Position=='G' filters work.
            _pos = df["Position"].astype(str).str.upper()
            if (_pos == "G").sum() == 0:
                goalie_mask = pd.Series(False, index=df.index)
                for col in ("Saves", "Wins", "Shutouts"):
                    if col in df.columns:
                        goalie_mask = goalie_mask | df[col].fillna(0).gt(0)
                if goalie_mask.any():
                    df.loc[goalie_mask, "Position"] = "G"

            df = _normalize_historical_goalie_rates(df)

            df['PPG'] = df['Points'] / df['GP']
            df['Save %'] = df['SavePct'] * 100
            return df
    except Exception:
        pass
    return pd.DataFrame()


@st.cache_data
def load_all_team_seasons() -> pd.DataFrame:
    """Fetch all team-season records from the NHL stats REST API.

    Fetches regular-season and playoff rows separately (gameTypeId 2 and 3),
    then concatenates them into one table with an explicit gameTypeId column.
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

        def _fetch_team_summary_by_type(game_type_id: int) -> pd.DataFrame:
            """Fetch team/summary rows filtered by game type."""
            try:
                resp = requests.get(
                    TEAM_STATS_URL,
                    params={"limit": -1, "cayenneExp": f"gameTypeId={game_type_id}"},
                    timeout=30,
                )
                resp.raise_for_status()
                rows = resp.json().get("data", [])
                if not rows:
                    return pd.DataFrame()
                dfx = pd.DataFrame(rows)
                dfx["gameTypeId"] = game_type_id
                return dfx
            except Exception:
                return pd.DataFrame()

        # Fetch regular season and playoffs separately.
        reg_df = _fetch_team_summary_by_type(2)
        ply_df = _fetch_team_summary_by_type(3)
        if reg_df.empty and ply_df.empty:
            return pd.DataFrame()
        df = pd.concat([d for d in (reg_df, ply_df) if not d.empty], ignore_index=True)

        # Attach teamAbbrev from the triCode map
        df["teamAbbrev"] = df["teamId"].map(id_to_tricode)
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
    """Search the D3 NHL player endpoint. Returns `[]` on empty query or failure."""
    if not query:
        return []
    try:
        return requests.get(
            SEARCH_URL, params={"culture": "en-us", "limit": 40, "q": query}
        ).json()
    except Exception:
        return []


def search_local_players(query: str, category: str) -> dict:
    """Fill D3 search gaps by matching first or last names from local records."""
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


@st.cache_data(ttl=3600)
def get_player_landing(player_id: int) -> dict:
    """Return the NHL player landing payload for a single player.

    This is the shared source for player metadata helpers so the app fetches the
    landing endpoint once per player instead of once per wrapper.

    Args:
        player_id: Numeric NHL player ID.

    Returns:
        Parsed landing payload dict, or {} if the request fails.
    """
    try:
        res = requests.get(STATS_URL.format(player_id), timeout=5).json()
        return res if isinstance(res, dict) else {}
    except Exception:
        return {}


def get_player_headshot(player_id: int) -> str:
    """Return the headshot URL from the cached player landing payload.

    Args:
        player_id: Numeric NHL player ID.

    Returns:
        URL string, or '' if no headshot is available.
    """
    res = get_player_landing(player_id)
    return str(res.get('headshot', '') or '')


def get_player_current_team(player_id: int) -> str:
    """Return the current team abbreviation from the cached landing payload.

    Active players return a tricode (e.g. 'EDM'). Retired players and free
    agents return an empty string, which callers should treat as "no logo".

    Args:
        player_id: Numeric NHL player ID.

    Returns:
        Three-letter team abbreviation string, or '' if inactive/unavailable.
    """
    res = get_player_landing(player_id)
    return str(res.get('currentTeamAbbrev', '') or '')


def get_player_roster_info(player_id: int) -> dict:
    """Return active-player position and sweater number, or `{}` if unavailable."""
    _POS_MAP = {'C': 'C', 'L': 'LW', 'R': 'RW', 'D': 'D', 'G': 'G'}
    try:
        res = get_player_landing(player_id)
        if not res.get('currentTeamAbbrev'):
            return {}
        raw_pos = res.get('position', '')
        num = res.get('sweaterNumber')
        if not raw_pos or num is None:
            return {}
        return {
            'position': _POS_MAP.get(raw_pos, raw_pos),
            'sweater_number': int(num),
        }
    except Exception:
        return {}


def get_player_hero_image(player_id: int) -> str:
    """Return the player hero image, falling back to headshot when needed."""
    res = get_player_landing(player_id)
    return str(res.get('heroImage', res.get('headshot', '')) or '')


# ---------------------------------------------------------------------------
# Awards / trophies
# ---------------------------------------------------------------------------

def get_player_awards(player_id: int) -> list:
    """Return the player's awards list from the cached landing payload.

    Args:
        player_id: Numeric NHL player ID.

    Returns:
        List of award dicts (possibly empty). Returns [] on failure.
    """
    awards = get_player_landing(player_id).get('awards', [])
    return awards if isinstance(awards, list) else []


@st.cache_data(ttl=3600)
def get_team_trophy_summary() -> dict:
    """Return team trophy summary keyed by tricode (Stanley Cup count + latest season).

    Source endpoint:
        records.nhl.com franchise-team-totals
        records.nhl.com franchise-season-results

    Returns:
        Dict of {triCode: {'stanley_cups': int, 'latest_cup_season': int | None}}
        for active NHL teams.
        Returns {} on failure.
    """
    try:
        totals_url = "https://records.nhl.com/site/api/franchise-team-totals?limit=2000"
        totals_rows = requests.get(totals_url, timeout=15).json().get("data", [])
        result: dict = {}
        for row in totals_rows:
            if not isinstance(row, dict):
                continue
            if not row.get("activeTeam"):
                continue
            if int(row.get("gameTypeId", 0) or 0) != 2:
                continue
            tri = str(row.get("triCode", "")).strip().upper()
            if not tri:
                continue
            cups = row.get("cups")
            try:
                cups_int = int(cups) if cups is not None else 0
            except Exception:
                cups_int = 0
            result[tri] = {"stanley_cups": cups_int, "latest_cup_season": None}

        # Derive latest Stanley Cup season per team from SCF-winning rows.
        # Some seasons appear twice (gameTypeId 2 and 3), so dedupe by seasonId.
        seasons_url = "https://records.nhl.com/site/api/franchise-season-results?limit=5000"
        season_rows = requests.get(seasons_url, timeout=20).json().get("data", [])
        cup_seasons: dict[str, set[int]] = {}
        for row in season_rows:
            if not isinstance(row, dict):
                continue
            tri = str(row.get("triCode", "")).strip().upper()
            if not tri:
                continue
            if str(row.get("seriesAbbrev", "")).strip().upper() != "SCF":
                continue
            if str(row.get("decision", "")).strip().upper() != "W":
                continue
            sid = row.get("seasonId")
            try:
                sid_int = int(sid)
            except Exception:
                continue
            cup_seasons.setdefault(tri, set()).add(sid_int)

        for tri, data in result.items():
            seasons = cup_seasons.get(tri)
            if seasons:
                data["latest_cup_season"] = max(seasons)
        return result
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# Per-player raw stats
# ---------------------------------------------------------------------------

def discover_all_leagues(sample_player_ids: list[str]) -> dict[str, int]:
    """Audit helper that counts observed `leagueAbbrev` values for sample players."""
    counts: dict[str, int] = {}
    for pid in sample_player_ids:
        try:
            res = requests.get(STATS_URL.format(int(pid)), timeout=15).json()
        except Exception:
            continue
        for season in res.get('seasonTotals', []) or []:
            league = str(season.get('leagueAbbrev', '')).strip()
            if not league:
                continue
            counts[league] = counts.get(league, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))


def get_player_league_abbrevs(player_id: int) -> list[str]:
    """Return unique leagueAbbrev values from cached seasonTotals rows.

    Args:
        player_id: Numeric NHL player ID.

    Returns:
        Sorted list of unique non-empty league abbreviations.
    """
    season_totals = get_player_landing(player_id).get('seasonTotals', []) or []
    leagues = {
        str(season.get('leagueAbbrev', '')).strip()
        for season in season_totals
        if isinstance(season, dict) and str(season.get('leagueAbbrev', '')).strip()
    }
    return sorted(leagues)


@st.cache_data
def get_player_raw_stats(
    player_id: int,
    base_name: str,
) -> tuple:
    """Fetch raw player seasons across all leagues and both game types.

    Keeps unknown leagues, stores NHLe multipliers for downstream use, and
    preserves the goalie-safe saves fallback.
    """
    try:
        res = get_player_landing(player_id)
        birth_date = str(res.get('birthDate', '2000'))
        birth_year = int(birth_date[:4]) if len(birth_date) >= 4 else 2000
        position   = res.get('position', 'S')
        data = []

        for s in res.get('seasonTotals', []):
            league_raw = str(s.get('leagueAbbrev', '')).strip()
            league_key = normalize_league_abbrev(league_raw)
            nhle_mult  = NHLE_MULTIPLIERS.get(league_key, NHLE_DEFAULT_MULTIPLIER)
            game_type = str(s.get('gameTypeId', ''))
            if game_type in ['2', '3']:
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
                    "League":     league_raw,
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
                    "NHLeMultiplier": nhle_mult,
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
    """Build the player-career lookup used by the KNN clone dialog."""
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
    """Estimate where a career total would rank on the all-time NHL list."""
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
    """Look up a player's exact all-time rank by player ID instead of by value."""
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


@st.cache_data
def get_team_all_time_stats() -> dict:
    """Compute all-time franchise stats for each NHL team from historical data.

    Uses regular-season records only (gameTypeId == 2). Computes career totals,
    all-time wins rank (1 = most wins), and best single season by wins.

    Returns:
        Dict mapping teamAbbrev (str) to a stats dict with keys:
            total_wins (int), total_gp (int), total_points (int), total_goals (int),
            wins_rank (int), best_year (int | None), best_wins (int | None),
            best_gp (int | None).
    """
    df = load_all_team_seasons()
    if df.empty:
        return {}
    reg = df[df['gameTypeId'] == 2].copy()

    totals = reg.groupby('teamAbbrev', as_index=False).agg(
        total_wins=('Wins', 'sum'),
        total_gp=('GP', 'sum'),
        total_points=('Points', 'sum'),
        total_goals=('Goals', 'sum'),
    )
    totals = totals.sort_values('total_wins', ascending=False).reset_index(drop=True)
    totals['wins_rank'] = range(1, len(totals) + 1)

    best = (
        reg.sort_values('Wins', ascending=False)
           .groupby('teamAbbrev', as_index=False)
           .first()[['teamAbbrev', 'SeasonYear', 'Wins', 'GP']]
           .rename(columns={'SeasonYear': 'best_year', 'Wins': 'best_wins', 'GP': 'best_gp'})
    )

    merged = totals.merge(best, on='teamAbbrev', how='left')
    result: dict = {}
    for _, row in merged.iterrows():
        result[row['teamAbbrev']] = {
            'total_wins':   int(row['total_wins']),
            'total_gp':     int(row['total_gp']),
            'total_points': int(row['total_points']),
            'total_goals':  int(row['total_goals']),
            'wins_rank':    int(row['wins_rank']),
            'best_year':    int(row['best_year'])  if pd.notna(row.get('best_year'))  else None,
            'best_wins':    int(row['best_wins'])  if pd.notna(row.get('best_wins'))  else None,
            'best_gp':      int(row['best_gp'])    if pd.notna(row.get('best_gp'))    else None,
        }
    return result
