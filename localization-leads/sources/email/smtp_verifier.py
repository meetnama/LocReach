"""
sources/email/smtp_verifier.py — Free SMTP-based email verifier

Replaces MillionVerifier with zero cost and no API key.

NOTE: Full SMTP verification (port 25 handshake) requires port 25 to be open
on the host machine. Most ISPs and office networks block this. In that case
_smtp_check() returns None and the verifier falls back to DNS-only mode,
which still catches invalid domains, dead companies, and typos.

Two-layer verification:
  Layer 1 — DNS (always works): does the domain have an MX record?
             No MX → "bad". Catches typos, dead domains, made-up companies.
  Layer 2 — SMTP (needs port 25): does the specific mailbox exist?
             Port blocked → falls back to "risky" (domain is valid, mailbox unknown).

How it works
────────────
1. Resolve the domain's MX record → find which mail server handles email
2. Open a TCP connection to that server on port 25
3. Send SMTP handshake: EHLO → MAIL FROM → RCPT TO
4. Read the server's response code:
     250  → mailbox exists         → "good"
     550+ → mailbox not found      → "bad"
     4xx  → temporary / greylisted → "risky"
5. Send QUIT — no email is ever actually sent or delivered

Catch-all detection
───────────────────
Before checking the real email, we check a random obviously-invalid address
(e.g. xk9zz_invalid_abc@domain.com). If the server accepts that too, the
domain is a "catch-all" — it accepts everything regardless. In that case
we return "risky" (same behaviour as MillionVerifier).

Caching
───────
MX records and catch-all status are cached per domain for the run lifetime,
so the MX lookup + catch-all probe happen only ONCE per company regardless
of how many people are checked there.

Returns
───────
  "good"  — mailbox confirmed to exist
  "risky" — catch-all domain, greylisted, or ambiguous
  "bad"   — mailbox definitively rejected by the server
  None    — port 25 blocked, DNS failure, or other network error
"""

import re
import socket
import smtplib
import random
import string
import time
from typing import Optional, Dict, Tuple

try:
    import dns.resolver as _dns
    _DNS_AVAILABLE = True
except ImportError:
    _DNS_AVAILABLE = False

from sources.base import LogFn

# SMTP timeout per operation (seconds)
_TIMEOUT   = 10
# Our "sender" identity used in MAIL FROM — any valid-looking address works
_FROM_ADDR = "verify@locreach-check.com"
# Ports tried in order (25 = standard, 587 = submission fallback)
_PORTS     = [25, 587]


def _random_local() -> str:
    """Generate an obviously-fake local part for catch-all detection."""
    chars = string.ascii_lowercase + string.digits
    return "zz_" + "".join(random.choices(chars, k=10)) + "_invalid"


def _mx_host(domain: str) -> Optional[str]:
    """Return the highest-priority MX hostname for domain, or None."""
    if not _DNS_AVAILABLE:
        return None
    try:
        records = _dns.resolve(domain, "MX", lifetime=8)
        best    = sorted(records, key=lambda r: r.preference)[0]
        return str(best.exchange).rstrip(".")
    except Exception:
        return None


def _smtp_check(mx: str, email: str, port: int = 25) -> Optional[str]:
    """
    Open an SMTP connection, probe one RCPT TO, return result string.

    Returns: "good" | "bad" | "risky" | None (connection failed)
    """
    try:
        smtp = smtplib.SMTP(timeout=_TIMEOUT)
        smtp.connect(mx, port)
        smtp.ehlo_or_helo_if_needed()
        smtp.mail(_FROM_ADDR)
        code, _ = smtp.rcpt(email)
        try:
            smtp.quit()
        except Exception:
            pass

        if code == 250:
            return "good"
        if code in (550, 551, 552, 553, 554):
            return "bad"
        # 4xx = temporary rejection / greylisting
        return "risky"

    except (socket.timeout, smtplib.SMTPConnectError,
            smtplib.SMTPServerDisconnected, ConnectionRefusedError,
            OSError):
        return None   # port blocked or unreachable
    except smtplib.SMTPRecipientsRefused:
        return "bad"
    except Exception:
        return "risky"


