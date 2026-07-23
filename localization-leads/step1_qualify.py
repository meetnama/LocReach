"""
step1_qualify.py — Fast Step 1 qualify path (no Streamlit).

Pipeline (Arabic plan / speed path):
  1. Cheap SERP screen  — title/snippet are the first indicators for BOTH
                          industry and geo; fail → never HTTP-open the domain
  2. Fast homepage HTTP — ~6s, no Chrome
  3. Light deep scan    — at most 2–4 high-value pages (about/contact/services…)
  4. Decide             — on-page geo + score → qualified / rejected
"""
from __future__ import annotations

import json
import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Optional
from urllib.parse import urljoin, urlparse

import sqlite3

from config import INDUSTRY_KEYWORDS, RELEVANCE_KEYWORDS, TLD_COUNTRY
from db import db_upsert_domain
from scanner import (
    _PARKING_SIGNALS,
    count_internal_pages,
    extract_company_name,
    extract_linkedin_url,
    is_quality_site,
)
from scoring import score_company
from sources.utils import get_domain, is_blocked

_POSITIVE_TERMS = (
    "localization", "localisation", "translation", "translating", "translator",
    "interpreting", "interpreter", "language service", "language services",
    "globalization", "globalisation", "subtitling", "dubbing", "transcreation",
    "lsp", "multilingual", "linguist",
)

_HIGH_VALUE_PATH_HINTS = (
    "/about", "/about-us", "/company", "/services", "/solutions",
    "/contact", "/contact-us", "/team", "/our-team",
    "/translation", "/localization", "/localisation", "/languages",
    "/interpreting", "/capabilities", "/what-we-do",
)

_MAX_DEEP_PAGES = 3  # + homepage ≤ 4
_HTTP_TIMEOUT = 6    # fail dead hosts faster (was 10s)

# SERP title junk — login walls / errors / legal boilerplate
_SERP_JUNK_TITLE = (
    "login", "sign in", "sign up", "create account", "forgot password",
    "404", "page not found", "access denied", "403 forbidden",
    "privacy policy", "terms of service", "cookie policy",
)
# Listicle / directory result pages — not a company to qualify
_SERP_LISTICLE = (
    "top 10", "top 20", "top 50", "best 10", "best 20",
    "best companies", "list of ", "directory of", "companies list",
    "agency list", "top agencies", "top firms",
)
_SORTED_TLDS = sorted(TLD_COUNTRY.items(), key=lambda kv: -len(kv[0]))


def serp_suggests_industry(title: str, snippet: str, industry_slug: str) -> bool:
    """
    First-pass industry hint from SERP title/snippet — decide whether to open
    the domain. Requires real industry evidence in the blurb (not a lone
    ambiguous "localization"). Thin/empty SERP returns True so weak engines
    don't starve; on-page scoring still decides keep.
    """
    if not industry_slug:
        return True
    from scoring import industry_evidence_ok, _industry_keyword_list

    keywords = _industry_keyword_list(industry_slug)
    if not keywords:
        return True
    combined = f"{title or ''} {snippet or ''}".strip()
    if len(combined) < 20:
        return True
    combined_lc = combined.lower()
    hits = [kw for kw in keywords if kw.lower() in combined_lc]
    return industry_evidence_ok(hits)


def serp_summary_has_industry(
    title: str, snippet: str, industry_slug: str,
) -> bool:
    """
    Industry match for SERP title+snippet verify fast-path.
    Requires a real industry slug and at least one strong LSP marker
    (lone ambiguous \"localization\" / \"language\" is not enough).
    """
    if not industry_slug:
        return False
    from scoring import _industry_keyword_list, _is_strong_industry_term

    keywords = _industry_keyword_list(industry_slug)
    if not keywords:
        return False
    combined_lc = f"{title or ''} {snippet or ''}".lower()
    if not combined_lc.strip():
        return False
    hits = [kw for kw in keywords if kw.lower() in combined_lc]
    if not hits:
        return False
    return any(_is_strong_industry_term(h) for h in hits)


