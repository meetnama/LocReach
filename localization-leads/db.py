"""
db.py — SQLite database layer for leads.db

Single source of truth for all DB operations.
Both the pipeline engine and the UI import from here.
"""
import sqlite3
from datetime import datetime

DB_PATH = "leads.db"


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


def db_wipe_all(conn: sqlite3.Connection) -> dict:
    """
    Wipe all pipeline tables for a clean start (keeps schema).
    Returns per-table row counts deleted.
    """
    counts = {}
    for table in ("leads", "people", "domains", "blocked_domains"):
        try:
            cur = conn.execute(f"SELECT COUNT(*) FROM {table}")
            n = cur.fetchone()[0]
            conn.execute(f"DELETE FROM {table}")
            counts[table] = n
        except sqlite3.OperationalError:
            counts[table] = 0
    conn.commit()
    try:
        conn.execute("VACUUM")
    except Exception:
        pass
    return counts


def db_email_exists(conn: sqlite3.Connection, email: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM leads WHERE email=?", (email,)
    ).fetchone() is not None


def db_insert_lead(conn: sqlite3.Connection, lead: dict) -> None:
    conn.execute("""
        INSERT OR IGNORE INTO leads
          (email, email_source, full_name, first_name, last_name, title, company,
           domain, country, linkedin_url, source_url)
        VALUES
          (:email, :email_source, :full_name, :first_name, :last_name, :title, :company,
           :domain, :country, :linkedin_url, :source_url)
    """, lead)
    conn.commit()


def db_mark_blocked_domain(conn: sqlite3.Connection, domain: str) -> None:
    """Persist a filtered/blocked domain so it is skipped in future searches."""
    conn.execute(
        "INSERT OR IGNORE INTO blocked_domains (domain, blocked_at) VALUES (?,?)",
        (domain, datetime.now().isoformat()),
    )
    conn.commit()


def db_load_blocked_domains(conn: sqlite3.Connection) -> set:
    """Return the set of all previously blocked domains."""
    rows = conn.execute("SELECT domain FROM blocked_domains").fetchall()
    return {r[0] for r in rows}


def db_load_all_domain_names(conn: sqlite3.Connection) -> set:
    """
    Return every domain already present in the `domains` table, regardless
    of status (qualified/rejected/failed/unreachable/discovered). Used by
    Step 1 so previously checked companies are never rescraped.
    """
    rows = conn.execute("SELECT domain FROM domains").fetchall()
    return {r[0] for r in rows}


def db_load_kept_domain_names(conn: sqlite3.Connection) -> set:
    """
    Domains already qualified. Prefer db_load_all_domain_names for Step 1
    skip lists so failed/unreachable/rejected are also not rechecked.
    """
    rows = conn.execute(
        "SELECT domain FROM domains WHERE status='qualified'"
    ).fetchall()
    return {r[0] for r in rows}


def db_promote_stale_rejects(conn: sqlite3.Connection) -> int:
    """
    Legacy: old LinkedIn gate wrote status=rejected for 'possible'/'strong'.
    Disabled — it also re-promoted geographic rejects (geo_fail) back to
    qualified (e.g. tuko.co.ke for an Egypt search). Returns 0.
    """
    return 0


def db_demote_geo_rejects(conn: sqlite3.Connection) -> int:
    """
    Demote any qualified row whose score_reasons record a geographic gate
    failure. Those must not stay qualified or feed Step 2/3.
    Returns number of rows demoted.
    """
    cur = conn.execute(
        """
        UPDATE domains
           SET status='rejected'
         WHERE status='qualified'
           AND IFNULL(score_reasons, '') LIKE '%geo_fail:%'
        """
    )
    conn.commit()
    return cur.rowcount or 0



# ── people ──────────────────────────────────────────────────────────────────────

def db_insert_person(conn: sqlite3.Connection, data: dict) -> None:
    """Insert a person — silently skips duplicates (domain, full_name)."""
    conn.execute("""
        INSERT OR IGNORE INTO people
          (domain, company_name, first_name, last_name, full_name,
           title, linkedin_url, people_source, found_at)
        VALUES
          (:domain, :company_name, :first_name, :last_name, :full_name,
           :title, :linkedin_url, :people_source, :found_at)
    """, data)
    conn.commit()


def db_mark_company_people_done(conn: sqlite3.Connection, domain: str) -> None:
    """Stamp people_searched_at so this company is not re-searched."""
    conn.execute(
        "UPDATE domains SET people_searched_at=? WHERE domain=?",
        (datetime.now().isoformat(), domain),
    )
    conn.commit()


