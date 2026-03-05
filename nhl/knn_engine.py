"""nhl.knn_engine — KNN ML projection engine for NHL player age curves.

Projects a player's future stat trajectory by finding the 10 most similar
historical players using L1 distance across shared career ages, then mapping
clone movement forward with equal-weight averages and a fixed prior blend.

Key design decisions:
    - L1 distance (Manhattan), not L2.
    - Partial career matching: requires >= max(2, len(ages)//3) shared ages.
    - Tier pre-filter: clones must have a career peak >= 50% of the live player's
      peak to prevent elite players matching against journeymen.
    - Top-10 clone influence is equal-weighted.
    - Clone/prior blending uses a fixed 70/30 split.
    - pct_change clamp: [-0.12, +0.25].
    - GP excluded from KNN. GP uses the 4-phase durability curve in
      player_pipeline.py instead.

No Streamlit import — this module is pure pandas math and is independently
testable without mocking any Streamlit state.

Imports from project:
    nhl.constants — RATE_STATS, ML_SUPPORTED_METRICS, STAT_CAPS, STAT_FLOORS,
                    CURRENT_SEASON_YEAR
    nhl.era       — apply_era_to_hist
"""

import pandas as pd

from nhl.constants import (
    CURRENT_SEASON_YEAR,
    ML_SUPPORTED_METRICS,
    RATE_STATS,
    STAT_CAPS,
    STAT_FLOORS,
)
from nhl.era import apply_era_to_hist


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _apply_stat_cap(val: float, metric: str, stat_category: str) -> float:
    """Apply the stat cap (and optional floor) for a single projected value.

    GAA is treated as a floor rather than a ceiling — no goalie projects below
    1.8 GAA long-term.  The GP cap is lowered to 65 for goalies.

    Args:
        val:           The current projected value.
        metric:        Stat column name.
        stat_category: 'Skater' or 'Goalie'.

    Returns:
        Value after applying caps and floors.
    """
    if metric in STAT_CAPS:
        cap = STAT_CAPS[metric]
        if metric == "GP" and stat_category == "Goalie":
            cap = 65
        val = max(val, cap) if metric == "GAA" else min(val, cap)
    if metric in STAT_FLOORS:
        val = max(val, STAT_FLOORS[metric])
    return val


def _build_clone_names(
    top_ids,
    clone_details_map: dict,
    id_to_name_map: dict,
    stat_category: str,
) -> list:
    """Build the clone detail list for the projection dialog popup.

    Args:
        top_ids:           Index of the 10 nearest-neighbour player IDs.
        clone_details_map: {playerId: stats_dict} from data_loaders.
        id_to_name_map:    {playerId: name} from data_loaders.
        stat_category:     'Skater' or 'Goalie'.

    Returns:
        List of clone dicts, each containing at minimum: name, team.
        Skater dicts also have: gp, pts, g, a, pm.
        Goalie dicts also have: gp, w, sv, so.
    """
    clone_names = []
    for c_id in top_ids:
        detail = clone_details_map.get(int(c_id))
        if detail:
            clone_names.append(detail.copy())
        else:
            c_name = id_to_name_map.get(int(c_id), f"Unknown (ID {c_id})")
            if stat_category == "Skater":
                clone_names.append(
                    {'name': c_name, 'team': '—', 'gp': 0, 'pts': 0, 'g': 0, 'a': 0, 'pm': 0}
                )
            else:
                clone_names.append(
                    {'name': c_name, 'team': '—', 'gp': 0, 'w': 0, 'sv': 0, 'so': 0}
                )
    return clone_names


def _estimate_sparse_future_target(
    last_avg: float,
    metric: str,
    age: int,
    stat_category: str,
) -> float:
    """Estimate a non-zero fallback target when clone data is exhausted.

    Args:
        last_avg: Previous season's clone average proxy.
        metric: Stat column being projected.
        age: Future age currently being projected.
        stat_category: 'Skater' or 'Goalie'.

    Returns:
        A gentle late-career continuation target in the same scale as the metric.
    """
    if metric == 'Save %':
        return last_avg - (0.15 if age <= 37 else 0.20 if age <= 39 else 0.25)
    if metric == 'GAA':
        return last_avg * (1.03 if stat_category == 'Goalie' else 1.01)
    if metric == '+/-':
        return last_avg - 2
    if metric in RATE_STATS:
        return last_avg * (0.97 if age <= 37 else 0.95)
    return last_avg * (0.96 if age <= 37 else 0.94 if age <= 39 else 0.92)