def serp_summary_verified(
    title: str,
    snippet: str,
    industry_slug: str,
    country: str = "",
    domain: str = "",
) -> bool:
    """
    True when the SERP result summary (title + snippet) already shows both
    industry (strong marker) and location — qualify without opening the site.
    """
    if not serp_summary_has_industry(title, snippet, industry_slug):
        return False
    if country and country != "All Countries":
        from sources.geo import serp_suggests_country
        if not serp_suggests_country(
            title or "", snippet or "", country, domain or "",
            require_signal=True,
        ):
            return False
    return True


def _foreign_cctld(domain: str, country: str) -> str:
    """Return foreign ccTLD if domain belongs to another country, else ''."""
    if not domain or not country or country == "All Countries":
        return ""
    dom = domain.lower().removeprefix("www.")
    for tld, ctry in _SORTED_TLDS:
        if dom.endswith(tld):
            return tld if ctry != country else ""
    return ""


def cheap_screen_candidate(
    *,
    url: str,
    title: str,
    snippet: str,
    industry_slug: str,
    skip_domains: set,
    country: str = "",
) -> tuple[bool, str, str]:
    """
    Pre-fetch rejection using SERP title/snippet before any HTTP open.
    Returns (keep, reason, domain).

    SERP blurb is the first indicator for BOTH:
      • industry — must hit INDUSTRY_KEYWORDS (e.g. translation / ترجمة)
      • geo — must hint at the selected country/city (when country ≠ All)

    Only candidates that pass both are fetched; on-page score + geo still
    decide final keep/reject. Thin/empty snippets do not auto-reject.
    Own ccTLD still satisfies the geo hint. Foreign ccTLD / junk / listicles
    are rejected up front.
    """
    domain = get_domain(url or "")
    if not domain:
        return False, "no_domain", ""

    if is_blocked(url):
        return False, "blocked", domain

    if domain in skip_domains:
        return False, "duplicate", domain

    foreign = _foreign_cctld(domain, country or "")
    if foreign:
        return False, "foreign_cctld", domain

    title = title or ""
    snippet = snippet or ""
    title_lc = title.lower()

    if title_lc and any(sig in title_lc for sig in _SERP_JUNK_TITLE):
        return False, "junk_title", domain

    if title_lc and any(sig in title_lc for sig in _SERP_LISTICLE):
        return False, "listicle", domain

    # ── SERP first indicators (industry + geo) before any HTTP open ──────────
    if not serp_suggests_industry(title, snippet, industry_slug):
        return False, "serp_irrelevant", domain

    if country and country != "All Countries":
        from sources.geo import serp_suggests_country
        if not serp_suggests_country(title, snippet, country, domain):
            return False, "serp_geo_miss", domain

    return True, "", domain


def ai_overview_screen(
    *,
    url: str,
    skip_domains: set,
    country: str = "",
) -> tuple[bool, str, str]:
    """
    Minimal hygiene for Google-verified panel companies
    (AI Overview / Local Pack — no industry/geo SERP gates).
    Returns (keep, reason, domain).
    """
    domain = get_domain(url or "")
    if not domain:
        return False, "no_domain", ""
    if is_blocked(url):
        return False, "blocked", domain
    if domain in skip_domains:
        return False, "duplicate", domain
    foreign = _foreign_cctld(domain, country or "")
    if foreign:
        return False, "foreign_cctld", domain
    return True, "", domain


# Alias — same hygiene for Local Pack / Maps businesses
serp_verified_screen = ai_overview_screen

_VERIFIED_REASONS = {
    "ai_overview": "ai_overview_verified",
    "local_pack": "local_pack_verified",
    "directory": "directory_verified",
    "serp_summary": "serp_summary_verified",
}


