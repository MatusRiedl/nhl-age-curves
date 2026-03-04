"""
nhl.player_pipeline — Per-player data processing pipeline.

Transforms raw API data for each player on the board through the full processing
chain and returns DataFrames ready for Plotly rendering.

Pipeline order (per player):
    1.  Fetch raw stats (get_player_raw_stats)
    2.  Skater/goalie gatekeeper — skip cross-mode players silently
    3.  League filter + NHLe multiplier application (Points, Goals, Assists only)
    4.  Season type filter (Regular / Playoffs / Both)
    5.  Era adjustment (skaters: Points/Goals/Assists; goalies: GAA/WeightedSV/Shutouts)
    6a. Games Played mode branch — groupby SeasonYear + cumsum all stats
    6b. Age mode branch — groupby Age + compute rate stats
    7.  Origin-anchor zero row (Games Played mode only)
    8.  Peak detection (pre-smoothing, pre-cumsum)
    9.  KNN projection (or linear fallback) if do_predict is True
    10. Cumulative toggle
    11. 3-season rolling average smoothing
    12. Real / projection split

No Streamlit import — all session-state values are passed as plain parameters,
making this module independently testable.

Imports from project:
    nhl.constants      — RATE_STATS, NHLE_MULTIPLIERS, ML_SUPPORTED_METRICS, NO_PROJECTION_METRICS
    nhl.era            — apply_era_to_hist, get_era_multiplier, get_goalie_era_sv_offset
    nhl.data_loaders   — get_player_raw_stats
    nhl.knn_engine     — run_knn_projection, run_linear_fallback
"""

import pandas as pd

from nhl.constants import (
    ML_SUPPORTED_METRICS,
    NHLE_DEFAULT_MULTIPLIER,
    NHLE_MULTIPLIERS,
    NO_PROJECTION_METRICS,
    RATE_STATS,
    normalize_league_abbrev,
)
from nhl.data_loaders import get_player_raw_stats
from nhl.era import apply_era_to_hist, get_era_multiplier, get_goalie_era_sv_offset
from nhl.knn_engine import run_knn_projection, run_linear_fallback


