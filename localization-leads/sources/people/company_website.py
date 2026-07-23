"""
sources/people/company_website.py — People source: company website team pages

Scrapes common "Meet the Team" / "Our Staff" / "Contact" pages on a company's
own website and extracts employee names + job titles using heuristics.

No API required. Completely free.

Detection strategy (in order of precision):
  1. Schema.org Person markup  — structured data, highest precision
  2. Common HTML card patterns — team-member / staff-card div patterns
  3. Proximity text heuristic  — name within 100 chars of a target title keyword

Validation:
  • Extracted names must be 2–4 words, each starting with a capital letter
  • Names may not contain digits, common English stop-words, or LSP jargon
  • Titles must match at least one TARGET_TITLES keyword
  • Max MAX_PER_DOMAIN contacts extracted per company

Works best on LSP sites that publish a "Meet the Team" or "Our Staff" page
(many do). False-positive rate is low because we only keep names co-located
with a target job title keyword.
"""
import re
import time
import requests
from typing import List, Optional, Tuple

from sources.base import PeopleSource, Company, Person, LogFn
from config import TARGET_TITLES


# ── Pages probed in order ──────────────────────────────────────────────────────
_TEAM_PATHS = [
    "/team",          "/our-team",        "/meet-the-team",
    "/staff",         "/our-staff",       "/people",
    "/about",         "/about-us",        "/about/team",
    "/management",    "/leadership",      "/company/team",
    "/contact",       "/contact-us",
]

# ── Name regex: 2–4 capitalised words (supports accented chars) ───────────────
_NAME_RE = re.compile(
    r'\b([A-ZÁÉÍÓÚÀÂÄÈÊËÎÏÔÙÛÜÆŒÇÑ][a-záéíóúàâäèêëîïôùûüæœçñ\'-]+'
    r'(?:\s+[A-ZÁÉÍÓÚÀÂÄÈÊËÎÏÔÙÛÜÆŒÇÑ][a-záéíóúàâäèêëîïôùûüæœçñ\'-]+){1,3})\b'
)

# Words that must NOT appear in a valid name — if any token in the candidate
# matches, the whole name is rejected. Keep these to words that are virtually
# never part of a real human name.
_BAD_WORDS = {
    # ── Articles / pronouns / conjunctions ───────────────────────────────
    "our", "the", "your", "with", "from", "about", "contact",
    "more", "read", "learn", "view", "here", "this", "that",
    "all", "any", "some", "and", "or", "for", "but", "not",
    "you", "we", "they", "us", "my", "me", "him", "her", "them",

    # ── Industry / company-page words ────────────────────────────────────
    "translation", "localization", "localisation", "language",
    "services", "solutions", "company", "agency", "team", "staff",
    "group", "global", "international", "management", "leadership",
    "meet", "welcome", "hello", "join", "get",

    # ── Cookie / privacy / consent banners ───────────────────────────────
    "privacy", "policy", "policies", "cookie", "cookies", "consent",
    "settings", "accept", "decline", "close", "preferences",
    "strictly", "necessary", "compliance", "sandbox",
    "gdpr", "ccpa", "analytics", "tracking",

    # ── Page chrome / call-to-action ────────────────────────────────────
    "free", "quote", "request", "speak", "click", "submit",
    "expand", "networking", "reach", "explore", "discover",
    "now", "today", "soon",

    # ── Services / products mistaken for people ─────────────────────────
    "subtitling", "voiceover", "dubbing", "transcription",
    "interpretation", "interpretations", "interpreting",
    "trade", "markets", "market", "authority", "budgets", "budget",
    "media", "paid",

    # ── Specific junk seen in real cleanup runs ─────────────────────────
    "deepen", "talentos",
}

# Words that mark a name as an honorific / suffix (not a real last name)
_BAD_SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "phd", "mba", "ma", "ba", "msc"}


def _is_valid_name(name: str) -> bool:
    parts = name.strip().split()
    if len(parts) < 2 or len(parts) > 4:
        return False
    if not all(p[0].isupper() for p in parts if p):
        return False
    if any(c.isdigit() for c in name):
        return False
    lparts = [p.lower() for p in parts]
    if any(p in _BAD_WORDS for p in lparts):
        return False
    if lparts[-1] in _BAD_SUFFIXES:
        return False
    return True


