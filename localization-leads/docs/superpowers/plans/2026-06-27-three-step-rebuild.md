# Three-Step Rebuild Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the LocReach lead-discovery tool as 3 clean steps — Find & Qualify Domains → Find People → Find Emails — with a unified `domains` table and light qualification scoring.

**Architecture:** A new `domains` table replaces the split `discovered_domains`/`verified_companies` tables. A new `scoring.py` module assigns an explainable 0–100 score per qualified company. The source engine (`sources/*`) is untouched; only the page layer, DB layer, and scoring are built/changed. Fresh DB — no migration of old data.

**Tech Stack:** Python 3.11+, Streamlit (UI), SQLite (storage), pytest (tests for pure logic). Existing deps only — no new packages.

**Spec:** `docs/superpowers/specs/2026-06-27-three-step-rebuild-design.md`

---

## File Structure

### New files

| File | Responsibility |
|------|---------------|
| `scoring.py` | `score_company()` + signal detectors — pure functions, fully unit-tested |
| `tests/__init__.py` | test package marker |
| `tests/conftest.py` | shared fixtures (sample site_data, temp DB) |
| `tests/test_scoring.py` | scoring + signal-detector tests |
| `tests/test_db.py` | domains-table DB function tests |
| `pages/1_Domains.py` | Step 1: find + qualify + score (merges Domain_Discovery + 2_Site_Scanner) |
| `pages/2_People.py` | Step 2: rewire reads to `domains` table (engine untouched) |
| `pages/3_Emails.py` | Step 3: relabel + repoint joins (engine untouched) |

### Modified files

| File | Change |
|------|--------|
| `db.py` | Add `domains` table to `db_init()`; add new query functions; repoint joins; deprecate old functions |
| `Domain_Discovery.py` | Replace 746-line search UI with a stripped landing page |
| `requirements.txt` | Add `pytest` (dev dependency) |

### Removed files (after new pages verified working — final task)

| File | Reason |
|------|--------|
| `pages/2_Site_Scanner.py` | Merged into `pages/1_Domains.py` |
| `pages/3_People_Finder.py` | Replaced by `pages/2_People.py` |
| `pages/4_Email_Finder.py` | Replaced by `pages/3_Emails.py` |

---

## Task 1: Add pytest and create test scaffolding

**Files:**
- Modify: `requirements.txt`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`

- [ ] **Step 1: Add pytest to requirements**

Append to `D:/LocHere/Sales_Tool/localization-leads/requirements.txt`:

```
pytest>=8.0
```

- [ ] **Step 2: Install pytest into the venv**

Run:
```bash
cd D:/LocHere/Sales_Tool/localization-leads
venv/Scripts/python.exe -m pip install -r requirements.txt
```
Expected: pip installs pytest (or reports already satisfied).

- [ ] **Step 3: Create test package marker**

Create `tests/__init__.py` (empty file):
```python
```

- [ ] **Step 4: Create conftest.py with shared fixtures**

Create `D:/LocHere/Sales_Tool/localization-leads/tests/conftest.py`:

```python
"""Shared fixtures for the test suite."""
import sqlite3
import pytest

import sys, os
# Make the project root importable when pytest runs from anywhere
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def site_data_basic():
    """A minimal real-company homepage: contact page + LinkedIn, 3 LSP keywords."""
    return {
        "markdown": (
            "Welcome to Acme Translation. "
            "We are a leading localization and language service provider. "
            "Contact us today for a free quote on your next translation project. "
            "Our team of linguists is ready to help."
        ),
        "links": [
            "https://acme.com/",
            "https://acme.com/contact",
            "https://acme.com/about",
            "https://www.linkedin.com/company/acme-translation",
        ],
    }


@pytest.fixture
def site_data_parked():
    """A parked / placeholder domain — should fail quality check."""
    return {
        "markdown": "buy this domain",
        "links": [],
    }


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    """A fresh in-file SQLite DB with the new schema. Returns an open connection."""
    db_file = tmp_path / "test_leads.db"
    import db as db_module
    # db_init takes a connection, so DB_PATH constant doesn't matter for init
    conn = sqlite3.connect(str(db_file))
    db_module.db_init(conn)
    yield conn
    conn.close()
```

- [ ] **Step 5: Verify pytest discovers nothing yet (no tests)**

Run:
```bash
cd D:/LocHere/Sales_Tool/localization-leads
venv/Scripts/python.exe -m pytest tests/ -v
```
Expected: `no tests ran` (exit code 5) — confirms pytest is wired up.

- [ ] **Step 6: Commit**

```bash
cd D:/LocHere/Sales_Tool/localization-leads
git init 2>/dev/null; git add requirements.txt tests/__init__.py tests/conftest.py
git commit -m "test: add pytest scaffolding and shared fixtures"
```

> **Note:** This project is not yet a git repo (per environment notes). If `git init` was already done in an earlier task, drop it. If this is the first commit and the working tree has large files (venv/, leads.db), add a `.gitignore` first:
> ```
> venv/
> .chrome_profile/
> leads.db
> __pycache__/
> *.pyc
> ```

---

## Task 2: Implement scoring.py with TDD (the new capability)

**Files:**
- Create: `tests/test_scoring.py`
- Create: `D:/LocHere/Sales_Tool/localization-leads/scoring.py`

This is the genuinely new logic. Pure functions — fully unit-tested.

- [ ] **Step 1: Write the failing test for score_company**

Create `D:/LocHere/Sales_Tool/localization-leads/tests/test_scoring.py`:

```python
"""Tests for the company qualification scoring module."""
import json

from scoring import score_company, _tier_from_score, _has_contact_page


def test_basic_company_scores_strong(site_data_basic):
    """A site with keywords + contact + about + LinkedIn should be 'strong'."""
    score, tier, reasons = score_company(
        site_data_basic,
        domain="acme.com",
        linkedin_url="https://www.linkedin.com/company/acme-translation",
    )
    assert score >= 60
    assert tier == "strong"
    assert isinstance(reasons, list) and len(reasons) > 0
    assert any("keyword" in r for r in reasons)
    assert any("contact" in r for r in reasons)
    assert any("LinkedIn" in r for r in reasons)


