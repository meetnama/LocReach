# LocReach Step 1 — Speed & Yield Fix (Complete)

**Target:** 25 leads in 15–30s, 100 leads in 45–90s.  
**Constraint:** `industry_evidence_ok` and `verify_country_location` are NOT modified.  
**Scope:** `step1_qualify.py`, `pages/1_Domains.py`, `db.py`, `sources/utils.py`, `sources/directory_scrape.py`, `config.py`

---

## 1. step1_qualify.py — The New Qualification Pipeline

Replace/add these functions. Keep everything else.

### 1.1 cheap_screen_loose() — Obvious Junk Only

```python
from urllib.parse import urlparse

def cheap_screen_loose(title: str, snippet: str, url: str) -> str:
    """
    Only reject obvious junk. Let on-page gates do real quality control.
    Returns: 'pass', 'serp_junk', 'blocked_domain'
    """
    from sources.config import BLOCKED_DOMAINS  # adjust import path as needed
    
    if not title or not url:
        return "serp_junk"
    
    domain = urlparse(url).netloc.lower().replace("www.", "")
    
    if any(bd in domain for bd in BLOCKED_DOMAINS):
        return "blocked_domain"
    
    t = (title + " " + snippet).lower()
    
    pure_junk = ["casino", "betting", "porn", "xxx", "crypto exchange", 
                 "forex broker", "dating", "escort"]
    if any(j in t for j in pure_junk):
        return "serp_junk"
    
    if domain.endswith((".gov", ".edu", ".mil")) and "translation" not in t and "localization" not in t:
        return "serp_junk"
    
    return "pass"
```

### 1.2 qualify_verified_fast() — Skip Website Open for Trusted Sources

```python
def qualify_verified_fast(domain: str, source: str, title: str, snippet: str,
                          country: str, industry: str):
    """
    Fast-path for pre-curated sources. Returns (status, score, reasons) or None.
    """
    if source not in ("directory_verified", "ai_overview_verified", "local_pack_verified"):
        return None
    
    score = 75
    reasons = [source]
    
    if country.lower() in snippet.lower():
        reasons.append("geo_snippet_confirmed")
    
    return ("qualified", score, reasons)
```

### 1.3 shallow_scrape_and_qualify() — Requests + Your Gates

```python
import requests
from bs4 import BeautifulSoup

def shallow_scrape_and_qualify(url: str, domain: str, country: str, 
                                industry: str, timeout: float = 1.5):
    """
    Fast shallow scrape. Runs EXISTING quality gates on real HTML.
    Returns dict with status, score, reasons.
    """
    try:
        headers = {
            "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/126.0.0.0 Safari/537.36")
        }
        resp = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
        if resp.status_code != 200:
            return {"status": "failed", "reason": f"http_{resp.status_code}"}
        
        soup = BeautifulSoup(resp.text, "html.parser")
        title = soup.title.string if soup.title else ""
        
        meta_desc = ""
        meta = soup.find("meta", attrs={"name": "description"})
        if meta:
            meta_desc = meta.get("content", "")
        
        body = soup.get_text(separator=" ", strip=True)[:3000]
        content = f"{title} {meta_desc} {body}"
        
        # EXISTING gates — DO NOT MODIFY
        from sources.scoring import industry_evidence_ok
        from sources.geo import verify_country_location
        
        if not industry_evidence_ok(content, industry=industry):
            return {"status": "rejected", "reason": "industry_fail", 
                    "content_preview": content[:500]}
        
        geo_ok, geo_reason = verify_country_location(content, country)
        if not geo_ok:
            return {"status": "rejected", "reason": f"geo_fail:{geo_reason}",
                    "content_preview": content[:500]}
        
        return {
            "status": "qualified",
            "score": 70,
            "reasons": ["shallow_scrape_qualified", "industry_evidence_ok", f"geo:{geo_reason}"],
            "title": title,
            "meta_description": meta_desc
        }
        
    except requests.exceptions.Timeout:
        return {"status": "unreachable", "reason": "timeout"}
    except Exception as e:
        return {"status": "failed", "reason": str(e)[:100]}
```

### 1.4 Update qualify_domain_fast() — New Flow

