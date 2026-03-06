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

app.py is a ~350-line orchestrator. It initializes session state, hydrates
shared URL params once, resolves compact ID-only share links back to display
names, calls render_sidebar() and render_controls() for UI, dispatches to
process_players() or process_teams() for data, then calls render_chart(). All
business logic, caching, and computation live in the nhl/ package modules
described in Section 2.

SECTION 2 — FILE STRUCTURE
-----------------------------
app.py                     — Thin orchestrator. Initializes session state,
                             calls UI/pipeline/chart functions from nhl/ package.
                             ~350 lines. No business logic here.

scraper.py                 — Standalone script. Run manually to refresh parquet.
                             Hits NHL API, maps positions, calculates ages, retries
                             transient/rate-limited responses, normalizes goalie
                             save percentage, and recomputes traded-season goalie
                             rates before exporting raw historical seasons to parquet.
                             Era adjustment is NOT applied at export time.
                             player_pipeline.py applies era adjustment once to hist_df
                             before the per-player KNN loop (via apply_era_to_hist()),
                             then passes the adjusted df into knn_engine.py with
                             do_era=False. The live player pipeline applies it
                             independently via get_era_multiplier() — both using the
                             same 8-period multiplier table so comparisons are symmetric.

nhl_historical_seasons.parquet — Local database. Loaded once at startup.

requirements.txt           — streamlit, pandas, plotly, requests, pyarrow/fastparquet

nhl/ package (all logic lives here — see Section 12 for full detail):
  __init__.py              — Package marker, module directory docstring
  constants.py             — All shared constants. No project imports.
  styles.py                — CSS injection only. No project imports.
  era.py                   — Era adjustment math. No Streamlit dependency.
  data_loaders.py          — Cached fetch/parquet loaders + shared player landing payload.
  baselines.py             — Aggregate historical + team 75th-pct baseline builders.
  knn_engine.py            — Hybrid KNN projection engine.
                             No Streamlit. Independently testable.
  player_pipeline.py       — process_players() full per-player pipeline +
                             clone wiring for dialog display.
  team_pipeline.py         — process_teams() team pipeline.
  controls.py              — Category/Metric + View Options expanders.
  sidebar.py               — Player/team sidebar UI.
  dialog.py                — @st.dialog season-detail popup.
  chart.py                 — Plotly chart rendering + aggregate baseline
                             overlays + JS pan-clamp injection.
  comparison.py            - render_comparison_area() tabbed comparison panel with
                             Overview, Trophies, and Live games quick-add actions.
  url_params.py            — encode_state_to_params() / apply_params_to_state().
                             Builds compact share-link query params, omits default
                             values, and restores them on first page load. No
                             Streamlit import.
  schedule.py              - get_live_or_recent_game() / get_upcoming_games() /
                             get_featured_players(). Handles first-load live defaults,
                             upcoming-game lookup, Central European local time labels,
                             and featured skater/goalie selection from club stats.
  async_preloader.py       — preload_all_categories(). Background cache warming
                             for Goalie and Team data using threading. Loads
                             non-active categories while user views current category.

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

Scoreboard: https://api-web.nhle.com/v1/scoreboard/now
            Returns: recent multi-day scoreboard payload used to find a live or
            most recently completed NHL game for first-load auto-population.

Scores:    https://api-web.nhle.com/v1/score/{date}
           Returns: games[] for a specific YYYY-MM-DD date.
           Fields used by schedule.py include id, gameState, gameType,
           startTimeUTC, venue.default, awayTeam, and homeTeam.

Club stats: https://api-web.nhle.com/v1/club-stats/{team_abbr}/now
            Returns: skaters[] and goalies[] with playerId, firstName, lastName,
            points, gamesPlayed, wins, and savePercentage.
            Used to pick each team's current-season points leader and best Save%
            goalie for chart and comparison seeding.

Records:   https://records.nhl.com/site/api/skater-career-scoring-regular-season
           https://records.nhl.com/site/api/skater-career-scoring-playoff
           https://records.nhl.com/site/api/goalie-career-stats
           https://records.nhl.com/site/api/goalie-career-playoff-stats
           Used for: Top 50 All-Time list and All-Time rank calculation in popup

