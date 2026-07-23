"""
sources/utils.py — Shared helper functions used across all sources.
"""
import re
import os
import time
import random
import atexit
import threading

from urllib.parse import urlparse, urlencode
from config import BLOCKED_DOMAINS, FREE_EMAIL_DOMAINS, RELEVANCE_KEYWORDS, TLD_COUNTRY, INDUSTRY_KEYWORDS


# ─────────────────────────────────────────────────────────────────────────────
# Google search via undetected-chromedriver
# ─────────────────────────────────────────────────────────────────────────────
# undetected-chromedriver patches Chrome at binary level to defeat Google's
# bot-detection — navigator.webdriver is never set, CDP is hidden, no
# "Chrome is being controlled by automated software" banner.
#
# One Chrome instance is reused for all search calls in the same process
# (closed automatically at exit). Runs headless by default so no window pops up.
#
# Persistent profile in <project>/.chrome_profile/LocReach/ — cookies and
# Google session accumulate across runs so the browser looks like a returning
# human user. Legacy LocHere* profiles are still tried as fallbacks.
#
# Set PLAYWRIGHT_HEADLESS=0 to show the Chrome window (debug only).
# ─────────────────────────────────────────────────────────────────────────────

_uc_lock      = threading.Lock()   # one search at a time
_uc_driver    = None               # shared Chrome instance
_captcha_flag = threading.Event()  # briefly set when CAPTCHA is detected (no human wait)

# After Google CAPTCHA: pause Google and use SearXNG/DDG until this timestamp
GOOGLE_CAPTCHA_COOLDOWN_SEC = 10 * 60  # 10 minutes — retry Google sooner; still long enough to clear most soft-blocks
_google_cooldown_until = 0.0
_google_cooldown_lock = threading.Lock()


class CaptchaHit(Exception):
    """Raised when Google shows a CAPTCHA — caller should fall back (no human wait)."""


def google_in_cooldown() -> bool:
    return time.time() < _google_cooldown_until


def google_cooldown_remaining() -> int:
    """Seconds left before Google may be tried again (0 if ready)."""
    return max(0, int(_google_cooldown_until - time.time()))


def trip_google_cooldown(seconds: int = GOOGLE_CAPTCHA_COOLDOWN_SEC) -> None:
    """Start / extend the Google CAPTCHA cooldown window."""
    global _google_cooldown_until
    with _google_cooldown_lock:
        _google_cooldown_until = max(_google_cooldown_until, time.time() + max(1, seconds))


def _get_uc_driver():
    """
    Return the shared undetected-Chrome driver, launching it if needed.
    Tries LocReach → LocReach_2 → LocReach_3, then legacy LocHere* profiles
    if an old session is still locked to those names.
    """
    global _uc_driver
    if _uc_driver is not None:
        return _uc_driver

    try:
        import undetected_chromedriver as uc
    except ImportError:
        print("⚠️  undetected-chromedriver not installed — run Install LocReach.bat")
        return None

    # Default headless (hidden). Opt in to a visible window with PLAYWRIGHT_HEADLESS=0.
    headless    = os.getenv("PLAYWRIGHT_HEADLESS", "1") != "0"
    profile_dir = os.path.normpath(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".chrome_profile")
    )
    os.makedirs(profile_dir, exist_ok=True)

    def _detect_chrome_major() -> int | None:
        import re as _re
        try:
            import winreg
            for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
                for sub in (
                    r"Software\Google\Chrome\BLBeacon",
                    r"Software\Wow6432Node\Google\Chrome\BLBeacon",
                ):
                    try:
                        with winreg.OpenKey(hive, sub) as k:
                            ver, _ = winreg.QueryValueEx(k, "version")
                            m = _re.search(r"^(\d+)\.", str(ver))
                            if m:
                                return int(m.group(1))
                    except OSError:
                        pass
        except ImportError:
            pass
        for base in (
            r"C:\Program Files\Google\Chrome\Application",
            r"C:\Program Files (x86)\Google\Chrome\Application",
        ):
            if not os.path.isdir(base):
                continue
            for entry in os.listdir(base):
                m = _re.match(r"^(\d+)\.\d+\.\d+\.\d+$", entry)
                if m and os.path.isdir(os.path.join(base, entry)):
                    return int(m.group(1))
        return None

    chrome_major = _detect_chrome_major()
    if chrome_major:
        print(f"🌐 [SEARCH] Detected Chrome {chrome_major} — fetching matching driver…")

    for profile_name in (
        "LocReach", "LocReach_2", "LocReach_3",
        "LocHere", "LocHere_2", "LocHere_3",  # legacy fallback
    ):
        try:
            options = uc.ChromeOptions()
            options.add_argument(f"--user-data-dir={profile_dir}")
            options.add_argument(f"--profile-directory={profile_name}")
            options.add_argument("--disable-infobars")
            options.add_argument("--no-first-run")
            options.add_argument("--no-default-browser-check")
            options.add_argument("--disable-background-networking")
            if headless:
                options.add_argument("--window-size=1920,1080")
                options.add_argument("--disable-gpu")
            else:
                options.add_argument("--start-maximized")

            driver = uc.Chrome(
                options        = options,
                headless       = headless,
                use_subprocess = True,
                version_main   = chrome_major,
            )
            _uc_driver = driver

            def _cleanup():
                try:
                    driver.quit()
                except Exception:
                    pass
            atexit.register(_cleanup)

            mode = "hidden" if headless else "visible"
            print(f"🌐 [SEARCH] Chrome ready (profile: {profile_name}, {mode})")
            return driver

        except Exception as exc:
            print(f"🌐 [SEARCH] Profile {profile_name} locked, trying next… ({exc})")
            continue

    print("🔴 [SEARCH] All Chrome profiles are locked — close any open Chrome windows and retry")
    return None


# Shared JS — finds organic results (a>h3 and h3→closest a). Survives redesigns.
_PARSE_RESULTS_JS = """
    const items    = [];
    const seenUrls = new Set();

    const JUNK = new Set([
        'more businesses', 'see more', 'more results',
        'people also ask', 'related searches', 'web results',
    ]);

    const cleanHref = (href) => {
        href = href || '';
        if (href.includes('/url?') || href.includes('google.com/url')) {
            try { href = new URL(href).searchParams.get('q') || href; } catch(e) {}
        }
        if (href.startsWith('/url?')) {
            try { href = new URL('https://google.com' + href).searchParams.get('q') || href; } catch(e) {}
        }
        return href;
    };

    const pushItem = (href, title, snipEl) => {
        href = cleanHref(href);
        if (!href.startsWith('http')) return;
        if (href.includes('google.com/search')) return;
        if (href.includes('google.com/maps'))   return;
        if (href.includes('google.com/imgres')) return;
        title = (title || '').trim();
        if (title.length < 4) return;
        if (JUNK.has(title.toLowerCase())) return;
        const urlKey = href.split('?')[0].replace(/[/]+$/, '');
        if (seenUrls.has(urlKey)) return;
        seenUrls.add(urlKey);
        items.push({
            link: href,
            title: title,
            snippet: snipEl ? (snipEl.innerText || '').trim() : '',
        });
    };

    for (const a of document.querySelectorAll('a[href]')) {
        const h3 = a.querySelector('h3');
        if (!h3) continue;
        const parent = a.closest('div') || a.parentElement;
        const snipEl = parent ? parent.querySelector(
            '[data-sncf="1"], .VwiC3b, .yXK7lf, .IsZvec, [style*="-webkit-line-clamp"]'
        ) : null;
        pushItem(a.href, h3.innerText, snipEl);
    }
    // Second pass: h3 whose link is an ancestor (newer Google layouts)
    if (items.length === 0) {
        for (const h3 of document.querySelectorAll('#search h3, #rso h3, div[data-sokoban-container] h3')) {
            const a = h3.closest('a[href]') || (h3.parentElement && h3.parentElement.closest('a[href]'));
            if (!a) continue;
            pushItem(a.href, h3.innerText, null);
        }
    }
    return items;
"""

