"""Streamlit entry point for NHL Age Curves.

Keeps orchestration in one place and delegates data loading, processing,
charting, and comparison rendering to `nhl/` modules.
"""

import streamlit as st

# --- nhl package imports (each module is documented in nhl/__init__.py) ---
from nhl.async_preloader import preload_all_categories
from nhl.baselines import get_historical_baselines, get_team_baselines
from nhl.chart import render_chart
from nhl.constants import ACTIVE_TEAMS
from nhl.controls import render_controls
from nhl.comparison import render_comparison_area
from nhl.data_loaders import (
    get_clone_details_map,
    get_id_to_name_map,
    get_player_available_nhl_seasons,
    load_all_team_seasons,
    load_historical_data,
)
from nhl.player_pipeline import process_players
from nhl.sidebar import render_sidebar
from nhl.styles import get_favicon_path, inject_css, inject_mobile_dropdown_fix
from nhl.team_pipeline import process_teams
from nhl.schedule import get_featured_players, get_live_or_recent_game
from nhl.url_params import apply_params_to_state, encode_state_to_params


def _resolve_shared_player_names(players: dict[str, str]) -> dict[str, str]:
    """Replace compact shared-link player IDs with display names when possible."""
    if not players:
        return {}

    id_to_name_lookup = {
        str(pid): name
        for category in ("Skater", "Goalie")
        for pid, name in get_id_to_name_map(category).items()
    }
    resolved_players = {}
    for player_id, display_name in players.items():
        clean_player_id = str(player_id).strip()
        clean_display_name = str(display_name or "").strip()
        if clean_display_name and clean_display_name != clean_player_id:
            resolved_players[clean_player_id] = clean_display_name
            continue
        resolved_players[clean_player_id] = id_to_name_lookup.get(
            clean_player_id,
            f"Unknown (ID {clean_player_id})",
        )
    return resolved_players


def _resolve_shared_team_names(teams: dict[str, str]) -> dict[str, str]:
    """Resolve full team names for abbreviations loaded from compact shared URLs.

    Args:
        teams: Dict mapping team abbreviations to names or abbreviation placeholders.

    Returns:
        Dict mapping team abbreviations to full franchise names when available.
    """
    if not teams:
        return {}

    resolved_teams = {}
    for team_abbr, display_name in teams.items():
        clean_team_abbr = str(team_abbr).strip().upper()
        clean_display_name = str(display_name or "").strip()
        if clean_display_name and clean_display_name != clean_team_abbr:
            resolved_teams[clean_team_abbr] = clean_display_name
            continue
        resolved_teams[clean_team_abbr] = ACTIVE_TEAMS.get(clean_team_abbr, clean_team_abbr)
    return resolved_teams


