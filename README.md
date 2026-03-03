# NHL Player Age Curves & Career Projections 🏒
An interactive analytics dashboard built in Python that visualizes aging curves and career trajectories for NHL players using live data and machine learning projections.

## Available online here
https://nhl-age-curves.streamlit.app/

## Features

* **Live API Integration:** Pulls real-time data directly from the NHL's undocumented public API: player stats, team rosters, and all-time records leaderboards.

* **KNN Machine Learning Projections:** Projects player performance to age 40 using a K-Nearest Neighbors algorithm. Matches against a database of ~8,500 NHL careers using full-career shape (not just recent seasons). An elite-tier pre-filter ensures top players are compared against historically similar talent levels (McDavid clones from Gretzky/Lemieux/Crosby, not role players).

* **Era-Adjusted Scoring:** Normalizes Points, Goals, and Assists independently across 8 NHL eras (the high-scoring 80s, the Dead Puck era, the modern game, etc.) using historical goals-per-game data so comparisons across generations are apples-to-apples.

* **75th Percentile Baseline:** Toggle a "Top 6 Forward / Starting Goalie" reference curve built from historical parquet data, with survivorship bias correction applied after age 31 (flat-or-rising baselines are overridden with a monotonic decay).

* **Multi-League NHLe Support:** Include non-NHL seasons (KHL, SHL, AHL, NCAA, OHL, WHL, and more) with automatic NHLe conversion factors applied to Points, Goals, and Assists before entering the pipeline.

* **Games Played X-Axis Mode:** Switch the X-axis from Age to career Games Played. Every player shares a common (0, 0) origin so you can directly compare players at the same point in career experience, normalizing for injuries and missed time.

* **Triple Class Architecture:** Natively separates skaters, goaltenders and teams, rendering entirely different metric sets (Save Percentage vs. Points Per Game, etc.).

* **Cumulative Tracking:** Toggle a race chart view to see cumulative career stats rather than single-season values.

* **Season Snapshot:** Click any data point to see that player's exact season stats at that age and their projected all-time career rank.

* **Shareable URLs:** All chart state (players on board, metric, toggles, category, season type) is encoded into the browser URL automatically. Copy the URL to share an exact comparison with anyone.

* **Dynamic Search:** Type a player's first or last name to get live results. Selecting a match immediately adds them to the chart, no separate button required.

* **Mobile Friendly Layout:** Controls are organized into collapsible expander sections so the chart stays front-and-center on smaller screens.

* **Player Headshots:** Each active roster entry in the sidebar shows the player's circular headshot thumbnail pulled from the NHL API.

## Tech Stack
* **Frontend/Framework:** Streamlit
* **Data & ML:** Pandas, PyArrow, custom KNN implementation
* **Visualization:** Plotly
* **Networking:** Requests (REST API)
* **Local Database:** Parquet (`nhl_historical_seasons.parquet`)

## Code Structure

The app is organized as a Python package under `nhl/`. `app.py` is a thin
~200-line orchestrator; all logic lives in the package modules.

```
app.py                   entry point and session-state orchestrator
nhl/
    constants.py         URLs, team list, stat caps, NHLe multipliers
    styles.py            CSS injection
    era.py               era-adjustment math (no Streamlit dependency)
    data_loaders.py      cached API fetch and parquet load functions
    baselines.py         75th-percentile baseline builders
    knn_engine.py        KNN projection engine (no Streamlit, testable)
    player_pipeline.py   full per-player data pipeline
    team_pipeline.py     team comparison pipeline
    controls.py          Category/Metric and View Options expanders
    sidebar.py           player and team sidebar UI
    dialog.py            season-detail popup dialog
    chart.py             Plotly chart rendering and JS pan-clamp
    comparison.py        player stat comparison panel
    url_params.py        URL query param encode/decode for shareable links
    schedule.py          live/recent game detection for chart auto-population
    async_preloader.py   background cache warming for Goalie/Team categories
scraper.py               standalone script to refresh the parquet file
nhl_historical_seasons.parquet   ML backbone (generate with scraper.py)
```

## How to Run Locally
1. Download latest standalone Python installer from https://www.python.org/downloads/ and during installation, check the box to "add Python to PATH"
2. Download this repository https://github.com/MatusRiedl/nhl-age-curves/archive/refs/heads/main.zip and extract it somewhere
3. Open the extracted folder, hold Shift and right click on empty space in the folder and click on "Open in Terminal"
4. Type this into terminal and hit Enter: `pip install -r requirements.txt`
5. Ensure `nhl_historical_seasons.parquet` is present in the root directory (required for ML projections and baseline)
6. If you want to update the historical file, open terminal in the folder and write `python scraper.py` to generate it
7. Launch the app by opening a terminal in the folder and write `streamlit run app.py`