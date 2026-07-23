"""
sources/people/title_filter.py — Title filtering.

Used after raw people are collected from X-Ray + LinkedIn /people page
sources. Apply this filter in the pipeline (pages/2_People.py), NOT in
the individual sources — that lets a source collect everyone and the
caller decide who's relevant.

Product decision: LocReach only needs a contact who is a Project Manager,
Vendor Manager, or Translation Manager (at LSPs or clients alike) — every
other role (C-suite, Director, VP, business development, etc.) is dropped,
regardless of company_type.

Returns True if the person's title should be kept.
"""
from __future__ import annotations

# Substring match, so this naturally also matches compound titles like
# "Localization Project Manager", "Translation Vendor Manager", etc.
_TARGET_ROLES = (
    "project manager",
    "vendor manager",
    "translation manager",
)


def passes(title: str, company_type: str = "") -> bool:
    """
    Returns True if `title` matches one of the three target roles:
    Project Manager, Vendor Manager, or Translation Manager.

    `company_type` is accepted for call-site compatibility (older callers
    pass it) but no longer changes the result — the same three roles are
    kept regardless of whether the company is an LSP or a client.
    """
    if not title:
        return False
    t = title.lower().strip()
    return any(role in t for role in _TARGET_ROLES)
