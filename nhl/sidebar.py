"""
nhl.sidebar — Player and team sidebar UI for the NHL Age Curves app.

Renders the full sidebar, switching between player mode and team mode based on
st.session_state.stat_category.  Reads and writes session state directly (standard
Streamlit pattern for sidebar widgets).

Returns a sidebar_keys dict that the chart renderer uses for cache-busting the
chart widget key.  This avoids the chart renderer having to access sidebar widget
values from session state, keeping chart.py's dependency surface narrow.

Imports from project:
    nhl.constants    — ACTIVE_TEAMS
    nhl.data_loaders — search_player, search_local_players, get_top_50,
                       get_top_50_goalies, get_team_roster, get_player_headshot
"""

import streamlit as st

from nhl.constants import ACTIVE_TEAMS
from nhl.data_loaders import (
    get_player_headshot,
    get_team_roster,
    get_top_50,
    get_top_50_goalies,
    search_local_players,
    search_player,
)


def render_sidebar() -> dict:
    """Render the full sidebar UI and return chart cache-busting keys.

    Dispatches to _render_player_sidebar() or _render_team_sidebar() based on
    st.session_state.stat_category.

    Returns:
        Dict with keys 'search_term', 'top_selected', 'team_abbr', 'roster_player'.
        Values are strings (empty string if the widget was not shown this run).
        Used as part of the chart widget key to force a re-render when sidebar
        selections change.
    """
    with st.sidebar:
        if st.session_state.stat_category != "Team":
            return _render_player_sidebar()
        else:
            return _render_team_sidebar()


def _render_player_sidebar() -> dict:
    """Render the player-mode sidebar: search, top-50, roster, and player board.

    Three ways to add a player:
        1. Global search (D3 API + local records fallback).
        2. Top 50 all-time dropdown with 'Add Legend' button.
        3. Active roster selector by team with 'Add Roster Player' button.

    Writes to:
        st.session_state.players     — dict {pid: name}
        st.session_state.search_ver  — incrementing int to reset the search box
        st.session_state.search_opts — current search result dict

    Returns:
        Dict with sidebar keys for chart cache-busting.
    """
    search_term   = ""
    top_selected  = ""
    team_abbr     = ""
    roster_player = ""

    st.subheader("Global Search")

    if 'search_ver' not in st.session_state:
        st.session_state.search_ver = 0
    if 'search_opts' not in st.session_state:
        st.session_state.search_opts = {}

    def _on_player_select():
        """Callback: add the selected player to the board and reset the search box."""
        ver  = st.session_state.search_ver
        sel  = st.session_state.get(f"_player_pick_{ver}")
        _SENT = "— select a player —"
        if not sel or sel == _SENT:
            return
        pid = st.session_state.search_opts.get(sel)
        if pid is None:
            return
        name = sel.split("] ")[-1] if "]" in sel else sel
        st.session_state.players[pid] = name
        st.session_state.search_ver  = ver + 1
        st.session_state.search_opts = {}

    search_term = st.text_input(
        "Search player:",
        placeholder="e.g., McDavid, Crosby, Connor…",
        label_visibility="collapsed",
        key=f"search_input_{st.session_state.search_ver}",
    )

    opts = {}
    if search_term:
        results = search_player(search_term)
        for p in results:
            tm    = p.get('teamAbbrev')
            label = f"[{tm}] {p['name']}" if tm else p['name']
            opts[label] = int(p['playerId'])
        local = search_local_players(search_term, st.session_state.stat_category)
        for label, pid in local.items():
            if pid not in opts.values():
                opts[label] = pid
        # Active players (have [TEAM] prefix) first, retired/free agents below
        active_opts   = {k: v for k, v in opts.items() if k.startswith("[")}
        inactive_opts = {k: v for k, v in opts.items() if not k.startswith("[")}
        opts = {**active_opts, **inactive_opts}

    st.session_state.search_opts = opts

    if opts:
        _SENT = "— select a player —"
        st.selectbox(
            "Results:",
            [_SENT] + list(opts.keys()),
            key=f"_player_pick_{st.session_state.search_ver}",
            on_change=_on_player_select,
            label_visibility="collapsed",
        )
    elif search_term:
        st.caption("No players found")

    st.markdown("---")

    _is_goalie_mode = st.session_state.stat_category == "Goalie"
    if _is_goalie_mode:
        top_50_dict  = get_top_50_goalies()
        top_50_label = "Top 50 All-Time Goalies"
    else:
        top_50_dict  = get_top_50()
        top_50_label = "Top 50 All-Time Skaters"
    top_selected = st.selectbox(top_50_label, list(top_50_dict.keys()))

    st.markdown("<div class='blue-btn-anchor'></div>", unsafe_allow_html=True)
    if st.button("Add Legend", use_container_width=True):
        st.session_state.players[top_50_dict[top_selected]] = top_selected.split(". ")[-1]

    team_abbr = st.selectbox(
        "Active Rosters",
        list(ACTIVE_TEAMS.keys()),
        format_func=lambda x: f"{x} - {ACTIVE_TEAMS[x]}",
    )
    if team_abbr:
        st.markdown(
            f"<div style='text-align:center;margin-bottom:5px;'>"
            f"<img src='https://assets.nhle.com/logos/nhl/svg/{team_abbr}_light.svg' height='40'>"
            f"</div>",
            unsafe_allow_html=True,
        )
        roster = get_team_roster(team_abbr)
        if _is_goalie_mode:
            roster = {k: v for k, v in roster.items() if k.startswith("[G]")}
        else:
            roster = {k: v for k, v in roster.items() if not k.startswith("[G]")}
        if roster:
            roster_player = st.selectbox(
                "Select Player:", list(roster.keys()), label_visibility="collapsed"
            )
            st.markdown("<div class='blue-btn-anchor'></div>", unsafe_allow_html=True)
            if st.button("Add Roster Player", use_container_width=True):
                clean_name = roster_player.split("] ")[-1] if "]" in roster_player else roster_player
                st.session_state.players[roster[roster_player]] = clean_name

    st.markdown("---")
    if st.session_state.players:
        for pid, name in list(st.session_state.players.items()):
            c_name, c_btn = st.columns([5, 1], vertical_alignment="center", gap="small")
            with c_name:
                headshot = get_player_headshot(pid)
                img_html = (
                    f"<img src='{headshot}' style='width:32px;height:32px;"
                    f"border-radius:50%;object-fit:cover;flex-shrink:0;'>"
                    if headshot else ""
                )
                st.markdown(
                    f"<div style='display:flex;align-items:center;gap:8px;'>"
                    f"{img_html}"
                    f"<div class='player-name'>{name}</div>"
                    f"</div>",
                    unsafe_allow_html=True,
                )
            with c_btn:
                if st.button("✖", key=f"drop_{pid}", type="primary"):
                    del st.session_state.players[pid]
                    st.rerun()
    else:
        st.info("Board is empty")

    return {
        "search_term":   search_term,
        "top_selected":  top_selected,
        "team_abbr":     team_abbr,
        "roster_player": roster_player,
    }


