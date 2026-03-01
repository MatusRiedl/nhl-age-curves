"""
nhl.chart — Plotly chart rendering and JS pan-clamp injection.

Assembles the final DataFrame from all processed pipelines, optionally adds
baseline data, builds the Plotly figure, injects a JS snippet for responsive
dtick and pan/zoom clamping, renders via st.plotly_chart, and fires the
season-detail dialog on point click.

Visual conventions (from CLAUDE.md):
    Real data:   solid colored line, filled markers
    Projection:  dotted gray line, open circle markers
    Baseline:    dashed white semi-transparent, marker size=1

Imports from project:
    nhl.constants — RATE_STATS, TEAM_RATE_STATS
    nhl.dialog    — show_season_details
"""

import pandas as pd
import plotly.express as px
import streamlit as st
import streamlit.components.v1 as components

from nhl.constants import RATE_STATS, TEAM_RATE_STATS
from nhl.dialog import show_season_details


def render_chart(
    processed_dfs: list,
    metric: str,
    team_mode: bool,
    games_mode: bool,
    do_cumul: bool,
    do_base: bool,
    do_smooth: bool,
    stat_category: str,
    historical_baselines: dict,
    team_baselines: dict,
    raw_dfs_cache: list,
    ml_clones_dict: dict,
    season_type: str,
    sidebar_keys: dict,
) -> None:
    """Build and render the Plotly age-curve chart.

    If processed_dfs is empty, shows an informational message instead.

    Args:
        processed_dfs:        List of DataFrames from process_players() or
                              process_teams().
        metric:               Currently selected stat metric string.
        team_mode:            True when stat_category == 'Team'.
        games_mode:           True when x_axis_mode == 'Games Played'.
        do_cumul:             Resolved cumulative flag (False for rate stats).
        do_base:              Whether to overlay the 75th-percentile baseline.
        do_smooth:            Whether spline line shape is active (cosmetic only here).
        stat_category:        'Skater' or 'Goalie' (passed to dialog).
        historical_baselines: {'Skater': DataFrame, 'Goalie': DataFrame}.
        team_baselines:       {season_year: {metric: value}}.
        raw_dfs_cache:        Raw DataFrames for the click dialog.
        ml_clones_dict:       KNN clone dicts for the click dialog.
        season_type:          'Regular', 'Playoffs', or 'Both'.
        sidebar_keys:         Dict with 'search_term', 'top_selected', 'team_abbr',
                              'roster_player' — used for chart widget key generation.
    """
    if not processed_dfs:
        # Allow baseline-only render when Show Baseline is on in player mode
        if not (do_base and not games_mode and not team_mode):
            if team_mode:
                st.info("Add teams from the sidebar to compare their historical performance.")
            else:
                st.info("Add players from the sidebar to get started.")
            return

    final_df = pd.concat(processed_dfs, ignore_index=True) if processed_dfs else pd.DataFrame()

    # ------------------------------------------------------------------
    # Baseline overlay
    # ------------------------------------------------------------------
    if do_base and not games_mode:
        if team_mode:
            # Team baseline: 75th pct of all teams per season year
            base_data = []
            for _sy in sorted(team_baselines.keys()):
                _val = team_baselines[_sy].get(metric)
                if _val is not None and not pd.isna(_val):
                    base_data.append({
                        "SeasonYear": _sy,
                        metric:        _val,
                        "Player":      "NHL Team 75th Pct Baseline",
                        "BaseName":    "Baseline",
                    })
            if base_data:
                final_df = pd.concat([final_df, pd.DataFrame(base_data)], ignore_index=True)
        else:
            # Player baseline: 75th pct by age from parquet
            base_df = historical_baselines.get(stat_category)
            if base_df is not None and not base_df.empty:
                base_data  = []
                cumul_val  = 0
                for age in range(18, 41):
                    if age in base_df.index and metric in base_df.columns:
                        val = base_df.loc[age, metric]
                        if pd.isna(val):
                            val = 0
                    else:
                        val = 0

                    if do_cumul and metric in [
                        'Points', 'Goals', 'Assists', 'Wins', 'Shutouts', 'GP', 'PIM', 'Saves', '+/-'
                    ]:
                        cumul_val += val
                        val = cumul_val

                    base_data.append({
                        "Age":      age,
                        metric:     val,
                        "Player":   "NHL 75th Percentile Baseline",
                        "BaseName": "Baseline",
                    })
                final_df = pd.concat([final_df, pd.DataFrame(base_data)], ignore_index=True)

    # Guard: baseline attempt may still leave final_df empty (e.g. switching to Goalie
    # mode with no goalies loaded and a metric that has no baseline data).
    if final_df.empty:
        st.info("Add players from the sidebar to get started.")
        return

    # ------------------------------------------------------------------
    # Determine x-axis column and custom_data columns
    # ------------------------------------------------------------------
    if team_mode and not games_mode:
        x_col       = "SeasonYear"
        custom_cols = ["BaseName", "Player"]
    elif games_mode:
        x_col       = "CumGP"
        custom_cols = ["BaseName", "Player", "Age"] if not team_mode else ["BaseName", "Player"]
    else:
        x_col       = "Age"
        custom_cols = ["BaseName", "Player"]

    # ------------------------------------------------------------------
    # Data bounds for axis range constraints and JS pan clamping
    # ------------------------------------------------------------------
    _x_vals = final_df[x_col].dropna()
    _y_vals = final_df[metric].dropna()
    _x_pad  = (_x_vals.max() - _x_vals.min()) * 0.02 + 0.5
    _y_pad  = float(_y_vals.max()) * 0.05
    _x_min  = float(_x_vals.min()) - _x_pad
    _x_max  = float(_x_vals.max()) + _x_pad
    _y_min  = max(0.0, float(_y_vals.min()))
    _y_max  = float(_y_vals.max()) + _y_pad
    _is_age_mode   = (x_col == "Age")
    _is_games_mode = (x_col == "Games Played")

    # ------------------------------------------------------------------
    # Build Plotly figure
    # ------------------------------------------------------------------
    fig = px.line(
        final_df,
        x           = x_col,
        y           = metric,
        color       = "Player",
        custom_data = custom_cols,
        markers     = True,
        template    = "plotly_dark",
        line_shape  = "spline" if do_smooth else "linear",
    )

    # Apply visual conventions per trace
    for trace in fig.data:
        if "(Proj)" in trace.name:
            trace.line.dash          = 'dot'
            trace.line.color         = 'gray'
            trace.marker.symbol      = 'circle-open'
        elif "Baseline" in trace.name:
            trace.line.dash          = 'dash'
            trace.line.color         = 'rgba(255, 255, 255, 0.4)'
            trace.marker.size        = 1

    fig.update_layout(
        uirevision  = 'constant',
        margin      = dict(l=0, r=0, t=40, b=80),
        height      = 600,
        font        = dict(size=16),
        hoverlabel  = dict(font_size=18, font_family="Arial", bgcolor="#1E1E1E"),
        legend      = dict(
            title=None, orientation="h",
            yanchor="top", y=-0.15,
            xanchor="center", x=0.5,
        ),
        clickmode   = 'event+select',
    )

    _val_fmt = (
        ".2f"
        if (team_mode and metric in TEAM_RATE_STATS) or (not team_mode and metric in RATE_STATS)
        else ".0f"
    )

    if team_mode and not games_mode:
        fig.update_traces(
            connectgaps    = True,
            line           = dict(width=4, shape='spline', smoothing=0.6),
            marker         = dict(size=8),
            hovertemplate  = (
                f"<b>%{{customdata[1]}}</b><br>Season %{{x}}<br>"
                f"{metric}: %{{y:{_val_fmt}}}<extra></extra>"
            ),
        )
        fig.update_xaxes(
            title_text  = "Season Year",
            tickangle   = 0,
            automargin  = True,
            title_font  = dict(size=25, family='Arial Black'),
            tickfont    = dict(size=18, family='Arial Black'),
        )
    elif games_mode:
        fig.update_traces(
            connectgaps    = True,
            line           = dict(width=4, shape='spline', smoothing=0.6),
            marker         = dict(size=8),
            hovertemplate  = (
                f"<b>%{{customdata[1]}}</b><br>"
                f"{'Career Game' if not team_mode else 'Season GP'} %{{x}}<br>"
                f"Value: %{{y:{_val_fmt}}}<extra></extra>"
            ),
        )
        fig.update_xaxes(
            title_text  = "Games Played",
            tickangle   = 0,
            automargin  = True,
            title_font  = dict(size=25, family='Arial Black'),
            tickfont    = dict(size=18, family='Arial Black'),
        )
    else:
        fig.update_traces(
            connectgaps    = True,
            line           = dict(width=4, shape='spline', smoothing=0.6),
            marker         = dict(size=8),
            hovertemplate  = (
                f"<b>%{{customdata[1]}}</b><br>Age %{{x}}<br>"
                f"Value: %{{y:{_val_fmt}}}<extra></extra>"
            ),
        )
        fig.update_xaxes(
            tickangle   = 0,
            automargin  = True,
            title_font  = dict(size=25, family='Arial Black'),
            tickfont    = dict(size=18, family='Arial Black'),
        )

    fig.update_yaxes(
        title_font = dict(size=25, family='Arial Black'),
        tickfont   = dict(size=18, family='Arial Black'),
    )

    # Percentage suffix for rate metrics shown as percentages
    if metric in ["Save %", "SH%", "Win%", "PP%"]:
        fig.update_yaxes(ticksuffix="%")
        if team_mode and not games_mode:
            fig.update_traces(
                hovertemplate=(
                    f"<b>%{{customdata[1]}}</b><br>Season %{{x}}<br>%{{y:.1f}}%<extra></extra>"
                )
            )
        else:
            x_label = "Career Game" if games_mode else "Age"
            fig.update_traces(
                hovertemplate=(
                    f"<b>%{{customdata[1]}}</b><br>{x_label} %{{x}}<br>%{{y:.1f}}%<extra></extra>"
                )
            )

    # ------------------------------------------------------------------
    # Chart widget key (cache-busting)
    # ------------------------------------------------------------------
    if team_mode:
        chart_key = (
            f"chart_team_{hash(str(st.session_state.teams))}"
            f"_{metric}_{st.session_state.do_smooth}_{st.session_state.x_axis_mode}"
        )
    else:
        chart_key = (
            f"chart_{hash(str({**st.session_state.skater_players, **st.session_state.goalie_players}))}"
            f"_{metric}_{st.session_state.do_predict}_{st.session_state.do_smooth}"
            f"_{sidebar_keys.get('search_term', '')}"
            f"_{sidebar_keys.get('top_selected', '')}"
            f"_{sidebar_keys.get('team_abbr', '')}"
            f"_{sidebar_keys.get('roster_player', '')}"
            f"_{st.session_state.x_axis_mode}"
        )

    plotly_config = {
        "displayModeBar": True,
        "modeBarButtonsToRemove": [
            "lasso2d", "select2d", "toggleSpikelines",
            "hoverCompareCartesian", "hoverClosestCartesian", "autoScale2d",
        ],
        "displaylogo": False,
    }

    event = st.plotly_chart(
        fig,
        use_container_width = True,
        on_select           = "rerun",
        selection_mode      = "points",
        key                 = chart_key,
        config              = plotly_config,
    )

    # ------------------------------------------------------------------
    # JS: responsive dtick + pan/zoom clamping
    # ------------------------------------------------------------------
    components.html(f"""<script>
(function() {{
    var X_MIN = {_x_min:.4f};
    var X_MAX = {_x_max:.4f};
    var Y_MIN = {_y_min:.4f};
    var Y_MAX = {_y_max:.4f};
    var IS_AGE_MODE   = {'true' if _is_age_mode else 'false'};
    var IS_GAMES_MODE = {'true' if _is_games_mode else 'false'};

    function calcDtick(width) {{
        var xRange = X_MAX - X_MIN;
        if (IS_AGE_MODE) {{
            var pixPerAge = width / xRange;
            if (pixPerAge >= 32) return 1;
            if (pixPerAge >= 16) return 2;
            if (pixPerAge >= 7)  return 5;
            return 10;
        }}
        if (IS_GAMES_MODE) {{
            var targetTicks = width >= 900 ? 8 : width >= 480 ? 5 : 3;
            var rawDtick = xRange / targetTicks;
            if (rawDtick <= 100)  return 100;
            if (rawDtick <= 200)  return 200;
            if (rawDtick <= 300)  return 250;
            if (rawDtick <= 400)  return 400;
            if (rawDtick <= 750)  return 500;
            return Math.ceil(rawDtick / 500) * 500;
        }}
        // Season Year mode
        if (width >= 900) return 2;
        if (width >= 480) return 5;
        return 10;
    }}

    function applySettings(plot, Plotly) {{
        var updates = {{'xaxis.dtick': calcDtick(plot.offsetWidth || window.parent.innerWidth)}};
        updates['xaxis.tickangle'] = 0;
        Plotly.relayout(plot, updates);

        // Clamp pan/zoom to data region
        var _clamping = false;
        plot.on('plotly_relayout', function(evt) {{
            if (_clamping) return;
            var clamps = {{}};
            var needs  = false;
            var r0 = evt['xaxis.range[0]'], r1 = evt['xaxis.range[1]'];
            var y0 = evt['yaxis.range[0]'], y1 = evt['yaxis.range[1]'];
            if (r0 !== undefined && r0 < X_MIN) {{ clamps['xaxis.range[0]'] = X_MIN; needs = true; }}
            if (r1 !== undefined && r1 > X_MAX) {{ clamps['xaxis.range[1]'] = X_MAX; needs = true; }}
            if (y0 !== undefined && y0 < Y_MIN) {{ clamps['yaxis.range[0]'] = Y_MIN; needs = true; }}
            if (y1 !== undefined && y1 > Y_MAX) {{ clamps['yaxis.range[1]'] = Y_MAX; needs = true; }}
            if (needs) {{ _clamping = true; Plotly.relayout(plot, clamps); _clamping = false; }}
        }});
    }}

    function init() {{
        var parent = window.parent;
        var Plotly = parent.Plotly;
        if (!Plotly) {{ setTimeout(init, 200); return; }}
        var plots = parent.document.querySelectorAll('.js-plotly-plot');
        if (!plots.length) {{ setTimeout(init, 200); return; }}
        plots.forEach(function(p) {{ applySettings(p, Plotly); }});

        parent.addEventListener('resize', function() {{
            parent.document.querySelectorAll('.js-plotly-plot').forEach(function(p) {{
                Plotly.relayout(p, {{'xaxis.dtick': calcDtick(p.offsetWidth || parent.innerWidth)}});
            }});
        }});
    }}

    setTimeout(init, 500);
}})();
</script>""", height=0)

    # ------------------------------------------------------------------
    # Click handler: fire season-detail dialog on point selection
    # ------------------------------------------------------------------
    if not team_mode and event and event.selection.get("points"):
        point          = event.selection["points"][0]
        cd             = point.get("customdata", [])
        age_for_detail = int(cd[2]) if games_mode else point["x"]
        show_season_details(
            player_name          = cd[1],
            age                  = age_for_detail,
            raw_dfs_list         = raw_dfs_cache,
            metric               = metric,
            val                  = point["y"],
            is_cumul             = do_cumul,
            full_df              = final_df,
            s_type               = season_type,
            ml_clones_dict       = ml_clones_dict,
            historical_baselines = historical_baselines,
            stat_category        = stat_category,
        )
