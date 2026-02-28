"""
nhl.team_pipeline — Per-team data processing pipeline.

Filters, transforms, and prepares team-season DataFrames for Plotly chart rendering.
The team pipeline is intentionally simpler than the player pipeline: no KNN projection,
no era adjustment, no NHLe conversion.

No Streamlit import — all session-state values are passed as plain parameters.

Imports from project:
    nhl.constants — TEAM_RATE_STATS
"""

import pandas as pd

from nhl.constants import TEAM_RATE_STATS


def process_teams(
    teams: dict,
    all_team_df: pd.DataFrame,
    metric: str,
    season_type: str,
    do_cumul: bool,
    do_smooth: bool,
    games_mode: bool,
) -> list:
    """Filter and transform team-season data for chart rendering.

    For each team on the board:
        1. Filter rows to the selected team abbreviation.
        2. Apply season type filter (Regular / Playoffs / Both).
        3. Sort by SeasonYear.
        4. Guard that the metric column exists (PP% absent for old seasons is OK).
        5. Apply cumulative toggle (counting stats only).
        6. Apply 3-season rolling average smoothing.
        7. Compute CumGP column for Games Played mode.

    Args:
        teams:        Dict of {team_abbr: team_name} from session state.
        all_team_df:  Full team-season DataFrame from load_all_team_seasons().
                      Must contain 'teamAbbrev', 'SeasonYear', 'GP', 'gameTypeId' columns.
        metric:       Currently selected stat metric string.
        season_type:  'Regular', 'Playoffs', or 'Both'.
        do_cumul:     Whether cumulative mode is active (already resolved: False for
                      rate stats, False in games_mode).
        do_smooth:    Whether 3-season rolling average is active.
        games_mode:   Whether x-axis is Games Played (not Season Year).

    Returns:
        List of DataFrames, one per team, ready for pd.concat and Plotly rendering.
        Empty list if all_team_df is empty or no teams have data for the given metric.
    """
    processed_dfs = []

    if all_team_df.empty or "teamAbbrev" not in all_team_df.columns:
        return processed_dfs

    for _abbr, _name in teams.items():
        df = all_team_df[all_team_df["teamAbbrev"] == _abbr].copy()
        if df.empty:
            continue

        # Season type filter (gameTypeId 2 = regular, 3 = playoffs)
        if "gameTypeId" in df.columns:
            if season_type == "Regular":
                df = df[df["gameTypeId"] == 2]
            elif season_type == "Playoffs":
                df = df[df["gameTypeId"] == 3]
            # "Both" — keep all rows

        if df.empty:
            continue

        df = df.sort_values("SeasonYear").reset_index(drop=True)

        # Guard: metric column must exist (PP% absent for old seasons is OK — NaN renders as gap)
        if metric not in df.columns:
            continue

        # Cumulative (counting stats only; rate stats excluded via do_cumul=False)
        if do_cumul and metric not in TEAM_RATE_STATS:
            df[metric] = df[metric].cumsum()

        # 3-season rolling average
        if do_smooth:
            df[metric] = df[metric].rolling(window=3, min_periods=1).mean()

        # Games Played x-axis
        if games_mode:
            df["CumGP"] = df["GP"].cumsum()

        df["Player"]   = _name
        df["BaseName"] = _abbr

        _keep_cols = ["SeasonYear", "GP", metric, "Player", "BaseName"]
        if games_mode:
            _keep_cols.append("CumGP")
        processed_dfs.append(df[[c for c in _keep_cols if c in df.columns]])

    return processed_dfs
