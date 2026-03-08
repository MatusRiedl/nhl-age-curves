NHL AGE CURVES - TECHNICAL HANDOVER DOCUMENT

For the next AI or human who has to touch this thing at 2am.
Entry point: `app.py`. Most logic lives in `nhl/`.

SECTION 1 - ARCHITECTURE OVERVIEW
---------------------------------
This is a modular Streamlit app.
There is no backend, no database, and no auth.
Streamlit reruns `app.py` top-to-bottom on every interaction, so persistent state lives in
`st.session_state` and heavy work lives behind `@st.cache_data`.

The app has three data sources/artifacts:
- LIVE: NHL public APIs
- LOCAL: `nhl_historical_seasons.parquet`
- LOCAL: `win_prob_weights.json`

The parquet file powers KNN projection and historical baselines. Without it, the app still
renders real data, but projection and baseline features degrade.

The JSON weight artifact powers pregame win probability in the Live games tab. The Streamlit
app never trains that model at runtime; it only loads frozen weights and scores current matchups.

`app.py` is the session-state coordinator and render pass. It:
- loads URL params once
- seeds session state
- auto-loads a live or recent game once per session when appropriate
- renders sidebar and controls
- dispatches to `process_players()` or `process_teams()`
- renders the chart and comparison panel

SECTION 2 - FILE STRUCTURE
--------------------------
Top level:
- `app.py` - session-state orchestrator and render pass
- `scraper.py` - manual historical parquet refresh
- `train_win_prob.py` - offline trainer for pregame win-probability weights
- `nhl_historical_seasons.parquet` - historical seasons used by baselines and KNN
- `win_prob_weights.json` - offline-trained logistic-regression artifact used at runtime
- `requirements.txt`

`nhl/` modules:
- `__init__.py` - package index docstring
- `constants.py` - shared constants and metric sets
- `styles.py` - CSS injection helpers
- `era.py` - era multipliers and historical adjustment helpers
- `data_loaders.py` - cached API fetchers and parquet loaders
- `baselines.py` - historical and team baseline builders
- `knn_engine.py` - KNN projection and fallback logic
- `win_prob.py` - shared pregame feature engineering and runtime scoring math
- `player_pipeline.py` - full player processing path
- `team_pipeline.py` - team processing path
- `controls.py` - top controls expander
- `sidebar.py` - sidebar UI and add/remove flows
- `dialog.py` - chart click dialogs
- `chart.py` - Plotly render, baseline overlay, share link, click dispatch
- `comparison.py` - Overview / Trophies / Live games tabs
- `url_params.py` - compact share-link encode/decode
- `schedule.py` - live defaults, upcoming games, featured players, and runtime win-prob inference
- `async_preloader.py` - background cache warming for non-active categories

SECTION 3 - EXTERNAL API ENDPOINTS
----------------------------------
Search:
`https://search.d3.nhle.com/api/v1/search/player`

Player landing payload:
`https://api-web.nhle.com/v1/player/{player_id}/landing`

Player game log payload:
`https://api-web.nhle.com/v1/player/{player_id}/game-log/{season_id}/{game_type_id}`

Season skater summary:
`https://api.nhle.com/stats/rest/en/skater/summary`

Season goalie summary:
`https://api.nhle.com/stats/rest/en/goalie/summary`

Roster:
`https://api-web.nhle.com/v1/roster/{team_abbr}/current`

Scoreboard now:
`https://api-web.nhle.com/v1/scoreboard/now`

Scores by date:
`https://api-web.nhle.com/v1/score/{date}`

Club stats:
`https://api-web.nhle.com/v1/club-stats/{team_abbr}/now`

Team summary:
`https://api.nhle.com/stats/rest/en/team/summary`

Records APIs:
- `https://records.nhl.com/site/api/skater-career-scoring-regular-season`
- `https://records.nhl.com/site/api/skater-career-scoring-playoff`
- `https://records.nhl.com/site/api/goalie-career-stats`
- `https://records.nhl.com/site/api/goalie-career-playoff-stats`

All are undocumented. All are wrapped in try/except. Keep the fallbacks.

SECTION 4 - SESSION STATE
-------------------------
`app.py` seeds these persistent keys up front:

