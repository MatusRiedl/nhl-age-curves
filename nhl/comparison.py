"""Tabbed comparison panel for overview cards, trophies, and live games."""

from dataclasses import dataclass
from html import escape
from typing import Callable

import pandas as pd
import streamlit as st

from nhl.constants import ACTIVE_TEAMS, RATE_STATS, TEAM_FOUNDED
from nhl.data_loaders import (
    get_player_awards,
    get_player_career_rank,
    get_player_current_team,
    get_player_hero_image,
    get_player_season_rank_map,
    get_player_roster_info,
    get_team_all_time_stats,
    get_team_trophy_summary,
)
from nhl.schedule import get_featured_players, get_upcoming_games

_TEAM_LOGO_URL = "https://assets.nhle.com/logos/nhl/svg/{abbr}_light.svg"
_TEAM_SHORT_NAMES = {
    "ANA": "Ducks",
    "BOS": "Bruins",
    "BUF": "Sabres",
    "CGY": "Flames",
    "CAR": "Hurricanes",
    "CHI": "Blackhawks",
    "COL": "Avalanche",
    "CBJ": "Blue Jackets",
    "DAL": "Stars",
    "DET": "Red Wings",
    "EDM": "Oilers",
    "FLA": "Panthers",
    "LAK": "Kings",
    "MIN": "Wild",
    "MTL": "Canadiens",
    "NSH": "Predators",
    "NJD": "Devils",
    "NYI": "Islanders",
    "NYR": "Rangers",
    "OTT": "Senators",
    "PHI": "Flyers",
    "PIT": "Penguins",
    "SJS": "Sharks",
    "SEA": "Kraken",
    "STL": "Blues",
    "TBL": "Lightning",
    "TOR": "Maple Leafs",
    "UTA": "Hockey Club",
    "VAN": "Canucks",
    "VGK": "Golden Knights",
    "WSH": "Capitals",
    "WPG": "Jets",
}
_DEFAULT_PANEL_TAB = "overview"
_DEFAULT_PLAYER_RANK_COLOR = "#4caf50"
_CATEGORY_TAB_KEYS = {
    "Skater": "panel_tab_skater",
    "Goalie": "panel_tab_goalie",
    "Team": "panel_tab_team",
}


@dataclass(frozen=True)
class PanelTabSpec:
    """Definition of one comparison panel tab."""

    id: str
    label: str
    render_player: Callable[..., None]
    render_team: Callable[..., None]


def _season_span_label_from_id(season_id: int | None) -> str:
    """Convert seasonId (e.g. 20222023) to a short span (2022-23)."""
    if season_id is None:
        return "?"
    try:
        raw = int(season_id)
        raw_str = str(raw)
        if len(raw_str) >= 8:
            start = int(raw_str[:4])
        else:
            start = raw
        return f"{start}-{str(start + 1)[2:]}"
    except Exception:
        return "?"


def _format_chart_season_label(value: str | int) -> str:
    """Format one chart-season selector value for the comparison panel.

    Args:
        value: Raw season selector value.

    Returns:
        Human-readable label such as ``All`` or ``2024-25``.
    """
    if str(value) == "All":
        return "All"
    try:
        season_year = int(value)
        return f"{season_year}-{str(season_year + 1)[2:]}"
    except Exception:
        return str(value)


def _is_selected_season_mode(selected_season: str | int) -> bool:
    """Return whether the comparison panel is in single-season mode.

    Args:
        selected_season: Selected chart-season value.

    Returns:
        True when one specific season is selected.
    """
    return str(selected_season) != "All"


def _build_selected_season_scope_label(selected_season: str | int, season_type: str) -> str:
    """Build the selected-season scope copy for Overview cards.

    Args:
        selected_season: Selected chart-season value.
        season_type: Regular, Playoffs, or Both.

    Returns:
        Compact scope label such as ``2024-25 · Regular season game log``.
    """
    season_scope_map = {
        "Regular": "Regular season",
        "Playoffs": "Playoffs",
        "Both": "Regular + playoffs",
    }
    return (
        f"{_season_span_label_from_id(selected_season)}"
        f" · {season_scope_map.get(season_type, season_type)} game log"
    )