# Google AI Overview / SGE — company names listed in the summary block.
# DOM changes often; keep selectors resilient and prefer list-item structure.
_PARSE_AI_OVERVIEW_JS = """
(() => {
    const items = [];
    const seenNames = new Set();
    const JUNK_HOST = /(google\\.|gstatic\\.|youtube\\.|blogger\\.|schema\\.org|googleapis\\.|g\\.co\\/)/i;
    const JUNK_NAME = /^(ai overview|overview|sources|show more|see more|related questions|people also ask|web results|more results)$/i;

    const cleanHref = (href) => {
        href = href || '';
        if (href.includes('/url?') || href.includes('google.com/url')) {
            try { href = new URL(href).searchParams.get('q') || href; } catch(e) {}
        }
        if (href.startsWith('/url?')) {
            try { href = new URL('https://google.com' + href).searchParams.get('q') || href; } catch(e) {}
        }
        return href;
    };

    const isAioHeading = (t) => {
        t = (t || '').trim().toLowerCase();
        return t.includes('ai overview')
            || t.includes('نظرة عامة')
            || t.includes('ملخص الذكاء')
            || t === 'overview';
    };

    let root = null;
    for (const h of document.querySelectorAll(
        'h1,h2,div[role="heading"],span[role="heading"],div[aria-level]'
    )) {
        if (!isAioHeading(h.innerText || h.getAttribute('aria-label') || '')) continue;
        root = h.closest('div') || h.parentElement;
        for (let i = 0; i < 6 && root && root.parentElement; i++) {
            const txt = (root.innerText || '');
            if (txt.length > 280 && (root.querySelector('li') || root.querySelector('a[href]')))
                break;
            root = root.parentElement;
        }
        break;
    }
    if (!root) {
        for (const sel of ['.hdzaWe', '.YzCcua', '.WaaZC', '.Ajpz4e', '.s75CSd', '.M8OgIe', '#eBuvYc']) {
            const el = document.querySelector(sel);
            if (!el) continue;
            const txt = (el.innerText || '');
            if (txt.length > 120) { root = el; break; }
        }
    }
    if (!root) return items;

    const push = (name, href, snip) => {
        name = (name || '').replace(/^\\d+[.)]\\s*/, '').replace(/\\s+/g, ' ').trim();
        if (name.length < 2 || name.length > 120 || JUNK_NAME.test(name)) return;
        const key = name.toLowerCase();
        if (seenNames.has(key)) return;
        href = cleanHref(href || '');
        if (href && (!href.startsWith('http') || JUNK_HOST.test(href))) href = '';
        if (href && (href.includes('google.com/search') || href.includes('google.com/maps')))
            href = '';
        seenNames.add(key);
        items.push({
            link: href,
            title: name,
            snippet: (snip || '').replace(/\\s+/g, ' ').trim().slice(0, 500),
            source: 'ai_overview',
        });
    };

    // Structured list / cards inside the overview
    const blocks = root.querySelectorAll('li, [role="listitem"]');
    if (blocks.length) {
        for (const li of blocks) {
            const text = (li.innerText || '').trim();
            if (text.length < 3 || text.length > 800) continue;
            const strong = li.querySelector('strong, b, em');
            let name = strong ? (strong.innerText || '').trim()
                             : text.split(/[\\n•|]/)[0].trim();
            name = name.split(/[–—:\\-]/)[0].trim();
            const a = li.querySelector('a[href]');
            let href = a ? a.href : '';
            // Prefer non-directory company site if multiple links
            for (const link of li.querySelectorAll('a[href]')) {
                const h = cleanHref(link.href);
                if (!h.startsWith('http') || JUNK_HOST.test(h)) continue;
                if (/goodfirms|clutch|g2\\.com|capterra|wikipedia|linkedin/i.test(h)) continue;
                href = h;
                break;
            }
            push(name, href, text);
        }
    }

    // Fallback: bold/strong names in overview body + nearest link
    if (items.length === 0) {
        for (const strong of root.querySelectorAll('strong, b')) {
            const name = (strong.innerText || '').trim();
            if (name.length < 2 || name.length > 80) continue;
            const block = strong.closest('div, p, span, li') || strong.parentElement;
            const a = block ? block.querySelector('a[href]') : null;
            push(name, a ? a.href : '', block ? block.innerText : name);
        }
    }

    // Last resort: external links whose anchor looks like a company name
    if (items.length === 0) {
        for (const a of root.querySelectorAll('a[href]')) {
            const href = cleanHref(a.href);
            if (!href.startsWith('http') || JUNK_HOST.test(href)) continue;
            if (/goodfirms|clutch|g2\\.com|capterra|wikipedia|linkedin/i.test(href)) continue;
            let title = (a.innerText || '').trim();
            if (!title || title.length < 2 || /^https?:/i.test(title)) {
                try { title = new URL(href).hostname.replace(/^www\\./, ''); } catch(e) { continue; }
            }
            push(title, href, '');
        }
    }
    return items;
})()
"""

# Google Local Pack / Maps "Businesses" block (الأنشطة التجارية).
# Prefer each card's Website / صفحة ويب link over Maps place URLs.
_PARSE_LOCAL_PACK_JS = """
(() => {
    const items = [];
    const seenNames = new Set();
    const JUNK_HOST = /(google\\.|gstatic\\.|youtube\\.|blogger\\.|schema\\.org|googleapis\\.|g\\.co\\/|maps\\.app\\.goo)/i;
    const JUNK_NAME = /^(businesses|business activities|more businesses|see more|more results|الأنشطة التجارية|المزيد من الأنشطة|directions|الاتجاهات|website|صفحة ويب)$/i;

    const cleanHref = (href) => {
        href = href || '';
        if (href.includes('/url?') || href.includes('google.com/url')) {
            try { href = new URL(href).searchParams.get('q') || href; } catch(e) {}
        }
        if (href.startsWith('/url?')) {
            try { href = new URL('https://google.com' + href).searchParams.get('q') || href; } catch(e) {}
        }
        return href;
    };

    const isWebsiteLabel = (t) => {
        t = (t || '').trim().toLowerCase();
        return t === 'website' || t === 'site' || t === 'web'
            || t.includes('website')
            || t.includes('صفحة ويب')
            || t.includes('الموقع');
    };

    const isMapsHref = (h) => {
        h = (h || '').toLowerCase();
        return h.includes('google.com/maps') || h.includes('maps.google')
            || h.includes('maps.app.goo') || h.includes('/maps/place');
    };

    const push = (name, href, snip) => {
        name = (name || '').replace(/^\\d+[.)]\\s*/, '').replace(/\\s+/g, ' ').trim();
        // Strip trailing category ellipsis from map pin titles
        name = name.replace(/\\s*[\\u2026...]\\s*$/, '').trim();
        if (name.length < 2 || name.length > 160 || JUNK_NAME.test(name)) return;
        const key = name.toLowerCase();
        if (seenNames.has(key)) return;
        href = cleanHref(href || '');
        if (href && (!href.startsWith('http') || JUNK_HOST.test(href) || isMapsHref(href)))
            href = '';
        seenNames.add(key);
        items.push({
            link: href,
            title: name,
            snippet: (snip || '').replace(/\\s+/g, ' ').trim().slice(0, 500),
            source: 'local_pack',
        });
    };

    // Prefer known local-pack card selectors
    let cards = Array.from(document.querySelectorAll(
        '.VkpGBb, .cXedhc, .Nv2PK, .rllt__link, div[data-local-attribute]'
    ));

    // Fallback: climb from "Businesses" / Arabic heading into card list
    if (cards.length === 0) {
        for (const h of document.querySelectorAll(
            'h1,h2,div[role="heading"],span[role="heading"],div[aria-level]'
        )) {
            const t = ((h.innerText || h.getAttribute('aria-label') || '') + '').trim().toLowerCase();
            if (!(t.includes('business') || t.includes('أنشطة') || t.includes('أنشطه')))
                continue;
            let root = h.closest('div') || h.parentElement;
            for (let i = 0; i < 5 && root; i++) {
                const found = root.querySelectorAll(
                    'a[href] [role="heading"], a[href] .OSrXXb, .qBF1Pd, .dbg0pd'
                );
                if (found.length >= 2) {
                    cards = Array.from(found).map(el =>
                        el.closest('.VkpGBb, .cXedhc, .Nv2PK, div[jscontroller], a[href]') || el.parentElement
                    ).filter(Boolean);
                    break;
                }
                root = root.parentElement;
            }
            if (cards.length) break;
        }
    }

    for (const card of cards) {
        if (!card) continue;
        const nameEl = card.querySelector(
            '.qBF1Pd, .OSrXXb, .dbg0pd, [role="heading"], .fontHeadlineSmall, .fontHeadlineMedium'
        );
        let name = nameEl ? (nameEl.innerText || '').trim() : '';
        if (!name) {
            const aTitle = card.querySelector('a[href]');
            name = aTitle ? (aTitle.innerText || '').split('\\n')[0].trim() : '';
        }
        if (!name) continue;

        let href = '';
        for (const a of card.querySelectorAll('a[href]')) {
            const label = (
                a.getAttribute('aria-label') || a.getAttribute('data-tooltip')
                || a.innerText || ''
            ).trim();
            const h = cleanHref(a.href);
            if (!h.startsWith('http') || JUNK_HOST.test(h) || isMapsHref(h)) continue;
            if (isWebsiteLabel(label)) { href = h; break; }
        }
        if (!href) {
            for (const a of card.querySelectorAll('a[href]')) {
                const h = cleanHref(a.href);
                if (!h.startsWith('http') || JUNK_HOST.test(h) || isMapsHref(h)) continue;
                if (h.includes('google.com')) continue;
                href = h;
                break;
            }
        }
        push(name, href, card.innerText || name);
    }
    return items;
})()
"""