class SmtpVerifier:
    """
    Drop-in replacement for MillionVerifier — free, no API key.

    Usage:
        verifier = SmtpVerifier(log=self._log)
        quality  = verifier.verify("name@company.com")
        # Returns "good" | "risky" | "bad" | None
    """

    def __init__(self, log: LogFn = None):
        self._log: LogFn = log or (lambda tag, msg: None)
        # domain → (mx_host | None, is_catch_all | None)
        self._domain_cache: Dict[str, Tuple[Optional[str], Optional[bool]]] = {}

    def verify(self, email: str) -> Optional[str]:
        """
        Verify a single email address.

        Layer 1 (DNS)  — always runs: no MX record → "bad"
        Layer 2 (SMTP) — runs if port 25 is open: mailbox probe → "good"/"bad"/"risky"
        Fallback       — port 25 blocked: domain is valid → "risky"

        Returns:
          "good"  — mailbox confirmed deliverable via SMTP
          "risky" — valid domain but mailbox unconfirmed (port blocked or catch-all)
          "bad"   — domain has no MX record, or SMTP confirmed mailbox missing
          None    — invalid email format or DNS completely unreachable
        """
        if not email or "@" not in email:
            return None

        domain = email.split("@")[1].lower()

        # ── Layer 1: DNS check ────────────────────────────────────────────────
        mx = _mx_host(domain)
        if mx is None:
            self._log("INFO", f"  SMTP: no MX for {domain} → bad")
            return "bad"   # domain can't receive email at all

        # ── Port-blocked fast-path (cached after first timeout) ───────────────
        # Once we know a domain's SMTP port is unreachable, skip all future
        # connection attempts for that domain — return "risky" instantly.
        if self._domain_cache.get(domain) == ("__blocked__", None):
            return "risky"

        # ── Layer 2: SMTP check ───────────────────────────────────────────────
        # Check for catch-all first (cached per domain)
        _, is_catchall = self._domain_info(domain)

        if is_catchall:
            return "risky"

        # Short-circuit if domain_info detected port block
        if self._domain_cache.get(domain) == ("__blocked__", None):
            return "risky"

        result = self._check_with_fallback(mx, email)

        if result is None:
            # Port blocked — cache so future calls skip connection attempts
            self._domain_cache[domain] = ("__blocked__", None)
            self._log("INFO", f"  SMTP: port blocked for {domain} → risky (cached)")
            return "risky"

        self._log("INFO", f"  SMTP verify {email} → {result}")
        return result

    def is_sendable(self, email: str) -> bool:
        return self.verify(email) in ("good", "risky")

    # ── Internal ──────────────────────────────────────────────────────────────

    def _domain_info(self, domain: str) -> Tuple[Optional[str], Optional[bool]]:
        """
        Returns (mx_host, is_catch_all) — cached per domain.
        mx_host = None means this domain can't be reached.
        """
        if domain in self._domain_cache:
            return self._domain_cache[domain]

        mx = _mx_host(domain)
        if not mx:
            self._domain_cache[domain] = (None, None)
            return None, None

        # Catch-all probe with an obviously fake address
        fake   = f"{_random_local()}@{domain}"
        result = self._check_with_fallback(mx, fake)

        if result is None:
            # Port blocked — cache the blocked status so verify() fast-paths
            self._domain_cache[domain] = ("__blocked__", None)
            return None, None

        is_catchall = (result == "good")
        if is_catchall:
            self._log("INFO", f"  SMTP: {domain} is catch-all → risky")

        self._domain_cache[domain] = (mx, is_catchall)
        return mx, is_catchall

    def _check_with_fallback(self, mx: str, email: str) -> Optional[str]:
        """Try port 25 first, fall back to 587."""
        for port in _PORTS:
            result = _smtp_check(mx, email, port)
            if result is not None:
                return result
            time.sleep(0.3)
        return None   # all ports blocked
