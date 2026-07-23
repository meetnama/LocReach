# LocReach — Three-Step Rebuild Design

**Date:** 2026-06-27
**Status:** Approved (pending spec review)
**Scope:** Rebuild the lead-discovery tool as 3 clean steps with a unified domain table and light qualification scoring.

---

## 1. Goal

Rebuild the LocReach lead-discovery tool as **3 focused steps**, matching the Product Bible's vision for an autonomous BD platform:

1. **Find & Qualify Domains** — discover company domains, verify they're real companies, and score their relevance.
2. **Find People** — for each qualified domain, find the relevant team members.
3. **Find Emails** — for each person, discover their verified business email.

This rebuild replaces the current 4-step structure (Domain Discovery → Site Scanner → People Finder → Email Finder) by **merging discovery + qualification into Step 1**, and rewiring Steps 2 & 3 to consume the unified output.

### Out of scope (deferred to a later phase)

The following Product Bible capabilities are explicitly **not** part of this rebuild:

- Personalized research (Step 8)
- AI outreach generation (Step 9)
- Follow-up sequences (Step 10)
- CRM sync (Step 11)
- Email *sending* — Step 3 only **discovers** emails; it does not send them.
- Full ICP scoring (rich criteria model) — this design implements **light scoring** only.

---

## 2. Architecture

The rebuild touches three layers. The **source engine** — the hardened scraping, search, and verification logic in `sources/` — stays completely untouched.

### 2.1 Layers touched

| Layer | Change |
|-------|--------|
| Page layer (`pages/`) | Rewritten into 3 pages + landing |
| DB layer (`db.py`) | Schema unified + auto-migration + new query functions |
| Scoring logic (NEW `scoring.py`) | New capability: transparent, signal-based domain qualification |
| Source engine (`sources/`) | **Untouched** |

### 2.2 New 3-page structure

```
Domain_Discovery.py          ← landing page: pipeline overview + counts
pages/
├── 1_Domains.py             ← NEW: find + qualify + score
├── 2_People.py              ← rewire: reads qualified domains
└── 3_Emails.py              ← relabel only: reads people table
```

### 2.3 Data flow

```
1_Domains.py  ──writes──►  domains (status='qualified', score, tier)
                                │
2_People.py   ──reads────►  domains WHERE status='qualified'
              ──writes──►  people
                                │
3_Emails.py   ──reads────►  people
              ──writes──►  leads
```

---

## 3. Database Schema & Migration

### 3.1 New unified `domains` table

```sql
CREATE TABLE IF NOT EXISTS domains (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    domain             TEXT UNIQUE NOT NULL,

    -- discovery context (from search)
    industry           TEXT DEFAULT '',
    country            TEXT DEFAULT '',
    keyword            TEXT DEFAULT '',
    found_at           TEXT,

    -- qualification output
    company_name       TEXT DEFAULT '',
    linkedin_url       TEXT DEFAULT '',
    status             TEXT DEFAULT 'discovered',   -- discovered|qualified|rejected

    -- NEW: light scoring
    score              INTEGER DEFAULT 0,           -- 0-100
    score_tier         TEXT DEFAULT '',             -- strong|possible|weak
    score_reasons      TEXT DEFAULT '',             -- JSON array of human-readable reason strings

    -- carried over from verified_companies
    company_type       TEXT DEFAULT '',             -- lsp|client|'' (set later in Step 2)
    people_searched_at TEXT,                        -- stamps Step 2 completion
    qualified_at       TEXT
);
```

**One row per domain** (UNIQUE on `domain`). This replaces the current awkward split where `discovered_domains` uses a composite key (domain, industry, country, keyword) and `verified_companies` uses domain-UNIQUE.

**Status lifecycle:**

```
discovered  ──(quality gate + scoring)──►  qualified  ──or──►  rejected
                                              │
                                         (Step 2 reads these)
```

### 3.2 Schema setup (fresh start)

Per the user's direction, **existing `leads.db` data does not need to be preserved.** There is no copy-forward migration. The setup is a clean schema rebuild:

1. **Delete the old `leads.db`** before first launch of the rebuilt app. This is documented in the install/migration notes, not done silently by code.
2. `db_init()` creates the new `domains` table fresh (`CREATE TABLE IF NOT EXISTS`).
3. The old tables (`discovered_domains`, `verified_companies`, `processed_domains`) are simply **not created** by the new `db_init()`. If an old `leads.db` is present, those tables sit inert and unused; the new code never reads them.
4. **`people` and `leads` tables are still created** by `db_init()` (Step 2 and Step 3 write to them) — they simply start empty in a fresh DB.

> **Decision:** trade the complexity of a data migration for a clean schema. Existing discovered data is disposable. The old `leads.db` can be deleted manually; a fresh one is created on first launch.

### 3.3 Join repointing

Because the DB starts fresh, `people` and `leads` are empty at launch. The Step 2 and Step 3 load functions (`db_load_people`, `db_load_people_without_email`, `db_load_leads`) are repointed to JOIN on the new `domains` table instead of `verified_companies`. The join key is `domain`, same as before.

### 3.4 New / changed DB functions

| Old function | New function | Notes |
|--------------|-------------|-------|
| `db_mark_discovered` + `db_insert_verified` | `db_upsert_domain` | Single insert/update |
| `db_load_unscanned` | `db_load_domains_to_qualify` | `WHERE status='discovered'` |
| `db_load_verified` | `db_load_qualified_domains` | `WHERE status='qualified'` |
| `db_load_companies_for_people` | `db_load_qualified_domains` | Same function, Step 2 reuses it |
| `db_mark_domain` (processed_domains) | *(deprecated)* | `status` field on `domains` replaces it |
| `db_get_company_type` / `db_set_company_type` | unchanged signature, repointed to `domains` | |
| `db_mark_company_people_done` | unchanged signature, repointed to `domains` | |
| `db_reset_people_search` | unchanged signature, repointed to `domains` | |
| `db_mark_person_email_done` | unchanged | |
| `db_count_leads` | unchanged | |

---

## 4. Scoring Logic

### 4.1 Philosophy

Lightweight and **explainable**. No LLM call, no paid API. The score is a transparent sum of positive signals found on the company's homepage. Every point traces to a visible reason shown in the UI.

The scoring runs **after** the existing quality check passes. It turns today's binary "verified/not" into a graded signal that lets the user triage at a glance.

### 4.2 Score composition (0–100)

| Category | Signal | Points | How detected |
|----------|--------|--------|--------------|
| **Industry relevance** (max 50) | Localization keyword density | 0–50 | Count of `RELEVANCE_KEYWORDS` matches in homepage text, scaled (≈7 keywords → max 50) |
| **Real-company signals** (max 40) | Has contact page | 20 | Link path contains `/contact`, `/kontakt`, `/impressum`, etc. |
| | Has about/team page | 10 | Link path contains `/about`, `/team`, `/uber-uns`, etc. |
| | Multilingual site | 10 | hreflang tags or language-nav links in page |
| **Reachability** (max 10) | Has LinkedIn page | 10 | LinkedIn URL found (existing `extract_linkedin_url` logic) |

Total maximum = 100.

### 4.3 Tier thresholds

- **≥ 60 → `strong`** (green) — worth pursuing
- **30–59 → `possible`** (orange) — review manually
- **< 30 → `weak`** (gray) — likely skip

A site that **fails** the existing `is_quality_site()` check (parked, empty, <100 chars) scores nothing and goes straight to `status='rejected'` — the scoring never runs.

### 4.4 New module: `scoring.py`