def _build_selected_season_rank_label(
    selected_season: str | int,
    season_type: str,
    metric: str,
    rank: int,
) -> str:
    """Build the selected-season leaderboard copy for Overview cards.

    Args:
        selected_season: Selected chart-season value.
        season_type: Regular, Playoffs, or Both.
        metric: Active chart metric.
        rank: 1-based league rank for the selected player.

    Returns:
        Compact leaderboard label such as ``#2 in 2024-25 Points``.
    """
    season_prefix_map = {
        'Regular': '',
        'Playoffs': 'Playoff ',
        'Both': 'Combined ',
    }
    metric_label = f"{season_prefix_map.get(season_type, '')}{metric}".strip()
    return f"#{rank} in {_season_span_label_from_id(selected_season)} {metric_label}"


def _get_visible_stat_total(real_df: pd.DataFrame, column: str, use_last_visible: bool) -> int:
    """Return a visible stat total from the active comparison rows.

    Args:
        real_df: Non-projection rows for one player.
        column: Stat column to total.
        use_last_visible: Use the last visible cumulative value instead of a sum.

    Returns:
        Integer total for the requested stat column.
    """
    if column not in real_df.columns or real_df.empty:
        return 0
    values = pd.to_numeric(real_df[column], errors="coerce").dropna()
    if values.empty:
        return 0
    total = values.iloc[-1] if use_last_visible else values.sum()
    return int(round(float(total)))


def _format_peak_metric_value(metric: str, value: float | int | None) -> str:
    """Format one peak metric value for Overview copy.

    Args:
        metric: Active metric name.
        value: Peak metric value.

    Returns:
        Readable formatted value or ``?``.
    """
    if value is None or pd.isna(value):
        return "?"
    numeric_value = float(value)
    if metric in RATE_STATS or not numeric_value.is_integer():
        return f"{numeric_value:.2f}"
    return str(int(numeric_value))


def _get_category_tab_key(stat_category: str) -> str:
    """Return the session-state key that stores the active panel tab.

    Args:
        stat_category: Active stat category string.

    Returns:
        Session-state key for the current category's comparison tab.
    """
    return _CATEGORY_TAB_KEYS.get(stat_category, "panel_tab_skater")


def get_panel_tab_ids() -> set[str]:
    """Return all registered panel tab IDs."""
    return {t.id for t in _PANEL_TABS}


def _get_player_chart_colors() -> dict[str, str | None]:
    """Return the active chart color map for real player traces.

    Args:
        None.

    Returns:
        Mapping of player display names to the colors used on the chart.
    """
    session_state = getattr(st, "session_state", None)
    if session_state is None:
        return {}

    if hasattr(session_state, "get"):
        player_colors = session_state.get("player_chart_colors", {})
    else:
        player_colors = getattr(session_state, "player_chart_colors", {})

    return player_colors if isinstance(player_colors, dict) else {}


def _iter_visible_players_for_category(processed_dfs: list, players: dict):
    """Yield selected players that still have visible rows in the active pipeline.

    Args:
        processed_dfs: Active processed DataFrames for the current chart category.
        players: Selected comparison players from session state.

    Returns:
        Iterator yielding ``(player_id, player_name, processed_df)`` tuples for
        players that still have non-projection rows in the active category.
    """
    proc_lookup: dict = {}
    for proc_df in processed_dfs:
        if proc_df.empty or "BaseName" not in proc_df.columns or "Player" not in proc_df.columns:
            continue
        base = proc_df["BaseName"].iloc[0]
        proc_lookup[base] = proc_df

    # Preserve insertion order from the selected players dict.
    for pid, name in players.items():
        proc_df = proc_lookup.get(name)
        if proc_df is None:
            continue
        real = proc_df[~proc_df["Player"].str.contains(r"\(Proj\)", na=False)]
        if real.empty:
            continue
        yield pid, name, proc_df


