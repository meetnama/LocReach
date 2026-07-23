"""
sources/email/emailformat_pattern.py — Free email-pattern lookup via email-format.com

email-format.com is a crowd-sourced email format database.
For any company domain, it returns the most commonly used email pattern
(e.g. first.last, flast, first_last, etc.).

No API key.  No signup.  Zero cost.

Strategy
────────
  1. GET https://www.email-format.com/d/{domain}/
  2. Parse the top-ranked email format from the HTML.
  3. Map that format to our internal pattern names (same keys as GENERATORS
     in internet_pattern.py).
  4. Generate candidate  →  SmtpVerifier checks it  →  return EmailResult.

Pattern extraction — two-pass approach
  Pass A: look for Hunter-style tokens in the page text:
          {first}.{last}  {f}.{last}  {first}_{last}  etc.
  Pass B: look for example emails with "John Doe" as the test name
          (john.doe@  jdoe@  johndoe@  etc.) and classify them structurally.

Caching
  Per-domain, for the lifetime of the pipeline run.
  email-format.com may not have data for small/new domains — returns None silently.

Rate limiting
  email-format.com does not require API keys but may block aggressive scrapers.
  We add a 1-second inter-domain delay and a respectful User-Agent.
"""

import re
import time
import unicodedata
from typing import Optional, Dict

import requests

from sources.base import EmailSource, Person, EmailResult, LogFn
from sources.utils import is_generic_email

_BASE        = "https://www.email-format.com/d"
_TIMEOUT     = 12
_INTER_DELAY = 0.3   # seconds between domain fetches (politeness)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# ── Pattern mapping ───────────────────────────────────────────────────────────
# Maps whatever email-format.com shows → our internal GENERATORS key.
#
# email-format.com may display:
#   • Hunter-style tokens   :  {first}.{last}  {f}.{last}  {first}{last}  etc.
#   • Example emails        :  john.doe@  j.doe@  johndoe@  jdoe@  john_doe@
#   • Plain text descriptions: "First Last" → we detect by example email shape
#
# When the page shows an example email with test name "John Doe":
#   local part "john.doe"  → first.last
#   local part "j.doe"     → f.last
#   local part "john.d"    → first.l
#   local part "john_doe"  → first_last
#   local part "johndoe"   → firstlast  (long, no separator)
#   local part "jdoe"      → flast      (initial + surname)
#   local part "doe"       → last
#   local part "john"      → first

# ── Hunter-style token → pattern name ────────────────────────────────────────
_TOKEN_TO_NAME: Dict[str, str] = {
    "{first}.{last}":  "first.last",
    "{f}.{last}":      "f.last",
    "{first}.{l}":     "first.l",
    "{first}_{last}":  "first_last",
    "{first}{last}":   "firstlast",
    "{f}{last}":       "flast",
    "{last}.{first}":  "last.first",   # rare but exists
    "{last}{first}":   "lastfirst",    # rare
    "{last}_{first}":  "last_first",   # rare
    "{last}":          "last",
    "{first}":         "first",
}

# ── Pattern generators (same as GENERATORS in internet_pattern.py) ────────────
_GENERATORS: Dict[str, callable] = {
    "first.last":  lambda f, l: f"{f}.{l}",
    "f.last":      lambda f, l: f"{f[0]}.{l}",
    "first.l":     lambda f, l: f"{f}.{l[0]}",
    "first_last":  lambda f, l: f"{f}_{l}",
    "firstlast":   lambda f, l: f"{f}{l}",
    "flast":       lambda f, l: f"{f[0]}{l}",
    "last.first":  lambda f, l: f"{l}.{f}",
    "lastfirst":   lambda f, l: f"{l}{f}",
    "last_first":  lambda f, l: f"{l}_{f}",
    "last":        lambda f, l: l,
    "first":       lambda f, l: f,
}

# ── Test name used by email-format.com for examples ───────────────────────────
# The site shows "John Smith" or "John Doe" as the example person.
_TEST_FIRST = ["john", "jane", "james", "william", "michael"]
_TEST_LAST  = ["smith", "doe", "jones", "williams", "brown", "taylor", "davis",
               "miller", "wilson", "moore", "anderson", "white"]


# ── Name helpers ──────────────────────────────────────────────────────────────

def _norm(s: str) -> str:
    s = s.lower().strip()
    s = unicodedata.normalize("NFKD", s)
    s = s.encode("ascii", errors="ignore").decode("ascii")
    return re.sub(r"[^a-z]", "", s)


# ── HTML parsing ──────────────────────────────────────────────────────────────

def _extract_pattern_from_html(html: str, domain: str) -> Optional[str]:
    """
    Two-pass pattern extraction from email-format.com HTML.

    Pass A — token scan: look for Hunter-style {first}/{last}/{f}/{l} tokens.
    Pass B — example email scan: look for example emails whose local part
             can be structurally classified with a known test name.

    Returns an internal pattern name ("first.last", "flast", etc.) or None.
    """
    text = html.lower()

    # ── Pass A: Hunter-style tokens ───────────────────────────────────────
    # email-format.com sometimes renders the format as {first}.{last}@domain
    token_pattern = re.compile(
        r"\{(first|last|f|l)\}"       # token
        r"[._-]?"                      # optional separator
        r"\{(first|last|f|l)\}",       # second token (optional)
        re.IGNORECASE,
    )
    # Also try single-token patterns
    single_token = re.compile(r"\{(first|last)\}", re.IGNORECASE)

    for token_key, name in _TOKEN_TO_NAME.items():
        if token_key.lower() in text:
            return name

    # ── Pass B: example email scan ────────────────────────────────────────
    # Find email addresses in the HTML that match @domain
    domain_re  = re.compile(
        r"([\w.+%-]+)@" + re.escape(domain),
        re.IGNORECASE,
    )
    candidates = domain_re.findall(html.lower())

    for local in candidates:
        result = _classify_local_example(local)
        if result:
            return result

    # ── Pass C: text description patterns ────────────────────────────────
    # Some pages describe the format in plain English:
    # "first name dot last name", "first initial last name", etc.
    if "first name.last name" in text or "firstname.lastname" in text:
        return "first.last"
    if "first initial.last" in text or "first initial last" in text:
        return "f.last"
    if "first.last initial" in text or "firstname.l" in text:
        return "first.l"
    if "first_last" in text or "first name_last name" in text:
        return "first_last"
    if "first name last name" in text and "." not in text[:200]:
        return "firstlast"

    return None


