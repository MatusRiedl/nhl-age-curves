"""Chart click dialogs for season snapshots, projections, and baselines."""

import streamlit as st

from nhl.data_loaders import get_all_time_rank


BASELINE_LABEL_TO_KEY = {
    'Skater 75th Percentile Baseline': 'Skater',
    'Goalie 75th Percentile Baseline': 'Goalie',
}


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

    st.info(
        "Short version: this is a hybrid forecasting system, not a single opaque model."
    )

    st.markdown("#### How baseline works")
    base_skater_col, base_goalie_col = st.columns(2)
    with base_skater_col:
        st.markdown(
            "**Skater baseline**\n\n"
            "A skater-only 75th percentile age curve built from historical player "
            "seasons. It answers: what does a strong skater age track usually look like?"
        )
    with base_goalie_col:
        st.markdown(
            "**Goalie baseline**\n\n"
            "A separate goalie-only 75th percentile curve. Goalie benchmarks are handled "
            "independently because their counting stats and rate stats age differently."
        )

    st.markdown(
        "The baseline is **not ML** and it is **not trying to predict this player**. "
        "It is a historical measuring stick so you can judge how exceptional a curve is."
    )


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
