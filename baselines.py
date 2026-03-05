"""
nhl.baselines — Historical and team 75th-percentile baseline builders.

Baselines provide a reference curve representing what a typical NHL-quality player
(75th percentile) produces at each age or season.  Both functions are permanently
cached since historical data doesn't change.

The survivorship bias fix is critical: after age 31, only unusually durable players
remain in the dataset, which can push the raw 75th percentile *upward* when it should
decline.  Rule A caps any rise at 0.92x the prior year.  Rule B prevents data-sparsity
cliffs at ages 38-40 by limiting single-year drops to 15%.

Imports from project:
    nhl.constants — TEAM_METRICS
"""

import pandas as pd
import streamlit as st

from nhl.constants import TEAM_METRICS


@st.cache_data
def build_historical_baselines(df: pd.DataFrame) -> dict:
    """Build 75th-percentile age-curve baselines for skaters and goalies.

    Uses role-specific GP thresholds to reduce low-sample noise:
        - Skaters: GP >= 40
        - Goalies: GP >= 20

    Survivorship bias corrections applied column-by-column for ages 32-41:
        Rule A: If baseline rises vs prior year, cap at prior * 0.92.
        Rule B: If baseline drops > 15% vs prior year, cap the drop at 15%.

    A 3-period centered rolling mean is applied first to smooth noisy raw percentiles.

    Late-career slope extrapolation applied after survivorship rules for ages 40-41:
        The centered rolling mean at age 40 incorporates near-empty age-41 data, which
        can pull the smoothed value to near-zero. After the survivorship loop, ages 40
        and 41 are floored at the value implied by continuing the slope from the prior
        two ages (clamped to a max drop of 25% per year).

    Args:
        df: Historical seasons DataFrame from load_historical_data().
            Must contain 'GP', 'Age', and 'Position' columns.

    Returns:
        Dict with keys 'Skater' and 'Goalie', each mapping to a DataFrame
        indexed by Age with stat columns at the 75th percentile.
        Returns {} if df is empty.
    """
    if df.empty:
        return {}

    goalie_df = df[(df['Position'] == 'G') & (df['GP'] >= 20)].copy()
    # Historical scrape artifacts can produce impossible Save% outliers (>100).
    # Clip only goalie Save% before quantiles so one bad row cannot warp the curve.
    if 'Save %' in goalie_df.columns:
        goalie_df['Save %'] = goalie_df['Save %'].clip(lower=80.0, upper=95.0)

    skater_base = (
        df[(df['Position'] != 'G') & (df['GP'] >= 40)]
        .groupby('Age')
        .quantile(0.75, numeric_only=True)
    )
    goalie_base = (
        goalie_df
        .groupby('Age')
        .quantile(0.75, numeric_only=True)
    )

    for base in [skater_base, goalie_base]:
        # Smooth raw percentiles first (3-period centered rolling mean)
        base_smoothed = base.rolling(window=3, min_periods=1, center=True).mean()
        for col in base.columns:
            base[col] = base_smoothed[col]
            # Apply survivorship bias rules for ages 32-41
            for age in range(32, 42):
                if age in base.index and (age - 1) in base.index:
                    prev = base.loc[age - 1, col]
                    curr = base.loc[age, col]
                    if prev <= 0:
                        continue
                    if curr > prev:
                        # Rule A: never let baseline rise after age 31
                        base.loc[age, col] = prev * 0.92
                    elif curr < prev * 0.85:
                        # Rule B: cap single-year drops at 15%
                        base.loc[age, col] = prev * 0.85

            # Slope extrapolation for ages 40-41: continue the decline rate
            # established by the prior two ages rather than accepting the
            # near-zero values produced by the centered rolling mean over
            # sparse late-career data.
            for age in [40, 41]:
                if (
                    age in base.index
                    and (age - 1) in base.index
                    and (age - 2) in base.index
                ):
                    prev = base.loc[age - 1, col]
                    prev2 = base.loc[age - 2, col]
                    if prev2 > 0 and prev > 0:
                        slope = max(min(prev / prev2, 1.0), 0.75)
                        extrapolated = prev * slope
                        if base.loc[age, col] < extrapolated:
                            base.loc[age, col] = extrapolated

    # Smooth abnormal mid-prime hump for goalie Save% (ages 29-31) by bridging
    # between surrounding anchors when the hump is clearly out of family.
    if (
        'Save %' in goalie_base.columns
        and all(a in goalie_base.index for a in (28, 29, 30, 31, 32))
    ):
        a28 = float(goalie_base.loc[28, 'Save %'])
        a32 = float(goalie_base.loc[32, 'Save %'])
        mids = [float(goalie_base.loc[a, 'Save %']) for a in (29, 30, 31)]
        if any(v > max(a28, a32) + 1.5 for v in mids):
            for age in (29, 30, 31):
                t = (age - 28) / 4.0
                goalie_base.loc[age, 'Save %'] = a28 + (a32 - a28) * t

    # Enforce a realistic late-career goalie Save% tail:
    # gradual decline from age 34 to 89.0 by age 40.
    if 'Save %' in goalie_base.columns and all(a in goalie_base.index for a in (34, 40)):
        start = float(goalie_base.loc[34, 'Save %'])
        end = 89.0
        for age in range(34, 41):
            t = (age - 34) / 6.0
            goalie_base.loc[age, 'Save %'] = start + (end - start) * t

    return {'Skater': skater_base, 'Goalie': goalie_base}


@st.cache_data
def build_team_baselines(all_team_df: pd.DataFrame) -> dict:
    """Compute 75th-percentile team baseline per SeasonYear for all TEAM_METRICS.

    Uses regular-season rows only (gameTypeId == 2).  Falls back to all rows if
    the gameTypeId column is absent.

    Args:
        all_team_df: Team-season DataFrame from load_all_team_seasons().

    Returns:
        Dict mapping int season_year to a nested dict of {metric: float_value}.
        Returns {} if all_team_df is empty.
    """
    if all_team_df.empty:
        return {}
    # Filter to regular season; fall back to all rows if column absent
    if "gameTypeId" in all_team_df.columns:
        reg = all_team_df[all_team_df["gameTypeId"] == 2].copy()
    else:
        reg = all_team_df.copy()
    if reg.empty:
        reg = all_team_df.copy()

    result = {}
    for sy, grp in reg.groupby("SeasonYear"):
        entry = {}
        for m in TEAM_METRICS:
            if m in grp.columns:
                vals = grp[m].dropna()
                entry[m] = float(vals.quantile(0.75)) if not vals.empty else None
        result[int(sy)] = entry
    return result
