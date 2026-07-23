"""
sources/people/google_linkedin.py — Broad X-Ray search via SearXNG

NEW STRATEGY (session 19): search by COMPANY NAME ONLY, collect every result.
Do NOT filter by title here — the pipeline applies title_filter.passes()
based on company_type (lsp vs client) after merging X-Ray + LinkedIn-page
results.

Query format:
  site:linkedin.com/in/ "{company_name}"

Up to 3 candidate names are tried per company. The first candidate that
yields ≥1 result is used; we don't keep firing alternatives once we have
hits, because every LinkedIn profile that mentions the company will surface
under the best-matching candidate.

SearXNG ONLY — no Chrome/Google fallback. CAPTCHAs are unsolvable at scale.
"""
from __future__ import annotations

import os
import re
import time
from typing import List

from sources.base import PeopleSource, Company, Person, LogFn
from sources.utils import searxng_search, duckduckgo_search


# ── Search-name candidate construction ────────────────────────────────────────

_TLD_RE = re.compile(
    r'\.(com|org|net|io|co|ai|app|dev|me|uk|us|de|fr|es|it|nl|be|ch|at|se|no|dk|fi|'
    r'pl|cz|ru|jp|cn|kr|in|au|nz|br|mx|cl|ar|za|ae|sg|hk|tw|tr|gr|pt|ie|ro|hu|ua)\b',
    re.IGNORECASE,
)

_CORP_SUFFIX_RE = re.compile(
    r'[,\s]+(inc|llc|ltd|gmbh|sa|sas|sarl|co|corp|corporation|incorporated|limited|'
    r'company|group|holding|holdings|sl|srl|sp\.?\s*z\s*o\.?o\.?|kft|pvt|ag|kg|nv|bv)\.?\s*$',
    re.IGNORECASE,
)


def _build_search_names(company: Company) -> List[str]:
    """
    Generate ordered candidate search terms for X-Ray queries.

    Tries (in order):
      1. company.name — cleaned of Inc/Ltd/etc., but only if it's not a domain
      2. LinkedIn company slug (hyphens → spaces)
      3. Bare second-level domain (hyphens → spaces, drop TLD)
      4. Full domain with TLD — LinkedIn profiles often list the company website URL
         in their experience section, so "absolutetranslations.com" in the query
         finds profiles that mention the company website. This is the key fallback
         for companies where the stored name is just the domain.
    """
    candidates: List[str] = []
    seen_lower: set        = set()

    name   = (company.name or "").strip()
    domain = (company.domain or "").strip()
    li_url = (company.linkedin_url or "").strip()

    def _add(s: str) -> None:
        s = s.strip()
        if s and s.lower() not in seen_lower:
            seen_lower.add(s.lower())
            candidates.append(s)

    # 1) company.name — only if it doesn't look like a domain itself
    if name and not _TLD_RE.search(name):
        clean = _CORP_SUFFIX_RE.sub("", name).strip()
        _add(clean)

    # 2) LinkedIn company slug
    if "/company/" in li_url:
        slug       = li_url.split("/company/", 1)[1].rstrip("/").split("/")[0].split("?")[0]
        slug_words = slug.replace("-", " ").replace("_", " ").strip()
        _add(slug_words)

    # 3) Bare second-level domain (hyphens/underscores → spaces)
    if domain:
        bare       = domain.split(".")[0]
        bare_words = bare.replace("-", " ").replace("_", " ").strip()
        _add(bare_words)

    # 4) Full domain with TLD — finds profiles that list the company URL in experience
    #    Most valuable when company_name is just a domain (123/175 companies here).
    _add(domain)

    return candidates or ([name] if name else [domain] if domain else [])


# ── Former-employee snippet filter ────────────────────────────────────────────

_FORMER_RE = re.compile(
    r'\b(former|previously|ex-|past employee|alumni|alumna|retired|used to work)\b',
    re.IGNORECASE,
)

# Identifiers we should NEVER accept as a last name even if they pass the
# pattern (common LinkedIn URL artefacts and credentials)
_BAD_NAME_TOKENS = {
    "undefined", "null", "n/a", "jr", "sr", "ii", "iii", "iv",
    "phd", "mba", "ma", "linkedin", "member",
}


