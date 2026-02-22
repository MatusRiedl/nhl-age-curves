import streamlit as st
import requests
import pandas as pd
import plotly.express as px

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

if 'players' not in st.session_state: st.session_state.players = {} 
if 'stat_category' not in st.session_state: st.session_state.stat_category = "Skater"

def get_era_multiplier(year):
    if 1980 <= year <= 1992: return 0.80  
    if 1997 <= year <= 2004: return 1.15  
    if 2005 <= year <= 2017: return 1.05  
    return 1.0 

@st.cache_data
def get_top_50():
    try:
        url = "https://records.nhl.com/site/api/skater-career-scoring-regular-season?sort=points&dir=DESC&limit=50"
        res = requests.get(url, timeout=5).json()
        players = {}
        for i, p in enumerate(res.get('data', [])):
            name = f"{i+1}. {p.get('firstName', '')} {p.get('lastName', '')}".strip()
            if name and p.get('playerId'):
                players[name] = int(p['playerId'])
        if players: return players
    except:
        pass
    return { "1. Wayne Gretzky": 8447400, "2. Jaromir Jagr": 8448208, "3. Sidney Crosby": 8471675, "4. Alexander Ovechkin": 8471214 }

@st.cache_data
def search_player(query):
    if not query: return []
    try: return requests.get(SEARCH_URL, params={"culture": "en-us", "limit": 10, "q": query}).json()
    except: return []

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
    except: return {}

@st.cache_data
def get_player_raw_stats(player_id, base_name):
    try:
        res = requests.get(STATS_URL.format(player_id)).json()
        birth_date = str(res.get('birthDate', '2000'))
        birth_year = int(birth_date[:4]) if len(birth_date) >= 4 else 2000
        data = []
        for s in res.get('seasonTotals', []):
            league = str(s.get('leagueAbbrev', '')).strip().upper()
            game_type = str(s.get('gameTypeId', ''))
            if league == 'NHL' and game_type in ['2', '3']:
                season_str = str(s.get('season', ''))
                season_year = int(season_str[:4]) if len(season_str) >= 4 else 2000
                age = season_year - birth_year
                gp = max(s.get('gamesPlayed', 1), 1)
                toi_str = str(s.get('avgToi', '0:00'))
                try:
                    parts = toi_str.split(':')
                    toi_val = int(parts[0]) + int(parts[1])/60.0 if len(parts) == 2 else 0
                except: toi_val = 0
                
                data.append({
                    "Age": age, "SeasonYear": season_year, "GameType": "Regular" if game_type == '2' else "Playoffs",
                    "GP": gp, "Points": s.get('points', 0), "Goals": s.get('goals', 0), "Assists": s.get('assists', 0),
                    "PIM": s.get('pim', 0) or s.get('penaltyMinutes', 0), "+/-": s.get('plusMinus', 0),
                    "Shots": s.get('shots', 0), "TotalTOIMins": toi_val * gp, "Wins": s.get('wins', 0),
                    "Shutouts": s.get('shutouts', 0), "Saves": s.get('saves', s.get('shotsAgainst', 0) - s.get('goalsAgainst', 0)),
                    "WeightedSV": float(s.get('savePctg', 0.0)) * 100 * gp, "WeightedGAA": float(s.get('goalsAgainstAvg', 0.0)) * gp
                })
        return pd.DataFrame(data), base_name
    except:
        return pd.DataFrame(), base_name

