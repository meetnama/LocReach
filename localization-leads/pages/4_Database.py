"""
pages/4_Database.py — Browse all leads.db records with search & filters.

In-app view of domains, people, leads, and blocked domains, plus full-DB
Excel export and database reset.
"""
from __future__ import annotations

import os
import sqlite3
from datetime import datetime as _dt

import pandas as pd
import streamlit as st

from db import db_init, db_count_domains, db_count_leads, db_wipe_all
from ui_theme import inject_theme, page_header, section_label, stat_cards

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "leads.db")

inject_theme()
page_header(
    "🗄️",
    "Database",
    "Browse every record in leads.db — search and filter without exporting.",
)

_reset_msg = st.session_state.pop("reset_done_msg", None)
if _reset_msg:
    st.success(
        f"Database reset — removed {sum(_reset_msg.values())} rows "
        f"(domains {_reset_msg.get('domains', 0)}, "
        f"people {_reset_msg.get('people', 0)}, "
        f"leads {_reset_msg.get('leads', 0)}, "
        f"blocked {_reset_msg.get('blocked_domains', 0)})."
    )


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(DB_PATH)
    db_init(c)
    return c


def _distinct(conn: sqlite3.Connection, table: str, col: str) -> list[str]:
    rows = conn.execute(
        f"SELECT DISTINCT {col} FROM {table} "
        f"WHERE {col} IS NOT NULL AND TRIM({col}) != '' "
        f"ORDER BY {col}"
    ).fetchall()
    return [r[0] for r in rows]


def _filter_df(df: pd.DataFrame, query: str, columns: list[str]) -> pd.DataFrame:
    q = (query or "").strip().lower()
    if not q or df.empty:
        return df
    mask = pd.Series(False, index=df.index)
    for col in columns:
        if col in df.columns:
            mask = mask | df[col].fillna("").astype(str).str.lower().str.contains(
                q, regex=False
            )
    return df[mask]


# ── Counts ────────────────────────────────────────────────────────────────────
with _conn() as conn:
    _domain_counts = db_count_domains(conn)
    _domains_n = conn.execute("SELECT COUNT(*) FROM domains").fetchone()[0]
    _people_n = conn.execute("SELECT COUNT(*) FROM people").fetchone()[0]
    _leads_n = db_count_leads(conn)
    _blocked_n = conn.execute("SELECT COUNT(*) FROM blocked_domains").fetchone()[0]

stat_cards([
    ("Domains", _domains_n, "signal"),
    ("Qualified", _domain_counts.get("qualified", 0), "qualified"),
    ("People", _people_n, "pipeline"),
    ("Leads", _leads_n, "reach"),
])

tab_domains, tab_people, tab_leads, tab_blocked = st.tabs(
    [
        f"Domains ({_domains_n})",
        f"People ({_people_n})",
        f"Leads ({_leads_n})",
        f"Blocked ({_blocked_n})",
    ]
)

