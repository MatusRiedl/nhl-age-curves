"""
nhl.chart — Plotly chart rendering and JS pan-clamp injection.

Assembles the final DataFrame from all processed pipelines, optionally adds
baseline data, builds the Plotly figure, renders a real toolbar row above the
chart, injects a JS snippet for responsive dtick / share-link handling, and
fires the season-detail dialog on point click.

Visual conventions (from CLAUDE.md):
    Real data:   solid colored line, filled markers
    Projection:  dotted player-colored line, open circle markers
    Baseline:    muted grey dashed line, visible round markers

Imports from project:
    nhl.constants — RATE_STATS, TEAM_RATE_STATS
    nhl.dialog    — show_season_details
"""

import json
from html import escape

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components

from nhl.constants import RATE_STATS, TEAM_RATE_STATS
from nhl.dialog import show_season_details


X_AXIS_TICK_COLOR = "rgba(255, 255, 255, 0.80)"
Y_AXIS_TICK_COLOR = "rgba(255, 255, 255, 0.80)"
X_AXIS_CUE_COLOR = "rgba(255, 255, 255, 0.25)"
Y_AXIS_CUE_COLOR = "rgba(255, 255, 255, 0.25)"
BASELINE_LINE_DASH = "14px,10px"
BASELINE_LINE_COLOR = "rgba(190, 190, 190, 0.72)"
BASELINE_MARKER_COLOR = "rgba(220, 220, 220, 0.92)"
PLAYER_COLOR_STATE_KEY = "player_chart_colors"


def _store_player_chart_colors(player_colors: dict[str, str | None]) -> None:
    """Persist the active player-to-chart-color map for sibling UI panels.

    Args:
        player_colors: Mapping of real-player names to their assigned chart colors.

    Returns:
        None.
    """
    setattr(st.session_state, PLAYER_COLOR_STATE_KEY, dict(player_colors))


def _get_chart_context_label(team_mode: bool, games_mode: bool) -> str:
    """Return the x-context label for the chart toolbar title.

    Args:
        team_mode: True when the chart is rendering team comparisons.
        games_mode: True when the x-axis uses games played instead of age.

    Returns:
        str: Label describing the x context, such as Age or Games Played.
    """
    if team_mode and not games_mode:
        return "Season"
    if games_mode:
        return "Games Played"
    return "Age"


def _get_chart_season_label(season_type: str) -> str:
    """Return the season descriptor for the chart toolbar title.

    Args:
        season_type: Selected season scope string from the UI.

    Returns:
        str: Human-readable season scope label.
    """
    season_labels = {
        "Regular": "Regular season",
        "Playoffs": "Playoffs",
        "Both": "Regular + playoffs",
    }
    return season_labels.get(season_type, season_type)


def _build_chart_header(metric: str, team_mode: bool, games_mode: bool, season_type: str) -> str:
    """Build the chart toolbar title shown above the plot area.

    Args:
        metric: Selected y-axis metric.
        team_mode: True when the chart is rendering team comparisons.
        games_mode: True when the x-axis uses games played instead of age.
        season_type: Selected season scope string from the UI.

    Returns:
        str: Title text such as ``Points by Age · Regular season``.
    """
    x_label = _get_chart_context_label(team_mode=team_mode, games_mode=games_mode)
    season_label = _get_chart_season_label(season_type)
    return f"{metric} by {x_label} · {season_label}"


def _build_chart_toolbar_markup(title: str, share_button_id: str, toolbar_id: str) -> str:
    """Build the HTML toolbar shown above the chart.

    Args:
        title: Visible chart title.
        share_button_id: DOM id for the copy-link button.
        toolbar_id: DOM id for the toolbar wrapper.

    Returns:
        str: Safe toolbar HTML.
    """
    safe_title = escape(title)
    return (
        f"<div id='{toolbar_id}' class='nhl-chart-toolbar'>"
        f"<div class='nhl-chart-toolbar__title'>{safe_title}</div>"
        f"<button id='{share_button_id}' type='button' class='nhl-chart-share-btn' aria-label='Copy share link'>"
        "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'>"
        "<path d='M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71'/><path d='M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71'/></svg>"
        "<span class='nhl-chart-share-btn__label'>Copy link</span>"
        "</button>"
        "</div>"
    )


