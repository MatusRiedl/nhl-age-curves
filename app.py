import streamlit as st
import requests
import pandas as pd
import plotly.express as px

st.set_page_config(page_title="NHL Age Curves", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
    <style>
        .block-container { padding-top: 2rem !important; padding-bottom: 0rem !important; }
        h1 { padding-bottom: 0px !important; margin-bottom: 0px !important; }
        .stButton button { width: 100%; }
        
        /* Make ONLY the Add to Chart button blue via anchor injection */
        div.element-container:has(#blue-btn-anchor) + div.element-container button {
            background-color: #2b71c7 !important;
            border-color: #2b71c7 !important;
            color: white !important;
        }
        div.element-container:has(#blue-btn-anchor) + div.element-container button:hover {
            background-color: #1a569d !important;
            border-color: #1a569d !important;
        }

        /* Stop the sidebar from wrapping the red X button to the next line */
        [data-testid="stSidebar"] [data-testid="stHorizontalBlock"] {
            flex-wrap: nowrap !important;
            align-items: center !important;
        }
        
        /* Force the master control toggles to stay side-by-side on phones */
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
RECORDS_URL = "https://records.nhl.com/site/api/skater-career-scoring-regular-season?sort=points&dir=DESC&limit=50"

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
        res = requests.get(RECORDS_URL, timeout=5).json()
        players = {}
        for p in res.get('data', []):
            name = f"{p.get('firstName', '')} {p.get('lastName', '')}".strip()
            if name and p.get('playerId'):
                players[name] = int(p['playerId'])
        if players: return players
    except:
        pass
    return { "Wayne Gretzky": 8447400, "Jaromir Jagr": 8448208, "Sidney Crosby": 8471675, "Alexander Ovechkin": 8471214 }

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
        for pos in ['forwards', 'defensemen', 'goalies']:
            for p in res.get(pos, []):
                name = f"{p['firstName']['default']} {p['lastName']['default']}"
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
                    "Age": age,
                    "SeasonYear": season_year,
                    "GameType": "Regular" if game_type == '2' else "Playoffs",
                    "GP": gp,
                    "Points": s.get('points', 0),
                    "Goals": s.get('goals', 0),
                    "Assists": s.get('assists', 0),
                    "PIM": s.get('pim', 0) or s.get('penaltyMinutes', 0),
                    "Shots": s.get('shots', 0),
                    "TotalTOIMins": toi_val * gp,
                    "Wins": s.get('wins', 0),
                    "Shutouts": s.get('shutouts', 0),
                    "Saves": s.get('saves', s.get('shotsAgainst', 0) - s.get('goalsAgainst', 0)),
                    "WeightedSV": float(s.get('savePctg', 0.0)) * 100 * gp,
                    "WeightedGAA": float(s.get('goalsAgainstAvg', 0.0)) * gp
                })
        return pd.DataFrame(data), base_name
    except:
        return pd.DataFrame(), base_name

BASELINE_CURVE = {
    18: 20, 19: 35, 20: 45, 21: 52, 22: 58, 23: 62, 24: 65, 25: 65,
    26: 63, 27: 60, 28: 56, 29: 52, 30: 48, 31: 42, 32: 36, 33: 30, 34: 24, 35: 18
}

@st.dialog("Season Snapshot")
def show_season_details(player_name, age, raw_dfs_list):
    st.markdown(f"### {player_name} at Age {age}")
    found = False
    for df in raw_dfs_list:
        if not df.empty and df['BaseName'].iloc[0] == player_name:
            season_data = df[df['Age'] == age]
            if not season_data.empty:
                cols_to_show = ['SeasonYear', 'GameType', 'GP', 'Points', 'Goals', 'Assists'] if st.session_state.stat_category == "Skater" else ['SeasonYear', 'GameType', 'GP', 'Wins', 'Saves', 'Shutouts']
                st.dataframe(season_data[cols_to_show], hide_index=True, use_container_width=True)
                found = True
                break
    if not found:
        st.write("Detailed data not available for this projection or baseline.")