def get_baseline_value(metric, age):
    pts_curve = {18: 20, 19: 35, 20: 45, 21: 52, 22: 58, 23: 62, 24: 65, 25: 65, 26: 63, 27: 60, 28: 56, 29: 52, 30: 48, 31: 42, 32: 36, 33: 30, 34: 24, 35: 18, 36: 12, 37: 8, 38: 4, 39: 2, 40: 0}
    gp_skater = {18: 40, 19: 60, 20: 75, 21: 80, 22: 80, 23: 80, 24: 80, 25: 80, 26: 80, 27: 80, 28: 78, 29: 78, 30: 75, 31: 72, 32: 68, 33: 65, 34: 60, 35: 55, 36: 50, 37: 40, 38: 30, 39: 20, 40: 10}
    gp_goalie = {18: 5, 19: 15, 20: 25, 21: 35, 22: 45, 23: 50, 24: 55, 25: 55, 26: 55, 27: 55, 28: 55, 29: 52, 30: 50, 31: 48, 32: 45, 33: 40, 34: 35, 35: 30, 36: 25, 37: 20, 38: 15, 39: 10, 40: 5}

    pts = pts_curve.get(age, 0)
    gps = gp_skater.get(age, 1)
    gpg = gp_goalie.get(age, 1)

    if metric == "Points": return pts
    if metric == "Goals": return pts * 0.35
    if metric == "Assists": return pts * 0.65
    if metric == "+/-": return (pts * 0.2) - 8 
    if metric == "GP": return gps if st.session_state.stat_category == "Skater" else gpg
    if metric == "PPG": return pts / gps if gps > 0 else 0
    if metric == "SH%": return 11.5 if age <= 32 else max(8.0, 11.5 - (age-32)*0.5)
    if metric == "PIM": return gps * 0.5
    if metric == "TOI": return 18.0 if age in range(21, 31) else max(10.0, 18.0 - abs(25-age)*0.3)
    if metric == "Wins": return gpg * 0.55
    if metric == "Saves": return gpg * 28
    if metric == "Shutouts": return gpg * 0.08
    if metric == "Save %": return 91.5 if age <= 32 else max(88.0, 91.5 - (age-32)*0.3)
    if metric == "GAA": return 2.50 if age <= 32 else min(3.50, 2.50 + (age-32)*0.1)
    return 0

@st.cache_data(ttl=3600)
def fetch_all_time_records(category, s_type):
    try:
        if category == "Skater":
            reg_url = "https://records.nhl.com/site/api/skater-career-scoring-regular-season"
            ply_url = "https://records.nhl.com/site/api/skater-career-scoring-playoff"
        else:
            reg_url = "https://records.nhl.com/site/api/goalie-career-stats"
            ply_url = "https://records.nhl.com/site/api/goalie-career-playoff-stats"
            
        reg_data = requests.get(reg_url, timeout=5).json().get('data', [])
        if s_type == "Regular": return reg_data
        
        ply_data = requests.get(ply_url, timeout=5).json().get('data', [])
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
    except: return []

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
def show_season_details(player_name, age, raw_dfs_list, metric, val, is_cumul, full_df, s_type):
    clean_name = player_name.replace(" (Proj)", "")
    st.markdown(f"### {player_name} at Age {age}")
    
    for df in raw_dfs_list:
        if not df.empty and 'BaseName' in df.columns and df['BaseName'].iloc[0] == clean_name:
            career_gp = int(df['GP'].sum())
            if st.session_state.stat_category == "Skater":
                career_pts, career_g, career_a, career_pm = int(df['Points'].sum()), int(df['Goals'].sum()), int(df['Assists'].sum()), int(df['+/-'].sum())
                st.info(f"**Career Totals (Reg+Playoffs):** {career_gp} GP | {career_pts} Pts | {career_g} G | {career_a} A | {career_pm} +/-")
            else:
                career_w, career_so, career_sv = int(df['Wins'].sum()), int(df['Shutouts'].sum()), int(df['Saves'].sum())
                st.info(f"**Career Totals (Reg+Playoffs):** {career_gp} GP | {career_w} W | {career_sv} Saves | {career_so} SO")
            break

    found = False
    for df in raw_dfs_list:
        if not df.empty and 'BaseName' in df.columns and df['BaseName'].iloc[0] == clean_name:
            season_data = df[df['Age'] == age]
            if not season_data.empty:
                cols_to_show = ['SeasonYear', 'GameType', 'GP', 'Points', 'Goals', 'Assists', '+/-'] if st.session_state.stat_category == "Skater" else ['SeasonYear', 'GameType', 'GP', 'Wins', 'Saves', 'Shutouts']
                display_df = season_data[cols_to_show].copy()
                for col in display_df.columns:
                    if col not in ['SeasonYear', 'GameType']: display_df[col] = display_df[col].astype(int)
                st.dataframe(display_df, hide_index=True, use_container_width=True)
                found = True
                break
    
    if not found:
        st.write("Detailed game-by-game data not available for this specific projected point.")
    
    if "(Proj)" in player_name:
        counting_stats = ['Points', 'Goals', 'Assists', 'Wins', 'Shutouts', 'GP', 'PIM', 'Saves', '+/-']
        if metric in counting_stats:
            st.markdown("---")
            with st.spinner("Calculating Career Total & Fetching NHL Records..."):
                player_data = full_df[full_df['BaseName'] == clean_name]
                player_data = player_data[player_data['Age'] <= age].drop_duplicates(subset=['Age'], keep='last')
                
                career_total = val if is_cumul else player_data[metric].sum()
                rank = get_all_time_rank(st.session_state.stat_category, s_type, metric, career_total)
                
                if rank:
                    st.success(f"🏆 **Career Projection at Age {age}:** Estimated **{int(career_total)}** career {metric}. This projects to rank **#{rank} All-Time** in NHL history.")