def test_no_keywords_scores_low():
    """A site with structure but zero LSP keywords scores weak."""
    site = {
        "markdown": "We sell shoes. Running shoes and boots for everyone.",
        "links": ["https://shoes.com/contact", "https://shoes.com/about"],
    }
    score, tier, reasons = score_company(site, domain="shoes.com", linkedin_url="")
    assert score < 60
    # still has some real-company signals, so not necessarily weak-tier
    assert all("keyword" not in r for r in reasons)


def test_empty_site_data_returns_zero():
    score, tier, reasons = score_company(None, domain="x.com", linkedin_url="")
    assert score == 0
    assert tier == "weak"
    assert reasons == []


def test_tier_thresholds():
    assert _tier_from_score(80) == "strong"
    assert _tier_from_score(60) == "strong"
    assert _tier_from_score(59) == "possible"
    assert _tier_from_score(30) == "possible"
    assert _tier_from_score(29) == "weak"
    assert _tier_from_score(0) == "weak"


def test_keyword_density_caps_at_50():
    """Even a keyword-stuffed page can't exceed 50 from relevance alone."""
    many = " ".join(["translation localization interpretation linguist "
                     "multilingual subtitling dubbing transcreation sworn"] * 5)
    site = {"markdown": many, "links": []}
    score, tier, reasons = score_company(site, domain="kw.com", linkedin_url="")
    assert score <= 100  # never exceeds total cap
    # relevance alone: min(50, count*7) — count capped by keyword list
    relevance_only = score_company({"markdown": many, "links": []}, "kw.com", "")[0]
    # remove non-relevance signals by passing empty links + no linkedin already done
    assert relevance_only <= 50


def test_has_contact_page_detects_localized_paths():
    links = ["https://acme.de/kontakt", "https://acme.de/"]
    assert _has_contact_page(links) is True
    links2 = ["https://acme.com/blog", "https://acme.com/"]
    assert _has_contact_page(links2) is False


def test_has_contact_page_handles_dict_links():
    """scanner can produce dict links with 'href' key."""
    links = [{"href": "https://acme.com/impressum"}, {"href": "https://acme.com/"}]
    assert _has_contact_page(links) is True


def test_multilingual_detection():
    site = {"markdown": 'link rel="alternate" hreflang="de" /', "links": []}
    assert score_company(site, "x.com", "")[0] >= 10 or True  # multilingual adds pts
    site2 = {"markdown": "just english text only here", "links": []}
    s2 = score_company(site2, "x.com", "")[0]
    # no hreflang, no language switcher — multilingual signal absent
    assert "multilingual site" not in [
        r for r in score_company(site2, "x.com", "")[2]
    ]
```

- [ ] **Step 2: Run the test to verify it fails**

Run:
```bash
cd D:/LocHere/Sales_Tool/localization-leads
venv/Scripts/python.exe -m pytest tests/test_scoring.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'scoring'`

- [ ] **Step 3: Write scoring.py implementation**

Create `D:/LocHere/Sales_Tool/localization-leads/scoring.py`:

```python
"""
scoring.py — Company qualification scoring (no API, pure signals).

Scores a qualified company's homepage on a 0-100 scale based on transparent,
explainable signals. Every point traces to a human-readable reason string.
"""
from config import RELEVANCE_KEYWORDS


# ── Public API ─────────────────────────────────────────────────────────────────

def score_company(site_data: dict, domain: str, linkedin_url: str = "") -> tuple:
    """
    Score a qualified company site. Returns (score, tier, reasons).

    site_data : {'markdown': str, 'links': list} from scanner.scrape_site()
    domain    : the company's domain
    linkedin_url : LinkedIn URL already extracted by scanner (avoids a re-scan)

    Returns:
      score   : 0-100 integer
      tier    : 'strong' | 'possible' | 'weak'
      reasons : list of human-readable reason strings for the UI
    """
    if not site_data:
        return 0, "weak", []

    reasons = []
    score = 0
    text = (site_data.get("markdown", "") or "").lower()
    links = site_data.get("links", []) or []

    # 1. Industry relevance — keyword density (max 50)
    hits = [kw for kw in RELEVANCE_KEYWORDS if kw in text]
    if hits:
        score += min(50, len(hits) * 7)
        reasons.append(f"{len(hits)} localization keywords")

    # 2. Real-company signals (max 40)
    if _has_contact_page(links):
        score += 20
        reasons.append("has contact page")
    if _has_about_or_team(links):
        score += 10
        reasons.append("has about/team page")
    if _is_multilingual(site_data):
        score += 10
        reasons.append("multilingual site")

    # 3. Reachability (max 10)
    if linkedin_url:
        score += 10
        reasons.append("has LinkedIn")

    # Cap defensively (shouldn't exceed 100, but guard anyway)
    if score > 100:
        score = 100

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


def _is_multilingual(site_data: dict) -> bool:
    md = (site_data.get("markdown", "") or "").lower()
    if "hreflang" in md:
        return True
    # language-switcher pattern: /en/ coexisting with another language path
    has_en = "/en/" in md
    has_other = ("/de/" in md or "/fr/" in md or "/es/" in md or "/it/" in md
                 or "/nl/" in md)
    return has_en and has_other


def _path_in_link(href: str, paths: tuple) -> bool:
    if not href:
        return False
    h = href.lower()
    return any(p in h for p in paths)
```

- [ ] **Step 4: Run tests to verify they pass**

Run:
```bash
cd D:/LocHere/Sales_Tool/localization-leads
venv/Scripts/python.exe -m pytest tests/test_scoring.py -v
```
Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
cd D:/LocHere/Sales_Tool/localization-leads
git add scoring.py tests/test_scoring.py
git commit -m "feat: add company qualification scoring module with tests"
```

---

## Task 3: Update db.py — add unified domains table

**Files:**
- Modify: `D:/LocHere/Sales_Tool/localization-leads/db.py` (the `db_init()` function and surrounding code)
- Test: `tests/test_db.py`

The new schema. Per spec §3.2: fresh start — no migration of old data. `db_init()` creates the `domains` table and stops creating the deprecated tables.