def _company_slug(name: str) -> str:
    """Alphanumeric slug for matching company names to hostnames."""
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())


def resolve_ai_overview_link(
    company_name: str,
    link: str = "",
    *,
    organic: list | None = None,
    aio_links: list | None = None,
) -> str:
    """
    Resolve an AI Overview company name to a company homepage URL.
    Prefer an explicit AIO link; else hostname slug match; else organic title match.
    Returns '' if unresolved or the only hits are blocked/directory domains.
    """
    organic = organic or []
    aio_links = list(aio_links or [])
    if link:
        aio_links.insert(0, link)

    slug = _company_slug(company_name)
    name_lc = (company_name or "").lower().strip()
    tokens = [t for t in re.findall(r"[a-z0-9]+", name_lc) if len(t) >= 4]
    candidates: list[str] = []

    def _host_matches(href: str) -> bool:
        dom = get_domain(href or "")
        if not dom:
            return False
        host = dom.split(".")[0]
        host_slug = _company_slug(host)
        if slug and (slug in host_slug or host_slug in slug):
            return True
        return any(t in host_slug for t in tokens)

    for href in aio_links:
        if not href or not href.startswith("http") or is_blocked(href):
            continue
        # Only keep AIO links whose host resembles the company (skip listicle cites)
        if _host_matches(href):
            candidates.insert(0, href)

    if name_lc:
        for row in organic:
            title = (row.get("title") or "").lower()
            href = row.get("link") or ""
            if not href or not title or is_blocked(href):
                continue
            titled = name_lc in title or (tokens and all(t in title for t in tokens[:2]))
            if not titled:
                continue
            if _host_matches(href):
                candidates.insert(0, href)
            elif href not in candidates:
                # Organic titled with company name — accept even if host slug is loose
                candidates.append(href)

    # Prefer hostname that resembles the company name
    ranked = sorted(
        candidates,
        key=lambda h: (0 if _host_matches(h) else 1, len(get_domain(h) or h)),
    )
    for href in ranked:
        if href and not is_blocked(href):
            return href
    return ""


def merge_serp_verified_results(
    raw: list,
    organic: list | None = None,
    *,
    source: str = "ai_overview",
) -> list:
    """
    Normalize verified SERP panel rows (AI Overview or Local Pack) to
    {link, title, snippet, source}. Drops entries that cannot be resolved
    to a non-blocked company domain.
    """
    organic = organic or []
    all_links = [r.get("link") or "" for r in (raw or []) if r.get("link")]
    out: list = []
    seen_dom: set[str] = set()
    for row in raw or []:
        name = (row.get("title") or "").strip()
        if not name:
            continue
        href = resolve_ai_overview_link(
            name,
            row.get("link") or "",
            organic=organic,
            aio_links=all_links,
        )
        if not href:
            continue
        dom = get_domain(href)
        if not dom or dom in seen_dom or is_blocked(href):
            continue
        seen_dom.add(dom)
        out.append({
            "link": href,
            "title": name,
            "snippet": (row.get("snippet") or "")[:500],
            "source": source,
        })
    return out


def merge_ai_overview_results(
    aio_raw: list,
    organic: list | None = None,
) -> list:
    """Normalize AI Overview rows (source='ai_overview')."""
    return merge_serp_verified_results(
        aio_raw, organic, source="ai_overview",
    )


def merge_local_pack_results(
    pack_raw: list,
    organic: list | None = None,
) -> list:
    """Normalize Local Pack / Maps business rows (source='local_pack')."""
    return merge_serp_verified_results(
        pack_raw, organic, source="local_pack",
    )


def _uc_google_search(
    query: str, num: int = 10, page: int = 1, *, return_aio_raw: bool = False,
):
    """Execute one Google search in the shared undetected-Chrome instance."""
    driver = _get_uc_driver()
    if driver is None:
        raise RuntimeError("undetected-chromedriver unavailable")

    start      = num * (page - 1)
    search_url = (
        "https://www.google.com/search?"
        + urlencode({"q": query, "num": min(num, 100), "hl": "en", "start": start})
    )

    driver.get(search_url)

    # ── GDPR consent guard ────────────────────────────────────────────────────
    try:
        if "consent.google.com" in driver.current_url:
            clicked = driver.execute_script("""
                const accept_re = /^(accept all|accept|agree|i agree)$/i;
                const selectors = [
                    '#introAgreeButton',
                    'button[jsname="b3VHJd"]',
                    '[aria-label="Accept all"]',
                ];
                for (const sel of selectors) {
                    const el = document.querySelector(sel);
                    if (el) { el.click(); return true; }
                }
                for (const btn of document.querySelectorAll('button')) {
                    if (btn.offsetParent && accept_re.test(btn.innerText.trim())) {
                        btn.click();
                        return true;
                    }
                }
                return false;
            """)
            if clicked:
                print("🌐 [SEARCH] GDPR consent accepted — reloading search…")
                time.sleep(2.0)
                driver.get(search_url)
    except Exception:
        pass

    # ── CAPTCHA guard (unattended: no human wait) ─────────────────────────────
    # On CAPTCHA: trip cooldown and raise so the caller can fall back to
    # SearXNG → DDG, then return to Google after GOOGLE_CAPTCHA_COOLDOWN_SEC.
    if "sorry.google.com" in driver.current_url:
        trip_google_cooldown()
        _captcha_flag.set()
        print("\n" + "=" * 60)
        print("  !! Google CAPTCHA detected — unattended auto-fallback.")
        print(f"  Cooling Google for {GOOGLE_CAPTCHA_COOLDOWN_SEC // 60} min;")
        print("  auto SearXNG (Docker) → DuckDuckGo; no human / no .bat.")
        print("=" * 60 + "\n")
        # Clear quickly so UI does not stay on "solve CAPTCHA"
        _captcha_flag.clear()
        raise CaptchaHit(
            f"Google CAPTCHA — cooldown {GOOGLE_CAPTCHA_COOLDOWN_SEC // 60} min, "
            "auto fallback SearXNG/DDG"
        )

    # ── Smart wait: pause until first result title appears ────────────────────
    try:
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.TAG_NAME, "h3"))
        )
    except Exception:
        pass

    # ── Human-like reading pause before scraping ──────────────────────────────
    # Simulate a person glancing at the results before clicking.
    # Use a non-uniform distribution: most pauses are short, occasional long ones.
    # Slightly tighter than before, still non-uniform (avoids metronome bot signal).
    pause = random.choice([
        random.uniform(0.25, 0.6),  # quick glance      — 60 %
        random.uniform(0.25, 0.6),
        random.uniform(0.25, 0.6),
        random.uniform(0.7, 1.4),   # normal read        — 30 %
        random.uniform(0.7, 1.4),
        random.uniform(1.8, 3.2),   # distracted moment  — 10 %
    ])
    time.sleep(pause)

    # ── Simulate partial scroll (humans don't just sit still) ─────────────────
    try:
        scroll_px = random.randint(80, 400)
        driver.execute_script(f"window.scrollBy(0, {scroll_px});")
        time.sleep(random.uniform(0.2, 0.5))
        driver.execute_script(f"window.scrollBy(0, -{scroll_px // 2});")
    except Exception:
        pass

    # ── Parse organic + AI Overview + Local Pack ──────────────────────────────
    raw = driver.execute_script(_PARSE_RESULTS_JS) or []
    aio_raw: list = []
    pack_raw: list = []
    if page == 1:
        try:
            aio_raw = driver.execute_script(_PARSE_AI_OVERVIEW_JS) or []
        except Exception:
            aio_raw = []
        try:
            pack_raw = driver.execute_script(_PARSE_LOCAL_PACK_JS) or []
        except Exception:
            pack_raw = []
    aio = merge_ai_overview_results(aio_raw, organic=raw)
    pack = merge_local_pack_results(pack_raw, organic=raw)
    # Verified panels first so dedupe keeps them over listicle organics
    organic = raw[:num]
    results = list(aio) + list(pack) + list(organic)

    print(
        f"🌐 [SEARCH] '{query}' → {len(raw)} organic, {len(aio)} AI Overview, "
        f"{len(pack)} Local Pack, returning {len(results)}"
    )

    # Page-1 with zero organics is never a valid "done" for real queries —
    # treat as soft-block and force unattended fallbacks (SearXNG / Bing).
    # Later empty pages are normal end-of-results (no cooldown).
    # Verified-panel-only page-1 still counts as a valid Google hit.
    if not results and page == 1:
        trip_google_cooldown()
        print("🌐 [SEARCH] Empty Google page-1 — triggering CAPTCHA fallback")
        raise CaptchaHit(
            f"Google empty/soft-block — cooldown {GOOGLE_CAPTCHA_COOLDOWN_SEC // 60} min, "
            "auto fallback SearXNG/Bing"
        )

    # ── Inter-search pacing — non-uniform, mimics human think time ────────────
    # Consecutive rapid-fire requests are the #1 signal Google blocks on.
    # Faster average gap, keep occasional long breaks so we don't look bursty.
    inter = random.choice([
        random.uniform(1.0, 2.0),   # normal gap         — 50 %
        random.uniform(1.0, 2.0),
        random.uniform(1.0, 2.0),
        random.uniform(2.2, 4.0),   # longer break        — 35 %
        random.uniform(2.2, 4.0),
        random.uniform(4.5, 7.0),   # occasional long gap — 15 %
    ])
    time.sleep(inter)

    if return_aio_raw:
        return results, aio_raw, pack_raw, raw
    return results


