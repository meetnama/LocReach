"""
geo.py — Geographic qualification gate.

Confirms a candidate company is actually BASED in the user-selected country,
not merely serving it. Global vendors (RWS, CCJK, TridIndia, BLEND, …) rank for
"<industry> companies in <country>" because they advertise that market, but a
generic gTLD (.com) with no local address/phone should not qualify under a
country filter. Signals used, strongest first:

  1. ccTLD of the domain     (.eg → Egypt = based there; .in → India = foreign)
  2. Explicit HQ / office phrasing   ("based in Egypt", …)
  3. A major city of the country in the page text   (Cairo, Alexandria …)
  4. Local phone is recorded as supporting evidence only when it looks like a
     real number (code + digits). A bare dialling code like "Egypt (+20)" in a
     contact-form dropdown is ignored, and phone alone never passes the gate.

A bare country-name mention is deliberately NOT sufficient — that is exactly
what lets global vendors slip through when they list every market they serve.
"""
from __future__ import annotations

import re

from config import COUNTRY_GEO, TLD_COUNTRY


def _cctld_by_country() -> dict:
    inv: dict = {}
    for tld, ctry in TLD_COUNTRY.items():
        inv.setdefault(ctry, []).append(tld)
    return inv


_CCTLD_BY_COUNTRY = _cctld_by_country()
# Longest TLDs first so ".com.eg" wins over ".eg" and ".com.au" over ".au".
_SORTED_TLDS = sorted(TLD_COUNTRY.items(), key=lambda kv: -len(kv[0]))

_HQ_PREFIXES = ("based in ", "headquartered in ", "located in ", "offices in ")

# Extra SERP tokens (local script / common forms) not always in COUNTRY_GEO.adj
_SERP_COUNTRY_EXTRA = {
    "Egypt": ["مصر", "القاهرة", "الإسكندرية", "الجيزة"],
}


def serp_suggests_country(
    title: str,
    snippet: str,
    country: str,
    domain: str = "",
    *,
    require_signal: bool = False,
) -> bool:
    """
    First-pass geo hint from SERP title/snippet — decide whether to open the
    domain at all. Looser than verify_country_location: country name, adjective,
    or major city in the blurb is enough (e.g. "translation services in Egypt").

    Thin/empty SERP text returns True by default so we don't starve when engines
    omit snippets; on-page geo still decides keep/reject after fetch.

    When ``require_signal=True`` (SERP-summary verified fast-path), thin text
    does NOT auto-pass — a real country/city/ccTLD token is required.
    """
    country = (country or "").strip()
    if not country or country == "All Countries":
        return True

    dom = (domain or "").lower().strip().removeprefix("www.")
    for tld in sorted(_CCTLD_BY_COUNTRY.get(country, []), key=len, reverse=True):
        if dom.endswith(tld):
            return True

    combined = f"{title or ''} {snippet or ''}".strip()
    if len(combined) < 20:
        return not require_signal

    combined_lc = combined.lower()
    geo = COUNTRY_GEO.get(country) or {}
    tokens_lc = [country.lower()]
    tokens_lc.extend(a.lower() for a in (geo.get("adj") or []) if a)
    tokens_lc.extend(c.lower() for c in (geo.get("cities") or []) if c)
    if any(t and _token_in_text(t, combined_lc) for t in tokens_lc):
        return True
    # Local-script extras (e.g. Arabic مصر) — match on original combined text
    for t in _SERP_COUNTRY_EXTRA.get(country) or []:
        if t and (t in combined or _token_in_text(t.lower(), combined_lc)):
            return True
    return False


def _token_in_text(needle: str, text_lc: str) -> bool:
    """Word-boundary match so 'lima'∉'preliminary', 'rome'∉'chromosome'."""
    n = (needle or "").strip().lower()
    if not n or not text_lc:
        return False
    if " " in n:
        return n in text_lc
    return bool(re.search(rf"(?<![a-z0-9]){re.escape(n)}(?![a-z0-9])", text_lc))


def _phone_code_digits(code: str) -> str:
    return (code or "").lstrip("+").strip()