All APIs are undocumented and unofficial. They can change or break without notice.
All are wrapped in try/except with silent fallbacks.

SECTION 4 — SESSION STATE
---------------------------
All 14 persistent session state keys (initialized at top of script):

  st.session_state.skater_players   dict: {player_id (str): "Player Name (TEAM)"} — Skater board
  st.session_state.goalie_players   dict: {player_id (str): "Player Name (TEAM)"} — Goalie board
  st.session_state.teams            dict: {team_abbr (str): full_name (str)} — Team board
  st.session_state.team_sel_abbr    str: active team abbreviation for roster filtering
  st.session_state.stat_category    str: "Skater", "Goalie", or "Team"
  st.session_state.season_type      str: "Regular", "Playoffs", or "Both"
  st.session_state.do_smooth        bool: Data Smoothing toggle
  st.session_state.do_predict       bool: Project to 40 toggle
  st.session_state.do_era           bool: Era-Adjust toggle
  st.session_state.do_cumul_toggle  bool: Cumulative toggle (raw; see do_cumul below)
  st.session_state.do_base          bool: Show Baseline toggle
  st.session_state.x_axis_mode      str: "Age", "Games Played", or "Season Year" (team mode)
  st.session_state.league_filter    list[str]: subset of NHLE_MULTIPLIERS keys, default ['NHL']
  st.session_state._url_loaded      bool: set True after URL params are read on first page load;
                                    prevents re-reading on subsequent reruns this session

  URL behavior:
    app.py reads dict(st.query_params) once during startup.
    During normal exploration it does not sync state back into the browser URL.
    The compact share URL is generated only when the chart Copy link control is clicked.

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
     KNN historical data is era-adjusted once in player_pipeline.py before the
     player loop (apply_era_to_hist, is_goalie derived from stat_category), then
     passed to knn_engine.py with do_era=False so clone matching stays consistent
     with the displayed era-adjusted player curve without redundant copies.

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

  8. PROJECTION GATE + KNN ENTRY (Age mode only):
     Projection only runs if all of the following are true:
       - "Project to 40" toggle is on
       - max_age < 40
       - metric not in NO_PROJECTION_METRICS = {'GP', 'SH%', 'TOI'}
       - career passes the thin-data guard (minimum seasons and total GP)
     If projection is allowed and metric is in ml_supported_metrics, use the
     KNN engine described in Section 7 with position-appropriate comparables.

  9. FALLBACK PROJECTION (Age mode only, only after projection is allowed):
     If metric is not ML-supported, or KNN cannot produce usable rows,
     player_pipeline.py switches to run_linear_fallback().
     GP, SH%, and TOI do not reach this branch in normal app flow because
     their forecast lines are suppressed entirely by NO_PROJECTION_METRICS.

  10. CUMULATIVE (Age mode only): If do_cumul, cumsum() the metric column.
      do_cumul is already False for rate stats and in Games Played mode.

  11. SMOOTHING: rolling(window=3, min_periods=1).mean() on the metric column.
      Available in both Age and Games Played modes.

  12. SPLIT (Age mode only): real_part (Age <= max_age) and proj_part (Age >= max_age).
      The final real point is duplicated into the projection trace for visual
      continuity, then proj_part is renamed to "Player Name (Proj)" for Plotly
      trace separation.

SECTION 7 — HYBRID KNN PROJECTION ENGINE DEEP DIVE
--------------------------------------
This is the core intellectual property of the app.
Only runs in Age mode. Skipped entirely in Games Played mode.

ml_supported_metrics = ['Points', 'Goals', 'Assists', '+/-', 'PPG', 'PIM',
                         'Wins', 'Shutouts', 'Saves', 'Save %', 'GAA']
NOTE: GP is intentionally excluded. See Section 7a.
Projection is also suppressed entirely for NO_PROJECTION_METRICS =
{'GP', 'SH%', 'TOI'}, so those metrics do not get a Forecast line in normal app flow.

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
  If no valid ages exist, falls back to fallback projection if projection is
  otherwise allowed by the pipeline gate.

