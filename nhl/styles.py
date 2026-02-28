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

        @media (max-width: 768px) {
            div:has(> #master-toggles) + div [data-testid="stHorizontalBlock"] {
                flex-wrap: nowrap !important;
            }
            div:has(> #master-toggles) + div [data-testid="column"] {
                min-width: 48% !important;
                flex: 1 1 48% !important;
            }
        }

        /* Comparison panel cards */
        .comparison-card {
            padding: 0.5rem 0.25rem;
        }
        .comparison-card b {
            font-size: 15px;
        }
        .comparison-card small {
            color: #aaa;
            font-size: 12px;
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
    blue Add-Legend button override, mobile responsive toggle columns, and
    Plotly modebar sizing for desktop and mobile.

    Must be called once per app run, after st.set_page_config().
    """
    st.markdown(_CSS, unsafe_allow_html=True)