# =============================================================================
# Page configuration — must be the first Streamlit call
# =============================================================================
st.set_page_config(
    page_title="NHL Age Analytics",
    page_icon=get_favicon_path().as_posix(),
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
if 'do_prime'         not in st.session_state: st.session_state.do_prime         = True
if 'x_axis_mode'       not in st.session_state: st.session_state.x_axis_mode       = "Age"
if 'chart_season'      not in st.session_state: st.session_state.chart_season      = "All"
if 'league_filter'     not in st.session_state: st.session_state.league_filter     = ['NHL']
if 'team_sel_abbr'     not in st.session_state:
    st.session_state.team_sel_abbr = list(ACTIVE_TEAMS.keys())[0]
if 'panel_tab_skater'  not in st.session_state: st.session_state.panel_tab_skater  = "overview"
if 'panel_tab_goalie'  not in st.session_state: st.session_state.panel_tab_goalie  = "overview"
if 'panel_tab_team'    not in st.session_state: st.session_state.panel_tab_team    = "overview"
if '_pre_season_chart_x_axis_mode' not in st.session_state:
    st.session_state._pre_season_chart_x_axis_mode = None
if '_pre_season_league_filter' not in st.session_state:
    st.session_state._pre_season_league_filter = None
if '_pre_season_do_era' not in st.session_state:
    st.session_state._pre_season_do_era = None

if st.session_state.stat_category not in {"Skater", "Goalie", "Team"}:
    st.session_state.stat_category = "Skater"

if st.session_state.players and any(
    str(name or "").strip() in ("", str(pid).strip())
    for pid, name in st.session_state.players.items()
):
    st.session_state.players = _resolve_shared_player_names(st.session_state.players)

if st.session_state.teams and any(
    str(name or "").strip() in ("", str(abbr).strip().upper())
    for abbr, name in st.session_state.teams.items()
):
    st.session_state.teams = _resolve_shared_team_names(st.session_state.teams)

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
st.markdown(
    """
    <div class='page-hero'>
        <h1 class='page-header'>
            <img src='https://assets.nhle.com/logos/nhl/svg/NHL_light.svg' class='nhl-logo'>
            <span class='animated-title' style='font-size:0.9em;'>Age Analytics</span>
        </h1>
        <p class='page-subtitle'>Hockey like never before!</p>
    </div>
    """,
    unsafe_allow_html=True,
)

# =============================================================================
# x_axis_mode guard: reset to a valid mode when switching between categories.
# "Age" is not valid in Team mode; "Season Year" is not valid in Player mode.
# =============================================================================
_tm = st.session_state.stat_category == "Team"
if _tm and st.session_state.x_axis_mode == "Age":
    st.session_state.x_axis_mode = "Season Year"
elif not _tm and st.session_state.x_axis_mode == "Season Year":
    st.session_state.x_axis_mode = "Age"

if _tm and st.session_state.chart_season != "All":
    st.session_state.chart_season = "All"

_season_mode_requested = (not _tm) and st.session_state.chart_season != "All"
if _season_mode_requested:
    if st.session_state.x_axis_mode != "Games Played":
        st.session_state._pre_season_chart_x_axis_mode = st.session_state.x_axis_mode
        st.session_state.x_axis_mode = "Games Played"
    if st.session_state.league_filter != ["NHL"]:
        if st.session_state._pre_season_league_filter is None:
            st.session_state._pre_season_league_filter = list(st.session_state.league_filter or ["NHL"])
        st.session_state.league_filter = ["NHL"]
    if st.session_state._pre_season_do_era is None:
        st.session_state._pre_season_do_era = bool(st.session_state.do_era)
    st.session_state.do_era = False
else:
    _saved_x_axis = st.session_state.get("_pre_season_chart_x_axis_mode")
    if _saved_x_axis in {"Age", "Games Played"} and st.session_state.x_axis_mode == "Games Played":
        st.session_state.x_axis_mode = _saved_x_axis
    st.session_state._pre_season_chart_x_axis_mode = None
    _saved_leagues = st.session_state.get("_pre_season_league_filter")
    if isinstance(_saved_leagues, list):
        st.session_state.league_filter = _saved_leagues or ["NHL"]
    st.session_state._pre_season_league_filter = None
    _saved_do_era = st.session_state.get("_pre_season_do_era")
    if isinstance(_saved_do_era, bool):
        st.session_state.do_era = _saved_do_era
    st.session_state._pre_season_do_era = None

# =============================================================================
# Controls — Category/Metric and View Options expanders.
# MUST render before render_sidebar() so control widget keys are registered in
# Streamlit's widget registry before any st.rerun() call from the sidebar can
# interrupt execution. Without this order, Streamlit orphan-cleans the key=
# widget entries on player removal and the init block resets them to False.
# The main content split is created before controls so the comparison panel can
# start higher on desktop while still stacking below the chart on smaller widths.
# Returns (metric, do_cumul): do_cumul is already resolved (False for rate stats,
# False in games_mode) so pipelines and chart don't need to recompute it.
# =============================================================================
_show_panel = True

st.markdown("<div id='main-chart-layout'></div>", unsafe_allow_html=True)

if _show_panel:
    col_chart, col_stats = st.columns([68, 32], gap="medium")
else:
    col_chart = st.container()
    col_stats = None

with col_chart:
    metric, do_cumul = render_controls()

# =============================================================================
# Sidebar — renders player/team board and returns keys for chart cache-busting.
# Rendered after controls so toggle keys survive any st.rerun() triggered here.
# =============================================================================
sidebar_keys = render_sidebar()

# =============================================================================
# Derived flags (read after controls have written to session state)
# =============================================================================
team_mode = st.session_state.stat_category == "Team"

# Active player board — shared across Skater and Goalie categories.
# The pipeline's is_goalie gatekeeper filters per category at render time.
active_players = {} if team_mode else st.session_state.players

chart_season_options: list[str | int] = ["All"]
if active_players:
    available_chart_seasons: set[int] = set()
    for _pid in active_players.keys():
        try:
            available_chart_seasons.update(get_player_available_nhl_seasons(int(_pid)))
        except Exception:
            continue
    chart_season_options.extend(sorted(available_chart_seasons, reverse=True))

if st.session_state.chart_season not in chart_season_options:
    st.session_state.chart_season = "All"
    _saved_x_axis = st.session_state.get("_pre_season_chart_x_axis_mode")
    if _saved_x_axis in {"Age", "Games Played"} and st.session_state.x_axis_mode == "Games Played":
        st.session_state.x_axis_mode = _saved_x_axis
    st.session_state._pre_season_chart_x_axis_mode = None
    _saved_leagues = st.session_state.get("_pre_season_league_filter")
    if isinstance(_saved_leagues, list):
        st.session_state.league_filter = _saved_leagues or ["NHL"]
    st.session_state._pre_season_league_filter = None

season_mode = (not team_mode) and st.session_state.chart_season != "All"
games_mode = st.session_state.x_axis_mode == "Games Played"
do_base = st.session_state.do_base and not team_mode and not season_mode
do_prime = st.session_state.do_prime and not season_mode
share_params = encode_state_to_params(st.session_state)

# =============================================================================
# Shared data: historical parquet + baselines
# Cached permanently — only recomputed when the parquet file changes.
# =============================================================================
hist_df              = load_historical_data()
historical_baselines = get_historical_baselines()

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
    team_baselines = get_team_baselines()

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
        selected_season   = st.session_state.chart_season,
        league_filter     = st.session_state.league_filter,
    )

