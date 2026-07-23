"""
sources/email/lead_gate.py — Decide whether an email result is confirmed enough to save.

Product rule (Step 3): only save leads with real evidence — not SMTP guesses.
  L1 Site crawl  → confirmed (email found on the company website)
  L2 EmailFormat   → confirmed only when SMTP verifier returns "good"
  L4 SearXNG       → confirmed (email indexed in search results)
"""
from __future__ import annotations

from sources.base import EmailResult


def is_confirmed_lead(result: EmailResult | None, layer: str) -> bool:
    """Return True if this email should be persisted as a lead."""
    if not result or not result.email or not layer:
        return False
    if layer == "L1-Site":
        return True
    if layer == "L4-Search":
        return True
    if layer == "L2-EFmt":
        return bool(result.verified)
    return False
