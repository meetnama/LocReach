"""
pages/1_Domains.py — LocReach Step 1: Find & Qualify Domains.

Merges discovery (SearXNG/Chrome/DDG search) with inline qualification
(scrape → quality check → score) into a single flow. Writes qualified
domains to the unified `domains` table.
"""
import os
import sqlite3
import threading
import queue
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

from sources.utils import (
    google_search, google_ai_overview, google_warmup, searxng_search, openserp_search,
    duckduckgo_search, bing_search,
    ensure_searxng, ensure_openserp, get_domain, _captcha_flag,
    CaptchaHit, google_in_cooldown, google_cooldown_remaining,
    running_on_cloud,
)
from sources.directory_scrape import (
    is_directory_scrape_target, scrape_directory_companies,
    directory_search_queries,
)
from db import (db_init, db_upsert_domain,
                db_mark_blocked_domain, db_load_blocked_domains,
                db_load_all_domain_names,
                db_demote_geo_rejects)
from step1_qualify import (
    cheap_screen_candidate, qualify_domain_fast, qualify_from_ai_overview,
    ai_overview_screen, serp_summary_verified,
)
from ui_theme import (
    inject_theme, page_header, step_indicator, stat_cards,
    section_label, render_table, tier_badge, link_icon,
)

# ── Paths ──────────────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH  = os.path.join(BASE_DIR, "leads.db")
LOG_DIR  = os.path.join(BASE_DIR, "logs")
STEP1_LOG = os.path.join(LOG_DIR, "step1_search.log")
_LOG_MAX_AGE_DAYS = 7

_SCAN_WORKERS = 4

# Diminishing-returns stop (unique new qualified / hour over a sliding window)
_DIM_WINDOW_SEC = 15 * 60
_DIM_MIN_TERMS = 3
_DIM_RATE_FLOOR = 12.0  # unique new qualified domains per hour

# Directory / “Top N” list pages mined as verified company sources
_MAX_DIRECTORY_SCRAPES = 12
_MAX_COMPANIES_PER_DIRECTORY = 40


def _ingest_verified_company(
    *,
    url: str,
    title: str,
    source: str,
    tier_label: str,
    skip: set,
    country: str,
    industry: str,
    keyword: str,
    wconn,
    db_lock,
    q_out: queue.Queue,
    kept_timestamps: list,
) -> tuple[str, int, int]:
    """
    Hygiene + qualify_from_ai_overview for a pre-verified company.
    Returns (outcome, dup_delta, blocked_delta) where outcome is
    'qualified' | 'rejected' | 'skip'.
    """
    keep, reason, domain = ai_overview_screen(
        url=url, skip_domains=skip, country=country,
    )
    if not keep:
        if reason == "blocked" and domain:
            with db_lock:
                db_mark_blocked_domain(wconn, domain)
        elif reason == "foreign_cctld" and domain:
            with db_lock:
                db_upsert_domain(wconn, {
                    "domain": domain,
                    "status": "failed",
                    "industry": industry,
                    "country": country,
                    "keyword": keyword,
                    "score_reasons": '["foreign_cctld"]',
                })
            skip.add(domain)
        q_out.put(("rejected", {
            "domain": domain or "?",
            "reason": reason or "blocked/filtered",
            "tier": tier_label,
        }))
        if reason == "duplicate":
            return "rejected", 1, 0
        return "rejected", 0, 1

    skip.add(domain)
    q_out.put(("scanning", domain))
    try:
        res = qualify_from_ai_overview(
            domain, industry, country, keyword,
            wconn, db_lock,
            company_name=title, title=title,
            source=source,
        )
    except Exception:
        skip.discard(domain)  # allow retry this run if upsert never happened
        return "skip", 0, 0
    if res.get("status") == "qualified":
        kept_timestamps.append(time.time())
        q_out.put(("qualified", res))
        return "qualified", 0, 0
    return "skip", 0, 0


def _step1_log_autoclean() -> None:
    """Drop the Step 1 search log if it is older than one week."""
    try:
        if os.path.isfile(STEP1_LOG):
            age_s = time.time() - os.path.getmtime(STEP1_LOG)
            if age_s > _LOG_MAX_AGE_DAYS * 86400:
                os.remove(STEP1_LOG)
    except OSError:
        pass


