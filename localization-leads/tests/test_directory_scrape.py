"""Directory / listicle scrape → verified companies (no network in unit tests)."""
import json
import sqlite3
import threading
from unittest.mock import patch

from sources.directory_scrape import (
    directory_search_queries,
    extract_names_from_snippet,
    is_directory_scrape_target,
    scrape_directory_companies,
)
from step1_qualify import qualify_from_ai_overview


def test_detects_known_directory_hosts():
    assert is_directory_scrape_target(
        "https://clutch.co/eg/translation",
        "Top Translation Services in Egypt",
    )
    assert is_directory_scrape_target(
        "https://www.goodfirms.co/directory/country/translation/egypt",
        "Top Translation Companies in Egypt - 2026 Reviews",
    )
    assert is_directory_scrape_target(
        "https://www.milestoneloc.com/blog/top-10",
        "Top 10 Translation Companies In Egypt 2025",
    )
    # Single company page — not a directory
    assert not is_directory_scrape_target(
        "https://www.certifiedtranslationoffices.com/alsun",
        "Localization Services in Cairo | Alsun Translation Services",
    )


def test_detects_lsp_industry_directories():
    assert is_directory_scrape_target(
        "https://www.proz.com/blueboard/123",
        "Proz Blue Board — Company",
    )
    assert is_directory_scrape_target(
        "https://www.translationdirectory.com/translators/egypt.htm",
        "Translation companies Egypt",
    )
    assert is_directory_scrape_target(
        "https://www.translatorscafe.com/cafe/MegaList.asp",
        "Translation agencies",
    )


def test_directory_search_queries_include_proz_for_localization():
    qs = directory_search_queries("localization", "Egypt")
    blob = " | ".join(qs).lower()
    assert "site:proz.com" in blob
    assert "site:translationdirectory.com" in blob
    assert "site:clutch.co" in blob
    assert "egypt" in blob


def test_directory_search_queries_general_dirs_for_other_industry():
    qs = directory_search_queries("gaming", "Germany")
    blob = " | ".join(qs).lower()
    assert "site:clutch.co" in blob
    assert "germany" in blob
    # LSP-only site: queries should not dominate non-LSP industries
    assert "site:proz.com" not in blob


def test_extract_names_from_goodfirms_style_snippet():
    snip = (
        "List of Translation Service Providers in Egypt "
        "Bayan-tech · Ali Saad Agency for Translation Services · "
        "DB Group · saudisoft · EgyTransLane for Translation Services"
    )
    names = extract_names_from_snippet(snip)
    joined = " | ".join(n.lower() for n in names)
    assert "bayan" in joined
    assert "saudisoft" in joined
    assert "egytranslane" in joined


def test_extract_names_from_numbered_snippet():
    snip = (
        "1. Milestone localization 2. GTE Localize "
        "3. Globalization Partners International GPI 4. Bayan-tech"
    )
    names = extract_names_from_snippet(snip)
    assert len(names) >= 3
    assert any("milestone" in n.lower() for n in names)
    assert any("gte" in n.lower() for n in names)


def test_scrape_directory_uses_html_and_snippet():
    html = """
    <html><body>
      <h2>1. Bayan-tech</h2>
      <a href="https://www.bayantech.com/">Visit Website</a>
      <h2>2. Future Trans</h2>
      <a href="https://future-trans.com/about">Future Trans</a>
      <a href="https://clutch.co/profile/x">Other directory</a>
    </body></html>
    """
    with patch("sources.directory_scrape._http_get", return_value=html):
        out = scrape_directory_companies(
            "https://www.goodfirms.co/directory/egypt",
            title="Top Translation Companies in Egypt",
            snippet="Bayan-tech · saudisoft · EgyTransLane",
            organic=[
                {"link": "https://saudisoft.com/", "title": "saudisoft — Translation"},
            ],
        )
    sources = {r["source"] for r in out}
    assert sources == {"directory"}
    domains = " ".join(r["link"] for r in out)
    assert "bayantech.com" in domains
    assert "future-trans.com" in domains or "future" in domains
    # Directory host itself never returned
    assert "goodfirms" not in domains
    assert "clutch.co" not in domains


def test_qualify_directory_reason(tmp_path):
    db = tmp_path / "d.db"
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
        "saudisoft.com", "Localization", "Egypt", "translation",
        conn, lock, company_name="saudisoft", source="directory",
    )
    assert res["status"] == "qualified"
    assert "directory_verified" in res["reasons"]
    row = conn.execute(
        "SELECT score_reasons FROM domains WHERE domain=?",
        ("saudisoft.com",),
    ).fetchone()
    assert "directory_verified" in json.loads(row[0])
    conn.close()
