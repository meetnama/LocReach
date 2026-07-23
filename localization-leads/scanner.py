"""
scanner.py — Company site scanner (Layer 2 of the pipeline).

Responsibilities:
  1. Fetch homepage via Chrome (JS-rendered, free) with plain-HTTP fallback
  2. Verify the site is a real, multi-page company (quality + relevance check)
  3. Extract the company's LinkedIn page URL
     → if not found on the site, fall back to a Google search
  4. Extract a clean company name from the page
"""
import re
from sources.base import Company
from sources.utils import chrome_scrape, get_domain, country_from_domain
from config import INDUSTRY_KEYWORDS, RELEVANCE_KEYWORDS


# ── Step 1: fetch homepage ─────────────────────────────────────────────────────

def scrape_site(url: str) -> dict | None:
    """
    Fetch a company homepage using Chrome (handles JS-rendered sites) with a
    plain requests.get fallback.  Returns {'markdown': str, 'links': list}.
    """
    return chrome_scrape(url)


# ── Parking / placeholder domain signals ──────────────────────────────────────
_PARKING_SIGNALS = (
    "buy this domain",
    "this domain is for sale",
    "domain for sale",
    "domain is available for purchase",
    "parked by",
    "parked free",
    "domain parking",
    "godaddy.com/forsale",
    "sedo.com",
    "coming soon",
    "under construction",
    "this site is under construction",
    "launching soon",
    "website coming soon",
)

_MIN_SITE_PAGES = 4
_ASSET_EXT = (
    ".css", ".js", ".mjs", ".map", ".png", ".jpg", ".jpeg", ".gif", ".svg",
    ".webp", ".ico", ".woff", ".woff2", ".ttf", ".eot", ".pdf", ".zip",
    ".mp4", ".mp3", ".xml", ".json",
)


def _iter_hrefs(links):
    for link in links or []:
        if isinstance(link, str):
            yield link
        elif isinstance(link, dict):
            yield link.get("href") or ""


def count_internal_pages(site_data: dict, domain: str) -> int:
    """
    Count distinct internal HTML-ish pages linked from the homepage.
    Homepage itself counts as 1; external / asset / mailto links are ignored.
    """
    if not site_data:
        return 0

    bare = (domain or "").lower().removeprefix("www.")
    paths: set[str] = {"/"}  # scraped homepage

    for href in _iter_hrefs(site_data.get("links")):
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        h = href.strip()
        # Protocol-relative or absolute
        if h.startswith("//"):
            h = "https:" + h
        if h.startswith("http://") or h.startswith("https://"):
            # same-domain only
            m = re.match(r"https?://([^/]+)(/.*)?$", h, re.I)
            if not m:
                continue
            host = m.group(1).lower().removeprefix("www.").split(":")[0]
            if host != bare and not host.endswith("." + bare):
                continue
            path = m.group(2) or "/"
        elif h.startswith("/"):
            path = h
        else:
            # relative path
            path = "/" + h

        path = path.split("#", 1)[0].split("?", 1)[0] or "/"
        path_lc = path.lower()
        if any(path_lc.endswith(ext) for ext in _ASSET_EXT):
            continue
        # normalize trailing slash (except root)
        if len(path) > 1 and path.endswith("/"):
            path = path.rstrip("/")
        paths.add(path.lower())

    return len(paths)


# ── Step 2: quality check ─────────────────────────────────────────────────────

def is_quality_site(site_data: dict, domain: str, industry_slug: str = "") -> bool:
    """
    True if the site looks like a real, accessible company website whose
    content actually matches what was searched for.

    A site FAILS if:
      - Page text < 100 chars  (parked / placeholder / empty response)
      - Page contains domain-parking or under-construction signals
      - Fewer than 4 distinct internal pages (homepage + nav links)
      - No localization / relevance keywords on the scraped homepage (mandatory)
      - When an industry is selected: homepage also lacks industry keywords
    """
    if not site_data:
        return False

    text    = site_data.get("markdown", "").strip()
    text_lc = text.lower()

    # Hard fail: not enough content to be a real page
    if len(text) < 100:
        return False

    # Hard fail: domain parking / placeholder signals
    if any(signal in text_lc for signal in _PARKING_SIGNALS):
        return False

    # Hard fail: too small a site (need a real multi-page company)
    if count_internal_pages(site_data, domain) < _MIN_SITE_PAGES:
        return False

    # Hard fail (mandatory): localization / relevance keywords on page
    if not any(kw in text_lc for kw in RELEVANCE_KEYWORDS):
        return False

    # When an industry is selected, homepage must also match that industry
    industry_kws = INDUSTRY_KEYWORDS.get((industry_slug or "").lower())
    if industry_kws and not any(kw in text_lc for kw in industry_kws):
        return False

    return True


