"""
Visual style of the website: colours, fonts, cards and the chart template.

Kept apart from src/app.py so that the page logic and the look can be
changed independently. Nothing here reads data or computes anything.

    from style import apply_style, hero, INK, LIME
    apply_style()           # once, right after st.set_page_config
    hero(title, subtitle)   # the lime header block

Colours: a lime accent on near-black ink, light grey page, white cards.
Fonts: the system sans-serif only (the site must work offline, so no web
fonts are downloaded).
"""

import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st

# Palette
INK = "#0e1a1f"          # near-black, headings and dark cards
INK_2 = "#4a5559"        # secondary text
MUTED = "#8a9396"        # axis labels
LIME = "#d4f26a"         # accent: hero, highlights
LIME_DARK = "#7f9c12"    # lime that is readable on white (lines, bars)
TEAL = "#1f5f6b"         # second series colour
PAGE = "#eef0ec"         # page background
CARD = "#ffffff"         # card background
LINE = "#dfe3dc"         # hairlines and grid

HEADING_FONT = ('"Segoe UI Black", "Arial Black", "Segoe UI", system-ui, '
                '-apple-system, sans-serif')
BODY_FONT = '"Segoe UI", system-ui, -apple-system, Roboto, Arial, sans-serif'

CSS = f"""
<style>
/* Page */
.stApp {{ background: {PAGE}; }}
.block-container {{ padding-top: 1.2rem; padding-bottom: 3rem; max-width: 1180px; }}
html, body, .stApp, .stMarkdown, p, li, label {{ font-family: {BODY_FONT}; color: {INK}; }}
header[data-testid="stHeader"] {{ background: transparent; }}

/* Headings */
h1, h2, h3 {{ font-family: {HEADING_FONT}; color: {INK}; letter-spacing: -0.02em; }}
h3 {{ text-transform: uppercase; font-size: 1.55rem !important; font-weight: 900 !important;
      margin-top: 2.2rem !important; padding-top: 1.4rem; border-top: 1px solid {LINE}; }}

/* Top bar */
.kz-topbar {{ display: flex; justify-content: space-between; align-items: center;
              background: {INK}; color: #fff; border-radius: 14px 14px 0 0;
              padding: 0.7rem 1.4rem; font-size: 0.85rem; }}
.kz-topbar b {{ color: {LIME}; font-family: {HEADING_FONT}; letter-spacing: 0.02em; }}
.kz-topbar span {{ color: #c9d1d3; }}

/* Hero */
.kz-hero {{ background: {LIME}; border-radius: 0 0 22px 22px; padding: 2rem 1.6rem 1.6rem; }}
.kz-hero h1 {{ font-family: {HEADING_FONT}; font-weight: 900; text-transform: uppercase;
               font-size: clamp(2rem, 4.4vw, 3.6rem); line-height: 0.98; margin: 0;
               color: {INK}; padding: 0; }}
.kz-hero p {{ max-width: 46rem; margin: 0.9rem 0 0; color: {INK}; font-size: 1rem; }}
.kz-pill {{ display: inline-block; margin-top: 1.1rem; background: {INK}; color: #fff;
            border-radius: 999px; padding: 0.45rem 1rem; font-size: 0.85rem; }}
.kz-pill b {{ color: {LIME}; }}

/* KPI cards (st.metric) */
[data-testid="stMetric"] {{ background: {CARD}; border-radius: 18px; padding: 1.1rem 1.3rem;
                            border: 1px solid {LINE}; height: 100%; }}
[data-testid="stMetricLabel"] p {{ color: {INK_2}; font-size: 0.85rem; text-transform: uppercase;
                                   letter-spacing: 0.04em; }}
[data-testid="stMetricValue"] {{ font-family: {HEADING_FONT}; font-weight: 900; color: {INK}; }}
.st-key-kpis {{ margin-top: 1rem; }}
.st-key-kpis [data-testid="stColumn"]:first-child [data-testid="stMetric"] {{
    background: {INK}; border-color: {INK}; }}
.st-key-kpis [data-testid="stColumn"]:first-child [data-testid="stMetricLabel"] p {{ color: #c9d1d3; }}
.st-key-kpis [data-testid="stColumn"]:first-child [data-testid="stMetricValue"],
.st-key-kpis [data-testid="stColumn"]:first-child [data-testid="stMetricValue"] * {{
    color: {LIME} !important; font-size: 3.2rem; line-height: 1.1; }}
.st-key-kpis [data-testid="stColumn"]:first-child [data-testid="stMetricDelta"] {{
    background: {LIME} !important; color: {INK} !important; }}
.st-key-kpis [data-testid="stColumn"]:first-child [data-testid="stMetricDelta"] div,
.st-key-kpis [data-testid="stColumn"]:first-child [data-testid="stMetricDelta"] p,
.st-key-kpis [data-testid="stColumn"]:first-child [data-testid="stMetricDelta"] svg {{
    color: {INK} !important; }}

/* Charts, tables, expanders as white cards */
[data-testid="stPlotlyChart"] {{ background: {CARD}; border-radius: 18px; padding: 0.6rem 0.8rem;
                                 border: 1px solid {LINE}; }}
[data-testid="stDataFrame"] {{ border-radius: 14px; overflow: hidden; border: 1px solid {LINE}; }}
[data-testid="stExpander"] details {{ background: {CARD}; border-radius: 18px; border: 1px solid {LINE}; }}

/* Notices */
[data-testid="stAlert"] {{ border-radius: 16px; }}

/* Controls */
[data-testid="stSlider"] [role="slider"] {{ background: {INK}; border: 3px solid {LIME}; }}
[data-baseweb="select"] > div {{ border-radius: 12px; }}

/* Captions */
[data-testid="stCaptionContainer"] p {{ color: {INK_2}; }}
</style>
"""


def chart_template():
    """Plotly template in the site's colours, used by every chart."""
    template = go.layout.Template()
    template.layout = go.Layout(
        font=dict(family=BODY_FONT.replace('"', ""), color=INK, size=13),
        colorway=[INK, LIME_DARK, TEAL],
        paper_bgcolor=CARD,
        plot_bgcolor=CARD,
        xaxis=dict(gridcolor=LINE, linecolor=LINE, zeroline=False,
                   tickfont=dict(color=INK_2), title=dict(font=dict(color=INK_2))),
        yaxis=dict(gridcolor=LINE, linecolor=LINE, zerolinecolor=LINE,
                   tickfont=dict(color=INK_2), title=dict(font=dict(color=INK_2))),
        hoverlabel=dict(bgcolor=INK, font=dict(color="#ffffff"), bordercolor=INK),
        legend=dict(font=dict(color=INK_2)),
    )
    return template


def apply_style():
    """Inject the page CSS and make the chart template the default."""
    st.markdown(CSS, unsafe_allow_html=True)
    pio.templates["kz"] = chart_template()
    pio.templates.default = "kz"


def hero(title, subtitle, note=""):
    """Dark top bar and the lime header block with the page title."""
    st.markdown(
        '<div class="kz-topbar"><b>KZ · DOLLARIZATION INDEX</b>'
        "<span>Household deposits · monthly · National Bank of Kazakhstan</span></div>"
        f'<div class="kz-hero"><h1>{title}</h1><p>{subtitle}</p>'
        + (f'<div class="kz-pill">{note}</div>' if note else "")
        + "</div>",
        unsafe_allow_html=True,
    )
