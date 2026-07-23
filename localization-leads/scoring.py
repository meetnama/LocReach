"""
scoring.py — Company qualification scoring (no API, pure signals).

Scores a company's scraped pages on a 0-100 scale based on transparent,
explainable signals. Industry evidence is mandatory and must be strong enough
that contact/about/LinkedIn padding cannot rescue an off-topic site.
"""
from config import INDUSTRY_KEYWORDS, RELEVANCE_KEYWORDS


# Terms that often appear outside LSP/translation (e.g. "manufacturing localization").
# Alone they do NOT satisfy the industry gate.
_AMBIGUOUS_INDUSTRY_TERMS = frozenset({
    "localization", "localisation", "localize", "localise",
    "l10n", "i18n", "internationalization", "globaliz", "language",
})

# Clear LSP / language-services signals (substring match against keyword hits).
_STRONG_INDUSTRY_MARKERS = (
    "translation", "translat", "traduct", "übersetzung", "tercüme",
    "ترجمة", "تعريب", "توطين", "مترجم",
    "language service", "lsp", "linguist", "interpreter", "interpreting",
    "subtitl", "dubbing", "sworn", "certified translat", "multilingual",
    "linguistic", "transcription",
)


def _industry_keyword_list(industry_slug: str) -> list:
    slug = (industry_slug or "").lower().strip()
    if slug and slug in INDUSTRY_KEYWORDS:
        return list(INDUSTRY_KEYWORDS[slug])
    return list(RELEVANCE_KEYWORDS)


def _is_strong_industry_term(kw: str) -> bool:
    k = (kw or "").lower()
    if not k or k in _AMBIGUOUS_INDUSTRY_TERMS:
        return False
    return any(m in k or k in m for m in _STRONG_INDUSTRY_MARKERS)


def industry_evidence_ok(hits: list[str]) -> bool:
    """
    Chosen industry is the primary keep factor.
    Need real LSP/language evidence — not a lone "localization" hit.
    """
    if not hits:
        return False
    strong = [h for h in hits if _is_strong_industry_term(h)]
    # ≥2 strong terms, or 1 strong + enough total keyword density
    if len(strong) >= 2:
        return True
    if len(strong) >= 1 and len(hits) >= 3:
        return True
    return False


# ── Public API ─────────────────────────────────────────────────────────────────

def score_company(
    site_data: dict,
    domain: str,
    linkedin_url: str = "",
    industry_slug: str = "",
) -> tuple:
    """
    Score a company site. Returns (score, tier, reasons).

    Industry (chosen INDUSTRY_KEYWORDS, else RELEVANCE_KEYWORDS) is mandatory.
    Insufficient industry evidence forces tier=weak regardless of contact/LI.
    """
    if not site_data:
        return 0, "weak", []

    reasons = []
    score = 0
    text = (site_data.get("markdown", "") or "").lower()
    links = site_data.get("links", []) or []

    # 1. Industry relevance — keyword density (mandatory; max 50)
    keywords = _industry_keyword_list(industry_slug)
    hits = [kw for kw in keywords if kw.lower() in text]
    if not hits:
        return 0, "weak", ["missing industry keywords"]
    score += min(50, len(hits) * 7)
    reasons.append(f"{len(hits)} industry keywords")

    # 2. Real-company signals (max 30)
    if _has_contact_page(links):
        score += 20
        reasons.append("has contact page")
    if _has_about_or_team(links):
        score += 10
        reasons.append("has about/team page")

    # 3. Reachability (max 10)
    if linkedin_url:
        score += 10
        reasons.append("has LinkedIn")

    if score > 100:
        score = 100

    # Industry is the main factor — contact/LI must not rescue off-topic sites.
    if not industry_evidence_ok(hits):
        reasons.append("insufficient industry evidence")
        score = min(score, 29)
        return score, "weak", reasons

    return score, _tier_from_score(score), reasons


def _tier_from_score(score: int) -> str:
    if score >= 60:
        return "strong"
    if score >= 30:
        return "possible"
    return "weak"


# ── Signal detectors ───────────────────────────────────────────────────────────

_CONTACT_PATHS = ("/contact", "/kontakt", "/impressum", "/nous-ecrire",
                  "/contattaci", "/contato", "/contacto", "/contact-us")
_ABOUT_PATHS = ("/about", "/team", "/uber-uns", "/a-propos", "/chi-siamo",
                "/sobre", "/our-team", "/company", "/about-us")


def _iter_hrefs(links):
    """Yield href strings; links may be bare strings or dicts with 'href'."""
    for link in links:
        if isinstance(link, str):
            yield link
        elif isinstance(link, dict):
            yield link.get("href") or ""


def _has_contact_page(links) -> bool:
    return any(_path_in_link(href, _CONTACT_PATHS) for href in _iter_hrefs(links))


def _has_about_or_team(links) -> bool:
    return any(_path_in_link(href, _ABOUT_PATHS) for href in _iter_hrefs(links))


def _path_in_link(href: str, paths: tuple) -> bool:
    if not href:
        return False
    h = href.lower()
    return any(p in h for p in paths)