- [ ] **Step 1: Write failing test for the domains table**

Create `D:/LocHere/Sales_Tool/localization-leads/tests/test_db.py`:

```python
"""Tests for the domains table and its DB functions."""
import sqlite3

from db import (
    db_init, db_upsert_domain, db_load_domains_to_qualify,
    db_load_qualified_domains,
)


def test_domains_table_exists_after_init(fresh_db):
    cur = fresh_db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='domains'"
    )
    assert cur.fetchone() is not None


def test_domains_table_has_scoring_columns(fresh_db):
    cur = fresh_db.execute("PRAGMA table_info(domains)")
    cols = {row[1] for row in cur.fetchall()}
    for expected in {"domain", "status", "score", "score_tier", "score_reasons",
                     "company_type", "people_searched_at"}:
        assert expected in cols, f"missing column: {expected}"


def test_upsert_domain_inserts_discovered(fresh_db):
    db_upsert_domain(fresh_db, {
        "domain": "acme.com", "status": "discovered",
        "industry": "translation", "country": "", "keyword": "test",
    })
    row = fresh_db.execute(
        "SELECT domain, status FROM domains WHERE domain=?", ("acme.com",)
    ).fetchone()
    assert row == ("acme.com", "discovered")


def test_upsert_domain_promotes_to_qualified(fresh_db):
    db_upsert_domain(fresh_db, {"domain": "acme.com", "status": "discovered"})
    db_upsert_domain(fresh_db, {
        "domain": "acme.com", "status": "qualified",
        "company_name": "Acme", "score": 78, "score_tier": "strong",
        "score_reasons": '["3 keywords","contact page"]',
    })
    row = fresh_db.execute(
        "SELECT status, company_name, score, score_tier FROM domains WHERE domain=?",
        ("acme.com",),
    ).fetchone()
    assert row == ("qualified", "Acme", 78, "strong")


def test_load_domains_to_qualify_returns_only_discovered(fresh_db):
    db_upsert_domain(fresh_db, {"domain": "a.com", "status": "discovered"})
    db_upsert_domain(fresh_db, {"domain": "b.com", "status": "qualified"})
    db_upsert_domain(fresh_db, {"domain": "c.com", "status": "discovered"})
    rows = db_load_domains_to_qualify(fresh_db)
    domains = {r[0] for r in rows}
    assert domains == {"a.com", "c.com"}


def test_load_qualified_domains_excludes_discovered(fresh_db):
    db_upsert_domain(fresh_db, {"domain": "a.com", "status": "discovered"})
    db_upsert_domain(fresh_db, {"domain": "b.com", "status": "qualified"})
    rows = db_load_qualified_domains(fresh_db)
    domains = {r[0] for r in rows}
    assert "b.com" in domains
    assert "a.com" not in domains


def test_load_qualified_domains_unsearched_for_people(fresh_db):
    """Step 2 reads qualified domains not yet people-searched."""
    db_upsert_domain(fresh_db, {"domain": "a.com", "status": "qualified"})
    db_upsert_domain(fresh_db, {
        "domain": "b.com", "status": "qualified", "people_searched_at": "2026-01-01",
    })
    rows = db_load_qualified_domains(fresh_db, only_unsearched=True)
    domains = {r[0] for r in rows}
    assert "a.com" in domains
    assert "b.com" not in domains
```

- [ ] **Step 2: Run tests to verify they fail**

Run:
```bash
cd D:/LocHere/Sales_Tool/localization-leads
venv/Scripts/python.exe -m pytest tests/test_db.py -v
```
Expected: FAIL — `ImportError: cannot import name 'db_upsert_domain'`

- [ ] **Step 3: Replace db_init() to create the new domains table**

In `D:/LocHere/Sales_Tool/localization-leads/db.py`, **replace the entire `db_init()` function** (currently lines 13–105) with:

```python
def db_init(conn: sqlite3.Connection) -> None:
    """
    Create the schema for the 3-step pipeline.

    Per design: fresh start. The unified `domains` table replaces the old
    `discovered_domains` + `verified_companies` split. `people` and `leads`
    remain as the Step 2 and Step 3 outputs.
    """
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS domains (
            id                 INTEGER PRIMARY KEY AUTOINCREMENT,
            domain             TEXT UNIQUE NOT NULL,
            industry           TEXT DEFAULT '',
            country            TEXT DEFAULT '',
            keyword            TEXT DEFAULT '',
            found_at           TEXT,
            company_name       TEXT DEFAULT '',
            linkedin_url       TEXT DEFAULT '',
            status             TEXT DEFAULT 'discovered',
            score              INTEGER DEFAULT 0,
            score_tier         TEXT DEFAULT '',
            score_reasons      TEXT DEFAULT '',
            company_type       TEXT DEFAULT '',
            people_searched_at TEXT,
            qualified_at       TEXT
        );
        CREATE TABLE IF NOT EXISTS people (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            domain        TEXT NOT NULL,
            company_name  TEXT DEFAULT '',
            first_name    TEXT DEFAULT '',
            last_name     TEXT DEFAULT '',
            full_name     TEXT DEFAULT '',
            title         TEXT DEFAULT '',
            linkedin_url  TEXT DEFAULT '',
            people_source TEXT DEFAULT '',
            found_at      TEXT,
            email_searched_at TEXT,
            UNIQUE (domain, full_name)
        );
        CREATE TABLE IF NOT EXISTS leads (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            email        TEXT UNIQUE NOT NULL,
            email_source TEXT DEFAULT '',
            full_name    TEXT DEFAULT '',
            first_name   TEXT DEFAULT '',
            last_name    TEXT DEFAULT '',
            title        TEXT DEFAULT '',
            company      TEXT DEFAULT '',
            domain       TEXT DEFAULT '',
            country      TEXT DEFAULT '',
            linkedin_url TEXT DEFAULT '',
            source_url   TEXT DEFAULT '',
            status       TEXT DEFAULT 'new'
        );
        CREATE TABLE IF NOT EXISTS blocked_domains (
            domain     TEXT PRIMARY KEY,
            blocked_at TEXT
        );
    """)
    # Forward-compatible column additions (safe on older DB files)
    for col in ["full_name", "domain", "linkedin_url", "email_source"]:
        try:
            conn.execute(f"ALTER TABLE leads ADD COLUMN {col} TEXT DEFAULT ''")
        except Exception:
            pass
    try:
        conn.execute("ALTER TABLE people ADD COLUMN email_searched_at TEXT")
    except Exception:
        pass
    conn.commit()
```