def process_players(
    players: dict,
    metric: str,
    hist_df: pd.DataFrame,
    id_to_name_map: dict,
    clone_details_map: dict,
    season_type: str,
    stat_category: str,
    do_era: bool,
    do_predict: bool,
    do_smooth: bool,
    do_cumul: bool,
    games_mode: bool,
    league_filter: list,
) -> tuple:
    """Process each player through the full data pipeline.

    Args:
        players:           Dict of {playerId: display_name} from session state.
        metric:            Currently selected stat metric string.
        hist_df:           Historical parquet DataFrame for KNN matching.
        id_to_name_map:    {playerId: name} for KNN clone labels.
        clone_details_map: {playerId: stats_dict} for KNN clone dialog table.
        season_type:       'Regular', 'Playoffs', or 'Both'.
        stat_category:     'Skater' or 'Goalie'.
        do_era:            Whether era adjustment is active.
        do_predict:        Whether projection to age 40 is active.
        do_smooth:         Whether 3-season rolling average is active.
        do_cumul:          Whether cumulative toggle is active (already resolved:
                           False for rate stats, False in games_mode).
        games_mode:        Whether x-axis is Games Played (not Age).
        league_filter:     List of league abbreviations to include.

    Returns:
        Tuple of (processed_dfs, raw_dfs_cache, ml_clones_dict, peak_info):
            processed_dfs:   List of DataFrames ready for Plotly chart rendering.
            raw_dfs_cache:   List of raw DataFrames (pre-pipeline) for click dialog.
            ml_clones_dict:  {base_name: [clone_detail_dicts]} for dialog popup.
            peak_info:       {base_name: {x, y, raw_peak_val, age, season_year, pid}}
    """
    processed_dfs  = []
    raw_dfs_cache  = []
    ml_clones_dict = {}
    peak_info      = {}

    _league_filter = [] if league_filter is None else league_filter

    # Era-adjust the historical DataFrame once before the player loop rather than
    # once per player inside knn_engine.py.  apply_era_to_hist returns df unchanged
    # when do_era=False (no copy), so this is free in the era-off case.
    # Guard on do_predict: when projection is off, knn_hist is never consumed.
    knn_hist = (
        apply_era_to_hist(hist_df, do_era, is_goalie=(stat_category == "Goalie"))
        if do_predict
        else hist_df
    )

    for pid, name in players.items():
        raw_df, base_name, pos_code = get_player_raw_stats(pid, name)
        if raw_df.empty:
            continue

        # --- Skater / goalie gatekeeper ---
        is_goalie = raw_df['Saves'].sum() > 0 or raw_df['Wins'].sum() > 0
        if stat_category == "Skater" and is_goalie:
            continue
        if stat_category == "Goalie" and not is_goalie:
            continue

        raw_df['BaseName'] = base_name
        raw_dfs_cache.append(raw_df.copy())

        # --- Step 3: League filter + NHLe conversion ---
        _selected_norm = {
            normalize_league_abbrev(_lg)
            for _lg in _league_filter
            if normalize_league_abbrev(_lg)
        }
        raw_df = raw_df[
            raw_df['League'].apply(normalize_league_abbrev).isin(_selected_norm)
        ].copy()
        if raw_df.empty:
            continue
        # Apply per-row NHLe multipliers to scoring stats only.
        # GP and all non-scoring stats are intentionally kept raw.
        if 'NHLeMultiplier' not in raw_df.columns:
            raw_df['NHLeMultiplier'] = raw_df['League'].apply(
                lambda _lg: NHLE_MULTIPLIERS.get(
                    normalize_league_abbrev(_lg), NHLE_DEFAULT_MULTIPLIER
                )
            )
        _mult = raw_df['NHLeMultiplier'].fillna(NHLE_DEFAULT_MULTIPLIER)
        raw_df['Points'] *= _mult
        raw_df['Goals'] *= _mult
        raw_df['Assists'] *= _mult

        # --- Step 4: Season type filter ---
        if season_type != "Both":
            raw_df = raw_df[raw_df['GameType'] == season_type]
        if raw_df.empty:
            continue

        # --- Step 5: Era adjustment (NHL rows only) ---
        if do_era and stat_category == "Skater":
            # FIX #4: Adjust Goals and Assists independently, not just Points.
            # Era multipliers derived from NHL GF/GP data; apply to NHL rows only
            # so non-NHL rows are not double-adjusted (NHLe already scales them).
            _nhl_mask = raw_df['League'].apply(normalize_league_abbrev) == 'NHL'
            if _nhl_mask.any():
                _era_mults = raw_df.loc[_nhl_mask, 'SeasonYear'].apply(get_era_multiplier)
                raw_df.loc[_nhl_mask, 'Points']  *= _era_mults.values
                raw_df.loc[_nhl_mask, 'Goals']   *= _era_mults.values
                raw_df.loc[_nhl_mask, 'Assists']  *= _era_mults.values

        if do_era and is_goalie:
            # Era-normalize goalie stats to the 2018+ baseline (NHL rows only).
            # Must target WeightedGAA and WeightedSV — the GP-weighted pre-groupby sums —
            # because Save % and GAA don't exist in raw_df until post-groupby.
            # Shutouts adjusted inversely: harder to record in high-scoring eras.
            _nhl_mask = raw_df['League'].apply(normalize_league_abbrev) == 'NHL'
            if _nhl_mask.any():
                _era_mults  = raw_df.loc[_nhl_mask, 'SeasonYear'].apply(get_era_multiplier)
                _sv_offsets = raw_df.loc[_nhl_mask, 'SeasonYear'].apply(get_goalie_era_sv_offset)
                _gp_nhl     = raw_df.loc[_nhl_mask, 'GP']
                raw_df.loc[_nhl_mask, 'WeightedGAA'] = (
                    raw_df.loc[_nhl_mask, 'WeightedGAA'] * _era_mults.values
                ).clip(lower=0)
                raw_df.loc[_nhl_mask, 'WeightedSV'] = (
                    raw_df.loc[_nhl_mask, 'WeightedSV'] + _sv_offsets.values * 100 * _gp_nhl.values
                ).clip(lower=0)
                raw_df.loc[_nhl_mask, 'Shutouts'] = (
                    raw_df.loc[_nhl_mask, 'Shutouts'] / _era_mults.values
                )

        # --- Step 6a: Games Played mode branch ---
        if games_mode:
            # Group by SeasonYear first to collapse Regular+Playoffs into one row
            age_per_season = raw_df.groupby('SeasonYear')['Age'].max()
            df = raw_df.groupby('SeasonYear').sum(numeric_only=True).reset_index()
            df['Age'] = df['SeasonYear'].map(age_per_season)
            df = df.sort_values('SeasonYear').reset_index(drop=True)

            # CumGP is always computed — it is the x-axis column in both sub-modes
            cum_gp = df['GP'].cumsum()
            df['CumGP'] = cum_gp

            if do_cumul:
                # Cumulative sub-branch: overwrite counting stats with career totals
                cum_points   = df['Points'].cumsum()
                cum_goals    = df['Goals'].cumsum()
                cum_assists  = df['Assists'].cumsum()
                cum_wins     = df['Wins'].cumsum()
                cum_shutouts = df['Shutouts'].cumsum()
                cum_pim      = df['PIM'].cumsum()
                cum_saves    = df['Saves'].cumsum()
                cum_pm       = df['+/-'].cumsum()
                cum_toi      = df['TotalTOIMins'].cumsum()
                cum_wsv      = df['WeightedSV'].cumsum()
                cum_wgaa     = df['WeightedGAA'].cumsum()
                cum_shots    = df['Shots'].cumsum()

                df['Points']   = cum_points
                df['Goals']    = cum_goals
                df['Assists']  = cum_assists
                df['Wins']     = cum_wins
                df['Shutouts'] = cum_shutouts
                df['PIM']      = cum_pim
                df['Saves']    = cum_saves
                df['+/-']      = cum_pm
                df['GP']       = cum_gp   # career GP to date

                df['PPG']    = cum_points / cum_gp
                df['TOI']    = cum_toi / cum_gp
                df['SH%']    = (cum_goals / cum_shots.replace(0, float('nan')) * 100).fillna(0)
                df['Save %'] = cum_wsv / cum_gp
                df['GAA']    = cum_wgaa / cum_gp

            else:
                # Per-season sub-branch: keep raw season stats; derive rate stats per season
                season_gp    = df['GP'].copy()   # season GP before any override
                df['PPG']    = df['Points'] / season_gp
                df['TOI']    = df['TotalTOIMins'] / season_gp
                df['SH%']    = (df['Goals'] / df['Shots'].replace(0, float('nan')) * 100).fillna(0)
                df['Save %'] = df['WeightedSV'] / season_gp
                df['GAA']    = df['WeightedGAA'] / season_gp
                # GP stays as season_gp; CumGP is the x-axis

        else:
            # --- Step 6b: Age mode branch ---
            # FIX #2: Preserve SeasonYear as max per age (not sum).
            season_year_max = raw_df.groupby('Age')['SeasonYear'].max()
            df = raw_df.groupby('Age').sum(numeric_only=True).reset_index()
            df['SeasonYear'] = df['Age'].map(season_year_max)

            df['PPG']    = df['Points'] / df['GP']
            df['TOI']    = df['TotalTOIMins'] / df['GP']
            df['SH%']    = (df['Goals'] / df['Shots'] * 100).fillna(0)
            df['Save %'] = df['WeightedSV'] / df['GP']
            df['GAA']    = df['WeightedGAA'] / df['GP']

        df['BaseName'] = base_name
        df['Player']   = base_name

        # --- Step 7: Origin-anchor zero row (Games Played cumulative mode) ---
        if games_mode and do_cumul:
            # Anchor every player's line at career game 0 so all share the same
            # x=0 origin.  Without this, each line starts at end of first season.
            # Not applied in per-season mode — lines naturally start at first season.
            _zero = {col: 0 for col in df.columns}
            _zero.update({
                'CumGP': 0, 'GP': 0,
                'Age':   int(df['Age'].iloc[0]) if not df.empty else 18,
                'Player': base_name, 'BaseName': base_name,
            })
            # Rate stats have no meaningful value at game 0 — leave as NaN
            for _rs in ('PPG', 'TOI', 'SH%', 'Save %', 'GAA'):
                if _rs in _zero:
                    _zero[_rs] = float('nan')
            df = pd.concat([pd.DataFrame([_zero]), df], ignore_index=True)

        # --- Step 8: Peak detection (pre-smoothing, pre-cumsum) ---
        _peak_x = _peak_age = _peak_sy = None
        try:
            if metric in df.columns and not df[metric].dropna().empty:
                if games_mode and do_cumul and metric not in RATE_STATS:
                    # Cumulative data: extract per-season increments for peak detection
                    _incremental = df[metric].diff().fillna(df[metric])
                    _pidx = (
                        _incremental.replace(0, float('nan')).idxmin()
                        if metric == 'GAA'
                        else _incremental.idxmax()
                    )
                else:
                    _series = df[metric].replace(0, float('nan')) if metric == 'GAA' else df[metric]
                    _pidx   = _series.idxmin() if metric == 'GAA' else _series.idxmax()
                if pd.notna(_pidx):
                    _pr      = df.loc[_pidx]
                    _peak_age = int(_pr['Age'])
                    _peak_sy  = int(_pr['SeasonYear']) if 'SeasonYear' in df.columns else None
                    _peak_x   = float(_pr['CumGP']) if games_mode else float(_peak_age)
        except Exception:
            pass

        # --- Step 9: KNN projection or linear fallback ---
        max_age = df['Age'].max()
        if not games_mode and do_predict and not is_goalie and max_age < 40 and metric not in NO_PROJECTION_METRICS:
            career_df = df.copy()
            use_ml    = not hist_df.empty and metric in ML_SUPPORTED_METRICS

            if use_ml:
                proj_rows, clone_names = run_knn_projection(
                    career_df      = career_df,
                    metric         = metric,
                    hist_df        = knn_hist,
                    is_goalie      = is_goalie,
                    pos_code       = pos_code,
                    do_era         = False,
                    season_type    = season_type,
                    stat_category  = stat_category,
                    id_to_name_map = id_to_name_map,
                    clone_details_map = clone_details_map,
                )
                if not proj_rows:
                    use_ml = False
                else:
                    ml_clones_dict[base_name] = clone_names
            if not use_ml:
                proj_rows = run_linear_fallback(
                    career_df  = career_df,
                    metric     = metric,
                    max_age    = int(max_age),
                    stat_category = stat_category,
                )

            if proj_rows:
                df = pd.concat([df, pd.DataFrame(proj_rows)], ignore_index=True)

        # --- Step 10: Cumulative toggle (age mode only) ---
        if do_cumul and not games_mode:
            # games_mode handles cumulation in Step 6a to avoid double-application
            df[metric] = df[metric].cumsum()

        # --- Step 11: 3-season rolling average smoothing ---
        if do_smooth:
            df[metric] = df[metric].rolling(window=3, min_periods=1).mean()

        # --- Step 12: Real / projection split ---
        if not games_mode and do_predict and df['Age'].max() > max_age:
            real_part = df[df['Age'] <= max_age].copy()
            proj_part = df[df['Age'] >= max_age].copy()
            proj_part['Player'] = f"{base_name} (Proj)"
            final_player_df = pd.concat([real_part, proj_part])
        else:
            final_player_df = df.copy()

        # Look up the star's chart y-value at the peak position (post-smoothing/cumsum)
        if _peak_x is not None and _peak_sy is not None:
            x_col_lk  = 'CumGP' if games_mode else 'Age'
            real_only = final_player_df[
                ~final_player_df['Player'].str.contains(r'\(Proj\)', na=False)
            ]
            match = real_only[real_only[x_col_lk] == _peak_x]
            if not match.empty and metric in match.columns:
                raw_pk       = df[df['Age'] == _peak_age][metric]
                raw_peak_val = float(raw_pk.iloc[0]) if not raw_pk.empty else float(match[metric].iloc[0])
                peak_info[base_name] = {
                    'x':            _peak_x,
                    'y':            float(match[metric].iloc[0]),
                    'raw_peak_val': raw_peak_val,
                    'age':          _peak_age,
                    'season_year':  _peak_sy,
                    'pid':          pid,
                }

        processed_dfs.append(final_player_df)

    return processed_dfs, raw_dfs_cache, ml_clones_dict, peak_info