# ─────────────────────────────────────────────────────────────────────────────
# Public interface
# ─────────────────────────────────────────────────────────────────────────────

def google_warmup() -> None:
    """
    Pre-launch Chrome so the first search has no cold-start delay.
    Call once before the search loop — returns when Chrome is ready.
    """
    with _uc_lock:
        _get_uc_driver()


def google_search(query: str, num: int = 10, page: int = 1) -> list:
    """
    Search Google via undetected-Chrome — free, human-like, no API key.
    Page-1 also prepends AI Overview + Local Pack companies
    (source='ai_overview' / 'local_pack').
    Raises CaptchaHit on CAPTCHA (no human wait; cooldown started in utils).
    Raises on other failures so the UI can surface the error.
    Caller should skip calling this while google_in_cooldown() is True.
    """
    with _uc_lock:
        return _uc_google_search(query, num=num, page=page)


def google_ai_overview(query: str, extra_organic: list | None = None) -> list:
    """
    Load Google page-1 and return verified panel companies:
    AI Overview + Local Pack / Maps businesses
    ({link, title, snippet, source: 'ai_overview'|'local_pack'}).

    ``extra_organic`` (e.g. SearXNG/OpenSERP hits) helps resolve company names
    that appear without a direct company URL.
    Raises CaptchaHit when Google blocks the page.
    """
    with _uc_lock:
        _results, aio_raw, pack_raw, organic = _uc_google_search(
            query, num=10, page=1, return_aio_raw=True,
        )
    combined = list(organic or []) + list(extra_organic or [])
    aio = merge_ai_overview_results(aio_raw, organic=combined)
    pack = merge_local_pack_results(pack_raw, organic=combined)
    # Dedupe by domain — AI Overview first, then Local Pack
    seen: set[str] = set()
    out: list = []
    for row in list(aio) + list(pack):
        dom = get_domain((row or {}).get("link") or "")
        if not dom or dom in seen:
            continue
        seen.add(dom)
        out.append(row)
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Chrome-based site scraper — replaces Firecrawl (free, handles JS pages)
# ─────────────────────────────────────────────────────────────────────────────

_SCRAPE_JS = """
(function() {
    // Visible text — cleaner than innerHTML stripping
    const text = document.body ? document.body.innerText : '';

    // All unique absolute links on the page
    const seen  = new Set();
    const links = [];
    for (const a of document.querySelectorAll('a[href]')) {
        let h = a.href || '';
        if (h.startsWith('http') && !seen.has(h)) {
            seen.add(h);
            links.push(h);
        }
    }

    return { text: text.slice(0, 12000), links: links.slice(0, 300) };
})();
"""


def _uc_chrome_scrape(url: str) -> dict | None:
    """Visit a URL with the shared Chrome instance and extract text + links."""
    driver = _get_uc_driver()
    if driver is None:
        return None

    try:
        driver.get(url if "://" in url else f"https://{url}")

        # Wait for meaningful content — body text should appear within 20s
        try:
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC
            WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
        except Exception:
            pass

        # Small pause — let JS frameworks finish rendering
        time.sleep(random.uniform(0.8, 1.6))

        result = driver.execute_script(_SCRAPE_JS)
        if not result:
            return None

        text  = result.get("text",  "") or ""
        links = result.get("links", []) or []

        print(f"🔎 [SCRAPE] {url} → {len(text)} chars, {len(links)} links")

        # Brief inter-page pause — polite and avoids rate-limiting
        time.sleep(random.uniform(1.0, 2.5))

        return {"markdown": text, "links": links}

    except Exception as exc:
        print(f"🔴 [SCRAPE] {url} failed: {exc}")
        return None


def _fast_scrape(url: str) -> dict | None:
    """
    Quick plain-HTTP scrape with UA rotation, SSL fallback, and one timeout retry.

    Resilience strategy:
      - Rotates User-Agent from _USER_AGENTS pool on every call
      - SSLError  → retries immediately with verify=False (expired/self-signed certs)
      - Timeout / ConnectionError → retries once with 20s timeout + verify=False
      - Any other exception → returns None (triggers Chrome fallback)

    Returns None when text < 100 chars (JS-only site) to trigger Chrome fallback.
    Returns {'markdown': str, 'links': list[str]} on success.
    """
    import requests as _req
    import re as _re

    target  = url if "://" in url else f"https://{url}"
    headers = {"User-Agent": random.choice(_USER_AGENTS)}

    def _get(timeout, verify):
        return _req.get(target, timeout=timeout, headers=headers,
                        allow_redirects=True, verify=verify)

    resp = None
    try:
        try:
            resp = _get(15, True)
        except _req.exceptions.SSLError:
            resp = _get(15, False)
        except (_req.exceptions.Timeout, _req.exceptions.ConnectionError):
            resp = _get(20, False)   # one retry on network hiccup
    except Exception:
        return None

    if resp is None or resp.status_code != 200:
        return None

    html = resp.text
    for tag in ("script", "style", "noscript", "nav", "footer", "head"):
        html = _re.sub(rf'<{tag}[^>]*>.*?</{tag}>', ' ', html,
                       flags=_re.DOTALL | _re.IGNORECASE)
    text  = _re.sub(r'<[^>]+>', ' ', html)
    text  = _re.sub(r'\s+', ' ', text).strip()[:12000]

    # Collect both absolute AND relative links
    raw_links = [m.group(1) for m in _re.finditer(r'href=["\']([^"\'#\s]+)["\']', html)]
    links = []
    for lnk in raw_links:
        if lnk.startswith("http") or (lnk.startswith("/") and not lnk.startswith("//")):
            links.append(lnk)
    links = links[:300]

    # < 100 chars → JS-only page, trigger Chrome fallback
    if len(text) < 100:
        return None

    return {"markdown": text, "links": links}