def _step1_log(msg: str) -> None:
    """Append a line to the local Step 1 search log (not shown in the UI)."""
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        with open(STEP1_LOG, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  {msg}\n")
    except OSError:
        pass


def _render_progress(ph, fraction: float) -> None:
    """One custom progress track — avoids Streamlit+theme CSS double-bar look."""
    pct = int(round(max(0.0, min(1.0, fraction)) * 100))
    ph.markdown(
        f'<div role="progressbar" aria-valuemin="0" aria-valuemax="100" '
        f'aria-valuenow="{pct}" '
        f'style="width:100%;height:8px;border-radius:999px;'
        f'background:#1e293b;overflow:hidden;margin:0.35rem 0 0.6rem 0;">'
        f'<div style="width:{pct}%;height:100%;border-radius:999px;'
        f'background:linear-gradient(90deg,#3b82f6,#a855f7);"></div></div>',
        unsafe_allow_html=True,
    )




inject_theme()

# ── Session state ──────────────────────────────────────────────────────────────
for k, v in {
    "s1_running":        False,
    "s1_done":           False,
    "s1_qualified":      [],       # list of result dicts
    "s1_rejected_log":   [],
    "s1_query_log":      [],
    "s1_queue":          None,
    "s1_current_query":  "",
    "s1_current_page":   1,
    "s1_queries_done":   0,
    "s1_checked":        0,        # sites actually scraped/scored
    "s1_failed":         0,
    "s1_unreachable":    0,
    "s1_filtered":       0,        # blocked / industry mismatch / dup (not scraped)
    "s1_target":         0,        # global company target for this run
    "s1_error":          "",
    "s1_start_time":     None,
    "s1_stop_event":     None,
    "s1_current_engine": "",       # last engine used for current page
    "s1_engine_note":    "",
    "s1_stop_reason":    "",       # target_met | check_budget | search_exhausted | diminishing_returns | stopped
}.items():
    if k not in st.session_state:
        st.session_state[k] = v

_conn = sqlite3.connect(DB_PATH, check_same_thread=False)
db_init(_conn)

# ══════════════════════════════════════════════════════════════════════════════
# SIDEBAR — search options (adapted from Domain_Discovery.py)
# ══════════════════════════════════════════════════════════════════════════════

_INDUSTRY_RAW = {
    "All Industries":     None,
    "E-commerce":         "e-commerce",
    "Education":          "education",
    "Financial":          "financial",
    "Gaming":             "gaming",
    "Legal":              "legal",
    "Localization":       "localization",
    "Marketing":          "marketing",
    "Media / Subtitling": "subtitling",
    "Medical / Pharma":   "medical",
    "Software / Tech":    "software",
    "Translation":        "translation",
}
INDUSTRY_OPTIONS = _INDUSTRY_RAW

COUNTRY_LIST = ["All Countries"] + sorted([
    "Argentina", "Australia", "Austria", "Belgium", "Brazil",
    "Canada", "Chile", "China", "Colombia", "Czech Republic",
    "Denmark", "Egypt", "Finland", "France", "Germany", "Greece",
    "Hungary", "India", "Indonesia", "Ireland", "Israel", "Italy",
    "Japan", "Kenya", "Malaysia", "Mexico", "Netherlands",
    "New Zealand", "Nigeria", "Norway", "Pakistan", "Peru",
    "Philippines", "Poland", "Portugal", "Romania", "Russia",
    "Saudi Arabia", "Singapore", "South Africa", "South Korea",
    "Spain", "Sweden", "Switzerland", "Thailand", "Turkey",
    "UAE", "Ukraine", "United Kingdom", "United States",
])

# Top cities used for templates 11–15 (approx. largest by metro / business activity)
MAJOR_CITIES = {
    "Argentina":       ["Buenos Aires", "Córdoba", "Rosario"],
    "Australia":       ["Sydney", "Melbourne", "Brisbane"],
    "Austria":         ["Vienna", "Graz", "Linz"],
    "Belgium":         ["Brussels", "Antwerp", "Ghent"],
    "Brazil":          ["São Paulo", "Rio de Janeiro", "Brasília"],
    "Canada":          ["Toronto", "Vancouver", "Montreal"],
    "Chile":           ["Santiago", "Valparaíso", "Concepción"],
    "China":           ["Shanghai", "Beijing", "Shenzhen"],
    "Colombia":        ["Bogotá", "Medellín", "Cali"],
    "Czech Republic":  ["Prague", "Brno", "Ostrava"],
    "Denmark":         ["Copenhagen", "Aarhus", "Odense"],
    "Egypt":           ["Cairo", "Alexandria", "Giza"],
    "Finland":         ["Helsinki", "Espoo", "Tampere"],
    "France":          ["Paris", "Lyon", "Marseille"],
    "Germany":         ["Berlin", "Munich", "Hamburg"],
    "Greece":          ["Athens", "Thessaloniki", "Patras"],
    "Hungary":         ["Budapest", "Debrecen", "Szeged"],
    "India":           ["Mumbai", "Delhi", "Bangalore"],
    "Indonesia":       ["Jakarta", "Surabaya", "Bandung"],
    "Ireland":         ["Dublin", "Cork", "Galway"],
    "Israel":          ["Tel Aviv", "Jerusalem", "Haifa"],
    "Italy":           ["Milan", "Rome", "Turin"],
    "Japan":           ["Tokyo", "Osaka", "Yokohama"],
    "Kenya":           ["Nairobi", "Mombasa", "Kisumu"],
    "Malaysia":        ["Kuala Lumpur", "George Town", "Johor Bahru"],
    "Mexico":          ["Mexico City", "Guadalajara", "Monterrey"],
    "Netherlands":     ["Amsterdam", "Rotterdam", "The Hague"],
    "New Zealand":     ["Auckland", "Wellington", "Christchurch"],
    "Nigeria":         ["Lagos", "Abuja", "Kano"],
    "Norway":          ["Oslo", "Bergen", "Trondheim"],
    "Pakistan":        ["Karachi", "Lahore", "Islamabad"],
    "Peru":            ["Lima", "Arequipa", "Trujillo"],
    "Philippines":     ["Manila", "Quezon City", "Cebu City"],
    "Poland":          ["Warsaw", "Kraków", "Wrocław"],
    "Portugal":        ["Lisbon", "Porto", "Braga"],
    "Romania":         ["Bucharest", "Cluj-Napoca", "Timișoara"],
    "Russia":          ["Moscow", "Saint Petersburg", "Novosibirsk"],
    "Saudi Arabia":    ["Riyadh", "Jeddah", "Dammam"],
    "Singapore":       ["Singapore"],
    "South Africa":    ["Johannesburg", "Cape Town", "Durban"],
    "South Korea":     ["Seoul", "Busan", "Incheon"],
    "Spain":           ["Madrid", "Barcelona", "Valencia"],
    "Sweden":          ["Stockholm", "Gothenburg", "Malmö"],
    "Switzerland":     ["Zurich", "Geneva", "Basel"],
    "Thailand":        ["Bangkok", "Chiang Mai", "Phuket"],
    "Turkey":          ["Istanbul", "Ankara", "Izmir"],
    "UAE":             ["Dubai", "Abu Dhabi", "Sharjah"],
    "Ukraine":         ["Kyiv", "Kharkiv", "Odesa"],
    "United Kingdom":  ["London", "Manchester", "Birmingham"],
    "United States":   ["New York", "Los Angeles", "Chicago"],
}

_PAGE_SIZE = 10  # match typical SERP page size (15 falsely looked "short" and ended every term)
# Cap workers on Render free tier to avoid Chrome/HTTP OOM; local stays aggressive.
_ON_CLOUD = running_on_cloud()
_MAX_WORKERS = 12 if _ON_CLOUD else 200
_DEFAULT_WORKERS = 8 if _ON_CLOUD else 200
# When free engines wake cold / rate-limit, retry page-1 before burning the term bank.
_EMPTY_SERP_RETRIES = 3 if _ON_CLOUD else 1
_MAX_META_PAGES = 10  # deeper free-engine pagination when hunting volume
# Only stop paginating when a page returns fewer than this many hits (not when < page_size).
_MIN_PAGE_HITS = 5


def _max_pages_for(target: int) -> int:
    """Max SERP pages per search term — deep enough to get past top-10 duplicates."""
    return min(150, max(15, -(-target // _PAGE_SIZE) * 8))


def _check_budget_for(target: int) -> int:
    """
    Max sites to scrape before giving up. Old rule (target×3) capped 100-target
    runs at ~12 kept when keep-rate is ~4%. Use ~25× target, floor 800.
    """
    return min(15000, max(target * 25, 800))


def _meta_pages_for(target: int) -> int:
    """Free-engine pagination depth scales with volume target."""
    return min(25, max(_MAX_META_PAGES, target // 8))


def _expansion_queries(
    industry_slug: str,
    country_name: str,
    city_list: list[str],
    shortfall: int,
) -> list[str]:
    """Second-wave terms when the primary list keeps hitting the same top domains."""
    ind = industry_slug or "localization"
    ctry = country_name or ""
    qs: list[str] = []
    roles = (
        "bureau", "office", "studio", "vendor", "provider",
        "partner", "consultancy", "firm", "company",
    )
    for role in roles:
        qs.append(f"{ind} {role} {ctry}")
        qs.append(f"translation {role} {ctry}")
    for cty in city_list[:6]:
        qs += [
            f"translation company {cty}",
            f"language services {cty}",
            f"localization agency {cty}",
            f"مكتب ترجمة {cty}",
            f"شركة ترجمة {cty}",
        ]
    if ctry == "Egypt":
        qs += [
            "site:.eg translation agency",
            "site:.eg localization company",
            "site:.eg language services",
            "Egyptian translation services company",
            "certified translation office Egypt",
            "document translation Egypt company",
            "interpretation company Egypt",
            "localization services Cairo Egypt contact",
            "translation company Alexandria Egypt",
            "translation company Giza Egypt",
            "LSP Egypt contact",
            "language service provider Egypt email",
        ]
    cap = max(25, min(80, shortfall * 2))
    return list(dict.fromkeys(q for q in qs if q.strip()))[:cap]


def _rotation_extra_queries(
    industry_slug: str,
    country_name: str,
    city_list: list[str],
) -> list[str]:
    """Extra unused templates for auto-rotate coverage beyond primary + expansion."""
    ind = industry_slug or "localization"
    ctry = country_name or ""
    qs: list[str] = []
    niches = (
        "subtitling", "interpretation", "interpreting", "transcreation",
        "website localization", "software localization", "DTP translation",
        "legal translation", "medical translation", "certified translation",
        "audiovisual translation", "game localization",
    )
    for niche in niches:
        if ctry:
            qs.append(f"{niche} company {ctry}")
            qs.append(f"{niche} agency {ctry}")
        qs.append(f"{niche} {ind} {ctry}".strip())
    dirs = (
        f"{ind} companies directory {ctry}",
        f"list of {ind} companies {ctry}",
        f"top {ind} agencies {ctry}",
        f"{ind} vendors {ctry}",
        f"outsourced {ind} {ctry}",
    )
    qs.extend(dirs)
    for cty in city_list[:8]:
        qs += [
            f"{ind} near {cty}",
            f"best translation office {cty}",
            f"language service provider {cty}",
        ]
    if ctry == "Egypt":
        qs += [
            "شركات ترجمة معتمدة مصر",
            "مكتب ترجمة معتمدة القاهرة",
            "خدمات الترجمة الفورية مصر",
            "تعريب مواقع مصر",
            "site:.eg مكتب ترجمة",
            "site:.eg ترجمة معتمدة",
            "translators Egypt company website",
            "localization Egypt LinkedIn company",
        ]
    tld = {
        "Egypt": ".eg", "Saudi Arabia": ".sa", "UAE": ".ae",
        "United Arab Emirates": ".ae",
        "Germany": ".de", "France": ".fr", "United Kingdom": ".uk",
    }.get(ctry)
    if tld:
        qs += [
            f"site:{tld} {ind}",
            f"site:{tld} translation agency",
            f"site:{tld} language services",
        ]
    return list(dict.fromkeys(q for q in qs if q and q.strip()))


def _build_template_bank(
    primary: list[str],
    industry_slug: str,
    country_name: str,
    city_list: list[str],
    target: int,
) -> list[str]:
    """
    Ordered unused-template bank — verified-source queries FIRST, then normal.

    Priority:
      1. Directory / industry-dir site: queries (Proz, Clutch, GoodFirms, …)
      2. Primary Industry/Country/City terms
      3. Expansion + rotation extras (normal SERP volume hunt)
    """
    bank: list[str] = []
    # 1) Verified-source directories first (before normal search)
    bank.extend(directory_search_queries(industry_slug, country_name))
    # 2) User/primary market terms (also feed AI Overview / Local Pack / SERP summary)
    bank.extend(primary or [])
    shortfall = max(0, (target or 0) - len(bank))
    # 3) Normal volume expansion last
    bank.extend(
        _expansion_queries(industry_slug, country_name, city_list, shortfall or (target or 50))
    )
    bank.extend(_rotation_extra_queries(industry_slug, country_name, city_list))
    return list(dict.fromkeys(q for q in bank if q and q.strip()))


def _result_verified_priority(
    r: dict,
    *,
    industry_slug: str = "",
    country: str = "",
) -> int:
    """
    Sort key for SERP hits — lower = higher priority (verified techniques first).
      0 AI Overview · 1 Local Pack · 2 Directory · 3 SERP summary · 9 normal
    """
    src = (r or {}).get("source") or ""
    if src == "ai_overview":
        return 0
    if src == "local_pack":
        return 1
    url = (r or {}).get("link") or ""
    title = (r or {}).get("title") or ""
    snippet = (r or {}).get("snippet") or ""
    if is_directory_scrape_target(url, title):
        return 2
    dom = get_domain(url) or ""
    if dom and serp_summary_verified(
        title, snippet, industry_slug, country=country, domain=dom,
    ):
        return 3
    return 9


def _dim_returns_rate(
    kept_timestamps: list[float],
    terms_done_at: list[float],
    run_start: float,
    now: float | None = None,
) -> tuple[float, int, int]:
    """Return (unique_new_per_hour, kept_in_window, terms_in_window)."""
    now = now if now is not None else time.time()
    window_start = now - _DIM_WINDOW_SEC
    kept_in = sum(1 for t in kept_timestamps if t >= window_start)
    terms_in = sum(1 for t in terms_done_at if t >= window_start)
    window_secs = min(_DIM_WINDOW_SEC, max(1.0, now - run_start))
    rate = kept_in / (window_secs / 3600.0)
    return rate, kept_in, terms_in


page_header("🌐", "Step 1 — Find & Qualify Domains",
            "Search, scrape, score, and qualify companies for outreach.")
step_indicator(1)

with st.expander("⚙️ Search Settings", expanded=True):

    st.markdown("**Industry**")
    industry = st.selectbox(
        "Industry", options=list(INDUSTRY_OPTIONS.keys()),
        label_visibility="collapsed",
    )

    st.markdown("")
    st.markdown("**Country**")
    country = st.selectbox(
        "Country", options=COUNTRY_LIST,
        label_visibility="collapsed",
    )
    # Always keep only companies based in the selected country (geo gate on).
    strict_location = True

    st.markdown("")
    st.markdown("**Search term** *(optional)*")
    keyword = st.text_input(
        "Keyword",
        placeholder="e.g. marketing companies in egypt",
        label_visibility="collapsed",
    )
    keywords_only = st.checkbox(
        "Use ONLY this written search term",
        value=False,
        help=(
            "Checked: run only what you typed (exact text). "
            "Unchecked: keep the auto-generated Industry/Country/City terms "
            "and add what you typed as an extra search term."
        ),
    )
    st.caption(
        "Checked → only your text. Unchecked → auto terms **plus** your text as one more term. "
        "Comma-separate for several custom terms."
    )

    st.markdown("")
    st.markdown("**Target companies (total)**")

    def _fmt_eta(seconds: int) -> str:
        if seconds < 60:
            return f"~{seconds}s"
        mins = max(1, round(seconds / 60))
        if mins < 60:
            return f"~{mins} min"
        hrs, rem = divmod(mins, 60)
        return f"~{hrs}h {rem}m" if rem else f"~{hrs}h"

    # Calibrated from live Egypt run: 865 sites checked → 86 kept in 28m 7s
    # at 48 workers (~10% keep rate, ~2s wall per checked site). Old formula
    # used target×18s/workers and ignored failed/unreachable volume.
    _KEEP_RATE_TYPICAL = 0.10
    _KEEP_RATE_HARD = 0.05
    _WALL_SEC_PER_CHECK_AT_48 = 1.95
    _REF_WORKERS = 48

    def _expected_checks(n: int, keep_rate: float) -> int:
        raw = max(n, round(n / max(0.01, keep_rate)))
        return min(_check_budget_for(n), raw)

    def _eta_wall(
        n: int,
        workers: int,
        n_terms: int = 15,
        keep_rate: float = _KEEP_RATE_TYPICAL,
    ) -> int:
        checks = _expected_checks(n, keep_rate)
        # Scale from 48-worker empirical baseline (SERP wait baked in).
        qualify = (
            checks
            * _WALL_SEC_PER_CHECK_AT_48
            * (_REF_WORKERS / max(1, workers))
        )
        # Extra query-bank terms add a little SERP time (mostly overlapped).
        search_slack = max(0, n_terms - 20) * 2
        return max(90, int(qualify + search_slack))

    def _eta_range(n: int, workers: int, n_terms: int = 15) -> str:
        mid = _eta_wall(n, workers, n_terms, _KEEP_RATE_TYPICAL)
        hi = _eta_wall(n, workers, n_terms, _KEEP_RATE_HARD)
        lo = max(60, int(mid * 0.85))
        hi = max(lo + 60, hi)
        return f"{_fmt_eta(lo)} – {_fmt_eta(hi)}"

    depth_choice = st.radio(
        "Depth",
        options=["100 companies", "500 companies", "Custom"],
        label_visibility="collapsed",
    )
    depth = None
    depth_error = ""
    if depth_choice == "100 companies":
        depth = 100
    elif depth_choice == "500 companies":
        depth = 500
    else:
        custom_raw = st.text_input(
            "Custom company count",
            value="",
            placeholder="Enter a number (max 2000)",
            label_visibility="collapsed",
            key="s1_custom_depth",
        ).strip()
        if not custom_raw:
            depth_error = "Enter how many companies to find (max 2000)."
        elif not custom_raw.isdigit():
            depth_error = "Custom count must be a whole number."
        else:
            depth = int(custom_raw)
            if depth < 1 or depth > 2000:
                depth = None
                depth_error = "Custom count must be between 1 and 2000."

    if depth_error:
        st.caption(f"⚠️ {depth_error}")
    else:
        st.caption(
            "Stops after this many **qualified** companies are kept (or after up to ~25× that "
            "many sites have been checked). Already-**qualified** domains are skipped. "
            "**Strong** and **possible** sites are kept (LinkedIn helps score, not required)."
        )

    qualify_workers = _DEFAULT_WORKERS

    # Engine is always Smart (parallel free + Google gap-fill) — no UI control
    engine = "Smart (SearXNG∥OpenSERP → Google → Bing → DDG)"

    st.markdown("---")

    # ── Build final query list ──────────────────────────────────────────────
    ind_kw            = INDUSTRY_OPTIONS.get(industry)
    industry_selected = ind_kw is not None
    country_selected  = country != "All Countries"
    country_name      = country if country_selected else ""
    # Always use biggest / most famous cities for the selected country
    city_list = list(MAJOR_CITIES.get(country_name, [])) if country_selected else []

    # Support multiple keywords separated by commas or newlines
    kw_list = [k.strip() for k in keyword.replace("\n", ",").split(",") if k.strip()]
    kw                = kw_list[0] if kw_list else ""  # primary keyword for DB/logging

    final_queries = []

    def _queries_for_country(ind: str, ctry: str) -> list:
        # Diverse phrasings (not near-duplicates) so SERPs don't reshuffle the same 10 domains
        base = [
            f"{ind} companies in {ctry}",
            f"{ind} agency in {ctry}",
            f"{ind} services {ctry}",
            f"{ind} firm {ctry}",
            f"best {ind} companies {ctry}",
            f"{ind} service providers in {ctry}",
            f'"{ind}" "{ctry}" -linkedin.com -facebook.com',
            f"{ind} company contact {ctry}",
        ]
        # Localization/translation share a market — add sibling terms for volume
        if ind in ("localization", "translation", "subtitling"):
            base += [
                f"translation agency {ctry}",
                f"language services company {ctry}",
                f"LSP translation {ctry}",
                f"ترجمة شركة {ctry}" if ctry == "Egypt" else f"translation office {ctry}",
            ]
        return base

    def _queries_for_city(ind: str, cty: str) -> list:
        q = [
            f"{ind} companies in {cty}",
            f"{ind} agency {cty}",
            f"{ind} services {cty}",
            f"translation agency {cty}" if ind in ("localization", "translation") else f"{ind} business {cty}",
        ]
        return q

    if keywords_only:
        # Exact custom term(s) only — no Industry/Country/City templates
        final_queries.extend(kw_list)
    else:
        if industry_selected and country_selected:
            final_queries.extend(_queries_for_country(ind_kw, country_name))
        if industry_selected and city_list:
            for cty in city_list:
                final_queries.extend(_queries_for_city(ind_kw, cty))
        if not final_queries and country_selected and not industry_selected:
            final_queries = [
                f"companies in {country_name}",
                f"organizations in {country_name}",
            ]
        if not final_queries and city_list and not industry_selected:
            for cty in city_list:
                final_queries.extend([
                    f"companies in {cty}",
                    f"businesses in {cty}",
                ])
        # Custom text becomes an extra full search term (not merged into others)
        if kw_list:
            final_queries.extend(kw_list)

    final_queries = list(dict.fromkeys(q for q in final_queries if q.strip()))
    bank_preview = _build_template_bank(
        final_queries, ind_kw or "", country_name, city_list, depth or 0,
    ) if final_queries and depth else []
    ready = len(final_queries) > 0 and depth is not None

    if keywords_only and not kw_list:
        st.caption("Enter a search term when **Use ONLY this written search term** is checked.")
    elif industry_selected and not country_selected and not city_list and not kw_list:
        st.caption("Pick a **Country** (or enter a custom search term) to generate search terms.")
    elif ready:
        st.caption(
            f"**{len(final_queries)}** primary search terms · "
            f"**{len(bank_preview)}** in auto-rotate bank"
        )
        st.caption(
            f"⏱ **Estimated: {_eta_range(depth, qualify_workers, max(len(bank_preview), 1))}** "
            f"({depth} companies · {qualify_workers} workers)"
        )
        with st.expander("See search terms"):
            for q in bank_preview or final_queries:
                st.caption(f"• {q}")
    else:
        st.caption("Select an industry with a country, or enter a custom search term to begin.")

# ── Buttons ────────────────────────────────────────────────────────────────────
bcol1, bcol2, bcol3 = st.columns([2, 2, 4])
with bcol1:
    run_btn = st.button(
        "▶️  Find & Qualify Domains",
        disabled=st.session_state.s1_running or not ready,
        use_container_width=True,
        type="primary",
    )
with bcol2:
    stop_btn = st.button(
        "⏹  Stop",
        disabled=not st.session_state.s1_running,
        use_container_width=True,
    )
with bcol3:
    status_ph = st.empty()

# ── Status + progress ──────────────────────────────────────────────────────────
# Verbose engine / page / term details go to logs/step1_search.log — not the UI.
_progress_ph = st.empty()

if st.session_state.s1_error:
    status_ph.error(f"Error: {st.session_state.s1_error}")

elif st.session_state.s1_running:
    cq         = st.session_state.s1_current_query
    qdone      = st.session_state.s1_queries_done
    cur_page   = st.session_state.s1_current_page
    qtotal     = len(final_queries)
    max_pages  = st.session_state.get("s1_max_pages") or _max_pages_for(depth or 100)
    elapsed    = int(time.time() - (st.session_state.s1_start_time or time.time()))
    mins, secs = divmod(elapsed, 60)
    elapsed_str = f"{mins}m {secs}s" if mins else f"{secs}s"
    n_kept = len(st.session_state.s1_qualified)

    if not cq:
        status_ph.info(f"Working… **{n_kept}** qualified so far — {elapsed_str}")
    else:
        status_ph.info(f"Searching… **{n_kept}** qualified so far — {elapsed_str}")

    tgt = st.session_state.s1_target or depth or 0
    if tgt:
        progress = min(1.0, n_kept / tgt)
    else:
        progress = (qdone + (cur_page - 1) / max_pages) / qtotal if qtotal else 0
    _render_progress(_progress_ph, progress)

elif st.session_state.s1_done:
    n = len(st.session_state.s1_qualified)
    elapsed = int(time.time() - (st.session_state.s1_start_time or time.time()))
    mins, secs = divmod(elapsed, 60)
    elapsed_str = f"{mins}m {secs}s" if mins else f"{secs}s"
    failed  = st.session_state.s1_failed
    unreach = st.session_state.s1_unreachable
    target_n = st.session_state.s1_target or 0
    reason = st.session_state.get("s1_stop_reason") or ""
    status_ph.success(
        f"Done — **{n} qualified** in {elapsed_str}"
        f" ({failed} failed · {unreach} unreachable)."
    )
    _render_progress(_progress_ph, 1.0)
    if target_n and n >= target_n:
        st.success(
            f"✅ Target reached — **{n}/{target_n} qualified**. "
            "Scroll down to review, or move to **Step 2**."
        )
    elif reason == "check_budget":
        st.warning(
            f"⏹️ Scrape budget reached (**{n}/{target_n} qualified**, "
            f"**{checked}** sites checked). Lower the target, broaden "
            "search terms, or wipe old qualified rows if re-testing the same market."
        )
    elif reason == "diminishing_returns":
        st.warning(
            f"⏹️ SERP yield flattened — **{n}/{target_n} qualified** "
            "(unique-new rate dropped). Try another country/keyword, "
            "or export what you have and continue coverage later."
        )
    elif reason == "stopped":
        st.info(f"⏹️ Stopped by you — **{n}** qualified so far.")
    elif reason in ("error", "serp_unavailable"):
        err = st.session_state.s1_error or "Search engines unavailable."
        st.error(f"⏹️ Step 1 aborted — {err}")
    elif target_n and n < target_n:
        # Summarize this-run SERP yield so "0 checked" is not a black box.
        qlog = st.session_state.get("s1_query_log") or []
        raw_sum = sum(int(x.get("raw") or 0) for x in qlog if isinstance(x, dict))
        filt_sum = sum(int(x.get("blocked") or 0) for x in qlog if isinstance(x, dict))
        dup_sum = sum(int(x.get("dup") or 0) for x in qlog if isinstance(x, dict))
        st.warning(
            f"⏹️ Search ran out of new candidates before the target "
            f"(**{n}/{target_n} qualified**). "
            f"This run: **{raw_sum}** SERP hits · **{checked}** checked · "
            f"**{filt_sum}** filtered · **{dup_sum}** already in DB. "
            "If SERP hits are 0, wait for SearXNG/OpenSERP to wake or cool down; "
            "if filtered is high, broaden industry/country."
        )
    else:
        st.success(
            f"✅ **{n} qualified companies** — scroll down to review, "
            "or move to **Step 2** to find people."
        )

else:
    status_ph.info("Select an industry or country and press Find & Qualify.")

# ── Stats ──────────────────────────────────────────────────────────────────────
qualified = st.session_state.s1_qualified
qdone     = st.session_state.s1_queries_done
qtotal    = len(final_queries)
checked   = st.session_state.s1_checked
target    = st.session_state.s1_target or (depth or 0)
filtered  = st.session_state.s1_filtered

# Always show counters after a run (even all-zeros) so empty SERP is visible.
if checked > 0 or filtered > 0 or st.session_state.s1_running or st.session_state.s1_done:
    check_cap = _check_budget_for(target) if target else 0
    stat_cards([
        ("Qualified",   f"{len(qualified)} / {target}" if target else len(qualified), "qualified"),
        ("Checked",     f"{checked} / {check_cap}" if check_cap else checked,         "signal"),
        ("Failed",      st.session_state.s1_failed,                                    "pipeline"),
        ("Unreachable", st.session_state.s1_unreachable,                               "slate"),
    ])
    if st.session_state.s1_done and filtered:
        st.caption(f"Filtered without opening (blocked / geo / junk / dup): **{filtered}**")

# ══════════════════════════════════════════════════════════════════════════════
# BACKGROUND WORKER
# ══════════════════════════════════════════════════════════════════════════════

def _search_page(query: str, num: int, page: int,
                 use_searxng: bool, use_google: bool, use_ddg: bool,
                 q_out: queue.Queue | None = None):
    """
    Unattended search for ONE page of the CURRENT term (never switches terms).

    Returns (results, tier, meta).

    Speed path (enterprise throughput):
      1. Race SearXNG ∥ OpenSERP in parallel — merge + dedupe
      2. Google Chrome gap-fill when free engines are dry (and not cooling)
      3. Bing Chrome → DDG HTML last resort
    """
    meta = {
        "captcha": False, "xng_tried": False, "xng_ok": False,
        "xng_down": False, "fallback": False, "chain": [],
    }

    def _note(msg: str):
        if q_out is not None and msg:
            q_out.put(("engine_note", msg))

    def _chain_status(label: str, st: dict, n: int = 0) -> str:
        """Prefer blocked/empty/down over a bare :0 so debug logs are honest."""
        status = (st or {}).get("status") or ""
        if n > 0:
            return f"{label}:{n}"
        if status in ("blocked", "down", "error", "empty"):
            detail = (st or {}).get("detail") or ""
            short = detail.replace(" → ", "; ")[:80] if detail else ""
            return f"{label}:{status}" + (f"({short})" if short else "")
        return f"{label}:0"

    def _dedupe(rows: list) -> list:
        seen: set[str] = set()
        out = []
        for r in rows or []:
            link = (r or {}).get("link", "") or ""
            key = get_domain(link) or link
            if not key or key in seen:
                continue
            seen.add(key)
            out.append(r)
        return out

    # ── 1. Race free engines ∥ Google panels (page-1) ─────────────────────────
    # Panels run in parallel so verified AIO/Local Pack are ready ASAP, then
    # prepended ahead of organics. Site qualify never starts until after harvest.
    xng_rows: list = []
    xng_st: dict = {}
    xng_err: Exception | None = None
    osp_rows: list = []
    osp_st: dict = {}
    osp_err: Exception | None = None
    panel_rows: list = []

    def _run_xng():
        st: dict = {}
        try:
            rows = searxng_search(query, num=num, page=page, status_out=st)
            return rows or [], st, None
        except Exception as exc:
            return [], st, exc

    def _run_osp():
        st: dict = {}
        try:
            rows = openserp_search(query, num=num, page=page, status_out=st)
            return rows or [], st, None
        except Exception as exc:
            return [], st, exc

    def _run_panels(extra_organic: list):
        try:
            rows = google_ai_overview(query, extra_organic=extra_organic or []) or []
            return rows, None
        except CaptchaHit as exc:
            return [], exc
        except Exception as exc:
            return [], exc

    # Race free engines first; then panels with their organics so name→URL
    # resolution works (racing with extra_organic=[] starved AIO links).
    race_jobs = {}
    with ThreadPoolExecutor(max_workers=2) as race:
        if use_searxng:
            meta["xng_tried"] = True
            race_jobs["xng"] = race.submit(_run_xng)
        race_jobs["osp"] = race.submit(_run_osp)
        for fut in as_completed(race_jobs.values()):
            name = next(k for k, v in race_jobs.items() if v is fut)
            rows, st, err = fut.result()
            if name == "xng":
                xng_rows, xng_st, xng_err = rows, st, err
            else:
                osp_rows, osp_st, osp_err = rows, st, err

    if page == 1 and use_google and not google_in_cooldown():
        organic_for_panels = _dedupe(list(xng_rows) + list(osp_rows))
        rows, err = _run_panels(organic_for_panels)
        if isinstance(err, CaptchaHit):
            meta["captcha"] = True
            meta["chain"].append("AIO:CAPTCHA")
            _note("Google panels skipped — CAPTCHA")
        elif err is not None:
            meta["chain"].append("AIO:error")
            _note(f"Google panels unavailable ({type(err).__name__})")
        else:
            panel_rows = rows or []
            if panel_rows:
                n_aio = sum(
                    1 for r in panel_rows if r.get("source") == "ai_overview"
                )
                n_pack = sum(
                    1 for r in panel_rows if r.get("source") == "local_pack"
                )
                meta["chain"].append(f"AIO:{n_aio}+Pack:{n_pack}")
                _note(
                    f"Priority panels — {n_aio} AI Overview + {n_pack} "
                    "Local Pack (before site qualify)"
                )

    if use_searxng:
        if xng_err is not None:
            meta["xng_down"] = True
            meta["chain"].append("SearXNG:down")
            _note(f"SearXNG unavailable — {xng_err}")
        elif xng_rows:
            meta["xng_ok"] = True
            meta["chain"].append(f"SearXNG:{len(xng_rows)}")
        else:
            meta["xng_ok"] = True
            meta["chain"].append(_chain_status("SearXNG", xng_st))
            if xng_st.get("status") == "blocked":
                _note(f"SearXNG blocked/upstream dry — {xng_st.get('detail', '')[:120]}")

    if osp_err is not None:
        meta["chain"].append("OpenSERP:down")
        _note(f"OpenSERP unavailable — {osp_err}")
    elif osp_rows:
        meta["chain"].append(f"OpenSERP:{len(osp_rows)}")
    else:
        meta["chain"].append(_chain_status("OpenSERP", osp_st))
        if osp_st.get("status") == "blocked":
            _note(f"OpenSERP blocked — {osp_st.get('detail', '')[:120]}")

    # Panels first, then free-engine organics (dedupe keeps panel rows)
    merged = _dedupe(list(panel_rows) + list(xng_rows) + list(osp_rows))

    if merged:
        if panel_rows and (xng_rows or osp_rows):
            if xng_rows and osp_rows:
                tier = "Panels+SearXNG+OpenSERP"
            elif xng_rows:
                tier = "Panels+SearXNG"
            else:
                tier = "Panels+OpenSERP"
        elif panel_rows:
            tier = "Google panels"
        elif xng_rows and osp_rows:
            tier = "SearXNG+OpenSERP"
        elif xng_rows:
            tier = "SearXNG"
        else:
            tier = "OpenSERP"
        if q_out is not None:
            q_out.put(("engine", tier))
            q_out.put(("engine_note", ""))
        return merged[:num], tier, meta

    meta["fallback"] = True

    # ── 2. Google Chrome gap-fill (when free engines were dry) ────────────────
    if use_google and not google_in_cooldown():
        try:
            results = google_search(query, num=num, page=page)
            if results:
                meta["chain"].append(f"Google:{len(results)}")
                if q_out is not None:
                    q_out.put(("engine", "Chrome+Google"))
                    q_out.put(("engine_note", "Google gap-fill (free engines dry)"))
                return results, "Chrome+Google", meta
            meta["chain"].append("Google:0")
        except CaptchaHit:
            meta["captcha"] = True
            meta["chain"].append("Google:CAPTCHA")
            _note(
                "Google CAPTCHA — free engines were dry; "
                "trying Bing→DDG (same term, no wait)"
            )
        except Exception as exc:
            meta["chain"].append("Google:error")
            _note(f"Google error — fallback ({type(exc).__name__})")
    elif use_google and google_in_cooldown():
        rem = google_cooldown_remaining()
        meta["chain"].append(f"Google:cooldown({rem}s)")
        _note(
            f"Google cooling {max(1, (rem + 59) // 60)}m — "
            "free engines dry; trying Bing→DDG"
        )

    # ── 3. Bing Chrome ────────────────────────────────────────────────────────
    if use_ddg:
        bing_st: dict = {}
        try:
            results = bing_search(query, num=num, page=page, status_out=bing_st)
            if results:
                meta["chain"].append(f"Bing:{len(results)}")
                if q_out is not None:
                    q_out.put(("engine", "Bing"))
                    q_out.put(("engine_note", "Bing Chrome fallback (same term)"))
                return results, "Bing", meta
            meta["chain"].append(_chain_status("Bing", bing_st))
            if bing_st.get("status") == "blocked":
                _note(
                    "Bing Chrome blocked (challenge), not empty — "
                    f"{bing_st.get('detail', '')[:120]}"
                )
        except Exception as exc:
            meta["chain"].append("Bing:error")
            _note(f"Bing Chrome failed — {type(exc).__name__}")

    # ── 4. DDG HTML last resort ───────────────────────────────────────────────
    if use_ddg and page == 1:
        ddg_st: dict = {}
        try:
            results = duckduckgo_search(
                query, num=num, status_out=ddg_st, bing_fallback=False,
            )
            if results:
                meta["chain"].append(f"DDG:{len(results)}")
                if q_out is not None:
                    q_out.put(("engine", "DuckDuckGo"))
                    q_out.put(("engine_note", "DDG HTML last resort (same term)"))
                return results, "DuckDuckGo", meta
            meta["chain"].append(_chain_status("DDG", ddg_st))
            if ddg_st.get("status") == "blocked":
                _note(f"DDG HTML blocked — {ddg_st.get('detail', '')[:120]}")
        except Exception as exc:
            meta["chain"].append("DDG:error")
            _note(f"DDG HTML failed — {type(exc).__name__}")

    chain = " → ".join(meta["chain"]) if meta["chain"] else "no engines tried"
    _note(f"No SERP hits — {chain}")
    return [], "none", meta


def _qualify_one(domain: str, industry: str, country: str, keyword: str,
                 conn: sqlite3.Connection, db_lock: threading.Lock,
                 industry_slug: str = "", google_title: str = "",
                 strict_location: bool = True) -> dict:
    """
    Fast path: HTTP homepage → ≤3 high-value pages → score → decide.
    No full-site crawl; Chrome only if HTTP homepage fails.
    """
    try:
        return qualify_domain_fast(
            domain, industry, country, keyword, conn, db_lock,
            industry_slug=industry_slug, google_title=google_title,
            strict_location=strict_location,
        )
    except Exception:
        try:
            with db_lock:
                db_upsert_domain(conn, {
                    "domain": domain,
                    "status": "unreachable",
                    "industry": industry,
                    "country": country,
                    "keyword": keyword,
                    "score_reasons": '["exception"]',
                })
        except Exception:
            pass
        return {
            "domain": domain, "status": "unreachable",
            "company_name": "", "linkedin_url": "",
            "industry": industry, "country": country,
            "keyword": keyword, "scanned_at": datetime.now().isoformat(),
        }


def _run_step1(queries: list, num: int, q_out: queue.Queue,
               stop_event: threading.Event,
               industry: str, country: str, keyword: str,
               engine: str = "Smart (SearXNG∥OpenSERP → Google → Bing → DDG)",
               industry_slug: str = "",
               workers: int = 24,
               strict_location: bool = True):
    """
    Background worker: SERP auto-rotate unused templates → qualify in parallel.

    Stops on target, check_budget, diminishing unique-new rate, bank empty, or stop.
    """
    searxng_only = engine == "SearXNG Only"
    # Cloud free tier: Chrome SERP (warmup/panels/gap-fill) OOMs or hangs and
    # was mis-reported as "SERP exhausted". Use SearXNG∥OpenSERP→DDG only.
    use_google  = (not searxng_only) and (not _ON_CLOUD)
    use_searxng = True
    use_ddg     = not searxng_only
    page_size   = _PAGE_SIZE
    max_pages   = _max_pages_for(num)
    workers     = max(1, min(int(workers or _DEFAULT_WORKERS), _MAX_WORKERS))

    stop_reason = "search_exhausted"
    total_kept = 0
    total_passed = 0
    check_budget = _check_budget_for(num)
    meta_pages_cap = _meta_pages_for(num)
    dim_returns = False
    kept_timestamps: list[float] = []
    terms_done_at: list[float] = []
    run_start = time.time()

    try:
        q_out.put(("engine_note", "Preparing search engines (SearXNG + OpenSERP if needed)…"))
        ensure_searxng(force=True)
        try:
            ensure_openserp(force=True)
        except Exception:
            pass

        # Prove free engines before burning the template bank.
        probe_hits = 0
        probe_detail = ""
        probe_q = (
            f"{(industry_slug or 'localization').replace('-', ' ')} company"
            + (f" {country}" if country and country != "All Countries" else "")
        )
        for probe_try in range(4 if _ON_CLOUD else 2):
            xng_st: dict = {}
            try:
                rows = searxng_search(
                    probe_q, num=5, page=1, status_out=xng_st,
                ) or []
                probe_hits = len(rows)
                if probe_hits:
                    probe_detail = f"SearXNG probe OK — {probe_hits} hits"
                    break
                probe_detail = f"SearXNG probe empty ({xng_st.get('status') or 'empty'})"
            except Exception as exc:
                probe_detail = f"SearXNG probe failed ({type(exc).__name__})"
            try:
                osp_st: dict = {}
                rows = openserp_search(
                    probe_q, num=5, page=1, status_out=osp_st,
                ) or []
                if rows:
                    probe_hits = len(rows)
                    probe_detail = f"OpenSERP probe OK — {probe_hits} hits"
                    break
                probe_detail = (
                    probe_detail
                    + f"; OpenSERP ({osp_st.get('status') or 'empty'})"
                )
            except Exception as exc:
                probe_detail = (
                    probe_detail
                    + f"; OpenSERP failed ({type(exc).__name__})"
                )
            q_out.put((
                "engine_note",
                f"Waiting for SERP engines… try {probe_try + 1} "
                f"({probe_detail})",
            ))
            time.sleep(3.0 + probe_try * 2.0)

        if probe_hits:
            q_out.put(("engine_note", probe_detail))
            _step1_log(probe_detail)
        else:
            msg = (
                "SERP engines returned no results after wake/probe. "
                f"Detail: {probe_detail or 'unknown'}. "
                "Retry in a minute (SearXNG/OpenSERP may still be cold or rate-limited)."
            )
            _step1_log(msg)
            q_out.put(("error", msg))
            q_out.put(("done", {
                "reason": "serp_unavailable",
                "kept": 0,
                "target": num,
                "checked": 0,
            }))
            return

        if use_google:
            google_warmup()
        elif _ON_CLOUD:
            q_out.put((
                "engine_note",
                "Cloud mode — Chrome SERP skipped (SearXNG∥OpenSERP→DDG only)",
            ))

        with sqlite3.connect(DB_PATH, check_same_thread=False) as wconn:
            db_init(wconn)
            db_lock = threading.Lock()
            demoted = db_demote_geo_rejects(wconn)
            if demoted:
                q_out.put((
                    "engine_note",
                    f"Removed {demoted} geo-mismatched domains from qualified",
                ))
            blocked  = db_load_blocked_domains(wconn)
            # Skip every domain already checked (qualified/rejected/failed/unreachable)
            existing = db_load_all_domain_names(wconn)
            skip = set(blocked) | existing
            pending_futs: dict = {}
            scraped_dirs: set[str] = set()
            dir_scrape_count = 0

            _city_list = (
                list(MAJOR_CITIES.get(country, []))
                if country and country != "All Countries" else []
            )
            template_bank = _build_template_bank(
                list(queries or []), industry_slug, country, _city_list, num,
            )

            with ThreadPoolExecutor(max_workers=workers) as pool:

                # Auto-rotate unused SERP templates until target / dim returns / bank empty
                if template_bank:
                    n_dir = len(directory_search_queries(industry_slug, country))
                    q_out.put((
                        "engine_note",
                        f"Priority first — {n_dir} directory queries, then panels / "
                        f"SERP summary, then site qualify · {len(template_bank)} templates",
                    ))
                    _step1_log(f"SERP bank size={len(template_bank)} dir_priority={n_dir}")

                for qi, query in enumerate(template_bank):
                    if stop_event.is_set() or total_kept >= num or total_passed >= check_budget:
                        break
                    if dim_returns:
                        break

                    raw_count     = 0
                    blocked_count = 0
                    dup_count     = 0
                    checked_count = 0
                    kept_count    = 0
                    tiers_used: set = set()
                    empty_reason = ""
                    last_chain = ""
                    page = 1
                    empty_serp_retries = 0
                    pending_google_resume = False
                    was_in_cooldown = google_in_cooldown() if use_google else False
                    term_used_fallback = False
                    kept_before_term = total_kept
                    passed_before_term = total_passed

                    def _handle_term_fut(fut):
                        nonlocal total_passed, total_kept, checked_count, kept_count
                        if fut not in pending_futs:
                            return
                        tier_hint = pending_futs.pop(fut)
                        try:
                            res = fut.result()
                        except Exception:
                            return
                        total_passed += 1
                        checked_count += 1
                        if res["status"] == "qualified":
                            kept_count += 1
                            total_kept += 1
                            kept_timestamps.append(time.time())
                            q_out.put(("qualified", res))
                        else:
                            q_out.put(("rejected", {
                                "domain": res["domain"],
                                "reason": res["status"],
                                "tier": tier_hint,
                            }))

                    def _drain_term(block: bool = False):
                        if block:
                            while pending_futs:
                                _handle_term_fut(
                                    next(as_completed(list(pending_futs.keys())))
                                )
                        else:
                            for fut in list(pending_futs.keys()):
                                if fut.done():
                                    _handle_term_fut(fut)

                    def _cap_term():
                        while (len(pending_futs) >= workers * 3
                               and not stop_event.is_set()):
                            if not pending_futs:
                                break
                            _handle_term_fut(
                                next(as_completed(list(pending_futs.keys())))
                            )
                            if total_kept >= num or total_passed >= check_budget:
                                break

                    while page <= max_pages:
                        if (stop_event.is_set() or total_kept >= num
                                or total_passed >= check_budget):
                            break

                        _drain_term(block=False)
                        if total_kept >= num or total_passed >= check_budget:
                            break

                        in_cd = use_google and google_in_cooldown()
                        if was_in_cooldown and not in_cd and use_google:
                            page = 1
                            pending_google_resume = True
                            q_out.put((
                                "engine_note",
                                "Google ready — resuming this search term on Google",
                            ))
                        was_in_cooldown = in_cd

                        q_out.put(("query_start", query))
                        q_out.put(("page", page))

                        page_results, tier, meta = _search_page(
                            query, page_size, page, use_searxng, use_google, use_ddg,
                            q_out=q_out,
                        )
                        if meta.get("chain"):
                            last_chain = " → ".join(meta["chain"])
                        if tier in (
                            "SearXNG", "OpenSERP", "SearXNG+OpenSERP",
                            "Bing", "DuckDuckGo",
                        ) or meta.get("xng_ok"):
                            term_used_fallback = True
                        if tier != "none":
                            tiers_used.add(tier)
                            q_out.put(("engine", tier))
                        elif not page_results and not empty_reason:
                            empty_reason = last_chain or (
                                "all engines returned no results"
                            )

                        if not page_results:
                            # Cloud: SearXNG/OpenSERP often return empty while waking
                            # or under 429 — retry same page before abandoning the term.
                            if (
                                page == 1
                                and empty_serp_retries < _EMPTY_SERP_RETRIES
                                and not stop_event.is_set()
                            ):
                                empty_serp_retries += 1
                                wait_s = 4.0 * empty_serp_retries
                                q_out.put((
                                    "engine_note",
                                    f"SERP empty/blocked — retry {empty_serp_retries}/"
                                    f"{_EMPTY_SERP_RETRIES} in {int(wait_s)}s "
                                    f"({last_chain or 'warming engines'})",
                                ))
                                time.sleep(wait_s)
                                continue
                            break

                        empty_serp_retries = 0
                        raw_count += len(page_results)
                        batch = []

                        # ── PRIORITY PASS: verified techniques before any site open ──
                        # Order: AI Overview → Local Pack → Directory → SERP summary
                        # Normal cheap_screen → HTTP qualify only runs in pass 2.
                        ranked = sorted(
                            enumerate(page_results),
                            key=lambda it: _result_verified_priority(
                                it[1],
                                industry_slug=industry_slug,
                                country=country,
                            ),
                        )
                        verified_handled: set[str] = set()

                        q_out.put((
                            "engine_note",
                            "Priority pass — panels / directories / SERP summary "
                            "(before site qualify)",
                        ))

                        for _idx, r in ranked:
                            if (stop_event.is_set() or total_kept >= num
                                    or total_passed >= check_budget):
                                break
                            pri = _result_verified_priority(
                                r, industry_slug=industry_slug, country=country,
                            )
                            if pri >= 9:
                                continue  # normal organics → pass 2

                            url = r.get("link", "")
                            title = r.get("title", "")
                            snippet = r.get("snippet", "")
                            dom_key = get_domain(url) or url

                            # Google AI Overview / Local Pack
                            if r.get("source") in ("ai_overview", "local_pack"):
                                src = r.get("source") or "ai_overview"
                                tier_label = (
                                    "Local Pack" if src == "local_pack"
                                    else "AI Overview"
                                )
                                outcome, d_dup, d_blk = _ingest_verified_company(
                                    url=url, title=title, source=src,
                                    tier_label=tier_label, skip=skip,
                                    country=country, industry=industry,
                                    keyword=keyword, wconn=wconn, db_lock=db_lock,
                                    q_out=q_out, kept_timestamps=kept_timestamps,
                                )
                                dup_count += d_dup
                                blocked_count += d_blk
                                if outcome == "qualified":
                                    total_passed += 1
                                    total_kept += 1
                                if dom_key:
                                    verified_handled.add(dom_key)
                                continue

                            # Directory / Top-N listicle
                            if is_directory_scrape_target(url, title):
                                dir_key = (url or "").split("?")[0].rstrip("/")
                                if (
                                    dir_key in scraped_dirs
                                    or dir_scrape_count >= _MAX_DIRECTORY_SCRAPES
                                ):
                                    if dom_key:
                                        verified_handled.add(dom_key)
                                    continue
                                scraped_dirs.add(dir_key)
                                dir_scrape_count += 1
                                q_out.put((
                                    "engine_note",
                                    f"Directory scrape — {get_domain(url) or title[:40]}",
                                ))
                                try:
                                    companies = scrape_directory_companies(
                                        url,
                                        title=title,
                                        snippet=snippet,
                                        organic=page_results,
                                        max_companies=_MAX_COMPANIES_PER_DIRECTORY,
                                    )
                                except Exception:
                                    companies = []
                                if companies:
                                    q_out.put((
                                        "engine_note",
                                        f"Directory — {len(companies)} verified "
                                        f"companies from {get_domain(url) or '?'}",
                                    ))
                                for c in companies:
                                    if (stop_event.is_set() or total_kept >= num
                                            or total_passed >= check_budget):
                                        break
                                    outcome, d_dup, d_blk = _ingest_verified_company(
                                        url=c.get("link", ""),
                                        title=c.get("title", ""),
                                        source="directory",
                                        tier_label="Directory",
                                        skip=skip,
                                        country=country, industry=industry,
                                        keyword=keyword, wconn=wconn,
                                        db_lock=db_lock, q_out=q_out,
                                        kept_timestamps=kept_timestamps,
                                    )
                                    dup_count += d_dup
                                    blocked_count += d_blk
                                    if outcome == "qualified":
                                        total_passed += 1
                                        total_kept += 1
                                    cdom = get_domain(c.get("link", "") or "")
                                    if cdom:
                                        verified_handled.add(cdom)
                                if dom_key:
                                    verified_handled.add(dom_key)
                                continue

                            # SERP title+snippet industry + location
                            if pri == 3:
                                outcome, d_dup, d_blk = _ingest_verified_company(
                                    url=url, title=title, source="serp_summary",
                                    tier_label="SERP summary",
                                    skip=skip,
                                    country=country, industry=industry,
                                    keyword=keyword, wconn=wconn,
                                    db_lock=db_lock, q_out=q_out,
                                    kept_timestamps=kept_timestamps,
                                )
                                dup_count += d_dup
                                blocked_count += d_blk
                                if outcome == "qualified":
                                    total_passed += 1
                                    total_kept += 1
                                if dom_key:
                                    verified_handled.add(dom_key)
                                continue

                        if total_kept >= num or stop_event.is_set():
                            _cap_term()
                            break

                        # ── NORMAL PASS: cheap screen → open site → score/geo ──
                        q_out.put((
                            "engine_note",
                            "Normal pass — site qualify for remaining SERP hits",
                        ))
                        for r in page_results:
                            if (stop_event.is_set() or total_kept >= num
                                    or total_passed + len(batch) + len(pending_futs)
                                    >= check_budget):
                                break
                            url = r.get("link", "")
                            title = r.get("title", "")
                            snippet = r.get("snippet", "")
                            dom_key = get_domain(url) or url
                            if dom_key and dom_key in verified_handled:
                                continue
                            # Skip anything that belongs on the priority path
                            if _result_verified_priority(
                                r, industry_slug=industry_slug, country=country,
                            ) < 9:
                                continue
                            if r.get("source") in ("ai_overview", "local_pack"):
                                continue

                            keep, reason, domain = cheap_screen_candidate(
                                url=url, title=title, snippet=snippet,
                                industry_slug=industry_slug, skip_domains=skip,
                                country=country,
                            )
                            if not keep:
                                if reason == "duplicate":
                                    dup_count += 1
                                else:
                                    blocked_count += 1
                                q_out.put(("rejected", {
                                    "domain": domain or "?",
                                    "reason": reason or "blocked/filtered",
                                    "tier": tier,
                                }))
                                if reason == "blocked" and domain:
                                    with db_lock:
                                        db_mark_blocked_domain(wconn, domain)
                                elif (
                                    reason in (
                                        "serp_irrelevant", "junk_title",
                                        "listicle", "foreign_cctld",
                                        "serp_geo_miss",
                                    )
                                    and domain
                                ):
                                    with db_lock:
                                        db_upsert_domain(wconn, {
                                            "domain": domain,
                                            "status": "failed",
                                            "industry": industry,
                                            "country": country,
                                            "keyword": keyword,
                                            "score_reasons": f'["{reason}"]',
                                        })
                                    skip.add(domain)
                                continue

                            skip.add(domain)
                            batch.append((domain, title))

                        if batch:
                            for d, title in batch:
                                q_out.put(("scanning", d))
                                fut = pool.submit(
                                    _qualify_one, d, industry, country, keyword,
                                    wconn, db_lock, industry_slug, title,
                                    strict_location,
                                )
                                pending_futs[fut] = tier

                        _cap_term()
                        if total_kept >= num or total_passed >= check_budget:
                            break
                        if stop_event.is_set():
                            break

                        truly_thin = len(page_results) < _MIN_PAGE_HITS
                        engine_dry = truly_thin or tier == "DuckDuckGo"

                        if not engine_dry:
                            if (
                                tier in (
                                    "SearXNG", "OpenSERP", "SearXNG+OpenSERP",
                                    "Panels+SearXNG", "Panels+OpenSERP",
                                    "Panels+SearXNG+OpenSERP", "Google panels",
                                )
                                and page >= meta_pages_cap
                            ):
                                q_out.put((
                                    "engine_note",
                                    f"{tier}: page {meta_pages_cap} reached — "
                                    "next search term (engines stay warm)",
                                ))
                                break
                            page += 1
                            if tier in (
                                "SearXNG", "SearXNG+OpenSERP",
                                "Panels+SearXNG", "Panels+SearXNG+OpenSERP",
                            ):
                                time.sleep(0.6)
                            elif tier in ("OpenSERP", "Panels+OpenSERP"):
                                time.sleep(0.4)
                            elif tier.startswith("Chrome") or tier == "Bing" or tier == "Google panels":
                                time.sleep(0.8)
                            continue

                        if tier.startswith("Chrome") or tier == "Google panels":
                            if meta.get("captcha") and not term_used_fallback:
                                page = 1
                                continue
                            break

                        if (
                            total_kept < num
                            and use_google
                            and not google_in_cooldown()
                            and not pending_google_resume
                        ):
                            page = 1
                            pending_google_resume = True
                            q_out.put((
                                "engine_note",
                                "Page thin — gap-filling this term on Google",
                            ))
                            continue

                        break

                    _drain_term(block=False)
                    _cap_term()
                    time.sleep(0.4)

                    # Account for qualify finishes that used pool-level paths
                    kept_count = max(kept_count, total_kept - kept_before_term)
                    checked_count = max(
                        checked_count, total_passed - passed_before_term,
                    )

                    q_out.put(("query_done", {
                        "query":   query,
                        "raw":     raw_count,
                        "blocked": blocked_count,
                        "dup":     dup_count,
                        "passed":  checked_count,
                        "checked": checked_count,
                        "kept":    kept_count,
                        "tiers":   ", ".join(sorted(tiers_used)) or "—",
                        "chain":   last_chain,
                        "empty_reason": empty_reason if raw_count == 0 else "",
                    }))

                    terms_done_at.append(time.time())
                    rate, kept_win, terms_win = _dim_returns_rate(
                        kept_timestamps, terms_done_at, run_start,
                    )
                    _step1_log(
                        f"RATE unique_new_per_hour={rate:.1f} "
                        f"window_kept={kept_win} terms_in_window={terms_win} "
                        f"total_kept={total_kept}"
                    )
                    if (
                        total_kept < num
                        and not stop_event.is_set()
                        and total_passed < check_budget
                        and terms_win >= _DIM_MIN_TERMS
                        and rate < _DIM_RATE_FLOOR
                    ):
                        dim_returns = True
                        _step1_log(
                            f"DIMINISHING RETURNS rate={rate:.1f}/hr "
                            f"(floor={_DIM_RATE_FLOOR}) after {terms_win} terms "
                            f"in window — stopping SERP rotate"
                        )
                        break

                while pending_futs:
                    fut = next(as_completed(list(pending_futs.keys())))
                    if fut not in pending_futs:
                        continue
                    tier_hint = pending_futs.pop(fut)
                    try:
                        res = fut.result()
                    except Exception:
                        continue
                    total_passed += 1
                    if res["status"] == "qualified":
                        total_kept += 1
                        kept_timestamps.append(time.time())
                        q_out.put(("qualified", res))
                    else:
                        q_out.put(("rejected", {
                            "domain": res["domain"],
                            "reason": res["status"],
                            "tier": tier_hint,
                        }))

        if stop_event.is_set():
            stop_reason = "stopped"
        elif total_kept >= num:
            stop_reason = "target_met"
        elif total_passed >= check_budget:
            stop_reason = "check_budget"
        elif dim_returns:
            stop_reason = "diminishing_returns"
        else:
            stop_reason = "search_exhausted"

    except Exception as exc:
        stop_reason = "error"
        q_out.put(("error", str(exc)))

    q_out.put(("done", {
        "reason": stop_reason,
        "kept": total_kept,
        "target": num,
        "checked": total_passed,
    }))


# ── Start run ──────────────────────────────────────────────────────────────────
if run_btn and not st.session_state.s1_running:
    _stop_event = threading.Event()
    st.session_state.s1_running       = True
    st.session_state.s1_done          = False
    st.session_state.s1_qualified     = []
    st.session_state.s1_rejected_log  = []
    st.session_state.s1_query_log     = []
    st.session_state.s1_current_query = ""
    st.session_state.s1_current_page  = 1
    st.session_state.s1_queries_done   = 0
    st.session_state.s1_checked        = 0
    st.session_state.s1_failed         = 0
    st.session_state.s1_unreachable    = 0
    st.session_state.s1_filtered       = 0
    st.session_state.s1_target         = depth or 0
    st.session_state.s1_error          = ""
    st.session_state.s1_start_time     = time.time()
    st.session_state.s1_queue          = queue.Queue()
    st.session_state.s1_stop_event     = _stop_event
    st.session_state.s1_current_engine = ""
    st.session_state.s1_engine_note    = ""
    st.session_state.s1_stop_reason    = ""
    st.session_state.s1_max_pages      = _max_pages_for(depth)
    st.session_state.s1_workers        = qualify_workers

    _step1_log_autoclean()
    _check_cap = _check_budget_for(depth or 0)
    _step1_log(
        f"─── RUN START industry={industry!r} country={country!r} "
        f"keyword={kw!r} target={depth} check_budget={_check_cap} "
        f"workers={qualify_workers} terms={len(final_queries)} "
        f"bank={len(bank_preview)} strict_location={strict_location} ───"
    )

    threading.Thread(
        target=_run_step1,
        args=(final_queries, depth, st.session_state.s1_queue,
              _stop_event, industry, country, kw),
        kwargs={
            "industry_slug": ind_kw or "",
            "engine": engine,
            "workers": qualify_workers,
            "strict_location": strict_location,
        },
        daemon=True,
    ).start()
    st.rerun()

if stop_btn:
    if st.session_state.s1_stop_event:
        st.session_state.s1_stop_event.set()
    st.session_state.s1_running = False
    st.session_state.s1_done    = True

# ── Drain queue ────────────────────────────────────────────────────────────────
if st.session_state.s1_queue:
    q = st.session_state.s1_queue
    seen_domains = {r["domain"] for r in st.session_state.s1_qualified}

    while not q.empty():
        kind, payload = q.get_nowait()

        if kind == "query_start":
            st.session_state.s1_current_query = payload

        elif kind == "page":
            st.session_state.s1_current_page = payload

        elif kind == "engine":
            st.session_state.s1_current_engine = payload or ""

        elif kind == "scanning":
            st.session_state.s1_current_domain = payload

        elif kind == "query_done":
            st.session_state.s1_queries_done += 1
            st.session_state.s1_current_page  = 1
            if isinstance(payload, dict):
                st.session_state.s1_query_log.append(payload)
                kept = payload.get("kept")
                if kept is None:
                    kept = 0
                checked_n = payload.get("checked", payload.get("passed", 0))
                why = payload.get("empty_reason") or ""
                chain = payload.get("chain") or ""
                tiers = payload.get("tiers") or ""
                parts = [
                    f"TERM {payload.get('query', '')!r} — "
                    f"{payload.get('raw', 0)} results · {kept} kept · "
                    f"{checked_n} checked · {payload.get('blocked', 0)} filtered · "
                    f"{payload.get('dup', 0)} duplicates",
                ]
                if tiers and tiers != "—":
                    parts.append(f" · via {tiers}")
                if why and payload.get("raw", 0) == 0:
                    parts.append(f" · why empty: {why}")
                elif chain:
                    parts.append(f" · {chain}")
                _step1_log("".join(parts))

        elif kind == "qualified":
            st.session_state.s1_checked += 1
            if payload["domain"] not in seen_domains:
                seen_domains.add(payload["domain"])
                st.session_state.s1_qualified.append(payload)

        elif kind == "rejected":
            reason = payload.get("reason", "")
            if reason == "unreachable":
                st.session_state.s1_checked += 1
                st.session_state.s1_unreachable += 1
            elif reason in ("failed", "unverified"):
                st.session_state.s1_checked += 1
                st.session_state.s1_failed += 1
            else:
                # blocked / industry mismatch / duplicate — never scraped
                st.session_state.s1_filtered += 1
            if len(st.session_state.s1_rejected_log) < 500:
                st.session_state.s1_rejected_log.append(payload)

        elif kind == "engine_note":
            note = payload or ""
            st.session_state.s1_engine_note = note
            if note:
                _step1_log(f"ENGINE {note}")

        elif kind == "error":
            st.session_state.s1_error = payload
            _step1_log(f"ERROR {payload}")

        elif kind == "done":
            st.session_state.s1_running       = False
            st.session_state.s1_done          = True
            st.session_state.s1_current_query = ""
            if isinstance(payload, dict):
                st.session_state.s1_stop_reason = payload.get("reason") or ""
            else:
                st.session_state.s1_stop_reason = ""
            _step1_log(
                f"─── RUN STOP reason={st.session_state.s1_stop_reason or '—'} "
                f"qualified={len(st.session_state.s1_qualified)} "
                f"failed={st.session_state.s1_failed} "
                f"unreachable={st.session_state.s1_unreachable} ───"
            )

# ══════════════════════════════════════════════════════════════════════════════
# RESULTS TABLE
# ══════════════════════════════════════════════════════════════════════════════

# ── Current run results ────────────────────────────────────────────────────────
if qualified:
    section_label("✅", f"Qualified Domains ({len(qualified)})")

    rows_html = []
    for entry in sorted(qualified, key=lambda e: e.get("score", 0), reverse=True):
        badge = tier_badge(entry.get("tier", ""))
        reasons = ", ".join(entry.get("reasons", []))
        li_cell = link_icon(entry.get("linkedin_url", ""))
        rows_html.append(
            f'<tr>'
            f'<td class="lr-cell-strong">{entry["domain"]}</td>'
            f'<td>{entry.get("company_name","")}</td>'
            f'<td>{badge}</td>'
            f'<td style="text-align:center">{entry.get("score",0)}</td>'
            f'<td>{li_cell}</td>'
            f'<td class="lr-muted" style="font-size:0.8em">{reasons}</td>'
            f'</tr>'
        )

    render_table(
        ["Domain", "Company", "Tier", "Score", "LinkedIn", "Signals"],
        "".join(rows_html),
        max_height="520px",
    )

# Per-term search diagnostics are written to logs/step1_search.log (weekly autoclean).
# Rejected-domain list is intentionally not shown — UI focuses on this run's
# qualified results only. Full DB browse lives on the Database page / Home export.

# ── Export (this Step 1 run only — not full DB / other steps) ───────────────────
if (qualified or st.session_state.s1_rejected_log) and not st.session_state.s1_running:
    section_label("📥", "Export")

    ecol1, ecol2 = st.columns(2)
    with ecol1:
        try:
            from export_excel import build_step1_excel_bytes
            xlsx_bytes = build_step1_excel_bytes(
                qualified,
                rejected_rows=st.session_state.s1_rejected_log,
            )
            st.download_button(
                label="📊  Download Excel (this run)",
                data=xlsx_bytes,
                file_name=f"locreach_domains_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
                type="primary",
            )
            st.caption(
                "Exports **this run only** (Qualified + Not Kept). "
                "Full DB export is on **Home**."
            )
        except Exception as _e:
            st.error(f"Excel export failed: {_e}")

# ── Auto-refresh while running ─────────────────────────────────────────────────
# 1.5s (was 0.7s) — a long scan reruns the whole page dozens of times; a
# tighter interval stresses the browser's main thread enough to risk
# delaying the heartbeat ping past the watchdog's shutdown timeout.
if st.session_state.s1_running:
    time.sleep(1.5)
    st.rerun()
elif st.session_state.s1_done and st.session_state.s1_queue is not None:
    st.session_state.s1_queue = None
    st.rerun()
