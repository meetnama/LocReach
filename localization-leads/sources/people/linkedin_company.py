"""
sources/people/linkedin_company.py — scrape a company's LinkedIn /people page
using the shared undetected-Chrome driver.

Secondary people source for Step 3. Returns Person objects (no title filter
applied here — caller filters based on company_type via title_filter.passes()).

LinkedIn shows a login wall to non-logged-in users for full profile lists,
but the /people page often renders a small grid (8-15 profiles) of public
employees that we CAN scrape. If the wall blocks us, this returns [] silently
and the X-Ray source carries the load.
"""
from __future__ import annotations

import os
import re
import time
from typing import List

from sources.base import Company, Person
from sources.utils import _uc_lock, _get_uc_driver

# ── LinkedIn auto-login ────────────────────────────────────────────────────────

_li_session_active = False   # module-level flag — resets when app restarts

# How long to wait for the user to complete manual login / 2FA (seconds).
# The window stays open and visible the whole time.
_LI_LOGIN_WAIT_SEC = 300   # 5 minutes


def _is_linkedin_logged_in(driver) -> bool:
    """Return True if the current URL looks like a logged-in LinkedIn page."""
    url = (driver.current_url or "").lower()
    return any(k in url for k in ("feed", "mynetwork", "jobs", "messaging", "notifications"))


def ensure_linkedin_login(log=None) -> bool:
    """
    Ensure the shared Chrome driver is logged into LinkedIn.

    Strategy:
      1. Navigate to /feed — if already logged in (persistent profile cookie),
         return True immediately.
      2. Navigate to /login and fill credentials via JavaScript (more reliable
         than Selenium send_keys against LinkedIn's hardened forms).
      3. Click Submit and wait up to 10 s for redirect.
      4. If login succeeded → mark session active, return True.
      5. If a security checkpoint / 2FA / CAPTCHA is shown OR credentials
         were not accepted → keep the Chrome window open on the login page
         and poll every 3 s for up to _LI_LOGIN_WAIT_SEC seconds.
         The user can complete login manually in that window.
      6. Once the feed URL is detected, mark session active and return True.
      7. If the timeout expires without login → return False (Step 3 continues
         without LinkedIn /people scraping).

    The persistent Chrome profile (`.chrome_profile/LocReach`) saves the session
    cookie after the first successful login, so step 1 succeeds on all
    subsequent runs.
    """
    global _li_session_active

    if _li_session_active:
        return True

    email    = os.getenv("LINKEDIN_EMAIL",    "").strip()
    password = os.getenv("LINKEDIN_PASSWORD", "").strip()

    def _log(msg: str) -> None:
        if log:
            log("LI-LOGIN", msg)

    try:
        with _uc_lock:
            driver = _get_uc_driver()
            if driver is None:
                _log("  Chrome unavailable — skipping LinkedIn login")
                return False

            # ── 1. Check if already logged in (persistent cookie) ──────────────
            _log("  Checking LinkedIn session…")
            try:
                driver.set_page_load_timeout(15)
                driver.get("https://www.linkedin.com/feed/")
            except Exception:
                try:
                    driver.execute_script("window.stop();")
                except Exception:
                    pass

            time.sleep(2.5)
            if _is_linkedin_logged_in(driver):
                _log("  ✅ Already logged in (persistent session)")
                _li_session_active = True
                return True

            # ── 2. Navigate to login page ──────────────────────────────────────
            _log(f"  Not logged in — navigating to login page for {email or '(no credentials)'}")
            try:
                driver.set_page_load_timeout(15)
                driver.get("https://www.linkedin.com/login")
            except Exception:
                try:
                    driver.execute_script("window.stop();")
                except Exception:
                    pass

            time.sleep(3)   # let the form render fully

            # ── 3. Fill credentials via JavaScript ─────────────────────────────
            filled = False
            if email and password:
                try:
                    filled = driver.execute_script(
                        """
                        var em = document.getElementById('username');
                        var pw = document.getElementById('password');
                        if (!em || !pw) return false;
                        // Set value via native input value setter so React/Vue
                        // event handlers fire correctly
                        var nativeSetter = Object.getOwnPropertyDescriptor(
                            window.HTMLInputElement.prototype, 'value').set;
                        nativeSetter.call(em, arguments[0]);
                        em.dispatchEvent(new Event('input', {bubbles:true}));
                        nativeSetter.call(pw, arguments[1]);
                        pw.dispatchEvent(new Event('input', {bubbles:true}));
                        return true;
                        """,
                        email, password,
                    )
                except Exception as exc:
                    _log(f"  JS form fill error: {exc}")

            if filled:
                _log("  Credentials filled via JS — submitting…")
                try:
                    driver.execute_script(
                        """
                        var btn = document.querySelector('button[type=submit]');
                        if (btn) btn.click();
                        """
                    )
                except Exception as exc:
                    _log(f"  Submit click error: {exc}")

                # Wait for redirect
                for _ in range(10):
                    time.sleep(1)
                    if _is_linkedin_logged_in(driver):
                        _log("  ✅ Logged in successfully via credentials")
                        _li_session_active = True
                        return True
                    url = (driver.current_url or "").lower()
                    if "login" not in url and "feed" not in url:
                        break   # redirected somewhere else — fall through to manual wait
            else:
                _log("  Could not fill credentials — waiting for manual login in Chrome window")

            # ── 4. Manual login wait ───────────────────────────────────────────
            # Keep the Chrome window open and visible on the login/checkpoint
            # page. Poll every 3 s until the user completes login or timeout.
            current_url = (driver.current_url or "").lower()
            if "checkpoint" in current_url or "challenge" in current_url:
                _log("  ⚠️  Security checkpoint detected — please complete it in the Chrome window")
            elif "login" in current_url or not _is_linkedin_logged_in(driver):
                _log(f"  ⏳ Waiting for manual login in Chrome window (up to {_LI_LOGIN_WAIT_SEC}s)…")

            deadline = time.time() + _LI_LOGIN_WAIT_SEC
            while time.time() < deadline:
                time.sleep(3)
                try:
                    if _is_linkedin_logged_in(driver):
                        _log("  ✅ Login detected — continuing")
                        _li_session_active = True
                        return True
                except Exception:
                    pass

            _log(f"  ❌ Login not completed within {_LI_LOGIN_WAIT_SEC}s — continuing without auth")
            return False

    except Exception as exc:
        if log:
            log("LI-LOGIN", f"  Unexpected error: {exc}")
        return False