def chrome_scrape(url: str) -> dict | None:
    """
    Scrape a company website.
    Strategy (fast → thorough):
      1. Plain requests (~1-3s) — works for ~80% of sites
      2. Chrome (~15s)          — only if requests returns empty / JS-only page

    Returns {'markdown': str, 'links': list[str]}.
    """
    # Fast path first — skip Chrome for sites with readable HTML
    result = _fast_scrape(url)
    if result is not None:
        return result

    # Slow path — JS-heavy site, need a real browser
    with _uc_lock:
        return _uc_chrome_scrape(url)


# ─────────────────────────────────────────────────────────────────────────────
# SearXNG search — self-hosted meta-search, no CAPTCHA, no browser needed
# Auto-started via Docker when possible (unattended — no human / no .bat).
# ─────────────────────────────────────────────────────────────────────────────

_SEARXNG_URL = os.getenv("SEARXNG_URL", "http://localhost:8888").rstrip("/")
_searxng_ensure_lock = threading.Lock()
_searxng_last_ensure = 0.0
_searxng_known_up = False
_searxng_call_lock = threading.Lock()
_searxng_last_call_mono = 0.0
_SEARXNG_MIN_GAP_SEC = 1.0  # tighter pace for throughput; still gaps upstream
_searxng_last_restart_mono = 0.0
_SEARXNG_RESTART_COOLDOWN_SEC = 900  # at most one docker restart / 15 min


def _try_restart_searxng_container(reason: str = "") -> bool:
    """
    One-shot `docker restart searxng` when upstreams are CAPTCHA-dead but the
    port is still open. Throttled so we never flap the container every query.
    """
    global _searxng_last_restart_mono, _searxng_known_up
    now = time.monotonic()
    if now - _searxng_last_restart_mono < _SEARXNG_RESTART_COOLDOWN_SEC:
        return False
    import subprocess
    print(f"🔍 [SEARXNG] Restarting container ({reason or 'empty / suspended upstreams'})…")
    try:
        p = subprocess.run(
            ["docker", "restart", "searxng"],
            capture_output=True, text=True, timeout=90,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        _searxng_last_restart_mono = time.monotonic()
        if p.returncode != 0:
            print(f"🔍 [SEARXNG] docker restart failed: {(p.stderr or p.stdout or '').strip()}")
            return False
        # Wait for JSON again
        for _ in range(20):
            time.sleep(1.0)
            if _searxng_port_open(timeout=1.0):
                _searxng_known_up = True
                print("🔍 [SEARXNG] Container restarted — port open")
                return True
    except Exception as exc:
        print(f"🔍 [SEARXNG] restart error: {exc}")
        _searxng_last_restart_mono = time.monotonic()
    return False


def _searxng_port_open(timeout: float = 1.5) -> bool:
    """True if something is listening on the SearXNG URL host:port."""
    import socket
    from urllib.parse import urlparse
    parsed = urlparse(_SEARXNG_URL)
    host = parsed.hostname or "localhost"
    port = parsed.port or 8888
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def ensure_searxng(force: bool = False) -> bool:
    """
    Make SearXNG reachable with zero human steps.

    1. If already up → True
    2. Else try `docker start searxng` or create the container (same as the .bat)
    3. Wait briefly for the port
    4. If Docker unavailable → False (caller should use DuckDuckGo)

    Throttled so we don't hammer Docker on every SERP page.
    """
    global _searxng_last_ensure, _searxng_known_up

    if not force and _searxng_known_up and _searxng_port_open():
        return True
    if _searxng_port_open():
        _searxng_known_up = True
        return True

    with _searxng_ensure_lock:
        # Re-check inside the lock
        if _searxng_port_open():
            _searxng_known_up = True
            return True

        now = time.time()
        if not force and (now - _searxng_last_ensure) < 45:
            return False
        _searxng_last_ensure = now

        import subprocess
        searxng_dir = os.path.normpath(
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "searxng")
        )
        settings = os.path.join(searxng_dir, "settings.yml")
        mount = searxng_dir.replace("\\", "/")

        def _run(cmd: list[str], timeout: int = 120) -> tuple[int, str]:
            try:
                p = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=timeout,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                out = (p.stdout or "") + (p.stderr or "")
                return p.returncode, out.strip()
            except FileNotFoundError:
                return 127, "docker not found"
            except Exception as exc:
                return 1, str(exc)

        print("🔍 [SEARXNG] Not reachable — auto-starting via Docker (unattended)…")
        code, out = _run(["docker", "info"], timeout=15)
        if code != 0:
            print(f"🔍 [SEARXNG] Docker unavailable ({out or code}) — will use DuckDuckGo")
            _searxng_known_up = False
            return False

        # Prefer restarting an existing container
        code, _ = _run(["docker", "inspect", "searxng"], timeout=15)
        if code == 0:
            code, out = _run(["docker", "start", "searxng"], timeout=60)
            if code != 0:
                print(f"🔍 [SEARXNG] docker start failed: {out}")
        else:
            if not os.path.isfile(settings):
                print(f"🔍 [SEARXNG] Missing settings at {settings} — will use DuckDuckGo")
                _searxng_known_up = False
                return False
            print("🔍 [SEARXNG] Creating container searxng…")
            _run(["docker", "pull", "searxng/searxng"], timeout=300)
            code, out = _run([
                "docker", "run", "-d",
                "--name", "searxng",
                "--restart", "unless-stopped",
                "-p", "8888:8080",
                "-v", f"{mount}:/etc/searxng:rw",
                "searxng/searxng",
            ], timeout=120)
            if code != 0:
                print(f"🔍 [SEARXNG] docker run failed: {out}")
                _searxng_known_up = False
                return False

        # Wait for HTTP port + a real JSON search (not just the port)
        import requests as _requests
        for _ in range(30):
            if _searxng_port_open(timeout=1.0):
                try:
                    probe = _requests.get(
                        f"{_SEARXNG_URL}/search",
                        params={
                            "q": "test", "format": "json",
                            "categories": "general", "language": "en",
                        },
                        timeout=8,
                        headers={"Accept": "application/json"},
                    )
                    if probe.status_code == 200:
                        _searxng_known_up = True
                        print("🔍 [SEARXNG] Auto-start OK — http://localhost:8888")
                        return True
                except Exception:
                    pass
            time.sleep(1.0)

        print("🔍 [SEARXNG] Still not serving JSON after auto-start — will use Bing (Chrome)")
        _searxng_known_up = False
        return False