def qualify_from_ai_overview(
    domain: str,
    industry: str,
    country: str,
    keyword: str,
    conn: sqlite3.Connection,
    db_lock: threading.Lock,
    *,
    company_name: str = "",
    title: str = "",
    source: str = "ai_overview",
) -> dict:
    """
    Fast-path: Google AI Overview, Local Pack, directory/listicle, or SERP
    title+snippet already listed/matched this company. Persist as qualified
    with NO homepage open / score / geo.
    """
    ts = datetime.now().isoformat()
    name = (company_name or title or "").strip() or domain
    src = source if source in _VERIFIED_REASONS else "ai_overview"
    reason_tag = _VERIFIED_REASONS[src]
    reasons = [reason_tag]
    row = {
        "domain": domain,
        "status": "qualified",
        "industry": industry,
        "country": country,
        "keyword": keyword,
        "company_name": name,
        "score": 70,
        "score_tier": "strong",
        "score_reasons": json.dumps(reasons),
        "qualified_at": ts,
    }
    with db_lock:
        db_upsert_domain(conn, row)
    return {
        "domain": domain,
        "status": "qualified",
        "company_name": name,
        "linkedin_url": "",
        "industry": industry,
        "country": country,
        "keyword": keyword,
        "scanned_at": ts,
        "pages_fetched": 0,
        "score": 70,
        "tier": "strong",
        "reasons": reasons,
        "source": src,
    }


def _http_fetch(url: str, timeout: float = _HTTP_TIMEOUT) -> Optional[dict]:
    """Ordinary HTTP homepage/page fetch — never Chrome."""
    import random
    import requests as _req
    from sources.utils import _USER_AGENTS

    target = url if "://" in url else f"https://{url}"
    headers = {"User-Agent": random.choice(_USER_AGENTS)}

    def _get(verify):
        return _req.get(
            target, timeout=timeout, headers=headers,
            allow_redirects=True, verify=verify,
        )

    try:
        try:
            resp = _get(True)
        except _req.exceptions.SSLError:
            resp = _get(False)
        except (_req.exceptions.Timeout, _req.exceptions.ConnectionError):
            return None
    except Exception:
        return None

    if resp is None or resp.status_code != 200:
        return None

    html = resp.text or ""
    for tag in ("script", "style", "noscript"):
        html = re.sub(rf"<{tag}[^>]*>.*?</{tag}>", " ", html,
                      flags=re.DOTALL | re.IGNORECASE)
    title_m = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.DOTALL)
    meta_m = re.search(
        r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)',
        html, re.I,
    )
    if not meta_m:
        meta_m = re.search(
            r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']description["\']',
            html, re.I,
        )
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text).strip()[:12000]
    prefix_bits = []
    if title_m:
        prefix_bits.append(re.sub(r"\s+", " ", title_m.group(1)).strip())
    if meta_m:
        prefix_bits.append(meta_m.group(1).strip())
    if prefix_bits:
        text = " ".join(prefix_bits) + " " + text

    raw_links = [m.group(1) for m in re.finditer(r'href=["\']([^"\'#\s]+)["\']', html)]
    links = []
    for lnk in raw_links:
        if lnk.startswith("http") or (lnk.startswith("/") and not lnk.startswith("//")):
            links.append(lnk)
    links = links[:300]

    if len(text) < 80:
        return None
    return {"markdown": text, "links": links}


def select_high_value_urls(site_data: dict, domain: str,
                           limit: int = _MAX_DEEP_PAGES) -> list[str]:
    if not site_data:
        return []
    bare = (domain or "").lower().removeprefix("www.")
    base = f"https://{bare}"
    scored: list[tuple[int, str]] = []
    seen = set()

    for href in site_data.get("links") or []:
        if isinstance(href, dict):
            href = href.get("href") or ""
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        abs_url = urljoin(base + "/", href)
        try:
            p = urlparse(abs_url)
        except Exception:
            continue
        host = (p.netloc or "").lower().removeprefix("www.").split(":")[0]
        if host != bare and not host.endswith("." + bare):
            continue
        path = (p.path or "/").lower()
        if path in ("", "/"):
            continue
        key = path.rstrip("/") or "/"
        if key in seen:
            continue
        seen.add(key)
        score = 0
        for i, hint in enumerate(_HIGH_VALUE_PATH_HINTS):
            if hint in path:
                score = 100 - i
                break
        if score:
            scored.append((score, abs_url.split("#")[0].split("?")[0]))

    scored.sort(key=lambda x: -x[0])
    return [u for _, u in scored[:limit]]


