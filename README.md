# NHL Player Age Curves & Career Projections 🏒
An interactive analytics dashboard built in Python that visualizes aging curves and career trajectories for NHL players using live data and machine learning projections.

## Available online here
https://nhl-age-curves.streamlit.app/

## Features
* **Live API Integration:** Pulls real time data directly from the NHL's undocumented public API including player stats, team rosters, and all time records leaderboards.
* **KNN Machine Learning Projections:** Projects player performance to age 40 using a K-Nearest Neighbors algorithm that finds the 10 most statistically similar historical players (position matched) and maps their career trajectories onto the current player.
* **Era Adjusted Scoring:** Normalizes points across NHL eras the high scoring 80s, the Dead Puck era, and the modern game so historical comparisons are apples to apples.
* **75th Percentile Baseline:** Toggle a "Top 6 Forward / Starting Goalie" reference curve built from a historical database of all NHL seasons, with survivorship bias correction applied after age 31.
* **Dual Class Architecture:** Natively supports and separates skaters from goaltenders, rendering entirely different metrics (e.g., Save Percentage vs. Points Per Game).
* **Cumulative Tracking:** Toggle a race chart view to see cumulative career stats by age rather than single season points.
* **Season Snapshot:** Click any data point on the chart to see that player's exact season stats at that age and their projected all time career rank.

## Tech Stack
* **Frontend/Framework:** Streamlit
* **Data & ML:** Pandas, custom KNN implementation
* **Visualization:** Plotly Express
* **Networking:** Requests (REST API)
* **Local Database:** Parquet via `pyarrow` or `fastparquet`

## How to Run Locally
1. Clone this repository.
2. Install the requirements: `pip install -r requirements.txt`
3. Ensure `nhl_historical_seasons.parquet` is present in the root directory (required for ML projections and baseline). Run `scraper.py` to generate or refresh it.
4. Run the app: `streamlit run app.py`