# ── JS payload — runs inside Chrome to harvest profile cards ──────────────────
# We don't care about LinkedIn's exact DOM structure. We just walk every
# anchor that points to a /in/<slug> profile and collect the visible text in
# its nearest ancestor card. The caller then heuristically separates name
# from title.
_LI_PEOPLE_JS = r"""
(function() {
    const out  = [];
    const seen = new Set();

    const anchors = document.querySelectorAll('a[href*="/in/"]');
    for (const a of anchors) {
        let href = a.href || a.getAttribute('href') || '';
        const m  = href.match(/^(https?:\/\/[^\/]*linkedin\.com\/in\/[^\/?#]+)/i);
        if (!m) continue;
        const url = m[1];
        if (seen.has(url)) continue;
        seen.add(url);

        // Climb up to the nearest card-like ancestor (li/div with class)
        let card = a.closest('li, article, [data-test-id], .org-people-profile-card, .artdeco-entity-lockup');
        if (!card) card = a.parentElement && a.parentElement.parentElement;
        if (!card) card = a;

        // Collect short text fragments visible in the card
        const fragments = [];
        for (const el of card.querySelectorAll('span, div, p, h1, h2, h3, h4')) {
            const t = (el.innerText || '').replace(/\s+/g, ' ').trim();
            if (!t) continue;
            if (t.length < 2 || t.length > 100) continue;
            if (fragments.includes(t))            continue;
            fragments.push(t);
            if (fragments.length >= 8) break;
        }

        out.push({ url: url, fragments: fragments });
        if (out.length >= 40) break;
    }
    return out;
})();
"""


_LI_LOGIN_RE = re.compile(
    r'(login|authwall|checkpoint|signup|uas/login)',
    re.IGNORECASE,
)

_NAME_HINT_RE = re.compile(
    r"^[A-ZÁÉÍÓÚÀÂÄÈÊËÎÏÔÙÛÜÆŒÇÑ][a-záéíóúàâäèêëîïôùûüæœçñ'\-]+"
    r"(?:\s+[A-ZÁÉÍÓÚÀÂÄÈÊËÎÏÔÙÛÜÆŒÇÑ][a-záéíóúàâäèêëîïôùûüæœçñ'\-]+){1,3}$"
)

_TITLE_HINT_RE = re.compile(
    r"\b(manager|director|head|vp|vice president|ceo|coo|cto|cfo|founder|"
    r"owner|engineer|specialist|coordinator|lead|partner|president|"
    r"chief|officer|consultant|analyst|architect|developer|designer|"
    r"strategist|principal|associate|executive|administrator|"
    r"linguist|translator|interpreter|reviewer|editor|content|"
    r"localization|localisation|translation|language|globalization)\b",
    re.IGNORECASE,
)

# Junk text that LinkedIn sprinkles around profile cards
_JUNK_PHRASES = {
    "see profile", "view profile", "connect", "follow", "message",
    "show more", "show less", "1st", "2nd", "3rd",
    "1st degree connection", "2nd degree connection",
    "premium", "open to work", "linkedin",
}

# Last words that indicate a company name fragment, not a person name
_CORP_SUFFIX_WORDS = {
    "inc", "inc.", "llc", "ltd", "ltd.", "gmbh", "corp", "corporation",
    "limited", "company", "group", "holding", "holdings",
    "sa", "sas", "sarl", "ag", "bv", "nv", "plc", "sl", "srl", "kft",
}


