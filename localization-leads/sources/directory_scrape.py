"""
sources/directory_scrape.py — Scrape SERP directory / “Top N” list pages
for company names + websites, then treat those companies as verified.

The directory host itself is never qualified as a lead (still blocked /
listicle). Only the listed companies are returned.

Also builds industry-aware SERP queries (`site:proz.com …`) so free
directories are discovered on purpose, not only when they happen to rank.
"""
from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

from sources.utils import (
    get_domain,
    is_blocked,
    merge_serp_verified_results,
    resolve_ai_overview_link,
)

# General free B2B / review directories (still blocked as lead domains).
_GENERAL_DIRECTORY_HOSTS = frozenset({
    "clutch.co",
    "goodfirms.co", "goodfirms.io",
    "lusha.com",
    "sortlist.com",
    "expertise.com",
    "themanifest.com",
    "designrush.com",
    "upcity.com",
    "g2.com",
    "capterra.com",
    "softwareadvice.com",
    "bark.com",
    "manifest.com",
    "trustpilot.com",
    "hotfrog.com",
    "brownbook.net",
    "cylex.us",
    "europages.com",
    "kompass.com",
})

# Localization / translation trade directories & member lists (free listings).
_LSP_DIRECTORY_HOSTS = frozenset({
    "proz.com",
    "translationcafe.com",
    "translatorscafe.com",  # common variant
    "translationdirectory.com",
    "gala-global.org",
    "atanet.org",
    "ata-divisions.org",
    "translatorswithoutborders.org",
    "twb.ngo",
})

# Hosts we open as company-list sources (still blocked as lead domains).
DIRECTORY_SCRAPE_HOSTS = _GENERAL_DIRECTORY_HOSTS | _LSP_DIRECTORY_HOSTS

# Industry slug → extra scrape hosts (merged into detection at query time
# via DIRECTORY_SCRAPE_HOSTS; kept here for SERP query generation).
_INDUSTRY_DIRECTORY_HOSTS: dict[str, frozenset[str]] = {
    "localization": _LSP_DIRECTORY_HOSTS,
    "translation": _LSP_DIRECTORY_HOSTS,
    "subtitling": _LSP_DIRECTORY_HOSTS,
    "media": _LSP_DIRECTORY_HOSTS,
}

# Title signals for “Top 10 / best companies” listicles on any host
_LISTICLE_TITLE = (
    "top 10", "top 20", "top 50", "top translation", "top localization",
    "best 10", "best 20", "best companies", "best translation",
    "list of ", "directory of", "companies list", "agency list",
    "top agencies", "top firms", "rankings", "reviews", "blue board",
    "member directory", "company directory", "find a translator",
)

_CTA_TEXT = re.compile(
    r"^(visit(\s+website)?|website|view\s+(profile|website|site)|"
    r"see\s+(more|profile)|learn\s+more|read\s+more|profile|"
    r"contact|directions|call|email|share|compare)$",
    re.I,
)
_MAX_COMPANIES = 50
_HTTP_TIMEOUT = 8

# Industries that benefit from LSP trade directories
_LSP_INDUSTRIES = frozenset({
    "localization", "translation", "subtitling", "",
})


def directory_search_queries(
    industry_slug: str = "",
    country_name: str = "",
) -> list[str]:
    """
    SERP templates that deliberately hit free directories listing companies.
    Results are scraped as verified sources (directory host never kept).
    """
    ind = (industry_slug or "localization").strip().lower()
    ctry = (country_name or "").strip()
    if ctry in ("All Countries", "all countries"):
        ctry = ""
    geo = f" {ctry}" if ctry else ""
    qs: list[str] = []

    # General free dirs — any industry
    label = ind if ind not in ("", "all") else "companies"
    qs += [
        f"site:clutch.co {label}{geo}",
        f"site:goodfirms.co {label}{geo}",
        f"site:goodfirms.io {label}{geo}",
        f"top {label} companies{geo} clutch",
        f"top {label} companies{geo} goodfirms",
        f"{label} companies directory{geo}",
        f"list of {label} companies{geo}",
    ]

    # Localization / translation trade directories
    if ind in _LSP_INDUSTRIES or ind in _INDUSTRY_DIRECTORY_HOSTS:
        qs += [
            f"site:proz.com translation company{geo}",
            f"site:proz.com blueboard{geo}",
            f"site:proz.com companies{geo}",
            f"proz.com blue board{geo}",
            f"site:translationdirectory.com{geo}",
            f"site:translatorscafe.com{geo}",
            f"site:translationcafe.com{geo}",
            f"translation agencies directory{geo}",
            f"localization companies directory{geo}",
            f"language service providers directory{geo}",
            f"LSP directory{geo}",
            f"site:gala-global.org members{geo}",
            f"site:atanet.org directory{geo}",
        ]
        if ctry:
            qs += [
                f"proz.com {ctry} translation company",
                f"translationdirectory.com {ctry}",
                f"translatorscafe.com {ctry} agency",
            ]

    return list(dict.fromkeys(q.strip() for q in qs if q and q.strip()))