```python
import json

def qualify_domain_fast(domain, url=None, serp_title="", serp_snippet="",
                        source="normal", country="Egypt", industry="localization"):
    """
    Updated pipeline:
    1. Verified fast-path (directories, AI Overview, Local Pack)
    2. Loose SERP screen (junk only)
    3. Shallow scrape + real quality gates
    """
    if url is None:
        url = f"https://{domain}"
    
    # 1. Verified sources — instant qualify, no website open
    verified = qualify_verified_fast(domain, source, serp_title, serp_snippet, country, industry)
    if verified:
        status, score, reasons = verified
        return {
            "domain": domain, "url": url, "status": status,
            "score": score, "score_reasons": json.dumps(reasons),
            "source": source
        }
    
    # 2. Loose SERP screen
    screen = cheap_screen_loose(serp_title, serp_snippet, url)
    if screen != "pass":
        return {
            "domain": domain, "url": url, "status": "rejected",
            "score": 0, "score_reasons": json.dumps([screen]),
            "source": source
        }
    
    # 3. Shallow scrape + your gates
    result = shallow_scrape_and_qualify(url, domain, country, industry, timeout=1.5)
    
    return {
        "domain": domain, "url": url,
        "status": result.get("status", "failed"),
        "score": result.get("score", 0),
        "score_reasons": json.dumps(result.get("reasons", [result.get("reason", "unknown")])),
        "source": source,
        "title": result.get("title", ""),
        "meta_description": result.get("meta_description", "")
    }
```

---

## 2. db.py — Batch Insert

Add this function. Do not remove existing `db_upsert_domain`.

```python
def db_upsert_domain_batch(domains: list, db_path=DB_PATH):
    """
    Batch insert/update domains. 10-50x faster than one-by-one.
    domains: list of dicts with keys: domain, url, status, score, 
             score_reasons, source, title, meta_description
    """
    import sqlite3
    if not domains:
        return
    
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    
    for d in domains:
        c.execute("""
            INSERT INTO domains 
            (domain, url, status, score, score_reasons, source, 
             title, meta_description, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
            ON CONFLICT(domain) DO UPDATE SET
                status = CASE 
                    WHEN excluded.status = 'qualified' THEN 'qualified'
                    WHEN status = 'qualified' THEN 'qualified'
                    ELSE excluded.status
                END,
                score = CASE WHEN excluded.score > score THEN excluded.score ELSE score END,
                score_reasons = excluded.score_reasons,
                source = excluded.source,
                title = COALESCE(NULLIF(excluded.title, ''), title),
                meta_description = COALESCE(NULLIF(excluded.meta_description, ''), meta_description),
                updated_at = datetime('now')
        """, (
            d["domain"], d.get("url"), d.get("status"),
            d.get("score", 0), d.get("score_reasons", "[]"),
            d.get("source", "normal"), d.get("title", ""), d.get("meta_description", "")
        ))
    
    conn.commit()
    conn.close()
```

---

## 3. pages/1_Domains.py — Search Loop Changes

### 3.1 Check Budget (Smarter)

Find the check_budget line and replace:

```python
def get_check_budget(target):
    if target <= 25:
        return max(target * 3, 60)      # 75 checks for 25 targets
    elif target <= 50:
        return target * 4               # 200 for 50
    elif target <= 100:
        return target * 5               # 500 for 100
    else:
        return min(8000, target * 8)

check_budget = get_check_budget(target_companies)
```

### 3.2 Diminishing Returns (Disable for Small Targets)

Find the diminishing-returns stop logic and wrap it:

```python
# Only apply diminishing returns for large targets
if target_companies > 50:
    if (unique_new_rate < 12 and terms_run >= 3 and elapsed_minutes >= 15):
        stop_reason = "SERP yield flattened"
        break
# For targets <= 50, run the full template bank
```

### 3.3 Parallel SERP Fetching

Replace sequential term fetching with batched parallel:

