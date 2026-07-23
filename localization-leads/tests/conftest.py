"""Shared fixtures for the test suite."""
import sqlite3
import pytest

import sys, os
# Make the project root importable when pytest runs from anywhere
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def site_data_basic():
    """A minimal real-company homepage: ≥4 pages + LinkedIn, LSP keywords."""
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
            "https://acme.com/services",
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
