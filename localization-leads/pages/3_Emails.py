"""
pages/3_Emails.py — LocReach Step 3: Find Emails

For every person found in Step 2 (email_searched_at IS NULL):
  L1 — Website crawler  : scrape company contact pages for exposed emails
  L2 — EmailFormat.com  : lookup company email pattern, SMTP-verify candidate
  L4 — SearXNG search   : '"First Last" "@domain.com"' — find indexed emails

Layer order: L1 → L2 → L4. The old L3 (SMTP pattern brute-force guessing)
was removed — it could save an email pattern even when the mail server
couldn't confirm it (shown as a low-confidence "risky"/"unknown" guess).
Per the "don't show a result unless it's confirmed" rule, only emails with
actual evidence (crawled off the site, verified via EmailFormat.com + SMTP,
or found already indexed by search) are saved as leads.

Safe stop/resume: each person is stamped email_searched_at AFTER processing,
so the loop resumes from where it stopped.
"""
import os
import sys
import re
import sqlite3
import threading
import queue
import time
import unicodedata
from datetime import datetime
from typing import Optional

import streamlit as st
import streamlit.components.v1 as components

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sources.base import Person, EmailResult
from sources.email.website_crawler import WebsiteEmailCrawler
from sources.email.emailformat_pattern import EmailFormatPatternEmail
from sources.email.smtp_verifier import SmtpVerifier
from sources.utils import searxng_search, clean_email, is_generic_email
from sources.email.lead_gate import is_confirmed_lead
from db import (
    db_init,
    db_insert_lead,
    db_load_people_without_email,
    db_load_leads,
    db_count_leads,
    db_mark_person_email_done,
)
from ui_theme import (
    inject_theme, page_header, step_indicator, stat_cards,
    section_label, render_table, source_badge, link_icon,
)
from template_render import render_leads_db_table, table_embed_height

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH  = os.path.join(BASE_DIR, "leads.db")

inject_theme()

# ── Session state ──────────────────────────────────────────────────────────────
for k, v in {
    "s4_running":    False,
    "s4_done":       False,
    "s4_queue":      None,
    "s4_stop_event": None,
    "s4_processed":  0,
    "s4_total":      0,
    "s4_found":      0,
    "s4_not_found":  0,
    "s4_start_time": None,
    "s4_error":      "",
    "s4_leads":      [],   # lead dicts found this run
    "s4_debug_log":  [],   # per-person debug entries
    "s4_current":    "",   # currently processing person name
}.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ── DB init + sidebar counts ──────────────────────────────────────────────────
_conn = sqlite3.connect(DB_PATH)
db_init(_conn)
_todo_count   = len(db_load_people_without_email(_conn))
_leads_count  = db_count_leads(_conn)
_conn.close()

page_header("📧", "Step 3 — Find Emails",
            "L1 site crawl → L2 EmailFormat + SMTP → L4 SearXNG search. Confirmed emails only.")
step_indicator(3)
stat_cards([
    ("To search",   _todo_count,  "pipeline"),
    ("Leads found", _leads_count, "qualified"),
])

# ── SearXNG status banner ──────────────────────────────────────────────────────
from sources.utils import service_reachable, service_url_host_port

_searxng_url = os.getenv("SEARXNG_URL", "http://localhost:8888").strip()
_searxng_host, _searxng_port = service_url_host_port(_searxng_url, 8888)
_searxng_ok = service_reachable(_searxng_url, local_default=8888, timeout=3.0)

if _searxng_ok:
    st.success(f"✅ **SearXNG running** at `{_searxng_host}:{_searxng_port}` — email search (L4) enabled.")
else:
    st.warning(
        f"⚠️ **SearXNG not reachable** at `{_searxng_host}:{_searxng_port}`. "
        "Layer 4 (search) will be **skipped**. "
        "Start **`5 - Start SearXNG.bat`** to enable it."
    )

# ══════════════════════════════════════════════════════════════════════════════
# CONTROLS
# ══════════════════════════════════════════════════════════════════════════════
ready = _todo_count > 0