class GoogleLinkedInPeople(PeopleSource):
    """
    Broad X-Ray search. Returns raw Person objects with people_source='xray'.
    No title filter — caller filters via title_filter.passes() based on
    company_type.
    """
    name           = "xray"
    MAX_PER_DOMAIN = 10   # up to 10 raw hits per company (was 5 — wider net now)

    def __init__(self, log: LogFn = None,
                 max_per_domain: int = None, **_legacy):
        super().__init__(log)
        self.max_per_domain = max_per_domain or self.MAX_PER_DOMAIN

    # ─────────────────────────────────────────────────────────────────────────
    def find_people(self, company: Company,
                    debug: dict = None) -> List[Person]:
        """
        Returns up to self.max_per_domain Person objects. If `debug` is passed,
        per-query stats are stored under debug['queries'] for the UI log.
        """
        if debug is not None:
            debug.setdefault("queries", [])

        _searxng_url = os.getenv("SEARXNG_URL", "http://localhost:8888").strip()
        if not _searxng_url:
            self.log("xray", "  [X-Ray] SKIPPED — SearXNG not configured.")
            return []

        def _search_searxng(query: str) -> list:
            try:
                return searxng_search(query, num=10)
            except Exception as exc:
                self.log("xray", f"  [X-Ray] SearXNG error: {exc}")
                return []

        def _search_ddg(query: str) -> list:
            try:
                return duckduckgo_search(query, num=10)
            except Exception as exc:
                self.log("xray", f"  [X-Ray] DDG error: {exc}")
                return []

        def _parse_results(results: list, source_tag: str) -> int:
            """Process results list into all_people. Returns count added."""
            added = 0
            for r in results:
                if len(all_people) >= self.max_per_domain:
                    break

                url     = r.get("link",    "")
                title   = r.get("title",   "")
                snippet = (r.get("snippet") or "").lower()

                if "linkedin.com/in/" not in url:
                    continue
                if url in seen_urls:
                    continue

                if _FORMER_RE.search(snippet) or _FORMER_RE.search(title):
                    continue

                full_name_raw = re.sub(r'\s*\((?:she|he|they|ze|xe)[^)]*\)', '',
                                       title, flags=re.IGNORECASE)
                full_name, job_title = _parse_linkedin_title(full_name_raw)
                if not full_name:
                    continue

                full_name = re.sub(r'\s*\([^)]*\)', '', full_name).strip()
                full_name = re.sub(
                    r',?\s+(?:PMP|MBA|PhD|MSc|BSc|CPA|CELTA|DELTA|MA|BA|JD|MD|'
                    r'MCIL|MITI|ITI|FCIL|Cert\.?\s*\w*)\b.*$',
                    '', full_name, flags=re.IGNORECASE,
                ).strip()

                parts = full_name.strip().split()
                if len(parts) < 2:
                    continue
                first_part = parts[0]
                last_part  = " ".join(parts[1:])

                last_stripped = last_part.rstrip(".,;:")
                if (
                    len(last_stripped) < 2
                    or last_part.lower()  in _BAD_NAME_TOKENS
                    or first_part.lower() in _BAD_NAME_TOKENS
                    or any(c.isdigit() for c in full_name)
                ):
                    continue

                name_key = (first_part.lower(), last_part.lower())
                if name_key in seen_names:
                    continue

                seen_urls.add(url)
                seen_names.add(name_key)
                all_people.append(Person(
                    first         = first_part,
                    last          = last_part,
                    title         = (job_title or "")[:80],
                    domain        = company.domain,
                    company_name  = company.name,
                    linkedin_url  = url,
                    people_source = self.name,
                ))
                added += 1
            return added

        search_names = _build_search_names(company)
        if not search_names:
            self.log("xray", "  [X-Ray] no usable search name — skipping")
            return []

        self.log("xray", f"  candidates for {company.domain}: {search_names}")

        all_people: List[Person] = []
        seen_urls:  set          = set()
        seen_names: set          = set()

        # ── Phase A: SearXNG — try each candidate in order ───────────────────
        for cand_idx, search_name in enumerate(search_names, 1):
            query = f'site:linkedin.com/in/ "{search_name}"'
            self.log("xray", f"  [{cand_idx}/{len(search_names)}] {query}")
            results    = _search_searxng(query)
            cand_added = _parse_results(results, "SearXNG")
            time.sleep(0.2)

            if debug is not None:
                debug["queries"].append({
                    "name":    search_name,
                    "query":   query,
                    "engine":  "SearXNG",
                    "results": len(results),
                    "added":   cand_added,
                })

            if cand_added > 0:
                break  # first candidate with hits wins

            if len(all_people) >= self.max_per_domain:
                break

        # ── Phase B: DuckDuckGo fallback — fires only if SearXNG found nothing ──
        if not all_people:
            # Try candidates in order; DDG often indexes LinkedIn differently
            for cand_idx, search_name in enumerate(search_names, 1):
                query      = f'site:linkedin.com/in/ "{search_name}"'
                self.log("xray", f"  [DDG fallback {cand_idx}] {query}")
                results    = _search_ddg(query)
                cand_added = _parse_results(results, "DDG")
                time.sleep(0.3)

                if debug is not None:
                    debug["queries"].append({
                        "name":    search_name,
                        "query":   query,
                        "engine":  "DDG",
                        "results": len(results),
                        "added":   cand_added,
                    })

                if cand_added > 0:
                    break

                if len(all_people) >= self.max_per_domain:
                    break

        self.log("xray", f"  [X-Ray] {len(all_people)} raw contacts collected")
        return all_people


# ── Result-title parsing helpers ──────────────────────────────────────────────

def _parse_linkedin_title(title_str: str):
    """
    Parse a SearXNG/Google result title for a LinkedIn profile.

    Common formats:
      "First Last - Job Title - Company | LinkedIn"
      "First Last - Job Title at Company | LinkedIn"
      "First Last – Job Title – Company | LinkedIn"

    Returns (full_name, job_title) or (None, None).
    """
    clean = re.sub(r'\s*\|?\s*LinkedIn\s*$', '', title_str, flags=re.IGNORECASE).strip()
    clean = re.sub(r'\s*\|.*$', '', clean).strip()

    parts = [p.strip() for p in re.split(r'\s+[–\-]\s+', clean) if p.strip()]
    if len(parts) >= 2:
        name = parts[0]
        job  = re.sub(r'\s+at\s+.+$', '', parts[1], flags=re.IGNORECASE).strip()
        return name, job
    if len(parts) == 1:
        return parts[0], ""
    return None, None


# ── Backwards-compatible exports ──────────────────────────────────────────────
# Kept so existing imports from the previous architecture don't break.

XRAY_TITLE_GROUPS: List[str] = []      # title-group iteration is gone

def title_matches(_: str) -> bool:     # unused now — kept as stub
    return True