def searxng_search(query: str, num: int = 10, page: int = 1,
                   status_out: dict | None = None) -> list:
    """
    Search via local SearXNG. Calls ensure_searxng() first (unattended).

    Returns the same dict shape as google_search: link, title, snippet.
    Raises on failure so the caller can fall back to DuckDuckGo / OpenSERP.

    Optional status_out receives {"status": "ok"|"empty"|"blocked"|"down", "detail": str}.
    """
    import requests as _requests
    global _searxng_known_up, _searxng_last_call_mono

    def _status(st: str, detail: str = ""):
        if status_out is not None:
            status_out.clear()
            status_out.update({"status": st, "detail": detail})

    if not ensure_searxng():
        _status("down", "SearXNG unreachable after auto-start attempt")
        raise RuntimeError("SearXNG unreachable after auto-start attempt")

    headers = {
        "Accept": "application/json",
        "User-Agent": "LocReach/1.0 (+local searxng client)",
        # botdetection expects a client IP when behind some proxies
        "X-Forwarded-For": "127.0.0.1",
        "X-Real-IP": "127.0.0.1",
    }

    last_unresponsive = ""

    def _fmt_unresponsive(data: dict) -> str:
        parts = []
        for item in (data.get("unresponsive_engines") or [])[:6]:
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                parts.append(f"{item[0]}={item[1]}")
            elif isinstance(item, (list, tuple)) and item:
                parts.append(str(item[0]))
            else:
                parts.append(str(item))
        return "; ".join(parts)

    def _one_attempt(pageno: int) -> list:
        nonlocal last_unresponsive
        global _searxng_last_call_mono
        with _searxng_call_lock:
            gap = time.monotonic() - _searxng_last_call_mono
            if gap < _SEARXNG_MIN_GAP_SEC:
                time.sleep(_SEARXNG_MIN_GAP_SEC - gap)
            params = {
                "q": query,
                "format": "json",
                "categories": "general",
                "language": "en",
                "pageno": pageno,
            }
            resp = _requests.get(
                f"{_SEARXNG_URL}/search",
                params=params,
                timeout=25,
                headers=headers,
            )
            _searxng_last_call_mono = time.monotonic()
        if resp.status_code == 403:
            raise RuntimeError(
                "SearXNG JSON forbidden (check settings.yml formats includes json "
                "and the container mounts Sales_Tool/searxng)"
            )
        resp.raise_for_status()
        data = resp.json()
        last_unresponsive = _fmt_unresponsive(data)
        return [
            {
                "link": r.get("url", ""),
                "title": r.get("title", ""),
                "snippet": r.get("content", ""),
            }
            for r in data.get("results", [])[:num]
            if r.get("url")
        ]

    last_exc = None
    for attempt in range(2):
        try:
            results = _one_attempt(page)
            print(
                f"🔍 [SEARXNG] '{query}' p{page} try{attempt + 1} → {len(results)} results"
                + (f" (unresponsive: {last_unresponsive})" if not results and last_unresponsive else "")
            )
            if results:
                _searxng_known_up = True
                _status("ok")
                return results
            # Empty: longer backoff — SearXNG upstreams (DDG/Google) CAPTCHA-suspend
            # after bursts; a short wait often restores hits for the next term.
            if attempt == 0:
                time.sleep(5.0)
        except Exception as exc:
            last_exc = exc
            print(f"🔍 [SEARXNG] '{query}' try{attempt + 1} failed: {exc}")
            if attempt == 0:
                time.sleep(3.0)

    # Still empty with a live port → often suspended upstreams; one container bounce
    if _searxng_port_open() and page == 1:
        if _try_restart_searxng_container("consecutive empty JSON searches"):
            time.sleep(12.0)
            for post_try in range(2):
                try:
                    results = _one_attempt(page)
                    if results:
                        print(f"🔍 [SEARXNG] after restart → {len(results)} results")
                        _searxng_known_up = True
                        _status("ok")
                        return results
                    time.sleep(4.0)
                except Exception as exc:
                    last_exc = exc
                    print(f"🔍 [SEARXNG] post-restart search failed: {exc}")
                    time.sleep(3.0)

    if last_exc is not None and not _searxng_port_open():
        _searxng_known_up = False
        _status("down", str(last_exc))
        raise RuntimeError(f"SearXNG request failed ({last_exc})")

    # Soft empty — distinguish upstream blocks from genuine empty SERP
    if last_unresponsive:
        detail = last_unresponsive
        blockedish = any(
            k in detail.lower()
            for k in ("captcha", "suspended", "denied", "too many", "429", "timeout")
        )
        _status("blocked" if blockedish else "empty", detail)
        print(f"🔍 [SEARXNG] soft-empty — {'blocked' if blockedish else 'empty'}: {detail}")
    else:
        _status("empty", "no results and no unresponsive engines reported")
    return []


# ─────────────────────────────────────────────────────────────────────────────
# OpenSERP — free self-hosted SERP API (Docker). Fallback when SearXNG is dry.
# https://github.com/karust/openserp  — no API key.
# ─────────────────────────────────────────────────────────────────────────────

_OPENSERP_URL = os.getenv("OPENSERP_URL", "http://localhost:7000").rstrip("/")
_openserp_ensure_lock = threading.Lock()
_openserp_last_ensure = 0.0
_openserp_known_up = False
_openserp_call_lock = threading.Lock()
_openserp_last_call_mono = 0.0
_OPENSERP_MIN_GAP_SEC = 0.8
# Prefer non-Google engines when LocReach already hit Google CAPTCHA
_OPENSERP_ENGINES = "bing,yandex,ecosia,duckduckgo"


def _openserp_port_open(timeout: float = 1.5) -> bool:
    import socket
    from urllib.parse import urlparse
    parsed = urlparse(_OPENSERP_URL)
    host = parsed.hostname or "localhost"
    port = parsed.port or 7000
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def ensure_openserp(force: bool = False) -> bool:
    """
    Make OpenSERP reachable (Docker) with zero human steps.
    Same unattended pattern as ensure_searxng — optional free SERP fallback.
    """
    global _openserp_last_ensure, _openserp_known_up

    if not force and _openserp_known_up and _openserp_port_open():
        return True
    if _openserp_port_open():
        _openserp_known_up = True
        return True

    with _openserp_ensure_lock:
        if _openserp_port_open():
            _openserp_known_up = True
            return True

        now = time.time()
        if not force and (now - _openserp_last_ensure) < 45:
            return False
        _openserp_last_ensure = now

        import subprocess

        def _run(cmd: list[str], timeout: int = 120) -> tuple[int, str]:
            try:
                p = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=timeout,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                out = (p.stdout or "") + (p.stderr or "")
                return p.returncode, out.strip()
            except FileNotFoundError:
                return 127, "docker not found"
            except Exception as exc:
                return 1, str(exc)

        print("🟣 [OPENSERP] Not reachable — auto-starting via Docker…")
        code, out = _run(["docker", "info"], timeout=15)
        if code != 0:
            print(f"🟣 [OPENSERP] Docker unavailable ({out or code})")
            _openserp_known_up = False
            return False

        code, _ = _run(["docker", "inspect", "openserp"], timeout=15)
        if code == 0:
            code, out = _run(["docker", "start", "openserp"], timeout=60)
            if code != 0:
                print(f"🟣 [OPENSERP] docker start failed: {out}")
        else:
            print("🟣 [OPENSERP] Creating container openserp…")
            _run(["docker", "pull", "karust/openserp:latest"], timeout=300)
            code, out = _run([
                "docker", "run", "-d",
                "--name", "openserp",
                "--restart", "unless-stopped",
                "-p", "7000:7000",
                "karust/openserp:latest",
                "serve", "-a", "0.0.0.0", "-p", "7000",
            ], timeout=180)
            if code != 0:
                print(f"🟣 [OPENSERP] docker run failed: {out}")
                _openserp_known_up = False
                return False

        import requests as _requests
        for _ in range(40):
            if _openserp_port_open(timeout=1.0):
                try:
                    probe = _requests.get(f"{_OPENSERP_URL}/health", timeout=5)
                    if probe.status_code < 500:
                        _openserp_known_up = True
                        print("🟣 [OPENSERP] Auto-start OK — http://localhost:7000")
                        return True
                except Exception:
                    try:
                        probe = _requests.get(
                            f"{_OPENSERP_URL}/mega/search",
                            params={
                                "text": "test", "limit": 1, "mode": "any",
                                "engines": "bing",
                            },
                            timeout=15,
                        )
                        if probe.status_code in (200, 503):
                            _openserp_known_up = True
                            print("🟣 [OPENSERP] Auto-start OK — http://localhost:7000")
                            return True
                    except Exception:
                        pass
            time.sleep(1.0)

        print("🟣 [OPENSERP] Still not ready after auto-start")
        _openserp_known_up = False
        return False