def _title_matches(title: str) -> bool:
    t = title.lower()
    return any(kw in t for kw in TARGET_TITLES)


# ── HTML fetch ─────────────────────────────────────────────────────────────────

def _get(url: str) -> Tuple[str, str]:
    """
    Fetch url → (raw_html, plain_text).
    Returns ("", "") on error or non-200.
    """
    try:
        r = requests.get(
            url, timeout=12,
            headers={"User-Agent": "Mozilla/5.0 (compatible; LeadBot/1.0)"},
            allow_redirects=True,
        )
        if r.status_code != 200:
            return "", ""
        html = r.text

        # Plain text: strip scripts/styles/nav/footer first
        text = html
        for tag in ("script", "style", "noscript", "nav", "footer", "head", "header"):
            text = re.sub(
                rf'<{tag}[^>]*>.*?</{tag}>', ' ', text,
                flags=re.DOTALL | re.IGNORECASE,
            )
        text = re.sub(r'<[^>]+>', ' ', text)
        text = re.sub(r'\s+',     ' ', text).strip()
        return html, text
    except Exception:
        return "", ""


# ── Extraction strategies ──────────────────────────────────────────────────────

def _schema_org(html: str) -> List[dict]:
    """
    Parse schema.org/Person microdata blocks:
      <div itemtype="…/Person"> … itemprop="name" … itemprop="jobTitle" … </div>
    """
    people = []
    blocks = re.findall(
        r'itemtype=["\'][^"\']*(?:schema\.org/)?Person["\'][^>]*>(.*?)</(?:div|article|li|section)[^>]*>',
        html, re.DOTALL | re.IGNORECASE,
    )
    for block in blocks:
        name_m  = re.search(r'itemprop=["\']name["\'][^>]*>([^<]{2,60})',  block, re.IGNORECASE)
        title_m = re.search(r'itemprop=["\']jobTitle["\'][^>]*>([^<]{2,80})', block, re.IGNORECASE)
        if name_m and title_m:
            name  = re.sub(r'\s+', ' ', name_m.group(1)).strip()
            title = re.sub(r'\s+', ' ', title_m.group(1)).strip()
            if _is_valid_name(name) and _title_matches(title):
                li_m   = re.search(r'href=["\']([^"\']*linkedin\.com/in/[^"\'? ]+)["\']',
                                   block, re.IGNORECASE)
                li_url = li_m.group(1) if li_m else ""
                people.append({"name": name, "title": title, "linkedin_url": li_url})
    return people


def _card_patterns(html: str) -> List[dict]:
    """
    Parse common team-card HTML patterns.
    Looks for a heading (h2/h3/h4/strong) followed closely by a role paragraph
    within a common team-card wrapper div/article/li.
    """
    people = []
    # Find any div/article/li that has both a name-ish heading and a title
    card_re = re.compile(
        r'<(?:div|article|li|section)[^>]*(?:class|id)=["\'][^"\']*'
        r'(?:team|staff|member|person|employee|card|bio)[^"\']*["\'][^>]*>(.*?)'
        r'</(?:div|article|li|section)>',
        re.DOTALL | re.IGNORECASE,
    )
    heading_re = re.compile(
        r'<(?:h[2-4]|strong|b)[^>]*>\s*([^<]{3,60})\s*</(?:h[2-4]|strong|b)>',
        re.IGNORECASE,
    )
    para_re = re.compile(
        r'<(?:p|span|div)[^>]*>\s*([^<]{3,80})\s*</(?:p|span|div)>',
        re.IGNORECASE,
    )
    seen = set()
    for card in card_re.finditer(html):
        block = card.group(1)
        # Collect all headings and paragraphs inside the card
        headings = [m.group(1).strip() for m in heading_re.finditer(block)]
        paras    = [m.group(1).strip() for m in para_re.finditer(block)]
        # Try each heading as a name, each para as a title
        # Look for a LinkedIn profile link anywhere in this card block
        li_m   = re.search(r'href=["\']([^"\']*linkedin\.com/in/[^"\'? ]+)["\']',
                           block, re.IGNORECASE)
        li_url = li_m.group(1) if li_m else ""

        for h in headings:
            h_clean = re.sub(r'\s+', ' ', h)
            if not _is_valid_name(h_clean):
                continue
            for p in paras:
                p_clean = re.sub(r'\s+', ' ', p)
                if _title_matches(p_clean) and h_clean not in seen:
                    seen.add(h_clean)
                    people.append({"name": h_clean, "title": p_clean[:80],
                                   "linkedin_url": li_url})
                    break
    return people


