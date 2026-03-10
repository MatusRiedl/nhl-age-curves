"""
nhl.styles — CSS injection and UI asset helpers for the NHL Age Curves page.

Contains the CSS injection helpers plus a small favicon path resolver so app.py
can keep page chrome configuration simple and robust across local and deployed
environments.
"""

import base64
from pathlib import Path

import streamlit as st

# ---------------------------------------------------------------------------
# Private CSS block
# ---------------------------------------------------------------------------

_CSS = """
    <style>
        .block-container { padding-top: 0.65rem !important; padding-bottom: 0rem !important; }

        [data-testid="stSidebar"] .sidebar-brand {
            display: flex;
            align-items: center;
            justify-content: center;
            width: 100%;
            margin: 0 0 0.65rem 0;
        }

        [data-testid="stSidebar"] .sidebar-brand__image {
            display: block;
            width: 100%;
            max-width: 100%;
            height: auto;
            margin: 0;
            filter: drop-shadow(0 8px 18px rgba(43, 113, 199, 0.16)) drop-shadow(0 6px 20px rgba(255, 255, 255, 0.22));
        }

        div.element-container:has(.sidebar-brand) {
            margin-bottom: 0.55rem !important;
        }

        [data-testid="stExpander"] {
            margin-top: 0 !important;
        }

        @media (max-width: 768px) {
            .block-container {
                padding-top: 0.35rem !important;
                padding-left: 0.35rem !important;
                padding-right: 0.35rem !important;
            }
            [data-testid="stSidebar"] .sidebar-brand__image {
                width: 100%;
            }
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
            color: #2596be !important;
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
            margin-top: 4px !important;
            margin-bottom: 4px !important;
        }
        [data-testid="stSidebar"] .element-container {
            margin-bottom: 2px !important;
        }
        [data-testid="stSidebar"] h3 {
            margin-top: 4px !important;
            margin-bottom: 4px !important;
        }
        [data-testid="stSidebar"] label[data-testid="stWidgetLabel"] {
            margin-bottom: 0.18rem !important;
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
        /* Dim sidebar selectbox value text to match text-input muted tone */
        [data-testid="stSidebar"] .stSelectbox [data-baseweb="select"] > div > div:first-child,
        [data-testid="stSidebar"] .stSelectbox [data-baseweb="select"] > div > div:first-child * {
            color: rgba(250, 250, 250, 0.55) !important;
        }

        /* Compact header and controls expander — reduce vertical whitespace */
        [data-testid="stExpander"] details summary {
            padding-top: 0.4rem !important;
            padding-bottom: 0.4rem !important;
            justify-content: center !important;
        }
        [data-testid="stExpander"] details summary p {
            font-size: 1.08rem !important;
            font-weight: 700 !important;
            color: rgba(255, 255, 255, 0.80) !important;
            letter-spacing: 0.01em !important;
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

        /* === Unified matchup cards === */
        .live-game-card {
            background:
                linear-gradient(
                    105deg,
                    var(--lgc-away-tint, transparent) 0%,
                    rgba(255, 255, 255, 0.018) 38%,
                    rgba(255, 255, 255, 0.018) 62%,
                    var(--lgc-home-tint, transparent) 100%
                );
            box-shadow: inset 0 0 80px var(--lgc-inset-glow, transparent);
            border: 1px solid rgba(255, 255, 255, 0.10);
            border-radius: 10px;
            margin-bottom: 0.55rem;
            padding: 0.55rem 0.65rem 0.45rem;
            box-sizing: border-box;
        }
        .lgc-matchup {
            display: flex;
            align-items: center;
            gap: 8px;
            flex-wrap: wrap;
            font-size: 1rem;
            margin-bottom: 0.15rem;
        }
        .lgc-detail {
            color: #8c8c8c;
            font-size: 0.9rem;
            line-height: 1.2;
            margin-bottom: 0.38rem;
        }
        .lgc-prob-section {
            /* probability labels + bar + meta embedded in card */
        }
        .live-games-probability--muted {
            color: #8c8c8c;
            font-size: 0.9rem;
        }

        .live-games-probability__labels {
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 0.75rem;
            font-size: 0.93rem;
            margin-bottom: 0.28rem;
        }
        .live-games-probability__label {
            color: rgba(255, 255, 255, var(--label-opacity, 0.92));
            text-shadow: 0 0 18px var(--label-glow, rgba(0, 0, 0, 0));
            transition: color 120ms ease, text-shadow 120ms ease, opacity 120ms ease;
        }
        .live-games-probability__label strong {
            font-size: 1.02rem;
            letter-spacing: -0.01em;
        }
        .live-games-probability__label--leading {
            color: rgba(255, 255, 255, 0.99);
        }
        .live-games-probability__label--trailing {
            color: rgba(255, 255, 255, 0.8);
        }
        .live-games-probability__bar {
            display: flex;
            position: relative;
            isolation: isolate;
            width: 100%;
            height: 8px;
            overflow: hidden;
            border-radius: 999px;
            background: rgba(255, 255, 255, 0.045);
            margin-bottom: 0.38rem;
            box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.04), inset 0 8px 18px rgba(255, 255, 255, 0.03);
        }
        .live-games-probability__bar::before,
        .live-games-probability__bar::after {
            content: "";
            position: absolute;
            top: -10px;
            bottom: -10px;
            pointer-events: none;
            filter: blur(10px);
            opacity: 0.95;
            z-index: 0;
        }
        .live-games-probability__bar::before {
            left: 0;
            width: var(--away-glow-width, 0%);
            background: linear-gradient(90deg, var(--away-bar-glow, rgba(0, 0, 0, 0)), rgba(0, 0, 0, 0) 88%);
        }
        .live-games-probability__bar::after {
            right: 0;
            width: var(--home-glow-width, 0%);
            background: linear-gradient(270deg, var(--home-bar-glow, rgba(0, 0, 0, 0)), rgba(0, 0, 0, 0) 88%);
        }
        .live-games-probability__segment {
            display: block;
            position: relative;
            z-index: 1;
            height: 100%;
            min-width: 0;
            background:
                linear-gradient(
                    180deg,
                    rgba(255, 255, 255, var(--segment-sheen, 0.08)) 0%,
                    var(--segment-color, rgba(255, 255, 255, 0.55)) 45%,
                    var(--segment-color, rgba(255, 255, 255, 0.55)) 100%
                );
            opacity: var(--segment-opacity, 1);
            filter: saturate(var(--segment-saturation, 1)) brightness(var(--segment-brightness, 1));
            transition: opacity 120ms ease, filter 120ms ease, box-shadow 120ms ease;
        }
        .live-games-probability__segment--leading {
            box-shadow: inset 0 0 12px rgba(255, 255, 255, 0.16), 0 0 14px var(--segment-glow, rgba(0, 0, 0, 0));
        }
        .live-games-probability__segment--trailing {
            box-shadow: inset 0 0 10px rgba(0, 0, 0, 0.16);
        }
        .live-games-probability__segment--tied {
            box-shadow: inset 0 0 10px rgba(255, 255, 255, 0.12);
        }
        .live-games-probability__divider {
            position: absolute;
            top: 0;
            bottom: 0;
            width: 6px;
            transform: translateX(-50%);
            border-radius: 999px;
            background: rgba(255, 255, 255, 0.4);
            pointer-events: none;
            z-index: 2;
        }
        .live-games-probability__meta {
            color: #9a9a9a;
            font-size: 0.78rem;
            line-height: 1.2;
        }
        div.element-container:has(.live-game-card) {
            margin-bottom: 0.55rem !important;
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
        div.element-container:has(.nhl-chart-toolbar) {
            margin: 0 !important;
            line-height: 0 !important;
        }
        div.element-container:has(.nhl-chart-toolbar) + div.element-container {
            margin-top: 0 !important;
        }
        .nhl-chart-toolbar {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 0.75rem;
            min-height: 40px !important;
            margin: 0 0 0.18rem 0;
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
                margin: 0 0 0.1rem 0;
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

        /* Match column gap between side-by-side player cards to prediction card gap */
        [data-baseweb="tab-panel"] [data-testid="stHorizontalBlock"]:has(.comparison-player-card) {
            column-gap: 1.1rem !important;
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
        .comparison-player-card {
            display: flex;
            align-items: flex-start;
            gap: 0.9rem;
            margin: 0 0 1.1rem 0;
            padding: 0.9rem;
            border: 1px solid rgba(70, 84, 122, 0.5);
            border-radius: 18px;
            background: linear-gradient(
                160deg,
                var(--pc-color-tint, transparent) 0%,
                rgba(12, 18, 33, 0.92) 40%,
                rgba(9, 13, 24, 0.98) 100%
            );
            box-shadow:
                inset 0 0 80px var(--pc-inset-glow, transparent),
                0 12px 24px rgba(0, 0, 0, 0.16);
        }
        .comparison-player-card--no-image {
            padding-left: 1rem;
        }
        .comparison-player-card__media {
            display: flex;
            flex-direction: column;
            align-items: flex-start;
            flex: 0 0 38%;
            max-width: 180px;
        }
        .comparison-player-card__media--player {
            position: relative;
            align-items: center;
            justify-content: flex-end;
            flex: 0 0 20%;
            min-width: 72px;
            min-height: 86px;
            max-width: 104px;
            padding: 0.15rem 0.2rem 0;
            isolation: isolate;
            overflow: visible;
        }
        .comparison-player-card__media--player::before {
            content: "";
            position: absolute;
            inset: 14% 8% 22%;
            border-radius: 50%;
            background: radial-gradient(
                circle at 50% 40%,
                rgba(255, 255, 255, 0.14) 0%,
                rgba(116, 148, 220, 0.18) 28%,
                rgba(39, 54, 92, 0) 74%
            );
            filter: blur(13px);
            z-index: 0;
            pointer-events: none;
        }
        .comparison-player-card__media--player::after {
            content: "";
            position: absolute;
            left: 16%;
            right: 16%;
            bottom: 0.45rem;
            height: 1.2rem;
            border-radius: 999px;
            background: radial-gradient(circle at 50% 50%, rgba(0, 0, 0, 0.38) 0%, rgba(0, 0, 0, 0) 72%);
            filter: blur(6px);
            z-index: 0;
            pointer-events: none;
        }
        .comparison-player-card__image {
            display: block;
            width: 100%;
            aspect-ratio: 4 / 3;
            object-fit: cover;
            border-radius: 14px;
        }
        .comparison-player-card__image--player-cutout {
            position: relative;
            z-index: 1;
            width: auto;
            max-width: 100%;
            height: 96px;
            aspect-ratio: auto;
            object-fit: contain;
            border-radius: 0;
            filter: drop-shadow(0 12px 14px rgba(0, 0, 0, 0.32)) drop-shadow(0 3px 6px rgba(0, 0, 0, 0.16));
            transform: translateY(5px) scale(1.16);
            transform-origin: center bottom;
        }
        .comparison-player-card__body {
            flex: 1 1 auto;
            min-width: 0;
        }
        .comparison-card-stats {
            display: flex;
            flex-wrap: wrap;
            align-items: baseline;
            gap: 0.2rem 0.9rem;
            margin: 0.18rem 0 0 0;
            font-size: 0.92rem;
        }
        .comparison-card-context-row {
            margin-top: 0.18rem;
            line-height: 1.2;
        }
        .comparison-card-stats__item {
            display: inline-flex;
            align-items: baseline;
            min-width: 0;
            white-space: nowrap;
        }
        .comparison-card-stats__label {
            color: #f4f6fb;
            font-weight: 700;
        }
        .comparison-card-stats__value {
            color: #f4f6fb;
            font-weight: 600;
        }
        .comparison-player-card--team {
            align-items: center;
        }
        .comparison-player-card__media--team {
            flex: 0 0 112px;
            max-width: 112px;
            align-items: center;
            justify-content: center;
        }
        .comparison-player-card__image--team-logo {
            width: 100%;
            aspect-ratio: 1 / 1;
            object-fit: contain;
            padding: 0.4rem;
        }
        .comparison-panel-heading {
            margin: 0 0 0.22rem 0;
            color: #f4f6fb;
            font-size: 0.98rem;
            font-weight: 700;
            letter-spacing: 0.01em;
        }
        .comparison-panel-heading--rail-title {
            display: flex;
            align-items: center;
            justify-content: center;
            width: 100%;
            text-align: center;
            font-size: 1.08rem;
            font-weight: 700;
            letter-spacing: 0.01em;
            line-height: 1.1;
            color: rgba(255, 255, 255, 0.80);
        }
        .comparison-panel-heading--predictions {
            margin: 0 auto 0.42rem;
            padding: 0.18rem 0 0.16rem;
        }
        .comparison-panel-heading--season {
            margin: 0 auto 0.2rem;
            padding: 0.18rem 0 0.08rem;
        }
        .comparison-trace-toggle-row {
            display: flex;
            flex-wrap: wrap;
            gap: 0.45rem;
            margin: 0.22rem 0 0 0;
        }
        .comparison-trace-toggle {
            display: inline-flex;
            align-items: center;
            gap: 0.55rem;
            padding: 0.34rem 0.72rem;
            border: 1px solid rgba(96, 165, 250, 0.20);
            border-radius: 999px;
            background: rgba(15, 23, 42, 0.62);
            color: #e5edf9;
            font-size: 0.78rem;
            font-weight: 600;
            line-height: 1;
            cursor: pointer;
            transition: border-color 0.18s ease, background 0.18s ease, color 0.18s ease, opacity 0.18s ease;
        }
        .comparison-trace-toggle:hover {
            border-color: rgba(148, 163, 184, 0.34);
            background: rgba(30, 41, 59, 0.86);
        }
        .comparison-trace-toggle.is-inactive {
            opacity: 0.56;
            background: rgba(15, 23, 42, 0.28);
        }
        .comparison-trace-toggle--icon-only {
            justify-content: center;
            gap: 0;
            min-width: 2.45rem;
            padding: 0.34rem 0.62rem;
        }
        .comparison-trace-toggle__line {
            position: relative;
            width: 18px;
            height: 0;
            border-top: 3px solid var(--trace-toggle-color, #4caf50);
            border-radius: 999px;
            flex: 0 0 auto;
        }
        .comparison-trace-toggle__line::after {
            content: "";
            position: absolute;
            top: -5px;
            left: 50%;
            width: 8px;
            height: 8px;
            transform: translateX(-50%);
            border-radius: 999px;
            background: var(--trace-toggle-color, #4caf50);
            box-shadow: 0 0 0 2px rgba(255, 255, 255, 0.12);
        }
        .comparison-trace-toggle__label {
            white-space: nowrap;
        }
        .comparison-trace-toggle--compact {
            padding: 0.28rem 0.64rem;
            font-size: 0.74rem;
        }

        /* Chart season selector moved into the comparison panel */
        div:has(> #comparison-season-filter) {
            margin: 0 !important;
            line-height: 0 !important;
        }
        div:has(> #comparison-season-filter) + div {
            margin-top: 0 !important;
            margin-bottom: 0 !important;
        }
        div:has(> #comparison-season-filter) + div .stSelectbox label {
            display: none !important;
        }
        div:has(> #comparison-season-filter) + div .stSelectbox {
            margin-bottom: 0 !important;
        }
        div:has(> #comparison-season-filter) + div .stSelectbox [data-baseweb="select"] > div > div:first-child,
        div:has(> #comparison-season-filter) + div .stSelectbox [data-baseweb="select"] > div > div:first-child * {
            font-weight: 700 !important;
            font-size: 1.08rem !important;
            color: rgba(255, 255, 255, 0.80) !important;
            letter-spacing: 0.01em !important;
        }
        div:has(> #comparison-controls-panel) {
            margin: 0 !important;
            line-height: 0 !important;
        }
        div:has(> #comparison-controls-panel) + div {
            margin-top: -0.55rem !important;
            margin-bottom: 0 !important;
        }
        div:has(> #comparison-controls-panel) + div [data-testid="stExpander"] {
            margin-bottom: 0 !important;
        }
        div:has(> #comparison-controls-panel) + div [data-testid="stExpander"] details summary {
            padding-top: 0.3rem !important;
            padding-bottom: 0.3rem !important;
        }
        div:has(> #comparison-predictions-panel) {
            margin: 0 !important;
            line-height: 0 !important;
        }
        div:has(> #comparison-predictions-panel) + div {
            margin-top: -0.34rem !important;
        }
        div.element-container:has(#comparison-main-plotly) {
            margin: 0 !important;
            line-height: 0 !important;
        }
        div.element-container:has(#comparison-main-plotly) + div.element-container {
            margin-top: 0 !important;
            margin-bottom: -2.15rem !important;
            line-height: 0 !important;
        }
        div.element-container:has(#comparison-main-plotly) + div.element-container [data-testid="stPlotlyChart"] {
            margin-bottom: 0 !important;
            padding-bottom: 0 !important;
            line-height: normal !important;
        }
        /* === Main chart window base styles === */
        div[data-testid="stPlotlyChart"] {
            border: 1px solid rgba(70, 84, 122, 0.5);
            border-radius: 14px;
            overflow: hidden;
            transition: box-shadow 0.3s ease, background 0.3s ease;
        }
        div.element-container:has(#comparison-detail-layout) {
            margin: -1.65rem 0 0 0 !important;
            line-height: 0 !important;
        }
        div.element-container:has(#comparison-detail-layout) + div.element-container {
            margin-top: 0 !important;
        }

        /* Comparison tab row (native st.tabs) */
        div.element-container:has(#comparison-tabs) {
            margin: 0 !important;
            line-height: 0 !important;
        }
        div.element-container:has(#comparison-tabs) + div.element-container {
            margin-top: -0.2rem !important;
        }
        div.element-container:has(#comparison-tabs) + div.element-container [data-testid="stTabs"] {
            margin-top: 0 !important;
            padding-top: 0 !important;
        }
        div.element-container:has(#comparison-tabs) + div.element-container [data-testid="stTabs"] [data-baseweb="tab-list"] {
            gap: 0.35rem !important;
            flex-wrap: wrap !important;
            margin-bottom: 0.22rem !important;
            min-height: 40px !important;
            align-items: center !important;
            padding-top: 0 !important;
        }
        div.element-container:has(#comparison-tabs) + div.element-container [data-testid="stTabs"] [data-baseweb="tab-border"] {
            display: none !important;
        }
        div.element-container:has(#comparison-tabs) + div.element-container [data-testid="stTabs"] button[role="tab"] {
            margin: 0 !important;
            border: 1px solid #2a2a2a !important;
            border-radius: 999px !important;
            background: rgba(17, 24, 39, 0.7) !important;
            padding: 4px 10px !important;
            min-height: 0 !important;
            height: auto !important;
        }
        div.element-container:has(#comparison-tabs) + div.element-container [data-testid="stTabs"] button[role="tab"] p {
            margin: 0 !important;
            font-size: 13px !important;
            font-weight: 600 !important;
            color: #d9d9d9 !important;
        }
        div.element-container:has(#comparison-tabs) + div.element-container [data-testid="stTabs"] button[role="tab"][aria-selected="true"] {
            border-color: #2596be !important;
            background: rgba(37, 150, 190, 0.14) !important;
        }
        div.element-container:has(#comparison-tabs) + div.element-container [data-testid="stTabs"] [data-baseweb="tab-panel"] {
            padding-top: 0.1rem !important;
        }
        @media (max-width: 768px) {
            div.element-container:has(#comparison-tabs) + div.element-container [data-testid="stTabs"] button[role="tab"] {
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
            .main .block-container {
                padding-left: 0.5rem !important;
                padding-right: 0.5rem !important;
            }
            .main [data-testid="stHorizontalBlock"] {
                flex-wrap: wrap !important;
            }
            .main [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {
                min-width: 100% !important;
                width: 100% !important;
            }
            .comparison-player-card {
                flex-direction: column;
                gap: 0.7rem;
                padding: 0.8rem;
                margin-bottom: 0.55rem;
            }
            div.element-container:has(.live-game-card) {
                margin-bottom: 1.1rem !important;
            }
            .comparison-player-card__media {
                flex-basis: auto;
                max-width: 100%;
            }
            .comparison-player-card__media--player {
                width: min(100%, 118px);
                min-height: 90px;
                margin: 0 auto;
            }
            .comparison-player-card__image--player-cutout {
                height: 100px;
                transform: translateY(6px) scale(1.14);
            }
            .comparison-card-stats {
                grid-template-columns: repeat(2, minmax(0, 1fr));
            }
            .comparison-player-card__media--team {
                flex-basis: auto;
                max-width: 124px;
                margin: 0 auto;
            }
            .comparison-player-card__image--team-logo {
                padding: 0.3rem;
            }
            .comparison-trace-toggle {
                gap: 0.45rem;
                padding: 0.3rem 0.64rem;
                font-size: 0.74rem;
            }
            .comparison-trace-toggle--icon-only {
                min-width: 2.2rem;
                padding: 0.3rem 0.52rem;
            }
            .comparison-trace-toggle--compact {
                padding: 0.26rem 0.56rem;
                font-size: 0.7rem;
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
            min-height: 30px !important;
            line-height: 1 !important;
            overflow: visible !important;
            display: flex !important;
            align-items: center !important;
        }
        .js-plotly-plot .plotly .modebar-btn::before,
        .js-plotly-plot .plotly .modebar-btn::after {
            display: none !important;
            content: none !important;
        }
        .js-plotly-plot .plotly .modebar-group {
            flex-wrap: nowrap !important;
            overflow-x: auto !important;
            overflow-y: visible !important;
            padding: 0 !important;
            line-height: 1 !important;
            display: flex !important;
            align-items: center !important;
        }
        .js-plotly-plot .plotly .modebar-btn {
            padding: 6px 8px !important;
            min-height: 30px !important;
            line-height: 1 !important;
            display: flex !important;
            align-items: center !important;
            justify-content: center !important;
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
                min-height: 22px !important;
            }
            .js-plotly-plot .plotly .modebar-btn svg {
                width: 14px !important;
                height: 14px !important;
            }
        }

        /* Early overlay sidebar mode — stop reflow on foldables / cramped widths */
        @media screen and (max-width: 1400px), screen and (max-width: 1600px) and (max-aspect-ratio: 11/10) {
            :root {
                --pp-overlay-sidebar-top: calc(env(safe-area-inset-top, 0px) + 3.75rem);
            }
            .comparison-player-card__media--player {
                display: none !important;
            }
            [data-testid="stAppViewContainer"] {
                overflow-x: clip !important;
            }
            section[data-testid="stSidebar"] {
                position: fixed !important;
                inset: var(--pp-overlay-sidebar-top) auto 0 0 !important;
                height: calc(100dvh - var(--pp-overlay-sidebar-top)) !important;
                z-index: 1002 !important;
            }
            section[data-testid="stSidebar"] > div:first-child {
                height: calc(100dvh - var(--pp-overlay-sidebar-top)) !important;
                box-shadow: 18px 0 36px rgba(8, 12, 22, 0.42) !important;
            }
            section[data-testid="stMain"] {
                width: 100% !important;
                max-width: 100% !important;
            }
            [data-testid="collapsedControl"] {
                position: fixed !important;
                top: calc(var(--pp-overlay-sidebar-top) + 0.35rem) !important;
                left: 0.75rem !important;
                z-index: 1003 !important;
            }
            [data-testid="stSidebarCollapseButton"] {
                z-index: 1003 !important;
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
                #2596be 50%,
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


def get_header_logo_path() -> Path:
    """Return the absolute path to the preferred brand logo PNG.

    Returns:
        Path: Absolute path to the PuckPeak logo file in the repository assets folder.
    """
    return Path(__file__).resolve().parent.parent / "assets" / "PP.png"


def get_header_logo_data_uri() -> str:
    """Return the brand logo PNG as an inline image data URI.

    Returns:
        str: Base64-encoded PNG data URI for embedding the local brand image,
            or an empty string if the PNG asset is unavailable.
    """
    logo_path = get_header_logo_path()
    if logo_path.exists():
        logo_bytes = logo_path.read_bytes()
        return f"data:image/png;base64,{base64.b64encode(logo_bytes).decode('ascii')}"

    return ""


def inject_css() -> None:
    """Inject the NHL Age Curves custom CSS into the Streamlit page.

    Covers: sidebar brand logo styling, tighter top spacing, sidebar compact/overlay layout,
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
