"""
nhl.comparison -- Right-column player comparison panel for the NHL Age Curves app.

Renders one stat card per selected player showing a full-body hero image,
career counting stats totals, all-time ranking, and best season highlight.
Imported and called from app.py whenever players are loaded (always visible).

Imports from project:
    nhl.data_loaders  -- get_player_hero_image(), get_player_current_team(),
                         get_player_career_rank()
"""

import streamlit as st

from nhl.data_loaders import (
    get_player_career_rank,
    get_player_current_team,
    get_player_hero_image,
)

_TEAM_LOGO_URL = "https://assets.nhle.com/logos/nhl/svg/{abbr}_light.svg"


def _ordinal(n: int) -> str:
    """Return ordinal string for a positive integer (e.g. 1 -> '1st').

    Args:
        n: Positive integer to convert.

    Returns:
        String with English ordinal suffix.
    """
    if 11 <= (n % 100) <= 13:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def render_comparison_panel(
    processed_dfs: list,
    players: dict,
    peak_info: dict,
    metric: str,
    stat_category: str,
    season_type: str,
) -> None:
    """Render the right-column player comparison panel.

    Displays one stat card per player stacked vertically. Each card shows a
    full-body hero image on the left and on the right: player name with current
    team logo, career totals, all-time career rank (by player ID lookup), and
    best season highlight. All text rows are packed into one HTML block to
    eliminate Streamlit's default inter-paragraph gaps.

    Args:
        processed_dfs: List of per-player DataFrames from process_players().
            Each DataFrame contains post-pipeline stats with a BaseName column.
        players: Dict mapping player ID (int or str) to display name (str).
        peak_info: Dict mapping base_name (str) to peak season metadata dict
            with keys: age, season_year, y, raw_peak_val, pid.
        metric: Currently selected stat metric label (e.g., 'Points', 'Goals').
        stat_category: 'Skater' or 'Goalie' — controls which counting stats
            are shown in career totals and which stat is used for ranking.
        season_type: 'Regular', 'Playoffs', or 'Both' — passed to the rank
            function so rankings match the active season filter.
    """
    is_goalie = stat_category == "Goalie"
    rank_suffix = "career Wins" if is_goalie else "career Pts"

    # Build lookup: base_name -> proc_df for fast access
    proc_lookup: dict = {}
    for proc_df in processed_dfs:
        if proc_df.empty or 'BaseName' not in proc_df.columns:
            continue
        base = proc_df['BaseName'].iloc[0]
        proc_lookup[base] = proc_df

    for pid, name in players.items():
        proc_df = proc_lookup.get(name)
        if proc_df is None:
            continue

        # Real (non-projected) seasons only
        real = proc_df[~proc_df['Player'].str.contains(r'\(Proj\)', na=False)]
        if real.empty:
            continue

        hero_url  = get_player_hero_image(int(pid))
        team_abbr = get_player_current_team(int(pid))
        logo_html = (
            f"<img src='{_TEAM_LOGO_URL.format(abbr=team_abbr)}' "
            f"height='18' style='vertical-align:middle;margin-left:6px;opacity:0.9;'>"
            if team_abbr else ""
        )

        # Career totals from post-pipeline processed data
        career_gp = int(real['GP'].sum()) if 'GP' in real.columns else 0
        if is_goalie:
            career_w  = int(real['Wins'].sum())     if 'Wins'     in real.columns else 0
            career_so = int(real['Shutouts'].sum())  if 'Shutouts' in real.columns else 0
            career_sv = int(real['Saves'].sum())    if 'Saves'    in real.columns else 0
        else:
            career_g  = int(real['Goals'].sum())    if 'Goals'   in real.columns else 0
            career_a  = int(real['Assists'].sum())   if 'Assists' in real.columns else 0
            career_pt = int(real['Points'].sum())    if 'Points'  in real.columns else 0

        # All-time rank by playerId — exact lookup, no value drift
        rank = get_player_career_rank(int(pid), stat_category, season_type)

        # Best season from peak_info (metric-aware, pre-computed by pipeline)
        peak = peak_info.get(name)

        # Build stat rows HTML (conditionally include rank and best season)
        if is_goalie:
            stats_row = (
                f"W:&nbsp;{career_w} &nbsp;|&nbsp; "
                f"SO:&nbsp;{career_so} &nbsp;|&nbsp; "
                f"SV:&nbsp;{career_sv:,} &nbsp;|&nbsp; "
                f"GP:&nbsp;{career_gp}"
            )
        else:
            stats_row = (
                f"G:&nbsp;{career_g} &nbsp;|&nbsp; "
                f"A:&nbsp;{career_a} &nbsp;|&nbsp; "
                f"Pts:&nbsp;{career_pt} &nbsp;|&nbsp; "
                f"GP:&nbsp;{career_gp}"
            )

        rank_row = ""
        if rank is not None:
            rank_row = (
                f"<br><span style='font-size:14px;color:#4caf50;font-weight:bold;'>"
                f"#{_ordinal(rank)} all-time &mdash; {rank_suffix}"
                f"</span>"
            )

        best_row = ""
        if peak:
            age = peak.get('age', '?')
            sy  = peak.get('season_year')
            val = peak.get('y')

            peak_row_df = real[real['Age'] == age]
            peak_gp = (
                int(peak_row_df['GP'].iloc[0])
                if not peak_row_df.empty and 'GP' in peak_row_df.columns
                else '?'
            )
            sy_str = f"{sy - 1}-{str(sy)[2:]}" if sy else '?'
            if val is None:
                val_str = '?'
            elif isinstance(val, float) and val % 1 != 0:
                val_str = f"{val:.2f}"
            else:
                val_str = str(int(val))

            best_row = (
                f"<br><span style='font-size:14px;color:#999;font-weight:bold;'>"
                f"Best: Age&nbsp;{age} ({sy_str})"
                f" &mdash; {val_str}&nbsp;{metric} in {peak_gp}&nbsp;GP"
                f"</span>"
            )

        with st.container():
            img_col, stat_col = st.columns([1, 2], gap="small")

            with img_col:
                if hero_url:
                    st.image(hero_url, use_container_width=True)

            with stat_col:
                st.markdown(
                    f"<div style='line-height:1.4;margin:0;padding:0;'>"
                    f"<strong>{name}</strong>{logo_html}<br>"
                    f"{stats_row}"
                    f"{rank_row}"
                    f"{best_row}"
                    f"</div>",
                    unsafe_allow_html=True,
                )

        st.markdown(
            "<hr style='margin:6px 0;border:none;border-top:1px solid #2a2a2a;'>",
            unsafe_allow_html=True,
        )
