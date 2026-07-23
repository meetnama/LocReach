"""
pages/2_People.py — LocReach Step 2: Find People

For every qualified domain from Step 1:
  1. Classify the company as LSP (translation provider) or Client (translation
     buyer) — keyword heuristic, escalated to Groq when ambiguous.
     Result cached in domains.company_type so it runs once per company.
  2. Run broad X-Ray search via SearXNG (collect all profiles matching the
     company name, no title filter at query time).
  3. Run LinkedIn /people page scraper via Chrome (secondary source).
  4. Merge + dedup by linkedin_url (else full_name).
  5. Apply title_filter.passes() based on company_type
     (LSP → managers/decision-makers; Client → localization-specific roles).
  6. Save survivors to the `people` table; stamp people_searched_at.

Sequential per-company loop — progress updates after every company, and
stop/resume is safe because each company is marked done before moving on.

The debug expander at the bottom shows per-company classifier output,
SearXNG queries fired, raw/filtered counts.
"""
import os
import sys
import sqlite3
import threading
import queue
import time
from datetime import datetime

import streamlit as st
import streamlit.components.v1 as components

# ── Make project root importable ──────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sources.base import Company
from sources.people.company_website import CompanyWebsitePeople
from sources.people.google_linkedin import GoogleLinkedInPeople
from sources.people.linkedin_company import find_people_from_linkedin_page, ensure_linkedin_login
from sources.people.company_classifier import classify_company
from sources.people import title_filter
from db import (
    db_init,
    db_load_qualified_domains,
    db_load_people,
    db_insert_person,
    db_mark_company_people_done,
    db_get_company_type,
    db_set_company_type,
    db_reset_people_search,
)
from ui_theme import (
    inject_theme, page_header, step_indicator, stat_cards,
    section_label, render_table, type_badge, link_icon,
)
from template_render import render_people_db_table, table_embed_height

# ── Paths ──────────────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH  = os.path.join(BASE_DIR, "leads.db")

inject_theme()

# ── Session state ──────────────────────────────────────────────────────────────
for k, v in {
    "s3_running":         False,
    "s3_done":            False,
    "s3_queue":           None,
    "s3_stop_event":      None,
    "s3_current_company": "",
    "s3_processed":       0,
    "s3_total":           0,
    "s3_people":          [],   # list of person dicts found this run
    "s3_no_people":       0,    # companies that returned 0 people
    "s3_start_time":      None,
    "s3_error":           "",
    "s3_debug_log":       [],   # list of per-company debug dicts (session 19)
    "s3_li_status":       "",   # live LinkedIn login status message
}.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ══════════════════════════════════════════════════════════════════════════════
# SIDEBAR
# ══════════════════════════════════════════════════════════════════════════════
_conn = sqlite3.connect(DB_PATH)
db_init(_conn)
_todo          = db_load_qualified_domains(_conn, only_unsearched=True)
_existing      = db_load_people(_conn)
_total_ver     = _conn.execute("SELECT COUNT(*) FROM domains WHERE status='qualified'").fetchone()[0]
_already_done  = _conn.execute("SELECT COUNT(*) FROM domains WHERE status='qualified' AND people_searched_at IS NOT NULL").fetchone()[0]
_conn.close()

page_header("👥", "Step 2 — Find People",
            "Classify companies, X-Ray LinkedIn, and filter by target titles.")
step_indicator(2)
stat_cards([
    ("Queued",    len(_todo),       "pipeline"),
    ("Searched",  _already_done,    "signal"),
    ("Qualified", _total_ver,       "qualified"),
    ("In DB",     len(_existing),   "reach"),
])