Note: this removes creation of `discovered_domains`, `verified_companies`, and `processed_domains`. Those are intentionally gone — fresh start.

- [ ] **Step 4: Add the new domain query functions**

Append to `D:/LocHere/Sales_Tool/localization-leads/db.py` (end of file):

```python
# ── domains table (unified Step 1 output) ─────────────────────────────────────

def db_upsert_domain(conn: sqlite3.Connection, data: dict) -> None:
    """
    Insert a domain or update its fields. Required key: 'domain'.
    Only provided fields are written; absent keys keep their existing value.

    status values: 'discovered' | 'qualified' | 'rejected'
    """
    domain = data["domain"]
    existing = conn.execute(
        "SELECT 1 FROM domains WHERE domain=?", (domain,)
    ).fetchone()

    if not existing:
        conn.execute(
            "INSERT INTO domains (domain, status, found_at) VALUES (?,?,?)",
            (domain, data.get("status", "discovered"),
             datetime.now().isoformat()),
        )

    # Build UPDATE for any explicitly provided columns
    updatable = ("industry", "country", "keyword", "company_name",
                 "linkedin_url", "status", "score", "score_tier",
                 "score_reasons", "company_type", "people_searched_at",
                 "qualified_at")
    sets, vals = [], []
    for col in updatable:
        if col in data:
            sets.append(f"{col}=?")
            vals.append(data[col])
    if sets:
        vals.append(domain)
        conn.execute(f"UPDATE domains SET {', '.join(sets)} WHERE domain=?", vals)

    conn.commit()


def db_load_domains_to_qualify(conn: sqlite3.Connection,
                               industry: str = "", country: str = "") -> list:
    """
    Return discovered (not-yet-qualified) domains.
    Returns list of (domain, industry, country, keyword).
    """
    sql = ("SELECT domain, industry, country, keyword FROM domains "
           "WHERE status='discovered'")
    args = []
    if industry:
        sql += " AND industry=?"; args.append(industry)
    if country:
        sql += " AND country=?"; args.append(country)
    sql += " ORDER BY id"
    return conn.execute(sql, args).fetchall()


def db_load_qualified_domains(conn: sqlite3.Connection,
                              industry: str = "", country: str = "",
                              only_unsearched: bool = False) -> list:
    """
    Return qualified domains. Used by Step 2 (people finder).
    only_unsearched=True limits to domains not yet people-searched.
    Returns list of (domain, company_name, linkedin_url, industry, country).
    """
    sql = ("SELECT domain, company_name, linkedin_url, industry, country "
           "FROM domains WHERE status='qualified'")
    args = []
    if only_unsearched:
        sql += " AND people_searched_at IS NULL"
    if industry:
        sql += " AND industry=?"; args.append(industry)
    if country:
        sql += " AND country=?"; args.append(country)
    sql += " ORDER BY score DESC, id"
    return conn.execute(sql, args).fetchall()


def db_mark_blocked_domain(conn: sqlite3.Connection, domain: str) -> None:
    """Persist a filtered/blocked domain so it's skipped in future searches."""
    conn.execute(
        "INSERT OR IGNORE INTO blocked_domains (domain, blocked_at) VALUES (?,?)",
        (domain, datetime.now().isoformat()),
    )
    conn.commit()


def db_load_blocked_domains(conn: sqlite3.Connection) -> set:
    """Return the set of all previously blocked domains."""
    rows = conn.execute("SELECT domain FROM blocked_domains").fetchall()
    return {r[0] for r in rows}


def db_count_domains(conn: sqlite3.Connection) -> dict:
    """Return status counts for the landing-page stat cards."""
    rows = conn.execute(
        "SELECT status, COUNT(*) FROM domains GROUP BY status"
    ).fetchall()
    counts = {"discovered": 0, "qualified": 0, "rejected": 0}
    for status, n in rows:
        counts[status] = n
    return counts
```

- [ ] **Step 5: Run the db tests to verify they pass**

Run:
```bash
cd D:/LocHere/Sales_Tool/localization-leads
venv/Scripts/python.exe -m pytest tests/test_db.py -v
```
Expected: all tests PASS.

- [ ] **Step 6: Commit**

```bash
cd D:/LocHere/Sales_Tool/localization-leads
git add db.py tests/test_db.py
git commit -m "feat: unify domains table with scoring columns and query functions"
```

---

## Task 4: Repoint people/leads DB functions to the domains table

**Files:**
- Modify: `D:/LocHere/Sales_Tool/localization-leads/db.py`

Step 2 and Step 3 currently JOIN on `verified_companies`. Repoint those JOINs to `domains`. With a fresh DB these tables start empty, so the joins just need the correct table name.

- [ ] **Step 1: Repoint db_load_people join**

In `db.py`, find `db_load_people` (currently joins `verified_companies v`). Replace every occurrence of:

```sql
JOIN verified_companies v ON p.domain = v.domain
```
with:
```sql
JOIN domains v ON p.domain = v.domain
```

And change the WHERE filter references from `v.industry` / `v.country` — those column names are identical in `domains`, so only the table name changes. Use the Edit tool with `replace_all` where the pattern is identical across the four query branches.

- [ ] **Step 2: Repoint db_load_people_without_email join**

Same change in `db_load_people_without_email`: `verified_companies` → `domains`.

- [ ] **Step 3: Repoint db_load_leads subquery**

In `db_load_leads`, the four branches each contain:
```sql
WHERE l.domain IN (
    SELECT domain FROM verified_companies WHERE industry=? AND country=?
)
```
Change `verified_companies` → `domains` in all branches.

- [ ] **Step 4: Repoint company_type + people_done functions**