bcol1, bcol2, bcol3 = st.columns([2, 2, 4])
with bcol1:
    run_btn = st.button(
        "▶️  Find Emails",
        disabled=st.session_state.s4_running or not ready,
        use_container_width=True,
        type="primary",
    )
with bcol2:
    stop_btn = st.button(
        "⏹  Stop",
        disabled=not st.session_state.s4_running,
        use_container_width=True,
    )
with bcol3:
    status_ph = st.empty()

# ── Status + progress ──────────────────────────────────────────────────────────
if st.session_state.s4_error:
    status_ph.error(f"Error: {st.session_state.s4_error}")

elif st.session_state.s4_running:
    person   = st.session_state.s4_current
    processed = st.session_state.s4_processed
    total     = st.session_state.s4_total
    elapsed   = int(time.time() - (st.session_state.s4_start_time or time.time()))
    mins, secs = divmod(elapsed, 60)
    elapsed_str = f"{mins}m {secs}s" if mins else f"{secs}s"

    if person:
        status_ph.info(f"Searching **{person}** — {processed} / {total} — {elapsed_str}")
    else:
        status_ph.info(f"Starting… ({elapsed_str})")

    progress = processed / total if total else 0
    st.progress(min(progress, 1.0))

elif st.session_state.s4_done:
    found     = st.session_state.s4_found
    processed = st.session_state.s4_processed
    elapsed   = int(time.time() - (st.session_state.s4_start_time or time.time()))
    mins, secs = divmod(elapsed, 60)
    elapsed_str = f"{mins}m {secs}s" if mins else f"{secs}s"
    status_ph.success(f"Done — **{found}** emails found across {processed} people in {elapsed_str}.")
    st.progress(1.0)
    st.success(f"✅ Complete — **{found} leads** saved to the database in {elapsed_str}.")
else:
    if not ready:
        status_ph.warning("No people to search. Run Step 2 first to find contacts.")
    else:
        status_ph.info(f"{_todo_count} people queued — press Find Emails.")

# ── Stats cards ────────────────────────────────────────────────────────────────
processed  = st.session_state.s4_processed
found      = st.session_state.s4_found
not_found  = st.session_state.s4_not_found
total      = st.session_state.s4_total

if processed > 0 or st.session_state.s4_running:
    stat_cards([
        ("Processed",    f"{processed} / {total}", "signal"),
        ("Emails Found", found,                     "qualified"),
        ("Not Found",    not_found,                 "pipeline"),
    ])

# ══════════════════════════════════════════════════════════════════════════════
# WORKER  (engine untouched — only page layer changed)
# ══════════════════════════════════════════════════════════════════════════════

def _norm_name(s: str) -> str:
    """ASCII-fold + strip non-alpha — for email pattern generation."""
    s = s.lower().strip()
    s = unicodedata.normalize("NFKD", s)
    s = s.encode("ascii", errors="ignore").decode("ascii")
    return re.sub(r"[^a-z]", "", s)


def _split_name(full_name: str, first: str, last: str):
    """Return (first, last) — use stored columns, fall back to splitting full_name."""
    f = (first or "").strip()
    l = (last  or "").strip()
    if not f and not l and full_name:
        parts = full_name.strip().split()
        f = parts[0]  if parts else ""
        l = parts[-1] if len(parts) > 1 else ""
    return f, l


def _searxng_email_search(person: Person) -> Optional[EmailResult]:
    """
    L4: search SearXNG for '"First Last" "@domain.com"'.
    Returns an EmailResult if a valid @domain email is found in results.
    """
    if not person.first or not person.last or not person.domain:
        return None
    query = f'"{person.first} {person.last}" "@{person.domain}"'
    try:
        results = searxng_search(query, num=5)
    except Exception:
        return None

    pattern = re.compile(
        r'\b([A-Za-z0-9._%+-]+@' + re.escape(person.domain) + r')\b',
        re.IGNORECASE,
    )
    for r in results:
        text = (r.get("snippet") or "") + " " + (r.get("title") or "") + " " + (r.get("link") or "")
        m = pattern.search(text)
        if m:
            email = clean_email(m.group(1))
            if email and not is_generic_email(email):
                return EmailResult(email=email, label="Search ✓", verified=True)
    return None


