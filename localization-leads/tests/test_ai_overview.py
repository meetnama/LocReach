"""AI Overview + Local Pack verify-fast-path unit tests (no Chrome / no network)."""
import json
import sqlite3
import threading

from sources.utils import (
    merge_ai_overview_results,
    merge_local_pack_results,
    resolve_ai_overview_link,
)
from step1_qualify import ai_overview_screen, qualify_from_ai_overview


def test_resolve_prefers_host_matching_company_name():
    href = resolve_ai_overview_link(
        "BayanTech",
        link="https://www.goodfirms.co/company/bayantech",  # blocked directory
        organic=[
            {"link": "https://www.bayantech.com/", "title": "BayanTech — Localization"},
        ],
        aio_links=["https://www.goodfirms.co/company/bayantech"],
    )
    assert "bayantech.com" in href


def test_resolve_uses_explicit_company_link():
    href = resolve_ai_overview_link(
        "Rosetta Certified Translation",
        link="https://rosettacertified.com/",
        organic=[],
    )
    assert "rosettacertified.com" in href


def test_merge_drops_unresolved_and_directories():
    aio_raw = [
        {"title": "BayanTech", "link": "", "snippet": "Cairo LSP"},
        {"title": "Ghost Co", "link": "", "snippet": "no organic hit"},
        {
            "title": "Arabize",
            "link": "https://arabize.com/about",
            "snippet": "est. 1994",
        },
    ]
    organic = [
        {"link": "https://bayantech.com/", "title": "BayanTech Egypt"},
        {"link": "https://clutch.co/eg/translation", "title": "Top firms"},
    ]
    out = merge_ai_overview_results(aio_raw, organic=organic)
    domains = {r["link"] for r in out}
    assert any("bayantech.com" in d for d in domains)
    assert any("arabize.com" in d for d in domains)
    assert not any("ghost" in d.lower() for d in domains)
    assert not any("clutch" in d for d in domains)
    assert all(r["source"] == "ai_overview" for r in out)


def test_ai_overview_screen_hygiene():
    keep, reason, domain = ai_overview_screen(
        url="https://bayantech.com/",
        skip_domains=set(),
        country="Egypt",
    )
    assert keep and domain == "bayantech.com" and reason == ""

    keep, reason, domain = ai_overview_screen(
        url="https://bayantech.com/",
        skip_domains={"bayantech.com"},
        country="Egypt",
    )
    assert not keep and reason == "duplicate"


def test_qualify_from_ai_overview_skips_http_and_marks_reason(tmp_path):
    db = tmp_path / "t.db"
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
        "bayantech.com", "Localization", "Egypt", "localization companies",
        conn, lock, company_name="BayanTech",
    )
    assert res["status"] == "qualified"
    assert res["pages_fetched"] == 0
    assert "ai_overview_verified" in res["reasons"]
    row = conn.execute(
        "SELECT status, score_reasons, company_name FROM domains WHERE domain=?",
        ("bayantech.com",),
    ).fetchone()
    assert row[0] == "qualified"
    assert "ai_overview_verified" in json.loads(row[1])
    assert row[2] == "BayanTech"
    conn.close()


def test_merge_local_pack_tags_source():
    pack_raw = [
        {
            "title": "EgyTranscript Translation & Interpretation Agency",
            "link": "https://egytranscript.com/",
            "snippet": "Dokki — translation service",
            "source": "local_pack",
        },
        {
            "title": "Future Trans",
            "link": "",
            "snippet": "Dokki",
        },
        {
            "title": "Bayantech – Translation & Localization Services",
            "link": "https://www.bayantech.com/",
            "snippet": "Agouza",
        },
    ]
    organic = [
        {"link": "https://future-trans.com/", "title": "Future Trans — Localization"},
    ]
    out = merge_local_pack_results(pack_raw, organic=organic)
    assert all(r["source"] == "local_pack" for r in out)
    domains = {r["link"] for r in out}
    assert any("egytranscript.com" in d for d in domains)
    assert any("bayantech.com" in d for d in domains)
    assert any("future" in d for d in domains)


def test_qualify_local_pack_reason(tmp_path):
    db = tmp_path / "t2.db"
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
        "egytranscript.com", "Localization", "Egypt", "localization",
        conn, lock, company_name="EgyTranscript", source="local_pack",
    )
    assert res["status"] == "qualified"
    assert res["source"] == "local_pack"
    assert "local_pack_verified" in res["reasons"]
    row = conn.execute(
        "SELECT score_reasons FROM domains WHERE domain=?",
        ("egytranscript.com",),
    ).fetchone()
    assert "local_pack_verified" in json.loads(row[0])
    conn.close()
