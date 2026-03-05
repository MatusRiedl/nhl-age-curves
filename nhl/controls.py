"""
nhl.controls — Category/Metric expander for the NHL Age Curves app.

Renders a single "Category & Metric" expander that appears below the page title.
It contains all controls in two rows:
    Row 1: 5 toggles spread across the full expander width (category radio lives
           in the sidebar)
    Row 2: X-Axis, Select Metric, Season Type, Leagues dropdowns (compact, left→right)

The expander uses expanded=True so it is always open on every rerun, ensuring toggles
remain visible after player add/remove actions.

Reads and writes st.session_state directly (that is the correct Streamlit pattern
for widget state).  Returns (metric, do_cumul) so app.py can pass both values into
the pipelines and chart renderer without reading session state itself.

Imports from project:
    nhl.constants — TEAM_METRICS, RATE_STATS, TEAM_RATE_STATS
    nhl.data_loaders — get_player_league_abbrevs
"""

import streamlit as st

from nhl.constants import RATE_STATS, TEAM_METRICS, TEAM_RATE_STATS, normalize_league_abbrev
from nhl.data_loaders import get_player_league_abbrevs


def render_controls() -> tuple:
    """Render the unified Category & Metric expander with all controls.

    The expander uses expanded=True so it is always open on every rerun, ensuring
    toggles remain visible and accessible after player add/remove actions.

    A single expander holds two rows:
        Row 1 — 5 toggles spread across the full expander width. The category
                radio (Skater/Goalie/Team) is rendered in the sidebar instead.
        Row 2 — X-Axis, Select Metric, Season Type, Leagues dropdowns.

    Reads:
        st.session_state.stat_category   — drives metric selectbox options
        st.session_state.x_axis_mode     — determines which mode note to show
        st.session_state.do_cumul_toggle — raw toggle value
        st.session_state.league_filter   — current league multiselect
    Writes (via widget keys):
        x_axis_mode, league_filter, season_type,
        do_smooth, do_predict, do_era, do_cumul_toggle, do_base, do_prime

    Returns:
        Tuple of (metric, do_cumul):
            metric   — currently selected stat metric string (e.g. 'Points').
            do_cumul — resolved cumulative flag: True only when the toggle is on,
                       the metric is not a rate stat, and games_mode is False.
    """
    team_mode   = st.session_state.stat_category == "Team"
    games_mode  = st.session_state.x_axis_mode == "Games Played"

    with st.expander("📊 Category & Metric", expanded=False):
        # ------------------------------------------------------------------
        # Row 1: Compact toggles row
        # ------------------------------------------------------------------
        _cumul_rate_set = TEAM_RATE_STATS if team_mode else RATE_STATS

        st.markdown("<div id='controls-row1'></div>", unsafe_allow_html=True)

        c_t1, c_t2, c_t3, c_t4, c_t5, c_t6 = st.columns(
            [1, 1, 1, 1, 1, 1], vertical_alignment="center"
        )

        with c_t1:
            st.toggle("Smoothing", key="do_smooth")

        with c_t2:
            if team_mode:
                st.toggle("Forecast", value=False, disabled=True)
            else:
                st.toggle("Forecast", key="do_predict", disabled=games_mode)

        with c_t3:
            if team_mode:
                st.toggle("Era-Adjust", value=False, disabled=True)
            else:
                st.toggle("Era-Adjust", key="do_era")

        with c_t4:
            st.toggle("Cumulative", key="do_cumul_toggle")

        with c_t5:
            st.toggle("Baseline", key="do_base", disabled=games_mode)

        with c_t6:
            st.toggle("Show Prime", key="do_prime")

        # ------------------------------------------------------------------
        # Row 2: X-Axis | Select Metric | Season Type | Leagues dropdowns
        # ------------------------------------------------------------------
        _x_opts = (
            ["Season Year", "Games Played"]
            if st.session_state.stat_category == "Team"
            else ["Age", "Games Played"]
        )

        st.markdown("<div id='controls-dropdowns'></div>", unsafe_allow_html=True)
        c_xaxis, c_metric, c_season, c_league = st.columns(
            [1.5, 1.5, 1.5, 2], vertical_alignment="top"
        )

        with c_xaxis:
            st.selectbox(
                "X-Axis",
                _x_opts,
                key="x_axis_mode",
                help=(
                    "Season Year: plot by NHL season (teams). "
                    "Age: plot by player age. "
                    "Games Played: cumulative game number."
                ),
            )

        with c_metric:
            if st.session_state.stat_category == "Skater":
                metric = st.selectbox(
                    "Select Metric",
                    ["Points", "Goals", "Assists", "+/-", "GP", "PPG", "SH%", "PIM", "TOI"],
                    key="skater_metric",
                    help=(
                        "+/-: Plus/Minus Differential | GP: Games Played | "
                        "PPG: Points Per Game | SH%: Shooting Percentage | "
                        "PIM: Penalty Minutes | TOI: Time on Ice (Avg Mins)"
                    ),
                )
            elif st.session_state.stat_category == "Goalie":
                metric = st.selectbox(
                    "Select Metric",
                    ["Save %", "GAA", "Shutouts", "Wins", "GP", "Saves"],
                    key="goalie_metric",
                    help=(
                        "Save %: Save Percentage | GAA: Goals Against Average | "
                        "GP: Games Played | Saves: Total Saves"
                    ),
                )
            else:
                metric = st.selectbox(
                    "Select Metric",
                    TEAM_METRICS,
                    key="team_metric",
                    help=(
                        "Points: standings pts | Wins: wins per season | Win%: pts pct | "
                        "Goals: team GF | GF/G: goals for/game | GA/G: goals against/game | "
                        "PP%: power play % | PPG: team scoring pts/game (est.)"
                    ),
                )

        with c_season:
            st.selectbox("Season Type", ["Regular", "Playoffs", "Both"], key="season_type")

        with c_league:
            if team_mode:
                st.multiselect(
                    "Leagues",
                    options=["NHL"],
                    default=["NHL"],
                    disabled=True,
                    help="Unavailable in Team mode.",
                )
            else:
                # Dynamic league universe from currently loaded players.
                _player_ids: set[int] = set()
                for _board_key in ("players", "skater_players", "goalie_players"):
                    _board = st.session_state.get(_board_key, {}) or {}
                    if isinstance(_board, dict):
                        for _pid in _board.keys():
                            try:
                                _player_ids.add(int(_pid))
                            except Exception:
                                continue

                _league_set = {"NHL"}
                for _pid in _player_ids:
                    for _lg in get_player_league_abbrevs(_pid):
                        if _lg:
                            _league_set.add(_lg)

                _non_nhl_sorted = sorted(
                    (lg for lg in _league_set if normalize_league_abbrev(lg) != "NHL"),
                    key=lambda s: s.upper(),
                )
                _league_options = ["NHL"] + _non_nhl_sorted

                # Keep current selection valid against dynamic options via normalized match.
                _current_selection = st.session_state.get("league_filter")
                if _current_selection is None:
                    _current_selection = ["NHL"]
                _norm_to_display: dict[str, str] = {}
                for _opt in _league_options:
                    _norm = normalize_league_abbrev(_opt)
                    if _norm and _norm not in _norm_to_display:
                        _norm_to_display[_norm] = _opt
                _resolved_selection: list[str] = []
                for _sel in _current_selection:
                    _mapped = _norm_to_display.get(normalize_league_abbrev(_sel))
                    if _mapped and _mapped not in _resolved_selection:
                        _resolved_selection.append(_mapped)
                st.session_state.league_filter = _resolved_selection

                st.multiselect(
                    "Leagues",
                    options=_league_options,
                    key="league_filter",
                    help=(
                        "NHL is available but optional. Additional options are discovered from "
                        "seasonTotals leagueAbbrev values of currently loaded players. "
                        "Points, Goals, and Assists are NHLe-adjusted; GP stays raw."
                    ),
                )
                _non_nhl = [
                    l for l in (st.session_state.league_filter or [])
                    if normalize_league_abbrev(l) != 'NHL'
                ]
                if _non_nhl:
                    st.caption(f"NHLe-adjusted: {', '.join(_non_nhl)}")

        # Captions for toggle context (rendered after metric is resolved)
        if st.session_state.do_cumul_toggle and metric in _cumul_rate_set:
            st.caption(f"⚠️ Cumulative disabled — {metric} is a rate stat.")
        if games_mode:
            _gm_note = (
                "ℹ️ Cumulative & Baseline unavailable in Games mode."
                if team_mode
                else "ℹ️ Projection & Baseline unavailable in Games mode."
            )
            st.caption(_gm_note)
        _ERA_GOALIE_STATS = {'Save %', 'GAA', 'Shutouts'}
        if (
            st.session_state.do_era
            and st.session_state.stat_category == 'Goalie'
            and metric not in _ERA_GOALIE_STATS
        ):
            st.caption(
                f"ℹ️ Era-Adjust for goalies applies to Save %, GAA, and Shutouts. "
                f"{metric} is not era-adjusted."
            )

        # Resolve do_cumul: False when metric is a rate stat; games_mode honours the toggle
        do_cumul = (
            st.session_state.do_cumul_toggle
            and metric not in _cumul_rate_set
        )

    return metric, do_cumul
