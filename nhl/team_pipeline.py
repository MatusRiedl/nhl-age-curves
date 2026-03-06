"""Per-team processing pipeline for chart-ready season or games-played curves."""

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
    """Filter, aggregate, and format selected team seasons for the chart."""
    processed_dfs = []

    if all_team_df.empty or "teamAbbrev" not in all_team_df.columns:
        return processed_dfs

    def _weighted_avg(grp: pd.DataFrame, col: str) -> float:
        """Compute GP-weighted mean for a column; NaN if unavailable."""
        if col not in grp.columns or "GP" not in grp.columns:
            return float("nan")
        valid = grp[[col, "GP"]].dropna()
        if valid.empty:
            return float("nan")
        total_w = float(valid["GP"].sum())
        if total_w <= 0:
            return float(valid[col].mean())
        return float((valid[col] * valid["GP"]).sum() / total_w)

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
            # "Both" keeps both rows here; they are collapsed below.

        if df.empty:
            continue

        if season_type == "Both":
            rows = []
            for _sy, _grp in df.groupby("SeasonYear", sort=True):
                gp = int(round(_grp["GP"].sum())) if "GP" in _grp.columns else 0
                wins = int(round(_grp["Wins"].sum())) if "Wins" in _grp.columns else float("nan")
                points = int(round(_grp["Points"].sum())) if "Points" in _grp.columns else float("nan")
                goals = int(round(_grp["Goals"].sum())) if "Goals" in _grp.columns else float("nan")

                win_pct = (points / (gp * 2.0) * 100.0) if gp > 0 and pd.notna(points) else _weighted_avg(_grp, "Win%")
                gf_g = (goals / gp) if gp > 0 and pd.notna(goals) else _weighted_avg(_grp, "GF/G")
                # goals-against count is not stored in the compact team table, so use GP-weighted GA/G.
                ga_g = _weighted_avg(_grp, "GA/G")
                ppg = ((goals / gp) * 2.7) if gp > 0 and pd.notna(goals) else _weighted_avg(_grp, "PPG")
                pp_pct = _weighted_avg(_grp, "PP%")

                rows.append(
                    {
                        "SeasonYear": _sy,
                        "GP": gp,
                        "Wins": wins,
                        "Points": points,
                        "Goals": goals,
                        "Win%": win_pct,
                        "GF/G": gf_g,
                        "GA/G": ga_g,
                        "PPG": ppg,
                        "PP%": pp_pct,
                    }
                )

            df = pd.DataFrame(rows)
            if df.empty:
                continue

            # Match precision conventions used in loader output.
            for _c in ("Win%", "PP%"):
                if _c in df.columns:
                    df[_c] = df[_c].round(1)
            for _c in ("GF/G", "GA/G", "PPG"):
                if _c in df.columns:
                    df[_c] = df[_c].round(3)

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