STEP 4 — DISTANCE (VECTORIZED):
  dist = valid_hist[valid_ages].sub(valid_match_vals).abs().sum(axis=1)
  L1 distance between the player's entire career and every historical
  player's matching 3 seasons. Lower = more similar. Fully vectorized.

STEP 5 — TOP 10 CLONES:
  top_ids = dist.nsmallest(10).index
  These 10 players drive the projection.
  Their influence is equal-weighted, not distance-weighted.

STEP 6 — HYBRID-DELTA MAPPING:
  For each future age (max_age+1 to 40):
    If clone rows exist at that age:
      raw_avg  = mean(clone values at that age)
      next_avg = raw_avg * 0.70 + last_avg * 0.30

    If clone rows are thin, exhausted, or NaN:
      use a non-zero sparse fallback target instead of 0.
      Counting stats decay gently by age band.
      Rate stats use metric-aware continuation rules.

    At age 36+:
      sparse late-age targets are stabilized before projection math.
      Upward skater rebounds are capped, and sparse goalie Save % spikes are
      damped against a gentler fallback target instead of trusting tiny clone pools.

    If KNN cannot produce usable rows at all, player_pipeline.py switches to
    run_linear_fallback() and stores an empty clone list for the dialog popup.

    For +/-, GAA, Save % (additive delta):
      current_val += (next_avg - last_avg)
      Save % yearly delta is clamped to [-1.2, +0.6].

    For all other metrics (multiplicative % change):
      pct_change = (next_avg - last_avg) / last_avg
      pct_change = clamped to [-0.12, +0.25] to prevent extreme single-year swings
      current_val += current_val * pct_change

  This maps the SLOPE of historical clones onto the MAGNITUDE of the current player.
  A clone that declined 15% between ages 32-33 will cause the same 15% decline
  in the projected player, regardless of their absolute stat level.

STEP 7 — STAT CAPS AND FLOORS (applied every projected year):
  Caps: Points=155, Goals=70, Assists=105, +/-=60, GP=82 (sk)/65 (g), PPG=1.9,
        SH%=25, PIM=150, TOI=28, Save%=93.5, Wins=45, Shutouts=10, Saves=2000
  GAA=1.8 is a FLOOR (not a ceiling) — no goalie should project below 1.8 GAA.
  Floors: +/-= -60 (stat_floors dict, applied in BOTH KNN and fallback paths).

Section 7a - WHY GP IS EXCLUDED FROM KNN AND FORECAST:
  KNN fills ages beyond a clone's career with 0 (the player retired).
  A clone pool of 10 players where 7 retired by age 35 would show average
  GP of ~24 at age 36 (7×0 + 3×65 / 10 = 19.5). This is not decline —
  it is survivorship bias in reverse.
  run_linear_fallback() still contains a 4-phase GP durability curve:
    Age ≤ 28:  +0.8 GP/year (soft growth toward prime)
    Age 29-33: ×0.990/year (~1% annual loss — prime plateau)
    Age 34-37: ×0.965/year (~3.5% annual loss — gradual decline)
    Age 38-40: ×0.930/year (~7% annual loss — late career)
  But player_pipeline.py suppresses GP forecasts entirely via
  NO_PROJECTION_METRICS, so this rule exists as fallback logic rather than
  normal UI behavior.

SECTION 8 — BASELINE ENGINE
------------------------------
Source: nhl_historical_seasons.parquet (same file as KNN)
Filter:
  Skaters: GP >= 40 per season
  Goalies: GP >= 20 per season
Target: aggregate 75th percentile per age for strong historical skater and goalie careers

Historical goalie reliability guardrails:
  - scraper.py normalizes goalie SavePct to 0-1 scale and recomputes traded-season
    SavePct and GAA from season totals instead of summing rate fields.
  - load_historical_data() sanitizes legacy goalie SavePct values from older parquet
    builds before deriving displayed Save %.

