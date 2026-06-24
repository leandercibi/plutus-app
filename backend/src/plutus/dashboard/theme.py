from __future__ import annotations

import streamlit as st

# Dark, calm palette (spec 14 §2). All hex lives here; no inline hex elsewhere.
BG_PRIMARY = "#1a1a1a"
SURFACE = "#1f1f1d"
PANEL = "#232321"
PANEL_DARK = "#141414"
BORDER = "#2a2a28"

TEXT_PRIMARY = "#f5f5f3"
TEXT_SECONDARY = "#a5a5a1"
TEXT_TERTIARY = "#7a7a76"
TEXT_MUTED = "#6a6a66"

SWING_ACCENT = "#c69a4a"  # amber
ACCUMULATION_ACCENT = "#8a7be0"  # purple
CASH_ACCENT = "#7fc88a"  # green
REGIME_BEAR = "#c45a5a"  # red

# Soft dead-zone chip color (B17).
DEAD_ZONE = "#e9b870"
DEAD_ZONE_BG = "#3a2b1a"

BUY_GREEN = "#7fc88a"
BUY_GREEN_BG = "#1f3320"
LOSS_RED = "#f0a3a3"
LOSS_RED_BG = "#2a1f1f"
INFO_BLUE = "#8aa9e0"
INFO_BLUE_BG = "#1f2b3a"

PILLAR_COLORS = {
    "technical": SWING_ACCENT,
    "expectancy": CASH_ACCENT,
    "flow": ACCUMULATION_ACCENT,
    "sentiment": TEXT_SECONDARY,
    "regime_fit": "#5dcaa5",
    "fundamentals": "#6aa3c8",
}


def inject_css() -> None:
    """Inject the global dark theme. Called once at app boot."""
    st.markdown(
        f"""
<style>
    .stApp {{ background: {BG_PRIMARY}; }}
    .main .block-container {{
        padding-top: 1.2rem; padding-bottom: 2rem; max-width: 1200px;
    }}
    /* sidebar */
    section[data-testid="stSidebar"] {{
        background: {PANEL_DARK}; border-right: 0.5px solid {BORDER};
    }}
    section[data-testid="stSidebar"] * {{ color: {TEXT_SECONDARY}; }}
    section[data-testid="stSidebar"] h1, section[data-testid="stSidebar"] h2,
    section[data-testid="stSidebar"] h3 {{ color: {TEXT_PRIMARY}; }}

    /* radio in sidebar = nav */
    section[data-testid="stSidebar"] div[role="radiogroup"] label {{
        background: transparent; padding: 6px 10px; border-radius: 6px;
        margin: 1px 0; color: {TEXT_SECONDARY}; font-size: 13px;
        border-left: 2px solid transparent;
    }}
    section[data-testid="stSidebar"] div[role="radiogroup"] label:hover {{
        background: {PANEL}; color: {TEXT_PRIMARY};
    }}
    section[data-testid="stSidebar"] div[role="radiogroup"] label[data-checked="true"] {{
        background: {PANEL}; color: {TEXT_PRIMARY};
        border-left: 2px solid {SWING_ACCENT};
    }}
    section[data-testid="stSidebar"] div[role="radiogroup"] > label > div:first-child {{
        display: none;  /* hide native radio dot */
    }}

    /* main body text */
    .main, .main * {{ color: {TEXT_PRIMARY}; }}
    .main .stCaption, .main small {{ color: {TEXT_TERTIARY}; }}
    .main h1 {{ color: {TEXT_PRIMARY}; font-weight: 500; font-size: 22px; }}
    .main h2 {{ color: {TEXT_PRIMARY}; font-weight: 500; font-size: 18px; }}
    .main h3 {{ color: {TEXT_PRIMARY}; font-weight: 500; font-size: 16px; }}

    /* metric */
    div[data-testid="stMetric"] {{
        background: {PANEL}; padding: 12px 14px; border-radius: 8px;
        border: 0.5px solid {BORDER};
    }}
    div[data-testid="stMetric"] label {{ color: {TEXT_TERTIARY}; font-size: 11px; }}
    div[data-testid="stMetricValue"] {{ color: {TEXT_PRIMARY}; font-size: 18px; font-weight: 500; }}
    div[data-testid="stMetricDelta"] {{ color: {TEXT_TERTIARY}; font-size: 11px; }}

    /* button */
    .stButton > button {{
        background: {PANEL}; color: {TEXT_PRIMARY};
        border: 0.5px solid {BORDER}; border-radius: 6px;
        font-size: 12px; padding: 4px 12px; font-weight: 400;
    }}
    .stButton > button:hover {{ background: {SURFACE}; border-color: {SWING_ACCENT}; }}
    .stButton > button:disabled {{ color: {TEXT_MUTED}; }}

    /* inputs */
    .stTextInput input, .stNumberInput input, .stSelectbox div[role="combobox"] {{
        background: {PANEL}; color: {TEXT_PRIMARY}; border-color: {BORDER};
    }}

    /* horizontal rule */
    hr {{ border-color: {BORDER}; }}

    /* alerts */
    div[data-testid="stAlert"] {{ background: {PANEL}; border-radius: 6px; }}

    /* Plutus custom classes */
    .plutus-card {{
        background: {SURFACE}; border-radius: 8px;
        padding: 12px 14px; margin-bottom: 10px;
        border: 0.5px solid {BORDER};
    }}
    .plutus-row {{
        display:grid; grid-template-columns: 90px 1fr 38px 60px;
        gap: 10px; align-items: center; font-size: 12px;
        color: {TEXT_PRIMARY}; padding: 6px 0;
    }}
    .plutus-row-detail {{
        font-size: 11px; color: {TEXT_TERTIARY};
        padding: 0 0 6px 100px; margin-top: -2px;
    }}
    .plutus-bar-track {{
        background: {BORDER}; border-radius: 3px; height: 6px; overflow: hidden;
    }}
    .plutus-bar-fill {{ height: 100%; }}
    .plutus-chip {{
        display: inline-block; padding: 3px 10px; border-radius: 12px;
        font-size: 11px; font-weight: 500;
    }}
    .plutus-pill {{
        display: inline-block; padding: 2px 8px; border-radius: 10px;
        font-size: 10px;
    }}
    .plutus-tranche {{
        display:inline-flex; width: 18px; height: 18px; border-radius: 3px;
        font-size: 9px; align-items:center; justify-content:center;
        color: #fff; margin-right: 3px;
    }}
    .plutus-banner {{
        padding: 10px 14px; border-radius: 6px; margin: 8px 0;
        font-size: 12px; line-height: 1.55;
    }}
    .plutus-section-label {{
        font-size: 10px; color: {TEXT_MUTED}; text-transform: lowercase;
        letter-spacing: 0.5px; margin: 14px 0 4px; padding: 0 8px;
    }}
    .plutus-counterfactual {{
        font-size: 12px; color: {TEXT_SECONDARY};
        border-top: 0.5px solid {BORDER}; padding-top: 8px; margin-top: 8px;
    }}
</style>
""",
        unsafe_allow_html=True,
    )