with st.expander("⚙️ Options", expanded=False):
    if not st.session_state.s3_running:
        if st.button("🔄 Reset all — re-search", use_container_width=True,
                     help="Clears people_searched_at so ALL qualified domains are re-processed. "
                          "Use after improving search logic."):
            _rc = sqlite3.connect(DB_PATH)
            n   = db_reset_people_search(_rc)
            _rc.close()
            st.success(f"Reset {n} companies. Reload to see updated queue.")
            st.rerun()
    skip_li_page = st.checkbox(
        "Skip LinkedIn /people page",
        value=False,
        help=(
            "When unchecked, Chrome auto-logs into LinkedIn (credentials in .env) "
            "and scrapes each company's /people page — finds 8–15 extra profiles per company. "
            "Check this box to skip Chrome entirely and rely only on X-Ray + website (~5× faster)."
        ),
    )

# ── SearXNG status banner ──────────────────────────────────────────────────────
from sources.utils import service_reachable, service_url_host_port

_searxng_url = os.getenv("SEARXNG_URL", "http://localhost:8888").strip()
_searxng_host, _searxng_port = service_url_host_port(_searxng_url, 8888)
_searxng_ok = service_reachable(_searxng_url, local_default=8888, timeout=3.0)

if _searxng_ok:
    st.success(f"✅ **SearXNG running** at `{_searxng_host}:{_searxng_port}` — LinkedIn X-Ray enabled. No CAPTCHAs.")
else:
    st.warning(
        f"⚠️ **SearXNG not reachable** at `{_searxng_host}:{_searxng_port}`. "
        "LinkedIn X-Ray will be **skipped** (website scraping still runs). "
        "Start **`5 - Start SearXNG.bat`** to enable X-Ray."
    )

# LinkedIn login status banner (shown while running and after)
_li_status = st.session_state.s3_li_status
if _li_status:
    if _li_status.startswith("✅"):
        st.success(_li_status)
    elif _li_status.startswith("⚠️"):
        st.warning(_li_status)
    else:
        st.info(_li_status)

# ══════════════════════════════════════════════════════════════════════════════
# CONTROLS
# ══════════════════════════════════════════════════════════════════════════════
ready = len(_todo) > 0

bcol1, bcol2, bcol3 = st.columns([2, 2, 4])
with bcol1:
    run_btn = st.button(
        "▶️  Find People",
        disabled=st.session_state.s3_running or not ready,
        use_container_width=True,
        type="primary",
    )
with bcol2:
    stop_btn = st.button(
        "⏹  Stop",
        disabled=not st.session_state.s3_running,
        use_container_width=True,
    )
with bcol3:
    status_ph = st.empty()

# ── Status + progress ──────────────────────────────────────────────────────────
if st.session_state.s3_error:
    status_ph.error(f"Error: {st.session_state.s3_error}")

elif st.session_state.s3_running:
    company   = st.session_state.s3_current_company
    processed = st.session_state.s3_processed
    total     = st.session_state.s3_total
    elapsed   = int(time.time() - (st.session_state.s3_start_time or time.time()))
    mins, secs = divmod(elapsed, 60)
    elapsed_str = f"{mins}m {secs}s" if mins else f"{secs}s"

    if company:
        status_ph.info(f"Searching **{company}** — {processed} / {total} — {elapsed_str} elapsed")
    else:
        status_ph.info(f"Starting Chrome… ({elapsed_str})")

    progress = processed / total if total else 0
    st.progress(min(progress, 1.0))

elif st.session_state.s3_done:
    n_people    = len(st.session_state.s3_people)
    n_processed = st.session_state.s3_processed
    elapsed     = int(time.time() - (st.session_state.s3_start_time or time.time()))
    mins, secs  = divmod(elapsed, 60)
    elapsed_str = f"{mins}m {secs}s" if mins else f"{secs}s"
    status_ph.success(
        f"Done — **{n_people}** people found across {n_processed} companies in {elapsed_str}."
    )
    st.progress(1.0)
    st.success(
        f"✅ Complete — **{n_people} contacts** found in {elapsed_str}. "
        "Ready for Step 3: Find Emails."
    )
else:
    if not ready:
        status_ph.warning("No companies to search. Run Step 1 first to qualify domains.")
    else:
        status_ph.info(f"{len(_todo)} companies ready — press Find People.")