def render_comparison_area(
    processed_dfs: list,
    players: dict,
    teams: dict,
    peak_info: dict,
    metric: str,
    stat_category: str,
    season_type: str,
    team_mode: bool,
    selected_season: str | int = "All",
    chart_season_options: list[str | int] | None = None,
    do_cumul: bool = False,
) -> None:
    """Render the tabbed comparison area for the active category."""
    tab_lookup = {tab.id: tab for tab in _PANEL_TABS}
    tab_ids = list(tab_lookup.keys())
    if not tab_ids:
        st.info("No comparison tabs configured.")
        return

    tab_key = _get_category_tab_key(stat_category)
    if tab_key not in st.session_state:
        st.session_state[tab_key] = _DEFAULT_PANEL_TAB

    if st.session_state[tab_key] not in tab_lookup:
        st.session_state[tab_key] = _DEFAULT_PANEL_TAB

    default_tab_id = st.session_state.get(tab_key, _DEFAULT_PANEL_TAB)
    has_visible_comparison = bool(teams) if team_mode else any(
        True for _ in _iter_visible_players_for_category(processed_dfs, players)
    )
    # Empty boards should land on something useful instead of a blank Overview tab.
    if not has_visible_comparison and "live_games" in tab_lookup:
        default_tab = tab_lookup["live_games"]
    else:
        default_tab = tab_lookup.get(default_tab_id, tab_lookup[_DEFAULT_PANEL_TAB])
    default_label = default_tab.label

    if not team_mode and chart_season_options:
        st.markdown("<div id='comparison-season-filter'></div>", unsafe_allow_html=True)
        st.selectbox(
            "Chart season",
            options=chart_season_options,
            key="chart_season",
            format_func=_format_chart_season_label,
        )

    st.markdown("<div id='comparison-tabs'></div>", unsafe_allow_html=True)
    tab_containers = st.tabs(
        [tab_lookup[tab_id].label for tab_id in tab_ids],
        default=default_label,
    )

    for tab_id, tab_container in zip(tab_ids, tab_containers):
        tab_spec = tab_lookup[tab_id]
        with tab_container:
            if team_mode:
                tab_spec.render_team(
                    active_teams=teams,
                    metric=metric,
                )
            else:
                tab_spec.render_player(
                    processed_dfs=processed_dfs,
                    players=players,
                    peak_info=peak_info,
                    metric=metric,
                    stat_category=stat_category,
                    season_type=season_type,
                    selected_season=selected_season,
                    do_cumul=do_cumul,
                )


def _add_live_game_to_comparison(game: dict) -> None:
    """Add both teams plus featured players for one upcoming game.

    Args:
        game: Normalized game dict returned by ``nhl.schedule.get_upcoming_games()``.

    Returns:
        None.
    """
    st.session_state.teams[game["away_abbr"]] = game["away_name"]
    st.session_state.teams[game["home_abbr"]] = game["home_name"]

    featured = get_featured_players(game["home_abbr"], game["away_abbr"])
    st.session_state.teams.update(featured.get("teams", {}))
    st.session_state.players.update(featured.get("players", {}))


def _build_live_game_matchup_html(game: dict) -> str:
    """Build the matchup label HTML with both team logos.

    Args:
        game: Normalized game dict returned by ``get_upcoming_games()``.

    Returns:
        HTML string showing away and home logos beside short team names.
    """
    away_logo = _TEAM_LOGO_URL.format(abbr=game["away_abbr"])
    home_logo = _TEAM_LOGO_URL.format(abbr=game["home_abbr"])
    away_short_name = _get_team_short_name(game["away_abbr"], game["away_name"])
    home_short_name = _get_team_short_name(game["home_abbr"], game["home_name"])
    return (
        "<div class='live-games-matchup' style='display:flex;align-items:center;gap:8px;flex-wrap:wrap;'>"
        f"<img src='{away_logo}' height='26' style='vertical-align:middle;'>"
        f"<strong>{away_short_name}</strong>"
        "<span style='color:#aaa;font-size:13px;'>at</span>"
        f"<img src='{home_logo}' height='26' style='vertical-align:middle;'>"
        f"<strong>{home_short_name}</strong>"
        "</div>"
    )


def _get_team_short_name(team_abbr: str, fallback_name: str) -> str:
    """Return the short display name for a team.

    Args:
        team_abbr: Three-letter NHL team abbreviation.
        fallback_name: Full team name to use if no short mapping exists.

    Returns:
        Team nickname without the city or market prefix.
    """
    return _TEAM_SHORT_NAMES.get(team_abbr, ACTIVE_TEAMS.get(team_abbr, fallback_name))


