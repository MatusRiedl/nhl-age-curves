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


@st.cache_data(ttl=300)
def _check_api_health() -> list:
    """Probe each NHL API endpoint and return (label, ok) pairs.

    Uses stream=True + close() to check HTTP status without downloading
    response bodies — critical for the Records endpoint which returns
    all-time career data and would be very large to fully download.
    Results are cached for 5 minutes to avoid hammering APIs on every rerun.

    Returns:
        List of (label, ok) tuples where ok is True when the endpoint
        responds with an HTTP status below 400, False on any error or timeout.
    """
    probes = [
        ("Search",       "https://search.d3.nhle.com/api/v1/search/player?q=Mc&limit=1&culture=en-us"),
        ("Player Stats", "https://api-web.nhle.com/v1/player/8478402/landing"),
        ("Roster",       "https://api-web.nhle.com/v1/roster/EDM/current"),
        ("Team Stats",   "https://api.nhle.com/stats/rest/en/team/summary?limit=1"),
        ("Records",      "https://records.nhl.com/site/api/skater-career-scoring-regular-season"),
    ]
    try:
        import requests
    except Exception:
        return [(label, False) for label, _ in probes]
    results = []
    for label, url in probes:
        try:
            r = requests.get(url, timeout=3, stream=True)
            r.close()
            results.append((label, r.status_code < 400))
        except Exception:
            results.append((label, False))
    return results


def _render_ram_footer() -> None:
    """Render a live process RAM readout and API health check at the bottom of the sidebar.

    Tries psutil first (cross-platform). Falls back to /proc/self/status
    (Linux / Streamlit Cloud, no external deps). Shows 'N/A' on Windows
    without psutil installed.

    API health shows a 🟢/🟡 traffic light for each NHL endpoint, cached
    for 5 minutes via _check_api_health().
    """
    rss_mb = "N/A"
    try:
        import os
        import psutil
        rss_mb = f"{psutil.Process(os.getpid()).memory_info().rss / 1024 / 1024:.0f} MB"
    except Exception:
        try:
            with open("/proc/self/status") as f:
                for line in f:
                    if line.startswith("VmRSS:"):
                        rss_mb = f"{int(line.split()[1]) / 1024:.0f} MB"
                        break
        except Exception:
            pass
    st.markdown("---")
    st.caption(f"RAM: {rss_mb}")
    try:
        statuses = _check_api_health()
        lines = ["**API Health** *(5 min cache)*"]
        for label, ok in statuses:
            dot = "🟢" if ok else "🟡"
            lines.append(f"{dot} {label}")
        st.caption("\n\n".join(lines))
    except Exception:
        st.caption("API Health: unavailable")


def render_sidebar() -> dict:
    """Render the full sidebar UI and return chart cache-busting keys.

    Renders the Skater/Goalie/Team category radio at the top of the sidebar,
    then dispatches to _render_player_sidebar() or _render_team_sidebar() based
    on st.session_state.stat_category.

    Returns:
        Dict with keys 'search_term', 'top_selected', 'team_abbr', 'roster_player'.
        Values are strings (empty string if the widget was not shown this run).
        Used as part of the chart widget key to force a re-render when sidebar
        selections change.
    """
    with st.sidebar:
        st.radio(
            "Category:",
            ["Skater", "Goalie", "Team"],
            horizontal=True,
            key="stat_category",
            label_visibility="collapsed",
        )
        st.markdown("---")
        if st.session_state.stat_category != "Team":
            return _render_player_sidebar()
        else:
            return _render_team_sidebar()