# =============================================================================
# Chart rendering (shared by both pipelines)
# Keep the comparison panel visible even on an empty board so the Live games
# tab can seed players and teams without forcing the user through the sidebar.
# The main split already started above so the right panel can sit beside the
# controls on desktop and stack below the chart on smaller widths.
# =============================================================================
with col_chart:
    render_chart(
        processed_dfs        = processed_dfs,
        metric               = metric,
        team_mode            = team_mode,
        games_mode           = games_mode,
        do_cumul             = do_cumul,
        do_base              = do_base,
        do_smooth            = st.session_state.do_smooth,
        stat_category        = st.session_state.stat_category,
        historical_baselines = historical_baselines,
        team_baselines       = team_baselines,
        raw_dfs_cache        = raw_dfs_cache,
        ml_clones_dict       = ml_clones_dict,
        season_type          = st.session_state.season_type,
        sidebar_keys         = sidebar_keys,
        peak_info            = peak_info,
        do_prime             = do_prime,
        do_era               = st.session_state.do_era,
        selected_season      = st.session_state.chart_season,
        share_params         = share_params,
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
            selected_season = st.session_state.chart_season,
            chart_season_options = chart_season_options,
            do_cumul      = do_cumul,
        )

# =============================================================================
# Footer
# =============================================================================
st.markdown("---")
# Keep this visible version synced with the newest changelog entry
st.markdown(
    "<p style='text-align:center;color:gray;font-size:14px;'>"
    "Created by Iksperial. v0.83.1 -- 5545 lines of Python<br>"
    "<em>Data is the only religion that strictly punishes you for ignoring it.</em>"
    "</p>",
    unsafe_allow_html=True,
)