def _proximity(text: str) -> List[dict]:
    """
    Text-proximity heuristic: find each TARGET_TITLES keyword in plain text,
    then look within ±100 characters for a valid proper name.

    Name before keyword → more natural ("Sarah Smith, Vendor Manager")
    Name after keyword  → fallback ("Vendor Manager: Sarah Smith")
    """
    people = []
    seen   = set()
    text_l = text.lower()

    for kw in TARGET_TITLES:
        pos = 0
        while True:
            idx = text_l.find(kw, pos)
            if idx == -1:
                break
            pos = idx + 1

            # ── window before keyword ────────────────────────────────────────
            before     = text[max(0, idx - 100): idx]
            names_b    = [m for m in _NAME_RE.findall(before) if _is_valid_name(m)]
            candidate  = names_b[-1] if names_b else None   # closest before

            if not candidate:
                # ── window after keyword ─────────────────────────────────────
                after   = text[idx + len(kw): min(len(text), idx + len(kw) + 100)]
                names_a = [m for m in _NAME_RE.findall(after) if _is_valid_name(m)]
                candidate = names_a[0] if names_a else None

            if not candidate or candidate in seen:
                continue

            # Use the matched keyword as the title — raw surrounding text is
            # unreliable (catches page copy like "Get the scoop from the people
            # who work here!"). The keyword IS the job title signal.
            title = kw.title()

            seen.add(candidate)
            people.append({"name": candidate, "title": title})

    return people


# ── People source ──────────────────────────────────────────────────────────────

class CompanyWebsitePeople(PeopleSource):
    """
    Scrapes company team / about / staff pages for employees with target titles.

    Free — no API keys needed.
    Probes up to len(_TEAM_PATHS) URLs, stopping once MAX_PER_DOMAIN contacts
    are found or all paths are exhausted.
    Extraction is tried in order: Schema.org → card patterns → proximity text.
    """
    name           = "Website"
    MAX_PER_DOMAIN = 5

    def find_people(self, company: Company) -> List[Person]:
        domain = company.domain
        self.log("SITE", f"  Website people: {domain}")

        found:      List[Person] = []
        seen_names: set          = set()

        for path in _TEAM_PATHS:
            if len(found) >= self.MAX_PER_DOMAIN:
                break

            url        = f"https://{domain}{path}"
            html, text = _get(url)
            if not html and not text:
                time.sleep(0.2)
                continue

            # Try extraction strategies in order of precision.
            # _proximity() was removed — it generated 80%+ false positives
            # (cookie banner text, nav menus, page copy mistaken for names).
            # Only structured HTML extractors are used now.
            candidates: List[dict] = (
                _schema_org(html)
                or _card_patterns(html)
            )

            added_this_page = 0
            for c in candidates:
                if len(found) >= self.MAX_PER_DOMAIN:
                    break

                name  = c["name"].strip()
                title = c.get("title", "").strip()
                parts = name.split()
                if len(parts) < 2:
                    continue

                first = parts[0]
                last  = " ".join(parts[1:])
                key   = (first.lower(), last.lower())
                if key in seen_names:
                    continue

                seen_names.add(key)
                found.append(Person(
                    first         = first,
                    last          = last,
                    title         = title[:80],
                    domain        = domain,
                    company_name  = company.name,
                    people_source = self.name,
                    linkedin_url  = c.get("linkedin_url", ""),
                ))
                added_this_page += 1

            if added_this_page:
                # Found people on this page — no need to crawl more paths
                break

            time.sleep(0.4)

        self.log("INFO", f"  [Website] {len(found)} contact(s) from site pages")
        return found