Core state:
- `players`
- `teams`
- `stat_category`
- `season_type`
- `x_axis_mode`
- `chart_season`
- `league_filter`
- `team_sel_abbr`

Toggles:
- `do_smooth`
- `do_predict`
- `do_era`
- `do_cumul_toggle`
- `do_base`
- `do_prime`

Comparison tab memory:
- `panel_tab_skater`
- `panel_tab_goalie`
- `panel_tab_team`

One-shot guards:
- `_url_loaded`
- `_default_loaded`
- `_preloaded`

Season-mode memory:
- `_pre_season_chart_x_axis_mode`

Notes:
- URL params are applied once, before defaults settle.
- Shared links can carry compact player IDs and team abbreviations.
- Missing URL params leave defaults alone.
- Extra widget keys like metric selectors are created later by Streamlit widgets.
- `do_cumul` is derived per render, not stored.

SECTION 5 - STRICT SKATER / GOALIE SPLIT
----------------------------------------
This rule matters more than your feelings:

`is_goalie = raw_df['Saves'].sum() > 0 or raw_df['Wins'].sum() > 0`

That check runs on the raw player frame before category-specific charting.
If the app is in Skater mode, goalies are skipped.
If the app is in Goalie mode, skaters are skipped.
Never cross-plot them.

SECTION 6 - DATA PIPELINE (PER PLAYER, PER RENDER)
--------------------------------------------------
`process_players()` runs this order:

1. Fetch raw player data.
   - Normal mode uses `get_player_raw_stats()`.
   - Selected-season mode uses `get_player_season_game_log()` and real NHL game logs.
   - Overview cards can also call cached season-summary leaderboards for league rank text.
2. Apply the skater/goalie gatekeeper.
3. Filter to the selected leagues.
4. If `Era` is on for skaters, apply NHLe to non-NHL `Points`, `Goals`, and `Assists`. If `Era` is off, keep league scoring raw.
5. Filter to `Regular`, `Playoffs`, or `Both`.
6. Apply era adjustment.
7. Branch by chart mode.
   - Selected-season mode: keep one row per real game, sort by `GameDate` + `GameId`, build `CumGP`, preserve `Age` plus exact game metadata (`GameId`, `GameDate`, teams, home/road) for clicks and peak copy.
   - Career Games Played mode: group by `SeasonYear`, build `CumGP`, keep `Age` for clicks.
   - Age mode: group by `Age`, preserve latest `SeasonYear`, compute rate stats.
8. Detect peak before projection, cumsum, and smoothing.
9. If allowed, project to age 40.
   - KNN path uses `run_knn_projection()`.
   - Fallback path uses `run_linear_fallback()`.
   - Current in-progress seasons are pace-adjusted inside the KNN step before clone matching.
10. Apply cumulative mode in Age mode only.
11. Apply 3-season rolling smoothing when enabled.
12. Split real vs projected traces.

Projection gate:
- not in Games Played mode
- not in selected-season mode
- `do_predict` is on
- max age is below 40
- metric is not in `NO_PROJECTION_METRICS`
- thin-data guard passes minimum seasons and GP thresholds

Split behavior:
- real trace uses `Age <= max_age`
- projection trace uses `Age >= max_age`
- the last real point is duplicated into the projected trace for visual continuity

SECTION 7 - HYBRID KNN PROJECTION ENGINE
----------------------------------------
Only runs in Age mode.

KNN rules that matter:
- distance metric is L1
- clone pool is top 10
- clone weights are equal
- clone/prior blend is fixed at 80/20
- percent-change clamp is `[-0.12, +0.25]`
- GP is intentionally excluded from KNN

Matching flow:
1. Filter historical rows by position where possible.
2. Pivot by `PlayerID x Age`.
3. Use mean for rate stats and sum for counting stats.
4. Keep only ages shared by the live player and the historical pivot.
5. Rank players by vectorized L1 distance.
6. Project future ages by mapping clone movement onto the live player.

Projection behavior:
- additive-delta path is used for `+/-`, `GAA`, and `Save %`
- multiplicative path is used for most counting stats
- sparse ages use non-zero fallback targets
- late ages use stabilization instead of trusting tiny clone pools
- stat caps apply every projected year
- `GAA` uses a floor, not a ceiling

