"""
ui_theme.py — Shared professional design system for LocReach Streamlit pages.
"""
import base64
import html as _html
from pathlib import Path

import streamlit as st

REACH     = {"400": "#60a5fa", "500": "#3b82f6", "600": "#2563eb"}
SIGNAL    = {"400": "#c084fc", "500": "#a855f7"}
QUALIFIED = {"400": "#34d399", "500": "#10b981"}
PIPELINE  = {"400": "#fb923c", "500": "#f97316"}
RED       = {"400": "#f87171", "500": "#ef4444"}
SLATE     = {
    "950": "#020617", "900": "#0f172a", "800": "#1e293b", "700": "#334155",
    "600": "#475569", "500": "#64748b", "400": "#94a3b8", "300": "#cbd5e1",
    "200": "#e2e8f0", "100": "#f1f5f9",
}


def _locreach_bg_data_uri() -> str:
    path = Path(__file__).resolve().parent / "assets" / "locreach_bg.png"
    if not path.is_file():
        return ""
    b64 = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{b64}"


_BG_URI = _locreach_bg_data_uri()
_APP_BG = (
    f'url("{_BG_URI}")'
    if _BG_URI
    else f'radial-gradient(ellipse 120% 80% at 10% -10%, #0b1b34 0%, {SLATE["950"]} 42%, #010409 100%)'
)

_THEME_CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