Baseline families built by build_historical_baselines(df):
  - Skater
  - Goalie

Construction + shaping:
  1. 75th percentile by age within the skater or goalie pool
  2. 3-period rolling average smooth (center=True) across ages
  3. After age 31, skater and counting-stat baselines use the classic
     `prev * 0.92` survivorship cap to stop false late-age rises.
  4. Skater late ages 36-41 are reshaped by blending sparse data with the trusted
     decline profile from the recent pre-tail ages.
  5. Goalie rate stats (`Save %`, `GAA`) skip the multiplicative skater rule.
  6. Goalie `Save %` keeps the smoothing pass, optional 29-31 hump bridging, and a
     curved blended late-career tail from ages 35-41 with bounded year-over-year
     decline and an age-aware minimum drop.

Chart selection and rendering:
  - Skater mode uses the Skater baseline.
  - Goalie mode uses the Goalie baseline.
  - chart.py builds baseline rows inline by reindexing ages 18-40 and linearly
    interpolating available ages before plotting.
  - Baseline disabled in Games Played mode (it is Age-indexed, no Games equivalent).
  - Baseline displayed as dashed white semi-transparent line when "Show Baseline" is on.

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
  load_historical_data()        - parquet file, plus legacy goalie rate sanitization
  build_historical_baselines()  - derived from parquet, same lifetime
  load_all_team_seasons()       - cached team history parquet load
  build_team_baselines()        - derived team baseline cache
  get_top_50()                  - rarely changes, no TTL needed
  get_top_50_goalies()          - goalie all-time leaderboard cache
  get_team_roster()             - no TTL (intentional for now)
  get_player_raw_stats()        - player historical data, no TTL needed

@st.cache_data(ttl=3600) - refreshes hourly:
  get_player_landing()         - shared player landing payload for metadata helpers
  fetch_all_time_records()      - records change slowly
  get_id_to_name_map()          - derived from records
  search_player()               - team labels change with trades
  get_clone_details_map()       - clone name/stat lookup from records API;
                                  used to populate the ML projection clone panel
  get_featured_players()        - current-season featured skater/goalie selection

No cache by design, but these reuse get_player_landing() so they do not trigger
extra player landing requests:
  get_player_headshot(), get_player_current_team(), get_player_roster_info(),
  get_player_hero_image(), get_player_awards(), get_player_league_abbrevs()

@st.cache_data(ttl=300) - refreshes every 5 minutes:
  get_live_or_recent_game()     - first-load default matchup lookup
  get_upcoming_games()          - next 4 future games for the Live games tab

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
package. app.py is now a thin orchestrator (~350 lines). This section describes
each module's responsibility, its public interface, and its import dependencies.

IMPORT DEPENDENCY GRAPH (no cycles):
  constants, era, styles,
  url_params                      no project imports (leaf modules)
  data_loaders, controls, team_pipeline,
  schedule                        import from constants only
  baselines                       imports from constants, era
  knn_engine                      imports from constants, era
  player_pipeline                 imports from constants, era, data_loaders, knn_engine
  sidebar                         imports from constants, data_loaders
  dialog                          imports from data_loaders
  chart                           imports from constants, dialog
  comparison                      imports from constants, data_loaders, schedule
  app.py                          imports all modules