```python
# scoring.py — Company qualification scoring (no API, pure signals)

from config import RELEVANCE_KEYWORDS
from sources.utils import country_from_domain

def score_company(site_data: dict, domain: str, linkedin_url: str = "") -> tuple[int, str, list[str]]:
    """
    Score a qualified company site. Returns (score, tier, reasons).

    site_data : {'markdown': str, 'links': list[str]} from scanner.scrape_site()
    domain    : the company's domain
    linkedin_url : LinkedIn URL already extracted by scanner (saves a re-scan)

    Returns:
      score   : 0-100 integer
      tier    : 'strong' | 'possible' | 'weak'
      reasons : list of human-readable reason strings for the UI
    """
    reasons = []
    score = 0
    text = (site_data or {}).get("markdown", "").lower()
    links = (site_data or {}).get("links", [])

    # 1. Industry relevance — keyword density
    hits = [kw for kw in RELEVANCE_KEYWORDS if kw in text]
    if hits:
        score += min(50, len(hits) * 7)
        reasons.append(f"{len(hits)} localization keywords")

    # 2. Real-company signals
    if _has_contact_page(links):  score += 20; reasons.append("has contact page")
    if _has_about_or_team(links): score += 10; reasons.append("has about/team page")
    if _is_multilingual(site_data): score += 10; reasons.append("multilingual site")

    # 3. Reachability
    if linkedin_url:
        score += 10; reasons.append("has LinkedIn")

    return score, _tier_from_score(score), reasons


def _tier_from_score(score: int) -> str:
    if score >= 60: return "strong"
    if score >= 30: return "possible"
    return "weak"


# ── Signal detectors (each a small pure function) ──────────────────────────────

_CONTACT_PATHS = ("/contact", "/kontakt", "/impressum", "/nous-ecrire",
                  "/contattaci", "/contato", "/contacto", "/contact-us")
_ABOUT_PATHS   = ("/about", "/team", "/uber-uns", "/a-propos", "/chi-siamo",
                  "/sobre", "/our-team", "/company")

def _has_contact_page(links: list) -> bool:
    return any(_path_in_link(href, _CONTACT_PATHS) for href in _iter_hrefs(links))

def _has_about_or_team(links: list) -> bool:
    return any(_path_in_link(href, _ABOUT_PATHS) for href in _iter_hrefs(links))

def _iter_hrefs(links: list):
    """Yield href strings from a links list that may contain bare strings or
    dicts with an 'href' key (both shapes are produced by scanner.scrape_site)."""
    for link in links:
        if isinstance(link, str):
            yield link
        elif isinstance(link, dict):
            yield link.get("href") or ""

def _is_multilingual(site_data: dict) -> bool:
    # hreflang tags or language-switcher links
    md = (site_data or {}).get("markdown", "").lower()
    return ("hreflang" in md) or ("/en/" in md and ("/de/" in md or "/fr/" in md or "/es/" in md))

def _path_in_link(href: str, paths: tuple) -> bool:
    if not href: return False
    h = href.lower()
    return any(p in h for p in paths)
```

### 4.5 Integration with existing scanner

`scanner.py` stays the source of truth for "is this a real site." The new flow in Page 1:

```
scrape_site()          ← existing
    ↓
is_quality_site()      ← existing gate (parked/empty/short → rejected)
    ↓ (passes)
score_company()        ← NEW: assigns score + tier
    ↓
extract_linkedin_url() ← existing (LinkedIn URL passed into score_company first, to avoid double work)
extract_company_name() ← existing
    ↓
db_upsert_domain(status='qualified', score=..., score_tier=..., score_reasons=..., ...)
```

**Rejected domains** (failed quality check OR blocked-list match) still get written to `blocked_domains` as today — that behavior is unchanged. They simply never receive a score.

---

## 5. Page Designs

### 5.1 Landing page — `Domain_Discovery.py`

Stripped down to a read-only overview. No threading, no search logic.

```
┌─ LocReach Lead Discovery ──────────────────────┐
│                                                 │
│  Step 1: Find & Qualify Domains   142 domains   │
│  Step 2: Find People               318 people   │
│  Step 3: Find Emails                87 leads    │
│                                                 │
│  [Go to Step 1 →]                               │
└─────────────────────────────────────────────────┘
```

Pure counts from the DB (`COUNT(*)` on `domains`, `people`, `leads`). Clicking a card uses Streamlit's `st.switch_page()`.

### 5.2 Page 1 — `pages/1_Domains.py` (the big new page)

Fuses current Domain Discovery + Site Scanner into one seamless flow. The search UI from `Domain_Discovery.py` (industry/country/keyword selectors, query bank, tiered engine) is carried over largely intact. The qualification half from `2_Site_Scanner.py` (scrape → quality check → extract LinkedIn/name) runs immediately on each discovered domain before it's stored.

**Layout:**

