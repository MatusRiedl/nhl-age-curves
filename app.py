"""
NHL Age Curves — Main Application Entry Point

This file is the thin orchestrator.  All logic lives in the nhl/ package modules.
Streamlit re-executes this file top-to-bottom on every user interaction.

Module responsibilities:
    nhl.styles          — inject_css(): animated title, logo, sidebar, modebar CSS
    nhl.constants       — ACTIVE_TEAMS and all shared constants
    nhl.data_loaders    — load_historical_data(), load_all_team_seasons(),
                          get_id_to_name_map(), get_clone_details_map()
    nhl.baselines       — build_historical_baselines(), build_team_baselines()
    nhl.sidebar         — render_sidebar(): player/team board + search UI
    nhl.controls        — render_controls(): Category/Metric + View Options expanders
    nhl.player_pipeline — process_players(): full per-player data pipeline
    nhl.team_pipeline   — process_teams(): per-team data pipeline
    nhl.chart           — render_chart(): Plotly figure + JS clamping + click dialog
    nhl.comparison      — render_comparison_area(): tabbed right-column comparison panel
"""

import streamlit as st

# --- nhl package imports (each module is documented in nhl/__init__.py) ---
from nhl.async_preloader import preload_all_categories
from nhl.baselines import build_historical_baselines, build_team_baselines
from nhl.chart import render_chart
from nhl.constants import ACTIVE_TEAMS
from nhl.controls import render_controls
from nhl.comparison import render_comparison_area
from nhl.data_loaders import (
    get_clone_details_map,
    get_id_to_name_map,
    load_all_team_seasons,
    load_historical_data,
)
from nhl.player_pipeline import process_players
from nhl.sidebar import render_sidebar
from nhl.styles import inject_css, inject_mobile_dropdown_fix
from nhl.team_pipeline import process_teams
from nhl.schedule import get_featured_players, get_live_or_recent_game
from nhl.url_params import apply_params_to_state, encode_state_to_params

# =============================================================================
# Page configuration — must be the first Streamlit call
# =============================================================================
st.set_page_config(
    page_title="NHL Age Curves",
    layout="wide",
    initial_sidebar_state="expanded",
)
inject_css()
inject_mobile_dropdown_fix()

# =============================================================================
# URL params — load once per session, before session state defaults are applied.
# The "not in" guards below mean URL-loaded values will not be overwritten.
# =============================================================================
if "_url_loaded" not in st.session_state:
    apply_params_to_state(dict(st.query_params), st.session_state)
    st.session_state["_url_loaded"] = True

# =============================================================================
# Session state initialization
# All keys that any module reads must be seeded here before the first widget run.
# =============================================================================
if 'players'           not in st.session_state: st.session_state.players           = {}
if 'teams'             not in st.session_state: st.session_state.teams             = {}
if 'stat_category'     not in st.session_state: st.session_state.stat_category     = "Skater"
if 'season_type'       not in st.session_state: st.session_state.season_type       = "Regular"
if 'do_smooth'         not in st.session_state: st.session_state.do_smooth         = False
if 'do_predict'        not in st.session_state: st.session_state.do_predict        = True
if 'do_era'            not in st.session_state: st.session_state.do_era            = False
if 'do_cumul_toggle'   not in st.session_state: st.session_state.do_cumul_toggle   = False
if 'do_base'           not in st.session_state: st.session_state.do_base           = True
if 'x_axis_mode'       not in st.session_state: st.session_state.x_axis_mode       = "Age"
if 'league_filter'     not in st.session_state: st.session_state.league_filter     = ['NHL']
if 'team_sel_abbr'     not in st.session_state:
    st.session_state.team_sel_abbr = list(ACTIVE_TEAMS.keys())[0]
if 'panel_tab_skater'  not in st.session_state: st.session_state.panel_tab_skater  = "overview"
if 'panel_tab_goalie'  not in st.session_state: st.session_state.panel_tab_goalie  = "overview"
if 'panel_tab_team'    not in st.session_state: st.session_state.panel_tab_team    = "overview"

# =============================================================================
# Auto-populate from live/recent NHL game — fires once per session, only when
# no players or teams were loaded from a shared URL.
# =============================================================================
if "_default_loaded" not in st.session_state:
    st.session_state["_default_loaded"] = True
    if not st.session_state.players and not st.session_state.teams:
        _game = get_live_or_recent_game()
        if _game:
            _featured = get_featured_players(*_game)
            st.session_state.players.update(_featured["players"])
            st.session_state.teams.update(_featured["teams"])

# =============================================================================
# Async preloading — warm the cache for other categories in the background
# Fires once per session. Goalie and Team data load while user views Skaters.
# =============================================================================
if "_preloaded" not in st.session_state:
    st.session_state["_preloaded"] = True
    preload_all_categories(st.session_state.stat_category)

# =============================================================================
# Page header
# =============================================================================
st.markdown("""
    <h1 style='display:flex;align-items:center;padding-bottom:0;margin-bottom:0;'>
        <img src='https://assets.nhle.com/logos/nhl/svg/NHL_light.svg' class='nhl-logo'>
        <span class='animated-title' style='font-size:0.9em;'>Age Curves</span>
    </h1>
""", unsafe_allow_html=True)
st.markdown("---")

# =============================================================================
# x_axis_mode guard: reset to a valid mode when switching between categories.
# "Age" is not valid in Team mode; "Season Year" is not valid in Player mode.
# =============================================================================
_tm = st.session_state.stat_category == "Team"
if _tm and st.session_state.x_axis_mode == "Age":
    st.session_state.x_axis_mode = "Season Year"