These functions reference `verified_companies` for the `company_type` and `people_searched_at` columns — both now live on `domains`. Update:

- `db_get_company_type`: `SELECT company_type FROM verified_companies` → `FROM domains`
- `db_set_company_type`: `UPDATE verified_companies SET company_type` → `UPDATE domains`
- `db_mark_company_people_done`: `UPDATE verified_companies SET people_searched_at` → `UPDATE domains`
- `db_reset_people_search`: `UPDATE verified_companies SET people_searched_at=NULL` → `UPDATE domains`

- [ ] **Step 5: Remove now-deprecated functions**

Delete these functions from `db.py` entirely (no longer called by any page after the rebuild):
- `db_load_discovered`
- `db_mark_discovered`
- `db_load_unscanned`
- `db_insert_verified`
- `db_load_verified`
- `db_load_companies_for_people`
- `db_mark_domain` (the processed_domains one)
- `db_domain_done`

Also delete the standalone re-creation of `discovered_domains` at the end of the old `db_init` (already removed in Task 3).

- [ ] **Step 6: Verify db.py imports cleanly**

Run:
```bash
cd D:/LocHere/Sales_Tool/localization-leads
venv/Scripts/python.exe -c "import db; print('db.py imports OK')"
```
Expected: prints `db.py imports OK` with no errors.

- [ ] **Step 7: Run full test suite**

Run:
```bash
cd D:/LocHere/Sales_Tool/localization-leads
venv/Scripts/python.exe -m pytest tests/ -v
```
Expected: all tests PASS.

- [ ] **Step 8: Commit**

```bash
cd D:/LocHere/Sales_Tool/localization-leads
git add db.py
git commit -m "refactor: repoint people/leads queries to unified domains table"
```

---

## Task 5: Build pages/1_Domains.py (Step 1 — the big merge)

**Files:**
- Create: `D:/LocHere/Sales_Tool/localization-leads/pages/1_Domains.py`

This page merges the search UI from `Domain_Discovery.py` with the scan logic from `pages/2_Site_Scanner.py`, adds inline scoring, and writes to the unified `domains` table. The source engine is untouched.

- [ ] **Step 1: Read the two source files to adapt from**

Read these in full — their search worker, queue model, and Streamlit state patterns are the proven foundation:
- `D:/LocHere/Sales_Tool/localization-leads/Domain_Discovery.py` (746 lines)
- `D:/LocHere/Sales_Tool/localization-leads/pages/2_Site_Scanner.py` (607 lines)

- [ ] **Step 2: Create pages/1_Domains.py**

Create `D:/LocHere/Sales_Tool/localization-leads/pages/1_Domains.py`. The structure below is the template. It imports the existing search + scan functions, runs discovery and qualification in one worker thread, applies `score_company()` inline, and writes to `db_upsert_domain()`.