# ══════════════════════════════════════════════════════════════════════════════
# DOMAINS
# ══════════════════════════════════════════════════════════════════════════════
with tab_domains:
    section_label("🔍", "Domains")
    with _conn() as conn:
        industries = ["All"] + _distinct(conn, "domains", "industry")
        countries = ["All"] + _distinct(conn, "domains", "country")
        statuses = ["All"] + _distinct(conn, "domains", "status")
        tiers = ["All"] + _distinct(conn, "domains", "score_tier")

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        f_status = st.selectbox("Status", statuses, key="dbv_dom_status")
    with c2:
        f_industry = st.selectbox("Industry", industries, key="dbv_dom_industry")
    with c3:
        f_country = st.selectbox("Country", countries, key="dbv_dom_country")
    with c4:
        f_tier = st.selectbox("Score tier", tiers, key="dbv_dom_tier")
    f_search = st.text_input(
        "Search domains",
        placeholder="domain, company, reasons…",
        key="dbv_dom_q",
    )

    sql = """
        SELECT domain, company_name, score, score_tier, industry, country,
               linkedin_url, score_reasons
          FROM domains WHERE 1=1
    """
    args: list = []
    if f_status != "All":
        sql += " AND status=?"; args.append(f_status)
    if f_industry != "All":
        sql += " AND industry=?"; args.append(f_industry)
    if f_country != "All":
        sql += " AND country=?"; args.append(f_country)
    if f_tier != "All":
        sql += " AND score_tier=?"; args.append(f_tier)
    sql += " ORDER BY score DESC, id DESC"

    with _conn() as conn:
        rows = conn.execute(sql, args).fetchall()

    df = pd.DataFrame(
        rows,
        columns=[
            "Domain", "Company", "Score", "Tier", "Industry", "Country",
            "LinkedIn", "Reasons",
        ],
    )
    df = _filter_df(
        df, f_search,
        ["Domain", "Company", "Reasons", "Industry", "Country"],
    )
    if not df.empty:
        df = df.sort_values("Score", ascending=False, kind="mergesort").reset_index(drop=True)
        df["Domain"] = df["Domain"].map(
            lambda d: (
                d if not d or str(d).startswith(("http://", "https://"))
                else f"https://{d}"
            )
        )
    st.caption(f"**{len(df)}** domains shown · sorted by Score")
    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        height=min(560, 40 + max(1, len(df)) * 35),
        column_config={
            "Domain": st.column_config.LinkColumn(
                "Domain",
                width="medium",
                display_text=r"https://(?:www\.)?(.*)",
            ),
            "Company": st.column_config.TextColumn("Company", width="medium"),
            "Score": st.column_config.NumberColumn("Score", width="small", format="%d"),
            "Tier": st.column_config.TextColumn("Tier", width="small"),
            "Industry": st.column_config.TextColumn("Industry", width="small"),
            "Country": st.column_config.TextColumn("Country", width="small"),
            "LinkedIn": st.column_config.LinkColumn("LinkedIn", width="small", display_text="Open"),
            "Reasons": st.column_config.TextColumn("Reasons", width="large"),
        },
    )

# ══════════════════════════════════════════════════════════════════════════════
# PEOPLE
# ══════════════════════════════════════════════════════════════════════════════
with tab_people:
    section_label("👥", "People")
    with _conn() as conn:
        p_countries = ["All"] + [
            r[0] for r in conn.execute(
                "SELECT DISTINCT d.country FROM people p "
                "JOIN domains d ON p.domain = d.domain "
                "WHERE d.country IS NOT NULL AND TRIM(d.country) != '' "
                "ORDER BY d.country"
            ).fetchall()
        ]
        p_industries = ["All"] + [
            r[0] for r in conn.execute(
                "SELECT DISTINCT d.industry FROM people p "
                "JOIN domains d ON p.domain = d.domain "
                "WHERE d.industry IS NOT NULL AND TRIM(d.industry) != '' "
                "ORDER BY d.industry"
            ).fetchall()
        ]
        p_sources = ["All"] + _distinct(conn, "people", "people_source")

    c1, c2, c3 = st.columns(3)
    with c1:
        pf_industry = st.selectbox("Industry", p_industries, key="dbv_ppl_industry")
    with c2:
        pf_country = st.selectbox("Country", p_countries, key="dbv_ppl_country")
    with c3:
        pf_source = st.selectbox("Source", p_sources, key="dbv_ppl_source")
    pf_search = st.text_input(
        "Search people",
        placeholder="name, title, company, domain…",
        key="dbv_ppl_q",
    )

    sql = """
        SELECT p.full_name, p.title, p.company_name, p.domain,
               d.industry, d.country, d.company_type,
               p.linkedin_url, p.people_source, p.found_at
          FROM people p
          LEFT JOIN domains d ON p.domain = d.domain
         WHERE 1=1
    """
    args = []
    if pf_industry != "All":
        sql += " AND d.industry=?"; args.append(pf_industry)
    if pf_country != "All":
        sql += " AND d.country=?"; args.append(pf_country)
    if pf_source != "All":
        sql += " AND p.people_source=?"; args.append(pf_source)
    sql += " ORDER BY p.id DESC"

    with _conn() as conn:
        rows = conn.execute(sql, args).fetchall()

    df = pd.DataFrame(
        rows,
        columns=[
            "Name", "Title", "Company", "Domain", "Industry", "Country",
            "Type", "LinkedIn", "Source", "Found at",
        ],
    )
    df = _filter_df(
        df, pf_search,
        ["Name", "Title", "Company", "Domain", "Industry", "Country"],
    )
    st.caption(f"**{len(df)}** people shown")
    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        height=min(560, 40 + max(1, len(df)) * 35),
        column_config={
            "LinkedIn": st.column_config.LinkColumn("LinkedIn", display_text="Open"),
        },
    )