def _build_chart_axis_cue_annotations(metric: str, team_mode: bool, games_mode: bool) -> list[dict]:
    """Build subtle in-chart axis cue annotations.

    Args:
        metric: Selected y-axis metric.
        team_mode: True when the chart is rendering team comparisons.
        games_mode: True when the x-axis uses games played instead of age.

    Returns:
        list[dict]: Plotly annotation dictionaries for y/x context cues.
    """
    x_label = _get_chart_context_label(team_mode=team_mode, games_mode=games_mode)
    return [
        dict(
            x=0.006,
            y=0.998,
            xref="paper",
            yref="paper",
            xanchor="left",
            yanchor="top",
            text=escape(metric),
            showarrow=False,
            font=dict(size=15, family="Arial Black", color=Y_AXIS_CUE_COLOR),
        ),
        dict(
            x=0.994,
            y=0.004,
            xref="paper",
            yref="paper",
            xanchor="right",
            yanchor="bottom",
            text=escape(x_label),
            showarrow=False,
            font=dict(size=15, family="Arial Black", color=X_AXIS_CUE_COLOR),
        ),
    ]


def _slugify_chart_export_name(title: str) -> str:
    """Convert the chart title into a stable download filename.

    Args:
        title: Human-readable chart title.

    Returns:
        str: Lowercase filesystem-friendly slug.
    """
    slug = "".join(ch.lower() if ch.isalnum() else "_" for ch in title)
    while "__" in slug:
        slug = slug.replace("__", "_")
    return slug.strip("_") or "nhl_age_chart"


def _is_baseline_trace(trace_name: str) -> bool:
    """Return whether a Plotly trace name represents a baseline series.

    Args:
        trace_name: Visible Plotly trace label.

    Returns:
        bool: True when the trace is a baseline line.
    """
    return "baseline" in trace_name.casefold()


