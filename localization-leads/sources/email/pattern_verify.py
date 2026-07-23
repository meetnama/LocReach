"""
sources/email/pattern_verify.py — Brute-force email pattern verification

Strategy
────────
Instead of searching the internet for a person's email (which depends on it
being publicly indexed), this source generates every common email pattern for
the person's name + domain, then verifies each one against the mail server
via a mailbox-level SMTP check.  No search engine required.

Algorithm
─────────
  1. Check if the domain is a catch-all (accepts everything).
       → If yes: return the most-common pattern as "risky" immediately.
         No point trying all patterns — the server says yes to everything.
  2. Try each pattern in order of global frequency (first.last first, etc.).
  3. Verify each candidate via the injected verifier.
       → "good"  : mailbox confirmed → return immediately, stop.
       → "bad"   : mailbox rejected  → try next pattern.
       → "risky" : ambiguous         → keep as fallback, try next.
       → None    : verifier error    → skip.
  4. If a "good" hit was found, return it.
     If only "risky" hits, return the first one (best guess).
     If nothing, return None.

Pattern order (global frequency, ~100M company emails analysed)
───────────────────────────────────────────────────────────────
  first.last   35%   john.smith
  flast        22%   jsmith
  first        12%   john
  f.last        8%   j.smith
  firstlast     7%   johnsmith
  last          5%   smith
  first_last    4%   john_smith
  last.first    3%   smith.john
  first.l       2%   john.s
  lastfirst     1%   smithjohn
  last_first    1%   smith_john
  f_last       0.5%  j_smith

Cost model
──────────
  Average patterns tried per person  ≈ 3  (first.last + flast cover 57%)
  Catch-all domains                  → 1 verifier call (probe) + 0 pattern calls
  Verifier cost (MillionVerifier)    ≈ $0.01 / call → ~$0.03 / person on average

Requirements
────────────
  A mailbox-level verifier — DNS-only is NOT sufficient.
  Pass any object with a .verify(email) → "good" | "risky" | "bad" | None
  Compatible with: MillionVerifier, NeverBounce, ZeroBounce, SmtpVerifier
  (SmtpVerifier works only when port 25 is open on the host machine.)
"""

import unicodedata
import re
import time
from typing import Optional, List, Tuple

from sources.base import EmailSource, Person, EmailResult, LogFn
from sources.utils import is_generic_email


def _resolve_email_domain(domain: str, log=None) -> str:
    """
    Subdomains (e.g. localization.saudisoft.com, mail.company.com) rarely have
    MX records — email is handled by the root domain instead.

    Walk up the domain hierarchy until we find a domain with an MX record.
    Returns the original domain if no better one is found (safe fallback).
    """
    from sources.email.smtp_verifier import _mx_host
    parts = domain.split(".")
    # Try the full domain first, then progressively strip subdomains.
    # Stop when we're down to just SLD + TLD (2 parts).
    # range(len(parts) - 1) gives indices 0 … len-2, so the last
    # candidate is always parts[-2] + "." + parts[-1] = root domain.
    for i in range(len(parts) - 1):
        candidate = ".".join(parts[i:])
        mx = _mx_host(candidate)
        if mx:
            if candidate != domain and log:
                log("PatVfy", f"  Subdomain {domain!r} has no MX — using {candidate!r} for email")
            return candidate
    return domain

# ── Pattern registry ──────────────────────────────────────────────────────────
# Each entry: (label, generator_fn)
# Ordered by descending global frequency — highest hit-rate first.
PATTERNS: List[Tuple[str, callable]] = [
    ("first.last",  lambda f, l: f"{f}.{l}"),
    ("flast",       lambda f, l: f"{f[0]}{l}"),
    ("first",       lambda f, l: f),
    ("f.last",      lambda f, l: f"{f[0]}.{l}"),
    ("firstlast",   lambda f, l: f"{f}{l}"),
    ("last",        lambda f, l: l),
    ("first_last",  lambda f, l: f"{f}_{l}"),
    ("last.first",  lambda f, l: f"{l}.{f}"),
    ("first.l",     lambda f, l: f"{f}.{l[0]}"),
    ("lastfirst",   lambda f, l: f"{l}{f}"),
    ("last_first",  lambda f, l: f"{l}_{f}"),
    ("f_last",      lambda f, l: f"{f[0]}_{l}"),
]


def _norm(s: str) -> str:
    """ASCII-fold + strip non-alpha (handles accented names)."""
    s = s.lower().strip()
    s = unicodedata.normalize("NFKD", s)
    s = s.encode("ascii", errors="ignore").decode("ascii")
    return re.sub(r"[^a-z]", "", s)