def _host_matches_directory(domain: str) -> bool:
    d = (domain or "").lower().removeprefix("www.")
    if not d:
        return False
    return any(d == h or d.endswith("." + h) for h in DIRECTORY_SCRAPE_HOSTS)


def is_directory_scrape_target(url: str, title: str = "") -> bool:
    """True when this SERP hit is a directory / Top-N list to mine."""
    dom = get_domain(url or "")
    if _host_matches_directory(dom):
        return True
    title_lc = (title or "").lower()
    if not title_lc:
        return False
    list_signals = (
        "top ", "best ", "list of", "directory", "rankings",
        "companies in", "agencies in", "firms in",
        "companies list", "agency list",
    )
    # Strong title cues (Top 10 / directory of / …)
    if any(sig in title_lc for sig in _LISTICLE_TITLE):
        return any(s in title_lc for s in list_signals)
    # Also catch "Translation … Companies In Australia" without "Top N"
    return any(s in title_lc for s in (
        "companies in", "agencies in", "firms in",
        "list of ", "directory of",
    ))


def extract_names_from_snippet(snippet: str) -> list[str]:
    """
    Pull company names from SERP snippets like:
    'Bayan-tech · Ali Saad Agency · DB Group · saudisoft'
    or numbered '1. Milestone 2. GTE Localize'.
    """
    text = (snippet or "").strip()
    if not text:
        return []
    names: list[str] = []

    # Numbered ranks: split on "1." "2." markers (handles inline lists)
    if re.search(r"\d{1,2}[.)]\s*[A-Za-z]", text):
        parts = re.split(r"\d{1,2}[.)]\s*", text)
        for p in parts:
            p = p.strip(" ·•|-–—;,\t")
            if not p or not re.match(r"^[A-Za-z]", p):
                continue
            # Take one company-sized chunk (stop at next sentence junk)
            chunk = re.split(r"\s{2,}|\s+[·•]\s+", p)[0].strip()
            chunk = re.sub(r"\s+\d{1,2}\s*$", "", chunk).strip()
            if 2 <= len(chunk) <= 80:
                names.append(chunk)

    # Bullet / middle-dot / pipe separated lists
    if "·" in text or "•" in text or "●" in text:
        parts = re.split(r"\s*[·•●]\s*", text)
        for p in parts:
            p = p.strip(" .-–—|")
            # Drop leading "List of … in Country" boilerplate, keep trailing name
            p = re.sub(
                r"^(?:list of|recommended|top\s+\d+)\s+"
                r"[\w &/,-]+?\s+in\s+[\w\s]+\s+",
                "",
                p,
                flags=re.I,
            ).strip(" .-–—|")
            if ":" in p and len(p.split(":")[0]) < 40:
                p = p.split(":", 1)[-1].strip()
            if 2 <= len(p) <= 80 and not _CTA_TEXT.match(p):
                if re.match(r"^[A-Za-z]", p):
                    names.append(p)

    # Dedupe preserve order
    out: list[str] = []
    seen: set[str] = set()
    for n in names:
        n = re.sub(r"\s+", " ", n).strip()
        n = re.sub(r"\s+\d{1,2}\s*$", "", n).strip()
        key = n.lower()
        if len(n) < 2 or key in seen:
            continue
        if any(x in key for x in (
            "http", "www.", "companies are listed", "showing ",
            "database", "reviews", "rankings", "get access",
        )):
            continue
        seen.add(key)
        out.append(n)
    return out[:_MAX_COMPANIES]