def _stabilize_late_target(
    next_avg: float,
    last_avg: float,
    metric: str,
    age: int,
    stat_category: str,
    clone_count: int,
) -> float:
    """Dampen sparse or upward late-career targets before applying deltas.

    Args:
        next_avg: Candidate clone average for the future age.
        last_avg: Previous season's clone average proxy.
        metric: Stat column being projected.
        age: Future age currently being projected.
        stat_category: 'Skater' or 'Goalie'.
        clone_count: Number of clone rows contributing at this future age.

    Returns:
        Stabilized target that avoids artificial age-36+ rebounds and flat floors.
    """
    if age < 36 or pd.isna(last_avg):
        return next_avg

    sparse_fallback = _estimate_sparse_future_target(last_avg, metric, age, stat_category)

    if metric == 'Save %':
        if clone_count < 3 or next_avg > last_avg:
            return min(next_avg, sparse_fallback)
        return next_avg

    if metric in ['GAA', '+/-']:
        return next_avg

    if next_avg > last_avg:
        return sparse_fallback

    if clone_count < 3:
        return next_avg * 0.35 + sparse_fallback * 0.65

    return next_avg


# ---------------------------------------------------------------------------
# Public functions
# ---------------------------------------------------------------------------

def run_knn_projection(
    career_df: pd.DataFrame,
    metric: str,
    hist_df: pd.DataFrame,
    is_goalie: bool,
    pos_code: str,
    do_era: bool,
    season_type: str,
    stat_category: str,
    id_to_name_map: dict,
    clone_details_map: dict,
) -> tuple:
    """Run KNN age-curve projection for a single player.

    Finds 10 historical clones using L1 distance on shared career ages, then
    projects future seasons with equal-weight clone averages, a fixed 70/30
    blend against the prior target, and a pct_change clamp of [-0.12, +0.25].

    Args:
        career_df:         Pre-processed player career DataFrame (Age, metric columns).
        metric:            Stat column name to project (must be in ML_SUPPORTED_METRICS).
        hist_df:           Raw historical parquet DataFrame.
        is_goalie:         True if the player is a goalie.
        pos_code:          Raw position code from the NHL API (for strict position filter).
        do_era:            Whether era adjustment is currently active.
        season_type:       'Regular', 'Playoffs', or 'Both' (mid-season pacing guard).
        stat_category:     'Skater' or 'Goalie'.
        id_to_name_map:    {playerId: name} for fallback clone display names.
        clone_details_map: {playerId: stats_dict} for clone career stat display.

    Returns:
        Tuple of (proj_rows, clone_names):
            proj_rows: List of dicts with Age, metric, Player, BaseName keys.
            clone_names: List of clone detail dicts for the dialog popup.
    """
    max_age       = career_df['Age'].max()
    base_name     = career_df['BaseName'].iloc[0] if 'BaseName' in career_df.columns else ''
    career_paced  = career_df[metric].copy()

    # Mid-season pacing: extrapolate the last (current) season to 82 GP
    if (season_type != "Playoffs"
            and len(career_df) > 0
            and career_df.iloc[-1]['SeasonYear'] >= CURRENT_SEASON_YEAR
            and career_df.iloc[-1]['GP'] < 82
            and career_df.iloc[-1]['GP'] > 0):
        pace = 82.0 / career_df.iloc[-1]['GP']
        if metric in ['Points', 'Goals', 'Assists', 'Wins', 'Shutouts', 'Saves', '+/-', 'PIM']:
            career_paced.iloc[-1] *= pace

    match_ages  = career_df['Age'].tolist()
    match_vals  = career_paced.tolist()
    current_val = float(career_df.loc[career_df['Age'] == max_age, metric].values[0])

    if hist_df.empty or metric not in ML_SUPPORTED_METRICS:
        return [], []

    # Era-adjust hist_df to match the live player's adjustment state
    knn_hist = apply_era_to_hist(hist_df, do_era, is_goalie=is_goalie)

    # Strict position filtering — fall back to category-level if < 10 players
    h_df = knn_hist[knn_hist['Position'] == pos_code]
    if len(h_df['PlayerID'].unique()) < 10:
        cat  = 'G' if stat_category == 'Goalie' else 'S'
        h_df = (
            knn_hist[knn_hist['Position'] == cat]
            if cat == 'G'
            else knn_hist[knn_hist['Position'] != 'G']
        )

    # FIX #1: Use mean for rate stats, sum for counting stats
    agg_fn = 'mean' if metric in RATE_STATS else 'sum'
    pivot  = h_df.pivot_table(index='PlayerID', columns='Age', values=metric, aggfunc=agg_fn)

    # Guard against young players whose ages don't exist as historical columns
    valid_ages = [a for a in match_ages if a in pivot.columns]
    if not valid_ages:
        return [], []

    # Partial career matching: require at least 1/3 of valid ages (min 2)
    min_shared  = max(2, len(valid_ages) // 3)
    valid_hist  = pivot[pivot[valid_ages].notna().sum(axis=1) >= min_shared]
    valid_match_vals = [v for a, v in zip(match_ages, match_vals) if a in valid_ages]

    if len(valid_hist) == 0:
        return [], []

    # Tier pre-filter: clones must have career peak >= 50% of live player's peak
    current_peak = max(match_vals) if match_vals else 0
    if current_peak > 0 and metric not in RATE_STATS and metric not in ['+/-', 'GP']:
        hist_peaks = valid_hist.max(axis=1)
        for tier_pct in [0.50, 0.30, 0.15]:
            tier_mask = hist_peaks >= current_peak * tier_pct
            if tier_mask.sum() >= 10:
                valid_hist = valid_hist[tier_mask]
                break

    # Vectorized L1 distance across all shared career ages
    # sum(axis=1) uses skipna=True — NaN ages simply ignored
    dist     = valid_hist[valid_ages].sub(valid_match_vals).abs().sum(axis=1)
    # Normalize by number of shared ages to avoid penalizing clones with more data
    n_shared = valid_hist[valid_ages].notna().sum(axis=1).clip(lower=1)
    dist     = dist / n_shared

    top_ids        = dist.nsmallest(10).index
    clone_names    = _build_clone_names(top_ids, clone_details_map, id_to_name_map, stat_category)

    last_avg = (
        valid_hist.loc[top_ids, valid_ages[-1]].dropna().mean()
        if valid_ages[-1] in valid_hist.columns
        else current_val
    )
    if pd.isna(last_avg) or last_avg == 0:
        last_avg = current_val if current_val != 0 else 1.0

    # FIX #5: Pre-build position lookup dict — O(1) per clone instead of full mask scan
    # (unused in projection math but kept for potential diagnostic use)
    # pos_lookup = h_df.drop_duplicates('PlayerID').set_index('PlayerID')['Position'].to_dict()

    # Ring-buffer of last 3 clone averages for trend extrapolation when clones run out
    recent_clone_avgs = []
    proj_rows = []

    for age in range(int(max_age) + 1, 41):
        clone_count = 0
        if age in pivot.columns:
            clone_vals = pivot.loc[top_ids, age].dropna()
            clone_count = len(clone_vals)
            if clone_count > 0:
                raw_avg = float(clone_vals.astype(float).mean())
                next_avg = raw_avg * 0.70 + last_avg * 0.30
                recent_clone_avgs.append(next_avg)
                if len(recent_clone_avgs) > 3:
                    recent_clone_avgs.pop(0)
            elif len(recent_clone_avgs) >= 2:
                # No clone data — extrapolate the % change from the last known averages.
                # GAA increases (worsens) with age so allow positive pct_per_step;
                # all other metrics decline, so cap at 0.0 to prevent artificial growth.
                if metric == 'Save %':
                    add_step = (recent_clone_avgs[-1] - recent_clone_avgs[0]) / max(
                        1, len(recent_clone_avgs) - 1
                    )
                    add_step = max(-0.7, min(0.2, add_step))
                    next_avg = recent_clone_avgs[-1] + add_step
                else:
                    pct_per_step  = (recent_clone_avgs[-1] / max(recent_clone_avgs[0], 1e-6)) - 1
                    pct_per_step /= max(1, len(recent_clone_avgs) - 1)
                    if metric == 'GAA':
                        pct_per_step = max(-0.08, min(0.08, pct_per_step))
                    else:
                        pct_per_step = max(-0.08, min(0.0, pct_per_step))
                    next_avg      = recent_clone_avgs[-1] * (1 + pct_per_step)
                recent_clone_avgs.append(next_avg)
                if len(recent_clone_avgs) > 3:
                    recent_clone_avgs.pop(0)
            elif len(recent_clone_avgs) == 1:
                next_avg = (
                    recent_clone_avgs[0] - 0.3
                    if metric == 'Save %'
                    else recent_clone_avgs[0] * 0.92
                )
                recent_clone_avgs.append(next_avg)
            else:
                next_avg = _estimate_sparse_future_target(last_avg, metric, age, stat_category)
        else:
            next_avg = _estimate_sparse_future_target(last_avg, metric, age, stat_category)

        if pd.isna(next_avg):
            next_avg = _estimate_sparse_future_target(last_avg, metric, age, stat_category)

        next_avg = _stabilize_late_target(
            next_avg=next_avg,
            last_avg=last_avg,
            metric=metric,
            age=age,
            stat_category=stat_category,
            clone_count=clone_count,
        )

        # Update current_val via delta or pct_change
        if metric == 'Save %':
            delta = next_avg - last_avg
            delta = max(-1.2, min(0.6, delta))
            current_val += delta
        elif metric in ['+/-', 'GAA']:
            current_val += (next_avg - last_avg)
        else:
            if last_avg > 0:
                pct_change = (next_avg - last_avg) / last_avg
                # Clamp: max 12% annual decline, max 25% growth
                pct_change  = max(min(pct_change, 0.25), -0.12)
                current_val += current_val * pct_change
            else:
                current_val += (next_avg - last_avg)

        if metric != "+/-":
            current_val = max(0, current_val)

        current_val = _apply_stat_cap(current_val, metric, stat_category)

        proj_rows.append({
            "Age":      age,
            metric:     current_val,
            "Player":   base_name,
            "BaseName": base_name,
        })
        last_avg = next_avg

    return proj_rows, clone_names


def run_linear_fallback(
    career_df: pd.DataFrame,
    metric: str,
    max_age: int,
    stat_category: str,
) -> list:
    """Project future ages using a simple linear or rule-based fallback.

    Used when KNN is unavailable (hist_df empty, metric not in ML_SUPPORTED_METRICS,
    or not enough valid historical players found).

    GP uses a 4-phase durability curve based on real long-career NHL reference data
    (Jagr ~68 GP at 40, Lidstrom ~73 GP at 40, Thornton ~60 GP at 39).

    Args:
        career_df:     Pre-processed player career DataFrame (Age, metric columns).
        metric:        Stat column name to project.
        max_age:       Last real-data age; projection starts at max_age + 1.
        stat_category: 'Skater' or 'Goalie'.

    Returns:
        List of dicts with Age, metric, Player, BaseName keys.
    """
    base_name   = career_df['BaseName'].iloc[0] if 'BaseName' in career_df.columns else ''
    match_vals  = career_df[metric].tolist()
    current_val = float(career_df.loc[career_df['Age'] == max_age, metric].values[0])
    slope = (
        (match_vals[-1] - match_vals[0]) / max(1, len(career_df) - 1)
        if len(career_df) >= 2
        else match_vals[-1] * 0.05
    )

    proj_rows = []
    for age in range(int(max_age) + 1, 41):
        if metric == "GP":
            gp_cap = 82 if stat_category == "Skater" else 65
            # 4-phase durability curve
            if age <= 28:
                current_val = min(gp_cap, current_val + 0.8)    # soft growth to prime
            elif age <= 33:
                current_val = min(gp_cap, current_val * 0.990)  # ~1%/yr — prime plateau
            elif age <= 37:
                current_val *= 0.965                             # ~3.5%/yr — gradual decline
            else:
                current_val *= 0.930                             # ~7%/yr — late career
        elif age <= 26:
            if age == int(max_age) + 1 and slope > 0:
                current_val = (current_val + (match_vals[-1] + slope)) / 2
            elif slope > 0:
                current_val += slope * (0.4 ** (age - max_age))
            else:
                current_val += current_val * 0.03
        else:
            if "GAA" in metric:
                current_val *= 1.05
            elif metric == "Save %":
                current_val -= 0.005
            elif "PIM" in metric:
                current_val *= 0.90
            elif metric in ["TOI", "SH%", "Saves"]:
                current_val *= 0.95
            elif metric == "+/-":
                current_val -= 2
            else:
                if age <= 28:
                    current_val *= 0.98
                elif age <= 31:
                    current_val *= 0.92
                elif age <= 35:
                    current_val *= 0.85
                else:
                    current_val *= 0.80

        current_val = _apply_stat_cap(current_val, metric, stat_category)
        if metric != "+/-":
            current_val = max(0, current_val)

        proj_rows.append({
            "Age":      age,
            metric:     current_val,
            "Player":   base_name,
            "BaseName": base_name,
        })

    return proj_rows