class PatternVerifyEmail(EmailSource):
    """
    Brute-force email pattern verifier — no search engine required.

    Tries all common email patterns for a person in frequency order,
    verifies each via SMTP, and returns the first confirmed deliverable.

    Wire it as L2 in the pipeline (after WebsiteEmailCrawler, before
    SearchEngineEmail).  Requires a mailbox-level verifier — pass the
    SmtpVerifier instance used by the rest of the pipeline.

    Usage:
        from sources.email.pattern_verify import PatternVerifyEmail
        from sources.email.smtp_verifier import SmtpVerifier

        verifier = SmtpVerifier()
        source = PatternVerifyEmail(verifier=verifier)
    """

    name = "PatVfy"

    def __init__(self, verifier, log: LogFn = None):
        """
        verifier : any object with .verify(email) → "good"|"risky"|"bad"|None
        """
        super().__init__(log)
        self._verifier = verifier
        # Cache catch-all status per domain — probe once, reuse for all persons
        self._catchall_cache: dict = {}   # domain → bool | None

    def find_email(self, person: Person) -> Optional[EmailResult]:
        if not person.first or not person.last or not person.domain:
            return None
        if not self._verifier:
            return None

        f = _norm(person.first)
        l = _norm(person.last)
        if not f or not l:
            return None

        # ── Subdomain MX fallback ─────────────────────────────────────────────
        # Subdomains (e.g. localization.saudisoft.com) rarely have MX records.
        # Email is delivered to the root domain instead.
        domain = person.domain
        domain = _resolve_email_domain(domain, self.log)

        # ── Step 1: catch-all check (cached per domain) ───────────────────────
        is_catchall = self._get_catchall(domain)

        if is_catchall:
            # Server accepts everything — SMTP can't distinguish real mailboxes.
            # Return the most common pattern as a "risky" best-guess.
            candidate = f"{f}.{l}@{domain}"
            if not is_generic_email(candidate):
                self.log("PatVfy", f"  Catch-all domain — best-guess: {candidate}")
                return EmailResult(email=candidate, label="PatVfy ~", verified=False)
            return None

        # ── Step 2: try patterns in frequency order ───────────────────────────
        risky_fallback: Optional[EmailResult] = None
        all_bad = True   # track whether EVERY probe came back "bad"

        for pattern_name, gen in PATTERNS:
            candidate = f"{gen(f, l)}@{domain}"

            if is_generic_email(candidate):
                continue   # skip role-address collisions (e.g. "last" = "info")

            self.log("PatVfy", f"  [{pattern_name}] trying {candidate}")

            try:
                quality = self._verifier.verify(candidate)
            except Exception as exc:
                self.log("WARN", f"  PatVfy verifier error: {exc}")
                quality = None

            if quality != "bad":
                all_bad = False   # server responded with something other than hard reject

            if quality == "good":
                self.log("PatVfy", f"  ✅ Confirmed: {candidate} [{pattern_name}]")
                return EmailResult(
                    email    = candidate,
                    label    = f"PatVfy ✓",
                    verified = True,
                )

            if quality == "risky" and risky_fallback is None:
                risky_fallback = EmailResult(
                    email    = candidate,
                    label    = f"PatVfy ~",
                    verified = False,
                )
                self.log("PatVfy", f"  ~ Risky (kept as fallback): {candidate}")

            # "bad" or None → try next pattern
            time.sleep(0.1)   # brief pause between verifier calls

        # ── Step 3: return best available result ──────────────────────────────
        if risky_fallback:
            self.log("PatVfy", f"  No confirmed hit — returning risky fallback")
            return risky_fallback

        # ── Step 4: directory-harvesting fallback ─────────────────────────────
        # If EVERY pattern returned "bad", the server likely uses directory-
        # harvesting protection (rejects ALL RCPT TO probes regardless of
        # whether the mailbox exists). Return first.last as an unverified guess
        # — it's the most common pattern (35%) and better than returning nothing.
        if all_bad:
            guess = f"{f}.{l}@{domain}"
            if not is_generic_email(guess):
                self.log("PatVfy", f"  ⚠ All probes rejected (harvesting protection?) — guessing {guess}")
                return EmailResult(email=guess, label="PatVfy ?", verified=False)

        return None

    # ── Internal ──────────────────────────────────────────────────────────────

    def _get_catchall(self, domain: str) -> Optional[bool]:
        """
        Returns True if domain is catch-all, False if not, None if unknown.
        Result is cached — the probe fires only once per domain per run.
        """
        if domain in self._catchall_cache:
            return self._catchall_cache[domain]

        self.log("PatVfy", f"  Catch-all probe: {domain}")

        # Use an obviously fake address as the probe
        fake = f"zz_xk9_notareal_person_xyz@{domain}"
        try:
            result = self._verifier.verify(fake)
        except Exception:
            result = None

        is_catchall = (result == "good")   # server accepted a fake address → catch-all
        self._catchall_cache[domain] = is_catchall

        if is_catchall:
            self.log("PatVfy", f"  {domain} is catch-all")
        else:
            self.log("PatVfy", f"  {domain} is NOT catch-all → will probe patterns")

        return is_catchall
