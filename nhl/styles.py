"""
nhl.styles — CSS injection and UI asset helpers for the NHL Age Curves page.

Contains the CSS injection helpers plus a small favicon path resolver so app.py
can keep page chrome configuration simple and robust across local and deployed
environments.
"""

from pathlib import Path

import streamlit as st

# ---------------------------------------------------------------------------
# Private CSS block
# ---------------------------------------------------------------------------

_CSS = """
    <style>
        .block-container { padding-top: 2rem !important; padding-bottom: 0rem !important; }

        .page-header {
            display: flex;
            align-items: center;
            flex-wrap: nowrap;
            gap: 0;
            padding-bottom: 0;
            margin-top: 0;
            margin-bottom: 0;
            white-space: nowrap;
        }

        .page-hero {
            margin-bottom: 0 !important;
        }

        .page-subtitle {
            margin: -0.35rem 0 0.2rem 0;
            color: #c0c0c0;
            font-size: 1.02rem;
        }

        div.element-container:has(.page-hero) {
            margin-bottom: 0.45rem !important;
        }

        [data-testid="stExpander"] {
            margin-top: 0 !important;
        }

        .animated-title {
            background: linear-gradient(to right, #c0c0c0, #2b71c7, #ff4b4b, #c0c0c0);
            background-size: 300% auto;
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            animation: sweep 6s linear infinite;
            white-space: nowrap;
        }

        @keyframes sweep {
            to { background-position: 300% center; }
        }

        .nhl-logo {
            height: 45px;
            margin-right: 15px;
            animation: spin-pulse 4s infinite ease-in-out;
        }

        @media (max-width: 768px) {
            .block-container {
                padding-top: 0.75rem !important;
                padding-left: 0.35rem !important;
                padding-right: 0.35rem !important;
            }
            .page-header {
                margin-top: 0 !important;
                margin-bottom: 0 !important;
            }
            .page-subtitle {
                margin-top: -0.2rem;
                margin-bottom: 0.15rem;
                font-size: 0.92rem;
            }
            .page-header .animated-title {
                font-size: 2.15rem !important;
                line-height: 1 !important;
            }
            .nhl-logo {
                height: 28px;
                margin-right: 8px;
            }
        }

        @keyframes spin-pulse {
            0% { transform: rotateY(0deg) scale(1); }
            50% { transform: rotateY(180deg) scale(1.15); }
            100% { transform: rotateY(360deg) scale(1); }
        }

        .stButton button { width: 100%; }

        [data-testid="stSidebar"] .sidebar-support-link {
            display: flex;
            align-items: center;
            justify-content: flex-start;
            gap: 0.65rem;
            width: 100%;
            margin: 0.72rem 0 0.48rem 0;
            padding: 0.58rem 0.82rem;
            border-radius: 999px;
            border: 1px solid rgba(255, 244, 231, 0.16);
            background: linear-gradient(135deg, #9d6535 0%, #bf7a3f 100%);
            color: #ffffff !important;
            text-decoration: none !important;
            box-shadow: 0 6px 14px rgba(88, 49, 24, 0.16);
            transition: transform 0.16s ease, box-shadow 0.16s ease, filter 0.16s ease;
        }

        [data-testid="stSidebar"] .sidebar-support-link:hover {
            transform: translateY(-1px);
            filter: brightness(1.02);
            box-shadow: 0 8px 18px rgba(88, 49, 24, 0.2);
        }

        [data-testid="stSidebar"] .sidebar-support-link:focus,
        [data-testid="stSidebar"] .sidebar-support-link:focus-visible {
            outline: 2px solid rgba(255, 255, 255, 0.8);
            outline-offset: 2px;
        }

        [data-testid="stSidebar"] .sidebar-support-link__emoji {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            flex: 0 0 auto;
            width: 1.65rem;
            height: 1.65rem;
            border-radius: 999px;
            background: rgba(255, 248, 240, 0.18);
            font-size: 0.95rem;
            line-height: 1;
            font-family: "Segoe UI Emoji", "Apple Color Emoji", "Noto Color Emoji", sans-serif;
        }

        [data-testid="stSidebar"] .sidebar-support-link__text {
            display: flex;
            flex-direction: column;
            align-items: flex-start;
            min-width: 0;
        }

        [data-testid="stSidebar"] .sidebar-support-link__label {
            font-weight: 700;
            font-size: 0.9rem;
            line-height: 1.08;
        }

        [data-testid="stSidebar"] .sidebar-support-link__sublabel {
            margin-top: 0.08rem;
            font-size: 0.73rem;
            line-height: 1.12;
            color: rgba(255, 247, 240, 0.86);
        }

        [data-testid="stSidebar"] [data-testid="stHorizontalBlock"] div.stButton button {
            width: auto !important;
            min-width: 0 !important;
            padding: 0.2rem 0.6rem !important;
            float: right;
        }

        /* Remove button styling - transparent background with white X */
        [data-testid="stSidebar"] [data-testid="stHorizontalBlock"] button[kind="secondary"][data-testid="stBaseButton-secondary"] {
            background-color: transparent !important;
            border: none !important;
            color: white !important;
            padding: 0 !important;
            min-width: 24px !important;
            width: 24px !important;
            height: 32px !important;
            font-size: 18px !important;
            line-height: 32px !important;
            margin-left: -8px !important;
            display: flex !important;
            align-items: center !important;
            justify-content: center !important;
        }
        [data-testid="stSidebar"] [data-testid="stHorizontalBlock"] button[kind="secondary"][data-testid="stBaseButton-secondary"]:hover {
            background-color: rgba(255, 255, 255, 0.1) !important;
            color: #ff4b4b !important;
        }

        /* Stretch columns to equal height, then center content within each */
        [data-testid="stSidebar"] [data-testid="stHorizontalBlock"] {
            flex-wrap: nowrap !important;
            align-items: stretch !important;
            gap: 0 !important;
        }

        /* Each column becomes a flex container so its inner block can be centered */
        [data-testid="stSidebar"] [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {
            display: flex !important;
            align-items: center !important;
        }

        /* The inner vertical block — centered, no margin leakage */
        [data-testid="stSidebar"] [data-testid="stHorizontalBlock"] [data-testid="stVerticalBlock"] {
            width: 100% !important;
            justify-content: center !important;
        }

        /* Zero out all margins inside these rows */
        [data-testid="stSidebar"] [data-testid="stHorizontalBlock"] .element-container {
            margin: 0 !important;
            padding: 0 !important;
        }

        /* Tighten sidebar vertical spacing */
        [data-testid="stSidebar"] .stMarkdown hr {
            margin-top: 6px !important;
            margin-bottom: 6px !important;
        }
        [data-testid="stSidebar"] .element-container {
            margin-bottom: 4px !important;
        }
        [data-testid="stSidebar"] h3 {
            margin-top: 4px !important;
            margin-bottom: 4px !important;
        }

        /* Remove gap above Global Search to match Top 50 spacing */
        [data-testid="stSidebar"] .element-container:has(> div > div > label[data-testid="stWidgetLabel"]:nth-child(1)) {
            margin-top: 0 !important;
        }
        /* Target the first text input after the category divider to remove top margin */
        [data-testid="stSidebar"] hr + .element-container .stTextInput label {
            margin-top: 0 !important;
            padding-top: 0 !important;
        }

        /* Normalize the first Team dropdown so it matches Global Search spacing and sizing */
        [data-testid="stSidebar"] hr + .element-container .stSelectbox label {
            margin-top: 0 !important;
            padding-top: 0 !important;
        }
        [data-testid="stSidebar"] hr + .element-container [data-baseweb="select"] > div {
            min-height: 3.25rem !important;
            border-radius: 0.75rem !important;
            padding-left: 0.95rem !important;
            padding-right: 2.75rem !important;
            align-items: center !important;
        }
        [data-testid="stSidebar"] hr + .element-container [data-baseweb="select"] > div > div:first-child {
            padding-left: 0 !important;
            padding-right: 0 !important;
        }
        [data-testid="stSidebar"] hr + .element-container [data-baseweb="select"] * {
            font-size: 15px !important;
            line-height: 1.3 !important;
        }
        [data-testid="stSidebar"] hr + .element-container [data-baseweb="select"] svg {
            width: 18px !important;
            height: 18px !important;
        }

        /* Compact header and controls expander — reduce vertical whitespace */
        [data-testid="stExpander"] details summary {
            padding-top: 0.4rem !important;
            padding-bottom: 0.4rem !important;
        }
        [data-testid="stExpander"] details > div {
            padding-top: 0.25rem !important;
            padding-bottom: 0.25rem !important;
        }
        [data-testid="stExpander"] .element-container {
            margin-bottom: 0 !important;
        }
        [data-testid="stExpander"] [data-testid="stHorizontalBlock"] {
            gap: 0.5rem !important;
            row-gap: 0.25rem !important;
        }
        [data-testid="stExpander"] .stRadio > label {
            margin-bottom: 0.1rem !important;
        }
        [data-testid="stExpander"] [data-testid="stToggle"] {
            margin-bottom: 0 !important;
        }
        [data-testid="stExpander"] [data-testid="stVerticalBlock"] {
            gap: 0.25rem !important;
        }

        /* Controls toolbar: muted unavailable pills */
        .controls-toolbar-muted {
            display: flex;
            flex-wrap: wrap;
            align-items: center;
            gap: 0.35rem;
            margin: 0.25rem 0 0.1rem 0;
        }
        .controls-toolbar-muted__label {
            color: #7f8aa3;
            font-size: 0.76rem;
            font-weight: 600;
        }
        .controls-pill {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            min-height: 1.8rem;
            padding: 0.12rem 0.62rem;
            border-radius: 999px;
            font-size: 0.76rem;
            font-weight: 600;
            line-height: 1;
            white-space: nowrap;
        }
        .controls-pill--disabled {
            border: 1px solid rgba(148, 163, 184, 0.2);
            background: rgba(30, 41, 59, 0.45);
            color: #7f8aa3;
        }

        .player-name {
            font-size: 15px;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
            line-height: 32px !important;
        }

        /* Center the markdown wrapper itself */
        [data-testid="stSidebar"] [data-testid="stHorizontalBlock"] [data-testid="stMarkdown"] {
            display: flex !important;
            align-items: center !important;
            margin: 0 !important;
        }

        /* Center the button wrapper */
        [data-testid="stSidebar"] [data-testid="stHorizontalBlock"] [data-testid="stButton"],
        [data-testid="stSidebar"] [data-testid="stHorizontalBlock"] .stButton {
            display: flex !important;
            align-items: center !important;
            justify-content: flex-end !important;
            margin: 0 !important;
        }

        div.element-container:has(.blue-btn-anchor) + div.element-container button {
            background-color: #2b71c7 !important;
            border-color: #2b71c7 !important;
            color: white !important;
        }
        div.element-container:has(.blue-btn-anchor) + div.element-container button:hover {
            background-color: #1a569d !important;
            border-color: #1a569d !important;
        }

        div.element-container:has(.faq-btn-anchor) + div.element-container button {
            background: rgba(43, 113, 199, 0.16) !important;
            border: 1px solid rgba(103, 168, 255, 0.28) !important;
            color: rgba(230, 241, 255, 0.95) !important;
            box-shadow: inset 0 0 0 1px rgba(43, 113, 199, 0.05) !important;
        }
        div.element-container:has(.faq-btn-anchor) + div.element-container button:hover {
            background: rgba(43, 113, 199, 0.24) !important;
            border-color: rgba(124, 184, 255, 0.4) !important;
            color: #ffffff !important;
        }

        div.element-container:has(.live-games-matchup),
        div.element-container:has(.live-games-detail) {
            margin-bottom: 0 !important;
        }
        .live-games-detail {
            color: #8c8c8c;
            font-size: 0.95rem;
            line-height: 1.2;
            margin: 0.1rem 0 0.3rem 0;
        }
        div.element-container:has(.live-games-detail) + div.element-container {
            margin-top: 0 !important;
            margin-bottom: 0 !important;
        }
        div.element-container:has(.live-games-detail) + div.element-container [data-testid="stButton"] {
            margin-top: 0 !important;
            margin-bottom: 0.1rem !important;
        }
        div.element-container:has(.live-games-detail) + div.element-container [data-testid="stButton"] button {
            padding: 0.18rem 0.7rem !important;
            font-size: 0.92rem !important;
            min-height: 2.3rem !important;
            width: auto !important;
            max-width: 100% !important;
            white-space: normal !important;
            overflow-wrap: anywhere !important;
        }
        div.element-container:has(.live-games-detail) + div + div.element-container {
            margin-top: 0 !important;
            margin-bottom: 0 !important;
        }
        div.element-container:has(.live-games-detail) + div + div.element-container hr {
            margin: 0 !important;
        }

        /* Controls dropdowns: stack one per row on mobile */
        @media (max-width: 768px) {
            div:has(> #controls-dropdowns) + div [data-testid="stHorizontalBlock"] {
                flex-wrap: wrap !important;
            }
            div:has(> #controls-dropdowns) + div [data-testid="column"] {
                min-width: 100% !important;
                flex: 1 1 100% !important;
            }
        }

        /* Main chart toolbar */
        .nhl-chart-toolbar {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 0.75rem;
            min-height: 40px !important;
            margin: 0 0 0.4rem 0;
        }
        .nhl-chart-toolbar__title {
            color: rgba(255, 255, 255, 0.90);
            font-size: 1rem;
            font-weight: 400;
            line-height: 1.2;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }
        .nhl-chart-share-btn {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            gap: 0.4rem;
            padding: 0.35rem 0.7rem;
            border: 1px solid rgba(148, 163, 184, 0.24);
            border-radius: 999px;
            background: rgba(15, 23, 42, 0.72);
            color: #dbe4f0;
            font-size: 0.8rem;
            font-weight: 600;
            line-height: 1;
            cursor: pointer;
            transition: border-color 0.18s ease, color 0.18s ease, background 0.18s ease;
        }
        .nhl-chart-share-btn:hover {
            color: #ffffff;
            border-color: rgba(255, 255, 255, 0.28);
            background: rgba(30, 41, 59, 0.88);
        }
        .nhl-chart-share-btn.is-copied {
            color: #4ade80;
            border-color: rgba(74, 222, 128, 0.45);
        }
        .nhl-chart-share-btn svg {
            width: 15px;
            height: 15px;
            display: block;
        }
        @media (max-width: 900px) {
            .nhl-chart-toolbar {
                gap: 0.5rem;
            }
            .nhl-chart-toolbar__title {
                font-size: 0.92rem;
            }
            .nhl-chart-share-btn {
                padding: 0.32rem 0.62rem;
                font-size: 0.76rem;
            }
        }
        @media (max-width: 768px) {
            .nhl-chart-toolbar {
                gap: 0.4rem;
                min-height: 32px !important;
                margin: 0 0 0.2rem 0;
            }
            .nhl-chart-toolbar__title {
                font-size: 0.84rem;
                line-height: 1.15;
            }
            .nhl-chart-share-btn {
                gap: 0.28rem;
                padding: 0.24rem 0.52rem;
                font-size: 0.7rem;
            }
            .nhl-chart-share-btn svg {
                width: 13px;
                height: 13px;
            }
        }

        /* Comparison panel cards */
        .comparison-card {
            padding: 0.5rem 0.25rem;
        }
        .comparison-card b {
            font-size: 18px;
        }
        .comparison-card small {
            color: #aaa;
            font-size: 12px;
        }

        /* Chart season selector moved into the comparison panel */
        div:has(> #comparison-season-filter) {
            margin: 0 !important;
            line-height: 0 !important;
        }
        div:has(> #comparison-season-filter) + div {
            margin-top: -0.55rem !important;
            margin-bottom: 0.2rem !important;
        }
        div:has(> #comparison-season-filter) + div .stSelectbox label {
            margin-top: 0 !important;
            padding-top: 0 !important;
        }

        /* Comparison tab row (native st.tabs) */
        div:has(> #comparison-tabs) + div [data-testid="stTabs"] {
            margin-top: -0.6rem !important;
            padding-top: 0 !important;
        }
        div:has(> #comparison-tabs) + div [data-testid="stTabs"] [data-baseweb="tab-list"] {
            gap: 0.35rem !important;
            flex-wrap: wrap !important;
            margin-bottom: 0.4rem !important;
            min-height: 40px !important;
            align-items: center !important;
            padding-top: 0 !important;
        }
        div:has(> #comparison-tabs) + div [data-testid="stTabs"] [data-baseweb="tab-border"] {
            display: none !important;
        }
        div:has(> #comparison-tabs) + div [data-testid="stTabs"] button[role="tab"] {
            margin: 0 !important;
            border: 1px solid #2a2a2a !important;
            border-radius: 999px !important;
            background: rgba(17, 24, 39, 0.7) !important;
            padding: 4px 10px !important;
            min-height: 0 !important;
            height: auto !important;
        }
        div:has(> #comparison-tabs) + div [data-testid="stTabs"] button[role="tab"] p {
            margin: 0 !important;
            font-size: 13px !important;
            font-weight: 600 !important;
            color: #d9d9d9 !important;
        }
        div:has(> #comparison-tabs) + div [data-testid="stTabs"] button[role="tab"][aria-selected="true"] {
            border-color: #ff4b4b !important;
            background: rgba(255, 75, 75, 0.14) !important;
        }
        div:has(> #comparison-tabs) + div [data-testid="stTabs"] [data-baseweb="tab-panel"] {
            padding-top: 0.1rem !important;
        }
        @media (max-width: 768px) {
            div:has(> #comparison-tabs) + div [data-testid="stTabs"] button[role="tab"] {
                padding: 3px 8px !important;
            }
        }

        /* Main content split — controls + chart on the left, comparison panel on the right */
        div:has(> #main-chart-layout) {
            margin: 0 !important;
            line-height: 0 !important;
        }
        div:has(> #main-chart-layout) + div {
            margin-top: -0.45rem !important;
        }
        div:has(> #main-chart-layout) + div [data-testid="stHorizontalBlock"] {
            align-items: flex-start !important;
        }
        @media screen and (max-width: 1280px) {
            div:has(> #main-chart-layout) + div [data-testid="stHorizontalBlock"] {
                flex-wrap: wrap !important;
            }
            div:has(> #main-chart-layout) + div [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {
                min-width: 100% !important;
                width: 100% !important;
                flex: 1 1 100% !important;
            }
        }

        /* Responsive: stack chart and stats panel vertically on mobile */
        @media screen and (max-width: 768px) {
            .main [data-testid="stHorizontalBlock"] {
                flex-wrap: wrap !important;
            }
            .main [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {
                min-width: 100% !important;
                width: 100% !important;
            }
        }

        /* Plotly modebar — always visible, fit on one row */
        .js-plotly-plot .plotly .modebar {
            opacity: 1 !important;
            top: 8px !important;
            right: 8px !important;
            left: auto !important;
            background: transparent !important;
            border: none !important;
            border-radius: 0 !important;
            box-shadow: none !important;
            padding: 0 !important;
        }
        .js-plotly-plot .plotly .modebar-btn::before,
        .js-plotly-plot .plotly .modebar-btn::after {
            display: none !important;
            content: none !important;
        }
        .js-plotly-plot .plotly .modebar-group {
            flex-wrap: nowrap !important;
            overflow-x: auto !important;
            padding: 0 !important;
        }
        .js-plotly-plot .plotly .modebar-btn {
            padding: 6px 8px !important;
        }
        .js-plotly-plot .plotly .modebar-btn svg {
            width: 18px !important;
            height: 18px !important;
        }
        @media (max-width: 768px) {
            .js-plotly-plot .plotly .modebar {
                top: 4px !important;
                right: 4px !important;
            }
            .js-plotly-plot .plotly .modebar-btn {
                padding: 3px 5px !important;
            }
            .js-plotly-plot .plotly .modebar-btn svg {
                width: 14px !important;
                height: 14px !important;
            }
        }

        /* ── Sidebar toggle: always visible ────────────────────────────── */
        [data-testid="stSidebarCollapseButton"] button,
        [data-testid="collapsedControl"] {
            opacity: 1 !important;
            visibility: visible !important;
        }
        [data-testid="stSidebarCollapseButton"] button,
        [data-testid="collapsedControl"] button {
            min-width: 36px;
            min-height: 36px;
        }

        /* ── Custom animated progress bar for cache spinners ───────────── */
        /* Hide the default "Running function_name()" text */
        [data-testid="stSpinner"] .stMarkdown p {
            display: none !important;
        }
        /* Replace with animated progress bar */
        [data-testid="stSpinner"] {
            position: relative !important;
            width: 100% !important;
            max-width: 400px !important;
            margin: 1rem auto !important;
        }
        [data-testid="stSpinner"]::before {
            content: '';
            display: block;
            width: 100%;
            height: 4px;
            background: linear-gradient(90deg,
                #2b71c7 0%,
                #ff4b4b 50%,
                #2b71c7 100%);
            background-size: 200% 100%;
            border-radius: 2px;
            animation: progress-sweep 2s ease-in-out infinite;
        }
        [data-testid="stSpinner"]::after {
            content: 'Loading data...';
            display: block;
            text-align: center;
            font-size: 14px;
            color: #888;
            margin-top: 8px;
        }
        @keyframes progress-sweep {
            0% { background-position: 200% 0; }
            100% { background-position: -200% 0; }
        }
        /* Keep the spinner icon itself hidden since we have our own animation */
        [data-testid="stSpinner"] > div:first-child {
            display: none !important;
        }
    </style>
"""
"""Full CSS block injected into the Streamlit page head."""