def merge_site_data(parts: list[dict]) -> dict:
    texts, links = [], []
    for p in parts:
        if not p:
            continue
        texts.append(p.get("markdown") or "")
        for lnk in p.get("links") or []:
            links.append(lnk)
    seen, uniq = set(), []
    for lnk in links:
        h = lnk if isinstance(lnk, str) else (lnk.get("href") if isinstance(lnk, dict) else "")
        if h and h not in seen:
            seen.add(h)
            uniq.append(lnk)
    return {"markdown": "\n\n".join(t for t in texts if t)[:24000], "links": uniq[:500]}


def homepage_looks_parked_or_dead(site_data: dict) -> bool:
    if not site_data:
        return True
    text = (site_data.get("markdown") or "").strip()
    if len(text) < 100:
        return True
    lc = text.lower()
    return any(sig in lc for sig in _PARKING_SIGNALS)


def homepage_is_promising(site_data: dict, industry_slug: str = "",
                          domain: str = "") -> bool:
    if not site_data or homepage_looks_parked_or_dead(site_data):
        return False
    text = (site_data.get("markdown") or "").lower()
    if any(k in text for k in RELEVANCE_KEYWORDS):
        return True
    if any(t in text for t in _POSITIVE_TERMS):
        return True
    ind = INDUSTRY_KEYWORDS.get((industry_slug or "").lower(), [])
    if ind and any(k in text for k in ind):
        return True
    return count_internal_pages(site_data, domain) >= 3


def bounded_deep_scan(domain: str, homepage: dict) -> dict:
    urls = select_high_value_urls(homepage, domain, limit=_MAX_DEEP_PAGES)
    parts = [homepage]
    if not urls:
        return merge_site_data(parts)
    # Parallel deep fetches — biggest qualify-latency cut when workers are busy
    with ThreadPoolExecutor(max_workers=min(3, len(urls))) as pool:
        futs = {pool.submit(_http_fetch, u, _HTTP_TIMEOUT): u for u in urls}
        for fut in as_completed(futs):
            page = fut.result()
            if page:
                parts.append(page)
    return merge_site_data(parts)


