"""
nhl.controls — Category/Metric expander for the NHL Age Curves app.

Renders a single "Category & Metric" expander that appears below the page title.
It contains all controls in two rows:
    Row 1: category radio (Skater / Goalie / Team) + all 5 toggles on the same row
    Row 2: X-Axis, Select Metric, Season Type, Leagues dropdowns (compact, left→right)

The expander uses expanded=True so it is always open on every rerun, ensuring toggles
remain visible after player add/remove actions.

Reads and writes st.session_state directly (that is the correct Streamlit pattern
for widget state).  Returns (metric, do_cumul) so app.py can pass both values into
the pipelines and chart renderer without reading session state itself.

Imports from project:
    nhl.constants — TEAM_METRICS, NHLE_MULTIPLIERS, RATE_STATS, TEAM_RATE_STATS
"""

import streamlit as st

from nhl.constants import NHLE_MULTIPLIERS, RATE_STATS, TEAM_METRICS, TEAM_RATE_STATS


def render_controls() -> tuple:
    """Render the unified Category & Metric expander with all controls.

    The expander uses expanded=True so it is always open on every rerun, ensuring
    toggles remain visible and accessible after player add/remove actions.

    A single expander holds two rows:
        Row 1 — Category radio (Skater/Goalie/Team) + all 5 toggles on the same row.
        Row 2 — X-Axis, Select Metric, Season Type, Leagues dropdowns.

    Reads:
        st.session_state.stat_category   — drives metric radio options
        st.session_state.x_axis_mode     — determines which mode note to show
        st.session_state.do_cumul_toggle — raw toggle value
        st.session_state.league_filter   — current league multiselect
    Writes (via widget keys):
        stat_category, x_axis_mode, league_filter, season_type,
        do_smooth, do_predict, do_era, do_cumul_toggle, do_base

    Returns:
        Tuple of (metric, do_cumul):
            metric   — currently selected stat metric string (e.g. 'Points').
            do_cumul — resolved cumulative flag: True only when the toggle is on,
                       the metric is not a rate stat, and games_mode is False.
    """
    team_mode  = st.session_state.stat_category == "Team"
    games_mode = st.session_state.x_axis_mode == "Games Played"

    with st.expander("📊 Category & Metric", expanded=True):
        # ------------------------------------------------------------------
        # Row 1: Category radio + compact toggles (no wasted desktop space)
        # ------------------------------------------------------------------
        _cumul_rate_set = TEAM_RATE_STATS if team_mode else RATE_STATS

        st.markdown("<div id='controls-row1'></div>", unsafe_allow_html=True)
        c_category, c_t1, c_t2, c_t3, c_t4, c_t5 = st.columns(
            [2.5, 2, 1.8, 1.5, 1.8, 1.8], vertical_alignment="center"
        )

        with c_category:
            st.radio(
                "Category:",
                ["Skater", "Goalie", "Team"],
                horizontal=True,
                key="stat_category",
                label_visibility="collapsed",
            )

        with c_t1:
            st.session_state.do_smooth = st.toggle(
                "3-Season Rolling Avg", value=st.session_state.do_smooth)

        with c_t2:
            st.session_state.do_predict = st.toggle(
                "Project to 40", value=st.session_state.do_predict,
                disabled=games_mode or team_mode)

        with c_t3:
            st.session_state.do_era = st.toggle(
                "Era-Adjust", value=st.session_state.do_era, disabled=team_mode)

        with c_t4:
            st.session_state.do_cumul_toggle = st.toggle(
                "Cumulative", value=st.session_state.do_cumul_toggle)

        with c_t5:
            st.session_state.do_base = st.toggle(
                "Show Baseline", value=st.session_state.do_base, disabled=games_mode)

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
                    ["Wins", "Save %", "GAA", "Shutouts", "GP", "Saves"],
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
            if st.session_state.stat_category != "Team":
                st.multiselect(
                    "Leagues",
                    options=list(NHLE_MULTIPLIERS.keys()),
                    default=["NHL"],
                    key="league_filter",
                    help=(
                        "NHL only by default. Select additional leagues to include "
                        "non-NHL seasons. Stats are multiplied by NHLe equivalency "
                        "factors (Points, Goals, Assists only; GP kept raw)."
                    ),
                )
                _non_nhl = [l for l in (st.session_state.league_filter or ['NHL']) if l != 'NHL']
                if _non_nhl:
                    st.caption(f"NHLe-adjusted: {', '.join(_non_nhl)}")
            else:
                st.caption("Team mode: NHL data only.")

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
        if team_mode:
            st.caption("ℹ️ Projection & Era-Adjust not applicable to teams.")

        # Resolve do_cumul: False when metric is a rate stat; games_mode honours the toggle
        do_cumul = (
            st.session_state.do_cumul_toggle
            and metric not in _cumul_rate_set
        )

    return metric, do_cumul