```
┌─ Sidebar ──────────────────────────────────────┐
│ Industry:  [Translation ▾]                      │
│ Country:   [All ▾]                              │
│ Keywords / queries: [multi-select]              │
│ [▶ Find & Qualify Domains]                      │
│                                                 │
│ ── Results filter ──                            │
│ Tier: [✓ strong ✓ possible ☐ weak]             │
└─────────────────────────────────────────────────┘

┌─ Main ─────────────────────────────────────────┐
│ ┌─ Stat cards ──────────────────────────────┐  │
│ │ Discovered: 142   Qualified: 87  Rejected:55│  │
│ └────────────────────────────────────────────┘  │
│                                                 │
│ ┌─ Live progress log ───────────────────────┐  │
│ │ searching: "translation agency Berlin" …  │  │
│ │ found: berltranslations.de → scraping…    │  │
│ │ ✓ qualified (strong, 78pts: 3 kw, contact │  │
│ │   page, LinkedIn)                         │  │
│ │ ✗ rejected (parked domain)                │  │
│ └────────────────────────────────────────────┘  │
│                                                 │
│ ┌─ Results table ───────────────────────────┐  │
│ │ Domain        Company    Tier  Score  Next │  │
│ │ berltrans.de  Berl Trans  🟢    78    →   │  │
│ │ alpha-lng.com Alpha Lng   🟠    44    →   │  │
│ │ parked.com    —          ⚪    —     —   │  │
│ └────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────┘
```

**Key behaviors:**

- **Search runs once, then auto-qualifies inline.** No separate "now go scan them" step. This is the core UX simplification.
- **Tier badges** are colored. Table sorts by score descending.
- **Per-row "Re-run"** button to re-score a domain.
- **Rejection log** (existing expander pattern) stays — shows every filtered domain + reason + tier.
- Background-thread + queue model carried over from current `Domain_Discovery.py` (proven reliable across prior sessions).

### 5.3 Page 2 — `pages/2_People.py` (rewired)

Engine untouched. Changes are surgical:

1. DB reads repointed: `db_load_companies_for_people` → `db_load_qualified_domains` (reads `domains WHERE status='qualified' AND people_searched_at IS NULL`).
2. `company_type` classification stays — but now reads/writes the `domains` table instead of `verified_companies`.
3. Company-type filter in the sidebar (LSP/Client) keeps working against the same field.
4. "People search" stamp writes `people_searched_at` to the `domains` table.

The People Finder engine (`sources/people/*` — SearXNG X-Ray, LinkedIn scraper, website crawler, title filter, classifier) is **not touched**.

### 5.4 Page 3 — `pages/3_Emails.py` (relabel + join repoint)

The lightest change. The Email Finder engine (`sources/email/*` — website crawl, email-format patterns, SMTP brute force) is **not touched**.

1. Header/copy relabeled ("Step 3" instead of "Step 4").
2. The DB join in `db_load_people_without_email` currently joins `people → verified_companies`. Repoint that join to `domains`. Since the join key is `domain` (stable), this is safe.
3. `db_load_leads` export query similarly repointed.

---

## 6. Full Change Set

| File | Change |
|------|--------|
| `db.py` | + `domains` table, migration, new query functions, repoint joins |
| **NEW** `scoring.py` | `score_company()` + signal detectors |
| `scanner.py` | unchanged — reused as-is by Page 1 |
| `config.py` | no change needed (uses existing `RELEVANCE_KEYWORDS`) |
| `sources/` | **untouched** |
| **NEW** `pages/1_Domains.py` | merge of discovery + qualification + scoring |
| `pages/2_People.py` | rewired DB reads (engine untouched) |
| `pages/3_Emails.py` | relabel + repoint joins (engine untouched) |
| `Domain_Discovery.py` | landing page (stripped to overview) |
| Old `pages/2_Site_Scanner.py`, `3_People_Finder.py`, `4_Email_Finder.py` | removed after new pages verified working |

---

## 7. Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Existing `leads.db` data is lost | By design (user-confirmed). Old DB deleted before first launch; documented in install notes. |
| Scoring heuristics mis-rank some companies | Scoring is advisory only (tier badge + sort); user can re-run per domain. No hard auto-rejection based on score alone. |
| Removing old pages breaks bookmarks | Acceptable — this is a rebuild. Old pages are removed only after new pages are verified working. |
| Source engine regression | Not touched. All `sources/*` modules stay byte-identical. |