def db_reset_people_search(conn: sqlite3.Connection,
                            industry: str = "", country: str = "") -> int:
    """
    Clear people_searched_at so companies are re-searched in the next run.
    Returns the number of companies reset.
    Optionally scoped to an industry / country slice.
    """
    if industry and country:
        cur = conn.execute(
            "UPDATE domains SET people_searched_at=NULL "
            "WHERE status='qualified' AND industry=? AND country=?",
            (industry, country),
        )
    elif industry:
        cur = conn.execute(
            "UPDATE domains SET people_searched_at=NULL "
            "WHERE status='qualified' AND industry=?",
            (industry,),
        )
    elif country:
        cur = conn.execute(
            "UPDATE domains SET people_searched_at=NULL "
            "WHERE status='qualified' AND country=?",
            (country,),
        )
    else:
        cur = conn.execute(
            "UPDATE domains SET people_searched_at=NULL "
            "WHERE status='qualified'"
        )
    conn.commit()
    return cur.rowcount


def db_get_company_type(conn: sqlite3.Connection, domain: str) -> str:
    """Return 'lsp' / 'client' / '' (empty when never classified)."""
    row = conn.execute(
        "SELECT company_type FROM domains WHERE domain=?",
        (domain,),
    ).fetchone()
    if not row or not row[0]:
        return ""
    return row[0]


def db_set_company_type(conn: sqlite3.Connection, domain: str,
                        company_type: str) -> None:
    """Persist the LSP-vs-client classification so it's only computed once."""
    conn.execute(
        "UPDATE domains SET company_type=? WHERE domain=?",
        (company_type, domain),
    )
    conn.commit()


def db_load_people(conn: sqlite3.Connection,
                   industry: str = "", country: str = "") -> list:
    """Return all found people, optionally filtered by company industry/country."""
    if industry and country:
        rows = conn.execute("""
            SELECT p.full_name, p.title, p.company_name, p.domain,
                   p.linkedin_url, p.people_source, p.found_at,
                   v.company_type
            FROM people p
            JOIN domains v ON p.domain = v.domain
            WHERE v.industry=? AND v.country=?
            ORDER BY p.id DESC
        """, (industry, country)).fetchall()
    elif industry:
        rows = conn.execute("""
            SELECT p.full_name, p.title, p.company_name, p.domain,
                   p.linkedin_url, p.people_source, p.found_at,
                   v.company_type
            FROM people p
            JOIN domains v ON p.domain = v.domain
            WHERE v.industry=?
            ORDER BY p.id DESC
        """, (industry,)).fetchall()
    elif country:
        rows = conn.execute("""
            SELECT p.full_name, p.title, p.company_name, p.domain,
                   p.linkedin_url, p.people_source, p.found_at,
                   v.company_type
            FROM people p
            JOIN domains v ON p.domain = v.domain
            WHERE v.country=?
            ORDER BY p.id DESC
        """, (country,)).fetchall()
    else:
        rows = conn.execute("""
            SELECT p.full_name, p.title, p.company_name, p.domain,
                   p.linkedin_url, p.people_source, p.found_at,
                   v.company_type
            FROM people p
            LEFT JOIN domains v ON p.domain = v.domain
            ORDER BY p.id DESC
        """).fetchall()
    return rows


# ── Step 4 — email finder ─────────────────────────────────────────────────────

def db_load_people_without_email(conn: sqlite3.Connection,
                                  industry: str = "", country: str = "") -> list:
    """
    Return people whose email has not been searched yet (email_searched_at IS NULL).
    Returns list of tuples: (id, domain, company_name, first_name, last_name,
                              full_name, title, linkedin_url, people_source)
    """
    if industry and country:
        rows = conn.execute("""
            SELECT p.id, p.domain, p.company_name, p.first_name, p.last_name,
                   p.full_name, p.title, p.linkedin_url, p.people_source
            FROM people p
            JOIN domains v ON p.domain = v.domain
            WHERE p.email_searched_at IS NULL AND v.industry=? AND v.country=?
            ORDER BY p.id
        """, (industry, country)).fetchall()
    elif industry:
        rows = conn.execute("""
            SELECT p.id, p.domain, p.company_name, p.first_name, p.last_name,
                   p.full_name, p.title, p.linkedin_url, p.people_source
            FROM people p
            JOIN domains v ON p.domain = v.domain
            WHERE p.email_searched_at IS NULL AND v.industry=?
            ORDER BY p.id
        """, (industry,)).fetchall()
    elif country:
        rows = conn.execute("""
            SELECT p.id, p.domain, p.company_name, p.first_name, p.last_name,
                   p.full_name, p.title, p.linkedin_url, p.people_source
            FROM people p
            JOIN domains v ON p.domain = v.domain
            WHERE p.email_searched_at IS NULL AND v.country=?
            ORDER BY p.id
        """, (country,)).fetchall()
    else:
        rows = conn.execute("""
            SELECT p.id, p.domain, p.company_name, p.first_name, p.last_name,
                   p.full_name, p.title, p.linkedin_url, p.people_source
            FROM people p
            WHERE p.email_searched_at IS NULL
            ORDER BY p.id
        """).fetchall()
    return rows