# ---------------------------------------------------------------------------
# Public function
# ---------------------------------------------------------------------------

def get_favicon_path() -> Path:
    """Return the absolute path to the custom site favicon asset.

    Args:
        None.

    Returns:
        Path: Absolute path to the favicon SVG file in the repository assets folder.
    """
    return Path(__file__).resolve().parent.parent / "assets" / "favicon.svg"


def inject_css() -> None:
    """Inject the NHL Age Curves custom CSS into the Streamlit page.

    Covers: animated gradient title, spinning NHL logo, sidebar compact layout,
    blue Add-Legend button override, compact controls toolbar styling,
    compact mobile header sizing,
    a real chart toolbar row with copy-link button, responsive stacking of the
    chart/stats panel split on laptop and mobile widths, and Plotly modebar sizing.

    Must be called once per app run, after st.set_page_config().
    """
    st.markdown(_CSS, unsafe_allow_html=True)


def inject_mobile_dropdown_fix() -> None:
    """Inject the CSS-only mobile dropdown fix after page config is set."""
    mobile_css = """
    <style>
        /* Disable search input in dropdowns on touch devices (mobile/tablet)
           to prevent on-screen keyboard from opening when tapping dropdowns */
        @media (pointer: coarse) {
            /* Target the input inside Streamlit selectbox/multiselect dropdowns */
            div[data-baseweb="select"] input,
            div[data-baseweb="popover"] input,
            div[data-baseweb="select"] [role="combobox"] input {
                pointer-events: none !important;
                caret-color: transparent !important;
                -webkit-user-select: none !important;
                user-select: none !important;
            }

            /* Ensure the dropdown container remains fully clickable */
            div[data-baseweb="select"] {
                cursor: pointer !important;
            }
        }

        /* Additional targeting for iOS Safari and older mobile browsers */
        @media (hover: none) and (pointer: coarse) {
            [role="combobox"] input,
            [role="listbox"] input {
                pointer-events: none !important;
                caret-color: transparent !important;
            }
        }
    </style>
    """
    st.markdown(mobile_css, unsafe_allow_html=True)