def _render_live_games_tab() -> None:
    """Render the shared Live games tab UI.

    Args:
        None.

    Returns:
        None.

    Shows the next four upcoming NHL games and lets the user seed the
    comparison board with both teams plus each club's featured skater and goalie.
    """
    st.caption("Adds both teams, each club's points leader, and the best Save% goalie.")
    upcoming_games = get_upcoming_games(limit=4)
    if not upcoming_games:
        st.info("No upcoming NHL games found right now.")
        return

    for game in upcoming_games:
        detail_bits = [game["start_label_cest"]]
        if game.get("venue"):
            detail_bits.append(game["venue"])
        matchup_html = _build_live_game_matchup_html(game)
        detail_html = escape(" • ".join(detail_bits))
        button_key = f"add_live_game_{game['game_id']}_{game['away_abbr']}_{game['home_abbr']}"

        st.markdown(matchup_html, unsafe_allow_html=True)
        st.markdown(f"<div class='live-games-detail'>{detail_html}</div>", unsafe_allow_html=True)
        if st.button("Compare", key=button_key):
            _add_live_game_to_comparison(game)
            st.rerun()

        st.markdown(
            "<hr style='margin:2px 0 6px 0;border:none;border-top:1px solid #2a2a2a;'>",
            unsafe_allow_html=True,
        )


def _render_live_games_players(
    processed_dfs: list,
    players: dict,
    peak_info: dict,
    metric: str,
    stat_category: str,
    season_type: str,
    selected_season: str | int = "All",
    do_cumul: bool = False,
) -> None:
    """Live games tab for skater and goalie modes.

    Args:
        processed_dfs: Active processed DataFrames.
        players: Selected comparison players.
        peak_info: Peak-season metadata.
        metric: Active metric name.
        stat_category: Active category string.
        season_type: Active season scope.

    Returns:
        None.
    """
    del processed_dfs, players, peak_info, metric, stat_category, season_type, selected_season, do_cumul
    _render_live_games_tab()


def _render_live_games_teams(active_teams: dict, metric: str) -> None:
    """Live games tab for team mode.

    Args:
        active_teams: Selected comparison teams.
        metric: Active metric name.

    Returns:
        None.
    """
    del active_teams, metric
    _render_live_games_tab()


