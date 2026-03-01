NHL AGE CURVES — TECHNICAL HANDOVER DOCUMENT

For: Next AI developer taking over implementation
Entry point: app.py (thin orchestrator); all logic lives in nhl/ package

SECTION 1 — ARCHITECTURE OVERVIEW
------------------------------------
This is a modular Streamlit application organized as a Python package (nhl/).
There is no backend server, no database connection, no authentication.
Streamlit reruns app.py from top to bottom on every user interaction
(toggle, button click, chart click, text input). All state persists via
st.session_state between reruns.

The app has two data sources:
  A) LIVE: NHL public APIs (undocumented, no auth required)
  B) LOCAL: nhl_historical_seasons.parquet — a pre-built database generated
     by scraper.py (separate script, not part of the nhl/ package)

The parquet file is the backbone of the ML engine and baseline. Without it,
the app still works but KNN projections and the 75th percentile baseline
are disabled.

app.py is a ~200-line orchestrator. It initializes session state, calls
render_sidebar() and render_controls() for UI, dispatches to process_players()
or process_teams() for data, then calls render_chart(). All business logic,
caching, and computation live in the nhl/ package modules described in Section 2.

SECTION 2 — FILE STRUCTURE
-----------------------------
app.py                     — Thin orchestrator. Initializes session state,
                             calls UI/pipeline/chart functions from nhl/ package.
                             ~200 lines. No business logic here.