# --- SIDEBAR: Player Management ---
with st.sidebar:
    st.title("Player Management")
    
    st.subheader("Global Search")
    search_term = st.text_input("Search for any player:", placeholder="e.g., Crosby, Brodeur")
    opts = {}
    if search_term:
        results = search_player(search_term)
        if results: opts = {f"{p['name']} ({p.get('teamAbbrev') or 'FA'})": int(p['playerId']) for p in results}
            
    selected = st.selectbox("Select Best Match:", list(opts.keys()) if opts else ["Waiting for search..."], disabled=not bool(opts))
    
    # Anchor injection trick to specifically style the next element (the button) blue
    st.markdown("<div id='blue-btn-anchor'></div>", unsafe_allow_html=True)
    if st.button("Add to Chart", use_container_width=True, type="primary", disabled=not bool(opts)):
        st.session_state.players[opts[selected]] = selected.split(" (")[0]
        st.rerun()

    st.markdown("---")
    
    st.subheader("Quick Adds")
    top_50_dict = get_top_50()
    top_selected = st.selectbox("Top 50 All-Time", list(top_50_dict.keys()))
    if st.button("Add Legend", use_container_width=True):
        st.session_state.players[top_50_dict[top_selected]] = top_selected
        st.rerun()

    team_abbr = st.selectbox("Active Rosters", list(ACTIVE_TEAMS.keys()), format_func=lambda x: ACTIVE_TEAMS[x])
    if team_abbr:
        roster = get_team_roster(team_abbr)
        if roster:
            roster_player = st.selectbox("Select Player:", list(roster.keys()), label_visibility="collapsed")
            if st.button("Add Roster Player", use_container_width=True):
                st.session_state.players[roster[roster_player]] = roster_player
                st.rerun()
                
    st.markdown("---")
    st.subheader("Players on Board")
    if st.session_state.players:
        for pid, name in list(st.session_state.players.items()):
            c_name, c_btn = st.columns([8, 2], vertical_alignment="center")
            with c_name: st.markdown(f"<div style='font-size: 15px; margin-bottom: 0;'>{name}</div>", unsafe_allow_html=True)
            with c_btn:
                if st.button("✖", key=f"drop_{pid}", type="primary"):
                    del st.session_state.players[pid]
                    st.rerun()
    else:
        st.info("Board is empty")

# --- MAIN: Visualization ---
st.title("NHL Player Age Curves")
st.markdown("---")

# 1. Metrics & Category Selector
# Flipped from [8, 2] to [2.5, 7.5] so Category sits right next to the Metrics
c_category, c_metric = st.columns([2.5, 7.5], vertical_alignment="center")

with c_category:
    st.session_state.stat_category = st.radio("Category:", ["Skater", "Goalie"], horizontal=True)

with c_metric:
    if st.session_state.stat_category == "Skater":
        metric = st.radio("Select Metric:", 
                            ["Points", "Goals", "Assists", "GP", "PPG", "SH%", "PIM", "TOI"], 
                            horizontal=True, key="skater_metric",
                            help="GP: Games Played | PPG: Points Per Game | SH%: Shooting Percentage | PIM: Penalty Minutes | TOI: Time on Ice (Avg Mins)")
    else:
        metric = st.radio("Select Metric:", 
                            ["SavePct", "GAA", "Wins", "Shutouts", "GP", "Saves"], 
                            horizontal=True, key="goalie_metric",
                            help="SavePct: Save Percentage | GAA: Goals Against Average | GP: Games Played | Saves: Total Saves")

# 2. Master Control Panel (Mobile Grid via CSS override)
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