def _render_overview_players(
    processed_dfs: list,
    players: dict,
    peak_info: dict,
    metric: str,
    stat_category: str,
    season_type: str,
    selected_season: str | int = "All",
    do_cumul: bool = False,
) -> None:
    """Overview tab: existing right-column player comparison cards."""
    is_goalie = stat_category == "Goalie"
    season_mode = _is_selected_season_mode(selected_season)
    use_last_visible_total = season_mode and do_cumul
    player_colors = _get_player_chart_colors()
    season_rank_map = (
        get_player_season_rank_map(stat_category, int(selected_season), season_type, metric)
        if season_mode
        else {}
    )
    rank_suffix_map = {"Goals": "Goals", "Assists": "Assists", "Points": "Points"}
    rank_suffix = "Wins" if is_goalie else rank_suffix_map.get(metric, "Points")

    for pid, name, proc_df in _iter_visible_players_for_category(processed_dfs, players):
        real = proc_df[~proc_df["Player"].str.contains(r"\(Proj\)", na=False)]
        sort_cols = [col for col in ["CumGP", "Age", "SeasonYear"] if col in real.columns]
        if sort_cols:
            real = real.sort_values(sort_cols).reset_index(drop=True)

        hero_url = get_player_hero_image(int(pid))
        team_abbr = get_player_current_team(int(pid))
        logo_html = (
            f"<img src='{_TEAM_LOGO_URL.format(abbr=team_abbr)}' "
            f"height='18' style='vertical-align:middle;margin-left:6px;opacity:0.9;'>"
            if team_abbr
            else ""
        )

        career_gp = _get_visible_stat_total(real, "GP", use_last_visible_total)
        if is_goalie:
            career_w = _get_visible_stat_total(real, "Wins", use_last_visible_total)
            career_so = _get_visible_stat_total(real, "Shutouts", use_last_visible_total)
            career_sv = _get_visible_stat_total(real, "Saves", use_last_visible_total)
            stats_row = (
                f"W:&nbsp;{career_w} &nbsp;|&nbsp; "
                f"SO:&nbsp;{career_so} &nbsp;|&nbsp; "
                f"SV:&nbsp;{career_sv:,} &nbsp;|&nbsp; "
                f"GP:&nbsp;{career_gp}"
            )
        else:
            career_g = _get_visible_stat_total(real, "Goals", use_last_visible_total)
            career_a = _get_visible_stat_total(real, "Assists", use_last_visible_total)
            career_pt = _get_visible_stat_total(real, "Points", use_last_visible_total)
            stats_row = (
                f"G:&nbsp;{career_g} &nbsp;|&nbsp; "
                f"A:&nbsp;{career_a} &nbsp;|&nbsp; "
                f"Pts:&nbsp;{career_pt} &nbsp;|&nbsp; "
                f"GP:&nbsp;{career_gp}"
            )

        scope_row = ""
        if season_mode:
            scope_color = player_colors.get(name) or _DEFAULT_PLAYER_RANK_COLOR
            season_rank = season_rank_map.get(int(pid))
            season_label = (
                _build_selected_season_rank_label(selected_season, season_type, metric, season_rank)
                if season_rank is not None
                else _build_selected_season_scope_label(selected_season, season_type)
            )
            scope_row = (
                f"<br><span style='font-size:14px;color:{scope_color};font-weight:bold;'>"
                f"{season_label}"
                "</span>"
            )

        rank_row = ""
        if not season_mode:
            rank = get_player_career_rank(int(pid), stat_category, season_type, metric)
            if rank is not None:
                rank_color = player_colors.get(name) or _DEFAULT_PLAYER_RANK_COLOR
                rank_row = (
                    f"<br><span style='font-size:14px;color:{rank_color};font-weight:bold;'>"
                    f"#{rank} all-time {rank_suffix}"
                    "</span>"
                )

        peak = peak_info.get(name)
        best_row = ""
        if peak:
            metric_short_map = {"Points": "Pts", "Goals": "G", "Assists": "A"}
            metric_short = metric_short_map.get(metric, metric)
            if season_mode:
                peak_game = peak.get("game_number") or peak.get("x") or "?"
                peak_date = peak.get("game_date")
                peak_value = peak.get("raw_peak_val", peak.get("y"))
                peak_date_str = f" ({peak_date})" if peak_date else ""
                best_row = (
                    "<br><span style='font-size:14px;color:#999;font-weight:bold;'>"
                    f"Best game:&nbsp;#{peak_game}{peak_date_str}"
                    f" -- {_format_peak_metric_value(metric, peak_value)}&nbsp;{metric_short}"
                    "</span>"
                )
            else:
                age = peak.get("age", "?")
                sy = peak.get("season_year")
                val = peak.get("y")
                peak_row_df = real[real["Age"] == age]
                peak_gp = (
                    int(peak_row_df["GP"].iloc[0])
                    if not peak_row_df.empty and "GP" in peak_row_df.columns
                    else "?"
                )
                sy_str = f"{sy - 1}-{str(sy)[2:]}" if sy else "?"
                best_row = (
                    "<br><span style='font-size:14px;color:#999;font-weight:bold;'>"
                    f"Best: Age&nbsp;{age} ({sy_str})"
                    f" -- {_format_peak_metric_value(metric, val)}&nbsp;{metric_short} in {peak_gp}&nbsp;GP"
                    "</span>"
                )

        with st.container():
            img_col, stat_col = st.columns([1, 2], gap="small")
            with img_col:
                if hero_url:
                    st.image(hero_url, use_container_width=True)

            with stat_col:
                roster_info = get_player_roster_info(int(pid))
                if roster_info:
                    pos = roster_info["position"]
                    num = roster_info["sweater_number"]
                    name_html = (
                        f"<span style='color:#aaa;font-size:13px;'>[{pos}]</span> "
                        f"<strong>{name}</strong> "
                        f"<span style='color:#aaa;font-size:13px;'>#{num}</span>"
                    )
                else:
                    name_html = f"<strong>{name}</strong>"

                st.markdown(
                    "<div style='line-height:1.4;margin:0;padding:0;'>"
                    f"{name_html}{logo_html}<br>"
                    f"{stats_row}"
                    f"{scope_row}"
                    f"{rank_row}"
                    f"{best_row}"
                    "</div>",
                    unsafe_allow_html=True,
                )

        st.markdown(
            "<hr style='margin:6px 0;border:none;border-top:1px solid #2a2a2a;'>",
            unsafe_allow_html=True,
        )