def _clean_fragment(frag: str) -> str:
    """Strip pronouns, parentheticals, and trailing punctuation."""
    s = re.sub(r"\s*\([^)]*\)", "", frag).strip()
    s = re.sub(r"^\s*[•·∙∘]\s*", "", s).strip()
    return s.strip(" ,;:")


def _parse_name_and_title(fragments: list[str]) -> tuple[str, str]:
    """
    Given fragments harvested from a single profile card, pick the best
    candidate for `name` and `title`. Returns ("", "") if no plausible
    name was found.
    """
    name  = ""
    title = ""

    cleaned = []
    for f in fragments:
        c = _clean_fragment(f)
        if not c:
            continue
        if c.lower() in _JUNK_PHRASES:
            continue
        cleaned.append(c)

    # Pass 1 — find the first fragment that looks like a person name
    for c in cleaned:
        if _NAME_HINT_RE.match(c):
            # Avoid grabbing "LinkedIn Member" / "Member" / etc.
            if c.lower() in {"linkedin member", "linkedin user", "member"}:
                continue
            # Reject company-name fragments like "Slideshare Inc", "Acme Ltd"
            last_word = c.split()[-1].lower().rstrip(".,")
            if last_word in _CORP_SUFFIX_WORDS:
                continue
            name = c
            break

    # Pass 2 — find the first fragment that looks like a job title
    for c in cleaned:
        if c == name:
            continue
        if _TITLE_HINT_RE.search(c):
            title = c
            break

    # Fallback — if we have a name but no title, take the next non-name
    # fragment that's short enough to plausibly be a role
    if name and not title:
        for c in cleaned:
            if c == name:
                continue
            if 5 < len(c) < 80:
                title = c
                break

    return name, title


def find_people_from_linkedin_page(
    company: Company,
    log=None,
    max_people: int = 15,
) -> List[Person]:
    """
    Scrape the /people sub-page of a LinkedIn company profile.
    Returns up to `max_people` Person objects, or [] on any error / login
    wall. Title filtering is NOT applied here — the caller does that.
    """
    def _log(tag: str, msg: str) -> None:
        if log:
            log(tag, msg)

    li_url = (company.linkedin_url or "").strip()
    if not li_url or "linkedin.com/company/" not in li_url:
        _log("LI-PG", f"  [LinkedIn page] no company URL for {company.domain} — skipping")
        return []

    people_url = li_url.rstrip("/") + "/people"
    _log("LI-PG", f"  [LinkedIn page] fetching {people_url}")

    raw: list = []
    try:
        with _uc_lock:
            driver = _get_uc_driver()
            if driver is None:
                _log("LI-PG", "  [LinkedIn page] Chrome unavailable")
                return []

            try:
                driver.set_page_load_timeout(20)   # LinkedIn React pages can take 12-20s
                driver.get(people_url)
            except Exception as exc:
                # Timeout or navigation error — call window.stop() to freeze
                # the DOM in place, then CONTINUE to extract whatever loaded.
                # Do NOT return [] here: the people cards often render before
                # the full page load completes, so partial DOM still has results.
                _log("LI-PG", f"  [LinkedIn page] load timeout — extracting partial DOM ({exc.__class__.__name__})")
                try:
                    driver.execute_script("window.stop();")
                except Exception:
                    pass

            # Wait for React to mount the people cards (increased from 1.5s)
            time.sleep(3)

            current_url = (driver.current_url or "").lower()
            if _LI_LOGIN_RE.search(current_url):
                _log("LI-PG", f"  [LinkedIn page] login wall hit ({current_url[:60]}) — skipping")
                return []

            try:
                raw = driver.execute_script(_LI_PEOPLE_JS) or []
            except Exception as exc:
                _log("LI-PG", f"  [LinkedIn page] JS exec error: {exc}")
                raw = []
    except Exception as exc:
        _log("LI-PG", f"  [LinkedIn page] error: {exc}")
        return []

    if not raw:
        _log("LI-PG", "  [LinkedIn page] 0 raw cards")
        return []

    found: List[Person] = []
    seen_urls: set     = set()

    for item in raw[:max_people * 2]:   # extra headroom for bad cards
        url = (item.get("url") or "").strip()
        if not url or url in seen_urls:
            continue
        if "/in/" not in url:
            continue
        seen_urls.add(url)

        fragments = item.get("fragments") or []
        name, title = _parse_name_and_title(fragments)
        if not name:
            continue

        parts = name.split()
        if len(parts) < 2:
            continue
        first = parts[0]
        last  = " ".join(parts[1:])

        found.append(Person(
            first         = first,
            last          = last,
            title         = (title or "")[:80],
            domain        = company.domain,
            company_name  = company.name,
            linkedin_url  = url,
            people_source = "linkedin_page",
        ))

        if len(found) >= max_people:
            break

    _log("LI-PG", f"  [LinkedIn page] extracted {len(found)} people")
    return found