MODULE: nhl/constants.py
  Single source of truth for all shared configuration. No project imports.
  Exports:
    SEARCH_URL, STATS_URL, ROSTER_URL, TEAM_STATS_URL, TEAM_LIST_URL
    ACTIVE_TEAMS        dict: abbrev -> full name (32 teams)
    RATE_STATS          set: stats requiring mean aggregation
    TEAM_RATE_STATS     set: team-mode rate stats
    TEAM_METRICS        list: ordered selectable team metrics
    ML_SUPPORTED_METRICS list: metrics KNN can project
    NO_PROJECTION_METRICS set: metrics with Forecast suppressed entirely
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
  All network I/O and parquet load. Network-heavy loaders use @st.cache_data,
  and lightweight player metadata helpers reuse get_player_landing().
  load_historical_data() also sanitizes legacy goalie SavePct values before
  deriving displayed Save % so stale parquet files cannot poison goalie charts.
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
    get_player_landing(player_id) -> dict            (ttl=3600)
    get_player_headshot(player_id) -> str            (no cache, uses get_player_landing)
    get_player_current_team(player_id) -> str        (no cache, uses get_player_landing)
    get_player_roster_info(player_id) -> dict        (no cache, uses get_player_landing)
    get_player_hero_image(player_id) -> str          (no cache, uses get_player_landing)
    get_player_awards(player_id) -> list             (no cache, uses get_player_landing)
    get_player_league_abbrevs(player_id) -> list[str] (no cache, uses get_player_landing)
    get_player_raw_stats(player_id, base_name) -> tuple[df, str, str] (permanent cache)
    get_id_to_name_map(category) -> dict             (ttl=3600)
    get_clone_details_map(category) -> dict          (ttl=3600)
    get_all_time_rank(category, s_type, metric, value) -> int|None

MODULE: nhl/baselines.py
  Historical and team 75th-percentile baseline builders. Uses @st.cache_data permanently.
  Historical baselines are aggregate Skater and Goalie curves built from the
  historical parquet plus the preserved late-tail shaping fixes.
  Exports:
    build_historical_baselines(df) -> dict
      {'Skater': DataFrame, 'Goalie': DataFrame}
    build_team_baselines(all_team_df) -> dict  {season_year: {metric: float}}

MODULE: nhl/knn_engine.py
  Hybrid KNN projection engine. No Streamlit import. Independently testable.
  All session state values are function parameters, not st.session_state reads.
  Uses L1 distance, equal-weight top-10 clone influence, fixed 70/30 blending,
  and sparse-age stabilization.
  Exports:
    run_knn_projection(career_df, metric, hist_df, is_goalie, pos_code,
                       do_era, season_type, stat_category,
                       id_to_name_map, clone_details_map)
                       -> tuple[list[dict], list[dict]]  (proj_rows, clone_names)
    run_linear_fallback(career_df, metric, max_age, stat_category) -> list[dict]

MODULE: nhl/player_pipeline.py
  Full per-player data pipeline. No Streamlit import.
  Stores clone detail lists in ml_clones_dict and keeps projection overlap with
  proj_part starting at Age >= max_age so the final real point is duplicated into
  the projection trace for continuity.
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
  The @st.dialog decorator is registered at import time - keep at module level.
  stat_category is a function parameter (not read from session state).
  Uses a simple label map for Skater and Goalie baseline clicks, and renders
  nearest historical matches from the clone lists stored in ml_clones_dict.
  Exports:
    show_season_details(player_name, age, raw_dfs_list, metric, val, is_cumul,
                        full_df, s_type, ml_clones_dict,
                        historical_baselines, stat_category) -> None

MODULE: nhl/chart.py
  Plotly chart assembly, aggregate baseline overlay, JS pan-clamp, click dispatch,
  and Copy link clipboard control.
  Builds Skater or Goalie baseline rows inline from the cached baseline DataFrames.
  Exports:
    render_chart(processed_dfs, metric, team_mode, games_mode, do_cumul,
                 do_base, do_smooth, stat_category, historical_baselines,
                 team_baselines, raw_dfs_cache, ml_clones_dict,
                 season_type, sidebar_keys, peak_info, do_prime, share_params) -> None

MODULE: nhl/comparison.py
  Right-column tabbed comparison panel rendered alongside the chart.
  Overview and Trophies render player or team summary cards.
  Live games lists the next 4 upcoming games and can seed st.session_state.teams
  plus st.session_state.players in one click.
  Exports:
    render_comparison_area(processed_dfs, players, teams, peak_info, metric,
                           stat_category, season_type, team_mode) -> None
    get_panel_tab_ids() -> set[str]

