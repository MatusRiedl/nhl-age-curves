"""
nhl.controls — Category/Metric and View Options expanders for the NHL Age Curves app.

Renders the two main control expanders that appear below the page title:
    1. "Category & Metric" — category radio, metric radio, x-axis mode, league filter.
    2. "View Options"      — season type, rolling avg, project, era-adjust,
                            cumulative, and baseline toggles.

Reads and writes st.session_state directly (that is the correct Streamlit pattern
for widget state).  Returns (metric, do_cumul) so app.py can pass both values into
the pipelines and chart renderer without reading session state itself.

Imports from project:
    nhl.constants — TEAM_METRICS, NHLE_MULTIPLIERS, RATE_STATS, TEAM_RATE_STATS
"""

import streamlit as st

from nhl.constants import NHLE_MULTIPLIERS, RATE_STATS, TEAM_METRICS, TEAM_RATE_STATS


def render_controls() -> tuple:
    """Render the Category/Metric expander and the View Options expander.

    Both expanders are expanded by default (expanded=True) so all controls are
    visible immediately on desktop; mobile users can tap the header to collapse.

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

    # ------------------------------------------------------------------
    # Expander 1: Category & Metric
    # ------------------------------------------------------------------
    with st.expander("📊 Category & Metric", expanded=True):
        c_category, c_metric = st.columns([2, 8], vertical_alignment="center")
        with c_category:
            st.radio(
                "Category:",
                ["Skater", "Goalie", "Team"],
                horizontal=True,
                key="stat_category",
            )
        with c_metric:
            if st.session_state.stat_category == "Skater":
                metric = st.radio(
                    "Select Metric:",
                    ["Points", "Goals", "Assists", "+/-", "GP", "PPG", "SH%", "PIM", "TOI"],
                    horizontal=True,
                    key="skater_metric",
                    help=(
                        "+/-: Plus/Minus Differential | GP: Games Played | "
                        "PPG: Points Per Game | SH%: Shooting Percentage | "
                        "PIM: Penalty Minutes | TOI: Time on Ice (Avg Mins)"
                    ),
                )
            elif st.session_state.stat_category == "Goalie":
                metric = st.radio(
                    "Select Metric:",
                    ["Wins", "Save %", "GAA", "Shutouts", "GP", "Saves"],
                    horizontal=True,
                    key="goalie_metric",
                    help=(
                        "Save %: Save Percentage | GAA: Goals Against Average | "
                        "GP: Games Played | Saves: Total Saves"
                    ),
                )
            else:
                metric = st.radio(
                    "Select Metric:",
                    TEAM_METRICS,
                    horizontal=True,
                    key="team_metric",
                    help=(
                        "Points: standings pts | Wins: wins per season | Win%: pts pct | "
                        "Goals: team GF | GF/G: goals for/game | GA/G: goals against/game | "
                        "PP%: power play % | PPG: team scoring pts/game (est.)"
                    ),
                )

        _x_opts = (
            ["Season Year", "Games Played"]
            if st.session_state.stat_category == "Team"
            else ["Age", "Games Played"]
        )
        c_xaxis, c_league, _ = st.columns([3, 4, 3])
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

    # ------------------------------------------------------------------
    # Expander 2: View Options & Toggles
    # ------------------------------------------------------------------
    with st.expander("⚙️ View Options", expanded=True):
        st.markdown("<div id='master-toggles'></div>", unsafe_allow_html=True)
        c1, c2, c3 = st.columns([2, 3, 3])
        with c1:
            st.selectbox("Season Type", ["Regular", "Playoffs", "Both"], key="season_type")
        with c2:
            st.toggle("3-Season Rolling Avg", key="do_smooth")
            st.toggle("Project to 40", key="do_predict", disabled=games_mode or team_mode)
        with c3:
            st.toggle("Era-Adjust", key="do_era", disabled=team_mode)
            _cumul_rate_set = TEAM_RATE_STATS if team_mode else RATE_STATS
            st.toggle("Cumulative", key="do_cumul_toggle")
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
            st.toggle("Show Baseline", key="do_base", disabled=games_mode)

        # Resolve do_cumul: False when metric is a rate stat; games_mode now honours the toggle
        do_cumul = (
            st.session_state.do_cumul_toggle
            and metric not in _cumul_rate_set
        )

    return metric, do_cumul