# ── Stats ──────────────────────────────────────────────────────────────────────
processed = st.session_state.s3_processed
n_people  = len(st.session_state.s3_people)
no_people = st.session_state.s3_no_people
total     = st.session_state.s3_total

if processed > 0 or st.session_state.s3_running:
    stat_cards([
        ("Processed",    f"{processed} / {total}", "signal"),
        ("People Found", n_people,                  "qualified"),
        ("No People",    no_people,                 "pipeline"),
    ])

# ══════════════════════════════════════════════════════════════════════════════
# BACKGROUND WORKER
# ══════════════════════════════════════════════════════════════════════════════

def _make_log(q: queue.Queue):
    def log(tag, msg):
        print(f"[{tag:6}] {msg}")
    return log


def _merge_people(people_list: list) -> list:
    """Deduplicate by (domain, full_name) — first occurrence wins."""
    seen   = set()
    result = []
    for p in people_list:
        key = (p.domain, p.full_name.lower().strip())
        if key not in seen:
            seen.add(key)
            result.append(p)
    return result


def _merge_by_linkedin(people_list: list) -> list:
    """
    Deduplicate merged source results.
    Primary key: linkedin_url (lowercased, trailing slash stripped).
    Fallback key for people with no LinkedIn URL: (domain, full_name).
    First occurrence wins.
    """
    seen_urls:  set = set()
    seen_names: set = set()
    out = []
    for p in people_list:
        li = (p.linkedin_url or "").lower().rstrip("/")
        if li:
            if li in seen_urls:
                continue
            seen_urls.add(li)
        else:
            key = (p.domain, p.full_name.lower().strip())
            if key in seen_names:
                continue
            seen_names.add(key)
        out.append(p)
    return out