scraper.py                 — Standalone script. Run manually to refresh parquet.
                             Hits NHL API, era-adjusts Points only, maps positions,
                             calculates ages, exports to parquet.
                             NOTE: scraper only era-adjusts Points. The app now
                             adjusts Points, Goals, AND Assists independently (FIX #4).
                             This means the parquet has era-adjusted Points but raw
                             Goals/Assists — the app re-applies era adjustment on top.

nhl_historical_seasons.parquet — Local database. Loaded once at startup.

requirements.txt           — streamlit, pandas, plotly, requests, pyarrow/fastparquet

nhl/ package (all logic lives here — see Section 12 for full detail):
  __init__.py              — Package marker, module directory docstring
  constants.py             — All shared constants. No project imports.
  styles.py                — CSS injection only. No project imports.
  era.py                   — Era adjustment math. No Streamlit dependency.
  data_loaders.py          — All 14 @st.cache_data fetch/parquet functions.
  baselines.py             — Historical + team 75th-pct baseline builders.
  knn_engine.py            — KNN ML projection. No Streamlit. Independently testable.
  player_pipeline.py       — process_players() full per-player pipeline.
  team_pipeline.py         — process_teams() team pipeline.
  controls.py              — Category/Metric + View Options expanders.
  sidebar.py               — Player/team sidebar UI.
  dialog.py                — @st.dialog season-detail popup.
  chart.py                 — Plotly chart rendering + JS pan-clamp injection.

SECTION 3 — EXTERNAL API ENDPOINTS
--------------------------------------
Search:    https://search.d3.nhle.com/api/v1/search/player
           Params: culture=en-us, limit=10, q={query}
           Returns: list of {playerId, name, teamAbbrev}

Stats:     https://api-web.nhle.com/v1/player/{player_id}/landing
           Returns: birthDate, position, seasonTotals[]
           seasonTotals fields used: leagueAbbrev, gameTypeId, season, gamesPlayed,
           avgToi, points, goals, assists, pim, plusMinus, shots, wins, shutouts,
           saves, shotsAgainst, goalsAgainst, savePctg, goalsAgainstAvg

Roster:    https://api-web.nhle.com/v1/roster/{team_abbr}/current
           Returns: forwards[], defensemen[], goalies[] with id, firstName, lastName,
           positionCode

Records:   https://records.nhl.com/site/api/skater-career-scoring-regular-season
           https://records.nhl.com/site/api/skater-career-scoring-playoff
           https://records.nhl.com/site/api/goalie-career-stats
           https://records.nhl.com/site/api/goalie-career-playoff-stats
           Used for: Top 50 All-Time list and All-Time rank calculation in popup

All APIs are undocumented and unofficial. They can change or break without notice.
All are wrapped in try/except with silent fallbacks.

SECTION 4 — SESSION STATE
---------------------------
All 11 persistent session state keys (initialized at top of script):

  st.session_state.skater_players   dict: {player_id (int): "Player Name" (str)} — Skater board
  st.session_state.goalie_players   dict: {player_id (int): "Player Name" (str)} — Goalie board
  st.session_state.stat_category    str: "Skater" or "Goalie"
  st.session_state.season_type      str: "Regular", "Playoffs", or "Both"
  st.session_state.do_smooth        bool: Data Smoothing toggle
  st.session_state.do_predict       bool: Project to 40 toggle
  st.session_state.do_era           bool: Era-Adjust toggle
  st.session_state.do_cumul_toggle  bool: Cumulative toggle (raw; see do_cumul below)
  st.session_state.do_base          bool: Show Baseline toggle
  st.session_state.x_axis_mode      str: "Age" or "Games Played"
  st.session_state.league_filter    list[str]: subset of NHLE_MULTIPLIERS keys, default ['NHL']

  do_cumul (not in session state) is derived each render:
    do_cumul = do_cumul_toggle AND metric not in RATE_STATS AND not games_mode
    (cumulative is forced off for rate stats and in Games Played mode)

  CURRENT_SEASON_YEAR is also computed at startup, not stored in session state:
    _now = datetime.now()
    CURRENT_SEASON_YEAR = _now.year if _now.month >= 9 else _now.year - 1
    (NHL seasons start in October — Jan-Aug we're still in the prior calendar year's season)

SECTION 5 — THE STRICT SKATER/GOALIE DICHOTOMY
-------------------------------------------------
This is the most important architectural rule:
  is_goalie = raw_df['Saves'].sum() > 0 or raw_df['Wins'].sum() > 0
  if st.session_state.stat_category == "Skater" and is_goalie: continue
  if st.session_state.stat_category == "Goalie" and not is_goalie: continue

Players are never cross-plotted. A goalie added while in Skater mode is silently
skipped and vice versa. The user must switch category to see those players.

SECTION 6 — DATA PIPELINE (per player, per render)
----------------------------------------------------
For every player in active_players (resolved from skater_players or goalie_players based on stat_category):

  1. FETCH: get_player_raw_stats(pid) → raw_df (one row per supported-league season/gametype)
     Columns: League, Age, SeasonYear, GameType, GP, Points, Goals, Assists, PIM, +/-,
              Shots, TotalTOIMins, Wins, Shutouts, Saves, WeightedSV, WeightedGAA
     Supported leagues = keys of NHLE_MULTIPLIERS (NHL, KHL, SHL, AHL, NLA, LIIGA,
     NCAA, OHL, WHL, QMJHL). All others are silently dropped inside the fetch function.

  2. GATEKEEPER: Skip if wrong category (goalie in skater mode, etc.)
     Note: is_goalie check runs on the full unfiltered raw_df before any league filter.

  3. LEAGUE FILTER + NHLe: Filter raw_df to user-selected leagues (league_filter).
     Then multiply Points, Goals, Assists by NHLE_MULTIPLIERS[league] for non-NHL rows.
     GP is kept raw. TOI, +/-, Shots, WeightedSV, WeightedGAA are also kept raw.
     Default is ['NHL'] — identical to pre-v0.31 behavior when NHL-only is selected.

  4. SEASON FILTER: If not "Both", filter to Regular or Playoffs only

  5. ERA ADJUST: Normalizes stats to the 2018+ scoring/style baseline. NHL rows only
     (League == 'NHL'); non-NHL rows already NHLe-scaled, must not be double-adjusted.
     Toggle: st.session_state.do_era. Applies to both Skaters and Goalies.

     SKATERS — multiply Points, Goals, Assists by get_era_multiplier(year).
     Multipliers derived from historical GF/GP per team; baseline = 2018+ (~3.05 GF/GP).
     Formula: multiplier = 3.05 / era_avg_GF_per_team.
     Era multipliers (8 periods):
       ≤1967          × 1.00  — Original Six (~2.85 GF/GP, close to modern baseline)
       1968–1979      × 0.89  — Expansion + WHA era (~3.40 GF/GP); 3.05/3.40=0.897
       1980–1992      × 0.80  — Gretzky/peak scoring era (~3.85 GF/GP); 3.05/3.85=0.792
       1993–1996      × 0.90  — Transitional decline (~3.35 GF/GP); 3.05/3.35=0.910
       1997–2004      × 1.15  — Dead puck era (~2.63 GF/GP); 3.05/2.63=1.160
       2005–2012      × 1.06  — Post-lockout settling (~2.87 GF/GP); 3.05/2.87=1.063
       2013–2017      × 1.12  — Analytics/trap era (~2.72 GF/GP); 3.05/2.72=1.121
       2018+          × 1.00  — Modern renaissance (baseline)

     GOALIES — three stats normalized using different methods:
       GAA:      multiply WeightedGAA by get_era_multiplier(year) pre-groupby.
                 Same formula as skaters — GAA scales directly with league scoring.
                 3.50 GAA in 1985 × 0.80 = 2.80 normalized.
       Save%:    additive offset via get_goalie_era_sv_offset(year).
                 Formula: raw_sv + (0.9110 - era_league_avg_sv).
                 Preserves each goalie's deviation from their era mean, expressed in
                 modern-era terms. Offset applied to WeightedSV pre-groupby
                 (scaled by 100 * GP to match WeightedSV units).
                 League-average Save% by era (0-1 scale):
                   ≤1967: 0.878  — stand-up goalies, no masks
                   1968–1979: 0.871  — expansion, high scoring
                   1980–1992: 0.873  — peak Gretzky era, butterfly emerging
                   1993–1996: 0.890  — butterfly spreading, larger pads
                   1997–2004: 0.902  — dead puck, full butterfly, trap defense
                   2005–2012: 0.908  — post-lockout refinement
                   2013–2017: 0.912  — analytics era, peak equipment
                   2018+: 0.911     — modern baseline (equipment size limits)
       Shutouts: inverse multiplier: raw_SO / era_multiplier.
                 Shutouts harder to record in high-scoring eras; inverse gives more
                 credit. 10 SO in 1985 / 0.80 = 12.5 adjusted.
       Wins:     not adjusted — too team-dependent for meaningful era normalization.
     KNN historical data is era-adjusted in parallel via apply_era_to_hist(is_goalie=True)
     so clone matching stays consistent with the displayed era-adjusted player curve.

  5. PIPELINE BRANCH — Age mode vs Games Played mode (x_axis_mode):

     AGE MODE (default):
       season_year_max = raw_df.groupby('Age')['SeasonYear'].max()  ← FIX #2
       df = raw_df.groupby('Age').sum(numeric_only=True).reset_index()
       df['SeasonYear'] = df['Age'].map(season_year_max)
       (SeasonYear is explicitly preserved via max() before the sum to prevent
       "Both" mode from summing e.g. 2025+2025=4050. FIX #2.)

     GAMES PLAYED MODE (x_axis_mode == "Games Played"):
       Groups by SeasonYear.sum() first (not Age) to collapse Regular+Playoffs
       into one row per season. Then computes cumulative columns:
         df['CumGP']   = df['GP'].cumsum()    ← the X-axis
         Counting stats (Points, Goals, etc.) = cumsum of that stat
         Rate stats (PPG, TOI, SH%, Save %, GAA) = cumulative numerator / CumGP
         (i.e., career average to that game, not per-season rate)
       Projection, Cumulative toggle, and Baseline are all disabled in this mode.
       Age is preserved in df and stored as custom_data[2] for click interaction.

  6. RATE STATS (Age mode only — computed after groupby):
     PPG    = Points / GP
     TOI    = TotalTOIMins / GP
     SH%    = Goals / Shots * 100
     Save % = WeightedSV / GP   (WeightedSV = savePctg * 100 * GP per season)
     GAA    = WeightedGAA / GP  (WeightedGAA = goalsAgainstAvg * GP per season)

  7. MID-SEASON PACING (Age mode only): If current season year and GP < 82,
     multiply counting stats by (82 / actual_GP) to project full-season pace.
     Prevents the ML engine from treating an 18-game sample as a full season.

  8. KNN ML PROJECTION (Age mode only, if "Project to 40" toggle and
     metric in ml_supported_metrics): See Section 7 for full detail.

  9. FALLBACK PROJECTION (Age mode only, if KNN fails or metric not ML-supported):
     GP: Dedicated durability curve (plateau + soft decay)
     Other: Hardcoded per-metric decay rates

  10. CUMULATIVE (Age mode only): If do_cumul, cumsum() the metric column.
      do_cumul is already False for rate stats and in Games Played mode.

  11. SMOOTHING: rolling(window=3, min_periods=1).mean() on the metric column.
      Available in both Age and Games Played modes.

  12. SPLIT (Age mode only): real_part (Age <= max_age) and proj_part (Age >= max_age).
      proj_part renamed to "Player Name (Proj)" for Plotly trace separation.

SECTION 7 — KNN ML ENGINE DEEP DIVE
--------------------------------------
This is the core intellectual property of the app.
Only runs in Age mode. Skipped entirely in Games Played mode.

ml_supported_metrics = ['Points', 'Goals', 'Assists', '+/-', 'PPG', 'PIM',
                         'Wins', 'Shutouts', 'Saves', 'Save %', 'GAA']
NOTE: GP is intentionally excluded. See Section 7a.

STEP 1 — POSITION FILTERING:
  h_df = hist_df[hist_df['Position'] == pos_code]
  If fewer than 10 unique players in that position, fall back to full
  Skater pool (Position != 'G') or full Goalie pool (Position == 'G').
  Position codes: C, LW, RW, D (skaters), G (goalies)

STEP 2 — PIVOT:
  pivot = h_df.pivot_table(index='PlayerID', columns='Age', values=metric,
                            aggfunc='mean' if metric in RATE_STATS else 'sum')
  Creates a matrix: rows=historical players, columns=ages 17-45, values=metric.
  RATE_STATS = {'PPG', 'Save %', 'GAA', 'SH%', 'TOI'}

STEP 3 — VALID AGE GUARD:
  valid_ages = [a for a in match_ages if a in pivot.columns]
  Prevents KeyError crash for players with career ages not in historical data.
  If no valid ages exist, falls back to fallback projection.

STEP 4 — DISTANCE (VECTORIZED):
  dist = valid_hist[valid_ages].sub(valid_match_vals).abs().sum(axis=1)
  L1 distance between the player's entire career and every historical
  player's matching 3 seasons. Lower = more similar. Fully vectorized.

STEP 5 — TOP 10 CLONES:
  top_ids = dist.nsmallest(10).index
  These 10 players drive the projection.

STEP 6 — HYBRID-DELTA MAPPING:
  For each future age (max_age+1 to 40):
    next_avg = pivot.loc[top_ids, age].fillna(0).mean()  # for counting stats
    OR
    next_avg = pivot.loc[top_ids, age].mean()             # for rate stats (NaN ignored)

    For +/-, GAA, Save % (additive delta):
      current_val += (next_avg - last_avg)

    For all other metrics (multiplicative % change):
      pct_change = (next_avg - last_avg) / last_avg
      pct_change = clamped to [-0.5, +0.5] to prevent extreme single-year swings
      current_val += current_val * pct_change

  This maps the SLOPE of historical clones onto the MAGNITUDE of the current player.
  A clone that declined 15% between ages 32-33 will cause the same 15% decline
  in the projected player, regardless of their absolute stat level.

STEP 7 — STAT CAPS AND FLOORS (applied every projected year):
  Caps: Points=155, Goals=70, Assists=105, +/-=60, GP=82 (sk)/65 (g), PPG=1.9,
        SH%=25, PIM=150, TOI=28, Save%=93.5, Wins=45, Shutouts=10, Saves=2000
  GAA=1.8 is a FLOOR (not a ceiling) — no goalie should project below 1.8 GAA.
  Floors: +/-= -60 (stat_floors dict, applied in BOTH KNN and fallback paths).

Section 7a — WHY GP IS EXCLUDED FROM KNN:
  KNN fills ages beyond a clone's career with 0 (the player retired).
  A clone pool of 10 players where 7 retired by age 35 would show average
  GP of ~24 at age 36 (7×0 + 3×65 / 10 = 19.5). This is not decline —
  it is survivorship bias in reverse. GP uses a 4-phase durability curve instead:
    Age ≤ 28:  +0.8 GP/year (soft growth toward prime)
    Age 29-33: ×0.990/year (~1% annual loss — prime plateau)
    Age 34-37: ×0.965/year (~3.5% annual loss — gradual decline)
    Age 38-40: ×0.930/year (~7% annual loss — late career)

SECTION 8 — BASELINE ENGINE
------------------------------
Source: nhl_historical_seasons.parquet (same file as KNN)
Filter: GP >= 40 per season (removes AHL callups and short stints)
Target: 75th percentile per age — represents Top 6 Forward / Starting Goalie level

Two-step survivorship bias fix:
  1. 3-period rolling average smooth (center=True) across ages
  2. Strict monotonic decay after age 31: if base[age] > base[age-1], override:
       base[age] = base[age-1] * 0.92
     Prevents the curve from spiking upward at age 35+ due to selection bias
     (only elite players play that long, which otherwise makes the baseline look
     like performance improves with age — it doesn't).

Separate baselines for 'Skater' (Position != 'G') and 'Goalie' (Position == 'G').
Baseline disabled in Games Played mode (it is Age-indexed, no Games equivalent).
Baseline displayed as dashed white semi-transparent line when "Show Baseline" is on.

SECTION 9 — PLOTLY RENDERING GUARDRAILS
-----------------------------------------
PROJECTION VISUAL STYLE:
  Real data: solid colored line, filled markers
  Projection: dotted gray line, open circle markers
  Baseline: dashed white semi-transparent line, tiny markers (size=1)

GAMES PLAYED MODE CHART DIFFERENCES:
  x-axis column: "CumGP" (not "Age")
  hover text: "Career Game X" (not "Age X")
  dtick: auto-scaled by Plotly (not forced to 1 — range is 0–1500+)
  custom_data: ["BaseName", "Player", "Age"] — Age stored for click handler
  On click: age_for_detail = int(point["customdata"][2]) — passed to show_season_details()

SECTION 10 — CACHING STRATEGY
--------------------------------
@st.cache_data (permanent, until Streamlit restarts):
  load_historical_data()        — parquet file, never changes during session
  build_historical_baselines()  — derived from parquet, same lifetime
  get_top_50()                  — rarely changes, no TTL needed
  get_team_roster()             — no TTL (intentional for now)
  get_player_raw_stats()        — player historical data, no TTL needed

@st.cache_data(ttl=3600) — refreshes hourly:
  fetch_all_time_records()      — records change slowly
  get_id_to_name_map()          — derived from records
  search_player()               — team labels change with trades
  get_clone_details_map()       — clone name/stat lookup from records API;
                                   used to populate the ML projection clone panel

SECTION 11 — GAMES PLAYED MODE
---------------------------------
Added in v0.23.0. Controlled by x_axis_mode session state key.

Purpose: Compare players at the same point in career experience (game count)
instead of age. Normalizes for injuries — a player who missed 100 games to
injury shows a shorter X-axis, not lower Y-axis values.

X-axis: CumGP — cumulative career games played at end of each season.
Y-axis (counting stats): cumulative career total at that game.
Y-axis (rate stats): career average to that game (cumulative numerator / CumGP).

Pipeline difference from Age mode:
  - groupby('SeasonYear').sum() instead of groupby('Age').sum()
    (collapses Regular+Playoffs per season into one row, same as Age mode does)
  - All cumulative numerators computed before overwriting columns
  - Age column preserved for click interaction

Disabled features in Games Played mode:
  - Project to 40 (requires projecting GP simultaneously — compounds error)
  - Show Baseline (baseline is Age-indexed, no Games equivalent)
  - Cumulative toggle (data is inherently cumulative in this mode)

Click interaction preserved: Age stored in custom_data[2], passed to
show_season_details() so season detail panel shows correctly regardless of mode.

SECTION 12 — MODULAR PACKAGE STRUCTURE (v0.37.0+)
----------------------------------------------------
As of v0.37.0, all logic has been extracted from a single app.py into the nhl/
package. app.py is now a thin orchestrator (~200 lines). This section describes
each module's responsibility, its public interface, and its import dependencies.

IMPORT DEPENDENCY GRAPH (no cycles):
  constants, era, styles          no project imports (leaf modules)
  baselines, data_loaders,
  controls, team_pipeline         import from constants only
  knn_engine                      imports from constants, era
  player_pipeline                 imports from constants, era, data_loaders, knn_engine
  sidebar                         imports from constants, data_loaders
  dialog                          imports from data_loaders
  chart                           imports from constants, dialog
  app.py                          imports all modules

MODULE: nhl/constants.py
  Single source of truth for all shared configuration. No project imports.
  Exports:
    SEARCH_URL, STATS_URL, ROSTER_URL, TEAM_STATS_URL, TEAM_LIST_URL
    ACTIVE_TEAMS        dict: abbrev -> full name (32 teams)
    RATE_STATS          set: stats requiring mean aggregation
    TEAM_RATE_STATS     set: team-mode rate stats
    TEAM_METRICS        list: ordered selectable team metrics
    ML_SUPPORTED_METRICS list: metrics KNN can project (excludes GP)
    NHLE_MULTIPLIERS    dict: league -> scoring translation factor
    CURRENT_SEASON_YEAR int: computed at import time from datetime.now()
    STAT_CAPS           dict: per-metric projection ceilings (GAA is a floor)
    STAT_FLOORS         dict: per-metric projection floors (+/- = -60)

MODULE: nhl/era.py
  Era adjustment math. No Streamlit. Pure pandas/float functions.
  Exports:
    get_era_multiplier(year) -> float
    get_goalie_era_sv_offset(year) -> float
    apply_era_to_hist(df, do_era, is_goalie=False) -> pd.DataFrame

MODULE: nhl/styles.py
  CSS injection. No project imports.
  Exports:
    inject_css() -> None

MODULE: nhl/data_loaders.py
  All network I/O and parquet load. Every function uses @st.cache_data.
  Exports:
    load_historical_data() -> pd.DataFrame           (permanent cache)
    load_all_team_seasons() -> pd.DataFrame          (permanent cache)
    _paginate_records(base_url) -> list              (private helper)
    fetch_all_time_records(category, s_type) -> list (ttl=3600)
    get_top_50() -> dict                             (permanent cache)
    get_top_50_goalies() -> dict                     (permanent cache)
    search_player(query) -> list                     (ttl=3600)
    search_local_players(query, category) -> dict    (no cache — calls cached siblings)
    get_team_roster(team_abbr) -> dict               (permanent cache)
    get_player_headshot(player_id) -> str            (permanent cache)
    get_player_raw_stats(player_id, base_name) -> tuple[df, str, str] (permanent cache)
    get_id_to_name_map(category) -> dict             (ttl=3600)
    get_clone_details_map(category) -> dict          (ttl=3600)
    get_all_time_rank(category, s_type, metric, value) -> int|None

MODULE: nhl/baselines.py
  75th-percentile baseline builders. Both functions use @st.cache_data permanently.
  Exports:
    build_historical_baselines(df) -> dict  {'Skater': DataFrame, 'Goalie': DataFrame}
    build_team_baselines(all_team_df) -> dict  {season_year: {metric: float}}

MODULE: nhl/knn_engine.py
  KNN ML projection. No Streamlit import. Independently testable.
  All session state values are function parameters, not st.session_state reads.
  Exports:
    run_knn_projection(career_df, metric, hist_df, is_goalie, pos_code,
                       do_era, season_type, stat_category,
                       id_to_name_map, clone_details_map)
                       -> tuple[list[dict], list[dict]]  (proj_rows, clone_names)
    run_linear_fallback(career_df, metric, max_age, stat_category) -> list[dict]

MODULE: nhl/player_pipeline.py
  Full per-player data pipeline. No Streamlit import.
  Exports:
    process_players(players, metric, hist_df, id_to_name_map, clone_details_map,
                    season_type, stat_category, do_era, do_predict, do_smooth,
                    do_cumul, games_mode, league_filter)
                    -> tuple[list[df], list[df], dict, dict]
                       (processed_dfs, raw_dfs_cache, ml_clones_dict, peak_info)

MODULE: nhl/team_pipeline.py
  Team-mode data pipeline. No Streamlit import.
  Exports:
    process_teams(teams, all_team_df, metric, season_type,
                  do_cumul, do_smooth, games_mode) -> list[pd.DataFrame]

MODULE: nhl/controls.py
  Category/Metric and View Options expanders. Reads and writes st.session_state.
  Exports:
    render_controls() -> tuple[str, bool]  (metric, do_cumul)

MODULE: nhl/sidebar.py
  Player/team sidebar UI. Reads and writes st.session_state.
  Exports:
    render_sidebar() -> dict
      Returns sidebar_keys dict with keys: search_term, top_selected,
      team_abbr, roster_player — used by render_chart() for widget key generation.

MODULE: nhl/dialog.py
  @st.dialog popup for chart click events.
  The @st.dialog decorator is registered at import time — keep at module level.
  stat_category is a function parameter (not read from session state).
  Exports:
    show_season_details(player_name, age, raw_dfs_list, metric, val, is_cumul,
                        full_df, s_type, ml_clones_dict,
                        historical_baselines, stat_category) -> None

MODULE: nhl/chart.py
  Plotly chart assembly, baseline overlay, JS pan-clamp, click dispatch.
  Exports:
    render_chart(processed_dfs, metric, team_mode, games_mode, do_cumul,
                 do_base, do_smooth, stat_category, historical_baselines,
                 team_baselines, raw_dfs_cache, ml_clones_dict,
                 season_type, sidebar_keys) -> None
