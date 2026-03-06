"""Chart click dialogs for season snapshots, projections, baselines, and help."""

import streamlit as st

from nhl.data_loaders import get_all_time_rank
from nhl.era import get_era_multiplier


BASELINE_LABEL_TO_KEY = {
    'Skater 75th Percentile Baseline': 'Skater',
    'Goalie 75th Percentile Baseline': 'Goalie',
}

_ERA_EXPLAINER_BANDS: tuple[tuple[str, int], ...] = (
    ("<= 1967", 1967),
    ("1968-79", 1975),
    ("1980-92", 1985),
    ("1993-96", 1995),
    ("1997-2004", 2001),
    ("2005-12", 2010),
    ("2013-17", 2015),
    ("2018+", 2022),
)


def _render_projection_guide_tab() -> None:
    """Render the projection explainer content.

    Args:
        None.

    Returns:
        None.
    """
    st.markdown("#### Basics")
    st.markdown(
        "- **Solid line:** real performance already logged.\n"
        "- **Dotted line:** projected continuation of the current career path.\n"
        "- **Dashed line:** strong historical benchmark, not a player-specific forecast."
    )

    st.markdown("#### How projection works")
    proj_skater_col, proj_goalie_col = st.columns(2)
    with proj_skater_col:
        st.markdown(
            "**Skaters**\n\n"
            "Compared only against historical skaters with similar early and mid-career "
            "shapes, then extended using how those comparable careers aged."
        )
    with proj_goalie_col:
        st.markdown(
            "**Goalies**\n\n"
            "Compared only against historical goalies. Their projection rules stay "
            "separate because goalie aging and volatility behave differently."
        )

    ml_col, rules_col = st.columns(2)
    with ml_col:
        st.markdown(
            "**What is ML-ish**\n\n"
            "The nearest-match layer. The app uses historical similarity to find the "
            "closest career paths and borrow aging behavior from them."
        )
    with rules_col:
        st.markdown(
            "**What is not ML**\n\n"
            "The guardrails. Caps, smoothing, presentation logic, and late-career "
            "stability rules are deliberate system design, not black-box learning."
        )


def _render_baseline_guide_tab() -> None:
    """Render the baseline explainer content.

    Args:
        None.

    Returns:
        None.
    """
    st.markdown(
        "The dashed baseline line is your historical benchmark. It is there so you can see "
        "whether a player is tracking below, around, or above a strong historical standard."
    )

    base_skater_col, base_goalie_col = st.columns(2)
    with base_skater_col:
        st.markdown(
            "**Skater baseline**\n\n"
            "A skater-only 75th percentile age curve built from historical player seasons. "
            "Think of it as: what does a really strong skater age track usually look like?"
        )
    with base_goalie_col:
        st.markdown(
            "**Goalie baseline**\n\n"
            "A separate goalie-only 75th percentile curve. Goalies get their own baseline "
            "because goalie stats age differently from skater stats."
        )

    st.markdown("#### How to read it")
    st.markdown(
        "- above the baseline usually means an exceptional track for that age\n"
        "- around the baseline means the player is in strong company\n"
        "- below the baseline does not mean bad — just below that specific historical bar"
    )


def _render_era_adjust_skaters_guide_tab() -> None:
    """Render the skater era-adjustment explainer content.

    Args:
        None.

    Returns:
        None.
    """
    st.markdown(
        "Era adjust normalizes NHL scoring to a modern baseline so cross-era comparisons "
        "stop cheating. It fixes the obvious problem: a raw point total from the 80s and "
        "a raw point total from the dead-puck era are not the same accomplishment."
    )

    st.markdown("#### What changes")
    st.markdown(
        "- **Raw stats:** the original season totals for **Goals**, **Assists**, and **Points**.\n"
        "- **Era-adjusted stats:** those same NHL totals after the app applies the era multiplier."
    )

    example_80s_col, example_dead_puck_col = st.columns(2)
    with example_80s_col:
        st.markdown(
            "**Example: 1985 skater**\n\n"
            "The 80s were offense-heavy, so the app deflates raw scoring from that environment."
        )
    with example_dead_puck_col:
        st.markdown(
            "**Example: 2001 skater**\n\n"
            "Dead-puck seasons were tougher for offense, so the app boosts scoring from that environment."
        )

    st.markdown("#### Multipliers used")
    st.markdown(
        "\n".join(
            f"- **{label}:** `{get_era_multiplier(sample_year):.2f}`"
            for label, sample_year in _ERA_EXPLAINER_BANDS
        )
    )

    st.markdown("#### Why it changed")
    st.markdown(
        "- High-scoring eras get **deflated** because offense was easier to rack up.\n"
        "- Low-scoring eras get **boosted** because offense was harder to produce.\n"
        "- That gives you a fairer apples-to-apples curve when players come from different generations."
    )