def _render_overview_teams(active_teams: dict, metric: str) -> None:
    """Overview tab: existing right-column team comparison cards."""
    team_stats = get_team_all_time_stats()

    for abbr, full_name in active_teams.items():
        stats = team_stats.get(abbr)
        if not stats:
            continue

        founded = TEAM_FOUNDED.get(abbr, "")
        logo_url = _TEAM_LOGO_URL.format(abbr=abbr)
        total_w = stats["total_wins"]
        total_pts = stats["total_points"]
        total_gf = stats["total_goals"]
        total_gp = stats["total_gp"]
        wins_rank = stats["wins_rank"]
        best_year = stats["best_year"]
        best_wins = stats["best_wins"]
        best_gp = stats["best_gp"]

        name_html = (
            f"<strong>{full_name}</strong> "
            f"<span style='color:#aaa;font-size:13px;'>{founded}</span>"
        )
        stats_row = (
            f"W:&nbsp;{total_w:,} &nbsp;|&nbsp; "
            f"Pts:&nbsp;{total_pts:,} &nbsp;|&nbsp; "
            f"GF:&nbsp;{total_gf:,} &nbsp;|&nbsp; "
            f"GP:&nbsp;{total_gp:,}"
        )
        rank_row = (
            "<br><span style='font-size:14px;color:#4caf50;font-weight:bold;'>"
            f"#{wins_rank} all-time Wins"
            "</span>"
        )
        best_row = ""
        if best_year and best_wins is not None:
            sy_str = f"{best_year - 1}-{str(best_year)[2:]}"
            best_row = (
                "<br><span style='font-size:14px;color:#999;font-weight:bold;'>"
                f"Best: {sy_str} -- {best_wins}&nbsp;W in {best_gp}&nbsp;GP"
                "</span>"
            )

        with st.container():
            st.markdown(
                "<div style='display:flex;align-items:flex-start;gap:14px;margin:4px 0;'>"
                f"<img src='{logo_url}' style='width:80px;flex-shrink:0;object-fit:contain;'>"
                "<div style='line-height:1.4;'>"
                f"{name_html}<br>"
                f"{stats_row}"
                f"{rank_row}"
                f"{best_row}"
                "</div>"
                "</div>",
                unsafe_allow_html=True,
            )

        st.markdown(
            "<hr style='margin:6px 0;border:none;border-top:1px solid #2a2a2a;'>",
            unsafe_allow_html=True,
        )


def _summarize_player_awards(awards: list[dict]) -> list[dict]:
    """Aggregate raw landing-page awards list by trophy name."""
    summary: dict[str, dict] = {}
    for award in awards:
        if not isinstance(award, dict):
            continue
        trophy_field = award.get("trophy")
        if isinstance(trophy_field, dict):
            trophy_name = trophy_field.get("default") or trophy_field.get("fr")
        else:
            trophy_name = str(trophy_field or "").strip()
        if not trophy_name:
            continue

        seasons = award.get("seasons")
        if not isinstance(seasons, list):
            seasons = []
        season_ids: list[int] = []
        for season in seasons:
            if not isinstance(season, dict):
                continue
            sid = season.get("seasonId")
            if sid is None:
                continue
            try:
                season_ids.append(int(sid))
            except Exception:
                continue

        wins_here = len(season_ids) if season_ids else 1
        item = summary.setdefault(trophy_name, {"count": 0, "latest": None})
        item["count"] += wins_here
        if season_ids:
            latest = max(season_ids)
            if item["latest"] is None or latest > item["latest"]:
                item["latest"] = latest

    rows = [
        {"trophy": trophy, "count": data["count"], "latest": data["latest"]}
        for trophy, data in summary.items()
    ]
    rows.sort(key=lambda x: (-x["count"], -(x["latest"] or 0), x["trophy"]))
    return rows


