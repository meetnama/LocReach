"""
ui_theme.py — Shared professional design system for LocReach Streamlit pages.
"""
import html as _html

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

_THEME_CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

/* ── Base / app shell ─────────────────────────────────────────────────── */
html, body, [class*="css"], .stApp {{
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif !important;
  overflow-x: hidden !important;
}}
.stApp {{
  background: radial-gradient(ellipse 120% 80% at 10% -10%, #0b1b34 0%, {SLATE["950"]} 42%, #010409 100%) fixed !important;
}}
/* Stable layout with branded sidebar */
[data-testid="stAppViewContainer"],
[data-testid="stAppViewContainer"] > section,
[data-testid="stMain"],
section.main {{
  transition: none !important;
  animation: none !important;
}}
section[data-testid="stSidebar"] {{
  display: flex !important;
  visibility: visible !important;
  pointer-events: auto !important;
  background: linear-gradient(180deg, {SLATE["900"]} 0%, {SLATE["950"]} 100%) !important;
  border-right: 1px solid rgba(59,130,246,0.25) !important;
  min-width: 15rem !important;
}}
section[data-testid="stSidebar"] > div {{
  background: transparent !important;
}}
[data-testid="stSidebarCollapsedControl"],
[data-testid="collapsedControl"] {{
  display: flex !important;
  visibility: visible !important;
  pointer-events: auto !important;
  color: {SLATE["300"]} !important;
}}
[data-testid="stSidebarHeader"] {{
  display: flex !important;
  visibility: visible !important;
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

/* ── Top navigation (st.navigation position=top) ─────────────────────── */
[data-testid="stSidebarNav"] {{
  display: flex !important;
  visibility: visible !important;
  background: linear-gradient(180deg, {SLATE["900"]}, {SLATE["950"]}) !important;
  border-bottom: 2px solid rgba(59,130,246,0.35) !important;
  padding: 0 1.5rem !important;
  box-shadow: 0 6px 24px rgba(0,0,0,0.4) !important;
  position: sticky !important;
  top: 0 !important;
  z-index: 999 !important;
  min-height: 3rem !important;
  transition: none !important;
}}
[data-testid="stSidebarNav"] ul {{
  gap: 4px !important;
  padding: 8px 0 !important;
}}
[data-testid="stSidebarNav"] li {{
  border-radius: 10px !important;
  overflow: hidden;
}}
[data-testid="stSidebarNav"] a {{
  border-radius: 10px !important;
  font-weight: 600 !important;
  font-size: 0.84rem !important;
  color: {SLATE["400"]} !important;
  padding: 10px 18px !important;
}}
[data-testid="stSidebarNav"] a:hover {{
  background: {SLATE["800"]} !important;
  color: {SLATE["100"]} !important;
}}
[data-testid="stSidebarNav"] a[aria-current="page"] {{
  background: linear-gradient(135deg, rgba(59,130,246,0.22), rgba(59,130,246,0.06)) !important;
  color: {REACH["400"]} !important;
  box-shadow: inset 0 0 0 1px rgba(59,130,246,0.35) !important;
}}

/* ── Typography ─────────────────────────────────────────────────────── */
h1, h2, h3 {{ font-weight: 800 !important; letter-spacing: -0.02em; color: {SLATE["100"]} !important; }}

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
.stNumberInput label {{ color: {SLATE["400"]} !important; font-weight: 600 !important; font-size: 0.78rem !important; }}
.stRadio label, .stCheckbox label {{ color: {SLATE["300"]} !important; }}

/* ── Metrics (fallback if sidebar_metrics not used) ─────────────────── */
[data-testid="stMetric"] {{
  background: {SLATE["800"]} !important;
  border: 1px solid {SLATE["700"]};
  border-radius: 12px;
  padding: 12px 14px;
}}
[data-testid="stMetricValue"] {{ color: {REACH["400"]} !important; font-weight: 800 !important; }}
[data-testid="stMetricLabel"] {{ color: {SLATE["500"]} !important; font-size: 0.72rem !important; }}

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

/* Sidebar brand */
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


def inject_theme(*, show_home_button: bool = True) -> None:
    """Inject shared CSS, sidebar nav, app bar, and optional Home shortcut."""
    st.markdown(_THEME_CSS, unsafe_allow_html=True)
    _render_sidebar_nav()
    st.markdown(
        '<div class="lr-appbar">'
        '<div class="lr-appbar-left">'
        '<div class="lr-logo">LR</div>'
        '<div><div class="lr-appname">LocReach</div>'
        '<div class="lr-tagline">B2B Lead Generation · Localization Industry</div></div>'
        '</div>'
        '<div class="lr-appbar-right">3-Step Pipeline</div>'
        '</div>',
        unsafe_allow_html=True,
    )
    if show_home_button:
        home_button()


def home_button() -> None:
    """Always-visible shortcut back to Home (every page)."""
    st.page_link(
        "pages/0_Home.py",
        label="← Back to Home",
        icon="🏠",
    )


def _render_sidebar_nav() -> None:
    """Left sidebar: brand + links to every app page."""
    with st.sidebar:
        sidebar_brand("LR", "Navigate the pipeline")
        sidebar_pipeline_nav()


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


def sidebar_brand(step_icon: str, step_label: str) -> None:
    """Branded sidebar header."""
    st.markdown(
        f'<div class="lr-sb-brand">'
        f'<div class="lr-sb-brand-icon">{_html.escape(step_icon)}</div>'
        f'<div><div class="lr-sb-brand-title">LocReach</div>'
        f'<div class="lr-sb-brand-sub">{_html.escape(step_label)}</div></div>'
        f'</div>',
        unsafe_allow_html=True,
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


def sidebar_pipeline_nav() -> None:
    """Quick links to Home, each pipeline step, and Database."""
    st.markdown("**Navigate**")
    st.page_link("pages/0_Home.py",     label="Home",              icon="🏠", use_container_width=True)
    st.page_link("pages/1_Domains.py",  label="Step 1 · Domains",  icon="🔍", use_container_width=True)
    st.page_link("pages/2_People.py",   label="Step 2 · People",   icon="👥", use_container_width=True)
    st.page_link("pages/3_Emails.py",   label="Step 3 · Emails",   icon="📧", use_container_width=True)
    st.page_link("pages/4_Database.py", label="Database",          icon="🗄️", use_container_width=True)
    st.markdown("---")
    st.caption("Use the top tabs or this sidebar to move between pages.")


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