def _make_log(q: queue.Queue):
    def _log(tag: str, msg: str) -> None:
        print(f"[{tag:6}] {msg}")
    return _log


def _run_step4(people_data: list, q_out: queue.Queue, stop_event: threading.Event):
    """
    Sequential per-person email search loop.
    Layer order: L1 (site crawl) → L2 (email-format.com) → L4 (SearXNG)
    Safe to stop at any point — email_searched_at is stamped after each person.
    """
    try:
        conn     = sqlite3.connect(DB_PATH, check_same_thread=False)
        db_init(conn)
        log_fn   = _make_log(q_out)
        smtp     = SmtpVerifier(log=log_fn)
        crawler  = WebsiteEmailCrawler(log=log_fn)
        efmt     = EmailFormatPatternEmail(mv_verifier=smtp, log=log_fn)

        total = len(people_data)

        for i, row in enumerate(people_data, 1):
            if stop_event.is_set():
                break

            (person_id, domain, company_name,
             raw_first, raw_last, full_name,
             title, li_url, _source) = row

            first, last = _split_name(full_name, raw_first, raw_last)

            q_out.put(("current", full_name or f"{first} {last}"))

            person = Person(
                first        = first,
                last         = last,
                title        = title        or "",
                domain       = domain       or "",
                company_name = company_name or "",
                linkedin_url = li_url       or "",
            )

            result: Optional[EmailResult] = None
            layer = ""
            dbg   = {
                "person":  full_name or f"{first} {last}",
                "domain":  domain,
                "title":   title,
                "tried":   [],
                "layer":   "",
                "email":   "",
            }

            # ── L1: website crawler ───────────────────────────────────────────
            try:
                result = crawler.find_email(person)
                dbg["tried"].append("L1-Site")
            except Exception as exc:
                log_fn("L1", f"  Error: {exc}")

            if result:
                layer = "L1-Site"

            # ── L2: email-format.com pattern ──────────────────────────────────
            if not result:
                try:
                    result = efmt.find_email(person)
                    dbg["tried"].append("L2-EFmt")
                except Exception as exc:
                    log_fn("L2", f"  Error: {exc}")

                if result:
                    layer = "L2-EFmt"

            # ── L4: SearXNG search ────────────────────────────────────────────
            if not result:
                try:
                    result = _searxng_email_search(person)
                    dbg["tried"].append("L4-Search")
                except Exception as exc:
                    log_fn("L4", f"  Error: {exc}")

                if result:
                    layer = "L4-Search"

            # ── Final generic-email guard ─────────────────────────────────────
            if result and is_generic_email(result.email):
                dbg["tried"].append("GENERIC-REJECT")
                log_fn("GUARD", f"  Rejected generic: {result.email}")
                result = None
                layer  = ""

            # ── Confirmed-only gate (L2 risky/unverified guesses are dropped) ─
            if result and not is_confirmed_lead(result, layer):
                dbg["tried"].append(f"{layer}-UNCONFIRMED")
                log_fn("GUARD", f"  Rejected unconfirmed ({layer}): {result.email}")
                result = None
                layer  = ""

            # ── Save result ───────────────────────────────────────────────────
            dbg["layer"] = layer
            if result:
                dbg["email"] = result.email
                lead = {
                    "email":        result.email,
                    "email_source": result.label,
                    "full_name":    full_name or f"{first} {last}",
                    "first_name":   first,
                    "last_name":    last,
                    "title":        title        or "",
                    "company":      company_name or "",
                    "domain":       domain       or "",
                    "country":      "",
                    "linkedin_url": li_url       or "",
                    "source_url":   "",
                }
                db_insert_lead(conn, lead)
                q_out.put(("lead", {**lead, "layer": layer}))
            else:
                q_out.put(("no_email", {"full_name": full_name, "domain": domain}))

            # Stamp done — safe resume point
            db_mark_person_email_done(conn, person_id)
            q_out.put(("progress", {"processed": i, "total": total}))
            q_out.put(("debug", dbg))

        conn.close()
        q_out.put(("done", {}))

    except Exception as exc:
        q_out.put(("error", str(exc)))


