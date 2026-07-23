"""
sources/email/website_crawler.py — Email source: company site crawler

Layer 1 of the email pipeline — completely free, no API keys.

Crawls a company's contact / about / team pages and extracts any email
address directly exposed on the site (HTML text, obfuscated with [at],
or embedded in PDF links).

Design decisions
────────────────
• Cache by domain: the scrape runs once per company regardless of how
  many people are processed from it.
• Name-match first: if an email's local-part contains the person's first
  or last name, return it immediately with a "Site ✓" label.
• Single-email short-circuit: if only one company email is found across
  all probed pages, return it — it's almost certainly the contact address.
• Multiple ambiguous emails → None (let paid layers handle it).
• PDF scanning: checks up to 3 linked PDFs for embedded emails.
  Requires pdfplumber (optional — silently skipped if not installed).
"""
import re
import time
import requests
from typing import Optional, List, Dict
from urllib.parse import urljoin

from sources.base import EmailSource, Person, EmailResult, LogFn
from sources.utils import clean_email, is_personal_email, is_institutional_email, is_generic_email


# ── Pages probed in order; crawl stops as soon as emails are found ─────────────
_CONTACT_PATHS = [
    "/contact",      "/contact-us",   "/contact_us",   "/contactus",
    "/about",        "/about-us",     "/about_us",
    "/team",         "/our-team",     "/meet-the-team",
    "/staff",        "/people",       "/leadership",
    "/who-we-are",   "/management",   "/directors",
    "/founders",     "/executives",   "/our-people",
]

# Obfuscation patterns: "name [at] domain.com", "name(at)domain", "name AT domain"
_OBFUSCATION_RE = re.compile(
    r'([A-Za-z0-9._%+-]+)\s*[\[\(]?\s*(?:at|AT|@)\s*[\]\)]?\s*([A-Za-z0-9.-]+\.[A-Za-z]{2,})',
)


def _domain_email_re(domain: str) -> re.Pattern:
    return re.compile(
        r'\b([A-Za-z0-9._%+-]+@' + re.escape(domain) + r')\b',
        re.IGNORECASE,
    )


def _fetch(url: str) -> str:
    """GET url → stripped plain text; empty string on any failure."""
    try:
        r = requests.get(
            url, timeout=10,
            headers={"User-Agent": "Mozilla/5.0 (compatible; LeadBot/1.0)"},
            allow_redirects=True,
        )
        if r.status_code != 200:
            return ""
        html = r.text
        # Remove noise blocks
        for tag in ("script", "style", "noscript", "nav", "footer", "head"):
            html = re.sub(
                rf'<{tag}[^>]*>.*?</{tag}>', ' ', html,
                flags=re.DOTALL | re.IGNORECASE,
            )
        text = re.sub(r'<[^>]+>', ' ', html)
        text = re.sub(r'\s+',     ' ', text)
        return text
    except Exception:
        return ""


def _fetch_pdf_emails(url: str, domain: str) -> List[str]:
    """Download PDF and extract emails matching domain. Returns [] if pdfplumber absent."""
    try:
        import pdfplumber, io
        r = requests.get(
            url, timeout=15,
            headers={"User-Agent": "Mozilla/5.0 (compatible; LeadBot/1.0)"},
        )
        if r.status_code != 200:
            return []
        if "pdf" not in r.headers.get("content-type", "").lower():
            return []
        pattern = _domain_email_re(domain)
        found = []
        with pdfplumber.open(io.BytesIO(r.content)) as pdf:
            for page in pdf.pages[:5]:
                text = page.extract_text() or ""
                for m in pattern.findall(text):
                    e = clean_email(m)
                    if e not in found:
                        found.append(e)
        return found
    except Exception:
        return []


def _extract_emails(text: str, domain: str) -> List[str]:
    """Extract all @domain emails from plain text, including obfuscated forms."""
    found: List[str] = []
    seen:  set        = set()
    pattern = _domain_email_re(domain)

    # 1. Standard regex
    for m in pattern.findall(text):
        e = clean_email(m)
        if e and e not in seen:
            seen.add(e); found.append(e)

    # 2. Obfuscated: "name [at] domain.com"
    for m in _OBFUSCATION_RE.finditer(text):
        local = m.group(1).strip()
        host  = m.group(2).strip().lower()
        if host == domain:
            e = clean_email(f"{local}@{host}")
            if e and e not in seen:
                seen.add(e); found.append(e)

    return found