GP note:
- the engine still contains a 4-phase durability fallback for GP
- normal app flow suppresses GP projection via `NO_PROJECTION_METRICS = {'GP', 'SH%', 'TOI'}`

SECTION 8 - BASELINE ENGINE
---------------------------
Source: `nhl_historical_seasons.parquet`

Historical baseline pools:
- skaters require at least 40 GP in a season
- goalies require at least 20 GP in a season

Families:
- `Skater`
- `Goalie`

Construction:
1. Take the 75th percentile by age.
2. Smooth with a centered rolling window.
3. Shape late tails so sparse old-age noise does not create fake rebounds.

Tail rules:
- after age 31, rising skater and counting-stat curves use the old `prev * 0.92` guard
- goalie `Save %` and `GAA` do not use that multiplicative rule
- skater late tails blend against recent trusted decline so they do not look like a fake staircase
- goalie `Save %` late tails stay curved and age-aware

Rendering rules:
- player mode uses historical skater or goalie baselines
- team mode uses team baselines
- Games Played mode disables baselines because the stored baseline index is age-based

SECTION 9 - PLOTLY RENDERING GUARDRAILS
---------------------------------------
Visual rules:
- real data = solid colored line with filled markers
- projection = dotted player-colored line with open markers
- baseline = dashed white semi-transparent line with tiny markers

Chart duties handled in `chart.py`:
- concatenate processed frames
- add baseline overlays when enabled
- link each player's projected trace to the same legend toggle so one click hides or shows both
- render compact chart header text and the chart-top single-season selector
- inject JS pan / zoom clamping
- dispatch click data into `show_season_details()`
- offer a Copy link control using compact URL params

Games Played mode chart specifics:
- x-axis uses `CumGP`
- selected-season mode says `Game`; career GP mode says `Career Game`
- single-season click payload stores `Age`, `GameId`, `GameDate`, and `GameType` so the dialog can resolve the exact game
- selected-season mode keeps peak highlights anchored to the real game number, not age

SECTION 10 - CACHING STRATEGY
-----------------------------
Permanent cache:
- `load_historical_data()`
- `load_win_prob_weights()`
- `get_historical_baselines()`
- `load_all_team_seasons()`
- `get_team_baselines()`
- `get_top_50()`
- `get_top_50_goalies()`
- `get_team_roster()`
- `get_player_raw_stats()`
- `get_player_season_game_log()`

Hourly cache (`ttl=3600`):
- `get_player_landing()`
- `get_player_available_nhl_seasons()`
- `get_season_leaderboard()`
- `get_player_season_rank_map()`
- `fetch_all_time_records()`
- `get_id_to_name_map()`
- `search_player()`
- `get_clone_details_map()`
- `get_featured_players()`
- `_get_cached_club_stats()`

Five-minute cache (`ttl=300`):
- `get_live_or_recent_game()`
- `get_upcoming_games()`
- `get_game_details()`
- `get_game_win_probabilities()`

SECTION 10A - PREGAME WIN PROBABILITY
-------------------------------------
Architecture split:
- offline training only: `train_win_prob.py`
- runtime inference only: `nhl/win_prob.py` + `nhl/schedule.py`

Offline trainer rules:
- fetch the last 5 completed regular seasons of NHL team game rows from `team/summary`
- build strict lagged pregame features with zero future leakage
- train `StandardScaler + LogisticRegression` using `scikit-learn`
- export coefficients, intercept, scaler means/scales, selected `C`, and metadata to `win_prob_weights.json`

Runtime rules:
- never retrain inside Streamlit
- never fetch historical seasons at runtime for this feature
- load frozen weights once through `load_win_prob_weights()`
- fetch only the current season game logs for the two teams in the upcoming matchup
- rebuild the same feature vector, score the base probability, then apply the capped goalie Save% proxy

Current feature set:
- season-to-date points %
- season-to-date goal diff per game
- last-10 points %
- last-10 goal diff per game
- season-to-date power-play %

Guardrails:
- no estimate before both teams have at least 5 completed regular-season games
- goalie adjustment is capped at `+/- 0.04`
- goalie text must stay honest: it is a proxy, not a confirmed starter model