# ══════════════════════════════════════════════════════════════════════════════
# BUTTON HANDLERS
# ══════════════════════════════════════════════════════════════════════════════

if run_btn and not st.session_state.s4_running:
    conn2 = sqlite3.connect(DB_PATH)
    db_init(conn2)
    people_data = db_load_people_without_email(conn2)
    conn2.close()

    if people_data:
        stop_ev = threading.Event()
        q       = queue.Queue()

        st.session_state.s4_running    = True
        st.session_state.s4_done       = False
        st.session_state.s4_queue      = q
        st.session_state.s4_stop_event = stop_ev
        st.session_state.s4_processed  = 0
        st.session_state.s4_total      = len(people_data)
        st.session_state.s4_found      = 0
        st.session_state.s4_not_found  = 0
        st.session_state.s4_start_time = time.time()
        st.session_state.s4_error      = ""
        st.session_state.s4_leads      = []
        st.session_state.s4_debug_log  = []
        st.session_state.s4_current    = ""

        t = threading.Thread(
            target=_run_step4,
            args=(people_data, q, stop_ev),
            daemon=True,
        )
        t.start()
        st.rerun()

if stop_btn and st.session_state.s4_running:
    if st.session_state.s4_stop_event:
        st.session_state.s4_stop_event.set()
    st.session_state.s4_running = False
    st.session_state.s4_done    = True

# ── Queue drain ────────────────────────────────────────────────────────────────
if st.session_state.s4_queue:
    q = st.session_state.s4_queue
    while not q.empty():
        try:
            msg_type, payload = q.get_nowait()
        except queue.Empty:
            break

        if msg_type == "current":
            st.session_state.s4_current = payload

        elif msg_type == "lead":
            st.session_state.s4_found += 1
            st.session_state.s4_leads.append(payload)

        elif msg_type == "no_email":
            st.session_state.s4_not_found += 1

        elif msg_type == "progress":
            st.session_state.s4_processed = payload["processed"]
            st.session_state.s4_total     = payload["total"]

        elif msg_type == "debug":
            st.session_state.s4_debug_log.append(payload)

        elif msg_type == "done":
            st.session_state.s4_running = False
            st.session_state.s4_done    = True

        elif msg_type == "error":
            st.session_state.s4_running = False
            st.session_state.s4_error   = payload

if st.session_state.s4_running:
    # 1.2s (was 0.5s) — see pages/1_Domains.py for why: fewer full-page
    # reruns during a long scan means less risk of starving the
    # heartbeat ping past the watchdog's shutdown timeout.
    time.sleep(1.2)
    st.rerun()
elif st.session_state.s4_done and st.session_state.s4_queue is not None:
    st.session_state.s4_queue = None
    st.rerun()

# ══════════════════════════════════════════════════════════════════════════════
# HTML REPORT GENERATOR
# ══════════════════════════════════════════════════════════════════════════════