def _render_era_adjust_goalies_guide_tab() -> None:
    """Render the goalie era-adjustment explainer content.

    Args:
        None.

    Returns:
        None.
    """
    st.markdown(
        "Goalie era adjust uses separate logic because goalie stats are not the same beast as skater scoring. "
        "The app tries to move goalie seasons into a modern context without pretending Save %, GAA, and Shutouts all behave the same way."
    )

    st.markdown("#### What changes")
    st.markdown(
        "- **Save %:** shifted toward the modern 2018+ environment while keeping how far above or below league average the goalie was.\n"
        "- **GAA:** scaled by the era multiplier so goals-against sits in the same modern scoring context.\n"
        "- **Shutouts:** moved the opposite way, because shutouts were harder to pile up in high-scoring eras."
    )

    goalie_sv_col, goalie_misc_col = st.columns(2)
    with goalie_sv_col:
        st.markdown(
            "**Save % logic**\n\n"
            "This is not the skater method. The app compares a goalie's Save % to that era's league average, then shifts it toward the modern baseline."
        )
    with goalie_misc_col:
        st.markdown(
            "**GAA + Shutouts logic**\n\n"
            "GAA gets scaled into the modern scoring environment, while Shutouts move inversely so old high-scoring eras do not get unfairly punished."
        )

def _render_smoothing_guide_tab() -> None:
    """Render the smoothing explainer content.

    Args:
        None.

    Returns:
        None.
    """
    st.markdown(
        "Smoothing is a display aid. It makes the visible curve easier to read without pretending "
        "the raw season-to-season noise is the real story."
    )

    smooth_math_col, smooth_visual_col = st.columns(2)
    with smooth_math_col:
        st.markdown(
            "**What the app does**\n\n"
            "When **Smooth** is on, the selected metric becomes a **3-season rolling average**. "
            "At the start of a career it uses whatever history exists, so the early points still render cleanly."
        )
    with smooth_visual_col:
        st.markdown(
            "**Why it looks calmer**\n\n"
            "The chart also switches to a curved line shape, so the trend reads more like a career arc "
            "and less like a seismograph having a bad day."
        )

    st.markdown("#### What smoothing helps with")
    st.markdown(
        "- softens one-year spikes and dips\n"
        "- makes long careers easier to scan\n"
        "- visually reduces harsh jumps between neighboring seasons"
    )


@st.dialog("How This App Works")
def show_app_guide() -> None:
    """Show a concise methodology guide without exposing the full recipe.

    Args:
        None.

    Returns:
        None.
    """
    st.markdown(
        "This app turns NHL careers into age curves so you can compare real results, "
        "historical baselines, and a forward-looking projection in one place."
    )

    projection_tab, baseline_tab, era_adjust_skaters_tab, era_adjust_goalies_tab, smoothing_tab = st.tabs(["Projection", "Baseline", "Era adjust skaters", "Era adjust goalies", "Smoothing"])
    with projection_tab:
        _render_projection_guide_tab()
    with baseline_tab:
        _render_baseline_guide_tab()
    with era_adjust_skaters_tab:
        _render_era_adjust_skaters_guide_tab()
    with era_adjust_goalies_tab:
        _render_era_adjust_goalies_guide_tab()
    with smoothing_tab:
        _render_smoothing_guide_tab()