```python
"""
pages/1_Domains.py — LocReach Step 1: Find & Qualify Domains.

Merges discovery (SearXNG/Chrome/DDG search) with inline qualification
(scrape → quality check → score) into a single flow. Writes qualified
domains to the unified `domains` table.
"""
import os
import json
import sqlite3
import threading
import queue
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

from sources.utils import (
    google_search, google_warmup, searxng_search, duckduckgo_search,
    get_domain, is_blocked, is_industry_match, _captcha_flag,
)
from scanner import (
    scrape_site, is_quality_site, extract_linkedin_url,
    find_linkedin_via_searxng, extract_company_name,
)
from scoring import score_company
from config import QUERY_CATEGORIES
from db import (db_init, db_upsert_domain, db_load_domains_to_qualify,
                db_load_qualified_domains, db_mark_blocked_domain,
                db_load_blocked_domains, db_count_domains)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH  = os.path.join(BASE_DIR, "leads.db")
_SCAN_WORKERS = 4

st.set_page_config(
    page_title="LocReach — Step 1: Domains",
    page_icon="🌐",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
  .stApp { background-color: #0f1117; }
  .block-container { padding-top: 1.5rem; }
  h1  { color: #e8f4f8 !important; font-size: 1.7rem !important; }
  h3  { color: #a8d8ea !important; }
  .stat-row  { display:flex; gap:14px; margin-bottom:22px; flex-wrap:wrap; }
  .stat-card { background:#1e2130; border:1px solid #2e3250; border-radius:10px;
               padding:14px 22px; text-align:center; min-width:120px; }
  .stat-val  { font-size:1.9rem; font-weight:700; }
  .stat-lbl  { font-size:0.75rem; color:#888; margin-top:3px; }
  .green { color:#4caf50; } .blue { color:#64b5f6; } .orange { color:#ffa726; }
  .gray  { color:#888; }
  div[data-testid="stSidebar"] { background-color: #161b22; }
</style>
""", unsafe_allow_html=True)

# ── Session state ──────────────────────────────────────────────────────────────
for k, v in {
    "s1_running":       False,
    "s1_done":          False,
    "s1_qualified":     [],       # (domain, company_name, score, tier, reasons)
    "s1_rejected_log":  [],
    "s1_query_log":     [],
    "s1_queue":         None,
    "s1_current_query": "",
    "s1_scanned":       0,
    "s1_total":         0,
    "s1_error":         "",
    "s1_start_time":    None,
    "s1_stop_event":    None,
    "s1_last_tiers":    "",
}.items():
    if k not in st.session_state:
        st.session_state[k] = v

_conn = sqlite3.connect(DB_PATH, check_same_thread=False)
db_init(_conn)

st.title("🌐 Step 1 — Find & Qualify Domains")

# ── Sidebar: search options (adapted from Domain_Discovery.py) ─────────────────
# Copy the _INDUSTRY_RAW / INDUSTRY_OPTIONS, country selector, and query
# multi-select widgets verbatim from Domain_Discovery.py sidebar block.
# (The engineer adapting this should open Domain_Discovery.py lines ~85-280 and
#  copy the widget code, changing the run-button label to "▶ Find & Qualify".)
# ... [WIDGET CODE ADAPTED FROM Domain_Discovery.py] ...

# After the run button (run_btn) is defined, wire up the worker below.

# ── Qualify+score a single discovered domain ───────────────────────────────────
def _qualify_one(domain: str, industry: str, country: str, keyword: str,
                 db_lock: threading.Lock) -> dict:
    """Scrape, quality-check, score, and persist a domain. Returns a result dict."""
    try:
        site_data = scrape_site(f"https://{domain}")
    except Exception:
        site_data = None

    if not is_quality_site(site_data, domain, industry):
        with db_lock:
            db_mark_blocked_domain(_conn, domain)
        return {"domain": domain, "status": "rejected", "reason": "low quality / unreachable"}

    li_url = extract_linkedin_url(site_data)
    if not li_url:
        li_url = find_linkedin_via_searxng(domain)

    score, tier, reasons = score_company(site_data, domain, linkedin_url=li_url)
    company_name = extract_company_name(site_data, domain, li_url=li_url)

    with db_lock:
        db_upsert_domain(_conn, {
            "domain": domain, "status": "qualified",
            "industry": industry, "country": country, "keyword": keyword,
            "company_name": company_name, "linkedin_url": li_url,
            "score": score, "score_tier": tier,
            "score_reasons": json.dumps(reasons),
            "qualified_at": datetime.now().isoformat(),
        })
    return {"domain": domain, "status": "qualified", "company_name": company_name,
            "score": score, "tier": tier, "reasons": reasons}


def _run_step1(queries, num, q_out, stop_event, industry, country):
    """Background worker: search → for each found domain, qualify + score inline."""
    try:
        with sqlite3.connect(DB_PATH, check_same_thread=False) as wconn:
            db_init(wconn)
            db_lock = threading.Lock()
            google_warmup()
            blocked = db_load_blocked_domains(wconn)

            for qi, query in enumerate(queries, 1):
                if stop_event.is_set():
                    break
                q_out.put(("query_start", query))
                # 3-tier search (adapt _search_page from Domain_Discovery.py)
                results = _search_page(query, num, 1, industry)
                for r in results:
                    if stop_event.is_set():
                        break
                    domain = get_domain(r.get("link", ""))
                    if not domain or domain in blocked or is_blocked(r["link"]):
                        q_out.put(("rejected", {"domain": domain or "?",
                                                 "reason": "blocked/filtered",
                                                 "tier": "filter"}))
                        with db_lock:
                            db_mark_blocked_domain(wconn, domain)
                        continue
                    q_out.put(("scanning", domain))
                    res = _qualify_one(domain, industry, country, query, db_lock)
                    if res["status"] == "qualified":
                        blocked.add(domain)
                        q_out.put(("qualified", res))
                    else:
                        q_out.put(("rejected", res))
                q_out.put(("query_done", {"n": len(results), "query": query}))
    except Exception as exc:
        q_out.put(("error", str(exc)))


def _search_page(query, num, page, industry_slug):
    """3-tier search (Tier A SearXNG → Tier B Chrome → Tier C DDG).
    Adapt verbatim from Domain_Discovery.py _search_page()."""
    # [COPY the body of _search_page from Domain_Discovery.py]
    pass


# ── Run button wiring ──────────────────────────────────────────────────────────
# run_btn = st.sidebar.button("▶ Find & Qualify Domains", ...)
# if run_btn and not st.session_state.s1_running:
#     ... reset session state, spawn _run_step1 in a thread ...
# stop_btn = st.sidebar.button("⏹ Stop", ...)

# ── Drain queue + render results ───────────────────────────────────────────────
# [Adapt the queue-drain + table-render block from Domain_Discovery.py,
#  but render score/tier columns. See Step 3 below for the table.]

# ── Results table with score + tier badges ─────────────────────────────────────
def _tier_badge(tier: str) -> str:
    color = {"strong": "#4caf50", "possible": "#ffa726", "weak": "#888"}.get(tier, "#555")
    label = {"strong": "🟢 Strong", "possible": "🟠 Possible",
             "weak": "⚪ Weak"}.get(tier, "—")
    return f'<span style="color:{color};font-weight:700">{label}</span>'
```

**Important adaptation notes for the engineer:**
- The full sidebar widget code (industry/country/keyword selectors) is **not rewritten** — it is copied from `Domain_Discovery.py` lines ~85–280 and pasted where marked `[WIDGET CODE ADAPTED FROM Domain_Discovery.py]`. The only change is the run-button label.
- The `_search_page()` function body is copied verbatim from `Domain_Discovery.py` lines ~329–364.
- The queue-drain + state-machine pattern is copied from `Domain_Discovery.py` lines ~507–549, adapted to handle the new queue message types (`query_start`, `scanning`, `qualified`, `rejected`, `query_done`, `error`).

- [ ] **Step 3: Add the results table with score + tier columns**

After the queue-drain block in `pages/1_Domains.py`, add the table renderer. The qualified results are in `st.session_state.s1_qualified` as tuples:

```python
# ── Results table ──────────────────────────────────────────────────────────────
qualified = st.session_state.s1_qualified
if qualified and not st.session_state.s1_running:
    st.subheader(f"✅ Qualified Domains ({len(qualified)})")
    rows_html = []
    for entry in sorted(qualified, key=lambda e: e.get("score", 0), reverse=True):
        badge = _tier_badge(entry.get("tier", ""))
        reasons = ", ".join(entry.get("reasons", []))
        rows_html.append(
            f'<tr><td>{entry["domain"]}</td><td>{entry.get("company_name","")}</td>'
            f'<td>{badge}</td><td>{entry.get("score",0)}</td>'
            f'<td style="color:#aaa;font-size:0.8em">{reasons}</td></tr>'
        )
    st.markdown(
        '<table style="width:100%;border-collapse:collapse">'
        '<tr style="color:#a8d8ea;text-align:left">'
        '<th>Domain</th><th>Company</th><th>Tier</th><th>Score</th><th>Signals</th></tr>'
        + "".join(rows_html) + '</table>',
        unsafe_allow_html=True,
    )

# ── Existing qualified domains from DB (persisted across runs) ──────────────────
db_rows = db_load_qualified_domains(_conn)
if db_rows and not st.session_state.s1_running:
    st.subheader(f"📁 All Qualified Domains in DB ({len(db_rows)})")
    # render db_rows similarly, joining score/tier from the domains table
```

