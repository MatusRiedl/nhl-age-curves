# NHL Player Age Curves & Career Projections 🏒
Hockey analytics & projections

## Available online here
https://nhl-age-curves.streamlit.app/

## Features

* **Live API Integration:** Pulls real-time data directly from the NHL's undocumented public API: player stats, team rosters, and all-time records leaderboards.

* **Hybrid KNN Projections:** Projects player performance to age 40 from the 10 nearest historical matches using L1 distance, equal-weight top-10 clone influence, a fixed 80/20 blend, and late-age stabilization when clone data gets thin.

* **Era-Adjusted Scoring:** Normalizes Points, Goals, and Assists independently across 8 NHL eras (the high-scoring 80s, the Dead Puck era, the modern game, etc.) using historical goals-per-game data so comparisons across generations are apples-to-apples.

* **75th Percentile Historical Baselines:** Toggle aggregate Skater and Goalie reference curves built from historical parquet data, with classic survivorship shaping and the preserved late-tail fixes.

* **Multi-League NHLe Support:** Include non-NHL seasons (KHL, SHL, AHL, NCAA, OHL, WHL, and more) with automatic NHLe conversion factors applied to Points, Goals, and Assists before entering the pipeline.

* **Games Played X-Axis Mode:** Switch the X-axis from Age to career Games Played. Every player shares a common (0, 0) origin so you can compare players at the same point in career experience instead of pretending missed seasons never happened.

* **Single-Season Game-Log Mode:** Use the chart-top `Chart season` selector next to the header to switch skaters, goalies, or teams from the default `All` history view into one real NHL season. Picking `2024-25`, `2023-24`, etc. forces the X-axis to individual games and plots actual game-log rows instead of season aggregates.

* **Triple Class Architecture:** Natively separates skaters, goaltenders and teams, rendering entirely different metric sets (Save Percentage vs. Points Per Game, etc.).

* **Cumulative Tracking:** Toggle a race chart view to see cumulative career stats rather than single-season values.

* **Season Snapshot:** In single-season mode, click any game to see the exact matchup card with both teams, logos, final score, venue/time when available, plus the player or team one-game stat line. Age-mode and projection clicks still keep the broader season/career context.

* **Live Games Quick-Add:** A dedicated comparison tab lists the next 4 upcoming games, shows venue, converts puck drop into Central European local time (CET/CEST), and can add both teams plus each club's current points leader and best Save% goalie in one click.

* **Pregame Win Probability:** The Live games tab also shows a pregame away/home win estimate for each upcoming matchup. The base probability comes from an offline-trained logistic regression on the last 5 completed NHL regular seasons, then a capped goalie Save% proxy is layered on top at runtime.

* **Shareable URLs:** Click the chart's **Copy link** control to copy a compact exact-state URL only when you want to share it. Player and team names are omitted from the query string, default values are skipped, and the browser URL stays clean while you explore.

* **Dynamic Search:** Type a player's first or last name to get live results. Selecting a match immediately adds them to the chart, no separate button required.

* **Mobile Friendly Layout:** Controls are organized into collapsible expander sections so the chart stays front-and-center on smaller screens.

* **Player Headshots:** Each active roster entry in the sidebar shows the player's circular headshot thumbnail pulled from the NHL API.

## Tech Stack
* **Frontend/Framework:** Streamlit
* **Data & ML:** Pandas, PyArrow, custom hybrid KNN implementation, offline scikit-learn logistic regression for pregame win probability
* **Visualization:** Plotly
* **Networking:** Requests (REST API)
* **Local Artifacts:** Parquet (`nhl_historical_seasons.parquet`) and exported win-probability weights (`win_prob_weights.json`)

## Code Structure

The app is organized as a Python package under `nhl/`. `app.py` is the
session-state orchestrator and render pass; most logic lives in the package modules.

```
app.py                   entry point and session-state orchestrator
nhl/
    constants.py         URLs, team list, stat caps, NHLe multipliers
    styles.py            CSS injection
    era.py               era-adjustment math (no Streamlit dependency)
    data_loaders.py      cached API fetch, season discovery, game-log, and parquet loaders
    baselines.py         aggregate historical baseline builders
    knn_engine.py        hybrid KNN projection engine
    win_prob.py          shared pregame win-probability feature engineering and runtime scoring
    player_pipeline.py   full per-player pipeline, including single-season game-log mode
    team_pipeline.py     team comparison pipeline
    controls.py          Category/Metric and View Options expanders
    sidebar.py           player and team sidebar UI
    dialog.py            season-detail popup dialog
    chart.py             Plotly chart rendering, chart-top season selector, share link, and JS pan-clamp
    comparison.py        tabbed comparison panel with season-aware Overview, Trophies, and Live games
    url_params.py        URL query param encode/decode for shareable links and chart season state
    schedule.py          live defaults, upcoming games, featured-player helpers, and runtime matchup inference
    async_preloader.py   background cache warming for Goalie/Team categories
scraper.py               standalone script to refresh the parquet file
train_win_prob.py        standalone script to train and export pregame win-probability weights
nhl_historical_seasons.parquet   ML backbone (generate with scraper.py)
win_prob_weights.json    offline-trained logistic-regression weights used at runtime
```

## How to Run Locally
1. Download latest standalone Python installer from https://www.python.org/downloads/ and during installation, check the box to "add Python to PATH"
2. Download this repository https://github.com/MatusRiedl/nhl-age-curves/archive/refs/heads/main.zip and extract it somewhere
3. Open the extracted folder, hold Shift and right click on empty space in the folder and click on "Open in Terminal"
4. Type this into terminal and hit Enter: `pip install -r requirements.txt`
5. Ensure `nhl_historical_seasons.parquet` is present in the root directory (required for KNN projections and baselines)
6. Ensure `win_prob_weights.json` is present in the root directory (required for pregame win probability in the Live games tab)
7. If you want to refresh the historical parquet, run `python scraper.py`
8. If you want to retrain the pregame win-probability model, run `python train_win_prob.py`
9. Launch the app by opening a terminal in the folder and write `streamlit run app.py`