def _render_trophies_players(
    processed_dfs: list,
    players: dict,
    peak_info: dict,
    metric: str,
    stat_category: str,
    season_type: str,
    selected_season: str | int = "All",
    do_cumul: bool = False,
) -> None:
    """Trophies tab for skater/goalie categories."""
    del peak_info, metric, stat_category, season_type, selected_season, do_cumul

    for pid, name, _ in _iter_visible_players_for_category(processed_dfs, players):
        hero_url = get_player_hero_image(int(pid))
        team_abbr = get_player_current_team(int(pid))
        logo_html = (
            f"<img src='{_TEAM_LOGO_URL.format(abbr=team_abbr)}' "
            f"height='18' style='vertical-align:middle;margin-left:6px;opacity:0.9;'>"
            if team_abbr
            else ""
        )

        roster_info = get_player_roster_info(int(pid))
        if roster_info:
            pos = roster_info["position"]
            num = roster_info["sweater_number"]
            name_html = (
                f"<span style='color:#aaa;font-size:13px;'>[{pos}]</span> "
                f"<strong>{name}</strong> "
                f"<span style='color:#aaa;font-size:13px;'>#{num}</span>"
            )
        else:
            name_html = f"<strong>{name}</strong>"

        awards = get_player_awards(int(pid))
        award_rows = _summarize_player_awards(awards)

        lines: list[str] = []
        for row in award_rows[:8]:
            latest = row["latest"]
            latest_str = (
                f" (latest { _season_span_label_from_id(latest) })"
                if latest is not None
                else ""
            )
            lines.append(
                f"<span style='font-size:14px;color:#ddd;'>"
                f"{row['trophy']}: <strong>x{row['count']}</strong>{latest_str}"
                f"</span>"
            )
        if not lines:
            lines.append(
                "<span style='font-size:14px;color:#999;font-weight:bold;'>"
                "No trophy data available."
                "</span>"
            )

        lines_html = "<br>".join(lines)
        with st.container():
            img_col, stat_col = st.columns([1, 2], gap="small")
            with img_col:
                if hero_url:
                    st.image(hero_url, use_container_width=True)
            with stat_col:
                st.markdown(
                    "<div style='line-height:1.5;margin:0;padding:0;'>"
                    f"{name_html}{logo_html}<br>"
                    f"{lines_html}"
                    "</div>",
                    unsafe_allow_html=True,
                )
        st.markdown(
            "<hr style='margin:6px 0;border:none;border-top:1px solid #2a2a2a;'>",
            unsafe_allow_html=True,
        )


def _render_trophies_teams(active_teams: dict, metric: str) -> None:
    """Trophies tab for team category (v1: Stanley Cups)."""
    del metric
    trophy_summary = get_team_trophy_summary()

    for abbr, full_name in active_teams.items():
        founded = TEAM_FOUNDED.get(abbr, "")
        logo_url = _TEAM_LOGO_URL.format(abbr=abbr)
        team_trophies = trophy_summary.get(abbr, {})
        cup_count = team_trophies.get("stanley_cups")
        latest_cup = team_trophies.get("latest_cup_season")

        if cup_count is None:
            cups_row = (
                "<span style='font-size:14px;color:#999;font-weight:bold;'>"
                "No trophy data available."
                "</span>"
            )
        else:
            latest_str = ""
            if int(cup_count) > 0 and latest_cup is not None:
                latest_str = f" (latest { _season_span_label_from_id(latest_cup) })"
            cups_row = (
                "<span style='font-size:16px;color:#f0c04a;font-weight:bold;'>"
                f"Stanley Cups: {int(cup_count)}{latest_str}"
                "</span>"
            )

        with st.container():
            st.markdown(
                "<div style='display:flex;align-items:flex-start;gap:14px;margin:4px 0;'>"
                f"<img src='{logo_url}' style='width:80px;flex-shrink:0;object-fit:contain;'>"
                "<div style='line-height:1.5;'>"
                f"<strong>{full_name}</strong> "
                f"<span style='color:#aaa;font-size:13px;'>{founded}</span><br>"
                f"{cups_row}"
                "</div>"
                "</div>",
                unsafe_allow_html=True,
            )
        st.markdown(
            "<hr style='margin:6px 0;border:none;border-top:1px solid #2a2a2a;'>",
            unsafe_allow_html=True,
        )


_PANEL_TABS = (
    PanelTabSpec(
        id="overview",
        label="Overview",
        render_player=_render_overview_players,
        render_team=_render_overview_teams,
    ),
    PanelTabSpec(
        id="trophies",
        label="Trophies",
        render_player=_render_trophies_players,
        render_team=_render_trophies_teams,
    ),
    PanelTabSpec(
        id="live_games",
        label="Live games",
        render_player=_render_live_games_players,
        render_team=_render_live_games_teams,
    ),
)


def render_comparison_panel(
    processed_dfs: list,
    players: dict,
    peak_info: dict,
    metric: str,
    stat_category: str,
    season_type: str,
) -> None:
    """Render the legacy player overview panel without tabs."""
    _render_overview_players(
        processed_dfs=processed_dfs,
        players=players,
        peak_info=peak_info,
        metric=metric,
        stat_category=stat_category,
        season_type=season_type,
        selected_season="All",
        do_cumul=False,
    )


def render_team_comparison_panel(active_teams: dict, metric: str) -> None:
    """Render legacy Overview-only team comparison cards.

    Args:
        active_teams: Selected comparison teams.
        metric: Active metric name.

    Returns:
        None.
    """
    _render_overview_teams(active_teams=active_teams, metric=metric)
