"""
nhl.styles — CSS injection for the NHL Age Curves Streamlit page.

Contains a single public function, inject_css(), that writes the full style block
into the Streamlit page.  Isolated here so the CSS blob does not clutter app.py
and can be updated without touching any other module.
"""

import streamlit as st

# ---------------------------------------------------------------------------
# Private CSS block
# ---------------------------------------------------------------------------

_CSS = """
    <style>
        .block-container { padding-top: 2rem !important; padding-bottom: 0rem !important; }

        .animated-title {
            background: linear-gradient(to right, #c0c0c0, #2b71c7, #ff4b4b, #c0c0c0);
            background-size: 300% auto;
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            animation: sweep 6s linear infinite;
        }

        @keyframes sweep {
            to { background-position: 300% center; }
        }

        .nhl-logo {
            height: 45px;
            margin-right: 15px;
            animation: spin-pulse 4s infinite ease-in-out;
        }

        @keyframes spin-pulse {
            0% { transform: rotateY(0deg) scale(1); }
            50% { transform: rotateY(180deg) scale(1.15); }
            100% { transform: rotateY(360deg) scale(1); }
        }

        .stButton button { width: 100%; }

        [data-testid="stSidebar"] [data-testid="stHorizontalBlock"] div.stButton button {
            width: auto !important;
            min-width: 0 !important;
            padding: 0.2rem 0.6rem !important;
            float: right;
        }

        [data-testid="stSidebar"] [data-testid="stHorizontalBlock"] {
            flex-wrap: nowrap !important;
            align-items: center !important;
            gap: 0 !important;
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

        /* Compact controls expander — reduce vertical whitespace */
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

        .player-name {
            font-size: 15px;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
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

        /* Controls row1 (category + toggles): wrap ~3 per row on mobile */
        @media (max-width: 768px) {
            div:has(> #controls-row1) + div [data-testid="stHorizontalBlock"] {
                flex-wrap: wrap !important;
            }
            div:has(> #controls-row1) + div [data-testid="column"] {
                min-width: 30% !important;
                flex: 1 1 30% !important;
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
        }
        .js-plotly-plot .plotly .modebar-btn::before,
        .js-plotly-plot .plotly .modebar-btn::after {
            display: none !important;
            content: none !important;
        }
        .js-plotly-plot .plotly .modebar-group {
            flex-wrap: nowrap !important;
            overflow-x: auto !important;
        }
        .js-plotly-plot .plotly .modebar-btn {
            padding: 8px 10px !important;
        }
        .js-plotly-plot .plotly .modebar-btn svg {
            width: 22px !important;
            height: 22px !important;
        }
        @media (max-width: 768px) {
            .js-plotly-plot .plotly .modebar-btn {
                padding: 3px 5px !important;
            }
            .js-plotly-plot .plotly .modebar-btn svg {
                width: 14px !important;
                height: 14px !important;
            }
        }
    </style>
"""
"""Full CSS block injected into the Streamlit page head."""


# ---------------------------------------------------------------------------
# Public function
# ---------------------------------------------------------------------------

def inject_css() -> None:
    """Inject the NHL Age Curves custom CSS into the Streamlit page.

    Covers: animated gradient title, spinning NHL logo, sidebar compact layout,
    blue Add-Legend button override, mobile responsive controls-bottom row wrapping
    (~3 columns per row via #controls-bottom marker),
    responsive stacking of the chart/stats panel split on narrow screens, and
    Plotly modebar sizing for desktop and mobile.

    Must be called once per app run, after st.set_page_config().
    """
    st.markdown(_CSS, unsafe_allow_html=True)
