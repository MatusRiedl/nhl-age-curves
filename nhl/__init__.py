"""
nhl — NHL Age Curves package.

This package splits the single-file app.py into focused modules:

    constants       — shared configuration, URLs, lookup tables, caps/floors
    styles          — CSS injection for Streamlit page styling
    era             — era-adjustment math (multipliers, offsets, DataFrame helpers)
    data_loaders    — all cached API fetch and parquet load functions
    baselines       — historical and team 75th-percentile baseline builders
    knn_engine      — KNN ML projection engine (no Streamlit dependency)
    player_pipeline — per-player data processing loop
    team_pipeline   — per-team data processing loop
    controls        — Category/Metric and View Options expanders (Streamlit UI)
    sidebar         — player and team sidebar UI (Streamlit UI)
    dialog          — @st.dialog season-detail popup
    chart           — Plotly chart rendering + JS pan-clamp injection
    comparison      — right-column player stat cards (hero image, career totals, best season)
"""