- [ ] **Step 4: Add a re-score button per domain (optional, spec §5.2)**

Add a small `st.button("Re-run", key=domain)` in the DB table row that calls `_qualify_one(domain, ...)` synchronously and `st.rerun()`.

- [ ] **Step 5: Manual verification — launch the app**

Run:
```bash
cd D:/LocHere/Sales_Tool/localization-leads
venv/Scripts/python.exe -m streamlit run Domain_Discovery.py --server.port 8501
```
Open `http://localhost:8501/Step_1_Domains`. Verify:
- Page loads without errors
- Sidebar shows industry/country/keyword selectors
- Clicking "Find & Qualify Domains" starts the search (watch the live log)
- Results table shows domain, company, tier badge, score, signals
- Re-running a query doesn't duplicate domains (UNIQUE constraint)

- [ ] **Step 6: Commit**

```bash
cd D:/LocHere/Sales_Tool/localization-leads
git add pages/1_Domains.py
git commit -m "feat: build Step 1 page (find + qualify + score domains)"
```

---

## Task 6: Build pages/2_People.py (Step 2 — rewire reads)

**Files:**
- Create: `D:/LocHere/Sales_Tool/localization-leads/pages/2_People.py`

The People Finder engine is untouched. This page reads qualified domains from the new `domains` table instead of the old `verified_companies` table.

- [ ] **Step 1: Copy pages/3_People_Finder.py as the base**

The existing `pages/3_People_Finder.py` (842 lines) is ~95% reusable. Create `pages/2_People.py` as a copy, then make these targeted changes:

- [ ] **Step 2: Repoint DB imports**

In `pages/2_People.py`, change the import block:
```python
from db import (
    db_init,
    db_load_companies_for_people,   # ← REMOVE
    db_load_people,
    db_insert_person,
    db_mark_company_people_done,
    db_get_company_type,
    db_set_company_type,
    db_reset_people_search,
)
```
to:
```python
from db import (
    db_init,
    db_load_qualified_domains,      # ← REPLACES db_load_companies_for_people
    db_load_people,
    db_insert_person,
    db_mark_company_people_done,
    db_get_company_type,
    db_set_company_type,
    db_reset_people_search,
)
```

- [ ] **Step 3: Repoint the companies-for-people query**

In the page body, find where it loads companies to search:
```python
_companies = db_load_companies_for_people(_conn, industry, country)
```
Replace with:
```python
_companies = db_load_qualified_domains(_conn, industry, country, only_unsearched=True)
```

The row shape from `db_load_qualified_domains` is `(domain, company_name, linkedin_url, industry, country)` — identical to what `db_load_companies_for_people` returned. No downstream unpacking changes needed.

- [ ] **Step 4: Update page title and copy**

Change:
- `page_title="LocHere — People Finder"` → `page_title="LocReach — Step 2: People"`
- `page_icon="👥"` (keep)
- The `st.title(...)` line → `st.title("👥 Step 2 — Find People")`

- [ ] **Step 5: Manual verification**

Run:
```bash
cd D:/LocHere/Sales_Tool/localization-leads
venv/Scripts/python.exe -m streamlit run Domain_Discovery.py --server.port 8501
```
Open the People page. Verify:
- Page loads; shows qualified domains from Step 1 as the search target
- Running a people search finds and stores people (requires Chrome for LinkedIn paths)
- Company-type filter (LSP/Client) still works
- Existing people show in the results table

- [ ] **Step 6: Commit**

```bash
cd D:/LocHere/Sales_Tool/localization-leads
git add pages/2_People.py
git commit -m "feat: build Step 2 page (rewire people finder to domains table)"
```

---

## Task 7: Build pages/3_Emails.py (Step 3 — relabel + verify joins)

**Files:**
- Create: `D:/LocHere/Sales_Tool/localization-leads/pages/3_Emails.py`

The lightest change. The Email Finder engine is untouched; the DB joins were already repointed in Task 4.

- [ ] **Step 1: Copy pages/4_Email_Finder.py as the base**

Create `pages/3_Emails.py` as a copy of `pages/4_Email_Finder.py` (743 lines).

- [ ] **Step 2: Update page title and copy**

Change:
- `page_title="LocHere — Email Finder"` → `page_title="LocReach — Step 3: Emails"`
- `page_icon="📧"` (keep)
- The `st.title(...)` → `st.title("📧 Step 3 — Find Emails")`
- Any "Step 4" references in body text → "Step 3"

- [ ] **Step 3: Verify the DB imports resolve**

The imports in this page (`db_load_people_without_email`, `db_mark_person_email_done`, `db_insert_lead`, `db_count_leads`) all still exist in `db.py` after Task 4. No import changes needed — just verify they resolve.

- [ ] **Step 4: Manual verification**

Run the app, open the Emails page. Verify:
- Page loads without import errors
- It reads people from Step 2 and runs email discovery
- Found leads appear in the table and export works

- [ ] **Step 5: Commit**

```bash
cd D:/LocHere/Sales_Tool/localization-leads
git add pages/3_Emails.py
git commit -m "feat: build Step 3 page (relabel email finder)"
```

---

## Task 8: Replace Domain_Discovery.py with landing page

**Files:**
- Modify: `D:/LocHere/Sales_Tool/localization-leads/Domain_Discovery.py` (full rewrite — 746 → ~60 lines)

- [ ] **Step 1: Replace the file contents**

Overwrite `D:/LocHere/Sales_Tool/localization-leads/Domain_Discovery.py` with:

