"""Tests for Excel export against the unified domains schema."""
from db import db_init, db_upsert_domain, db_insert_lead
from export_excel import build_excel_bytes


def test_build_excel_bytes_with_new_schema(fresh_db):
    """export_excel must query the unified `domains` table, not legacy names."""
    db_upsert_domain(fresh_db, {
        "domain": "acme.com",
        "status": "qualified",
        "industry": "translation",
        "country": "Germany",
        "keyword": "test",
    })
    db_insert_lead(fresh_db, {
        "email": "jane@acme.com",
        "email_source": "Site ✓",
        "full_name": "Jane Doe",
        "first_name": "Jane",
        "last_name": "Doe",
        "title": "Project Manager",
        "company": "Acme",
        "domain": "acme.com",
        "country": "Germany",
        "linkedin_url": "",
        "source_url": "",
    })

    db_path = fresh_db.execute("PRAGMA database_list").fetchone()[2]
    data = build_excel_bytes(db_path)

    assert isinstance(data, bytes)
    assert len(data) > 1000
    assert data[:2] == b"PK"  # xlsx is a zip archive