def _run_step3(companies_data: list, q_out: queue.Queue,
               stop_event: threading.Event,
               skip_li_page: bool = True):
    """
    Sequential per-company loop:
      classify → X-Ray → [LinkedIn page] → website → merge → title-filter → save → mark done

    LinkedIn /people page is skipped when skip_li_page=True (default), when the
    company has no LinkedIn URL, or when X-Ray already found ≥5 results.

    Progress counter updates after each company. Stop is safe at any point.
    """
    try:
        conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        db_init(conn)

        log_fn = _make_log(q_out)

        # ── Auto-login LinkedIn once before the company loop ──────────────────
        if not skip_li_page:
            q_out.put(("li_status", "⏳ Logging into LinkedIn — check the Chrome window if prompted…"))
            li_logged_in = ensure_linkedin_login(log=log_fn)
            if li_logged_in:
                q_out.put(("li_status", "✅ LinkedIn logged in — /people page scraping active"))
            else:
                q_out.put(("li_status", "⚠️ LinkedIn login failed — /people page will be skipped"))

        # X-Ray broad search (no title-in-query)
        xray_source = GoogleLinkedInPeople(log=log_fn, max_per_domain=10)
        # Website scraper kept as a tertiary source for very small sites
        website_source = CompanyWebsitePeople(log=log_fn)

        # Build Company objects — row = (domain, company_name, linkedin_url, industry, country)
        companies = [
            Company(
                name         = row[1] or row[0],
                domain       = row[0],
                url          = f"https://{row[0]}",
                linkedin_url = row[2] or "",
                country      = row[4] or "",
            )
            for row in companies_data
        ]

        for company in companies:
            if stop_event.is_set():
                break

            q_out.put(("scanning", company.name))

            dbg = {
                "company":      company.name,
                "domain":       company.domain,
                "type":         "",
                "type_method":  "",
                "type_kw_hits": 0,
                "queries":      [],
                "raw_xray":     0,
                "raw_page":     0,
                "raw_website":  0,
                "after_filter": 0,
                "saved":        0,
                "errors":       [],
            }

            # ── 1. Classify ───────────────────────────────────────────────────
            company_type = db_get_company_type(conn, company.domain)
            if not company_type:
                try:
                    company_type, cinfo = classify_company(company)
                    dbg["type_method"]  = cinfo.get("method", "")
                    dbg["type_kw_hits"] = cinfo.get("kw_hits", 0)
                except Exception as exc:
                    dbg["errors"].append(f"classify: {exc}")
                    company_type = "client"
                    dbg["type_method"] = "error → client default"
                db_set_company_type(conn, company.domain, company_type)
            else:
                dbg["type_method"] = "cached"
            dbg["type"] = company_type

            if stop_event.is_set():
                break

            # ── 2. X-Ray (SearXNG) — broad company-name search ────────────────
            xray_people = []
            try:
                xray_people = xray_source.find_people(company, debug=dbg)
            except Exception as exc:
                dbg["errors"].append(f"xray: {exc}")
            dbg["raw_xray"] = len(xray_people)

            if stop_event.is_set():
                break

            # ── 3. LinkedIn /people page (Chrome) — secondary source ─────────
            # Skip if: quick-mode flag set, no LinkedIn URL, or X-Ray already
            # found enough candidates (Chrome login-wall scraping is slow).
            page_people = []
            _li_skip_reason = ""
            if skip_li_page:
                _li_skip_reason = "quick mode"
            elif not company.linkedin_url:
                _li_skip_reason = "no LinkedIn URL"
            elif len(xray_people) >= 5:
                _li_skip_reason = f"X-Ray already found {len(xray_people)}"

            if _li_skip_reason:
                dbg["errors"].append(f"linkedin_page: skipped ({_li_skip_reason})")
            else:
                try:
                    page_people = find_people_from_linkedin_page(company, log=log_fn)
                except Exception as exc:
                    dbg["errors"].append(f"linkedin_page: {exc}")
            dbg["raw_page"] = len(page_people)

            if stop_event.is_set():
                break

            # ── 4. Website fallback (structural extractors only) ──────────────
            site_people = []
            try:
                site_people = website_source.find_people(company)
            except Exception as exc:
                dbg["errors"].append(f"website: {exc}")
            dbg["raw_website"] = len(site_people)

            # ── 5. Merge + dedup ──────────────────────────────────────────────
            merged = _merge_by_linkedin(xray_people + page_people + site_people)

            # ── 6. Title filter by company_type ───────────────────────────────
            filtered = [p for p in merged if title_filter.passes(p.title, company_type)]
            # Cap at 10 per company
            filtered = filtered[:10]
            dbg["after_filter"] = len(filtered)

            # ── 7. Save + mark done ───────────────────────────────────────────
            ts = datetime.now().isoformat()
            for p in filtered:
                db_insert_person(conn, {
                    "domain":        p.domain,
                    "company_name":  p.company_name,
                    "first_name":    p.first,
                    "last_name":     p.last,
                    "full_name":     p.full_name,
                    "title":         p.title,
                    "linkedin_url":  p.linkedin_url,
                    "people_source": p.people_source,
                    "found_at":      ts,
                })
            db_mark_company_people_done(conn, company.domain)
            dbg["saved"] = len(filtered)

            # Push debug entry to UI
            q_out.put(("debug", dbg))

            if filtered:
                q_out.put(("people", [
                    {
                        "full_name":     p.full_name,
                        "title":         p.title,
                        "company_name":  p.company_name,
                        "domain":        p.domain,
                        "linkedin_url":  p.linkedin_url,
                        "people_source": p.people_source,
                        "company_type":  company_type,
                    }
                    for p in filtered
                ]))
            else:
                q_out.put(("no_people", company.domain))

        conn.close()

    except Exception as exc:
        q_out.put(("error", str(exc)))

    q_out.put(("done", None))


