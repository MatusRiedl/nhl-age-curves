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
        /* Reduce top margin on first text input (Global Search) after divider */
        [data-testid="stSidebar"] hr + .element-container .stTextInput {
            margin-top: -4px !important;
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

        /* Allow controls toggle columns to shrink below content width (enables ellipsis) */
        div:has(> #controls-row1) + div [data-testid="stColumn"] {
            min-width: 0 !important;
            overflow: hidden !important;
        }

        /* Truncate toggle labels on narrow/intermediate screen widths */
        [data-testid="stExpander"] [data-testid="stToggle"] label {
            display: flex !important;
            align-items: center !important;
            overflow: hidden !important;
            max-width: 100% !important;
            flex-wrap: nowrap !important;
        }
        [data-testid="stExpander"] [data-testid="stToggle"] label > p,
        [data-testid="stExpander"] [data-testid="stToggle"] label > span:not([data-testid]) {
            white-space: nowrap !important;
            overflow: hidden !important;
            text-overflow: ellipsis !important;
            min-width: 0 !important;
            flex: 1 1 0 !important;
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

def inject_css() -> None:
    """Inject the NHL Age Curves custom CSS into the Streamlit page.

    Covers: animated gradient title, spinning NHL logo, sidebar compact layout,
    blue Add-Legend button override, toggle label ellipsis truncation for intermediate
    screen widths (foldable/tablet), mobile responsive controls row wrapping
    (~3 columns per row via #controls-row1 marker),
    responsive stacking of the chart/stats panel split on narrow screens, and
    Plotly modebar sizing for desktop and mobile.

    Must be called once per app run, after st.set_page_config().
    """
    st.markdown(_CSS, unsafe_allow_html=True)


def inject_mobile_dropdown_fix() -> None:
    """Inject JavaScript to prevent mobile keyboard from opening on dropdown taps.

    Streamlit's selectbox/multiselect use React Select which has a searchable
    input field. On mobile touch devices, focusing this input triggers the
    on-screen keyboard. This script intercepts touch events and prevents the
    input from receiving focus on mobile devices only.

    The fix targets:
        - Top 50 All-Time Skaters/Goalies dropdown
        - Active Rosters team selector
        - Select Player roster dropdown
        - X-Axis, Select Metric, Season Type, Leagues dropdowns

    Must be called once per app run, after st.set_page_config().
    """
    mobile_js = """
    <script>
    (function() {
        // Detect touch devices
        const isTouchDevice = window.matchMedia('(pointer: coarse)').matches ||
                              'ontouchstart' in window ||
                              navigator.maxTouchPoints > 0;

        if (!isTouchDevice) return; // Only run on mobile/touch devices

        // Function to disable search inputs in dropdowns
        function disableDropdownSearch() {
            // Target all inputs within dropdown popovers/menus
            const inputs = document.querySelectorAll('div[data-baseweb="popover"] input, div[data-baseweb="menu"] input, [role="listbox"] input, [role="combobox"] input');
            inputs.forEach(function(input) {
                if (input && !input._mobileFixed) {
                    input._mobileFixed = true;
                    // Prevent the input from receiving focus
                    input.setAttribute('readonly', 'readonly');
                    input.style.pointerEvents = 'none';
                    input.style.caretColor = 'transparent';
                }
            });
        }

        // Monitor for dropdown menu appearances
        const observer = new MutationObserver(function(mutations) {
            mutations.forEach(function(mutation) {
                if (mutation.addedNodes.length > 0) {
                    // Check if any added nodes contain dropdown menus
                    mutation.addedNodes.forEach(function(node) {
                        if (node.nodeType === 1) { // Element node
                            if (node.matches && (node.matches('[data-baseweb="popover"]') || node.matches('[data-baseweb="menu"]') || node.querySelector('[data-baseweb="popover"], [data-baseweb="menu"]'))) {
                                setTimeout(disableDropdownSearch, 0);
                            }
                        }
                    });
                }
            });
        });

        // Start observing the body for dropdown additions
        observer.observe(document.body, {
            childList: true,
            subtree: true
        });

        // Also handle clicks on selectboxes to catch the initial open
        document.addEventListener('click', function(e) {
            const selectbox = e.target.closest('div[data-baseweb="select"]');
            if (selectbox) {
                // Small delay to let the dropdown render
                setTimeout(disableDropdownSearch, 50);
                setTimeout(disableDropdownSearch, 150);
            }
        }, true);

        // Handle touch events specifically
        document.addEventListener('touchstart', function(e) {
            const selectbox = e.target.closest('div[data-baseweb="select"]');
            if (selectbox) {
                setTimeout(disableDropdownSearch, 50);
                setTimeout(disableDropdownSearch, 150);
            }
        }, { passive: true, capture: true });
    })();
    </script>
    """
    import streamlit.components.v1 as components
    components.html(mobile_js, height=0)
