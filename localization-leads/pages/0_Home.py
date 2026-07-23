"""
pages/0_Home.py — LocReach Home / Pipeline Dashboard.

Master landing page with pipeline overview, live DB stats, and navigation
to each of the three workflow steps.
"""
import os
import sqlite3

import streamlit as st
import streamlit.components.v1 as components

from db import (
    db_init, db_count_domains, db_count_leads, db_load_people_without_email,
    db_wipe_all,
)
from ui_theme import (
    inject_theme, stat_cards, section_label, pipeline_cards,
)
from template_render import render_pipeline_snapshot

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH  = os.path.join(BASE_DIR, "leads.db")

inject_theme(show_home_button=False)

_conn = sqlite3.connect(DB_PATH)
db_init(_conn)
_domain_counts = db_count_domains(_conn)
_qualified     = _domain_counts.get("qualified", 0)
_people_total  = _conn.execute("SELECT COUNT(*) FROM people").fetchone()[0]
_people_todo   = len(db_load_people_without_email(_conn))
_people_done   = _people_total - _people_todo
_leads         = db_count_leads(_conn)
_conn.close()

# ── Hero ──────────────────────────────────────────────────────────────────────
st.markdown(
    '<div class="lr-hero">'
    '<p class="lr-hero-title">Welcome to LocReach</p>'
    '<p class="lr-hero-sub">Your 3-step B2B lead pipeline for the localization industry. '
    'Find qualified companies, discover decision-makers, and verify contact emails.</p>'
    '</div>',
    unsafe_allow_html=True,
)

# Post-reset confirmation (set just before st.rerun in the Danger Zone below)
_reset_msg = st.session_state.pop("reset_done_msg", None)
if _reset_msg:
    st.success(
        f"Database reset — removed {sum(_reset_msg.values())} rows "
        f"(domains {_reset_msg.get('domains', 0)}, "
        f"people {_reset_msg.get('people', 0)}, "
        f"leads {_reset_msg.get('leads', 0)}, "
        f"blocked {_reset_msg.get('blocked_domains', 0)})."
    )

stat_cards([
    ("Qualified Domains", _qualified,                    "qualified"),
    ("People Found",      _people_total,                 "signal"),
    ("Awaiting Email",    _people_todo,                  "pipeline"),
    ("Verified Leads",    _leads,                        "reach"),
])

# ── Live pipeline snapshot (read-only, Jinja-rendered) ──────────────────────────
# Rendered from templates/_pipeline_snapshot_embed.html and embedded as a static
# iframe — same Jinja→Streamlit bridge used by the three step pages.
components.html(
    render_pipeline_snapshot(
        qualified=_qualified,
        people_total=_people_total,
        people_done=_people_done,
        people_todo=_people_todo,
        leads=_leads,
    ),
    height=210,
    scrolling=False,
)

section_label("🗺️", "Pipeline Steps")

pipeline_cards([
    {
        "num": 1, "icon": "🔍",
        "title": "Find & Qualify Domains",
        "page": "pages/1_Domains.py",
    },
    {
        "num": 2, "icon": "👥",
        "title": "Find People",
        "page": "pages/2_People.py",
    },
    {
        "num": 3, "icon": "📧",
        "title": "Find Emails",
        "page": "pages/3_Emails.py",
    },
])



# ── Database browser ────────────────────────────────────────────────────────────
section_label("🗄️", "Database")
_db_col1, _db_col2 = st.columns([2, 4])
with _db_col1:
    if st.button(
        "🗄️ Open Database view",
        use_container_width=True,
        key="home_open_database",
    ):
        st.switch_page("pages/4_Database.py")
st.caption(
    "Browse **everything** in `leads.db` (domains, people, leads, blocked) "
    "with search and filters. Per-run Excel downloads stay on each Step page."
)

# ── Full database Excel export (by category) ───────────────────────────────────
section_label("📥", "Export full database")
_ex1, _ex2 = st.columns([2, 4])
with _ex1:
    try:
        from export_excel import build_excel_bytes
        from datetime import datetime as _dt
        _xlsx = build_excel_bytes(DB_PATH)
        st.download_button(
            label="📊 Export full database (Excel)",
            data=_xlsx,
            file_name=f"locreach_full_db_{_dt.now().strftime('%Y%m%d_%H%M')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
            type="primary",
            key="home_export_full_db",
        )
    except Exception as _e:
        st.error(f"Excel export failed: {_e}")
st.caption(
    "One workbook with sheets by category: **Qualified**, **Rejected**, **Failed**, "
    "**Unreachable**, **Discovered**, plus **People**, **Leads**, **Blocked**, and **Summary**."
)

# ── Danger zone — reset database ────────────────────────────────────────────────
section_label("⚠️", "Danger Zone")
with st.expander("Reset database", expanded=False):
    st.markdown(
        "Permanently delete **all** qualified domains, people, leads, and the "
        "blocked-domain list from `leads.db`. The pipeline starts empty again. "
        "**This cannot be undone.**"
    )
    _confirm_reset = st.checkbox(
        "I understand this erases all pipeline data",
        key="reset_confirm",
    )
    if st.button(
        "🗑️ Reset database",
        type="primary",
        disabled=not _confirm_reset,
        help="Wipes every pipeline table. Requires the confirmation checkbox.",
    ):
        _wc = sqlite3.connect(DB_PATH)
        db_init(_wc)
        _counts = db_wipe_all(_wc)
        _wc.close()
        st.session_state["reset_done_msg"] = _counts
        st.rerun()
