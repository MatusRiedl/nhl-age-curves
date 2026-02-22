# NHL Player Age Curves & Career Projections 🏒

An interactive, web-based analytics dashboard built in Python that visualizes the aging curves and career trajectories of NHL players using live data.

## Available online here
https://nhl-age-curves.streamlit.app/

## Features
* **Live API Integration:** Pulls real-time, unstructured JSON data directly from the NHL's undocumented web API.
* **Era-Adjusted Scoring:** Includes a mathematical modifier to normalize points across different NHL eras (e.g., the high-scoring 80s vs. the Dead Puck era).
* **Predictive Projections:** Applies standard hockey analytics decay models to project a player's statistical decline out to age 40 based on their current age and specific metric.
* **Dual-Class Architecture:** Natively supports and separates skaters from goaltenders, rendering entirely different metrics (e.g., Save Percentage vs. Points Per Game).
* **Cumulative Tracking:** Toggle a race-chart view to see cumulative career stats by age rather than single-season points. 

## Tech Stack
* **Frontend/Framework:** Streamlit
* **Data Manipulation:** Pandas
* **Visualization:** Plotly Express
* **Networking:** Requests (REST API)

## How to Run Locally
1. Clone this repository.
2. Install the requirements: `pip install -r requirements.txt`
3. Run the app: `streamlit run app.py`