elif not _tm and st.session_state.x_axis_mode == "Season Year":
    st.session_state.x_axis_mode = "Age"

# =============================================================================
# Controls — Category/Metric and View Options expanders.
# MUST render before render_sidebar() so toggle widget keys are registered in
# Streamlit's widget registry before any st.rerun() call from the sidebar can
# interrupt execution. Without this order, Streamlit orphan-cleans the key=
# widget entries on player removal and the init block resets them to False.
# Returns (metric, do_cumul): do_cumul is already resolved (False for rate stats,
# False in games_mode) so pipelines and chart don't need to recompute it.
# =============================================================================
metric, do_cumul = render_controls()

# =============================================================================
# Sidebar — renders player/team board and returns keys for chart cache-busting.
# Rendered after controls so toggle keys survive any st.rerun() triggered here.
# =============================================================================
sidebar_keys = render_sidebar()

# =============================================================================
# Derived flags (read after controls have written to session state)
# =============================================================================
team_mode  = st.session_state.stat_category == "Team"
games_mode = st.session_state.x_axis_mode == "Games Played"

# Active player board — shared across Skater and Goalie categories.
# The pipeline's is_goalie gatekeeper filters per category at render time.
active_players = {} if team_mode else st.session_state.players

# =============================================================================
# Shared data: historical parquet + baselines
# Cached permanently — only recomputed when the parquet file changes.
# =============================================================================
hist_df              = load_historical_data()
historical_baselines = build_historical_baselines(hist_df)

# id_to_name_map and clone_details_map are only needed in player mode (KNN engine)
if not team_mode:
    id_to_name_map    = get_id_to_name_map(st.session_state.stat_category)
    clone_details_map = get_clone_details_map(st.session_state.stat_category)
else:
    id_to_name_map    = {}
    clone_details_map = {}

# =============================================================================
# Pipeline dispatch
# =============================================================================
processed_dfs  = []
raw_dfs_cache  = []
ml_clones_dict = {}
peak_info      = {}
team_baselines = {}

if team_mode:
    # ── Team pipeline ─────────────────────────────────────────────────
    all_team_df    = load_all_team_seasons()
    team_baselines = build_team_baselines(all_team_df)

    if all_team_df.empty or "teamAbbrev" not in all_team_df.columns:
        st.warning(
            "Team stats could not be loaded — NHL API may be temporarily unavailable. "
            "Try refreshing."
        )

    if st.session_state.teams:
        processed_dfs = process_teams(
            teams       = st.session_state.teams,
            all_team_df = all_team_df,
            metric      = metric,
            season_type = st.session_state.season_type,
            do_cumul    = do_cumul,
            do_smooth   = st.session_state.do_smooth,
            games_mode  = games_mode,
        )

elif active_players:
    # ── Player pipeline ────────────────────────────────────────────────
    processed_dfs, raw_dfs_cache, ml_clones_dict, peak_info = process_players(
        players           = active_players,
        metric            = metric,
        hist_df           = hist_df,
        id_to_name_map    = id_to_name_map,
        clone_details_map = clone_details_map,
        season_type       = st.session_state.season_type,
        stat_category     = st.session_state.stat_category,
        do_era            = st.session_state.do_era,
        do_predict        = st.session_state.do_predict,
        do_smooth         = st.session_state.do_smooth,
        do_cumul          = do_cumul,
        games_mode        = games_mode,
        league_filter     = st.session_state.league_filter or ['NHL'],
    )

# =============================================================================
# Chart rendering (shared by both pipelines)
# Stats panel is always visible in player mode when players are loaded.
# Desktop: 65/35 split (chart left, stats right). Mobile: stacked via CSS.
# =============================================================================
_show_panel = bool(processed_dfs)

if _show_panel:
    col_chart, col_stats = st.columns([65, 35], gap="medium")
else:
    col_chart = st.container()
    col_stats = None

with col_chart:
    render_chart(
        processed_dfs        = processed_dfs,
        metric               = metric,
        team_mode            = team_mode,
        games_mode           = games_mode,
        do_cumul             = do_cumul,
        do_base              = st.session_state.do_base and st.session_state.stat_category != "Goalie",
        do_smooth            = st.session_state.do_smooth,
        stat_category        = st.session_state.stat_category,
        historical_baselines = historical_baselines,
        team_baselines       = team_baselines,
        raw_dfs_cache        = raw_dfs_cache,
        ml_clones_dict       = ml_clones_dict,
        season_type          = st.session_state.season_type,
        sidebar_keys         = sidebar_keys,
    )

if col_stats is not None:
    with col_stats:
        render_comparison_area(
            processed_dfs = processed_dfs,
            players       = active_players,
            teams         = st.session_state.teams,
            peak_info     = peak_info,
            metric        = metric,
            stat_category = st.session_state.stat_category,
            season_type   = st.session_state.season_type,
            team_mode     = team_mode,
        )

# =============================================================================
# Sync current state to URL (does not trigger a rerun in Streamlit 1.30+)
# =============================================================================
st.query_params.clear()
st.query_params.update(encode_state_to_params(st.session_state))

# =============================================================================
# Footer
# =============================================================================
st.markdown("---")
st.markdown(
    "<p style='text-align:center;color:gray;font-size:14px;'>"
    "Created by Iksperial. v0.55 <br>"
    "<em>Data is the only religion that strictly punishes you for ignoring it.</em>"
    "</p>",
    unsafe_allow_html=True,
)