def _extract_from_html(html: str, page_url: str) -> list[dict]:
    """Extract {title, link} company candidates from directory HTML."""
    page_dom = get_domain(page_url)
    base = page_url if "://" in page_url else f"https://{page_url}"
    items: list[dict] = []
    seen: set[str] = set()

    def _push(name: str, href: str) -> None:
        name = re.sub(r"\s+", " ", (name or "")).strip()
        name = re.sub(r"^\d+[.)]\s*", "", name).strip()
        if len(name) < 2 or len(name) > 120:
            return
        if _CTA_TEXT.match(name):
            return
        key = name.lower()
        if key in seen:
            return
        href = href or ""
        if href and not href.startswith("http"):
            href = urljoin(base, href)
        if href:
            dom = get_domain(href)
            if not dom or dom == page_dom or is_blocked(href):
                href = ""
            if any(x in (href or "").lower() for x in (
                "facebook.com", "linkedin.com", "twitter.com", "youtube.com",
            )):
                href = ""
        seen.add(key)
        items.append({"title": name, "link": href, "snippet": ""})

    # Anchors: <a href="...">text</a>
    for m in re.finditer(
        r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',
        html,
        flags=re.I | re.DOTALL,
    ):
        href, inner = m.group(1), m.group(2)
        text = re.sub(r"<[^>]+>", " ", inner)
        text = re.sub(r"\s+", " ", text).strip()
        if href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        abs_url = urljoin(base, href)
        dom = get_domain(abs_url)
        if not dom or dom == page_dom:
            continue
        if is_blocked(abs_url):
            # Directory cross-links (clutch→goodfirms) — skip
            continue
        if _CTA_TEXT.match(text) or not text:
            # Visit Website → use domain slug as weak name; resolve later
            slug = dom.split(".")[0]
            if len(slug) >= 3:
                _push(slug.replace("-", " ").title(), abs_url)
            continue
        if 2 <= len(text) <= 100:
            _push(text, abs_url)

    # Numbered / bulleted names in visible text (no link)
    text_only = re.sub(r"<script[^>]*>.*?</script>", " ", html,
                       flags=re.I | re.DOTALL)
    text_only = re.sub(r"<style[^>]*>.*?</style>", " ", text_only,
                       flags=re.I | re.DOTALL)
    text_only = re.sub(r"<[^>]+>", "\n", text_only)
    for m in re.finditer(
        r"(?:^|\n)\s*(\d{1,2})[.)]\s+([A-Za-z][^\n]{1,80})",
        text_only,
    ):
        _push(m.group(2).strip(), "")

    return items[:_MAX_COMPANIES]


def _http_get(url: str) -> str:
    import random
    import requests as _req
    from sources.utils import _USER_AGENTS

    target = url if "://" in url else f"https://{url}"
    headers = {"User-Agent": random.choice(_USER_AGENTS)}
    try:
        try:
            resp = _req.get(
                target, timeout=_HTTP_TIMEOUT, headers=headers,
                allow_redirects=True, verify=True,
            )
        except _req.exceptions.SSLError:
            resp = _req.get(
                target, timeout=_HTTP_TIMEOUT, headers=headers,
                allow_redirects=True, verify=False,
            )
        if resp is None or resp.status_code != 200:
            return ""
        return resp.text or ""
    except Exception:
        return ""


def scrape_directory_companies(
    url: str,
    *,
    title: str = "",
    snippet: str = "",
    organic: list | None = None,
    max_companies: int = _MAX_COMPANIES,
) -> list[dict]:
    """
    Open a directory / listicle URL (and mine its SERP snippet) → verified
    company rows: {link, title, snippet, source: 'directory'}.

    Never returns the directory host as a company.
    """
    organic = list(organic or [])
    raw: list[dict] = []

    for name in extract_names_from_snippet(snippet):
        raw.append({"title": name, "link": "", "snippet": snippet[:200]})

    html = _http_get(url)
    if html:
        raw.extend(_extract_from_html(html, url))

    # Also try resolving snippet names against any links harvested from HTML
    html_links = [r.get("link") or "" for r in raw if r.get("link")]
    for row in raw:
        if row.get("link"):
            continue
        href = resolve_ai_overview_link(
            row.get("title") or "",
            "",
            organic=organic,
            aio_links=html_links,
        )
        if href:
            row["link"] = href

    page_dom = get_domain(url)
    cleaned: list[dict] = []
    for row in raw:
        href = row.get("link") or ""
        if href and get_domain(href) == page_dom:
            row = {**row, "link": ""}
        cleaned.append(row)

    out = merge_serp_verified_results(
        cleaned, organic=organic, source="directory",
    )
    return out[:max_companies]
