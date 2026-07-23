"""Tests for confirmed-email gate (Step 3 lead saving)."""
from sources.base import EmailResult
from sources.email.lead_gate import is_confirmed_lead


def test_l1_site_always_confirmed():
    r = EmailResult(email="jane@acme.com", label="Site ✓")
    assert is_confirmed_lead(r, "L1-Site") is True


def test_l4_search_always_confirmed():
    r = EmailResult(email="jane@acme.com", label="Search ✓", verified=True)
    assert is_confirmed_lead(r, "L4-Search") is True


def test_l2_requires_smtp_good():
    good = EmailResult(email="jane@acme.com", label="EFmt ✓", verified=True)
    risky = EmailResult(email="jane@acme.com", label="EFmt ~", verified=False)
    assert is_confirmed_lead(good, "L2-EFmt") is True
    assert is_confirmed_lead(risky, "L2-EFmt") is False


def test_unknown_layer_rejected():
    r = EmailResult(email="jane@acme.com", label="PatVfy ✓", verified=True)
    assert is_confirmed_lead(r, "L3-PatVfy") is False