def openserp_search(query: str, num: int = 10, page: int = 1,
                    status_out: dict | None = None) -> list:
    """
    Search via local OpenSERP (/mega/search, mode=any).
    Prefer Bing/Yandex/Ecosia/DDG so we do not re-burn Google after CAPTCHA.
    """
    import requests as _requests
    global _openserp_known_up, _openserp_last_call_mono

    def _status(st: str, detail: str = ""):
        if status_out is not None:
            status_out.clear()
            status_out.update({"status": st, "detail": detail})

    if not ensure_openserp():
        _status("down", "OpenSERP unreachable")
        raise RuntimeError("OpenSERP unreachable after auto-start attempt")

    start = max(0, (page - 1) * max(num, 10))
    with _openserp_call_lock:
        gap = time.monotonic() - _openserp_last_call_mono
        if gap < _OPENSERP_MIN_GAP_SEC:
            time.sleep(_OPENSERP_MIN_GAP_SEC - gap)
        try:
            resp = _requests.get(
                f"{_OPENSERP_URL}/mega/search",
                params={
                    "text": query,
                    "limit": min(num, 20),
                    "start": start,
                    "mode": "any",
                    "engines": _OPENSERP_ENGINES,
                    "lang": "EN",
                },
                timeout=45,
            )
            _openserp_last_call_mono = time.monotonic()
        except Exception as exc:
            _openserp_known_up = False
            _status("down", str(exc))
            raise RuntimeError(f"OpenSERP request failed ({exc})") from exc

    if resp.status_code == 503:
        detail = ""
        try:
            detail = (resp.json() or {}).get("message") or resp.text[:200]
        except Exception:
            detail = resp.text[:200]
        print(f"🟣 [OPENSERP] blocked/unavailable for '{query}': {detail}")
        _status("blocked", detail or "HTTP 503")
        return []

    if resp.status_code >= 400:
        _status("error", f"HTTP {resp.status_code}")
        print(f"🟣 [OPENSERP] HTTP {resp.status_code} for '{query}'")
        return []

    data = resp.json() if resp.content else {}
    meta = data.get("meta") or {}
    failed = meta.get("engines_failed") or []
    responded = meta.get("engines_responded") or []
    results = []
    for r in data.get("results") or []:
        url = r.get("url") or ""
        if not url.startswith("http"):
            continue
        rtype = (r.get("type") or "organic").lower()
        if rtype not in ("organic", "web"):
            continue
        results.append({
            "link": url,
            "title": r.get("title") or "",
            "snippet": r.get("snippet") or "",
        })
        if len(results) >= num:
            break

    print(
        f"🟣 [OPENSERP] '{query}' → {len(results)} results "
        f"(ok={responded or '-'} fail={failed or '-'})"
    )
    if results:
        _openserp_known_up = True
        _status("ok", f"engines={responded}")
        return results

    if failed:
        _status("blocked", f"engines_failed={failed}")
    else:
        _status("empty", f"engines_responded={responded}")
    return []


# ─────────────────────────────────────────────────────────────────────────────
# DuckDuckGo HTML search — Tier C, no API key, no JS, pure requests
# ─────────────────────────────────────────────────────────────────────────────

_BING_PARSE_JS = """
    const items = [];
    const seen = new Set();
    const push = (href, title, snippet) => {
        if (!href || !href.startsWith('http')) return;
        if (href.includes('bing.com') || href.includes('microsoft.com')) return;
        const key = href.split('?')[0].replace(/[/]+$/, '');
        if (seen.has(key)) return;
        seen.add(key);
        items.push({
            link: href,
            title: (title || '').trim(),
            snippet: (snippet || '').trim(),
        });
    };
    for (const li of document.querySelectorAll('li.b_algo')) {
        const a = li.querySelector('h2 a') || li.querySelector('a[href^="http"]');
        if (!a) continue;
        const snip = li.querySelector('.b_caption p, .b_lineclamp2, p');
        push(a.href, a.innerText, snip ? snip.innerText : '');
    }
    if (items.length === 0) {
        for (const a of document.querySelectorAll('h2 a[href^="http"], ol#b_results a[href^="http"]')) {
            push(a.href, a.innerText, '');
            if (items.length >= 20) break;
        }
    }
    return items;
"""


def _uc_bing_search(query: str, num: int = 10, page: int = 1,
                    status_out: dict | None = None) -> list:
    """
    Bing via the same Chrome instance — reliable when Google is blocked and
    SearXNG/DDG HTML are down. Unattended; no human.

    Detects Bing's "solve the challenge" interstitial and retries once after
    a homepage warm — never silently pretends the query has zero organics.
    """
    def _status(st: str, detail: str = ""):
        if status_out is not None:
            status_out.clear()
            status_out.update({"status": st, "detail": detail})

    driver = _get_uc_driver()
    if driver is None:
        print("🔎 [BING] Chrome driver unavailable")
        _status("error", "Chrome driver unavailable")
        return []

    first = 1 + max(0, page - 1) * 10
    url = (
        "https://www.bing.com/search?"
        + urlencode({
            "q": query, "count": min(num, 20), "first": first,
            "setlang": "en", "mkt": "en-US",
        })
    )

    def _looks_challenged() -> bool:
        try:
            body = (driver.execute_script(
                "return (document.body && document.body.innerText || '').slice(0, 500)"
            ) or "").lower()
            title = (driver.title or "").lower()
            return (
                "please solve the challenge" in body
                or "one last step" in body
                or "verify you are a human" in body
                or "captcha" in title
            )
        except Exception:
            return False

    def _parse() -> list:
        raw = driver.execute_script(_BING_PARSE_JS) or []
        return raw[:num]

    try:
        driver.get(url)
        time.sleep(random.uniform(1.5, 2.5))
        try:
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC
            WebDriverWait(driver, 8).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "li.b_algo, h2 a, #b_results, body")
                )
            )
        except Exception:
            pass

        if _looks_challenged():
            print(f"🔎 [BING] challenge page — warming bing.com then retry for '{query}'")
            try:
                driver.get("https://www.bing.com/")
                time.sleep(random.uniform(2.0, 3.5))
                driver.get(url)
                time.sleep(random.uniform(2.0, 3.5))
            except Exception as exc:
                print(f"🔎 [BING] retry navigation failed: {exc}")
                _status("blocked", f"challenge; retry nav failed: {exc}")
                return []
            if _looks_challenged():
                print(
                    f"🔎 [BING] still challenged for '{query}' — "
                    "blocked (not a true zero-result)"
                )
                _status("blocked", "Bing challenge interstitial")
                return []

        results = _parse()
        print(f"🔎 [BING] '{query}' → {len(results)} results")
        if results:
            _status("ok")
        else:
            _status("empty", "SERP parsed but zero organics")
        return results
    except Exception as exc:
        print(f"🔎 [BING] '{query}' failed: {exc}")
        _status("error", str(exc))
        return []


def bing_search(query: str, num: int = 10, page: int = 1,
                status_out: dict | None = None) -> list:
    """Public Bing search via Chrome (fallback when Google/SearXNG/DDG fail)."""
    with _uc_lock:
        return _uc_bing_search(query, num=num, page=page, status_out=status_out)


def duckduckgo_search(query: str, num: int = 10,
                      status_out: dict | None = None,
                      bing_fallback: bool = True) -> list:
    """
    DuckDuckGo HTML (often challenge-blocked with HTTP 202).

    When bing_fallback=True (default for other callers), falls through to
    Chrome Bing. Step 1 passes bing_fallback=False so Bing is tried earlier
    in the ordered engine chain, not nested here.
    """
    import requests as _req
    from urllib.parse import unquote as _unquote

    def _status(st: str, detail: str = ""):
        if status_out is not None:
            status_out.clear()
            status_out.update({"status": st, "detail": detail})

    headers = {
        "User-Agent": random.choice(_USER_AGENTS),
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml",
    }

    def _parse_ddg(html: str) -> list:
        results = []
        for m in re.finditer(
            r'<a[^>]+class="[^"]*result__a[^"]*"[^>]+href="([^"]*)"[^>]*>(.*?)</a>',
            html,
            re.DOTALL,
        ):
            raw_href = m.group(1)
            title = re.sub(r"<[^>]+>", "", m.group(2)).strip()
            if "uddg=" in raw_href:
                m2 = re.search(r"uddg=([^&]+)", raw_href)
                href = _unquote(m2.group(1)) if m2 else ""
            elif raw_href.startswith("http"):
                href = raw_href
            else:
                continue
            if href.startswith("http"):
                results.append({"link": href, "title": title, "snippet": ""})
            if len(results) >= num:
                break
        return results

    ddg_detail = ""
    for method in ("GET", "POST"):
        try:
            if method == "GET":
                resp = _req.get(
                    "https://html.duckduckgo.com/html/",
                    params={"q": query, "kl": "wt-wt"},
                    headers=headers,
                    timeout=15,
                )
            else:
                resp = _req.post(
                    "https://html.duckduckgo.com/html/",
                    data={"q": query, "b": ""},
                    headers={**headers, "Content-Type": "application/x-www-form-urlencoded"},
                    timeout=15,
                )
            if resp.status_code == 200:
                found = _parse_ddg(resp.text)
                if found:
                    print(f"🦆 [DDG] '{query}' → {len(found)} results ({method})")
                    _status("ok", f"DDG HTML {method}")
                    return found
                ddg_detail = f"HTTP 200 empty ({method})"
            else:
                ddg_detail = f"HTTP {resp.status_code} ({method})"
                print(f"🦆 [DDG] HTTP {resp.status_code} ({method}) for '{query}'")
        except Exception as exc:
            ddg_detail = f"{method} failed: {exc}"
            print(f"🦆 [DDG] '{query}' {method} failed: {exc}")

    if not bing_fallback:
        print(f"🦆 [DDG] HTML blocked for '{query}' — no Bing recurse (ordered chain)")
        _status("blocked", ddg_detail or "DDG HTML blocked")
        return []

    print(f"🦆 [DDG] HTML blocked — falling back to Bing (Chrome) for '{query}'")
    bing_st: dict = {}
    results = bing_search(query, num=num, page=1, status_out=bing_st)
    if results:
        _status("ok", f"DDG blocked ({ddg_detail}); Bing Chrome ok")
        return results
    bst = bing_st.get("status") or "empty"
    _status(
        "blocked" if bst == "blocked" else bst,
        f"DDG blocked ({ddg_detail}); Bing:{bst}"
        + (f" ({bing_st.get('detail')})" if bing_st.get("detail") else ""),
    )
    return results


