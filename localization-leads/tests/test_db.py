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