# --- SIDEBAR: Player Management ---
with st.sidebar:
    st.subheader("Global Search")
    # Tying the search term into a variable to fix the zombie pop-up later
    search_term = st.text_input("Search for any player:", placeholder="e.g., Crosby, Brodeur", label_visibility="collapsed")
    opts = {}
    if search_term:
        results = search_player(search_term)
        if results:
            for p in results:
                tm = p.get('teamAbbrev')
                label = f"[{tm}] {p['name']}" if tm else p['name']
                opts[label] = int(p['playerId'])
            
    selected = st.selectbox("Select Best Match:", list(opts.keys()) if opts else ["Waiting for search..."], disabled=not bool(opts))
    
    st.markdown("<div class='blue-btn-anchor'></div>", unsafe_allow_html=True)
    if st.button("Add to Chart", use_container_width=True, disabled=not bool(opts)):
        st.session_state.players[opts[selected]] = selected.split("] ")[-1] if "]" in selected else selected
        st.rerun()

    st.markdown("---")
    
    st.subheader("Quick Adds")
    top_50_dict = get_top_50()
    top_selected = st.selectbox("Top 50 All-Time", list(top_50_dict.keys()))
    
    st.markdown("<div class='blue-btn-anchor'></div>", unsafe_allow_html=True)
    if st.button("Add Legend", use_container_width=True):
        st.session_state.players[top_50_dict[top_selected]] = top_selected.split(". ")[-1]
        st.rerun()

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
                st.rerun()
                
    st.markdown("---")
    st.subheader("Players on Board")
    if st.session_state.players:
        for pid, name in list(st.session_state.players.items()):
            c_name, c_btn = st.columns([5, 1], vertical_alignment="center", gap="small")
            with c_name: st.markdown(f"<div class='player-name'>{name}</div>", unsafe_allow_html=True)
            with c_btn:
                if st.button("✖", key=f"drop_{pid}", type="primary"):
                    del st.session_state.players[pid]
                    st.rerun()
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

c_category, c_metric = st.columns([2.5, 7.5], vertical_alignment="center")

with c_category:
    st.session_state.stat_category = st.radio("Category:", ["Skater", "Goalie"], horizontal=True)

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

