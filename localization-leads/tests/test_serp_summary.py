"""SERP title+snippet verify fast-path (industry ≥1 word + geo)."""
import json
import sqlite3
import threading

from sources.directory_scrape import directory_search_queries
from step1_qualify import (
    serp_summary_has_industry,
    serp_summary_verified,
    qualify_from_ai_overview,
)


def test_serp_summary_rosetta_style():
    title = "The Best Localization & Translation Companies in Egypt Certified ..."
    snippet = (
        "Rosetta The Best Localization Companies in Egypt provides "
        "high-quality and accurate website translation and localization service"
    )
    assert serp_summary_has_industry(title, snippet, "localization")
    assert serp_summary_verified(
        title, snippet, "localization",
        country="Egypt", domain="rosettacertified.com",
    )


def test_serp_summary_transtec_style():
    title = "Transtec - Certified Translation Office in Cairo"
    snippet = (
        "Transtec offers professional translation services in Cairo, Egypt "
        "... Localization Services. Localization and translation of websites"
    )
    assert serp_summary_verified(
        title, snippet, "localization",
        country="Egypt", domain="transteceg.com",
    )
    assert serp_summary_verified(
        title, snippet, "translation",
        country="Egypt", domain="transteceg.com",
    )


def test_serp_summary_rejects_industry_without_geo():
    title = "Acme Translation & Localization Services"
    snippet = "We offer localization and translation worldwide"
    assert serp_summary_has_industry(title, snippet, "localization")
    assert not serp_summary_verified(
        title, snippet, "localization",
        country="Egypt", domain="acme.com",
    )


def test_serp_summary_rejects_ambiguous_localization_only():
    title = "Acme Localization Services in Egypt"
    snippet = "We offer localization in Cairo, Egypt"
    assert not serp_summary_has_industry(title, snippet, "localization")
    assert not serp_summary_verified(
        title, snippet, "localization",
        country="Egypt", domain="acme.com",
    )


def test_serp_summary_rejects_thin_blurb_without_geo_token():
    title = "Acme Translation Co"
    snippet = "Professional LSP"
    assert serp_summary_has_industry(title, snippet, "localization")
    assert not serp_summary_verified(
        title, snippet, "localization",
        country="Egypt", domain="acme.com",
    )


def test_serp_summary_rejects_geo_without_industry():
    title = "Acme Mining Corp — Cairo, Egypt"
    snippet = "Leading mining and minerals company in Egypt"
    assert not serp_summary_has_industry(title, snippet, "localization")
    assert not serp_summary_verified(
        title, snippet, "localization",
        country="Egypt", domain="acmemining.com",
    )


def test_directory_queries_come_before_generic_in_bank_contract():
    """Directory site: queries exist so the Step 1 bank can put them first."""
    qs = directory_search_queries("localization", "Egypt")
    assert qs
    assert any(q.startswith("site:") for q in qs)


def test_qualify_serp_summary_reason(tmp_path):
    db = tmp_path / "s.db"
    conn = sqlite3.connect(str(db))
    conn.execute(
        """CREATE TABLE domains (
            id INTEGER PRIMARY KEY,
            domain TEXT UNIQUE,
            status TEXT,
            industry TEXT, country TEXT, keyword TEXT,
            company_name TEXT DEFAULT '',
            linkedin_url TEXT DEFAULT '',
            score INTEGER, score_tier TEXT, score_reasons TEXT,
            company_type TEXT DEFAULT '',
            found_at TEXT, qualified_at TEXT,
            people_searched_at TEXT
        )"""
    )
    conn.commit()
    lock = threading.Lock()
    res = qualify_from_ai_overview(
        "transteceg.com", "Localization", "Egypt", "localization",
        conn, lock, company_name="Transtec", source="serp_summary",
    )
    assert res["status"] == "qualified"
    assert "serp_summary_verified" in res["reasons"]
    row = conn.execute(
        "SELECT score_reasons FROM domains WHERE domain=?",
        ("transteceg.com",),
    ).fetchone()
    assert "serp_summary_verified" in json.loads(row[0])
    conn.close()