/* ── Base / app shell ─────────────────────────────────────────────────── */
html, body, .stApp {{
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif !important;
  color: #ffffff !important;
}}
.stApp {{
  background-color: {SLATE["950"]} !important;
  background-image: {_APP_BG} !important;
  background-size: cover !important;
  background-position: center center !important;
  background-repeat: no-repeat !important;
  background-attachment: fixed !important;
}}
/* App-wide white text */
.stApp p, .stApp span, .stApp label, .stApp li, .stApp a,
.stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp h5, .stApp h6,
.stApp [data-testid="stMarkdownContainer"],
.stApp [data-testid="stCaptionContainer"],
.stApp [data-testid="stWidgetLabel"],
.stApp [data-testid="stMetricLabel"],
.stApp [data-testid="stMetricValue"],
.stApp .stCaption, .stApp small, .stApp code {{
  color: #ffffff !important;
}}
.stApp button, .stApp [data-testid="stPageLink-NavLink"] {{
  color: #ffffff !important;
}}
/* Stable layout with branded sidebar */
[data-testid="stAppViewContainer"],
[data-testid="stAppViewContainer"] > section,
[data-testid="stMain"],
section.main {{
  transition: none !important;
  animation: none !important;
  background: transparent !important;
}}
/* Left navigation sidebar — fixed width, no scroll */
section[data-testid="stSidebar"],
aside[data-testid="stSidebar"] {{
  display: flex !important;
  visibility: visible !important;
  opacity: 1 !important;
  transform: none !important;
  margin-left: 0 !important;
  width: 180px !important;
  min-width: 180px !important;
  max-width: 180px !important;
  overflow-x: hidden !important;
  overflow-y: hidden !important;
  background: linear-gradient(180deg, rgba(15,23,42,0.92) 0%, rgba(2,6,23,0.94) 100%) !important;
  border-right: 3px solid rgba(96,165,250,0.55) !important;
  z-index: 999 !important;
}}
section[data-testid="stSidebar"] > div,
aside[data-testid="stSidebar"] > div {{
  background: transparent !important;
  width: 100% !important;
  max-width: 100% !important;
  overflow-x: hidden !important;
  overflow-y: hidden !important;
  padding: 0.45rem 0.4rem !important;
  box-sizing: border-box !important;
}}
/* Beat Streamlit's inline style="width: 300px" on the sidebar */
html body section[data-testid="stSidebar"],
html body aside[data-testid="stSidebar"],
section.stSidebar[data-testid="stSidebar"],
aside.stSidebar[data-testid="stSidebar"] {{
  width: 180px !important;
  min-width: 180px !important;
  max-width: 180px !important;
  flex: 0 0 180px !important;
  display: flex !important;
  flex-direction: column !important;
  align-items: stretch !important;
}}
/* THE empty-space culprit: Streamlit sizes this to content (~82px) inside a wider sidebar */
section[data-testid="stSidebar"] [data-testid="stSidebarContent"],
aside[data-testid="stSidebar"] [data-testid="stSidebarContent"] {{
  width: 100% !important;
  min-width: 100% !important;
  max-width: 100% !important;
  flex: 1 1 auto !important;
  align-self: stretch !important;
  box-sizing: border-box !important;
}}
section[data-testid="stSidebar"] [data-testid="stSidebarUserContent"],
aside[data-testid="stSidebar"] [data-testid="stSidebarUserContent"],
section[data-testid="stSidebar"] [data-testid="stHtml"],
aside[data-testid="stSidebar"] [data-testid="stHtml"],
section[data-testid="stSidebar"] [data-testid="stElementContainer"],
aside[data-testid="stSidebar"] [data-testid="stElementContainer"],
section[data-testid="stSidebar"] [data-testid="stVerticalBlock"],
aside[data-testid="stSidebar"] [data-testid="stVerticalBlock"] {{
  width: 100% !important;
  min-width: 100% !important;
  max-width: 100% !important;
  box-sizing: border-box !important;
}}
section[data-testid="stSidebar"] ::-webkit-scrollbar,
aside[data-testid="stSidebar"] ::-webkit-scrollbar {{
  display: none !important;
  width: 0 !important;
  height: 0 !important;
}}
section[data-testid="stSidebar"],
aside[data-testid="stSidebar"],
section[data-testid="stSidebar"] *,
aside[data-testid="stSidebar"] * {{
  scrollbar-width: none !important;
  -ms-overflow-style: none !important;
}}
section[data-testid="stSidebar"] p,
section[data-testid="stSidebar"] span,
section[data-testid="stSidebar"] label,
aside[data-testid="stSidebar"] p,
aside[data-testid="stSidebar"] span,
aside[data-testid="stSidebar"] label {{
  color: #ffffff !important;
}}
/* Custom HTML sidebar — force Streamlit wrappers to full bar width */
section[data-testid="stSidebar"] [data-testid="stSidebarContent"],
aside[data-testid="stSidebar"] [data-testid="stSidebarContent"],
section[data-testid="stSidebar"] [data-testid="stSidebarUserContent"],
aside[data-testid="stSidebar"] [data-testid="stSidebarUserContent"],
section[data-testid="stSidebar"] [data-testid="stVerticalBlock"],
aside[data-testid="stSidebar"] [data-testid="stVerticalBlock"],
section[data-testid="stSidebar"] [data-testid="stVerticalBlock"] > div,
aside[data-testid="stSidebar"] [data-testid="stVerticalBlock"] > div,
section[data-testid="stSidebar"] [data-testid="element-container"],
aside[data-testid="stSidebar"] [data-testid="element-container"],
section[data-testid="stSidebar"] [data-testid="stElementContainer"],
aside[data-testid="stSidebar"] [data-testid="stElementContainer"],
section[data-testid="stSidebar"] [data-testid="stHtml"],
aside[data-testid="stSidebar"] [data-testid="stHtml"],
section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"],
aside[data-testid="stSidebar"] [data-testid="stMarkdownContainer"],
section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] > div,
aside[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] > div {{
  width: 100% !important;
  max-width: 100% !important;
  min-width: 100% !important;
  box-sizing: border-box !important;
}}
.lr-side {{
  display: block !important;
  width: 100% !important;
  min-width: 100% !important;
  box-sizing: border-box !important;
}}
.lr-side-brand {{
  display: flex !important;
  justify-content: center !important;
  align-items: center !important;
  width: 100% !important;
  margin: 2px 0 14px 0 !important;
}}
.lr-side-brand img {{
  display: block !important;
  width: 140px !important;
  max-width: 100% !important;
  height: auto !important;
  margin: 0 auto !important;
  background: transparent !important;
  border: none !important;
  box-shadow: none !important;
}}
.lr-side-nav {{
  display: flex !important;
  flex-direction: column !important;
  gap: 4px !important;
  width: 100% !important;
  min-width: 100% !important;
  box-sizing: border-box !important;
}}
a.lr-nav-item,
section[data-testid="stSidebar"] a.lr-nav-item,
aside[data-testid="stSidebar"] a.lr-nav-item {{
  display: flex !important;
  align-items: center !important;
  justify-content: flex-start !important;
  width: 100% !important;
  min-width: 100% !important;
  max-width: 100% !important;
  box-sizing: border-box !important;
  margin: 0 !important;
  padding: 0.6rem 0.75rem !important;
  border-radius: 10px !important;
  border: 1px solid transparent !important;
  background: rgba(255,255,255,0.03) !important;
  color: #ffffff !important;
  font-size: 0.95rem !important;
  font-weight: 600 !important;
  line-height: 1.2 !important;
  text-decoration: none !important;
  white-space: nowrap !important;
  transition: background 0.15s ease, border-color 0.15s ease !important;
}}
a.lr-nav-item:hover {{
  background: rgba(59,130,246,0.24) !important;
  border-color: rgba(59,130,246,0.35) !important;
  color: #ffffff !important;
  text-decoration: none !important;
}}
a.lr-nav-item.is-active {{
  background: rgba(59,130,246,0.32) !important;
  border: 1px solid rgba(96,165,250,0.5) !important;
  color: #ffffff !important;
  font-weight: 700 !important;
  pointer-events: none !important;
}}
a.lr-nav-item .lr-nav-lbl {{ flex: 1 1 auto; color: #ffffff !important; }}
/* Logo — legacy class kept */
.lr-sidebar-logo-wrap {{
  display: flex !important;
  justify-content: center !important;
  width: 100% !important;
  margin: 4px 0 12px 0 !important;
}}
.lr-sidebar-logo-wrap img,
img.lr-sidebar-logo {{
  display: block !important;
  width: 180px !important;
  max-width: 180px !important;
  height: auto !important;
  margin: 0 auto !important;
  background: transparent !important;
  border: none !important;
  box-shadow: none !important;
}}
/* Nav buttons — full sidebar width, left-aligned labels */
section[data-testid="stSidebar"] .stButton,
aside[data-testid="stSidebar"] .stButton {{
  width: 100% !important;
  margin: 0 !important;
}}
section[data-testid="stSidebar"] .stButton > button,
aside[data-testid="stSidebar"] .stButton > button {{
  display: flex !important;
  align-items: center !important;
  justify-content: flex-start !important;
  width: 100% !important;
  margin: 3px 0 !important;
  padding: 0.55rem 0.65rem !important;
  border-radius: 10px !important;
  border: 1px solid transparent !important;
  background: transparent !important;
  color: #ffffff !important;
  font-size: 0.92rem !important;
  font-weight: 600 !important;
  box-shadow: none !important;
  white-space: nowrap !important;
  text-align: left !important;
  box-sizing: border-box !important;
  transform: none !important;
  transition: background 0.15s ease, border-color 0.15s ease !important;
}}
section[data-testid="stSidebar"] .stButton > button p,
aside[data-testid="stSidebar"] .stButton > button p,
section[data-testid="stSidebar"] .stButton > button div,
aside[data-testid="stSidebar"] .stButton > button div {{
  white-space: nowrap !important;
  text-align: left !important;
  margin: 0 !important;
}}
section[data-testid="stSidebar"] .stButton > button:hover:not(:disabled),
aside[data-testid="stSidebar"] .stButton > button:hover:not(:disabled) {{
  background: rgba(59,130,246,0.24) !important;
  border-color: rgba(59,130,246,0.35) !important;
  color: #ffffff !important;
  transform: none !important;
  box-shadow: none !important;
}}
section[data-testid="stSidebar"] .stButton > button[kind="primary"],
aside[data-testid="stSidebar"] .stButton > button[kind="primary"],
section[data-testid="stSidebar"] .stButton > button[data-testid="baseButton-primary"],
aside[data-testid="stSidebar"] .stButton > button[data-testid="baseButton-primary"],
section[data-testid="stSidebar"] .stButton > button:disabled,
aside[data-testid="stSidebar"] .stButton > button:disabled {{
  background: rgba(59,130,246,0.32) !important;
  border: 1px solid rgba(96,165,250,0.45) !important;
  color: #ffffff !important;
  opacity: 1 !important;
  cursor: default !important;
  font-weight: 700 !important;
  box-shadow: none !important;
  width: 100% !important;
}}
/* Keep page_link styles as fallback */
section[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"],
aside[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"],
section[data-testid="stSidebar"] a[href],
aside[data-testid="stSidebar"] a[href] {{
  display: flex !important;
  align-items: center !important;
  gap: 0.45rem !important;
  width: 100% !important;
  max-width: 100% !important;
  box-sizing: border-box !important;
  margin: 3px 0 !important;
  padding: 0.55rem 0.7rem !important;
  border-radius: 10px !important;
  border: 1px solid transparent !important;
  background: transparent !important;
  color: #ffffff !important;
  font-size: 0.92rem !important;
  font-weight: 600 !important;
  white-space: nowrap !important;
  overflow: visible !important;
  text-overflow: clip !important;
  text-decoration: none !important;
  transition: background 0.15s ease, border-color 0.15s ease !important;
}}
section[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"] p,
aside[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"] p,
section[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"] span,
aside[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"] span,
section[data-testid="stSidebar"] a[href] p,
aside[data-testid="stSidebar"] a[href] p,
section[data-testid="stSidebar"] a[href] span,
aside[data-testid="stSidebar"] a[href] span {{
  color: #ffffff !important;
  overflow: visible !important;
  text-overflow: clip !important;
  white-space: nowrap !important;
  flex: 1 1 auto !important;
  min-width: 0 !important;
}}
section[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"]:hover,
aside[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"]:hover,
section[data-testid="stSidebar"] a[href]:hover,
aside[data-testid="stSidebar"] a[href]:hover {{
  background: rgba(59,130,246,0.24) !important;
  border-color: rgba(59,130,246,0.35) !important;
  color: #ffffff !important;
}}
section[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"]:hover p,
aside[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"]:hover p,
section[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"]:hover span,
aside[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"]:hover span,
section[data-testid="stSidebar"] a[href]:hover p,
aside[data-testid="stSidebar"] a[href]:hover p,
section[data-testid="stSidebar"] a[href]:hover span,
aside[data-testid="stSidebar"] a[href]:hover span {{
  color: #ffffff !important;
}}
section[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"][aria-current="page"],
aside[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"][aria-current="page"],
section[data-testid="stSidebar"] a[aria-current="page"],
aside[data-testid="stSidebar"] a[aria-current="page"] {{
  background: rgba(59,130,246,0.34) !important;
  border: 1px solid rgba(96,165,250,0.65) !important;
  border-left: 4px solid {REACH["400"]} !important;
  color: #ffffff !important;
}}
section[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"][aria-current="page"] p,
aside[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"][aria-current="page"] p,
section[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"][aria-current="page"] span,
aside[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"][aria-current="page"] span,
section[data-testid="stSidebar"] a[aria-current="page"] p,
aside[data-testid="stSidebar"] a[aria-current="page"] p,
section[data-testid="stSidebar"] a[aria-current="page"] span,
aside[data-testid="stSidebar"] a[aria-current="page"] span {{
  color: #ffffff !important;
}}
[data-testid="stSidebarResizer"],
[data-testid="stSidebarResizeHandle"] {{
  display: none !important;
}}
/* Hide Streamlit sidebar chrome: collapse chevron + image fullscreen */
[data-testid="stSidebarCollapsedControl"],
[data-testid="collapsedControl"],
[data-testid="stSidebarCollapseButton"],
[data-testid="stSidebarCollapse"],
section[data-testid="stSidebar"] [data-testid="stElementToolbar"],
aside[data-testid="stSidebar"] [data-testid="stElementToolbar"],
section[data-testid="stSidebar"] [data-testid="StyledFullScreenButton"],
aside[data-testid="stSidebar"] [data-testid="StyledFullScreenButton"],
section[data-testid="stSidebar"] button[title="View fullscreen"],
aside[data-testid="stSidebar"] button[title="View fullscreen"],
section[data-testid="stSidebar"] button[title="Fullscreen"],
aside[data-testid="stSidebar"] button[title="Fullscreen"],
section[data-testid="stSidebar"] [class*="StyledFullScreenButton"],
aside[data-testid="stSidebar"] [class*="StyledFullScreenButton"] {{
  display: none !important;
  visibility: hidden !important;
  pointer-events: none !important;
  width: 0 !important;
  height: 0 !important;
  opacity: 0 !important;
}}
[data-testid="stSidebarHeader"] {{
  display: none !important;
  visibility: hidden !important;
  height: 0 !important;
  min-height: 0 !important;
  padding: 0 !important;
  margin: 0 !important;
}}
header[data-testid="stHeader"] {{
  background: transparent !important;
  border: none !important;
  box-shadow: none !important;
}}
.block-container {{ padding-top: 1rem !important; max-width: 1280px; padding-bottom: 3rem !important; }}

/* Home shortcut row */
.lr-home-row {{
  display: flex; align-items: center; gap: 10px;
  margin: 0 0 10px 0;
}}

/* Hide Streamlit chrome */
[data-testid="stToolbar"], [data-testid="stDecoration"], #MainMenu,
[data-testid="stStatusWidget"], footer {{
  display: none !important;
  visibility: hidden !important;
  height: 0 !important;
}}
.stDeployButton {{ display: none !important; }}

/* Framework nav unused (position=hidden) */
[data-testid="stSidebarNav"] {{
  display: none !important;
}}

/* Guaranteed in-page navigation strip */
.lr-nav-strip {{
  display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
  margin: 0 0 1rem 0; padding: 12px 14px;
  background: linear-gradient(135deg, rgba(15,23,42,0.98), rgba(2,6,23,0.98));
  border: 1px solid rgba(59,130,246,0.4);
  border-radius: 12px;
}}
.lr-nav-strip-title {{
  font-weight: 800; font-size: 0.85rem; color: {REACH["400"]};
  margin-right: 8px; letter-spacing: 0.02em;
}}

/* ── Typography ─────────────────────────────────────────────────────── */
h1, h2, h3 {{ font-weight: 800 !important; letter-spacing: -0.02em; color: #ffffff !important; }}

/* ── Buttons ─────────────────────────────────────────────────────────── */
.stButton > button, .stDownloadButton > button {{
  border-radius: 10px !important;
  font-weight: 600 !important;
  font-size: 0.88rem !important;
  transition: transform 0.15s ease, box-shadow 0.15s ease !important;
  border: 1px solid {SLATE["700"]} !important;
  padding: 0.55rem 1rem !important;
}}
.stButton > button:hover:not(:disabled), .stDownloadButton > button:hover:not(:disabled) {{
  transform: translateY(-1px);
  box-shadow: 0 6px 18px rgba(0,0,0,0.4);
}}
.stButton > button[kind="primary"], .stDownloadButton > button[kind="primary"] {{
  background: linear-gradient(135deg, {REACH["500"]}, {REACH["600"]}) !important;
  border: none !important;
  box-shadow: 0 2px 14px rgba(59,130,246,0.32) !important;
  color: white !important;
}}
.stButton > button:focus-visible, .stDownloadButton > button:focus-visible {{
  outline: 2px solid {REACH["400"]} !important;
  outline-offset: 2px;
}}

/* ── Inputs ─────────────────────────────────────────────────────────── */
.stTextInput input, .stNumberInput input,
.stSelectbox div[data-baseweb="select"] > div,
.stMultiSelect div[data-baseweb="select"] > div {{
  border-radius: 8px !important;
  border: 1px solid {SLATE["700"]} !important;
  background: {SLATE["800"]} !important;
  color: {SLATE["100"]} !important;
}}
.stTextInput label, .stSelectbox label, .stRadio label, .stCheckbox label,
.stNumberInput label {{ color: #ffffff !important; font-weight: 600 !important; font-size: 0.78rem !important; }}
.stRadio label, .stCheckbox label {{ color: #ffffff !important; }}

/* ── Metrics (fallback if sidebar_metrics not used) ─────────────────── */
[data-testid="stMetric"] {{
  background: {SLATE["800"]} !important;
  border: 1px solid {SLATE["700"]};
  border-radius: 12px;
  padding: 12px 14px;
}}
[data-testid="stMetricValue"] {{ color: #ffffff !important; font-weight: 800 !important; }}
[data-testid="stMetricLabel"] {{ color: #ffffff !important; font-size: 0.72rem !important; }}

/* ── Progress ───────────────────────────────────────────────────────── */
.stProgress > div > div > div > div {{
  background: linear-gradient(90deg, {REACH["500"]}, {SIGNAL["500"]}) !important;
  border-radius: 999px !important;
}}
.stProgress > div > div {{ background: {SLATE["800"]} !important; border-radius: 999px !important; height: 8px !important; }}

/* ── Alerts ─────────────────────────────────────────────────────────── */
[data-testid="stAlert"] {{
  border-radius: 12px !important;
  border: 1px solid {SLATE["700"]} !important;
  background: {SLATE["900"]} !important;
}}

/* ── Expander ───────────────────────────────────────────────────────── */
[data-testid="stExpander"] {{
  border-radius: 12px !important;
  border: 1px solid {SLATE["800"]} !important;
  background: {SLATE["900"]} !important;
  overflow: hidden;
}}
[data-testid="stExpander"] summary {{ font-weight: 600 !important; }}

/* ── Dividers ───────────────────────────────────────────────────────── */
hr {{ border-color: {SLATE["800"]} !important; }}

/* ── Scrollbars ─────────────────────────────────────────────────────── */
.lr-scroll::-webkit-scrollbar {{ width: 7px; height: 7px; }}
.lr-scroll::-webkit-scrollbar-track {{ background: {SLATE["950"]}; }}
.lr-scroll::-webkit-scrollbar-thumb {{ background: {SLATE["600"]}; border-radius: 6px; }}
.lr-scroll::-webkit-scrollbar-thumb:hover {{ background: {SLATE["500"]}; }}

/* ══ LocReach custom components ═══════════════════════════════════════ */

/* App top brand strip (injected above content) */
.lr-appbar {{
  display: flex; align-items: center; justify-content: space-between;
  margin: -0.5rem 0 1.25rem; padding: 14px 20px;
  background: linear-gradient(135deg, rgba(15,23,42,0.95), rgba(2,6,23,0.98));
  border: 1px solid {SLATE["800"]}; border-radius: 16px;
  box-shadow: 0 12px 40px rgba(0,0,0,0.35);
}}
.lr-appbar-left {{ display: flex; align-items: center; gap: 12px; }}
.lr-logo {{
  display:flex; align-items:center; justify-content:center;
  width: 40px; height: 40px; border-radius: 11px; font-weight: 800; font-size: 0.85rem;
  color: white; background: linear-gradient(135deg, {REACH["500"]}, {REACH["600"]});
  box-shadow: 0 4px 14px rgba(59,130,246,0.35);
}}
.lr-appname {{ font-size: 1.15rem; font-weight: 800; color: {SLATE["100"]}; letter-spacing: -0.02em; }}
.lr-tagline {{ font-size: 0.72rem; color: {SLATE["500"]}; margin-top: 1px; }}
.lr-appbar-right {{ font-size: 0.72rem; color: {SLATE["500"]}; font-weight: 600; letter-spacing: 0.04em; text-transform: uppercase; }}

/* Main-area horizontal nav fallback */
div[data-testid="stHorizontalBlock"]:has(a[href*="0_Home"]) a,
div[data-testid="stHorizontalBlock"]:has(a[href*="1_Domains"]) a {{
  font-weight: 600 !important;
  border-radius: 10px !important;
}}

/* Sidebar logo */
.lr-sidebar-logo {{
  display: block !important;
  width: 180px !important;
  max-width: 180px !important;
  height: auto !important;
  margin: 0 auto !important;
  background: transparent !important;
  border: none !important;
  box-shadow: none !important;
}}
section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"],
aside[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] {{
  background: transparent !important;
}}

/* Sidebar brand (text fallback) */
.lr-sb-brand {{
  display:flex; align-items:center; gap:10px; margin-bottom: 16px;
  padding: 12px; border-radius: 12px;
  background: linear-gradient(135deg, rgba(59,130,246,0.12), rgba(59,130,246,0.02));
  border: 1px solid rgba(59,130,246,0.2);
}}
.lr-sb-brand-icon {{
  width:36px; height:36px; border-radius:9px; display:flex; align-items:center; justify-content:center;
  font-weight:800; font-size:0.75rem; color:white;
  background: linear-gradient(135deg, {REACH["500"]}, {REACH["600"]});
}}
.lr-sb-brand-title {{ font-weight:800; font-size:0.95rem; color:{SLATE["100"]}; }}
.lr-sb-brand-sub {{ font-size:0.68rem; color:{SLATE["500"]}; }}

/* Sidebar metric grid */
.lr-sb-metrics {{ display:grid; grid-template-columns:1fr 1fr; gap:8px; margin: 12px 0; }}
.lr-sb-metric {{
  background:{SLATE["800"]}; border:1px solid {SLATE["700"]}; border-radius:10px;
  padding:10px 12px; text-align:center;
}}
.lr-sb-metric-val {{ font-size:1.25rem; font-weight:800; color:{REACH["400"]}; line-height:1.1; }}
.lr-sb-metric-lbl {{ font-size:0.62rem; color:{SLATE["500"]}; text-transform:uppercase; letter-spacing:0.04em; margin-top:4px; font-weight:700; }}

/* Page header */
.lr-header {{ display:flex; align-items:center; gap:14px; margin-bottom: 4px; }}
.lr-header-icon {{
  display:flex; align-items:center; justify-content:center;
  width:48px; height:48px; border-radius:14px; font-size:22px; flex-shrink:0;
  background: linear-gradient(135deg, {REACH["500"]}, {REACH["600"]});
  box-shadow: 0 4px 18px rgba(59,130,246,0.32);
}}
.lr-header-title {{ font-size:1.55rem; font-weight:800; color:{SLATE["100"]}; margin:0; letter-spacing:-0.02em; line-height:1.2; }}
.lr-header-sub {{ font-size:0.84rem; color:{SLATE["500"]}; margin-top:3px; }}

/* Step indicator */
.lr-steps {{ display:flex; gap:10px; margin: 18px 0 22px; }}
.lr-step {{
  flex:1; border-radius:12px; padding:12px 14px; text-align:center;
  border:1px solid {SLATE["800"]}; background:{SLATE["900"]};
}}
.lr-step-active {{
  border-color:{REACH["500"]};
  background: linear-gradient(135deg, rgba(59,130,246,0.18), rgba(59,130,246,0.04));
  box-shadow: 0 0 0 1px rgba(59,130,246,0.3), 0 4px 16px rgba(59,130,246,0.1);
}}
.lr-step-num {{ font-weight:800; font-size:0.72rem; color:{SLATE["500"]}; letter-spacing:0.06em; }}
.lr-step-active .lr-step-num {{ color:{REACH["400"]}; }}
.lr-step-label {{ font-size:0.78rem; color:{SLATE["400"]}; margin-top:3px; font-weight:600; }}
.lr-step-active .lr-step-label {{ color:{SLATE["200"]}; }}

/* Stat cards */
.lr-stats {{ display:flex; gap:12px; flex-wrap:wrap; margin-bottom:20px; }}
.lr-stat {{
  flex:1; min-width:128px; background:{SLATE["900"]}; border:1px solid {SLATE["800"]};
  border-radius:14px; padding:16px 18px; text-align:center;
  box-shadow: 0 4px 14px rgba(0,0,0,0.2);
}}
.lr-stat-val {{ font-size:1.85rem; font-weight:800; line-height:1.15; }}
.lr-stat-lbl {{ font-size:0.68rem; color:{SLATE["500"]}; margin-top:5px; text-transform:uppercase; letter-spacing:0.05em; font-weight:700; }}
.lr-c-reach     {{ color:{REACH["400"]}; }}
.lr-c-signal    {{ color:{SIGNAL["400"]}; }}
.lr-c-qualified {{ color:{QUALIFIED["400"]}; }}
.lr-c-pipeline  {{ color:{PIPELINE["400"]}; }}
.lr-c-slate     {{ color:{SLATE["400"]}; }}
.lr-c-red       {{ color:{RED["400"]}; }}

/* Section headers */
.lr-section {{
  display:flex; align-items:center; gap:8px; margin: 24px 0 12px;
  font-weight:700; font-size:0.92rem; color:{SLATE["100"]};
  padding-bottom:10px; border-bottom:1px solid {SLATE["800"]};
}}

/* Control panel strip */
.lr-controls {{
  display:flex; flex-wrap:wrap; gap:10px; align-items:center;
  padding: 14px 16px; margin-bottom: 16px;
  background: {SLATE["900"]}; border: 1px solid {SLATE["800"]};
  border-radius: 14px;
}}

/* Badges */
.lr-badge {{
  display:inline-flex; align-items:center; padding:3px 10px;
  border-radius:999px; font-size:0.72rem; font-weight:700; white-space:nowrap;
}}
.lr-badge-strong   {{ background:rgba(16,185,129,0.15); color:{QUALIFIED["400"]}; border:1px solid rgba(16,185,129,0.3); }}
.lr-badge-possible {{ background:rgba(249,115,22,0.15); color:{PIPELINE["400"]}; border:1px solid rgba(249,115,22,0.3); }}
.lr-badge-weak     {{ background:rgba(100,116,139,0.15); color:{SLATE["400"]}; border:1px solid rgba(100,116,139,0.3); }}
.lr-badge-lsp      {{ background:rgba(249,115,22,0.15); color:{PIPELINE["400"]}; border:1px solid rgba(249,115,22,0.3); }}
.lr-badge-client   {{ background:rgba(168,85,247,0.15); color:{SIGNAL["400"]}; border:1px solid rgba(168,85,247,0.3); }}
.lr-badge-neutral  {{ background:rgba(100,116,139,0.15); color:{SLATE["400"]}; border:1px solid rgba(100,116,139,0.3); }}
.lr-badge-source   {{ background:rgba(59,130,246,0.15); color:{REACH["400"]}; border:1px solid rgba(59,130,246,0.3); }}
.lr-badge-danger   {{ background:rgba(239,68,68,0.15); color:{RED["400"]}; border:1px solid rgba(239,68,68,0.3); }}

/* Tables */
.lr-table-wrap {{ overflow:auto; border-radius:12px; border:1px solid {SLATE["800"]}; background:{SLATE["900"]}; box-shadow: 0 4px 16px rgba(0,0,0,0.2); }}
.lr-table {{ width:100%; border-collapse:collapse; font-size:0.84rem; }}
.lr-table thead th {{
  background:{SLATE["800"]}; color:{SLATE["300"]}; font-weight:700; text-align:left;
  padding:11px 14px; position:sticky; top:0; font-size:0.7rem; text-transform:uppercase;
  letter-spacing:0.04em; border-bottom:1px solid {SLATE["700"]}; z-index:1;
}}
.lr-table tbody td {{ padding:10px 14px; border-bottom:1px solid {SLATE["800"]}; color:{SLATE["300"]}; }}
.lr-table tbody tr:hover {{ background:rgba(148,163,184,0.06); }}
.lr-table tbody tr:last-child td {{ border-bottom:none; }}
.lr-cell-strong {{ color:{SLATE["100"]}; font-weight:600; }}
.lr-link {{ color:{SIGNAL["400"]}; text-decoration:none; }}
.lr-link:hover {{ text-decoration:underline; }}
.lr-muted {{ color:{SLATE["600"]}; }}
.lr-mono {{ font-family: 'SFMono-Regular', Menlo, Consolas, monospace; color:{QUALIFIED["400"]}; }}

/* Pipeline step buttons (same Streamlit button behaviour as Database) */
.lr-hero {{
  margin-bottom: 8px; padding: 24px 26px; border-radius: 18px;
  background: linear-gradient(135deg, rgba(59,130,246,0.14), rgba(168,85,247,0.06));
  border: 1px solid rgba(59,130,246,0.25);
}}
.lr-hero-title {{ font-size:1.65rem; font-weight:800; color:{SLATE["100"]}; margin:0 0 6px; }}
.lr-hero-sub {{ font-size:0.9rem; color:{SLATE["400"]}; margin:0; line-height:1.5; }}
</style>
"""


_SIDEBAR_NAV = (
    ("0_Home.py",     "home",      "Home"),
    ("1_Domains.py",  "domains",   "Step 1"),
    ("2_People.py",   "people",    "Step 2"),
    ("3_Emails.py",   "emails",    "Step 3"),
    ("4_Database.py", "database",  "Database"),
)


def render_app_sidebar() -> None:
    """Custom HTML sidebar: centered logo + full-width nav links."""
    with st.sidebar:
        sidebar_brand()


def inject_theme(*, show_home_button: bool = True) -> None:
    """Inject shared CSS, sidebar nav, and optional Home shortcut."""
    # st.html — not st.markdown: Streamlit 1.57 was escaping large HTML/CSS as text,
    # so our sidebar width rules never applied and nav rendered as raw markup.
    st.html(_THEME_CSS)
    render_app_sidebar()
    # Do not mount components.html here — Step 1 auto-reruns ~1.5s and that
    # remount spam previously flooded logs and competed with the heartbeat iframe.
    if show_home_button:
        home_button()


def home_button() -> None:
    """Always-visible shortcut back to Home (every page)."""
    st.page_link(
        "pages/0_Home.py",
        label="← Back to Home",
        icon="🏠",
    )


def pipeline_nav_bar() -> None:
    """Always-visible horizontal page links in the main content area."""
    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        st.page_link("pages/0_Home.py",     label="Home",             icon="🏠", use_container_width=True)
    with c2:
        st.page_link("pages/1_Domains.py",  label="Step 1 · Domains", icon="🔍", use_container_width=True)
    with c3:
        st.page_link("pages/2_People.py",   label="Step 2 · People",  icon="👥", use_container_width=True)
    with c4:
        st.page_link("pages/3_Emails.py",   label="Step 3 · Emails",  icon="📧", use_container_width=True)
    with c5:
        st.page_link("pages/4_Database.py", label="Database",         icon="🗄️", use_container_width=True)


def sidebar_brand(step_icon: str = "LR", step_label: str = "Navigate the pipeline") -> None:
    """Single HTML block: centered logo + full-width nav (no st.button)."""
    current = _current_page_filename()
    logo_path = Path(__file__).resolve().parent / "assets" / "locreach_logo.png"
    if logo_path.is_file():
        b64 = base64.b64encode(logo_path.read_bytes()).decode("ascii")
        brand = (
            f'<div class="lr-side-brand" style="display:flex;justify-content:center;width:100%;margin:2px 0 14px 0;">'
            f'<img src="data:image/png;base64,{b64}" alt="LocReach" width="140" '
            f'style="width:140px;max-width:100%;height:auto;display:block;margin:0 auto;" />'
            f"</div>"
        )
    else:
        brand = (
            f'<div class="lr-sb-brand">'
            f'<div class="lr-sb-brand-icon">{_html.escape(step_icon)}</div>'
            f'<div><div class="lr-sb-brand-title">LocReach</div>'
            f'<div class="lr-sb-brand-sub">{_html.escape(step_label)}</div></div>'
            f"</div>"
        )

    links = []
    for fname, url_path, label in _SIDEBAR_NAV:
        active = " is-active" if fname == current else ""
        links.append(
            f'<a class="lr-nav-item{active}" href="/{url_path}" '
            f'style="display:flex;align-items:center;width:100%;'
            f'box-sizing:border-box;padding:0.6rem 0.75rem;border-radius:10px;'
            f'text-decoration:none;color:#fff;font-weight:600;">'
            f'<span class="lr-nav-lbl">{_html.escape(label)}</span></a>'
        )

    st.html(
        f'<div class="lr-side" style="display:block;width:100%;min-width:100%;box-sizing:border-box;">'
        f'{brand}'
        f'<nav class="lr-side-nav" style="display:flex;flex-direction:column;gap:4px;width:100%;">'
        f'{"".join(links)}</nav></div>'
    )


def sidebar_metrics(items) -> None:
    """items: iterable of (label, value) — 2-column metric grid for sidebar."""
    cells = ""
    for label, value in items:
        cells += (
            f'<div class="lr-sb-metric">'
            f'<div class="lr-sb-metric-val">{_html.escape(str(value))}</div>'
            f'<div class="lr-sb-metric-lbl">{_html.escape(label)}</div></div>'
        )
    st.markdown(f'<div class="lr-sb-metrics">{cells}</div>', unsafe_allow_html=True)


def page_header(icon: str, title: str, subtitle: str = "") -> None:
    sub_html = f'<p class="lr-header-sub">{_html.escape(subtitle)}</p>' if subtitle else ""
    st.markdown(
        f'<div class="lr-header">'
        f'<div class="lr-header-icon">{icon}</div>'
        f'<div><p class="lr-header-title">{_html.escape(title)}</p>{sub_html}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


def step_indicator(active_step: int) -> None:
    """Show only the current pipeline step (hide the other steps)."""
    steps = {1: "Find & Qualify", 2: "Find People", 3: "Find Emails"}
    label = steps.get(active_step, f"Step {active_step}")
    st.markdown(
        f'<div class="lr-steps">'
        f'<div class="lr-step lr-step-active">'
        f'<div class="lr-step-num">STEP {active_step}</div>'
        f'<div class="lr-step-label">{_html.escape(label)}</div></div>'
        f'</div>',
        unsafe_allow_html=True,
    )


def stat_cards(items) -> None:
    cells = ""
    for label, value, color in items:
        cells += (
            f'<div class="lr-stat"><div class="lr-stat-val lr-c-{color}">{value}</div>'
            f'<div class="lr-stat-lbl">{_html.escape(label)}</div></div>'
        )
    st.markdown(f'<div class="lr-stats">{cells}</div>', unsafe_allow_html=True)


def section_label(icon: str, title: str) -> None:
    st.markdown(
        f'<div class="lr-section"><span>{icon}</span> {_html.escape(title)}</div>',
        unsafe_allow_html=True,
    )


def render_table(headers, rows_html: str, max_height: str = "480px") -> None:
    ths = "".join(f"<th>{_html.escape(h)}</th>" for h in headers)
    st.markdown(
        f'<div class="lr-table-wrap lr-scroll" style="max-height:{max_height}">'
        f'<table class="lr-table"><thead><tr>{ths}</tr></thead>'
        f'<tbody>{rows_html}</tbody></table></div>',
        unsafe_allow_html=True,
    )


def tier_badge(tier: str) -> str:
    labels = {"strong": "Strong", "possible": "Possible", "weak": "Weak"}
    css = {"strong": "lr-badge-strong", "possible": "lr-badge-possible", "weak": "lr-badge-weak"}
    if tier not in labels:
        return '<span class="lr-muted">—</span>'
    return f'<span class="lr-badge {css[tier]}">{labels[tier]}</span>'


def type_badge(company_type: str) -> str:
    ct = (company_type or "").lower()
    if ct == "lsp":
        return '<span class="lr-badge lr-badge-lsp">LSP</span>'
    if ct == "client":
        return '<span class="lr-badge lr-badge-client">Client</span>'
    return '<span class="lr-muted">—</span>'


def source_badge(label: str) -> str:
    if not label:
        return '<span class="lr-muted">—</span>'
    return f'<span class="lr-badge lr-badge-source">{_html.escape(label)}</span>'


def link_icon(url: str) -> str:
    if not url:
        return '<span class="lr-muted">—</span>'
    safe = _html.escape(url, quote=True)
    return f'<a href="{safe}" target="_blank" class="lr-link">↗</a>'


def _current_page_filename() -> str:
    """Best-effort current page script name (e.g. '1_Domains.py')."""
    known = {
        "0_Home.py",
        "1_Domains.py",
        "2_People.py",
        "3_Emails.py",
        "4_Database.py",
    }
    path_map = {
        "home": "0_Home.py",
        "domains": "1_Domains.py",
        "people": "2_People.py",
        "emails": "3_Emails.py",
        "database": "4_Database.py",
    }
    import inspect
    # Prefer pages/* frame — most reliable while a page script is running
    for fr in inspect.stack():
        f = fr.filename.replace("\\", "/")
        if "/pages/" in f and f.endswith(".py"):
            name = f.rsplit("/", 1)[-1]
            if name in known:
                try:
                    st.session_state["_lr_nav_page"] = name
                except Exception:
                    pass
                return name
    # URL path from custom sidebar links (/home, /domains, ...)
    try:
        uri = ""
        try:
            uri = (st.context.url or "") if hasattr(st, "context") else ""
        except Exception:
            uri = ""
        path = ""
        if uri:
            from urllib.parse import urlparse
            path = (urlparse(uri).path or "").strip("/").split("/")[-1].lower()
        if path in path_map:
            return path_map[path]
    except Exception:
        pass
    try:
        stamped = st.session_state.get("_lr_nav_page", "")
        if stamped in known:
            return stamped
    except Exception:
        pass
    try:
        from streamlit.runtime.scriptrunner_utils.script_run_context import (
            get_script_run_ctx,
        )
        ctx = get_script_run_ctx()
        if ctx is not None:
            path = getattr(ctx, "main_script_path", None) or ""
            if path:
                name = str(path).replace("\\", "/").rsplit("/", 1)[-1]
                if name in known:
                    return name
                if name in ("Domain_Discovery.py", "streamlit_app.py", "app.py"):
                    return "0_Home.py"
    except Exception:
        pass
    return "0_Home.py"


def sidebar_pipeline_nav() -> None:
    """Deprecated — nav is rendered inside sidebar_brand() as custom HTML."""
    return


def pipeline_cards(steps) -> None:
    """
    Pipeline step buttons — same hover/click behaviour as Open Database view
    (st.button + st.switch_page). No HTML links, no long descriptions.
    """
    cols = st.columns(max(1, len(steps)))
    for col, step in zip(cols, steps):
        with col:
            page = step.get("page")
            icon = step.get("icon", "")
            num = step["num"]
            title = step["title"]
            label = f"{icon} Step {num} · {title}"
            if page:
                if st.button(
                    label,
                    key=f"pipeline_step_{num}",
                    use_container_width=True,
                ):
                    st.switch_page(page)
            else:
                st.markdown(f"**{label}**")