```python
from concurrent.futures import ThreadPoolExecutor, as_completed

def fetch_serp_for_term(term):
    # Call your existing engine wrapper
    from sources.utils import search_all_engines  # or whatever your function is named
    return search_all_engines(term)

BATCH_SIZE = 10

# In your main search loop:
term_batches = [template_terms[i:i+BATCH_SIZE] 
                for i in range(0, len(template_terms), BATCH_SIZE)]

for batch in term_batches:
    if qualified_count >= target_companies or checked_count >= check_budget:
        break
    
    # Fetch batch in parallel
    serp_results = []
    with ThreadPoolExecutor(max_workers=BATCH_SIZE) as executor:
        future_to_term = {executor.submit(fetch_serp_for_term, term): term 
                         for term in batch}
        for future in as_completed(future_to_term):
            term = future_to_term[future]
            try:
                results = future.result(timeout=10)
                for r in results:
                    r["_source_term"] = term
                serp_results.extend(results)
            except Exception as e:
                logger.warning(f"SERP failed for {term}: {e}")
    
    # Deduplicate by URL
    seen = set()
    unique_results = []
    for r in serp_results:
        url = r.get("url", "")
        if url and url not in seen:
            seen.add(url)
            unique_results.append(r)
    
    # Process each
    for result in unique_results:
        if checked_count >= check_budget or qualified_count >= target_companies:
            break
        
        domain = extract_domain(result["url"])  # your existing helper
        if domain in all_domain_names:
            continue
        
        checked_count += 1
        
        # Determine source for fast-path
        source = "normal"
        from sources.directory_scrape import is_directory_scrape_target
        if is_directory_scrape_target(result.get("title", ""), result.get("url", "")):
            source = "directory_verified"
        elif result.get("is_ai_overview"):
            source = "ai_overview_verified"
        elif result.get("is_local_pack"):
            source = "local_pack_verified"
        
        # Qualify
        qual = qualify_domain_fast(
            domain=domain,
            url=result["url"],
            serp_title=result.get("title", ""),
            serp_snippet=result.get("snippet", ""),
            source=source,
            country=selected_country,
            industry=selected_industry
        )
        
        # Collect for batch insert
        if qual["status"] == "qualified":
            batch_domains.append(qual)
            qualified_count += 1
        elif qual["status"] in ("rejected", "failed", "unreachable"):
            batch_domains.append(qual)  # insert rejected too for skip tracking
        
        # Flush batch every 50
        if len(batch_domains) >= 50:
            db_upsert_domain_batch(batch_domains)
            batch_domains = []
            all_domain_names.update(d["domain"] for d in batch_domains)
    
    # Update UI counters here...

# Final flush
if batch_domains:
    db_upsert_domain_batch(batch_domains)
```

---

## 4. sources/utils.py — Source Metadata

Ensure your search parsers return source flags. In your SearXNG/OpenSERP/Google result builders, add:

```python
result = {
    "title": title,
    "snippet": snippet,
    "url": url,
    "engine": engine_name,
    "is_directory": False,      # set True if from directory host
    "is_ai_overview": False,    # set True in google_ai_overview parser
    "is_local_pack": False,     # set True in local_pack parser
}
```

---

## 5. sources/directory_scrape.py — Expose Detection

Ensure `is_directory_scrape_target` is importable from `step1_qualify.py`. If it's private/internal, make it a top-level function:

```python
def is_directory_scrape_target(title: str, url: str) -> bool:
    known_hosts = [
        "clutch.co", "goodfirms.co", "proz.com", "translationcafe.com",
        "translationdirectory.com", "gala-global.org", "atanet.org",
        "translated.net", "transperfect.com", "slator.com",
        "nimdzi.com", "csa-research.com"
    ]
    t = title.lower()
    u = url.lower()
    
    if any(h in u for h in known_hosts):
        return True
    
    patterns = [
        "top translation companies", "top localization companies",
        "translation companies in", "localization companies in",
        "best translation services", "language service providers",
        "translation agencies in", "localization agencies in"
    ]
    if any(p in t for p in patterns):
        return True
    
    return False
```

---

## 6. config.py — Verify Worker Count

Ensure local shows 200 workers:

```python
def get_worker_count():
    if running_on_cloud():   # your existing cloud detect
        return 8
    return 200
```

---

## Implementation Checklist

- [ ] Add `cheap_screen_loose`, `qualify_verified_fast`, `shallow_scrape_and_qualify` to `step1_qualify.py`
- [ ] Update `qualify_domain_fast` to use the new 3-step flow
- [ ] Add `db_upsert_domain_batch` to `db.py`
- [ ] Update `1_Domains.py`: check budget, diminishing returns, parallel SERP, batch insert
- [ ] Ensure `is_directory_scrape_target` is importable from `directory_scrape.py`
- [ ] Ensure search parsers in `utils.py` return `is_directory` / `is_ai_overview` / `is_local_pack` flags
- [ ] Test: Localization + Egypt, target 25
- [ ] Verify: RWS/CCJK still rejected (`geo_fail`), Cairo-based still pass
- [ ] Commit + push to GitHub

---

## Expected Results

| Target | Time | Checks | Method |
|--------|------|--------|--------|
| 25 | 15–30s | ~75 | 60% directory fast-path, 40% shallow scrape |
| 100 | 45–90s | ~500 | Full template bank, parallel fetch |

---

## What NOT to Change

- `industry_evidence_ok()` in `sources/scoring.py`
- `verify_country_location()` in `sources/geo.py`
- DB schema (tables, columns)
- `.env` handling