# ─────────────────────────────────────────────────────────────────────────────
# Domain / email helpers
# ─────────────────────────────────────────────────────────────────────────────

def get_domain(s: str) -> str:
    if "@" in s:
        return s.split("@")[-1].lower()
    try:
        p = urlparse(s if "://" in s else "http://" + s)
        return p.netloc.replace("www.", "").lower()
    except Exception:
        return s.lower()


_JUNK_SUBDOMAINS = (
    "blog.", "news.", "press.", "media.", "jobs.", "careers.",
    "shop.", "store.", "support.", "help.", "community.", "forum.",
    "developers.", "dev.", "docs.", "status.", "ir.", "investors.",
    # Account / auth pages
    "login.", "signin.", "signup.", "register.", "account.", "accounts.",
    "auth.", "sso.", "portal.", "dashboard.", "app.",
    # Misc junk
    "finance.", "obs-settings.", "settings.", "ayuda.", "cdn.",
)

_IP_RE = re.compile(r"^\d{1,3}(\.\d{1,3}){3}$")

# Browser User-Agent pool — rotate to avoid simple bot detection
_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
]

_JUNK_DOMAIN_FRAGMENTS = (
    "zoominfo", "crunchbase", "pitchbook",
    "statista", "ibisworld", "grandviewresearch", "mordorintelligence",
    "marketsandmarkets", "alliedmarketresearch", "sphericalinsights",
    "precedenceresearch", "valuatesreports", "reportsanddata",
    "businessresearchinsights", "expertmarketresearch", "imarcgroup",
    "fortunebusinessinsights", "coherentmarketinsights",
    "databridgemarketresearch", "researchandmarkets",
    # Company aggregators / directories
    "superbcompanies", "companiesmarket", "companydata",
    "techbehemoths", "digitalagencynetwork", "agencyspotter",
    "agencyanalytics",
)

# Title/snippet signals that clearly indicate a non-content page
# (login walls, error pages, legal boilerplate) — NOT government/education
_JUNK_TITLE_SIGNALS = (
    "login", "sign in", "sign up", "create account", "forgot password",
    "404", "page not found", "access denied", "403 forbidden",
    "privacy policy", "terms of service", "cookie policy",
)


# Social / profile hosts — never company lead domains (LinkedIn is found later)
_SOCIAL_DOMAINS = (
    "linkedin.com", "facebook.com", "instagram.com", "twitter.com", "x.com",
    "youtube.com", "tiktok.com", "pinterest.com", "reddit.com",
)


def is_blocked(url: str) -> bool:
    """
    Returns True for junk/directory/aggregator/government/IP URLs that should
    never be treated as lead candidates.
    """
    d = get_domain(url)
    if not d:
        return True
    # Consumer Google Translate hosts (any ccTLD) — not lead companies
    if d.startswith("translate.google.") or d == "translate.google":
        return True
    # Block IP addresses
    if _IP_RE.match(d):
        return True
    # Never qualify social / LinkedIn profile pages as company domains
    if any(d == s or d.endswith("." + s) for s in _SOCIAL_DOMAINS):
        return True
    # Block .mil, .gov, .edu TLDs (including ccTLD variants like .gov.uk)
    parts = d.split(".")
    if parts[-1] in ("mil", "gov", "edu"):
        return True
    if len(parts) >= 3 and parts[-2] in ("gov", "edu"):
        return True
    if any(d.startswith(sub) for sub in _JUNK_SUBDOMAINS):
        return True
    bare = parts[0]
    if any(frag in bare for frag in _JUNK_DOMAIN_FRAGMENTS):
        return True
    return any(d == b or d.endswith("." + b) for b in BLOCKED_DOMAINS)


def is_relevant(text: str) -> bool:
    t = text.lower()
    return any(kw in t for kw in RELEVANCE_KEYWORDS)


def is_industry_match(title: str, snippet: str, industry_slug: str) -> bool:
    """
    Return True if the search result (title + snippet) is relevant to the
    searched industry.  If no industry is selected (slug is empty/None),
    always returns True — no filtering applied.

    Logic:
      1. If title contains an obvious junk signal → False immediately
      2. Combine title + snippet, check for at least one industry keyword
    """
    if not industry_slug:
        return True   # no industry filter selected

    keywords = INDUSTRY_KEYWORDS.get(industry_slug.lower(), [])
    if not keywords:
        return True   # unknown industry — don't filter

    combined = (title + " " + snippet).lower()

    # Hard reject on junk title signals
    title_lc = title.lower()
    if any(sig in title_lc for sig in _JUNK_TITLE_SIGNALS):
        return False

    # At least one industry keyword must appear in title+snippet
    return any(kw in combined for kw in keywords)


def clean_email(addr: str) -> str:
    return (addr or "").strip().lower()


def is_personal_email(email: str) -> bool:
    domain = email.split("@")[1].lower() if "@" in email else ""
    return domain in FREE_EMAIL_DOMAINS


_GENERIC_PREFIXES = {
    "info", "hello", "hola", "hi", "hey", "greetings",
    "team", "contact", "contactus", "contact-us", "contacts",
    "support", "help", "helpdesk", "service", "services",
    "sales", "marketing", "business", "commercial",
    "admin", "administration", "office", "mail", "mailbox",
    "enquiries", "enquiry", "queries", "query", "questions",
    "general", "reception", "welcome", "connect",
    "noreply", "no-reply", "donotreply", "do-not-reply",
    "billing", "accounts", "finance", "accounting", "invoice",
    "hr", "humanresources", "careers", "jobs", "recruitment", "hiring",
    "press", "media", "pr", "news", "newsletter", "updates",
    "legal", "privacy", "compliance", "abuse", "security",
    "webmaster", "postmaster", "it", "tech",
    "translations", "translation", "translate", "translators", "translator",
    "localization", "localisation",
    "crisis", "emergency", "urgent",
    "projects", "project", "pm", "operations",
    "quotes", "quote", "request", "rfq", "services", "service",
    "feedback", "complaints", "complaint", "invoice", "invoices",
    "purchase", "orders", "order", "payment", "payments",
    "newbusiness", "new-business", "new_business", "biz", "bizdev",
    "partnerships", "partnership", "apply", "vendor", "vendors",
    "solutions", "solution", "global",
}


def is_generic_email(email: str) -> bool:
    if "@" not in email:
        return False
    local = email.split("@")[0].lower().strip()
    if local in _GENERIC_PREFIXES:
        return True
    for prefix in _GENERIC_PREFIXES:
        if local.startswith(prefix) and len(local) <= len(prefix) + 3:
            return True
    return False


def is_institutional_email(email: str) -> bool:
    domain = email.split("@")[1].lower() if "@" in email else ""
    return domain.endswith(".mil")


def country_from_domain(domain: str) -> str:
    domain = domain.lower()
    for tld, country in sorted(TLD_COUNTRY.items(), key=lambda x: -len(x[0])):
        if domain.endswith(tld):
            return country
    return ""