st.markdown("<div style='margin-top: 10px;'></div>", unsafe_allow_html=True)
st.markdown("<div id='master-toggles'></div>", unsafe_allow_html=True)
c1, c2 = st.columns(2)
with c1: 
    season_type = st.selectbox("Season", ["Regular", "Playoffs", "Both"], label_visibility="collapsed")
    do_smooth = st.toggle("Data Smoothing")
    do_predict = st.toggle("Project to 40")
with c2: 
    do_era = st.toggle("Era-Adjust")
    do_cumul = st.toggle("Cumulative")
    do_base = st.toggle("Show Baseline")

if st.session_state.players:
    processed_dfs = []
    raw_dfs_cache = []
    
    stat_caps = { "Points": 155, "Goals": 70, "Assists": 105, "+/-": 60, "GP": 82, "PPG": 1.9, "SH%": 25, "PIM": 150, "TOI": 28, "Save %": 93.5, "GAA": 1.8, "Wins": 45, "Shutouts": 10, "Saves": 2000 }
    
    for pid, name in st.session_state.players.items():
        raw_df, base_name = get_player_raw_stats(pid, name)
        if raw_df.empty: continue
        
        is_goalie = raw_df['Saves'].sum() > 0 or raw_df['Wins'].sum() > 0
        if st.session_state.stat_category == "Skater" and is_goalie: continue
        if st.session_state.stat_category == "Goalie" and not is_goalie: continue
        
        raw_df['BaseName'] = base_name
        raw_dfs_cache.append(raw_df.copy())
        
        if season_type != "Both":
            raw_df = raw_df[raw_df['GameType'] == season_type]
        if raw_df.empty: continue
        
        if do_era and st.session_state.stat_category == "Skater":
            raw_df['EraMult'] = raw_df['SeasonYear'].apply(get_era_multiplier)
            raw_df['Points'] = raw_df['Points'] * raw_df['EraMult']

        df = raw_df.groupby('Age').sum(numeric_only=True).reset_index()
        
        df['PPG'] = df['Points'] / df['GP']
        df['TOI'] = df['TotalTOIMins'] / df['GP']
        df['SH%'] = (df['Goals'] / df['Shots'] * 100).fillna(0)
        df['Save %'] = df['WeightedSV'] / df['GP']
        df['GAA'] = df['WeightedGAA'] / df['GP']
        
        df['BaseName'] = base_name
        df['Player'] = base_name 
        
        if do_predict:
            max_age = df['Age'].max()
            if max_age < 40:
                recent = df.tail(3)
                
                paced_recent = recent[metric].copy()
                if season_type != "Playoffs" and len(recent) > 0 and recent.iloc[-1]['SeasonYear'] >= 2024 and recent.iloc[-1]['GP'] < 82 and recent.iloc[-1]['GP'] > 0:
                    pace = 82.0 / recent.iloc[-1]['GP']
                    if metric in ['Points', 'Goals', 'Assists', 'Wins', 'Shutouts', 'Saves', '+/-', 'PIM']:
                        paced_recent.iloc[-1] *= pace
                
                slope = (paced_recent.iloc[-1] - paced_recent.iloc[0]) / max(1, len(recent) - 1) if len(recent) >= 2 else paced_recent.iloc[-1] * 0.05
                
                proj_name = f"{base_name} (Proj)"
                current_val = float(df.loc[df['Age'] == max_age, metric].values[0])
                
                proj_data = []
                for age in range(int(max_age) + 1, 41):
                    # Dedicated Durability Curve for GP
                    if metric == "GP":
                        gp_cap = 82 if st.session_state.stat_category == "Skater" else 65
                        if age <= 28:
                            current_val = min(gp_cap, current_val + 1)
                        elif age <= 32:
                            current_val *= 0.98
                        elif age <= 36:
                            current_val *= 0.92
                        else:
                            current_val *= 0.82
                    
                    # Momentum Curve for all other stats
                    elif age <= 26:
                        if age == int(max_age) + 1 and slope > 0:
                            current_val = (current_val + (paced_recent.iloc[-1] + slope)) / 2
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
                    if metric != "+/-": current_val = max(0, current_val)
                    
                    proj_data.append({"Age": age, metric: current_val, "Player": base_name, "BaseName": base_name})
                
                df = pd.concat([df, pd.DataFrame(proj_data)], ignore_index=True)

        if do_cumul:
            if metric in ['Points', 'Goals', 'Assists', 'Wins', 'Shutouts', 'GP', 'PIM', 'Saves', '+/-']:
                df[metric] = df[metric].cumsum()
            else:
                st.warning(f"Cumulative tracking disabled: Mathematically invalid for rate stat ({metric}).")

        if do_smooth:
            df[metric] = df[metric].rolling(window=3, min_periods=1).mean()

        if do_predict and df['Age'].max() > max_age:
            real_part = df[df['Age'] <= max_age].copy()
            proj_part = df[df['Age'] >= max_age].copy()
            proj_part['Player'] = f"{base_name} (Proj)"
            final_player_df = pd.concat([real_part, proj_part])
        else:
            final_player_df = df.copy()

        processed_dfs.append(final_player_df)

    if processed_dfs:
        final_df = pd.concat(processed_dfs, ignore_index=True)
        
        if do_base:
            base_data = []
            cumul_val = 0
            for age in range(18, 41):
                val = get_baseline_value(metric, age)
                if do_cumul and metric in ['Points', 'Goals', 'Assists', 'Wins', 'Shutouts', 'GP', 'PIM', 'Saves', '+/-']:
                    cumul_val += val
                    val = cumul_val
                role_name = "NHL Top 6 Baseline" if st.session_state.stat_category == "Skater" else "NHL Starter Baseline"
                base_data.append({"Age": age, metric: val, "Player": role_name, "BaseName": "Baseline"})
            final_df = pd.concat([final_df, pd.DataFrame(base_data)], ignore_index=True)

        fig = px.line(final_df, x="Age", y=metric, color="Player", custom_data=["BaseName", "Player"], markers=True, template="plotly_dark", line_shape="spline" if do_smooth else "linear")
        
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
        
        fig.update_traces(connectgaps=True, line=dict(width=4), marker=dict(size=8), hovertemplate="<b>%{customdata[1]}</b><br>Age %{x}<br>Value: %{y:.2f}<extra></extra>")
        
        fig.update_xaxes(dtick=1, title_font=dict(size=25, family='Arial Black'), tickfont=dict(size=18, family='Arial Black'))
        fig.update_yaxes(title_font=dict(size=25, family='Arial Black'), tickfont=dict(size=18, family='Arial Black'))
        
        if metric in ["Save %", "SH%"]:
            fig.update_yaxes(ticksuffix="%")
            fig.update_traces(hovertemplate="<b>%{customdata[1]}</b><br>Age %{x}<br>%{y:.1f}%<extra></extra>")
        
        # Zombie Popup Fix: We explicitly hash the text input string into the chart's unique ID.
        # When you hit enter, the key regenerates, which violently clears the chart's memory of your last click.
        chart_key = f"chart_{hash(str(st.session_state.players))}_{metric}_{do_predict}_{do_smooth}_{search_term}"
        event = st.plotly_chart(fig, use_container_width=True, on_select="rerun", selection_mode="points", key=chart_key)
        
        if event and event.selection.get("points"):
            point = event.selection["points"][0]
            show_season_details(point["customdata"][1], point["x"], raw_dfs_cache, metric, point["y"], do_cumul, final_df, season_type)
            
    else:
        st.info("No data found for the selected parameters.")

st.markdown("---")
st.markdown("<p style='text-align: center; color: gray; font-size: 14px;'>Created by Iksperial, built by Gemini 3.1 Pro 2026. <br><em>Data is the only religion that strictly punishes you for ignoring it.</em></p>", unsafe_allow_html=True)