def _make_leads_html(leads: list) -> str:
    """Generate a self-contained dark-themed HTML report for the leads list."""
    now_str   = datetime.now().strftime("%Y-%m-%d %H:%M")
    total     = len(leads)

    src_counts: dict = {}
    for lead in leads:
        src = lead.get("email_source", "Unknown") or "Unknown"
        for k in ("Site", "EFmt", "Search", "PatVfy"):
            if k in src:
                src_counts[k] = src_counts.get(k, 0) + 1
                break
        else:
            src_counts["Other"] = src_counts.get("Other", 0) + 1

    _SRC_LABELS = {
        "Site":   ("Site Crawl",   "#34d399"),
        "EFmt":   ("Email Format", "#60a5fa"),
        "Search": ("Search",       "#c084fc"),
        "PatVfy": ("SMTP Brute",   "#fb923c"),
    }
    stat_cards = f'<div class="card"><div class="card-val blue">{total}</div><div class="card-lbl">Total Leads</div></div>'
    for k, (lbl, col) in _SRC_LABELS.items():
        cnt = src_counts.get(k, 0)
        if cnt:
            stat_cards += f'<div class="card"><div class="card-val" style="color:{col}">{cnt}</div><div class="card-lbl">{lbl}</div></div>'

    _SRC_COLOUR = {"Site": "#34d399", "EFmt": "#60a5fa", "Search": "#c084fc", "PatVfy": "#fb923c"}

    rows_html = ""
    for i, lead in enumerate(leads, 1):
        name    = lead.get("full_name",    "") or "—"
        title   = lead.get("title",        "") or "—"
        company = lead.get("company",      "") or "—"
        email   = lead.get("email",        "") or "—"
        domain  = lead.get("domain",       "") or ""
        li      = lead.get("linkedin_url", "") or ""
        src_lbl = lead.get("email_source", "") or ""

        src_col = "#888"
        for k, col in _SRC_COLOUR.items():
            if k in src_lbl:
                src_col = col
                break
        src_badge = (f'<span style="background:{src_col}22;color:{src_col};border:1px solid {src_col}44;'
                     f'border-radius:4px;padding:2px 7px;font-size:0.72rem">{src_lbl}</span>')

        li_link  = f'<a href="{li}" target="_blank" style="color:#60a5fa;text-decoration:none">🔗</a>' if li else "—"
        dom_link = (f'<a href="https://{domain}" target="_blank" style="color:#888;font-size:0.8em;'
                    f'text-decoration:none">{domain}</a>') if domain else "—"

        rows_html += f"""
        <tr class="data-row">
          <td style="color:#555;padding:9px 14px">{i}</td>
          <td style="font-weight:600;color:#e8f4f8;padding:9px 14px">{name}</td>
          <td style="color:#a8d8ea;padding:9px 14px">{title}</td>
          <td style="padding:9px 14px;color:#ccc">{company}</td>
          <td style="padding:9px 14px;color:#34d399;font-family:monospace">{email}</td>
          <td style="padding:9px 14px">{src_badge}</td>
          <td style="padding:9px 14px">{dom_link}</td>
          <td style="padding:9px 14px;text-align:center">{li_link}</td>
        </tr>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>LocReach — Leads</title>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body   {{ background: #0f1117; color: #ccc; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; padding: 32px 24px; }}
    h1     {{ color: #e8f4f8; font-size: 1.6rem; margin-bottom: 4px; }}
    .meta  {{ color: #555; font-size: 0.85rem; margin-bottom: 28px; }}
    .cards {{ display: flex; gap: 14px; flex-wrap: wrap; margin-bottom: 28px; }}
    .card  {{ background: #1e2130; border: 1px solid #2e3250; border-radius: 10px; padding: 14px 24px; text-align: center; min-width: 120px; }}
    .card-val {{ font-size: 1.8rem; font-weight: 700; }}
    .card-lbl {{ font-size: 0.72rem; color: #888; margin-top: 4px; }}
    .blue  {{ color: #60a5fa; }}
    table  {{ width: 100%; border-collapse: collapse; background: #1a1d2e; border-radius: 8px; overflow: hidden; font-size: 0.85rem; }}
    thead th {{ background: #1e2130; color: #a8d8ea; padding: 11px 14px; text-align: left; border-bottom: 2px solid #2e3250; position: sticky; top: 0; }}
    .data-row:hover {{ background: #1e2130; }}
    td {{ border-bottom: 1px solid #1e2130; }}
    .scroll {{ overflow-x: auto; border-radius: 8px; }}
    input#search {{ background: #1e2130; border: 1px solid #2e3250; border-radius: 6px; color: #ccc;
                    padding: 8px 14px; font-size: 0.9rem; width: 280px; margin-bottom: 14px; outline: none; }}
    input#search:focus {{ border-color: #34d399; }}
  </style>
</head>
<body>
  <h1>📧 LocReach — Leads</h1>
  <div class="meta">Generated {now_str}</div>

  <div class="cards">
    {stat_cards}
  </div>

  <input id="search" type="text" placeholder="Filter by name, email, company…" oninput="filterTable(this.value)">

  <div class="scroll">
    <table id="leads-table">
      <thead>
        <tr>
          <th>#</th>
          <th>Name</th>
          <th>Title</th>
          <th>Company</th>
          <th>Email</th>
          <th>Source</th>
          <th>Domain</th>
          <th style="text-align:center">LI</th>
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
# RESULTS TABLE
# ══════════════════════════════════════════════════════════════════════════════

display_leads = list(st.session_state.s4_leads)

if not display_leads and not st.session_state.s4_running and not st.session_state.s4_done:
    st.info("No leads yet. Press **▶️ Find Emails** to start searching.")

if display_leads:
    section_label("📋", f"Leads ({len(display_leads)})")

    html_rows = ""
    for lead in display_leads:
        li_cell = link_icon(lead.get("linkedin_url", ""))
        src = lead.get("layer") or lead.get("email_source", "")
        html_rows += (
            f"<tr>"
            f'<td class="lr-cell-strong">{lead.get("full_name","")}</td>'
            f'<td class="lr-mono">{lead.get("email","")}</td>'
            f'<td>{lead.get("title","")}</td>'
            f'<td class="lr-muted">{lead.get("domain","")}</td>'
            f'<td>{source_badge(src)}</td>'
            f'<td style="text-align:center">{li_cell}</td>'
            f"</tr>"
        )

    render_table(
        ["Name", "Email", "Title", "Domain", "Source", "LI"],
        html_rows,
        max_height="520px",
    )

# ── All leads in the DB (read-only, Jinja-rendered) ─────────────────────────────
# Rendered from templates/_db_leads_embed.html with real data and embedded as a
# static iframe. Read-only, so the Jinja/Tailwind template needs no Python callback.
if not st.session_state.s4_running:
    _lconn = sqlite3.connect(DB_PATH)
    db_init(_lconn)
    _db_leads = db_load_leads(_lconn)
    _lconn.close()
    if _db_leads:
        components.html(
            render_leads_db_table(_db_leads),
            height=table_embed_height(len(_db_leads)),
            scrolling=False,
        )

# ── Export ─────────────────────────────────────────────────────────────────────
if display_leads:
    section_label("📥", "Export")
    exp_col1, exp_col2 = st.columns([1, 1])

    with exp_col1:
        html_bytes = _make_leads_html(display_leads).encode("utf-8")
        st.download_button(
            label="📄  Download HTML Report",
            data=html_bytes,
            file_name=f"Emails_results_{datetime.now().strftime('%Y-%m-%d')}.html",
            mime="text/html",
            use_container_width=True,
            type="primary",
        )

    with exp_col2:
        try:
            from export_excel import build_leads_excel_bytes
            xlsx_bytes = build_leads_excel_bytes(display_leads)
            st.download_button(
                label="📊  Download Excel (this run)",
                data=xlsx_bytes,
                file_name=f"locreach_leads_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )
            st.caption("Exports **this run's** leads only. Full DB export is on **Home**.")
        except Exception as _e:
            st.error(f"Excel export failed: {_e}")

# ── Debug expander ─────────────────────────────────────────────────────────────
if st.session_state.s4_debug_log:
    with st.expander(f"🔍 Debug log ({len(st.session_state.s4_debug_log)} entries)", expanded=False):
        for dbg in reversed(st.session_state.s4_debug_log[-50:]):
            found_icon = "✅" if dbg.get("email") else "⬜"
            layers_str = " → ".join(dbg.get("tried", []))
            email_str  = dbg.get("email", "—")
            st.markdown(
                f"{found_icon} **{dbg.get('person','')}** "
                f"(`{dbg.get('domain','')}`) — "
                f"layers: `{layers_str}` — "
                f"result: `{email_str}` "
                f"via **{dbg.get('layer','—')}**"
            )