Not separately cached, but intentionally fan out from `get_player_landing()`:
- `get_player_headshot()`
- `get_player_current_team()`
- `get_player_roster_info()`
- `get_player_hero_image()`
- `get_player_awards()`
- `get_player_league_abbrevs()`

SECTION 11 - GAMES PLAYED MODE
------------------------------
Purpose: compare careers by accumulated games instead of age, or one selected NHL season by real game number.

Behavior:
- career mode groups by `SeasonYear`, not `Age`
- selected-season mode keeps one row per game
- x-axis is `CumGP`
- counting stats become cumulative totals by game count when cumulative mode is on
- rate stats become rolling visible averages in games mode
- `Age` is preserved for click dialogs, but single-season clicks resolve by exact game identity instead of only age
- Team selected-season mode is a season-progress branch, not the old franchise games view reused.
- Team selected-season metric values are season-to-date after each game: counting stats are cumulative, rate stats are running rates, and `PP%` falls back to the running mean of game PP% because the public team game feed does not expose PP chances.
- Team selected-season clicks now open a team game snapshot dialog with the matchup card and one-row team snapshot table.

Normal app-flow restrictions:
- no projection
- no baseline
- selected-season mode still allows cumulative display, but comparison cards must use the last visible cumulative value instead of summing cumulative rows again

The pipeline still keeps the age metadata, but the single-season dialog now keys off the exact clicked game and can show matchup, score, venue/time, and the player's one-game stat line.

SECTION 12 - MODULAR PACKAGE STRUCTURE
--------------------------------------
Import shape:
- leaf-ish modules: `constants`, `styles`, `era`, `url_params`
- data layer: `data_loaders`, `schedule`, `baselines`
- pure processing: `knn_engine`, `player_pipeline`, `team_pipeline`, `async_preloader`
- UI: `controls`, `sidebar`, `dialog`, `chart`, `comparison`
- `app.py` ties everything together

Module responsibilities:
- `constants.py` - shared URLs, metric lists, caps, floors, league multipliers
- `era.py` - scoring-era multipliers and historical adjustment helpers
- `data_loaders.py` - all parquet and network I/O; keep silent fallbacks
- `baselines.py` - cached historical and team baseline builders
- `knn_engine.py` - clone matching, hybrid-delta projection, stat caps, fallback projection
- `win_prob.py` - leak-safe pregame team features, artifact validation, and dot-product scoring
- `player_pipeline.py` - end-to-end player pipeline and peak metadata
- `team_pipeline.py` - end-to-end team pipeline, including selected-season team season-progress mode
- `controls.py` - top control surface; returns `(metric, do_cumul)`
- `sidebar.py` - player/team add flows plus sidebar status widgets
- `dialog.py` - player clicks, team game snapshot clicks, projection, and baseline dialogs
- `chart.py` - figure assembly, baseline overlay, share-link button, player/team click dispatch
- `comparison.py` - tabbed comparison area with season-aware Overview, Trophies, and Live games including pregame win probability
- `url_params.py` - compact share-link encoder/decoder with legacy link support
- `schedule.py` - live/recent matchup detection, upcoming games, featured players, and runtime pregame win-prob inference
- `async_preloader.py` - background warming of non-active category caches

Key integration notes:
- `schedule.py` only auto-seeds the board on first session load and only if a shared URL did not already populate players or teams
- `comparison.py` stores tab memory per category via `panel_tab_skater`, `panel_tab_goalie`, and `panel_tab_team`
- `train_win_prob.py` is the only place that should import `scikit-learn` for this feature; runtime scoring must stay numpy/pandas only
- selected-season Overview cards prefer league-wide season rank text from the summary endpoints and fall back to the old game-log scope label if rank data is unavailable
- Team chart-season options now come from `load_all_team_seasons()` history for the selected franchises, not from player landing payloads.
- Team selected-season share links now rely on the same forced-games-mode URL logic as skater and goalie season mode.
- `url_params.py` supports compact ID-only links, legacy `id|name` / `abbr|name` links, and the chart-top `chart_season` selector without redundantly encoding forced games mode

That is the architecture. No magic, just disciplined pandas.