def qualify_domain_fast(
    domain: str,
    industry: str,
    country: str,
    keyword: str,
    conn: sqlite3.Connection,
    db_lock: threading.Lock,
    industry_slug: str = "",
    google_title: str = "",
    strict_location: bool = True,
) -> dict:
    """
    Fast qualify: HTTP homepage → ≤3 deep pages → score → decide.

    Outcomes:
      qualified — industry evidence first (strong/possible), then country geo
      rejected  — scored but not kept (weak industry / location mismatch) → DB
      failed / unreachable — persisted so later runs skip them

    Order of keep gates (both required when a country is selected):
      1. Chosen industry — primary; insufficient LSP/industry evidence → reject
      2. Country — only after industry passes; must look BASED in that country
    """
    ts = datetime.now().isoformat()
    base = {
        "domain": domain, "company_name": "", "linkedin_url": "",
        "industry": industry, "country": country, "keyword": keyword,
        "scanned_at": ts, "pages_fetched": 0,
    }

    def _persist(status: str, extra: dict | None = None) -> None:
        row = {
            "domain": domain,
            "status": status,
            "industry": industry,
            "country": country,
            "keyword": keyword,
        }
        if extra:
            row.update(extra)
        with db_lock:
            db_upsert_domain(conn, row)

    try:
        homepage = _http_fetch(f"https://{domain}")
    except Exception:
        homepage = None

    if not homepage:
        # One Chrome fallback for JS-only shells (rare — slower)
        try:
            from scanner import scrape_site
            homepage = scrape_site(f"https://{domain}")
        except Exception:
            homepage = None

    if not homepage:
        _persist("unreachable", {"score_reasons": json.dumps(["unreachable"])})
        return {**base, "status": "unreachable"}

    base["pages_fetched"] = 1

    if homepage_looks_parked_or_dead(homepage):
        _persist("failed", {"score_reasons": json.dumps(["parked_or_empty"])})
        return {**base, "status": "failed", "reason": "parked_or_empty"}

    if not homepage_is_promising(homepage, industry_slug, domain=domain):
        if count_internal_pages(homepage, domain) < 2:
            _persist("failed", {"score_reasons": json.dumps(["not_promising"])})
            return {**base, "status": "failed", "reason": "not_promising"}

    deep_urls = select_high_value_urls(homepage, domain, limit=_MAX_DEEP_PAGES)
    site_data = bounded_deep_scan(domain, homepage)
    base["pages_fetched"] = 1 + len(deep_urls)

    text_lc = (site_data.get("markdown") or "").lower()
    if any(s in text_lc for s in _PARKING_SIGNALS) or len(text_lc) < 100:
        _persist("failed", {"score_reasons": json.dumps(["quality"])})
        return {**base, "status": "failed", "reason": "quality"}

    # Prefer full quality gate on merged pages; if only page-count fails but
    # relevance is clear, still score (deep pages added evidence).
    quality_ok = is_quality_site(site_data, domain, industry_slug)
    has_rel = any(k in text_lc for k in RELEVANCE_KEYWORDS)
    if not quality_ok and not has_rel:
        _persist("failed", {"score_reasons": json.dumps(["quality"])})
        return {**base, "status": "failed", "reason": "quality"}

    li_url = extract_linkedin_url(site_data)  # on-page only
    score_val, tier, reasons = score_company(
        site_data, domain, linkedin_url=li_url, industry_slug=industry_slug,
    )
    company_name = extract_company_name(
        site_data, google_title or domain, li_url=li_url
    )
    reasons = list(reasons) + [f"pages:{base['pages_fetched']}"]

    scored = {
        "company_name": company_name,
        "linkedin_url": li_url,
        "score": score_val,
        "score_tier": tier,
        "score_reasons": json.dumps(reasons),
    }

    # 1) Industry is the main factor — never qualify without it.
    industry_ok = tier in ("strong", "possible")
    if not industry_ok:
        _persist("rejected", scored)
        return {
            **base, "status": "unverified",
            "reason": "industry_mismatch",
            "company_name": company_name, "linkedin_url": li_url,
            "score": score_val, "tier": tier, "reasons": reasons,
        }

    # 2) Country gate — only after industry passes.
    location_ok = True
    location_mismatch = False
    if strict_location and country and country != "All Countries":
        from sources.geo import verify_country_location
        location_ok, loc_ev = verify_country_location(
            domain, site_data.get("markdown") or "", country
        )
        reasons.append(("geo_ok:" if location_ok else "geo_fail:") + ",".join(loc_ev))
        scored["score_reasons"] = json.dumps(reasons)
        location_mismatch = not location_ok

    if not location_ok:
        _persist("rejected", scored)
        return {
            **base, "status": "unverified",
            "reason": "location_mismatch" if location_mismatch else "low_score",
            "company_name": company_name, "linkedin_url": li_url,
            "score": score_val, "tier": tier, "reasons": reasons,
        }

    _persist("qualified", {**scored, "qualified_at": ts})

    return {
        **base, "status": "qualified",
        "company_name": company_name, "linkedin_url": li_url,
        "score": score_val, "tier": tier, "reasons": reasons,
        "country": country,
    }