# ── Start run ──────────────────────────────────────────────────────────────────
if run_btn and not st.session_state.s3_running:
    _stop_event = threading.Event()
    st.session_state.s3_running         = True
    st.session_state.s3_done            = False
    st.session_state.s3_queue           = queue.Queue()
    st.session_state.s3_stop_event      = _stop_event
    st.session_state.s3_current_company = ""
    st.session_state.s3_processed       = 0
    st.session_state.s3_people          = []
    st.session_state.s3_no_people       = 0
    st.session_state.s3_total           = len(_todo)
    st.session_state.s3_error           = ""
    st.session_state.s3_start_time      = time.time()
    st.session_state.s3_debug_log       = []
    st.session_state.s3_li_status       = ""

    threading.Thread(
        target=_run_step3,
        args=(_todo, st.session_state.s3_queue, _stop_event),
        kwargs={"skip_li_page": skip_li_page},
        daemon=True,
    ).start()
    st.rerun()

if stop_btn:
    if st.session_state.s3_stop_event:
        st.session_state.s3_stop_event.set()
    st.session_state.s3_running = False
    st.session_state.s3_done    = True

# ── Drain queue ────────────────────────────────────────────────────────────────
if st.session_state.s3_queue:
    q = st.session_state.s3_queue
    while not q.empty():
        kind, payload = q.get_nowait()

        if kind == "li_status":
            st.session_state.s3_li_status = payload

        elif kind == "scanning":
            st.session_state.s3_current_company = payload

        elif kind == "people":
            st.session_state.s3_people.extend(payload)
            st.session_state.s3_processed += 1

        elif kind == "no_people":
            st.session_state.s3_no_people += 1
            st.session_state.s3_processed += 1

        elif kind == "debug":
            st.session_state.s3_debug_log.append(payload)

        elif kind == "error":
            st.session_state.s3_error = payload

        elif kind == "done":
            st.session_state.s3_running         = False
            st.session_state.s3_done            = True
            st.session_state.s3_current_company = ""

# ══════════════════════════════════════════════════════════════════════════════
# RESULTS TABLE
# ══════════════════════════════════════════════════════════════════════════════
# Current run results only — starts empty on page load (like Step 1)
display_people = list(st.session_state.s3_people)

if display_people:
    section_label("👤", f"People Found ({len(display_people)})")

    table_rows = ""
    for i, p in enumerate(display_people, 1):
        name    = p.get("full_name",    "—")
        title   = p.get("title",        "—")
        company = p.get("company_name", "—")
        li_cell = link_icon(p.get("linkedin_url", ""))
        badge   = type_badge(p.get("company_type"))

        table_rows += (
            f"<tr>"
            f"<td class='lr-muted' style='width:32px'>{i}</td>"
            f"<td class='lr-cell-strong'>{name}</td>"
            f"<td>{title}</td>"
            f"<td>{company}</td>"
            f"<td style='text-align:center'>{badge}</td>"
            f"<td style='text-align:center'>{li_cell}</td>"
            f"</tr>"
        )

    render_table(
        ["#", "Name", "Title", "Company", "Type", "LinkedIn"],
        table_rows,
        max_height="520px",
    )

# ── All people in the DB (read-only, Jinja-rendered) ────────────────────────────
# Rendered from templates/_db_people_embed.html with real data and embedded as a
# static iframe. Read-only, so the Jinja/Tailwind template needs no Python callback.
if not st.session_state.s3_running and _existing:
    components.html(
        render_people_db_table(_existing),
        height=table_embed_height(len(_existing)),
        scrolling=False,
    )

# ══════════════════════════════════════════════════════════════════════════════
# HTML REPORT GENERATOR
# ══════════════════════════════════════════════════════════════════════════════

