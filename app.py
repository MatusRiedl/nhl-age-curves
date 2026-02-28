import streamlit as st
import requests
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import os
from datetime import datetime

st.set_page_config(page_title="NHL Age Curves", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
    <style>
        .block-container { padding-top: 2rem !important; padding-bottom: 0rem !important; }
        
        .animated-title { 
            background: linear-gradient(to right, #c0c0c0, #2b71c7, #ff4b4b, #c0c0c0);
            background-size: 300% auto;
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            animation: sweep 6s linear infinite;
        }
        
        @keyframes sweep {
            to { background-position: 300% center; }
        }

        .nhl-logo {
            height: 45px;
            margin-right: 15px;
            animation: spin-pulse 4s infinite ease-in-out;
        }

        @keyframes spin-pulse {
            0% { transform: rotateY(0deg) scale(1); }
            50% { transform: rotateY(180deg) scale(1.15); }
            100% { transform: rotateY(360deg) scale(1); }
        }
        
        .stButton button { width: 100%; }
        
        [data-testid="stSidebar"] [data-testid="stHorizontalBlock"] div.stButton button {
            width: auto !important;
            min-width: 0 !important;
            padding: 0.2rem 0.6rem !important;
            float: right;
        }

        [data-testid="stSidebar"] [data-testid="stHorizontalBlock"] {
            flex-wrap: nowrap !important;
            align-items: center !important;
            gap: 0 !important;
        }

        /* Tighten sidebar vertical spacing */
        [data-testid="stSidebar"] .stMarkdown hr {
            margin-top: 6px !important;
            margin-bottom: 6px !important;
        }
        [data-testid="stSidebar"] .element-container {
            margin-bottom: 4px !important;
        }
        [data-testid="stSidebar"] h3 {
            margin-top: 4px !important;
            margin-bottom: 4px !important;
        }
        
        .player-name {
            font-size: 15px;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }
        
        div.element-container:has(.blue-btn-anchor) + div.element-container button {
            background-color: #2b71c7 !important;
            border-color: #2b71c7 !important;
            color: white !important;
        }
        div.element-container:has(.blue-btn-anchor) + div.element-container button:hover {
            background-color: #1a569d !important;
            border-color: #1a569d !important;
        }

        @media (max-width: 768px) {
            div:has(> #master-toggles) + div [data-testid="stHorizontalBlock"] {
                flex-wrap: nowrap !important;
            }
            div:has(> #master-toggles) + div [data-testid="column"] {
                min-width: 48% !important;
                flex: 1 1 48% !important;
            }
        }
    </style>
""", unsafe_allow_html=True)

SEARCH_URL = "https://search.d3.nhle.com/api/v1/search/player"
STATS_URL = "https://api-web.nhle.com/v1/player/{}/landing"
ROSTER_URL = "https://api-web.nhle.com/v1/roster/{}/current"

ACTIVE_TEAMS = {
    "ANA": "Anaheim Ducks", "BOS": "Boston Bruins", "BUF": "Buffalo Sabres",
    "CGY": "Calgary Flames", "CAR": "Carolina Hurricanes", "CHI": "Chicago Blackhawks",
    "COL": "Colorado Avalanche", "CBJ": "Columbus Blue Jackets", "DAL": "Dallas Stars",
    "DET": "Detroit Red Wings", "EDM": "Edmonton Oilers", "FLA": "Florida Panthers",
    "LAK": "Los Angeles Kings", "MIN": "Minnesota Wild", "MTL": "Montreal Canadiens",
    "NSH": "Nashville Predators", "NJD": "New Jersey Devils", "NYI": "New York Islanders",
    "NYR": "New York Rangers", "OTT": "Ottawa Senators", "PHI": "Philadelphia Flyers",
    "PIT": "Pittsburgh Penguins", "SJS": "San Jose Sharks", "SEA": "Seattle Kraken",
    "STL": "St. Louis Blues", "TBL": "Tampa Bay Lightning", "TOR": "Toronto Maple Leafs",
    "UTA": "Utah Hockey Club", "VAN": "Vancouver Canucks", "VGK": "Vegas Golden Knights",
    "WSH": "Washington Capitals", "WPG": "Winnipeg Jets"
}

# --- Rate stats require mean aggregation; counting stats use sum ---
RATE_STATS = {'PPG', 'Save %', 'GAA', 'SH%', 'TOI'}

# --- NHLe (NHL Equivalency) multipliers — 2024 research values (Bacon/Chatel model) ---
# Points, Goals, Assists for non-NHL rows are multiplied by these before entering the pipeline.
# Leagues not listed are dropped (noise filter). Keys are uppercase to match API leagueAbbrev.
NHLE_MULTIPLIERS = {
    'NHL': 1.0, 'KHL': 0.77, 'SHL': 0.57, 'AHL': 0.39,
    'NLA': 0.46, 'LIIGA': 0.44, 'NCAA': 0.19,
    'OHL': 0.14, 'WHL': 0.14, 'QMJHL': 0.11,
}

# --- FIX #3: Dynamic current season year — never hardcodes a year again ---
# NHL season starts in October; if we're Jan-Aug we're still in the season
# that began the prior calendar year.
_now = datetime.now()
CURRENT_SEASON_YEAR = _now.year if _now.month >= 9 else _now.year - 1

if 'players' not in st.session_state: st.session_state.players = {}
if 'stat_category' not in st.session_state: st.session_state.stat_category = "Skater"
if 'season_type' not in st.session_state: st.session_state.season_type = "Regular"
if 'do_smooth' not in st.session_state: st.session_state.do_smooth = False
if 'do_predict' not in st.session_state: st.session_state.do_predict = False
if 'do_era' not in st.session_state: st.session_state.do_era = False
if 'do_cumul_toggle' not in st.session_state: st.session_state.do_cumul_toggle = False
if 'do_base' not in st.session_state: st.session_state.do_base = False
if 'x_axis_mode' not in st.session_state: st.session_state.x_axis_mode = "Age"
if 'league_filter' not in st.session_state: st.session_state.league_filter = ['NHL']

@st.cache_data
def load_historical_data():
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
def build_historical_baselines(df):
    if df.empty: return {}
    full_time = df[df['GP'] >= 40]
    
    skater_base = full_time[full_time['Position'] != 'G'].groupby('Age').quantile(0.75, numeric_only=True)
    goalie_base = full_time[full_time['Position'] == 'G'].groupby('Age').quantile(0.75, numeric_only=True)
    
    # Fix Survivorship Bias: Smooth the curve and enforce bounded decay after age 31.
    # Rule A (existing): if baseline rises after 31, cap at 0.92× prev — survivorship fix.
    # Rule B (new): if baseline drops >15% in one year, cap the drop at 15%.
    #   Prevents data-sparsity cliff at ages 38-40 where the parquet has very few
    #   players still playing 40+ GP — the raw 75th pct collapses toward 0.
    for base in [skater_base, goalie_base]:
        base_smoothed = base.rolling(window=3, min_periods=1, center=True).mean()
        for col in base.columns:
            base[col] = base_smoothed[col]
            for age in range(32, 42):
                if age in base.index and (age-1) in base.index:
                    prev = base.loc[age-1, col]
                    curr = base.loc[age, col]
                    if prev <= 0:
                        continue
                    if curr > prev:
                        base.loc[age, col] = prev * 0.92
                    elif curr < prev * 0.85:
                        base.loc[age, col] = prev * 0.85

    return {'Skater': skater_base, 'Goalie': goalie_base}

def get_era_multiplier(year):
    """Era-adjust scoring to normalize across NHL rule/style changes.
    Baseline = 2018-present (~3.05 GF/GP per team = ~6.1 total goals/game).
    Multiplier = baseline_GF / era_GF.  Values < 1.0 deflate (high-scoring eras),
    values > 1.0 inflate (low-scoring eras).
    """
    if year <= 1967:   return 1.00   # Original Six (~2.85 GF/GP — close to modern baseline)
    if 1968 <= year <= 1979: return 0.89  # Expansion + WHA era (~3.40 GF/GP); 3.05/3.40=0.897
    if 1980 <= year <= 1992: return 0.80  # Gretzky/peak scoring era (~3.85 GF/GP); 3.05/3.85=0.792
    if 1993 <= year <= 1996: return 0.90  # Transitional decline (~3.35 GF/GP); 3.05/3.35=0.910
    if 1997 <= year <= 2004: return 1.15  # Dead puck era (~2.63 GF/GP); 3.05/2.63=1.160
    if 2005 <= year <= 2012: return 1.06  # Post-lockout settling (~2.87 GF/GP); 3.05/2.87=1.063
    if 2013 <= year <= 2017: return 1.12  # Analytics/trap era (~2.72 GF/GP); 3.05/2.72=1.121
    return 1.00  # 2018+ scoring renaissance (~3.05 GF/GP — the baseline)

def apply_era_to_hist(df, do_era):
    """Return hist_df with Points/Goals/Assists era-adjusted using the app's 8-period
    multiplier when do_era is True. Used to keep KNN and ranking comparisons consistent
    with whatever era-adjustment state the live player data is in."""
    if not do_era:
        return df
    d = df.copy()
    mult = d['SeasonYear'].apply(get_era_multiplier)
    for col in ['Points', 'Goals', 'Assists']:
        if col in d.columns:
            d[col] = d[col] * mult
    return d

def _paginate_records(base_url):
    """Fetch all pages from an NHL records endpoint (default page size is ~25)."""
    all_data = []
    start = 0
    page_size = 500
    while True:
        try:
            page = requests.get(f"{base_url}?start={start}&limit={page_size}", timeout=15).json().get('data', [])
            all_data.extend(page)
            if len(page) < page_size:
                break
            start += page_size
        except Exception:
            break
    return all_data

@st.cache_data(ttl=3600)
def fetch_all_time_records(category, s_type):
    try:
        if category == "Skater":
            reg_url = "https://records.nhl.com/site/api/skater-career-scoring-regular-season"
            ply_url = "https://records.nhl.com/site/api/skater-career-scoring-playoff"
        else:
            reg_url = "https://records.nhl.com/site/api/goalie-career-stats"
            ply_url = "https://records.nhl.com/site/api/goalie-career-playoff-stats"

        reg_data = _paginate_records(reg_url)
        if s_type == "Regular": return reg_data

        ply_data = _paginate_records(ply_url)
        if s_type == "Playoffs": return ply_data

        combined = {}
        for r in reg_data: combined[r['playerId']] = r.copy()
        for p in ply_data:
            pid = p['playerId']
            if pid in combined:
                for k in ['points', 'goals', 'assists', 'gamesPlayed', 'penaltyMinutes', 'wins', 'shutouts', 'saves', 'plusMinus']:
                    if k in p and k in combined[pid]: combined[pid][k] += p[k]
            else:
                combined[pid] = p.copy()
        return list(combined.values())
    except Exception: return []

@st.cache_data
def get_top_50():
    try:
        url = "https://records.nhl.com/site/api/skater-career-scoring-regular-season?sort=points&dir=DESC&limit=100"
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
                if count > 50: break

        if players: return players
    except Exception:
        pass
    return { "1. Wayne Gretzky": 8447400, "2. Jaromir Jagr": 8448208, "3. Sidney Crosby": 8471675, "4. Alexander Ovechkin": 8471214 }

# FIX #9: Added ttl=3600 so stale team labels (mid-season trades) expire automatically.
@st.cache_data(ttl=3600)
def search_player(query):
    if not query: return []
    try: return requests.get(SEARCH_URL, params={"culture": "en-us", "limit": 20, "q": query}).json()
    except Exception: return []

def search_local_by_first_name(query, category):
    """Supplement d3 API results with first-name matches from the local records cache.
    The d3 search API only indexes last names / full-name prefixes, so 'Connor' won't
    find McDavid. This function fills that gap by matching the query against first names
    in id_to_name_map (which has full 'First Last' strings from the records API)."""
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
        # Only match on first name; skip if query also matches the last name
        # (the d3 API already handles last-name queries well)
        if first.startswith(q) and not last.startswith(q):
            team = (details.get(pid) or {}).get('team', '') or ''
            if not team:
                # clone_details_map often has no team for active players because the
                # records API omits activeTeamAbbrevs. Fall back to a d3 search by
                # last name — search_player() is cached so no extra latency on repeats.
                last_name = full_name.split()[-1]
                for r in search_player(last_name):
                    if int(r.get('playerId', 0)) == pid:
                        team = r.get('teamAbbrev', '') or ''
                        break
            label = f"[{team}] {full_name}" if team else full_name
            results[label] = pid
        if len(results) >= 10:
            break
    return results

@st.cache_data
def get_team_roster(team_abbr):
    try:
        res = requests.get(ROSTER_URL.format(team_abbr)).json()
        players = {}
        pos_map = {'C': 'C', 'L': 'LW', 'R': 'RW', 'D': 'D', 'G': 'G'}
        for pos_group in ['forwards', 'defensemen', 'goalies']:
            for p in res.get(pos_group, []):
                raw_pos = p.get('positionCode', '?')
                clean_pos = pos_map.get(raw_pos, raw_pos)
                name = f"[{clean_pos}] {p['firstName']['default']} {p['lastName']['default']}"
                players[name] = int(p['id'])
        return dict(sorted(players.items()))
    except Exception: return {}

@st.cache_data
def get_player_headshot(player_id):
    try:
        res = requests.get(STATS_URL.format(player_id), timeout=5).json()
        return res.get('headshot', '')
    except Exception:
        return ''

@st.cache_data
def get_player_raw_stats(player_id, base_name):
    try:
        res = requests.get(STATS_URL.format(player_id)).json()
        birth_date = str(res.get('birthDate', '2000'))
        birth_year = int(birth_date[:4]) if len(birth_date) >= 4 else 2000
        position = res.get('position', 'S')
        data = []

        for s in res.get('seasonTotals', []):
            league = str(s.get('leagueAbbrev', '')).strip().upper()
            game_type = str(s.get('gameTypeId', ''))
            if league in NHLE_MULTIPLIERS and game_type in ['2', '3']:
                season_str = str(s.get('season', ''))
                season_year = int(season_str[:4]) if len(season_str) >= 4 else 2000
                age = season_year - birth_year
                gp = max(s.get('gamesPlayed', 1), 1)
                toi_str = str(s.get('avgToi', '0:00'))
                try:
                    parts = toi_str.split(':')
                    toi_val = int(parts[0]) + int(parts[1])/60.0 if len(parts) == 2 else 0
                except Exception: toi_val = 0

                # FIX #5: Robust Saves calculation. If 'saves' is present, use it.
                # Otherwise compute from shotsAgainst - goalsAgainst, but only if
                # shotsAgainst is actually present (non-zero) to prevent 0-0=0
                # which would cause a goalie to be misidentified as a skater.
                raw_saves = s.get('saves')
                if raw_saves is not None and raw_saves > 0:
                    calc_saves = raw_saves
                else:
                    sa = s.get('shotsAgainst', 0) or 0
                    ga = s.get('goalsAgainst', 0) or 0
                    calc_saves = max(0, sa - ga) if sa > 0 else 0

                data.append({
                    "League": league,
                    "Age": age, "SeasonYear": season_year, "GameType": "Regular" if game_type == '2' else "Playoffs",
                    "GP": gp, "Points": s.get('points', 0), "Goals": s.get('goals', 0), "Assists": s.get('assists', 0),
                    "PIM": s.get('pim', 0) or s.get('penaltyMinutes', 0), "+/-": s.get('plusMinus', 0),
                    "Shots": s.get('shots', 0), "TotalTOIMins": toi_val * gp, "Wins": s.get('wins', 0),
                    "Shutouts": s.get('shutouts', 0), "Saves": calc_saves,
                    "WeightedSV": float(s.get('savePctg', 0.0)) * 100 * gp, "WeightedGAA": float(s.get('goalsAgainstAvg', 0.0)) * gp
                })
        return pd.DataFrame(data), base_name, position
    except Exception:
        return pd.DataFrame(), base_name, 'S'

@st.cache_data(ttl=3600)
def get_id_to_name_map(category):
    records = fetch_all_time_records(category, "Regular")
    return {int(r['playerId']): f"{r.get('firstName', '')} {r.get('lastName', '')}".strip() for r in records}

@st.cache_data(ttl=3600)
def get_clone_details_map(category):
    """Returns {playerId: {name, team, ...stats}} from the records API."""
    records = fetch_all_time_records(category, "Regular")
    details = {}
    for r in records:
        pid = int(r['playerId'])
        team = r.get('lastTeamAbbrev', '') or r.get('activeTeamAbbrevs', '') or ''
        if ',' in str(team):
            team = str(team).split(',')[-1].strip()
            
        gp = int(r.get('gamesPlayed', 0) or 0)
        
        # The API returns franchise sub-totals and a grand total. 
        # Only overwrite if this row has more games played (filters out the franchise fragments).
        if pid not in details or gp > details[pid]['gp']:
            if category == "Skater":
                details[pid] = {
                    'name': f"{r.get('firstName', '')} {r.get('lastName', '')}".strip(),
                    'team': team,
                    'gp': gp,
                    'pts': int(r.get('points', 0) or 0),
                    'g': int(r.get('goals', 0) or 0),
                    'a': int(r.get('assists', 0) or 0),
                    'pm': int(r.get('plusMinus', 0) or 0),
                }
            else:
                details[pid] = {
                    'name': f"{r.get('firstName', '')} {r.get('lastName', '')}".strip(),
                    'team': team,
                    'gp': gp,
                    'w': int(r.get('wins', 0) or 0),
                    'sv': int(r.get('saves', 0) or 0),
                    'so': int(r.get('shutouts', 0) or 0),
                }
    return details

def get_all_time_rank(category, s_type, metric, value):
    records = fetch_all_time_records(category, s_type)
    if not records: return None
    key_map = { "Points": "points", "Goals": "goals", "Assists": "assists", "+/-": "plusMinus", "GP": "gamesPlayed", "PIM": "penaltyMinutes", "Wins": "wins", "Shutouts": "shutouts", "Saves": "saves" }
    key = key_map.get(metric)
    if not key: return None
    records = sorted([r for r in records if r.get(key) is not None], key=lambda x: x.get(key, 0), reverse=True)
    for i, record in enumerate(records):
        if value >= record.get(key, 0): return i + 1
    return len(records) + 1

@st.dialog("Season Snapshot")
def show_season_details(player_name, age, raw_dfs_list, metric, val, is_cumul, full_df, s_type, ml_clones_dict, historical_baselines):
    clean_name = player_name.replace(" (Proj)", "")
    is_baseline = (clean_name == "NHL 75th Percentile Baseline")
    is_projection = "(Proj)" in player_name
    is_real = not is_baseline and not is_projection

    st.markdown(f"### {player_name} at Age {age}")

    # ─── CASE 3: BASELINE LINE CLICK ───────────────────────────────────
    if is_baseline:
        base_df = historical_baselines.get(st.session_state.stat_category)
        if base_df is not None and not base_df.empty and age in base_df.index:
            if st.session_state.stat_category == "Skater":
                b_gp  = int(round(base_df.loc[age, 'GP']))   if 'GP'      in base_df.columns else 0
                b_pts = int(round(base_df.loc[age, 'Points']))if 'Points'  in base_df.columns else 0
                b_g   = int(round(base_df.loc[age, 'Goals'])) if 'Goals'   in base_df.columns else 0
                b_a   = int(round(base_df.loc[age, 'Assists']))if 'Assists' in base_df.columns else 0
                b_pm  = int(round(base_df.loc[age, '+/-']))   if '+/-'     in base_df.columns else 0
                st.markdown(
                    f"<div style='background-color: #2b2b2b; border-left: 4px solid rgba(255,255,255,0.4); padding: 10px 14px; border-radius: 4px; margin-bottom: 8px;'>"
                    f"<b>75th Percentile at Age {age}:</b> {b_gp} GP | {b_pts} Pts | {b_g} G | {b_a} A | {b_pm} +/-</div>",
                    unsafe_allow_html=True)
            else:
                b_gp = int(round(base_df.loc[age, 'GP']))       if 'GP'       in base_df.columns else 0
                b_w  = int(round(base_df.loc[age, 'Wins']))     if 'Wins'     in base_df.columns else 0
                b_sv = int(round(base_df.loc[age, 'Saves']))    if 'Saves'    in base_df.columns else 0
                b_so = int(round(base_df.loc[age, 'Shutouts'])) if 'Shutouts' in base_df.columns else 0
                st.markdown(
                    f"<div style='background-color: #2b2b2b; border-left: 4px solid rgba(255,255,255,0.4); padding: 10px 14px; border-radius: 4px; margin-bottom: 8px;'>"
                    f"<b>75th Percentile at Age {age}:</b> {b_gp} GP | {b_w} W | {b_sv} Saves | {b_so} SO</div>",
                    unsafe_allow_html=True)
        else:
            st.write("No baseline data available for this age.")
        return  # No further content for baseline clicks

    # ─── SHARED: Career Totals (blue) — for both real & projection ──────
    for df in raw_dfs_list:
        if not df.empty and 'BaseName' in df.columns and df['BaseName'].iloc[0] == clean_name:
            display_df_career = df[df['GameType'] == s_type] if s_type != "Both" else df
            career_gp = int(display_df_career['GP'].sum())
            label = "Reg+Playoffs" if s_type == "Both" else s_type
            if st.session_state.stat_category == "Skater":
                career_pts = int(display_df_career['Points'].sum())
                career_g   = int(display_df_career['Goals'].sum())
                career_a   = int(display_df_career['Assists'].sum())
                career_pm  = int(display_df_career['+/-'].sum())
                st.info(f"**Career Totals ({label}):** {career_gp} GP | {career_pts} Pts | {career_g} G | {career_a} A | {career_pm} +/-")
            else:
                career_w  = int(display_df_career['Wins'].sum())
                career_so = int(display_df_career['Shutouts'].sum())
                career_sv = int(display_df_career['Saves'].sum())
                st.info(f"**Career Totals ({label}):** {career_gp} GP | {career_w} W | {career_sv} Saves | {career_so} SO")
            break

    # ─── CASE 1: REAL DATA LINE CLICK ──────────────────────────────────
    if is_real:
        # Career Subtotals up to clicked age (orange) — placed right below blue career totals
        for df in raw_dfs_list:
            if not df.empty and 'BaseName' in df.columns and df['BaseName'].iloc[0] == clean_name:
                sub_df = df[df['Age'] <= age]
                if s_type != "Both":
                    sub_df = sub_df[sub_df['GameType'] == s_type]
                if not sub_df.empty:
                    s_gp = int(sub_df['GP'].sum())
                    if st.session_state.stat_category == "Skater":
                        s_pts = int(sub_df['Points'].sum())
                        s_g   = int(sub_df['Goals'].sum())
                        s_a   = int(sub_df['Assists'].sum())
                        s_pm  = int(sub_df['+/-'].sum())
                        st.warning(f"**Career Subtotals (to Age {age}):** {s_gp} GP | {s_pts} Pts | {s_g} G | {s_a} A | {s_pm} +/-")
                    else:
                        s_w  = int(sub_df['Wins'].sum())
                        s_so = int(sub_df['Shutouts'].sum())
                        s_sv = int(sub_df['Saves'].sum())
                        st.warning(f"**Career Subtotals (to Age {age}):** {s_gp} GP | {s_w} W | {s_sv} Saves | {s_so} SO")
                break

        # Season detail table
        for df in raw_dfs_list:
            if not df.empty and 'BaseName' in df.columns and df['BaseName'].iloc[0] == clean_name:
                season_data = df[df['Age'] == age]
                if s_type != "Both":
                    season_data = season_data[season_data['GameType'] == s_type]
                if not season_data.empty:
                    cols_to_show = ['SeasonYear', 'GameType', 'GP', 'Points', 'Goals', 'Assists', '+/-'] if st.session_state.stat_category == "Skater" else ['SeasonYear', 'GameType', 'GP', 'Wins', 'Saves', 'Shutouts']
                    display_df = season_data[cols_to_show].copy()
                    for col in display_df.columns:
                        if col not in ['SeasonYear', 'GameType']: display_df[col] = display_df[col].astype(int)
                    st.dataframe(display_df, hide_index=True, use_container_width=True)
                break
        return  # End of real data click

    # ─── CASE 2: PROJECTION LINE CLICK ─────────────────────────────────
    if is_projection:
        counting_stats = ['Points', 'Goals', 'Assists', 'Wins', 'Shutouts', 'GP', 'PIM', 'Saves', '+/-']

        # Always compute projected career totals up to clicked age
        player_data = full_df[full_df['BaseName'] == clean_name]
        player_data = player_data[player_data['Age'] <= age].drop_duplicates(subset=['Age'], keep='last')

        if metric in counting_stats:
            career_total = val if is_cumul else player_data[metric].sum()
            rank = get_all_time_rank(st.session_state.stat_category, s_type, metric, career_total)
            if rank:
                st.success(f"🏆 **At Age {age}:** Estimated **{int(career_total)}** career {metric} → **#{rank} All-Time** in NHL history.")
                
        # ML Projection Clones — single column with team + career stats
        if clean_name in ml_clones_dict and ml_clones_dict[clean_name]:
            st.markdown("---")
            st.markdown("**ML Projection Clones (Position-Matched):**")
            clones = ml_clones_dict[clean_name]
            is_skater_mode = st.session_state.stat_category == "Skater"

            if is_skater_mode:
                stat_headers = "<th style='text-align:right; padding:4px;'>GP</th><th style='text-align:right; padding:4px;'>Pts</th><th style='text-align:right; padding:4px;'>G</th><th style='text-align:right; padding:4px;'>A</th>"
            else:
                stat_headers = "<th style='text-align:right; padding:4px;'>GP</th><th style='text-align:right; padding:4px;'>W</th><th style='text-align:right; padding:4px;'>Saves</th><th style='text-align:right; padding:4px;'>SO</th>"

            table_html = "<table style='width:100%; font-size:13px; border-collapse: collapse;'>"
            table_html += f"<tr style='border-bottom: 1px solid #444;'>"
            table_html += f"<th style='text-align:left; padding:4px;'>Player</th>{stat_headers}"
            table_html += "</tr>"

            for c in clones:
                tm = f"[{c['team']}] " if c.get('team') and c['team'] != '—' else ""
                table_html += "<tr style='border-bottom: 1px solid #333;'>"
                table_html += f"<td style='padding:3px 4px; white-space:nowrap;'>{tm}{c['name']}</td>"
                if is_skater_mode:
                    table_html += (f"<td style='text-align:right; padding:3px 4px;'>{c.get('gp',0)}</td>"
                                   f"<td style='text-align:right; padding:3px 4px;'>{c.get('pts',0)}</td>"
                                   f"<td style='text-align:right; padding:3px 4px;'>{c.get('g',0)}</td>"
                                   f"<td style='text-align:right; padding:3px 4px;'>{c.get('a',0)}</td>")
                else:
                    table_html += (f"<td style='text-align:right; padding:3px 4px;'>{c.get('gp',0)}</td>"
                                   f"<td style='text-align:right; padding:3px 4px;'>{c.get('w',0)}</td>"
                                   f"<td style='text-align:right; padding:3px 4px;'>{c.get('sv',0)}</td>"
                                   f"<td style='text-align:right; padding:3px 4px;'>{c.get('so',0)}</td>")
                table_html += "</tr>"
            table_html += "</table>"
            st.markdown(table_html, unsafe_allow_html=True)

# --- SIDEBAR: Player Management ---
with st.sidebar:
    st.subheader("Global Search")

    if 'search_ver' not in st.session_state:
        st.session_state.search_ver = 0
    if 'search_opts' not in st.session_state:
        st.session_state.search_opts = {}

    def _on_player_select():
        ver = st.session_state.search_ver
        sel = st.session_state.get(f"_player_pick_{ver}")
        _SENT = "— select a player —"
        if not sel or sel == _SENT:
            return
        pid = st.session_state.search_opts.get(sel)
        if pid is None:
            return
        name = sel.split("] ")[-1] if "]" in sel else sel
        st.session_state.players[pid] = name
        st.session_state.search_ver = ver + 1
        st.session_state.search_opts = {}

    search_term = st.text_input(
        "Search player:",
        placeholder="e.g., McDavid, Crosby, Connor…",
        label_visibility="collapsed",
        key=f"search_input_{st.session_state.search_ver}"
    )

    opts = {}
    if search_term:
        results = search_player(search_term)
        for p in results:
            tm = p.get('teamAbbrev')
            label = f"[{tm}] {p['name']}" if tm else p['name']
            opts[label] = int(p['playerId'])
        local = search_local_by_first_name(search_term, st.session_state.stat_category)
        for label, pid in local.items():
            if pid not in opts.values():
                opts[label] = pid

    st.session_state.search_opts = opts

    if opts:
        _SENT = "— select a player —"
        st.selectbox(
            "Results:",
            [_SENT] + list(opts.keys()),
            key=f"_player_pick_{st.session_state.search_ver}",
            on_change=_on_player_select,
            label_visibility="collapsed",
        )
    elif search_term:
        st.caption("No players found")

    st.markdown("---")

    top_50_dict = get_top_50()
    top_selected = st.selectbox("Top 50 All-Time", list(top_50_dict.keys()))

    st.markdown("<div class='blue-btn-anchor'></div>", unsafe_allow_html=True)
    if st.button("Add Legend", use_container_width=True):
        st.session_state.players[top_50_dict[top_selected]] = top_selected.split(". ")[-1]

    team_abbr = st.selectbox("Active Rosters", list(ACTIVE_TEAMS.keys()), format_func=lambda x: f"{x} - {ACTIVE_TEAMS[x]}")
    if team_abbr:
        st.markdown(f"<div style='text-align: center; margin-bottom: 5px;'><img src='https://assets.nhle.com/logos/nhl/svg/{team_abbr}_light.svg' height='40'></div>", unsafe_allow_html=True)
        roster = get_team_roster(team_abbr)
        if roster:
            roster_player = st.selectbox("Select Player:", list(roster.keys()), label_visibility="collapsed")

            st.markdown("<div class='blue-btn-anchor'></div>", unsafe_allow_html=True)
            if st.button("Add Roster Player", use_container_width=True):
                clean_name = roster_player.split("] ")[-1] if "]" in roster_player else roster_player
                st.session_state.players[roster[roster_player]] = clean_name

    st.markdown("---")
    if st.session_state.players:
        for pid, name in list(st.session_state.players.items()):
            c_name, c_btn = st.columns([5, 1], vertical_alignment="center", gap="small")
            with c_name:
                headshot = get_player_headshot(pid)
                img_html = f"<img src='{headshot}' style='width:32px;height:32px;border-radius:50%;object-fit:cover;flex-shrink:0;'>" if headshot else ""
                st.markdown(f"""
                    <div style='display:flex;align-items:center;gap:8px;'>
                        {img_html}
                        <div class='player-name'>{name}</div>
                    </div>
                """, unsafe_allow_html=True)
            with c_btn:
                if st.button("✖", key=f"drop_{pid}", type="primary"):
                    del st.session_state.players[pid]
    else:
        st.info("Board is empty")

# --- MAIN: Visualization ---
st.markdown("""
    <h1 style='display: flex; align-items: center; padding-bottom: 0; margin-bottom: 0;'>
        <img src='https://assets.nhle.com/logos/nhl/svg/NHL_light.svg' class='nhl-logo'>
        <span class='animated-title'>NHL Age Curves</span>
    </h1>
""", unsafe_allow_html=True)
st.markdown("---")


# --- EXPANDER 1: Category & Metric ---
# expanded=True ships open on desktop; mobile users can tap the header to collapse it.
with st.expander("📊 Category & Metric", expanded=True):
    c_category, c_metric = st.columns([2, 8], vertical_alignment="center")
    with c_category:
        st.radio("Category:", ["Skater", "Goalie"], horizontal=True, key="stat_category")
    with c_metric:
        if st.session_state.stat_category == "Skater":
            metric = st.radio("Select Metric:",
                                ["Points", "Goals", "Assists", "+/-", "GP", "PPG", "SH%", "PIM", "TOI"],
                                horizontal=True, key="skater_metric",
                                help="+/-: Plus/Minus Differential | GP: Games Played | PPG: Points Per Game | SH%: Shooting Percentage | PIM: Penalty Minutes | TOI: Time on Ice (Avg Mins)")
        else:
            metric = st.radio("Select Metric:",
                                ["Save %", "GAA", "Wins", "Shutouts", "GP", "Saves"],
                                horizontal=True, key="goalie_metric",
                                help="Save %: Save Percentage | GAA: Goals Against Average | GP: Games Played | Saves: Total Saves")
    c_xaxis, c_league, _ = st.columns([3, 4, 3])
    with c_xaxis:
        st.selectbox("X-Axis", ["Age", "Games Played"], key="x_axis_mode",
                     help="Age: plot by player age (default). Games Played: plot by career game number — normalizes for injuries and missed time.")
    with c_league:
        st.multiselect(
            "Leagues",
            options=list(NHLE_MULTIPLIERS.keys()),
            default=["NHL"],
            key="league_filter",
            help="NHL only by default. Select additional leagues to include non-NHL seasons. Stats are multiplied by NHLe equivalency factors (Points, Goals, Assists only; GP kept raw)."
        )
        _non_nhl = [l for l in (st.session_state.league_filter or ['NHL']) if l != 'NHL']
        if _non_nhl:
            st.caption(f"NHLe-adjusted: {', '.join(_non_nhl)}")

# --- EXPANDER 2: View Options & Toggles ---
games_mode = st.session_state.x_axis_mode == "Games Played"
with st.expander("⚙️ View Options", expanded=True):
    st.markdown("<div id='master-toggles'></div>", unsafe_allow_html=True)
    c1, c2, c3 = st.columns([2, 3, 3])
    with c1:
        st.selectbox("Season Type", ["Regular", "Playoffs", "Both"], key="season_type")
    with c2:
        st.toggle("3-Season Rolling Avg", key="do_smooth")
        st.toggle("Project to 40", key="do_predict", disabled=games_mode)
    with c3:
        st.toggle("Era-Adjust", key="do_era")
        st.toggle("Cumulative", key="do_cumul_toggle", disabled=games_mode)
        if st.session_state.do_cumul_toggle and metric in RATE_STATS and not games_mode:
            st.caption(f"⚠️ Cumulative disabled — {metric} is a rate stat.")
        if games_mode:
            st.caption("ℹ️ Cumulative, Projection & Baseline unavailable in Games mode.")
        st.toggle("Show Baseline", key="do_base", disabled=games_mode)
        do_cumul = st.session_state.do_cumul_toggle and metric not in RATE_STATS and not games_mode

# --- ML ENGINE & DATA PROCESSING ---
hist_df = load_historical_data()
historical_baselines = build_historical_baselines(hist_df)
id_to_name_map = get_id_to_name_map(st.session_state.stat_category)
clone_details_map = get_clone_details_map(st.session_state.stat_category)

# GP is intentionally excluded from ML — it uses the dedicated durability decay curve below.
# KNN would fillna(0) for retired players, causing a false nosedive for young players.
ml_supported_metrics = ['Points', 'Goals', 'Assists', '+/-', 'PPG', 'PIM', 'Wins', 'Shutouts', 'Saves', 'Save %', 'GAA']
stat_caps = { "Points": 155, "Goals": 70, "Assists": 105, "+/-": 60, "GP": 82, "PPG": 1.9, "SH%": 25, "PIM": 150, "TOI": 28, "Save %": 93.5, "GAA": 1.8, "Wins": 45, "Shutouts": 10, "Saves": 2000 }
stat_floors = { "+/-": -60 }  # FIX #1: Floor cap for +/- to mirror ceiling

ml_clones_dict = {}
peak_info = {}  # key=base_name, value={x, y, age, season_year, pid}

if st.session_state.players:
    processed_dfs = []
    raw_dfs_cache = []

    for pid, name in st.session_state.players.items():
        raw_df, base_name, pos_code = get_player_raw_stats(pid, name)
        if raw_df.empty: continue

        is_goalie = raw_df['Saves'].sum() > 0 or raw_df['Wins'].sum() > 0
        if st.session_state.stat_category == "Skater" and is_goalie: continue
        if st.session_state.stat_category == "Goalie" and not is_goalie: continue

        raw_df['BaseName'] = base_name
        raw_dfs_cache.append(raw_df.copy())

        # --- League filter + NHLe conversion ---
        # Guard against empty multiselect; default back to NHL-only.
        _league_filter = st.session_state.get('league_filter', ['NHL']) or ['NHL']
        raw_df = raw_df[raw_df['League'].isin(_league_filter)].copy()
        if raw_df.empty: continue
        # Apply NHLe multipliers to Points, Goals, Assists for non-NHL rows.
        # GP kept raw per spec. All other stats (TOI, +/-, Shots) also kept raw.
        for _lg, _mult in NHLE_MULTIPLIERS.items():
            if _mult < 1.0:
                _mask = raw_df['League'] == _lg
                if _mask.any():
                    raw_df.loc[_mask, 'Points']  = raw_df.loc[_mask, 'Points']  * _mult
                    raw_df.loc[_mask, 'Goals']   = raw_df.loc[_mask, 'Goals']   * _mult
                    raw_df.loc[_mask, 'Assists']  = raw_df.loc[_mask, 'Assists']  * _mult

        if st.session_state.season_type != "Both":
            raw_df = raw_df[raw_df['GameType'] == st.session_state.season_type]
        if raw_df.empty: continue

        if st.session_state.do_era and st.session_state.stat_category == "Skater":
            # FIX #4: Adjust Goals and Assists independently, not just Points.
            # Previously only Points was adjusted, making Assists = Points - Goals
            # inconsistent after adjustment.
            # Era multipliers are derived from NHL GF/GP data; apply to NHL rows only
            # so non-NHL rows are not double-adjusted (NHLe already scales them).
            _nhl_mask = raw_df['League'] == 'NHL'
            if _nhl_mask.any():
                _era_mults = raw_df.loc[_nhl_mask, 'SeasonYear'].apply(get_era_multiplier)
                raw_df.loc[_nhl_mask, 'Points']  = raw_df.loc[_nhl_mask, 'Points']  * _era_mults.values
                raw_df.loc[_nhl_mask, 'Goals']   = raw_df.loc[_nhl_mask, 'Goals']   * _era_mults.values
                raw_df.loc[_nhl_mask, 'Assists']  = raw_df.loc[_nhl_mask, 'Assists']  * _era_mults.values

        if games_mode:
            # GAMES MODE: X = cumulative career GP, Y = cumulative totals (or career-avg rates).
            # Group by SeasonYear first to collapse Regular+Playoffs into one row per season
            # (mirrors what groupby('Age').sum() does in Age mode).
            age_per_season = raw_df.groupby('SeasonYear')['Age'].max()
            df = raw_df.groupby('SeasonYear').sum(numeric_only=True).reset_index()
            df['Age'] = df['SeasonYear'].map(age_per_season)
            df = df.sort_values('SeasonYear').reset_index(drop=True)

            # Capture cumulative numerators before overwriting columns
            cum_gp       = df['GP'].cumsum()
            cum_points   = df['Points'].cumsum()
            cum_goals    = df['Goals'].cumsum()
            cum_assists  = df['Assists'].cumsum()
            cum_wins     = df['Wins'].cumsum()
            cum_shutouts = df['Shutouts'].cumsum()
            cum_pim      = df['PIM'].cumsum()
            cum_saves    = df['Saves'].cumsum()
            cum_pm       = df['+/-'].cumsum()
            cum_toi      = df['TotalTOIMins'].cumsum()
            cum_wsv      = df['WeightedSV'].cumsum()
            cum_wgaa     = df['WeightedGAA'].cumsum()
            cum_shots    = df['Shots'].cumsum()

            df['CumGP']    = cum_gp
            df['Points']   = cum_points
            df['Goals']    = cum_goals
            df['Assists']  = cum_assists
            df['Wins']     = cum_wins
            df['Shutouts'] = cum_shutouts
            df['PIM']      = cum_pim
            df['Saves']    = cum_saves
            df['+/-']      = cum_pm
            df['GP']       = cum_gp  # career GP to date

            df['PPG']    = cum_points / cum_gp
            df['TOI']    = cum_toi / cum_gp
            df['SH%']    = (cum_goals / cum_shots.replace(0, float('nan')) * 100).fillna(0)
            df['Save %'] = cum_wsv / cum_gp
            df['GAA']    = cum_wgaa / cum_gp
        else:
            # FIX #2: Preserve SeasonYear as max per age (not sum).
            # Without this, "Both" mode sums Regular+Playoff SeasonYear into garbage
            # values (e.g., 4050 instead of 2025), breaking mid-season pacing detection.
            season_year_max = raw_df.groupby('Age')['SeasonYear'].max()
            df = raw_df.groupby('Age').sum(numeric_only=True).reset_index()
            df['SeasonYear'] = df['Age'].map(season_year_max)

            df['PPG'] = df['Points'] / df['GP']
            df['TOI'] = df['TotalTOIMins'] / df['GP']
            df['SH%'] = (df['Goals'] / df['Shots'] * 100).fillna(0)
            df['Save %'] = df['WeightedSV'] / df['GP']
            df['GAA'] = df['WeightedGAA'] / df['GP']

        df['BaseName'] = base_name
        df['Player'] = base_name

        if games_mode:
            # Anchor every player's line at career game 0 so all players share the
            # same x=0 origin. Without this, each line starts at the end of the
            # player's first season (e.g. x=50 for Crosby), making it impossible to
            # compare "game 100 of McDavid vs game 100 of Crosby" visually.
            _zero = {col: 0 for col in df.columns}
            _zero.update({
                'CumGP': 0, 'GP': 0,
                'Age': int(df['Age'].iloc[0]) if not df.empty else 18,
                'Player': base_name, 'BaseName': base_name,
            })
            # Rate stats have no meaningful value at game 0 — leave as NaN so
            # Plotly doesn't draw a false zero anchor on PPG / GAA / etc.
            for _rs in ('PPG', 'TOI', 'SH%', 'Save %', 'GAA'):
                if _rs in _zero:
                    _zero[_rs] = float('nan')
            df = pd.concat([pd.DataFrame([_zero]), df], ignore_index=True)

        # PEAK DETECTION: find the best season before cumsum/smoothing.
        # Games mode counting stats are already cumulative at this point — use diff()
        # to recover per-season increments for an apples-to-apples comparison.
        _peak_x = _peak_age = _peak_sy = None
        try:
            if metric in df.columns and not df[metric].dropna().empty:
                if games_mode and metric not in RATE_STATS:
                    _incremental = df[metric].diff().fillna(df[metric])
                    _pidx = _incremental.replace(0, float('nan')).idxmin() if metric == 'GAA' else _incremental.idxmax()
                else:
                    _series = df[metric].replace(0, float('nan')) if metric == 'GAA' else df[metric]
                    _pidx = _series.idxmin() if metric == 'GAA' else _series.idxmax()
                if pd.notna(_pidx):
                    _pr = df.loc[_pidx]
                    _peak_age = int(_pr['Age'])
                    _peak_sy = int(_pr['SeasonYear']) if 'SeasonYear' in df.columns else None
                    _peak_x = float(_pr['CumGP']) if games_mode else float(_peak_age)
        except Exception:
            pass

        if not games_mode and st.session_state.do_predict:
            max_age = df['Age'].max()
            if max_age < 40:
                # Use the player's entire career for KNN matching — more information
                # means better clone matches. tail(3) was too narrow: a player with an
                # unusual last 3 years (injury, lockout, line change) would match to
                # players with similar recent blips, not similar career shapes.
                career_df = df.copy()
                career_paced = career_df[metric].copy()

                # FIX #3: Use dynamic CURRENT_SEASON_YEAR instead of hardcoded 2024.
                # Mid-season pacing still applies only to the last (current) season.
                if (st.session_state.season_type != "Playoffs"
                        and len(career_df) > 0
                        and career_df.iloc[-1]['SeasonYear'] >= CURRENT_SEASON_YEAR
                        and career_df.iloc[-1]['GP'] < 82
                        and career_df.iloc[-1]['GP'] > 0):
                    pace = 82.0 / career_df.iloc[-1]['GP']
                    if metric in ['Points', 'Goals', 'Assists', 'Wins', 'Shutouts', 'Saves', '+/-', 'PIM']:
                        career_paced.iloc[-1] *= pace

                match_ages = career_df['Age'].tolist()
                match_vals = career_paced.tolist()
                current_val = float(df.loc[df['Age'] == max_age, metric].values[0])

                use_ml = not hist_df.empty and metric in ml_supported_metrics
                proj_data = []

                if use_ml:
                    # Era-adjust hist_df to match the live player's adjustment state.
                    knn_hist = apply_era_to_hist(hist_df, st.session_state.do_era)
                    # Strict Position Filtering
                    h_df = knn_hist[knn_hist['Position'] == pos_code]
                    if len(h_df['PlayerID'].unique()) < 10:
                        cat = 'G' if st.session_state.stat_category == 'Goalie' else 'S'
                        h_df = knn_hist[knn_hist['Position'] == cat] if cat == 'G' else knn_hist[knn_hist['Position'] != 'G']

                    # FIX #1: Use mean for rate stats, sum for counting stats.
                    # Summing PPG / Save% / GAA across duplicate ages produces garbage numbers.
                    agg_fn = 'mean' if metric in RATE_STATS else 'sum'
                    pivot = h_df.pivot_table(index='PlayerID', columns='Age', values=metric, aggfunc=agg_fn)

                    # Guard against young players whose ages don't exist as historical columns.
                    valid_ages = [a for a in match_ages if a in pivot.columns]
                    if not valid_ages:
                        use_ml = False
                    else:
                        # Partial career matching: require at least 1/3 of valid ages (min 2).
                        # Old strict dropna excluded most elite players who didn't start at 18
                        # or had gaps — forcing bad matches against anyone who happened to play
                        # those exact ages (e.g., Frank Mahovlich, Rod Seiling for McDavid).
                        min_shared = max(2, len(valid_ages) // 3)
                        valid_hist = pivot[pivot[valid_ages].notna().sum(axis=1) >= min_shared]
                        valid_match_vals = [v for a, v in zip(match_ages, match_vals) if a in valid_ages]

                        if len(valid_hist) > 0:
                            # Tier pre-filter: for counting stats, only match against players
                            # whose career peak is at least 50% of the current player's peak.
                            # Prevents elite players (McDavid, Crosby) from matching "no-names"
                            # who happened to have a similar early-career trajectory fragment.
                            # Falls back to looser tiers if not enough candidates remain.
                            current_peak = max(match_vals) if match_vals else 0
                            if (current_peak > 0 and metric not in RATE_STATS
                                    and metric not in ['+/-', 'GP']):
                                hist_peaks = valid_hist.max(axis=1)
                                for tier_pct in [0.50, 0.30, 0.15]:
                                    tier_mask = hist_peaks >= current_peak * tier_pct
                                    if tier_mask.sum() >= 10:
                                        valid_hist = valid_hist[tier_mask]
                                        break

                            # Vectorized L1 distance across all shared career ages.
                            # sum(axis=1) uses skipna=True, so NaN ages (where clone has
                            # no data) are simply ignored — no special handling needed.
                            dist = valid_hist[valid_ages].sub(valid_match_vals).abs().sum(axis=1)
                            # Normalize by number of shared ages so a clone with 3 perfect-
                            # match ages isn't unfairly penalized vs. one with 10 near-matches.
                            n_shared = valid_hist[valid_ages].notna().sum(axis=1).clip(lower=1)
                            dist = dist / n_shared

                            top_ids = dist.nsmallest(10).index

                            # FIX #5: Pre-build a position lookup dict once — O(1) per clone.
                            # Old code: h_df[h_df['PlayerID'] == c_id] was a full mask scan
                            # repeated 10 times per player per render cycle.
                            pos_lookup = (h_df.drop_duplicates('PlayerID')
                                             .set_index('PlayerID')['Position']
                                             .to_dict())

                            clone_names = []
                            for c_id in top_ids:
                                detail = clone_details_map.get(int(c_id))
                                if detail:
                                    clone_names.append(detail.copy())
                                else:
                                    c_name = id_to_name_map.get(int(c_id), f"Unknown (ID {c_id})")
                                    if st.session_state.stat_category == "Skater":
                                        clone_names.append({'name': c_name, 'team': '—', 'gp': 0, 'pts': 0, 'g': 0, 'a': 0, 'pm': 0})
                                    else:
                                        clone_names.append({'name': c_name, 'team': '—', 'gp': 0, 'w': 0, 'sv': 0, 'so': 0})
                            ml_clones_dict[base_name] = clone_names

                            last_avg = valid_hist.loc[top_ids, valid_ages[-1]].dropna().mean() if valid_ages[-1] in valid_hist.columns else current_val
                            if pd.isna(last_avg) or last_avg == 0: last_avg = current_val if current_val != 0 else 1.0

                            # Ring-buffer of the last 3 meaningful clone averages for
                            # trend extrapolation when clones run out of data at old ages.
                            recent_clone_avgs = []

                            for age in range(int(max_age) + 1, 41):
                                if age in pivot.columns:
                                    clone_vals = pivot.loc[top_ids, age].dropna()
                                    if len(clone_vals) > 0:
                                        # Blend raw clone mean with previous year's average
                                        # (70/30) to dampen noise from small late-career pools.
                                        # Without this, a single injury year in 3 remaining
                                        # clones causes a whipsaw spike or drop.
                                        raw_avg = clone_vals.mean()
                                        next_avg = raw_avg * 0.70 + last_avg * 0.30
                                        recent_clone_avgs.append(next_avg)
                                        if len(recent_clone_avgs) > 3:
                                            recent_clone_avgs.pop(0)
                                    elif len(recent_clone_avgs) >= 2:
                                        # No clone data — extrapolate the percentage decline
                                        # rate observed in the last known clone averages.
                                        # This keeps projection data-driven instead of snapping
                                        # to zero when the last elite clone retires.
                                        pct_per_step = (recent_clone_avgs[-1] / max(recent_clone_avgs[0], 1e-6)) - 1
                                        pct_per_step /= max(1, len(recent_clone_avgs) - 1)
                                        pct_per_step = max(-0.08, min(0.0, pct_per_step))
                                        next_avg = recent_clone_avgs[-1] * (1 + pct_per_step)
                                        recent_clone_avgs.append(next_avg)
                                        if len(recent_clone_avgs) > 3:
                                            recent_clone_avgs.pop(0)
                                    elif len(recent_clone_avgs) == 1:
                                        next_avg = recent_clone_avgs[0] * 0.92
                                        recent_clone_avgs.append(next_avg)
                                    else:
                                        next_avg = 0
                                else:
                                    next_avg = 0

                                if pd.isna(next_avg): next_avg = 0

                                if metric in ['+/-', 'GAA', 'Save %']:
                                    current_val += (next_avg - last_avg)
                                else:
                                    if last_avg > 0:
                                        pct_change = (next_avg - last_avg) / last_avg
                                        # Tighter clamp than the old ±0.5: max 12% annual
                                        # decline prevents unrealistic single-year cliff drops
                                        # for elite players who age more gracefully than average.
                                        pct_change = max(min(pct_change, 0.25), -0.12)
                                        current_val += (current_val * pct_change)
                                    else:
                                        current_val += (next_avg - last_avg)

                                if metric != "+/-": current_val = max(0, current_val)

                                if metric in stat_caps:
                                    cap = stat_caps[metric]
                                    # NOTE: GAA cap is intentionally a floor (1.8), not a ceiling —
                                    # no goalie can project below a 1.8 GAA long-term.
                                    if metric == "GP" and st.session_state.stat_category == "Goalie": cap = 65
                                    current_val = max(current_val, cap) if "GAA" in metric else min(current_val, cap)
                                # FIX #1: Apply floor caps (e.g., +/- cannot dive below -60)
                                if metric in stat_floors:
                                    current_val = max(current_val, stat_floors[metric])

                                proj_data.append({"Age": age, metric: current_val, "Player": base_name, "BaseName": base_name})
                                last_avg = next_avg
                        else:
                            use_ml = False

                if not use_ml:
                    slope = (match_vals[-1] - match_vals[0]) / max(1, len(career_df) - 1) if len(career_df) >= 2 else match_vals[-1] * 0.05
                    for age in range(int(max_age) + 1, 41):
                        if metric == "GP":
                            gp_cap = 82 if st.session_state.stat_category == "Skater" else 65
                            # Redesigned durability curve based on real long-career NHL data.
                            # We are projecting players who MAKE IT to 40 — they are durable.
                            # Real reference: Jagr ~68 GP at 40, Lidstrom ~73 GP at 40, Thornton ~60 GP at 39.
                            # Old code used 0.92 and 0.82 compounding = cliff (71 GP -> 25 GP by 40).
                            # New model: plateau through prime, then two gentle decay phases.
                            if age <= 28:
                                current_val = min(gp_cap, current_val + 0.8)   # soft growth to prime
                            elif age <= 33:
                                current_val = min(gp_cap, current_val * 0.990) # ~1%/yr — prime plateau
                            elif age <= 37:
                                current_val *= 0.965                            # ~3.5%/yr — gradual decline
                            else:
                                current_val *= 0.930                            # ~7%/yr — late career
                        elif age <= 26:
                            if age == int(max_age) + 1 and slope > 0:
                                current_val = (current_val + (match_vals[-1] + slope)) / 2
                            elif slope > 0:
                                current_val += slope * (0.4 ** (age - max_age))
                            else:
                                current_val += current_val * 0.03
                        else:
                            if "GAA" in metric: current_val *= 1.05
                            elif metric == "Save %": current_val -= 0.005
                            elif "PIM" in metric: current_val *= 0.90
                            elif metric in ["TOI", "SH%", "Saves"]: current_val *= 0.95
                            elif metric == "+/-": current_val -= 2
                            else:
                                if age <= 28: current_val *= 0.98
                                elif age <= 31: current_val *= 0.92
                                elif age <= 35: current_val *= 0.85
                                else: current_val *= 0.80

                        if metric in stat_caps:
                            cap = stat_caps[metric]
                            if metric == "GP" and st.session_state.stat_category == "Goalie": cap = 65
                            current_val = max(current_val, cap) if "GAA" in metric else min(current_val, cap)
                        # FIX #1: Apply floor caps (e.g., +/- cannot dive below -60)
                        if metric in stat_floors:
                            current_val = max(current_val, stat_floors[metric])
                        if metric != "+/-": current_val = max(0, current_val)

                        proj_data.append({"Age": age, metric: current_val, "Player": base_name, "BaseName": base_name})

                df = pd.concat([df, pd.DataFrame(proj_data)], ignore_index=True)

        if do_cumul:
            # do_cumul is already False for rate stats and always False in games_mode.
            df[metric] = df[metric].cumsum()

        if st.session_state.do_smooth:
            df[metric] = df[metric].rolling(window=3, min_periods=1).mean()

        if not games_mode and st.session_state.do_predict and df['Age'].max() > max_age:
            real_part = df[df['Age'] <= max_age].copy()
            proj_part = df[df['Age'] >= max_age].copy()
            proj_part['Player'] = f"{base_name} (Proj)"
            final_player_df = pd.concat([real_part, proj_part])
        else:
            final_player_df = df.copy()

        # Look up the star's chart y-value at the peak position (post-smoothing/cumsum).
        if _peak_x is not None and _peak_sy is not None:
            x_col_lk = 'CumGP' if games_mode else 'Age'
            real_only = final_player_df[~final_player_df['Player'].str.contains(r'\(Proj\)', na=False)]
            match = real_only[real_only[x_col_lk] == _peak_x]
            if not match.empty and metric in match.columns:
                # raw_peak_val: pre-smoothing/pre-cumsum value for accurate season ranking.
                raw_pk = df[df['Age'] == _peak_age][metric]
                raw_peak_val = float(raw_pk.iloc[0]) if not raw_pk.empty else float(match[metric].iloc[0])
                peak_info[base_name] = {
                    'x': _peak_x,
                    'y': float(match[metric].iloc[0]),
                    'raw_peak_val': raw_peak_val,
                    'age': _peak_age,
                    'season_year': _peak_sy,
                    'pid': pid,
                }

        processed_dfs.append(final_player_df)

    if processed_dfs:
        final_df = pd.concat(processed_dfs, ignore_index=True)

        if st.session_state.do_base and not games_mode:
            base_df = historical_baselines.get(st.session_state.stat_category)
            if base_df is not None and not base_df.empty:
                base_data = []
                cumul_val = 0
                for age in range(18, 41):
                    if age in base_df.index and metric in base_df.columns:
                        val = base_df.loc[age, metric]
                        if pd.isna(val): val = 0
                    else:
                        val = 0

                    if do_cumul and metric in ['Points', 'Goals', 'Assists', 'Wins', 'Shutouts', 'GP', 'PIM', 'Saves', '+/-']:
                        cumul_val += val
                        val = cumul_val

                    role_name = "NHL 75th Percentile Baseline"
                    base_data.append({"Age": age, metric: val, "Player": role_name, "BaseName": "Baseline"})
                final_df = pd.concat([final_df, pd.DataFrame(base_data)], ignore_index=True)

        x_col = "CumGP" if games_mode else "Age"
        custom_cols = ["BaseName", "Player", "Age"] if games_mode else ["BaseName", "Player"]
        fig = px.line(final_df, x=x_col, y=metric, color="Player", custom_data=custom_cols, markers=True, template="plotly_dark", line_shape="spline" if st.session_state.do_smooth else "linear")

        for trace in fig.data:
            if "(Proj)" in trace.name:
                trace.line.dash = 'dot'
                trace.line.color = 'gray'
                trace.marker.symbol = 'circle-open'
            elif "Baseline" in trace.name:
                trace.line.dash = 'dash'
                trace.line.color = 'rgba(255, 255, 255, 0.4)'
                trace.marker.size = 1

        fig.update_layout(
            uirevision='constant',
            margin=dict(l=0, r=0, t=40, b=80),
            height=600,
            font=dict(size=16),
            hoverlabel=dict(font_size=18, font_family="Arial", bgcolor="#1E1E1E"),
            legend=dict(title=None, orientation="h", yanchor="top", y=-0.15, xanchor="center", x=0.5),
            clickmode='event+select'
        )

        _val_fmt = ".2f" if metric in RATE_STATS else ".0f"
        if games_mode:
            fig.update_traces(connectgaps=True, line=dict(width=4, shape='spline', smoothing=0.6), marker=dict(size=8), hovertemplate=f"<b>%{{customdata[1]}}</b><br>Career Game %{{x}}<br>Value: %{{y:{_val_fmt}}}<extra></extra>")
            fig.update_xaxes(title_text="Games Played", title_font=dict(size=25, family='Arial Black'), tickfont=dict(size=18, family='Arial Black'))
        else:
            fig.update_traces(connectgaps=True, line=dict(width=4, shape='spline', smoothing=0.6), marker=dict(size=8), hovertemplate=f"<b>%{{customdata[1]}}</b><br>Age %{{x}}<br>Value: %{{y:{_val_fmt}}}<extra></extra>")
            fig.update_xaxes(dtick=1, title_font=dict(size=25, family='Arial Black'), tickfont=dict(size=18, family='Arial Black'))

        fig.update_yaxes(title_font=dict(size=25, family='Arial Black'), tickfont=dict(size=18, family='Arial Black'))

        if metric in ["Save %", "SH%"]:
            fig.update_yaxes(ticksuffix="%")
            x_label = "Career Game" if games_mode else "Age"
            fig.update_traces(hovertemplate=f"<b>%{{customdata[1]}}</b><br>{x_label} %{{x}}<br>%{{y:.1f}}%<extra></extra>")

        safe_roster = roster_player if 'roster_player' in locals() else ""
        chart_key = f"chart_{hash(str(st.session_state.players))}_{metric}_{st.session_state.do_predict}_{st.session_state.do_smooth}_{search_term}_{top_selected}_{team_abbr}_{safe_roster}_{st.session_state.x_axis_mode}"
        event = st.plotly_chart(fig, use_container_width=True, on_select="rerun", selection_mode="points", key=chart_key)

        if event and event.selection.get("points"):
            point = event.selection["points"][0]
            cd = point.get("customdata", [])
            age_for_detail = int(cd[2]) if games_mode else point["x"]
            show_season_details(cd[1], age_for_detail, raw_dfs_cache, metric, point["y"], do_cumul, final_df, st.session_state.season_type, ml_clones_dict, historical_baselines)

    else:
        st.info("No data found for the selected parameters.")

st.markdown("---")
st.markdown("<p style='text-align: center; color: gray; font-size: 14px;'>Created by Iksperial. <br><em>Data is the only religion that strictly punishes you for ignoring it.</em></p>", unsafe_allow_html=True)