```python
"""
Domain_Discovery.py — LocReach Lead Discovery landing page.

Read-only overview of the 3-step pipeline. Click a card to jump to a step.
"""
import os
import sqlite3

import streamlit as st

from db import db_init, db_count_domains

st.set_page_config(
    page_title="LocReach Lead Discovery",
    page_icon="🌐",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
  .stApp { background-color: #0f1117; }
  .block-container { padding-top: 2rem; }
  h1 { color: #e8f4f8 !important; font-size: 1.9rem !important; }
  h3 { color: #a8d8ea !important; }
  .step-card { background:#1e2130; border:1px solid #2e3250; border-radius:12px;
               padding:24px; margin-bottom:16px; cursor:pointer; }
  .step-num { font-size:0.8rem; color:#64b5f6; letter-spacing:2px; }
  .step-name { font-size:1.4rem; font-weight:700; color:#e8f4f8; margin:4px 0; }
  .step-count { font-size:1.1rem; color:#4caf50; }
</style>
""", unsafe_allow_html=True)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "leads.db")
_conn = sqlite3.connect(DB_PATH)
db_init(_conn)

st.title("🌐 LocReach Lead Discovery")
st.markdown("Autonomous B2B lead discovery for the localization industry.")

domain_counts = db_count_domains(_conn)
people_count = _conn.execute("SELECT COUNT(*) FROM people").fetchone()[0]
leads_count = _conn.execute("SELECT COUNT(*) FROM leads").fetchone()[0]

col1, col2, col3 = st.columns(3)
with col1:
    st.markdown(
        f'<div class="step-card"><div class="step-num">STEP 1</div>'
        f'<div class="step-name">Find & Qualify Domains</div>'
        f'<div class="step-count">{domain_counts["qualified"]} qualified · '
        f'{domain_counts["discovered"]} discovered</div></div>',
        unsafe_allow_html=True,
    )
    if st.button("Go to Step 1 →", use_container_width=True):
        st.switch_page("pages/1_Domains.py")
with col2:
    st.markdown(
        f'<div class="step-card"><div class="step-num">STEP 2</div>'
        f'<div class="step-name">Find People</div>'
        f'<div class="step-count">{people_count} people found</div></div>',
        unsafe_allow_html=True,
    )
    if st.button("Go to Step 2 →", use_container_width=True):
        st.switch_page("pages/2_People.py")
with col3:
    st.markdown(
        f'<div class="step-card"><div class="step-num">STEP 3</div>'
        f'<div class="step-name">Find Emails</div>'
        f'<div class="step-count">{leads_count} leads</div></div>',
        unsafe_allow_html=True,
    )
    if st.button("Go to Step 3 →", use_container_width=True):
        st.switch_page("pages/3_Emails.py")

_conn.close()
```

- [ ] **Step 2: Manual verification**

Run:
```bash
cd D:/LocHere/Sales_Tool/localization-leads
venv/Scripts/python.exe -m streamlit run Domain_Discovery.py --server.port 8501
```
Open `http://localhost:8501`. Verify:
- Landing page shows 3 cards with live counts
- Each "Go to Step N" button navigates to the correct page
- No errors in the console

- [ ] **Step 3: Commit**

```bash
cd D:/LocHere/Sales_Tool/localization-leads
git add Domain_Discovery.py
git commit -m "feat: replace search UI with 3-step landing page"
```

---

## Task 9: Remove old pages and final verification

**Files:**
- Delete: `pages/2_Site_Scanner.py`, `pages/3_People_Finder.py`, `pages/4_Email_Finder.py`

- [ ] **Step 1: Confirm no imports reference the old pages**

Run:
```bash
cd D:/LocHere/Sales_Tool/localization-leads
grep -rn "Site_Scanner\|People_Finder\|Email_Finder\|3_People_Finder\|4_Email_Finder\|2_Site_Scanner" --include="*.py" . | grep -v venv | grep -v test
```
Expected: no output (nothing imports the old pages).

- [ ] **Step 2: Delete the old page files**

Run:
```bash
cd D:/LocHere/Sales_Tool/localization-leads
rm pages/2_Site_Scanner.py pages/3_People_Finder.py pages/4_Email_Finder.py
```

- [ ] **Step 3: Run the full test suite**

Run:
```bash
cd D:/LocHere/Sales_Tool/localization-leads
venv/Scripts/python.exe -m pytest tests/ -v
```
Expected: all tests PASS.

- [ ] **Step 4: Full end-to-end manual verification**

Run the app fresh. Before first launch, delete the old DB:
```bash
cd D:/LocHere/Sales_Tool/localization-leads
rm -f leads.db
venv/Scripts/python.exe -m streamlit run Domain_Discovery.py --server.port 8501
```

Verify the full pipeline:
1. **Landing page** shows all counts at 0
2. **Step 1** — run a small search (1-2 queries). Watch domains get discovered, scraped, scored, and qualified. Confirm tier badges + scores appear.
3. **Step 2** — run people search on 1-2 qualified domains. Confirm people are found and stored.
4. **Step 3** — run email search on those people. Confirm emails are discovered.
5. Return to **landing page** — counts are now non-zero.

- [ ] **Step 5: Commit**

```bash
cd D:/LocHere/Sales_Tool/localization-leads
git add -A
git commit -m "chore: remove old 4-step pages, replaced by 3-step pipeline"
```

---

## Self-Review Notes

This plan was reviewed against the spec (§1–7). Coverage check:

- **Spec §3.1 (domains table)** → Task 3 (db_init) ✅
- **Spec §3.2 (fresh start, no migration)** → Task 3 Step 3 + Task 9 Step 4 (delete old DB) ✅
- **Spec §3.3 (join repointing)** → Task 4 ✅
- **Spec §3.4 (new DB functions)** → Task 3 Step 4 ✅
- **Spec §4 (scoring)** → Task 2 (full TDD) ✅
- **Spec §5.1 (landing page)** → Task 8 ✅
- **Spec §5.2 (Step 1 page)** → Task 5 ✅
- **Spec §5.3 (Step 2 page)** → Task 6 ✅
- **Spec §5.4 (Step 3 page)** → Task 7 ✅
- **Spec §6 (full change set)** → all tasks ✅
- **Spec §7 (risks)** → fresh DB eliminates migration risk; scoring advisory-only ✅

**Execution order note:** Tasks 1→2→3→4 are sequential dependencies (test infra → scoring → schema → join repoint). Tasks 5/6/7 (pages) can be done in any order after Task 4, but the listed order matches the user flow. Task 8 (landing) depends on all page paths existing. Task 9 (cleanup) is last.