# ── Step 3: LinkedIn company URL ──────────────────────────────────────────────

def extract_linkedin_url(site_data: dict) -> str:
    """Return the first linkedin.com/company/ URL found in links or markdown."""
    if not site_data:
        return ""
    for link in site_data.get("links", []):
        href = link if isinstance(link, str) else (link.get("href") or "")
        if "linkedin.com/company/" in href:
            return href.split("?")[0].rstrip("/")
    m = re.search(
        r'https?://(?:www\.)?linkedin\.com/company/[^\s\)\]"\'<>]+',
        site_data.get("markdown", ""),
    )
    return m.group(0).rstrip("/") if m else ""


def find_linkedin_via_searxng(company_name: str) -> str:
    """
    Fallback: search SearXNG for a company's LinkedIn page.
    Tries two queries — strict site: first, then a broader fallback.
    Returns '' gracefully if SearXNG is down.

    company_name may be either a clean brand name or a bare domain
    (e.g. "daytranslations.com") — both work as SearXNG query terms.
    """
    from sources.utils import searxng_search

    # Strip TLD for cleaner matching (e.g. "daytranslations.com" → "daytranslations")
    clean = re.sub(r'\.[a-z]{2,6}$', '', company_name.lower()).replace('-', ' ')

    queries = [
        f'"{company_name}" site:linkedin.com/company',
        f'"{clean}" site:linkedin.com/company',
    ]

    for query in queries:
        try:
            results = searxng_search(query, num=5)
        except Exception:
            return ""   # SearXNG unreachable — degrade gracefully, no crash

        for r in results:
            link = r.get("link", "")
            if "linkedin.com/company/" in link:
                return link.split("?")[0].rstrip("/")

    return ""


# ── Step 4: company name ──────────────────────────────────────────────────────

# Words that signal an SEO/marketing title rather than a real company name
_SEO_WORDS = {
    "iso", "certified", "certifications", "accredited", "sworn", "official",
    "authorized", "agency", "services", "solutions", "provider", "bureau",
    "professional", "expert", "experts", "global", "international",
    "worldwide", "group", "translations", "translation", "localization",
    "localisation", "language", "multilingual", "company", "consultancy",
}


def _is_seo_title(name: str) -> bool:
    """True if the name looks like an SEO page title rather than a brand name."""
    words = set(name.lower().split())
    # Too many words = likely a sentence / tagline
    if len(words) > 5:
        return True
    # Heavily generic vocabulary = SEO spam
    if len(words & _SEO_WORDS) >= 2:
        return True
    return False


def extract_company_name(site_data: dict, google_title: str, li_url: str = "") -> str:
    """
    Best-effort company name — priority order:
      1. LinkedIn company slug  (most reliable — always the real brand identifier)
      2. First H1 heading in the page markdown (only if not SEO-looking)
      3. Left part of the Google result title (split on | - –)
    """
    # 1. LinkedIn slug: /company/blarlo → "Blarlo"
    #    Only trust slugs that contain hyphens (real multi-word names).
    #    Single-word slugs like "vananservicesinc" are just the company name
    #    concatenated with no spaces — useless for display, fall through.
    if li_url:
        m = re.search(r'linkedin\.com/company/([^/?#\s]+)', li_url)
        if m:
            slug = m.group(1).rstrip("/")
            if "-" in slug:                     # only trust hyphenated slugs
                name = slug.replace("-", " ").title()
                if name and not _is_seo_title(name):
                    return name

    # 2. H1 from page markdown
    if site_data:
        m = re.search(r'^#\s+(.+)', site_data.get("markdown", ""), re.MULTILINE)
        if m:
            candidate = m.group(1).strip()
            if not _is_seo_title(candidate):
                return candidate

    # 3. Google title fallback
    return re.split(r'[|\-–]', google_title)[0].strip()