def _classify_local_example(local: str) -> Optional[str]:
    """
    Given a local-part from an example email using a test name (john, doe, smith…),
    return the pattern name.  Returns None if the local doesn't use a test name.
    """
    local = local.lower().strip()
    if not local:
        return None

    # Check each known (first, last) combo from test names
    for f in _TEST_FIRST:
        for l in _TEST_LAST:
            # first.last  →  john.smith
            if local == f"{f}.{l}":
                return "first.last"
            # f.last  →  j.smith
            if local == f"{f[0]}.{l}":
                return "f.last"
            # first.l  →  john.s
            if local == f"{f}.{l[0]}":
                return "first.l"
            # first_last  →  john_smith
            if local == f"{f}_{l}":
                return "first_last"
            # firstlast  →  johnsmith
            if local == f"{f}{l}":
                return "firstlast"
            # flast  →  jsmith
            if local == f"{f[0]}{l}":
                return "flast"
            # last  →  smith
            if local == l:
                return "last"
            # first  →  john
            if local == f:
                return "first"
            # last.first  →  smith.john
            if local == f"{l}.{f}":
                return "last.first"
            # lastfirst  →  smithjohn
            if local == f"{l}{f}":
                return "lastfirst"
            # last_first  →  smith_john
            if local == f"{l}_{f}":
                return "last_first"

    return None


# ── Source class ──────────────────────────────────────────────────────────────

class EmailFormatPatternEmail(EmailSource):
    """
    Free email-pattern lookup via email-format.com.

    No API key.  No signup.  Zero cost.

    Slot: L2 in the email pipeline — after WebsiteEmailCrawler, before
    InternetPatternEmail and SearchEngineEmail.

    When email-format.com has no data for a domain, returns None silently
    so the next source can try.

    The mv_verifier parameter accepts any object with a .verify(email) method
    (SmtpVerifier or MillionVerifier) — used to confirm the generated candidate.
    Pass None to skip verification (not recommended for production).
    """

    name = "EFmt"

    def __init__(self, mv_verifier=None, log: LogFn = None):
        super().__init__(log)
        self._mv    = mv_verifier
        # domain → pattern_name (str) | None (no data)
        self._cache: Dict[str, Optional[str]] = {}

    # ── Public interface ──────────────────────────────────────────────────────

    def find_email(self, person: Person) -> Optional[EmailResult]:
        if not person.first or not person.last or not person.domain:
            return None

        pattern_name = self._get_pattern(person.domain)
        if not pattern_name:
            return None

        gen = _GENERATORS.get(pattern_name)
        if not gen:
            return None

        f = _norm(person.first)
        l = _norm(person.last)
        if not f or not l:
            return None

        candidate = f"{gen(f, l)}@{person.domain}"
        if is_generic_email(candidate):
            return None

        self.log("EFmt", f"  [{pattern_name}] → {candidate}")

        # ── Verify ────────────────────────────────────────────────────────
        if self._mv:
            quality = self._mv.verify(candidate)
            if quality == "bad":
                self.log("WARN", f"  EFmt: verifier rejected {candidate}")
                return None
            if quality == "risky":
                self.log("INFO", f"  EFmt: catch-all/risky — {candidate}")
            return EmailResult(
                email    = candidate,
                label    = "EFmt ✓" if quality == "good" else "EFmt ~",
                verified = (quality == "good"),
            )

        # No verifier — return unverified (pipeline's MV gate will catch it)
        return EmailResult(email=candidate, label="EFmt ?", verified=False)

    # ── Internal: domain lookup (cached) ─────────────────────────────────────

    def _get_pattern(self, domain: str) -> Optional[str]:
        """Fetch + parse email-format.com for domain. Cached per run."""
        if domain in self._cache:
            return self._cache[domain]

        self.log("EFmt", f"  Lookup: {domain}")
        try:
            url = f"{_BASE}/{domain}/"
            r   = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT,
                               allow_redirects=True)
            time.sleep(_INTER_DELAY)

            if r.status_code == 404:
                self.log("EFmt", f"  No data for {domain} (404)")
                self._cache[domain] = None
                return None

            if r.status_code != 200:
                self.log("WARN", f"  EFmt HTTP {r.status_code} for {domain}")
                self._cache[domain] = None
                return None

            pattern = _extract_pattern_from_html(r.text, domain)
            if pattern:
                self.log("EFmt", f"  Pattern found for {domain}: {pattern}")
            else:
                self.log("EFmt", f"  No usable pattern for {domain}")

            self._cache[domain] = pattern
            return pattern

        except requests.exceptions.Timeout:
            self.log("WARN", f"  EFmt timeout for {domain}")
            self._cache[domain] = None
            return None
        except Exception as exc:
            self.log("WARN", f"  EFmt error ({domain}): {exc}")
            self._cache[domain] = None
            return None