def _make_people_html(people: list) -> str:
    """Generate a self-contained dark-themed HTML report for the people list."""
    now_str  = datetime.now().strftime("%Y-%m-%d %H:%M")
    total    = len(people)
    lsp_cnt  = sum(1 for p in people if (p.get("company_type") or "").lower() == "lsp")
    cli_cnt  = sum(1 for p in people if (p.get("company_type") or "").lower() == "client")

    rows_html = ""
    for i, p in enumerate(people, 1):
        name    = p.get("full_name",    "") or "—"
        title   = p.get("title",        "") or "—"
        company = p.get("company_name", "") or "—"
        domain  = p.get("domain",       "") or ""
        li      = p.get("linkedin_url", "") or ""
        ctype   = (p.get("company_type") or "").lower()

        if ctype == "lsp":
            badge = '<span style="background:#3a2a10;color:#fb923c;padding:2px 8px;border-radius:4px;font-size:0.7rem;font-weight:600">LSP</span>'
        elif ctype == "client":
            badge = '<span style="background:#13314f;color:#60a5fa;padding:2px 8px;border-radius:4px;font-size:0.7rem;font-weight:600">Client</span>'
        else:
            badge = '<span style="color:#555">—</span>'

        li_link = f'<a href="{li}" target="_blank" style="color:#60a5fa;text-decoration:none">🔗 LinkedIn</a>' if li else '—'
        dom_link = f'<a href="https://{domain}" target="_blank" style="color:#888;font-size:0.8em;text-decoration:none">{domain}</a>' if domain else "—"

        rows_html += f"""
        <tr class="data-row">
          <td style="color:#555;padding:9px 14px">{i}</td>
          <td style="font-weight:600;color:#e8f4f8;padding:9px 14px">{name}</td>
          <td style="color:#a8d8ea;padding:9px 14px">{title}</td>
          <td style="color:#ccc;padding:9px 14px">{company}</td>
          <td style="padding:9px 14px;text-align:center">{badge}</td>
          <td style="padding:9px 14px">{dom_link}</td>
          <td style="padding:9px 14px;text-align:center">{li_link}</td>
        </tr>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>LocReach — People Found</title>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body   {{ background: #0f1117; color: #ccc; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; padding: 32px 24px; }}
    h1     {{ color: #e8f4f8; font-size: 1.6rem; margin-bottom: 4px; }}
    .meta  {{ color: #555; font-size: 0.85rem; margin-bottom: 28px; }}
    .cards {{ display: flex; gap: 14px; flex-wrap: wrap; margin-bottom: 28px; }}
    .card  {{ background: #1e2130; border: 1px solid #2e3250; border-radius: 10px; padding: 14px 24px; text-align: center; min-width: 120px; }}
    .card-val {{ font-size: 1.8rem; font-weight: 700; }}
    .card-lbl {{ font-size: 0.72rem; color: #888; margin-top: 4px; }}
    .blue    {{ color: #60a5fa; }}
    .orange  {{ color: #fb923c; }}
    .green   {{ color: #34d399; }}
    table    {{ width: 100%; border-collapse: collapse; background: #1a1d2e; border-radius: 8px; overflow: hidden; font-size: 0.85rem; }}
    thead th {{ background: #1e2130; color: #a8d8ea; padding: 11px 14px; text-align: left; border-bottom: 2px solid #2e3250; position: sticky; top: 0; }}
    .data-row:hover {{ background: #1e2130; }}
    td {{ border-bottom: 1px solid #1e2130; }}
    .scroll {{ overflow-x: auto; border-radius: 8px; }}
    input#search {{ background: #1e2130; border: 1px solid #2e3250; border-radius: 6px; color: #ccc;
                    padding: 8px 14px; font-size: 0.9rem; width: 260px; margin-bottom: 14px; outline: none; }}
    input#search:focus {{ border-color: #34d399; }}
  </style>
</head>
<body>
  <h1>👥 LocReach — People Found</h1>
  <div class="meta">Generated {now_str}</div>

  <div class="cards">
    <div class="card"><div class="card-val blue">{total}</div><div class="card-lbl">Total People</div></div>
    <div class="card"><div class="card-val orange">{lsp_cnt}</div><div class="card-lbl">At LSPs</div></div>
    <div class="card"><div class="card-val blue">{cli_cnt}</div><div class="card-lbl">At Clients</div></div>
    <div class="card"><div class="card-val green">{total - lsp_cnt - cli_cnt}</div><div class="card-lbl">Unclassified</div></div>
  </div>

  <input id="search" type="text" placeholder="Filter by name, title, company…" oninput="filterTable(this.value)">

  <div class="scroll">
    <table id="people-table">
      <thead>
        <tr>
          <th>#</th>
          <th>Name</th>
          <th>Title</th>
          <th>Company</th>
          <th style="text-align:center">Type</th>
          <th>Domain</th>
          <th style="text-align:center">LinkedIn</th>
        </tr>
      </thead>
      <tbody id="tbody">
        {rows_html}
      </tbody>
    </table>
  </div>

  <script>
    function filterTable(q) {{
      q = q.toLowerCase();
      document.querySelectorAll('#tbody tr').forEach(function(row) {{
        row.style.display = row.textContent.toLowerCase().includes(q) ? '' : 'none';
      }});
    }}
  </script>
</body>
</html>"""