def _render_player_sidebar() -> dict:
    """Render the player-mode sidebar: search, top-50, roster, and player board.

    Three ways to add a player:
        1. Global search (D3 API + local records fallback).
        2. Top 50 all-time dropdown (auto-adds on selection).
        3. Active roster selector by team (auto-adds on selection).

    Writes to:
        st.session_state.players     — dict {pid: name} shared across Skater/Goalie modes
        st.session_state.search_ver  — incrementing int to reset the search box
        st.session_state.search_opts — current search result dict
        st.session_state.top50_ver   — incrementing int to reset the top-50 box
        st.session_state.top50_opts  — current top-50 dict for callback lookup
        st.session_state.roster_ver  — incrementing int to reset the roster box
        st.session_state.roster_opts — current roster dict for callback lookup

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
    if 'top50_ver' not in st.session_state:
        st.session_state.top50_ver = 0
    if 'top50_opts' not in st.session_state:
        st.session_state.top50_opts = {}
    if 'roster_ver' not in st.session_state:
        st.session_state.roster_ver = 0
    if 'roster_opts' not in st.session_state:
        st.session_state.roster_opts = {}

    def _on_player_select():
        """Callback: add the selected player to the shared board and reset the search box."""
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

    def _on_top50_select():
        """Callback: add the selected top-50 player to the shared board and reset the dropdown."""
        ver  = st.session_state.top50_ver
        sel  = st.session_state.get(f"_top50_pick_{ver}")
        _SENT = "— select a player —"
        if not sel or sel == _SENT:
            return
        pid = st.session_state.top50_opts.get(sel)
        if pid is None:
            return
        name = sel.split(". ", 1)[-1].split(" (")[0]
        st.session_state.players[pid] = name
        st.session_state.top50_ver = ver + 1

    def _on_roster_select():
        """Callback: add the selected roster player to the shared board and reset the dropdown."""
        ver  = st.session_state.roster_ver
        sel  = st.session_state.get(f"_roster_pick_{ver}")
        _SENT = "— select a player —"
        if not sel or sel == _SENT:
            return
        pid = st.session_state.roster_opts.get(sel)
        if pid is None:
            return
        name = sel.split("] ")[-1] if "]" in sel else sel
        if " #" in name:
            name = name.split(" #")[0]
        st.session_state.players[pid] = name
        st.session_state.roster_ver = ver + 1

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
        current_metric = st.session_state.get("skater_metric", "Points")
        top_50_dict    = get_top_50(current_metric)
        top_50_label   = "Top 50 All-Time Skaters"
    _SENT = "— select a player —"
    st.session_state.top50_opts = top_50_dict
    top_selected = st.selectbox(
        top_50_label,
        [_SENT] + list(top_50_dict.keys()),
        key=f"_top50_pick_{st.session_state.top50_ver}",
        on_change=_on_top50_select,
    )

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
            st.session_state.roster_opts = roster
            roster_player = st.selectbox(
                "Select Player:",
                [_SENT] + list(roster.keys()),
                key=f"_roster_pick_{st.session_state.roster_ver}",
                on_change=_on_roster_select,
                label_visibility="collapsed",
            )

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

    _render_ram_footer()

    return {
        "search_term":   search_term,
        "top_selected":  top_selected,
        "team_abbr":     team_abbr,
        "roster_player": roster_player,
    }


def _render_team_sidebar() -> dict:
    """Render the team-mode sidebar: team selector (auto-adds on selection), team board.

    The team logo is shown above the dropdown and reflects the current dropdown selection.
    Selecting a team immediately adds it to the board and resets the dropdown.

    Writes to:
        st.session_state.teams    — dict {abbr: name}
        st.session_state.team_ver — incrementing int to reset the team selectbox

    Returns:
        Dict with sidebar keys for chart cache-busting (only 'team_abbr' is relevant).
    """
    st.subheader("Team Comparison")

    if 'team_ver' not in st.session_state:
        st.session_state.team_ver = 0

    _SENT = "— select a team —"
    _team_keys = list(ACTIVE_TEAMS.keys())

    def _on_team_select():
        """Callback: add the selected team to the board and reset the dropdown."""
        ver = st.session_state.team_ver
        sel = st.session_state.get(f"_team_pick_{ver}")
        if not sel or sel == _SENT:
            return
        st.session_state.teams[sel] = ACTIVE_TEAMS[sel]
        st.session_state.team_ver = ver + 1

    # Logo shown ABOVE the dropdown — reflects current dropdown selection
    _logo_abbr = st.session_state.get(f"_team_pick_{st.session_state.team_ver}", _SENT)
    if _logo_abbr and _logo_abbr != _SENT:
        st.markdown(
            f"<div style='text-align:center;margin-bottom:5px;'>"
            f"<img src='https://assets.nhle.com/logos/nhl/svg/{_logo_abbr}_light.svg' height='40'>"
            f"</div>",
            unsafe_allow_html=True,
        )

    _team_sel = st.selectbox(
        "Select Team:",
        [_SENT] + _team_keys,
        format_func=lambda x: x if x == _SENT else f"{x} — {ACTIVE_TEAMS[x]}",
        key=f"_team_pick_{st.session_state.team_ver}",
        on_change=_on_team_select,
        label_visibility="collapsed",
    )

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

    _render_ram_footer()

    return {
        "search_term":   "",
        "top_selected":  "",
        "team_abbr":     _team_sel if _team_sel != _SENT else "",
        "roster_player": "",
    }
