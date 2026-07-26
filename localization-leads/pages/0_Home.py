"""
pages/0_Home.py — LocReach Home / Pipeline Dashboard.

Master landing page with pipeline overview and live DB stats.
"""
import os
import sqlite3

import streamlit as st
import streamlit.components.v1 as components

from db import (
    db_init, db_count_domains, db_count_leads, db_load_people_without_email,
)
from ui_theme import inject_theme
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
    height=150,
    scrolling=False,
)