MODULE: nhl/url_params.py
  URL query param serialization and deserialization. No Streamlit import. No project imports.
  Called from app.py: loaded once per session via _url_loaded guard and encoded
  only when the chart Copy link control is clicked.
  Exports:
    encode_state_to_params(ss) -> dict
      Converts session state to a compact dict for st.query_params.update().
      Encoded URL param keys:
        cat    — stat_category: S / G / T
        sk_m   — skater_metric (stat name string)
        go_m   — goalie_metric (stat name string)
        tm_m   — team_metric (stat name string)
        sp     — season_type: Regular / Playoffs / Both
        xm     — x_axis_mode: A / GP / SY
        lg     — league_filter: comma-joined list
        sm / pr / era / cu / bl / pf  — bool toggles only when non-default
        pt_s / pt_g / pt_t            — panel tabs only when not "overview"
        pl     — players: semicolon-joined player IDs
        tm     — teams: semicolon-joined team abbreviations
      Default-valued params are omitted from output entirely.
    apply_params_to_state(params, ss) -> None
      Reads dict(st.query_params) and writes into session state.
      Validates metric values against known-valid sets before applying.
      Only writes keys that are present; absent keys keep their session-state defaults.
      Accepts both compact ID-only links and legacy "id|name" / "abbr|name" links.

MODULE: nhl/schedule.py
  Schedule helpers for chart auto-population and the Live games comparison tab.
  Called once per browser session via the _default_loaded guard in app.py.
  Skipped entirely when URL params have already populated players/teams.
  Imports: nhl.constants (ACTIVE_TEAMS)
  Score and team endpoints (all undocumented, no auth):
    https://api-web.nhle.com/v1/scoreboard/now
    https://api-web.nhle.com/v1/score/{date}
    https://api-web.nhle.com/v1/club-stats/{team_abbr}/now
  Game states recognized: LIVE, CRIT (live); FINAL, OVER, OFF (finished).
  Valid game types: 2 (regular season), 3 (playoffs). Preseason and all-star ignored.
  Exports:
    get_live_or_recent_game() -> tuple[str, str] | None   [ttl=300]
      Checks scoreboard/now first. If nothing qualifies, walks back up to 7
      calendar days through score/{date}. Returns (home_abbr, away_abbr) or None.
    get_upcoming_games(limit=4, days_ahead=14) -> list[dict]   [ttl=300]
      Scans forward from today, keeps future regular-season and playoff games,
      formats Central European local time labels, and returns matchup plus venue
      metadata for the Live games tab.
    get_featured_players(home_abbr, away_abbr) -> dict    [ttl=3600]
      For each team: fetches club-stats/{abbr}/now, picks the current-season
      points leader, then picks the best Save% goalie with games-played and wins
      tie-breaks.
      Returns {'players': {id: name, ...}, 'teams': {abbr: name, ...}}.
  Session state integration:
    _default_loaded guard in app.py (fires once per session after URL params load).
    Auto-population is skipped when st.session_state.players or .teams are non-empty
    (i.e. a shared URL was opened).

MODULE: nhl/async_preloader.py
  Background cache warming using threading. Preloads data for non-active categories
  so users don't wait when switching between Skater, Goalie, and Team modes.
  Called once per session via _preloaded guard in app.py, after session state init.
  No Streamlit imports. Only imports from nhl.data_loaders.
  Design note:
    Uses Python threading (not asyncio) for simplicity with Streamlit's synchronous
    execution model. Daemon threads call @st.cache_data functions; results are stored
    in Streamlit's cache for subsequent synchronous calls.
  Exports:
    preload_all_categories(current_category: str) -> None
      Spawns background threads to warm cache for categories other than current.
      When viewing Skaters: preloads Goalie (id_to_name_map, clone_details_map)
      and Team (load_all_team_seasons) data.
      When viewing Goalies or Teams: preloads the other two categories.
    preload_goalie_data() -> None
      Internal helper. Spawns threads for get_id_to_name_map("Goalie") and
      get_clone_details_map("Goalie").
    preload_team_data() -> None
      Internal helper. Spawns thread for load_all_team_seasons().
    _preload_in_thread(target: Callable, name: str) -> None
      Internal helper. Creates and starts a daemon thread for the target function.