# ══════════════════════════════════════════════════════════════════════════════
# EXPORT
# ══════════════════════════════════════════════════════════════════════════════
if display_people:
    section_label("📥", "Export")
    exp_col1, exp_col2 = st.columns([1, 1])

    with exp_col1:
        html_bytes = _make_people_html(display_people).encode("utf-8")
        st.download_button(
            label="📄  Download HTML Report",
            data=html_bytes,
            file_name=f"People_results_{datetime.now().strftime('%Y-%m-%d')}.html",
            mime="text/html",
            use_container_width=True,
            type="primary",
        )

    with exp_col2:
        try:
            from export_excel import build_people_excel_bytes
            xlsx_bytes = build_people_excel_bytes(display_people)
            st.download_button(
                label="📊  Download Excel (this run)",
                data=xlsx_bytes,
                file_name=f"locreach_people_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )
            st.caption("Exports **this run's** people only. Full DB export is on **Home**.")
        except Exception as _e:
            st.error(f"Excel export failed: {_e}")

# ══════════════════════════════════════════════════════════════════════════════
# DEBUG LOG
# ══════════════════════════════════════════════════════════════════════════════
if st.session_state.s3_debug_log:
    st.markdown("---")
    with st.expander(
        f"🐛 Debug Log ({len(st.session_state.s3_debug_log)} companies)",
        expanded=False,
    ):
        for entry in st.session_state.s3_debug_log:
            badge = entry.get("type", "?") or "?"
            badge_color = "#fb923c" if badge == "lsp" else "#60a5fa" if badge == "client" else "#888"
            st.markdown(
                f"**{entry.get('company', '?')}** "
                f"`{entry.get('domain', '')}` — "
                f"<span style='color:{badge_color};font-weight:600'>"
                f"{badge.upper()}</span> "
                f"(via {entry.get('type_method', '?')}, "
                f"keyword hits: {entry.get('type_kw_hits', 0)})",
                unsafe_allow_html=True,
            )
            queries = entry.get("queries", []) or []
            if queries:
                for q in queries:
                    engine = q.get("engine", "SearXNG")
                    eng_col = "#fb923c" if engine == "DDG" else "#60a5fa"
                    st.markdown(
                        f"  • <span style='color:{eng_col};font-size:0.75rem'>[{engine}]</span> "
                        f"`{q.get('query', '')}` → "
                        f"{q.get('results', 0)} results, {q.get('added', 0)} added",
                        unsafe_allow_html=True,
                    )
            st.markdown(
                f"  raw: xray=**{entry.get('raw_xray', 0)}**, "
                f"page=**{entry.get('raw_page', 0)}**, "
                f"website=**{entry.get('raw_website', 0)}** → "
                f"after_filter=**{entry.get('after_filter', 0)}** → "
                f"saved=**{entry.get('saved', 0)}**"
            )
            errs = entry.get("errors") or []
            if errs:
                for e in errs:
                    st.markdown(f"  ⚠ {e}")
            st.markdown("")

# ── Auto-refresh ───────────────────────────────────────────────────────────────
if st.session_state.s3_running:
    time.sleep(2.0)
    st.rerun()
elif st.session_state.s3_done and st.session_state.s3_queue is not None:
    st.session_state.s3_queue = None
    st.rerun()