# 3. Data Processing & Plotting
if st.session_state.players:
    processed_dfs = []
    raw_dfs_cache = []
    
    for pid, name in st.session_state.players.items():
        raw_df, base_name = get_player_raw_stats(pid, name)
        if raw_df.empty: continue
        
        raw_df['BaseName'] = base_name
        raw_dfs_cache.append(raw_df.copy())
        
        if season_type != "Both":
            raw_df = raw_df[raw_df['GameType'] == season_type]
        if raw_df.empty: continue
        
        if do_era and st.session_state.stat_category == "Skater":
            raw_df['EraMult'] = raw_df['SeasonYear'].apply(get_era_multiplier)
            raw_df['Points'] = raw_df['Points'] * raw_df['EraMult']
            raw_df['Goals'] = raw_df['Goals'] * raw_df['EraMult']
            raw_df['Assists'] = raw_df['Assists'] * raw_df['EraMult']

        df = raw_df.groupby('Age').sum(numeric_only=True).reset_index()
        
        df['PPG'] = df['Points'] / df['GP']
        df['TOI'] = df['TotalTOIMins'] / df['GP']
        df['SH%'] = (df['Goals'] / df['Shots'] * 100).fillna(0)
        df['SavePct'] = df['WeightedSV'] / df['GP']
        df['GAA'] = df['WeightedGAA'] / df['GP']
        
        df['BaseName'] = base_name
        df['Player'] = base_name
        
        if do_cumul:
            if metric in ['Points', 'Goals', 'Assists', 'Wins', 'Shutouts', 'GP', 'PIM', 'Saves']:
                df[metric] = df[metric].cumsum()
            else:
                st.warning(f"Cumulative tracking disabled: Mathematically invalid for rate stat ({metric}).")

        if do_smooth:
            df[metric] = df[metric].rolling(window=3, min_periods=1).mean()

        if do_predict and not do_cumul:
            max_age = df['Age'].max()
            if max_age < 40:
                last_row = df.loc[df['Age'] == max_age].copy()
                val = float(last_row[metric].values[0])
                proj_name = f"{base_name} (Proj)"
                
                proj_data = [last_row.to_dict('records')[0]]
                proj_data[0]['Player'] = proj_name
                
                for age in range(int(max_age) + 1, 41):
                    if "GAA" in metric: val *= 1.05
                    elif "SavePct" in metric: val *= 0.995
                    elif "PIM" in metric: val *= 0.90
                    elif metric in ["GP", "TOI", "SH%", "Saves"]: val *= 0.95
                    else:
                        if age <= 28: val *= 0.98
                        elif age <= 31: val *= 0.92
                        elif age <= 35: val *= 0.85
                        else: val *= 0.75
                    proj_data.append({"Age": age, metric: val, "Player": proj_name, "BaseName": base_name})
                
                df = pd.concat([df, pd.DataFrame(proj_data)], ignore_index=True)

        processed_dfs.append(df)

    if processed_dfs:
        final_df = pd.concat(processed_dfs, ignore_index=True)
        
        if do_base and metric in ["Points", "Goals", "Assists"]:
            base_data = []
            cumul_val = 0
            for age, pts in BASELINE_CURVE.items():
                val = pts
                if metric == "Goals": val = pts * 0.35
                if metric == "Assists": val = pts * 0.65
                
                if do_cumul:
                    cumul_val += val
                    val = cumul_val
                    
                base_data.append({"Age": age, metric: val, "Player": "NHL Top 6 Baseline", "BaseName": "Baseline"})
            final_df = pd.concat([final_df, pd.DataFrame(base_data)], ignore_index=True)

        fig = px.line(final_df, x="Age", y=metric, color="Player", custom_data=["BaseName"], markers=True, template="plotly_dark", line_shape="spline" if do_smooth else "linear")
        
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
        
        fig.update_xaxes(dtick=1, title_font=dict(size=25, family='Arial Black'), tickfont=dict(size=18, family='Arial Black'))
        fig.update_yaxes(title_font=dict(size=25, family='Arial Black'), tickfont=dict(size=18, family='Arial Black'))
        fig.update_traces(line=dict(width=4), marker=dict(size=8), hovertemplate="<b>%{customdata[0]}</b><br>Age %{x}<br>Value: %{y:.2f}<extra></extra>")
        
        if metric in ["SavePct", "SH%"]:
            fig.update_yaxes(ticksuffix="%")
            fig.update_traces(hovertemplate="<b>%{customdata[0]}</b><br>Age %{x}<br>%{y:.1f}%<extra></extra>")
            
        event = st.plotly_chart(fig, use_container_width=True, on_select="rerun", selection_mode="points")
        
        if event and event.selection.get("points"):
            point = event.selection["points"][0]
            selected_age = point["x"]
            selected_player = point["customdata"][0]
            if "Baseline" not in selected_player and "(Proj)" not in selected_player:
                show_season_details(selected_player, selected_age, raw_dfs_cache)
            
    else:
        st.info("No data found for the selected parameters.")

st.markdown("---")
st.markdown("<p style='text-align: center; color: gray; font-size: 14px;'>Created by Iksperial, built by Gemini 3.1 Pro 2026. <br><em>Data is the only religion that strictly punishes you for ignoring it.</em></p>", unsafe_allow_html=True)