@st.dialog("Season Snapshot")
def show_season_details(
    player_name: str,
    age: int,
    raw_dfs_list: list,
    metric: str,
    val: float,
    is_cumul: bool,
    full_df,
    s_type: str,
    ml_clones_dict: dict,
    historical_baselines: dict,
    stat_category: str,
) -> None:
    """Render the correct click dialog for a real point, projection, or baseline."""
    age = int(age)
    clean_name    = player_name.replace(" (Proj)", "")
    baseline_key  = BASELINE_LABEL_TO_KEY.get(clean_name)
    is_baseline   = baseline_key is not None
    is_projection = "(Proj)" in player_name
    is_real       = not is_baseline and not is_projection

    st.markdown(f"### {player_name} at Age {age}")

    # ── CASE 3: BASELINE LINE CLICK ────────────────────────────────────
    if is_baseline:
        base_df = historical_baselines.get(baseline_key)
        if base_df is not None and not base_df.empty and age in base_df.index:
            if stat_category == "Skater":
                b_gp  = int(round(base_df.loc[age, 'GP']))    if 'GP'      in base_df.columns else 0
                b_pts = int(round(base_df.loc[age, 'Points'])) if 'Points'  in base_df.columns else 0
                b_g   = int(round(base_df.loc[age, 'Goals']))  if 'Goals'   in base_df.columns else 0
                b_a   = int(round(base_df.loc[age, 'Assists']))if 'Assists' in base_df.columns else 0
                b_pm  = int(round(base_df.loc[age, '+/-']))   if '+/-'     in base_df.columns else 0
                st.markdown(
                    f"<div style='background-color:#2b2b2b;border-left:4px solid rgba(255,255,255,0.4);"
                    f"padding:10px 14px;border-radius:4px;margin-bottom:8px;'>"
                    f"<b>75th Percentile at Age {age}:</b> {b_gp} GP | {b_pts} Pts | "
                    f"{b_g} G | {b_a} A | {b_pm} +/-</div>",
                    unsafe_allow_html=True,
                )
            else:
                b_gp = int(round(base_df.loc[age, 'GP']))       if 'GP'       in base_df.columns else 0
                b_w  = int(round(base_df.loc[age, 'Wins']))     if 'Wins'     in base_df.columns else 0
                b_sv = int(round(base_df.loc[age, 'Saves']))    if 'Saves'    in base_df.columns else 0
                b_so = int(round(base_df.loc[age, 'Shutouts'])) if 'Shutouts' in base_df.columns else 0
                st.markdown(
                    f"<div style='background-color:#2b2b2b;border-left:4px solid rgba(255,255,255,0.4);"
                    f"padding:10px 14px;border-radius:4px;margin-bottom:8px;'>"
                    f"<b>75th Percentile at Age {age}:</b> {b_gp} GP | {b_w} W | "
                    f"{b_sv} Saves | {b_so} SO</div>",
                    unsafe_allow_html=True,
                )
        else:
            st.write("No baseline data available for this age.")
        return  # No further content for baseline clicks

    # ── SHARED: Career Totals (blue) — shown for both real & projection ─
    for df in raw_dfs_list:
        if not df.empty and 'BaseName' in df.columns and df['BaseName'].iloc[0] == clean_name:
            display_df_career = df[df['GameType'] == s_type] if s_type != "Both" else df
            career_gp         = int(display_df_career['GP'].sum())
            label             = "Reg+Playoffs" if s_type == "Both" else s_type
            if stat_category == "Skater":
                career_pts = int(display_df_career['Points'].sum())
                career_g   = int(display_df_career['Goals'].sum())
                career_a   = int(display_df_career['Assists'].sum())
                career_pm  = int(display_df_career['+/-'].sum())
                st.info(
                    f"**Career Totals ({label}):** {career_gp} GP | {career_pts} Pts | "
                    f"{career_g} G | {career_a} A | {career_pm} +/-"
                )
            else:
                career_w  = int(display_df_career['Wins'].sum())
                career_so = int(display_df_career['Shutouts'].sum())
                career_sv = int(display_df_career['Saves'].sum())
                st.info(
                    f"**Career Totals ({label}):** {career_gp} GP | {career_w} W | "
                    f"{career_sv} Saves | {career_so} SO"
                )
            break

    # ── CASE 1: REAL DATA LINE CLICK ───────────────────────────────────
    if is_real:
        # Career subtotals up to clicked age (orange)
        for df in raw_dfs_list:
            if not df.empty and 'BaseName' in df.columns and df['BaseName'].iloc[0] == clean_name:
                sub_df = df[df['Age'] <= age]
                if s_type != "Both":
                    sub_df = sub_df[sub_df['GameType'] == s_type]
                if not sub_df.empty:
                    s_gp = int(sub_df['GP'].sum())
                    if stat_category == "Skater":
                        s_pts = int(sub_df['Points'].sum())
                        s_g   = int(sub_df['Goals'].sum())
                        s_a   = int(sub_df['Assists'].sum())
                        s_pm  = int(sub_df['+/-'].sum())
                        st.warning(
                            f"**Career Subtotals (to Age {age}):** {s_gp} GP | "
                            f"{s_pts} Pts | {s_g} G | {s_a} A | {s_pm} +/-"
                        )
                    else:
                        s_w  = int(sub_df['Wins'].sum())
                        s_so = int(sub_df['Shutouts'].sum())
                        s_sv = int(sub_df['Saves'].sum())
                        st.warning(
                            f"**Career Subtotals (to Age {age}):** {s_gp} GP | "
                            f"{s_w} W | {s_sv} Saves | {s_so} SO"
                        )
                break

        # Season detail table
        for df in raw_dfs_list:
            if not df.empty and 'BaseName' in df.columns and df['BaseName'].iloc[0] == clean_name:
                season_data = df[df['Age'] == age]
                if s_type != "Both":
                    season_data = season_data[season_data['GameType'] == s_type]
                if not season_data.empty:
                    cols_to_show = (
                        ['SeasonYear', 'GameType', 'GP', 'Points', 'Goals', 'Assists', '+/-']
                        if stat_category == "Skater"
                        else ['SeasonYear', 'GameType', 'GP', 'Wins', 'Saves', 'Shutouts']
                    )
                    display_df = season_data[cols_to_show].copy()
                    for col in display_df.columns:
                        if col not in ['SeasonYear', 'GameType']:
                            display_df[col] = display_df[col].astype(int)
                    st.dataframe(display_df, hide_index=True, use_container_width=True)
                break
        return  # End of real data click

    # ── CASE 2: PROJECTION LINE CLICK ──────────────────────────────────
    if is_projection:
        counting_stats = [
            'Points', 'Goals', 'Assists', 'Wins', 'Shutouts', 'GP', 'PIM', 'Saves', '+/-'
        ]

        # Projected career totals up to clicked age
        player_data = full_df[full_df['BaseName'] == clean_name]
        player_data = player_data[player_data['Age'] <= age].drop_duplicates(
            subset=['Age'], keep='last'
        )

        if metric in counting_stats:
            career_total = val if is_cumul else player_data[metric].sum()
            rank = get_all_time_rank(stat_category, s_type, metric, career_total)
            if rank:
                st.success(
                    f"🏆 **At Age {age}:** Estimated **{int(career_total)}** career "
                    f"{metric} → **#{rank} All-Time** in NHL history."
                )

        # ML Projection Clones — single column with team + career stats
        clones = ml_clones_dict.get(clean_name, []) or []
        if clones:
            st.markdown("---")
            st.markdown("**Nearest Historical Matches:**")
            is_skater_mode = stat_category == "Skater"

            if is_skater_mode:
                stat_headers = (
                    "<th style='text-align:right; padding:4px;'>GP</th>"
                    "<th style='text-align:right; padding:4px;'>Pts</th>"
                    "<th style='text-align:right; padding:4px;'>G</th>"
                    "<th style='text-align:right; padding:4px;'>A</th>"
                )
            else:
                stat_headers = (
                    "<th style='text-align:right; padding:4px;'>GP</th>"
                    "<th style='text-align:right; padding:4px;'>W</th>"
                    "<th style='text-align:right; padding:4px;'>Saves</th>"
                    "<th style='text-align:right; padding:4px;'>SO</th>"
                )

            table_html  = "<table style='width:100%; font-size:13px; border-collapse:collapse;'>"
            table_html += (
                "<tr style='border-bottom:1px solid #444;'>"
                f"<th style='text-align:left; padding:4px;'>Player</th>{stat_headers}"
                "</tr>"
            )

            for c in clones:
                tm = f"[{c['team']}] " if c.get('team') and c['team'] != '—' else ""
                table_html += "<tr style='border-bottom:1px solid #333;'>"
                table_html += f"<td style='padding:3px 4px; white-space:nowrap;'>{tm}{c['name']}</td>"
                if is_skater_mode:
                    table_html += (
                        f"<td style='text-align:right; padding:3px 4px;'>{c.get('gp', 0)}</td>"
                        f"<td style='text-align:right; padding:3px 4px;'>{c.get('pts', 0)}</td>"
                        f"<td style='text-align:right; padding:3px 4px;'>{c.get('g', 0)}</td>"
                        f"<td style='text-align:right; padding:3px 4px;'>{c.get('a', 0)}</td>"
                    )
                else:
                    table_html += (
                        f"<td style='text-align:right; padding:3px 4px;'>{c.get('gp', 0)}</td>"
                        f"<td style='text-align:right; padding:3px 4px;'>{c.get('w', 0)}</td>"
                        f"<td style='text-align:right; padding:3px 4px;'>{c.get('sv', 0)}</td>"
                        f"<td style='text-align:right; padding:3px 4px;'>{c.get('so', 0)}</td>"
                    )
                table_html += "</tr>"
            table_html += "</table>"
            st.markdown(table_html, unsafe_allow_html=True)
