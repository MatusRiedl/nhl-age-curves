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
import plotly.graph_objects as go
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
    peak_info: dict = None,
    do_prime: bool = False,
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
        historical_baselines: Baseline dict keyed by Skater and Goalie.
        team_baselines:       {season_year: {metric: value}}.
        raw_dfs_cache:        Raw DataFrames for the click dialog.
        ml_clones_dict:       KNN clone dicts for the click dialog.
        season_type:          'Regular', 'Playoffs', or 'Both'.
        sidebar_keys:         Dict with 'search_term', 'top_selected', 'team_abbr',
                              'roster_player' — used for chart widget key generation.
        peak_info:            {base_name: {age, x, y, ...}} from player_pipeline.
        do_prime:            Whether to show peak age highlight bands.
    """
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
            base_label = (
                'Goalie 75th Percentile Baseline'
                if stat_category == 'Goalie'
                else 'Skater 75th Percentile Baseline'
            )
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
    baseline_traces = []
    player_colors = {}  # Map player name -> color
    proj_traces = []  # Store (name, x, y, color) for projection glow traces
    
    # First pass: capture player colors and projection data
    for trace in fig.data:
        if "(Proj)" not in trace.name and "Baseline" not in trace.name:
            # This is a real player line - capture its color
            player_colors[trace.name] = trace.line.color if trace.line.color else None
    
    for trace in fig.data:
        if "(Proj)" in trace.name:
            # Extract player name from projection (e.g., "Sebastian Aho (Proj)" -> "Sebastian Aho")
            player_name = trace.name.replace(" (Proj)", "")
            proj_color = player_colors.get(player_name) if player_colors.get(player_name) else 'gray'
            proj_traces.append({
                'name': trace.name,
                'x': trace.x,
                'y': trace.y,
                'color': proj_color,
            })
            # Style projection to match player color with dotted style
            trace.line.dash          = 'dot'
            trace.line.color         = proj_color
            trace.marker.symbol      = 'circle-open'
        elif "Baseline" in trace.name:
            trace.line.dash          = 'dash'
            trace.line.color         = 'rgba(255, 255, 255, 0.55)'
            trace.line.width         = 2
            trace.marker.size        = 1
            baseline_traces.append({'x': trace.x, 'y': trace.y})

    # Add stacked glow traces for baseline (after loop to avoid modifying fig.data during iteration)
    if baseline_traces and do_base and not games_mode:
        for baseline_trace in baseline_traces:
            fig.add_trace(go.Scatter(
                x=baseline_trace['x'], y=baseline_trace['y'],
                mode='lines',
                line=dict(color='rgba(255,255,255,0.06)', width=12, dash='dash'),
                showlegend=False,
                hoverinfo='skip',
                name='_glow_outer',
            ))
            fig.add_trace(go.Scatter(
                x=baseline_trace['x'], y=baseline_trace['y'],
                mode='lines',
                line=dict(color='rgba(255,255,255,0.12)', width=5, dash='dash'),
                showlegend=False,
                hoverinfo='skip',
                name='_glow_inner',
            ))

    # Add glow traces for projection lines (use player's color for each projection)
    for proj in proj_traces:
        if proj['x'] is not None and proj['y'] is not None:
            # Outer glow
            fig.add_trace(go.Scatter(
                x=proj['x'], y=proj['y'],
                mode='lines',
                line=dict(color=proj['color'], width=10, dash='dot'),
                showlegend=False,
                hoverinfo='skip',
                name='_proj_glow_outer',
            ))
            # Inner glow
            fig.add_trace(go.Scatter(
                x=proj['x'], y=proj['y'],
                mode='lines',
                line=dict(color=proj['color'], width=4, dash='dot'),
                showlegend=False,
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
        margin      = dict(l=0, r=0, t=40, b=12),
        height      = 500,
        font        = dict(size=17),
        hoverlabel  = dict(font_size=17, font_family="Arial", bgcolor="#1E1E1E"),
        legend      = dict(
            title=None, orientation="h",
            yanchor="top", y=-0.22,
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
        fig.update_layout(
            margin = dict(l=0, r=0, t=40, b=18),
            legend = dict(y=-0.35),
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
            title_text  = "Season Year",
            dtick       = _team_dtick,
            tickangle   = -45,
            automargin  = True,
            title_font  = dict(size=25, family='Arial Black'),
            tickfont    = dict(size=18, family='Arial Black'),
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

    plotly_config = {
        "displayModeBar": True,
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
        var updates = {{'xaxis.dtick': calcDtick(width, initialRange)}};
        updates['xaxis.tickangle'] = (IS_AGE_MODE || IS_GAMES_MODE) ? 0 : -45;
        Plotly.relayout(plot, updates);

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

    // Share link button helpers
    function injectShareStyles(parent) {{
        if (parent.document.getElementById('nhl-share-btn-style')) return;
        var s = parent.document.createElement('style');
        s.id = 'nhl-share-btn-style';
        s.textContent = [
            '.nhl-share-btn {{',
            '  position:absolute; left:10px; z-index:1001;',
            '  cursor:pointer; padding:4px;',
            '  display:flex; align-items:center;',
            '  gap:6px;',
            '  opacity:1; transition:opacity 0.2s, color 0.3s;',
            '  color:#c0c0c0;',
            '  background:none;',
            '  font-size:13px; font-weight:600;',
            '}}',
            '.nhl-share-btn:hover {{ color:#ffffff; }}',
            '.nhl-share-btn svg {{ width:22px; height:22px; display:block; }}',
            '@media (max-width:768px) {{',
            '  .nhl-share-btn {{ padding:3px 5px; gap:4px; font-size:11px; }}',
            '  .nhl-share-btn svg {{ width:14px; height:14px; }}',
            '}}',
        ].join('');
        parent.document.head.appendChild(s);
    }}

    function positionShareBtn(plot, btn, parent) {{
        // Keep the button centered in the top gutter above the plotting area.
        var topGutter = 40;
        if (
            plot && plot._fullLayout && plot._fullLayout._size &&
            typeof plot._fullLayout._size.t === 'number'
        ) {{
            topGutter = plot._fullLayout._size.t;
        }} else if (
            plot && plot.layout && plot.layout.margin &&
            typeof plot.layout.margin.t === 'number'
        ) {{
            topGutter = plot.layout.margin.t;
        }}

        var fallbackHeight = ((parent.innerWidth || 1024) <= 768) ? 20 : 28;
        var btnHeight = btn.offsetHeight || fallbackHeight;
        var topPx = Math.max(4, Math.round((topGutter - btnHeight) / 2));
        btn.style.top = topPx + 'px';
    }}

    function addShareBtn(plot, parent) {{
        var existing = plot.querySelector('.nhl-share-btn');
        if (existing) existing.remove();

        var btn = parent.document.createElement('div');
        btn.className = 'nhl-share-btn';
        btn.title = 'Copy share link';
        btn.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"'
            + ' fill="none" stroke="currentColor" stroke-width="2"'
            + ' stroke-linecap="round" stroke-linejoin="round">'
            + '<path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/>'
            + '<path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/>'
            + '</svg>'
            + '<span>Copy link</span>';

        btn.addEventListener('click', function() {{
            var url = parent.location.href;
            var succeed = function() {{
                btn.style.color = '#4caf50';
                setTimeout(function() {{ btn.style.color = ''; }}, 1500);
            }};
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

        plot.style.position = 'relative';
        plot.appendChild(btn);
        positionShareBtn(plot, btn, parent);
    }}

    function init() {{
        var parent = window.parent;
        var Plotly = parent.Plotly;
        if (!Plotly) {{ setTimeout(init, 200); return; }}
        var plots = parent.document.querySelectorAll('.js-plotly-plot');
        if (!plots.length) {{ setTimeout(init, 200); return; }}
        plots.forEach(function(p) {{ applySettings(p, Plotly); }});

        // Inject share button
        injectShareStyles(parent);
        if (plots.length) plots.forEach(function(p) {{ addShareBtn(p, parent); }});

        parent.addEventListener('resize', function() {{
            parent.document.querySelectorAll('.js-plotly-plot').forEach(function(p) {{
                var range = getCurrentXRange(p);
                Plotly.relayout(p, {{'xaxis.dtick': calcDtick(p.offsetWidth || parent.innerWidth, range), 'xaxis.tickangle': (IS_AGE_MODE || IS_GAMES_MODE) ? 0 : -45}});
                var btn = p.querySelector('.nhl-share-btn');
                if (btn) positionShareBtn(p, btn, parent);
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