def _has_bare_phone_code(text_lc: str, code: str) -> bool:
    """True if the dialling prefix appears at all (including dropdown lists)."""
    digits = _phone_code_digits(code)
    if not digits:
        return False
    patterns = [
        f"+{digits}",
        f"00{digits}",
        f"({digits})",
        f"( {digits} )",
        f"+ {digits}",
    ]
    return any(p in text_lc for p in patterns)


def _has_local_phone_number(text_lc: str, code: str) -> bool:
    """
    True only for a real local number: country code followed by enough
    subscriber digits. Rejects bare codes such as "Egypt (+20)" in forms.
    """
    digits = _phone_code_digits(code)
    if not digits:
        return False
    # +20 2 1234 5678 / 0020-10-xxxxxxx / (+20) 1234567890
    # Require ≥7 further digits so a lone "(+20)" in a country list fails.
    pat = re.compile(
        rf"(?<!\d)(?:\+|00)\s*{re.escape(digits)}"
        rf"[\s\-./()]*(?:\d[\s\-./()]*){{7,}}"
    )
    return bool(pat.search(text_lc))


def verify_country_location(domain: str, text: str, country: str) -> tuple[bool, list[str]]:
    """
    Decide whether `domain` / page `text` indicate a company based in `country`.

    Returns (is_based_in_country, evidence). When `country` is empty or
    "All Countries" the gate is disabled and always passes.
    """
    country = (country or "").strip()
    if not country or country == "All Countries":
        return True, ["location gate off"]

    dom = (domain or "").lower().strip().removeprefix("www.")
    text_lc = (text or "").lower()

    # 1. Domain ccTLD ---------------------------------------------------------
    for tld in sorted(_CCTLD_BY_COUNTRY.get(country, []), key=len, reverse=True):
        if dom.endswith(tld):
            return True, [f"ccTLD {tld}"]
    # A ccTLD belonging to a *different* country is strong proof it is foreign.
    for tld, ctry in _SORTED_TLDS:
        if ctry != country and dom.endswith(tld):
            return False, [f"foreign ccTLD {tld} -> {ctry}"]

    geo = COUNTRY_GEO.get(country)
    if not geo:
        # No signal table for this country — fall back to a plain name mention.
        hit = country.lower() in text_lc
        return hit, ([f"name '{country}'"] if hit else ["no location signal"])

    evidence: list[str] = []
    code = geo.get("code", "")

    # 2. Explicit HQ / office phrasing ---------------------------------------
    hq_ok = False
    for adj in geo.get("adj", []):
        if any((prefix + adj) in text_lc for prefix in _HQ_PREFIXES):
            hq_ok = True
            evidence.append(f"HQ phrase '{adj}'")
            break

    # 3. Major city (word-boundary — avoid lima⊂preliminary, rome⊂chromosome)
    city_hit = next(
        (c for c in geo.get("cities", []) if c and _token_in_text(c, text_lc)),
        None,
    )
    if city_hit:
        evidence.append(f"city '{city_hit}'")

    # 4. Local phone — real number only; bare "+20" / "Egypt (+20)" ignored ----
    phone_full = _has_local_phone_number(text_lc, code)
    phone_bare = _has_bare_phone_code(text_lc, code)
    if phone_full:
        evidence.append(f"phone {code} number")
    elif phone_bare:
        evidence.append(f"phone {code} code-only (ignored)")

    # A phone signal alone is never enough (global contact forms list every
    # dialling code; one +20 line is too weak). Require HQ phrasing or a
    # major city. City-only on a generic gTLD is weak without HQ or a real
    # local phone — still accept city when HQ is present, or city + phone.
    if hq_ok:
        return True, evidence
    if city_hit and phone_full:
        return True, evidence
    # City alone: accept only when the page also mentions the country/adj
    # (reduces "Rome"/"Lima" false locals on global vendor pages).
    if city_hit:
        country_mentioned = _token_in_text(country.lower(), text_lc) or any(
            _token_in_text(a.lower(), text_lc) for a in (geo.get("adj") or []) if a
        )
        if country_mentioned:
            return True, evidence
        evidence.append("city alone without country/HQ (ignored)")

    if phone_bare and not hq_ok and not city_hit:
        return False, evidence + ["need city or HQ (phone alone insufficient)"]
    return False, evidence if evidence else ["no local address / phone / city"]