def _render_team_sidebar() -> dict:
    """Render the team-mode sidebar: team selector, Add Team button, team board.

    The team logo is shown above the dropdown and updates live on selection change
    by reading st.session_state.team_sel_abbr (set by the selectbox key).

    Writes to:
        st.session_state.teams       — dict {abbr: name}
        st.session_state.team_sel_abbr — currently highlighted team abbreviation

    Returns:
        Dict with sidebar keys for chart cache-busting (only 'team_abbr' is relevant).
    """
    st.subheader("Team Comparison")

    # Logo shown ABOVE the dropdown — updates live on selection change
    _logo_abbr = st.session_state.get("team_sel_abbr", list(ACTIVE_TEAMS.keys())[0])
    st.markdown(
        f"<div style='text-align:center;margin-bottom:5px;'>"
        f"<img src='https://assets.nhle.com/logos/nhl/svg/{_logo_abbr}_light.svg' height='40'>"
        f"</div>",
        unsafe_allow_html=True,
    )

    st.selectbox(
        "Select Team:",
        list(ACTIVE_TEAMS.keys()),
        format_func=lambda x: f"{x} — {ACTIVE_TEAMS[x]}",
        key="team_sel_abbr",
        label_visibility="collapsed",
    )

    st.markdown("<div class='blue-btn-anchor'></div>", unsafe_allow_html=True)
    if st.button("Add Team", use_container_width=True):
        _sel = st.session_state.team_sel_abbr
        st.session_state.teams[_sel] = ACTIVE_TEAMS[_sel]

    st.markdown("---")

    if st.session_state.teams:
        for _abbr, _name in list(st.session_state.teams.items()):
            c_name, c_btn = st.columns([5, 1], vertical_alignment="center", gap="small")
            with c_name:
                _logo_url = f"https://assets.nhle.com/logos/nhl/svg/{_abbr}_light.svg"
                st.markdown(
                    f"<div style='display:flex;align-items:center;gap:8px;'>"
                    f"<img src='{_logo_url}' style='width:32px;height:32px;"
                    f"object-fit:contain;flex-shrink:0;'>"
                    f"<div class='player-name'>{_name}</div>"
                    f"</div>",
                    unsafe_allow_html=True,
                )
            with c_btn:
                if st.button("✖", key=f"drop_team_{_abbr}", type="primary"):
                    del st.session_state.teams[_abbr]
                    st.rerun()
    else:
        st.info("Board is empty")

    return {
        "search_term":   "",
        "top_selected":  "",
        "team_abbr":     st.session_state.get("team_sel_abbr", ""),
        "roster_player": "",
    }
