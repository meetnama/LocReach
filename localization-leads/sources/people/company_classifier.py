"""
sources/people/company_classifier.py — classify a verified company as an
LSP (translation/localization service provider) or a Client (a company
that needs translation services).

Strategy (fast → expensive):
  1. Scrape homepage text via _fast_scrape() with Chrome fallback
  2. Keyword pass: if 2+ LSP-specific keywords appear → "lsp" (free, instant)
  3. Otherwise call Groq (llama-3.1-8b-instant, free 100K tokens/day) with
     the first 800 chars of homepage text
  4. On any failure → "client" (safer default; stricter title filter applies)

The result is cached in verified_companies.company_type so we never
re-classify the same company twice.
"""
from __future__ import annotations

import os
from typing import Optional

import requests

from sources.utils import _fast_scrape, chrome_scrape


# ── LSP keyword list ──────────────────────────────────────────────────────────
# Phrases that almost certainly appear on the homepage of a translation /
# localization service provider. We require 2+ hits to call it "lsp" without
# escalating to Groq — otherwise too many false positives (e.g. a SaaS that
# mentions "translation" once as a feature).
LSP_KEYWORDS = [
    "translation agency",
    "language service",
    "language services",
    "localization company",
    "localisation company",
    "translation services",
    "translation company",
    "interpretation services",
    "language solutions",
    "we translate",
    "our translators",
    "translation provider",
    "lsp",
    "transcreation",
    "post-editing",
    "post editing",
    "cat tool",
    "sdl",
    "memoq",
    "trados",
    "translation memory",
    "language service provider",
]

GROQ_URL   = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "llama-3.1-8b-instant"


def _scrape_homepage_text(company) -> str:
    """Get homepage text via _fast_scrape, Chrome fallback."""
    url = f"https://{company.domain}"
    try:
        data = _fast_scrape(url)
        if data is None:
            data = chrome_scrape(url)
        if not data:
            return ""
        return (data.get("markdown") or "").strip()
    except Exception:
        return ""


def _keyword_classify(text: str) -> Optional[str]:
    """
    Returns "lsp" if 2+ LSP keywords are present in the text.
    Returns None when the keyword signal is ambiguous (0 or 1 match) —
    caller should escalate to Groq in that case.
    """
    if not text:
        return None
    text_l = text.lower()
    hits = sum(1 for kw in LSP_KEYWORDS if kw in text_l)
    if hits >= 2:
        return "lsp"
    return None


def _groq_classify(text: str) -> str:
    """
    Call Groq to classify when keyword evidence is insufficient.
    Returns "lsp" or "client". Falls back to "client" on any error.
    """
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key:
        return "client"

    snippet = (text or "")[:800].strip()
    if not snippet:
        return "client"

    payload = {
        "model": GROQ_MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a B2B sales classifier. "
                    "Reply with exactly one word: lsp or client."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Based on this company homepage text, is this company "
                    "a translation/localization SERVICE PROVIDER (they do "
                    "translations for others) or a CLIENT that might NEED "
                    f"translation services?\n\nText: {snippet}"
                ),
            },
        ],
        "max_tokens":  5,
        "temperature": 0.0,
    }

    try:
        resp = requests.post(
            GROQ_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type":  "application/json",
            },
            json    = payload,
            timeout = 15,
        )
        if resp.status_code != 200:
            return "client"
        reply = resp.json()["choices"][0]["message"]["content"].lower().strip()
    except Exception:
        return "client"

    return "lsp" if "lsp" in reply else "client"


def classify_company(company) -> tuple[str, dict]:
    """
    Classify `company` as "lsp" or "client".

    Returns (company_type, debug_info) where debug_info is a small dict
    suitable for the per-company debug log (text length, keyword hit count,
    method used, etc.).
    """
    text = _scrape_homepage_text(company)
    info: dict = {
        "scrape_chars": len(text),
        "method":       None,
        "kw_hits":      0,
    }

    if not text:
        info["method"] = "default (no homepage text)"
        return "client", info

    # Count keyword hits for the debug log even if we still escalate to Groq
    text_l = text.lower()
    hits   = sum(1 for kw in LSP_KEYWORDS if kw in text_l)
    info["kw_hits"] = hits

    if hits >= 2:
        info["method"] = "keywords"
        return "lsp", info

    # Ambiguous → ask Groq
    result = _groq_classify(text)
    info["method"] = "groq" if os.getenv("GROQ_API_KEY", "").strip() else "default (no GROQ_API_KEY)"
    return result, info