def _apply_special_trace_styling(fig: go.Figure, player_colors: dict[str, str | None]) -> None:
    """Reapply baseline and projection styling after shared trace updates.

    Args:
        fig: Plotly figure to mutate in place.
        player_colors: Mapping of real-player names to their Plotly colors.

    Returns:
        None.
    """
    for trace in fig.data:
        if "(Proj)" in trace.name:
            player_name = trace.name.replace(" (Proj)", "")
            proj_color = player_colors.get(player_name) or "gray"
            trace.legendgroup = player_name
            trace.showlegend = False
            trace.line.dash = 'dot'
            trace.line.color = proj_color
            trace.marker.symbol = 'circle-open'
        elif _is_baseline_trace(trace.name):
            trace.legendgroup = trace.name
            trace.line.dash = BASELINE_LINE_DASH
            trace.line.color = BASELINE_LINE_COLOR
            trace.line.width = 4
            trace.marker.size = 8
            trace.marker.color = BASELINE_MARKER_COLOR
            trace.marker.line.width = 0
            trace.marker.symbol = 'circle'


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
    peak_info: dict = None,
    do_prime: bool = False,
    share_params: dict | None = None,
) -> None:
    """Build the Plotly chart, optional baseline overlays, and click handling."""
    _store_player_chart_colors({})
    if peak_info is None:
        peak_info = {}
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
            base_rows = []
            base_key = 'Goalie' if stat_category == 'Goalie' else 'Skater'
            base_df = historical_baselines.get(base_key)
            base_label = 'Reference baseline'
            counting_metrics = {
                'Points', 'Goals', 'Assists', 'Wins', 'Shutouts', 'GP', 'PIM', 'Saves', '+/-'
            }
            if base_df is not None and not base_df.empty and metric in base_df.columns:
                values = base_df[metric].sort_index().reindex(range(18, 41)).astype(float)
                values = values.interpolate(method='linear')
                cumulative_value = 0.0
                for age, val in values.items():
                    if pd.isna(val):
                        continue
                    plot_val = float(val)
                    if do_cumul and metric in counting_metrics:
                        cumulative_value += plot_val
                        plot_val = cumulative_value
                    base_rows.append({
                        'Age': int(age),
                        metric: plot_val,
                        'Player': base_label,
                        'BaseName': 'Baseline',
                    })

            if base_rows:
                final_df = pd.concat([final_df, pd.DataFrame(base_rows)], ignore_index=True)

    # Guard: baseline attempt may still leave final_df empty (e.g. switching to Goalie
    # mode with no goalies loaded and a metric that has no baseline data).
    if final_df.empty:
        st.info("Add players from the sidebar to get started.")
        return

    # Team season-year hover should display season spans (e.g., 2024 -> 24-25)
    if team_mode and not games_mode and "SeasonYear" in final_df.columns:
        def _season_span_label(start_year: float) -> str:
            try:
                sy = int(start_year)
                return f"{str(sy)[2:]}-{str(sy + 1)[2:]}"
            except Exception:
                return str(start_year)

        final_df["SeasonLabel"] = final_df["SeasonYear"].apply(_season_span_label)

    # ------------------------------------------------------------------
    # Determine x-axis column and custom_data columns
    # ------------------------------------------------------------------
    if team_mode and not games_mode:
        x_col       = "SeasonYear"
        custom_cols = ["BaseName", "Player", "SeasonLabel"]
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
    _is_games_mode = games_mode

    # Full data range for clamping
    _x_full_range = float(_x_vals.max() - _x_vals.min())

    # Initial 20-year zoom for team mode (users can double-click to see full history)
    _team_initial_range = None
    if team_mode and not games_mode and _x_full_range > 20:
        _max_year = float(_x_vals.max())
        _zoom_min = _max_year - 20
        _zoom_max = _max_year + (_x_pad * 0.5)  # Small padding on the right
        _team_initial_range = [_zoom_min, _zoom_max] if _zoom_min >= _x_min else None

    # Python-side dtick for team/season-year mode (applied immediately, before JS lands)
    # Use zoomed range size if applicable, otherwise full range
    if _team_initial_range:
        _x_range_size = _team_initial_range[1] - _team_initial_range[0]
    else:
        _x_range_size = _x_full_range

    if _x_range_size <= 25:
        _team_dtick = 2
    elif _x_range_size <= 50:
        _team_dtick = 5
    elif _x_range_size <= 100:
        _team_dtick = 10
    else:
        _team_dtick = 20

    chart_header = _build_chart_header(
        metric=metric,
        team_mode=team_mode,
        games_mode=games_mode,
        season_type=season_type,
    )
    chart_axis_cues = _build_chart_axis_cue_annotations(
        metric=metric,
        team_mode=team_mode,
        games_mode=games_mode,
    )

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
    player_colors = {}  # Map player name -> color
    proj_traces = []  # Store (x, y, color, legendgroup) for projection glow traces
    
    # First pass: capture player colors and projection data
    for trace in fig.data:
        if "(Proj)" not in trace.name and not _is_baseline_trace(trace.name):
            # This is a real player line - capture its color
            player_colors[trace.name] = trace.line.color if trace.line.color else None
            trace.legendgroup = trace.name
        elif _is_baseline_trace(trace.name):
            trace.legendgroup = trace.name
    
    for trace in fig.data:
        if "(Proj)" in trace.name:
            # Extract player name from projection (e.g., "Sebastian Aho (Proj)" -> "Sebastian Aho")
            player_name = trace.name.replace(" (Proj)", "")
            proj_color = player_colors.get(player_name) if player_colors.get(player_name) else 'gray'
            proj_traces.append({
                'x': trace.x,
                'y': trace.y,
                'color': proj_color,
                'legendgroup': player_name,
            })

    _store_player_chart_colors(player_colors)

    _apply_special_trace_styling(fig, player_colors)

    # Add glow traces for projection lines (use player's color for each projection)
    for proj in proj_traces:
        if proj['x'] is not None and proj['y'] is not None:
            # Outer glow
            fig.add_trace(go.Scatter(
                x=proj['x'], y=proj['y'],
                mode='lines',
                line=dict(color=proj['color'], width=10, dash='dot'),
                showlegend=False,
                legendgroup=proj['legendgroup'],
                hoverinfo='skip',
                name='_proj_glow_outer',
            ))
            # Inner glow
            fig.add_trace(go.Scatter(
                x=proj['x'], y=proj['y'],
                mode='lines',
                line=dict(color=proj['color'], width=4, dash='dot'),
                showlegend=False,
                legendgroup=proj['legendgroup'],
                hoverinfo='skip',
                name='_proj_glow_inner',
            ))

    # Add peak age highlights (translucent vertical rectangles)
    if do_prime and not team_mode:
        for player_name, peak_data in peak_info.items():
            player_color = player_colors.get(player_name)
            if player_color and peak_data.get('age'):
                peak_age = peak_data['age']
                fig.add_vrect(
                    x0=peak_age - 1.5,
                    x1=peak_age + 1.5,
                    fillcolor=player_color,
                    opacity=0.10,
                    layer="below",
                    line_width=0,
                )


    fig.update_layout(
        uirevision  = 'constant',
        margin      = dict(l=0, r=0, t=18, b=12),
        height      = 430,
        font        = dict(size=16),
        hoverlabel  = dict(font_size=16, font_family="Arial", bgcolor="#1E1E1E"),
        annotations = chart_axis_cues,
        title       = dict(text=""),
        legend      = dict(
            title=None, orientation="h",
            yanchor="top", y=-0.20,
            xanchor="center", x=0.5,
            groupclick="togglegroup",
        ),
        clickmode   = 'event+select',
    )

    _val_fmt = (
        ".2f"
        if (team_mode and metric in TEAM_RATE_STATS) or (not team_mode and metric in RATE_STATS)
        else ".0f"
    )

    if team_mode and not games_mode:
        fig.update_layout(
            margin = dict(l=0, r=0, t=18, b=18),
            legend = dict(y=-0.30),
        )
        fig.update_traces(
            connectgaps    = True,
            line           = dict(width=4, shape='spline', smoothing=0.6),
            marker         = dict(size=8),
            hovertemplate  = (
                f"<b>%{{customdata[1]}}</b><br>Season %{{customdata[2]}}<br>"
                f"{metric}: %{{y:{_val_fmt}}}<extra></extra>"
            ),
        )
        fig.update_xaxes(
            title_text  = "",
            dtick       = _team_dtick,
            tickangle   = -45,
            automargin  = True,
            tickfont    = dict(size=16, family='Arial Black', color=X_AXIS_TICK_COLOR),
            range       = _team_initial_range,
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
            title_text  = "",
            tickangle   = 0,
            automargin  = True,
            tickfont    = dict(size=16, family='Arial Black', color=X_AXIS_TICK_COLOR),
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
            title_text  = "",
            tickangle   = 0,
            automargin  = True,
            tickfont    = dict(size=16, family='Arial Black', color=X_AXIS_TICK_COLOR),
        )

    fig.update_yaxes(
        title_text = "",
        tickfont   = dict(size=16, family='Arial Black', color=Y_AXIS_TICK_COLOR),
    )

    # Percentage suffix for rate metrics shown as percentages
    if metric in ["Save %", "SH%", "Win%", "PP%"]:
        fig.update_yaxes(ticksuffix="%")
        if team_mode and not games_mode:
            fig.update_traces(
                hovertemplate=(
                    f"<b>%{{customdata[1]}}</b><br>Season %{{customdata[2]}}<br>%{{y:.1f}}%<extra></extra>"
                )
            )
        else:
            x_label = "Career Game" if games_mode else "Age"
            fig.update_traces(
                hovertemplate=(
                    f"<b>%{{customdata[1]}}</b><br>{x_label} %{{x}}<br>%{{y:.1f}}%<extra></extra>"
                )
            )

    _apply_special_trace_styling(fig, player_colors)

    # ------------------------------------------------------------------
    # Chart widget key (cache-busting)
    # ------------------------------------------------------------------
    if team_mode:
        chart_key = (
            f"chart_team_{hash(str(st.session_state.teams))}"
            f"_{metric}_{st.session_state.do_smooth}_{st.session_state.x_axis_mode}"
        )
    else:
        # Use processed_dfs for player names instead of session state for better testability
        player_names = [df['BaseName'].iloc[0] for df in processed_dfs if not df.empty]
        chart_key = (
            f"chart_{hash(str(player_names))}"
            f"_{metric}_{st.session_state.do_predict}_{st.session_state.do_smooth}"
            f"_{sidebar_keys.get('search_term', '')}"
            f"_{sidebar_keys.get('top_selected', '')}"
            f"_{sidebar_keys.get('team_abbr', '')}"
            f"_{sidebar_keys.get('roster_player', '')}"
            f"_{st.session_state.x_axis_mode}"
        )

    share_button_id = f"nhl-share-btn-{abs(hash(chart_key))}"
    toolbar_id = f"nhl-chart-toolbar-{abs(hash(chart_key))}"
    st.markdown(
        _build_chart_toolbar_markup(chart_header, share_button_id, toolbar_id),
        unsafe_allow_html=True,
    )

    plotly_config = {
        "displayModeBar": True,
        "toImageButtonOptions": {
            "filename": _slugify_chart_export_name(chart_header),
            "format": "png",
            "scale": 2,
        },
        "modeBarButtonsToRemove": [
            "lasso2d", "select2d", "toggleSpikelines",
            "hoverCompareCartesian", "hoverClosestCartesian", "autoScale2d",
            "resetScale2d", "zoomIn2d", "zoomOut2d",
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
    # Zoom range for JS (used for responsive dtick in season year mode)
    _x_zoom_min = _team_initial_range[0] if _team_initial_range else _x_min
    _x_zoom_max = _team_initial_range[1] if _team_initial_range else _x_max
    _share_params_json = json.dumps(share_params or {})
    _share_button_id_json = json.dumps(share_button_id)
    _toolbar_id_json = json.dumps(toolbar_id)

    components.html(f"""<script>
(function() {{
    var X_MIN = {_x_min:.4f};
    var X_MAX = {_x_max:.4f};
    var X_ZOOM_MIN = {_x_zoom_min:.4f};
    var X_ZOOM_MAX = {_x_zoom_max:.4f};
    var Y_MIN = {_y_min:.4f};
    var Y_MAX = {_y_max:.4f};
    var IS_AGE_MODE   = {'true' if _is_age_mode else 'false'};
    var IS_GAMES_MODE = {'true' if _is_games_mode else 'false'};
    var SHARE_PARAMS = {_share_params_json};
    var SHARE_BUTTON_ID = {_share_button_id_json};
    var TOOLBAR_ID = {_toolbar_id_json};

    function calcDtick(width, currentRange) {{
        var xRange = currentRange || (X_MAX - X_MIN);
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
        // Season Year mode — use zoom range for initial calculation
        // 4-digit labels need ~50px each at typical chart widths
        var pixPerYear = width / xRange;
        if (pixPerYear >= 50) return 1;
        if (pixPerYear >= 25) return 2;
        if (pixPerYear >= 10) return 5;
        if (pixPerYear >= 5)  return 10;
        return 20;
    }}

    function calcResponsiveAxisTickFontSize(width) {{
        if (width <= 480) return 12;
        if (width <= 768) return 14;
        return 16;
    }}

    function syncToolbarTitleOffset(plot, parent) {{
        var toolbar = parent.document.getElementById(TOOLBAR_ID);
        if (!toolbar) return;
        var title = toolbar.querySelector('.nhl-chart-toolbar__title');
        if (!title) return;

        var width = plot.offsetWidth || parent.innerWidth;
        if (width > 768) {{
            title.style.paddingLeft = '0px';
            return;
        }}

        var gutter = 0;
        if (plot._fullLayout && plot._fullLayout._size) {{
            gutter = plot._fullLayout._size.l || 0;
        }}
        title.style.paddingLeft = Math.max(0, Math.round(gutter)) + 'px';
    }}

    function getCurrentXRange(plot) {{
        // Get the current visible X-axis range from the plot layout
        if (plot.layout && plot.layout.xaxis) {{
            var axis = plot.layout.xaxis;
            // First try explicit range
            if (axis.range && axis.range.length === 2) {{
                return axis.range[1] - axis.range[0];
            }}
            // Fall back: compute from axis data bounds (works with auto-range)
            if (axis._fullRange && axis._fullRange.length === 2) {{
                return axis._fullRange[1] - axis._fullRange[0];
            }}
        }}
        // Ultimate fallback: use X_MAX - X_MIN from Python
        return X_MAX - X_MIN;
    }}

    function applySettings(plot, Plotly) {{
        var width = plot.offsetWidth || window.parent.innerWidth;
        // For season year mode with zoom, use zoom range for initial dtick
        // Otherwise use full data range (X_MAX - X_MIN) so all years display properly
        var initialRange = (!IS_AGE_MODE && !IS_GAMES_MODE && X_ZOOM_MAX > X_ZOOM_MIN)
            ? (X_ZOOM_MAX - X_ZOOM_MIN) : (X_MAX - X_MIN);
        var axisTickFontSize = calcResponsiveAxisTickFontSize(width);
        var updates = {{
            'xaxis.dtick': calcDtick(width, initialRange),
            'xaxis.tickfont.size': axisTickFontSize,
            'yaxis.tickfont.size': axisTickFontSize,
        }};
        updates['xaxis.tickangle'] = (IS_AGE_MODE || IS_GAMES_MODE) ? 0 : -45;
        Plotly.relayout(plot, updates).then(function() {{
            syncToolbarTitleOffset(plot, window.parent);
        }});

        // Clamp pan/zoom to data region and update dtick on zoom
        var _updating = false;
        plot.on('plotly_relayout', function(evt) {{
            if (_updating) return;

            // Handle clamping
            var clamps = {{}};
            var needsClamp  = false;
            var r0 = evt['xaxis.range[0]'], r1 = evt['xaxis.range[1]'];
            var y0 = evt['yaxis.range[0]'], y1 = evt['yaxis.range[1]'];
            if (r0 !== undefined && r0 < X_MIN) {{ clamps['xaxis.range[0]'] = X_MIN; needsClamp = true; }}
            if (r1 !== undefined && r1 > X_MAX) {{ clamps['xaxis.range[1]'] = X_MAX; needsClamp = true; }}
            if (y0 !== undefined && y0 < Y_MIN) {{ clamps['yaxis.range[0]'] = Y_MIN; needsClamp = true; }}
            if (y1 !== undefined && y1 > Y_MAX) {{ clamps['yaxis.range[1]'] = Y_MAX; needsClamp = true; }}
            if (needsClamp) {{ _updating = true; Plotly.relayout(plot, clamps); _updating = false; }}

            // For season year mode, update dtick based on current visible range
            // Handle both zoom (r0 or r1 defined) and double-click reset (both undefined)
            if (!IS_AGE_MODE && !IS_GAMES_MODE) {{
                // Check for double-click reset (both ranges are undefined)
                var isReset = (r0 === undefined && r1 === undefined);
                if (isReset || r0 !== undefined || r1 !== undefined) {{
                    var currentRange = getCurrentXRange(plot);
                    var newDtick = calcDtick(width, currentRange);
                    // Only update if dtick actually changed
                    if (plot.layout && plot.layout.xaxis && plot.layout.xaxis.dtick !== newDtick) {{
                        _updating = true;
                        Plotly.relayout(plot, {{'xaxis.dtick': newDtick}});
                        _updating = false;
                    }}
                }}
            }}
        }});
    }}

    function bindShareButton(parent) {{
        var btn = parent.document.getElementById(SHARE_BUTTON_ID);
        if (!btn || btn.dataset.bound === '1') return;
        btn.dataset.bound = '1';
        var label = btn.querySelector('.nhl-chart-share-btn__label');

        function encodeShareValue(value) {{
            return encodeURIComponent(String(value))
                .replace(/%3B/gi, ';')
                .replace(/%2C/gi, ',');
        }}

        function buildShareUrl(parent) {{
            var UrlCtor = parent.URL || URL;
            var url = new UrlCtor(parent.location.href);
            var parts = [];

            Object.entries(SHARE_PARAMS).forEach(function(entry) {{
                var key = entry[0];
                var value = entry[1];
                if (value === null || value === undefined) return;
                var clean = String(value);
                if (!clean.length) return;
                parts.push(encodeURIComponent(key) + '=' + encodeShareValue(clean));
            }});

            url.search = parts.length ? ('?' + parts.join('&')) : '';
            return url.toString();
        }}

        btn.addEventListener('click', function() {{
            var url = buildShareUrl(parent);
            var succeed = function() {{
                btn.classList.add('is-copied');
                if (label) label.textContent = 'Copied';
                setTimeout(function() {{
                    btn.classList.remove('is-copied');
                    if (label) label.textContent = 'Copy link';
                }}, 1400);
            }};
            if (parent.history && parent.history.replaceState) {{
                parent.history.replaceState(null, '', url);
            }}
            if (parent.navigator && parent.navigator.clipboard) {{
                parent.navigator.clipboard.writeText(url).then(succeed).catch(function() {{
                    var t = parent.document.createElement('input');
                    t.value = url; parent.document.body.appendChild(t);
                    t.select(); parent.document.execCommand('copy');
                    parent.document.body.removeChild(t); succeed();
                }});
            }} else {{
                var t = parent.document.createElement('input');
                t.value = url; parent.document.body.appendChild(t);
                t.select(); parent.document.execCommand('copy');
                parent.document.body.removeChild(t); succeed();
            }}
        }});
    }}

    function init() {{
        var parent = window.parent;
        var Plotly = parent.Plotly;
        if (!Plotly) {{ setTimeout(init, 200); return; }}
        var plots = parent.document.querySelectorAll('.js-plotly-plot');
        if (!plots.length) {{ setTimeout(init, 200); return; }}
        plots.forEach(function(p) {{ applySettings(p, Plotly); }});
        bindShareButton(parent);

        parent.addEventListener('resize', function() {{
            parent.document.querySelectorAll('.js-plotly-plot').forEach(function(p) {{
                var range = getCurrentXRange(p);
                var width = p.offsetWidth || parent.innerWidth;
                Plotly.relayout(p, {{
                    'xaxis.dtick': calcDtick(width, range),
                    'xaxis.tickangle': (IS_AGE_MODE || IS_GAMES_MODE) ? 0 : -45,
                    'xaxis.tickfont.size': calcResponsiveAxisTickFontSize(width),
                    'yaxis.tickfont.size': calcResponsiveAxisTickFontSize(width),
                }}).then(function() {{
                    syncToolbarTitleOffset(p, parent);
                }});
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