class WebsiteEmailCrawler(EmailSource):
    """
    Crawls company website pages for publicly exposed email addresses.

    Layer 1 — free, no API needed.
    Cache: one domain crawl per pipeline run, reused for all people
    discovered at the same company.
    """
    name = "Site"

    def __init__(self, log: LogFn = None):
        super().__init__(log)
        # domain → sorted list of unique emails found (empty list = crawled, nothing found)
        self._cache: Dict[str, List[str]] = {}

    # ── Public interface ──────────────────────────────────────────────────────

    def find_email(self, person: Person) -> Optional[EmailResult]:
        domain = person.domain
        raw_emails = self._crawl(domain)

        # Drop role/generic addresses (info@, hello@, support@, etc.) — these are
        # company inboxes, not personal contacts.
        emails = [e for e in raw_emails if not is_generic_email(e)]

        if not emails:
            return None

        first_l = person.first.lower()
        last_l  = person.last.lower()

        # 1. Name match in local-part  → highest confidence
        for email in emails:
            local = email.split("@")[0].lower()
            if (first_l and first_l in local) or (last_l and last_l in local):
                self.log("SITE", f"  Name match → {email}")
                return EmailResult(email=email, label="Site ✓")

        # 2. Exactly one personal email → return it
        if len(emails) == 1:
            self.log("SITE", f"  Single personal email → {emails[0]}")
            return EmailResult(email=emails[0], label="Site")

        # 3. Multiple ambiguous emails → can't pick safely
        self.log("SITE", f"  {len(emails)} personal emails on {domain} — ambiguous")
        return None

    # ── Internal crawl (cached) ───────────────────────────────────────────────

    def _crawl(self, domain: str) -> List[str]:
        if domain in self._cache:
            return self._cache[domain]

        self.log("SITE", f"  Crawling {domain} for exposed emails …")
        found: List[str] = []

        # ── Phase 1: probe contact / about / team paths ───────────────────────
        for path in _CONTACT_PATHS:
            url  = f"https://{domain}{path}"
            text = _fetch(url)
            if not text:
                time.sleep(0.2)
                continue
            extracted = _extract_emails(text, domain)
            page_found = []
            for e in extracted:
                if not is_personal_email(e) and not is_institutional_email(e) and e not in found:
                    page_found.append(e)
            found.extend(page_found)
            # Only stop early when at least one NON-GENERIC email was found.
            # If the page only had info@/hello@/etc., continue to the next path —
            # a personal email may appear on /team or /about even if /contact has
            # only a generic address.
            if any(not is_generic_email(e) for e in page_found):
                break
            time.sleep(0.3)

        # ── Phase 2: homepage fallback ────────────────────────────────────────
        if not found:
            text = _fetch(f"https://{domain}/")
            for e in _extract_emails(text, domain):
                if not is_personal_email(e) and not is_institutional_email(e) and e not in found:
                    found.append(e)

        # ── Phase 3: linked PDFs (up to 3) ───────────────────────────────────
        if not found:
            try:
                r = requests.get(
                    f"https://{domain}/", timeout=10,
                    headers={"User-Agent": "Mozilla/5.0 (compatible; LeadBot/1.0)"},
                )
                if r.status_code == 200:
                    pdf_hrefs = re.findall(
                        r'href=["\']([^"\']*\.pdf)["\']', r.text, re.IGNORECASE,
                    )
                    for href in pdf_hrefs[:3]:
                        pdf_url = urljoin(f"https://{domain}/", href)
                        for e in _fetch_pdf_emails(pdf_url, domain):
                            if e not in found:
                                found.append(e)
                        if found:
                            break
                        time.sleep(0.5)
            except Exception:
                pass

        self._cache[domain] = found
        if found:
            self.log("SITE", f"  Found {len(found)} email(s) on {domain}")
        else:
            self.log("SITE", f"  No public emails found on {domain}")
        return found