# ══════════════════════════════════════════════════════════════════════════════
# LEADS
# ══════════════════════════════════════════════════════════════════════════════
with tab_leads:
    section_label("📧", "Leads")
    with _conn() as conn:
        l_countries = ["All"] + _distinct(conn, "leads", "country")
        l_sources = ["All"] + _distinct(conn, "leads", "email_source")

    c1, c2 = st.columns(2)
    with c1:
        lf_country = st.selectbox("Country", l_countries, key="dbv_lead_country")
    with c2:
        lf_source = st.selectbox("Email source", l_sources, key="dbv_lead_source")
    lf_search = st.text_input(
        "Search leads",
        placeholder="email, name, title, company, domain…",
        key="dbv_lead_q",
    )

    sql = """
        SELECT email, full_name, title, company, domain, country,
               email_source, linkedin_url, first_name, last_name
          FROM leads WHERE 1=1
    """
    args = []
    if lf_country != "All":
        sql += " AND country=?"; args.append(lf_country)
    if lf_source != "All":
        sql += " AND email_source=?"; args.append(lf_source)
    sql += " ORDER BY id DESC"

    with _conn() as conn:
        rows = conn.execute(sql, args).fetchall()

    df = pd.DataFrame(
        rows,
        columns=[
            "Email", "Name", "Title", "Company", "Domain", "Country",
            "Source", "LinkedIn", "First name", "Last name",
        ],
    )
    df = _filter_df(
        df, lf_search,
        ["Email", "Name", "Title", "Company", "Domain", "Country"],
    )
    st.caption(f"**{len(df)}** leads shown")
    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        height=min(560, 40 + max(1, len(df)) * 35),
        column_config={
            "Email": st.column_config.TextColumn("Email", width="medium"),
            "LinkedIn": st.column_config.LinkColumn("LinkedIn", display_text="Open"),
        },
    )

# ══════════════════════════════════════════════════════════════════════════════
# BLOCKED
# ══════════════════════════════════════════════════════════════════════════════
with tab_blocked:
    section_label("🚫", "Blocked domains")
    bf_search = st.text_input(
        "Search blocked",
        placeholder="domain…",
        key="dbv_blk_q",
    )
    with _conn() as conn:
        rows = conn.execute(
            "SELECT domain, blocked_at FROM blocked_domains ORDER BY blocked_at DESC"
        ).fetchall()
    df = pd.DataFrame(rows, columns=["Domain", "Blocked at"])
    df = _filter_df(df, bf_search, ["Domain"])
    st.caption(f"**{len(df)}** blocked domains shown")
    st.dataframe(df, use_container_width=True, hide_index=True, height=400)

st.caption(
    "Live view of `leads.db`. Per-run Excel downloads remain on each Step page."
)

# ── Full database Excel export (by category) ───────────────────────────────────
section_label("📥", "Export full database")
_ex1, _ex2 = st.columns([2, 4])
with _ex1:
    try:
        from export_excel import build_excel_bytes
        _xlsx = build_excel_bytes(DB_PATH)
        st.download_button(
            label="📊 Export full database (Excel)",
            data=_xlsx,
            file_name=f"locreach_full_db_{_dt.now().strftime('%Y%m%d_%H%M')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
            type="primary",
            key="db_export_full_db",
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
        key="db_reset_confirm",
    )
    if st.button(
        "🗑️ Reset database",
        type="primary",
        disabled=not _confirm_reset,
        help="Wipes every pipeline table. Requires the confirmation checkbox.",
        key="db_reset_button",
    ):
        _wc = sqlite3.connect(DB_PATH)
        db_init(_wc)
        _counts = db_wipe_all(_wc)
        _wc.close()
        st.session_state["reset_done_msg"] = _counts
        st.rerun()