def db_mark_person_email_done(conn: sqlite3.Connection, person_id: int) -> None:
    """Stamp email_searched_at so this person is not re-searched on resume."""
    conn.execute(
        "UPDATE people SET email_searched_at=? WHERE id=?",
        (datetime.now().isoformat(), person_id),
    )
    conn.commit()


def db_load_leads(conn: sqlite3.Connection,
                  industry: str = "", country: str = "") -> list:
    """Return all leads, optionally filtered by company industry/country."""
    if industry and country:
        rows = conn.execute("""
            SELECT l.email, l.email_source, l.full_name, l.title, l.company,
                   l.domain, l.linkedin_url
            FROM leads l
            WHERE l.domain IN (
                SELECT domain FROM domains WHERE industry=? AND country=?
            )
            ORDER BY l.id DESC
        """, (industry, country)).fetchall()
    elif industry:
        rows = conn.execute("""
            SELECT l.email, l.email_source, l.full_name, l.title, l.company,
                   l.domain, l.linkedin_url
            FROM leads l
            WHERE l.domain IN (
                SELECT domain FROM domains WHERE industry=?
            )
            ORDER BY l.id DESC
        """, (industry,)).fetchall()
    elif country:
        rows = conn.execute("""
            SELECT l.email, l.email_source, l.full_name, l.title, l.company,
                   l.domain, l.linkedin_url
            FROM leads l
            WHERE l.domain IN (
                SELECT domain FROM domains WHERE country=?
            )
            ORDER BY l.id DESC
        """, (country,)).fetchall()
    else:
        rows = conn.execute("""
            SELECT email, email_source, full_name, title, company, domain, linkedin_url
            FROM leads ORDER BY id DESC
        """).fetchall()
    return rows


def db_count_leads(conn: sqlite3.Connection) -> int:
    """Return total number of leads saved."""
    row = conn.execute("SELECT COUNT(*) FROM leads").fetchone()
    return row[0] if row else 0


def db_load_all(free_email_domains: set, db_path: str = DB_PATH) -> list:
    """
    Load all leads from the database for export.
    Filters out personal emails and reconstructs missing full_name / domain fields
    from older rows.
    """
    try:
        conn = sqlite3.connect(db_path)
        db_init(conn)
        rows = conn.execute("""
            SELECT email, email_source, full_name, first_name, last_name,
                   title, company, domain, country, linkedin_url
            FROM leads ORDER BY id DESC
        """).fetchall()
        conn.close()
    except Exception:
        return []

    keys = ["email", "email_source", "full_name", "first_name", "last_name",
            "title", "company", "domain", "country", "linkedin_url"]
    leads = []
    for row in rows:
        d = dict(zip(keys, row))
        # Reconstruct missing fields from older rows
        if not d["full_name"] and (d["first_name"] or d["last_name"]):
            d["full_name"] = f"{d['first_name']} {d['last_name']}".strip()
        if not d["domain"] and "@" in d["email"]:
            d["domain"] = d["email"].split("@")[1].lower()
        # Skip personal emails
        email_dom = d["email"].split("@")[1].lower() if "@" in d["email"] else ""
        if email_dom in free_email_domains:
            continue
        leads.append(d)
    return leads


# ── domains table (unified Step 1 output) ─────────────────────────────────────

def db_upsert_domain(conn: sqlite3.Connection, data: dict) -> None:
    """
    Insert a domain or update its fields. Required key: 'domain'.
    Only provided fields are written; absent keys keep their existing value.

    status values: 'discovered' | 'qualified' | 'rejected' | 'failed' | 'unreachable'
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


def db_count_domains(conn: sqlite3.Connection) -> dict:
    """Return status counts for the landing-page stat cards."""
    rows = conn.execute(
        "SELECT status, COUNT(*) FROM domains GROUP BY status"
    ).fetchall()
    counts = {"discovered": 0, "qualified": 0, "rejected": 0}
    for status, n in rows:
        counts[status] = n
    return counts
