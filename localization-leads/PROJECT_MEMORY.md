# LocReach Lead Discovery — Project Memory

_Last updated: 2026-07-23 (session 39 — verified-first Step 1: panels, directories, SERP summary, then normal qualify)_

**Read this first in every new session.** This file is the authoritative snapshot of how the app works *today*. Older user-facing docs (`Setup/README.txt`, desktop `Chats.txt`, Arabic summaries) may still describe the **old 4-step pipeline** (`discovered_domains` + `verified_companies` + separate Site Scanner). The live app is a **3-step unified pipeline** with a single `domains` table.

---

## Current product (2026-07-23)

| Item | Value |
|------|--------|
| **Product name** | **LocReach** (UI, launchers, exports) |
| **Purpose** | B2B lead-gen for localization/translation: find qualified companies → decision-makers → confirmed work emails |
| **Stack** | Streamlit (Python), SQLite (`leads.db`), undetected-chromedriver, SearXNG + OpenSERP (Docker), Groq (optional classifier) |
| **Entry point** | `Domain_Discovery.py` via `st.navigation(position="top")` |
| **Launcher** | `Setup/6 - Start LocReach.bat` → auto-starts SearXNG + OpenSERP when possible, then `pythonw run_app.py` |
| **Ports** | Streamlit `:8501`, heartbeat `:8502`, SearXNG `:8888`, OpenSERP (local Docker) |
| **Tests** | `test_scoring` + `test_ai_overview` + `test_directory_scrape` + `test_serp_summary` (21+ related); re-run `pytest tests/ -q` after Step 1 changes |
| **Step 1 log** | `localization-leads/logs/step1_search.log` (weekly autoclean on run start) |
| **Launcher log** | `localization-leads/logs/run_app.log` (shutdown reason: `/closing` vs heartbeat timeout) |

### 3-step pipeline (live)

| Step | Page | What it does | DB output |
|------|------|--------------|-----------|
| **Home** | `pages/0_Home.py` | Dashboard; step **buttons**; Open Database; full-DB Excel; Danger Zone reset (`db_wipe_all`) | reads only |
| **1** | `pages/1_Domains.py` | **Verified-first** harvest → then cheap screen → scrape/score → industry → geo | `domains` + `score_reasons` tags |
| **2** | `pages/2_People.py` | Classify LSP/client → X-Ray → optional LinkedIn `/people` → website → title filter | `people` |
| **3** | `pages/3_Emails.py` | L1 site → L2 EmailFormat+SMTP → L4 SearXNG; confirmed only | `leads` |
| **Database** | `pages/4_Database.py` | Browse Domains / People / Leads / Blocked | reads only |

**Product direction:** Discover + export only (no import). Per-run Excel on Steps; full-DB Excel on Home.

### Step 1 — verified-first architecture (session 39)

**Priority before any website open / `qualify_domain_fast`:**

| # | Technique | Where | DB `score_reasons` |
|---|-----------|--------|-------------------|
| 1 | Directory / industry-dir SERP queries first in bank | `directory_search_queries` → `_build_template_bank` | (feeds #3) |
| 2 | Google AI Overview + Local Pack (Maps businesses) | `_PARSE_AI_OVERVIEW_JS` / `_PARSE_LOCAL_PACK_JS`; raced ∥ SearXNG/OpenSERP on page-1 via `google_ai_overview` | `ai_overview_verified` / `local_pack_verified` |
| 3 | Directory / Top-N scrape | `sources/directory_scrape.py` (`is_directory_scrape_target`, `scrape_directory_companies`); hosts: Clutch, GoodFirms, **Proz**, TranslationCafe, TranslationDirectory, GALA, ATA, … | `directory_verified` |
| 4 | SERP title+snippet: industry ≥1 keyword + location | `serp_summary_verified` / `serp_summary_has_industry` in `step1_qualify.py` | `serp_summary_verified` |
| 5 | **Normal path only after priority pass** | `cheap_screen_candidate` → `_qualify_one` / `qualify_domain_fast` | score/geo reasons |

- Hygiene for verified paths: `ai_overview_screen` (blocked / duplicate / foreign ccTLD only) → `qualify_from_ai_overview(..., source=…)`
- Directory **host** never qualified as a lead (still in `BLOCKED_DOMAINS`); only listed company domains
- Caps: `_MAX_DIRECTORY_SCRAPES=12`, `_MAX_COMPANIES_PER_DIRECTORY=40`
- Per-page: `_result_verified_priority` sorts hits; **Priority pass** then **Normal pass** (UI engine notes)
- Score sentinel for verified: 70 / `strong`

**Normal path keep order (session 38, still applies to pass 5):** industry first (`industry_evidence_ok`), then country geo (`verify_country_location`).

**Cheap SERP screen (pass 5 only):** `serp_suggests_industry` (strict — not lone ambiguous “localization”) + `serp_suggests_country`; reject junk/listicle/foreign/`serp_irrelevant`/`serp_geo_miss`; persist as `failed`.

**On-page (pass 5):** `score_company` + `industry_evidence_ok` ≥2 strong or 1 strong+≥3 hits; then geo (ccTLD / HQ / city; phone alone never enough).

**DB skip:** `blocked_domains` + all `domains` names. Reset = `db_wipe_all` (all tables); Score-0 rejects are intentional skip-set fills after wipe+re-run.

### Step 1 search / throughput (current)

| Piece | Behavior |
|-------|----------|
| **Template bank** | Directory queries **first** → primary → expansion → rotation (`_build_template_bank`) |
| **Engine race (page-1)** | SearXNG ∥ OpenSERP ∥ **Google panels**; panels prepended; then Google gap-fill → Bing → DDG |
| **Workers** | Fixed **200** |
| **Check budget** | `min(15000, max(target×25, 800))` |
| **Diminishing returns** | ≥3 terms / 15‑min, &lt;12 unique-new/hr → stop |
| **UI stats** | This-run only; no full-DB embed on Step 1 |

### Title filter (Step 2)

`sources/people/title_filter.py` — project manager, vendor manager, translation manager only.

### Email layers (Step 3)

L1 site / L2 EFmt+SMTP / L4 SearXNG. Gate: `lead_gate.is_confirmed_lead()`.

### Launcher / heartbeat

Parent `window.parent` ping; `SHUTDOWN_TIMEOUT` **180s**. **Still needs** full restart + long Step 1 live-validate.

**Restart rule:** After code changes, fully restart via `6 - Start LocReach.bat`.

---

## UI architecture (2026-07-22)

| Component | Status |
|-----------|--------|
| **Framework** | Streamlit; read-only Jinja embeds via `template_render.py` + `components.html` |
| **Design system** | `ui_theme.py` — Email_Tools palette |
| **Navigation** | Top tabs + sidebar (`inject_theme` → `sidebar_pipeline_nav`) |
| **Home button** | Every page **except** Home |
| **Pipeline steps (Home)** | `pipeline_cards` → real `st.button` + `st.switch_page` (same as Open Database). No HTML cards/Open→/descriptions/stat captions |
| **Database page** | Domains table: Domain as **link**, sorted by **Score**, no Status/Keyword/Type/date cols |
| **Jinja embeds** | Home pipeline snapshot; Step 2/3 DB tables; Step 1 full-DB embed **gone** |

---

## Repository map

```
Sales_Tool/                              # Git root
├── Setup/                               # Windows .bat launchers (path-independent via %~dp0)
│   ├── 1 - Get Python.bat
│   ├── 2 - Get Chrome.bat
│   ├── 3 - Get Docker.bat
│   ├── 4 - Install LocReach.bat         # prereq checks + venv + Desktop/Start Menu shortcut
│   ├── 5 - Start SearXNG.bat
│   ├── 6 - Start LocReach.bat           # auto-starts SearXNG + OpenSERP when possible, then app
│   ├── 7 - Start OpenSERP.bat
│   ├── README.txt
│   └── MOVE TO NEW PC.txt
├── searxng/
│   └── settings.yml                     # AUTHORITATIVE; must include `- json` in formats
├── localization-leads/                  # Main Python app
│   ├── Domain_Discovery.py
│   ├── run_app.py
│   ├── ui_theme.py
│   ├── template_render.py               # Jinja→Streamlit bridge (read-only embeds)
│   ├── db.py                            # CRUD; db_load_all_domain_names; db_demote_geo_rejects (promote disabled)
│   ├── step1_qualify.py                 # verified fast-path + cheap_screen + qualify_domain_fast
│   ├── scanner.py / scoring.py (industry_evidence_ok) / config.py (+ COUNTRY_GEO) / export_excel.py
│   ├── pages/0_Home.py … 4_Database.py  # 1_Domains: verified-first two-pass harvest
│   ├── sources/utils.py                 # Google Chrome SERP + AI Overview + Local Pack parsers
│   ├── sources/directory_scrape.py      # directory/listicle + LSP dirs; directory_search_queries
│   ├── sources/geo.py                   # serp_suggests_country + verify_country_location
│   ├── sources/email/… , sources/people/…
│   ├── templates/                       # Jinja embeds (read-only)
│   ├── tests/                           # scoring + ai_overview + directory_scrape + serp_summary
│   ├── logs/
│   │   ├── run_app.log
│   │   └── step1_search.log             # Step 1 search diagnostics (weekly autoclean)
│   ├── leads.db
│   ├── .env
│   ├── .streamlit/config.toml
│   ├── .chrome_profile/
│   └── venv/
└── .cursorrules                         # NOT on disk (session 36) — Cursor still injects the LocReach design rule; likely a User/Project rule in Cursor settings
```

**Removed 2026-07-16 (tooling only — not required to run LocReach):** `.claude/`, `localization-leads/.claude/`, `.zcode/`, `.repowise*`, `.repowise-workspace.yaml`. Optional Cursor files may remain: `.cursorignore`, `.mcp.json`.

---

## DB schema (current — `leads.db`)

| Table | Purpose |
|-------|---------|
| `domains` | **Unified Step 1 output** — `status`: discovered / qualified / rejected; scoring fields; `company_type`; `people_searched_at` |
| `people` | Step 2 contacts — `UNIQUE(domain, full_name)`; `email_searched_at` |
| `leads` | Step 3 confirmed emails — `UNIQUE(email)` |
| `blocked_domains` | Junk filtered in search — never revisited |

**Legacy tables removed:** `discovered_domains`, `verified_companies`, `processed_domains`.

**Key DB functions:** `db_init`, `db_upsert_domain`, `db_load_all_domain_names`, `db_load_kept_domain_names`, `db_promote_stale_rejects`, `db_load_qualified_domains`, `db_insert_person`, `db_mark_company_people_done`, `db_load_people_without_email`, `db_insert_lead`, `db_mark_person_email_done`, `db_count_domains`, `db_count_leads`

---

## How to launch

**Daily use:**
1. Docker Desktop running (recommended for SearXNG/OpenSERP)
2. `6 - Start LocReach.bat` → backends + browser `http://localhost:8501`
3. Top nav: Home → Step 1 → Step 2 → Step 3
4. Close LocReach browser tab to stop (watchdog kills Streamlit)

**First-time / new PC:** `1 → 2 → (3) → 4 → (5) → 6`. Copy `leads.db` + `.env` to preserve data.

**Clean Step 1 re-test:** stop LocReach → delete `localization-leads/leads.db` (+ wal/shm if any) → restart → re-run. Same market without wipe mostly hits already-qualified skips + duplicate SERPs.

**Env vars:** `LOCREACH_HEARTBEAT_PORT` (default 8502), `LOCREACH_NO_BROWSER=1`, `SEARXNG_URL`, `GROQ_API_KEY`, `LINKEDIN_EMAIL`, `LINKEDIN_PASSWORD`

---

## Export (current — session 38)

**Per-run on each Step; full DB on Home (category sheets).**

| Location | Button | Builder | Output |
|----------|--------|---------|--------|
| Step 1 | 📊 Download Excel (this run) | `build_step1_excel_bytes(qualified, rejected_rows=…)` | Qualified + optional **Not Kept** |
| Step 2 | HTML + Excel (this run) | `build_people_excel_bytes` | this run's people |
| Step 3 | HTML + Excel (this run) | `build_leads_excel_bytes` | this run's leads |
| **Home** | 📊 Export full database | `build_excel_bytes(DB_PATH)` | Summary + **Qualified/Rejected/Failed/Unreachable/Discovered** + People + Leads + Blocked |

- Per-run = session only. Full DB = all markets/runs, split by domain `status`.
- Home Danger Zone reset unchanged (`db_wipe_all`).

**Env / deps:** `GROQ_API_KEY`, LinkedIn creds, `SEARXNG_URL`; **dnspython** required for L2 SMTP.

---

## Session 39 (2026-07-23) — verified-first Step 1

**Shipped**
- AI Overview + Local Pack Chrome parsers (`sources/utils.py`); `google_ai_overview`
- `sources/directory_scrape.py` — general + LSP dirs (Proz, TranslationCafe, …); `directory_search_queries`
- `serp_summary_verified` — title+snippet industry≥1 + geo → no site open
- `qualify_from_ai_overview` sources: `ai_overview` / `local_pack` / `directory` / `serp_summary`
- Priority bank + two-pass harvest in `pages/1_Domains.py` (`_result_verified_priority`, `_ingest_verified_company`)
- Tests: `test_ai_overview.py`, `test_directory_scrape.py`, `test_serp_summary.py`

**Still pending:** heartbeat live-validate; demote old pre-gate qualified; tighten city-only geo; more industry dirs as needed

---

## Session 38 (2026-07-22) — industry-first gates, SERP open gate, UI/export polish

**Qualification**
- SERP title/snippet = first open gate for **industry + geo** (`serp_suggests_industry`, `serp_suggests_country`, `serp_geo_miss`)
- On-page: industry mandatory via `industry_evidence_ok`; then geo
- Geo: phone alone insufficient; bare `+20` / dialling-code lists ignored; need city or HQ (or own ccTLD)
- False-positive lessons: ulatus.com (form `Egypt (+20)`); aimr/evma/hbc (lone “localization” + city/.eg)

**UI / UX**
- Home: Open Database **button**; full-DB export button; Recommended Flow removed; pipeline = `st.button` steps (no card HTML/Open→/stats)
- Step 1: no full-DB qualified embed; no DB cumulative caption under cards; workers UI removed → **200** fixed
- Database: Domain link; sort by Score; drop Status/Keyword/Type/dates

**Export:** Home full DB by category sheets; Step 1 Not Kept sheet from `s1_rejected_log`

**Not live-validated:** heartbeat 180s / parent ping still needs one long Step 1 after full restart

---

## Session 36 (2026-07-19) — palette, geo gate, reset button, export split

**1. Email_Tools color palette (all pages).** Ported the sibling project `D:\Work\Email_Tools`'s palette. Kept LocReach token names, repointed values: `reach`→blue `#3b82f6`, `signal`→purple `#a855f7`, `qualified`→emerald (unchanged), `pipeline`→orange `#f97316`. Files: `ui_theme.py` (token dicts + rgba triples `20,184,166→59,130,246`, `14,165,233→168,85,247`, `245,158,11→249,115,22` + bg tint), `.streamlit/config.toml`, `templates/_embed_base.html` + `_base.html` (full Tailwind scales), inline hexes in the 3 step pages, `export_excel.py` accent cells. Deliberate cross-page change (overrides the old teal palette + one-page rule).

**2. Geographic qualification gate.** Location was previously only a SERP query hint, never verified → global vendors (RWS/CCJK/TridIndia/BLEND/…) qualified for Egypt. Added `sources/geo.py::verify_country_location` + `config.py::COUNTRY_GEO`; enforced in `qualify_domain_fast` via new `strict_location` param; UI toggle in `1_Domains.py` (default ON). See "Qualification gate" section. Smoke-tested: RWS/TridIndia/"serves Egypt market" → rejected; "Cairo, Egypt +20" / "based in Egypt" → kept.

**3. DB reset button (Home).** `pages/0_Home.py` Danger Zone → confirm-gated 🗑️ Reset → `db_wipe_all` + banner.

**4. Export restructure.** Per-run Excel on each step page (new `build_people_excel_bytes` / `build_leads_excel_bytes` in `export_excel.py`; Step 1 button relabeled "this run"); whole-DB Excel moved to Home 📦 Export. See "Export" section.

**Notes:** all edited files byte-compile (used `required_permissions:["all"]` — Windows sandbox blocks shell otherwise). `.cursorrules` **does not exist on disk** (Test-Path False, untracked) though Cursor still injects the LocReach design-system rule into sessions — likely a User/Project rule in Cursor settings, not a repo file. User deferred hunting it down.

---

## Session 35 (2026-07-18) — Jinja→Streamlit read-only embed bridge

**Goal:** Wire the orphaned `templates/` Jinja/Tailwind design into the live Streamlit app.

**Key finding:** `ui_theme.py` already reproduces the Tailwind design system on native widgets, and `templates/*.html` (domains/people/emails) are Flask-oriented mockups whose buttons can't call Python from a Streamlit iframe. So a **full** wire-up is not viable without a Flask migration (forbidden by `.cursorrules`).

**What shipped (read-only embed pattern):**
1. `template_render.py` — Jinja `Environment` on `templates/`; `render_qualified_db_table` / `render_people_db_table` / `render_leads_db_table` / `render_pipeline_snapshot`; `table_embed_height` (alias `qualified_db_table_height`).
2. `templates/_embed_base.html` — lightweight base (Tailwind CDN + tokens) for iframe embeds; separate from `_base.html`.
3. Partials: `_db_domains_embed.html`, `_db_people_embed.html`, `_db_leads_embed.html`, `_pipeline_snapshot_embed.html`.
4. Pages wired via `st.components.v1.html`:
   - `1_Domains.py` → "All Qualified Domains in DB" (`db_load_qualified_domains`)
   - `2_People.py` → "All People in DB" (`db_load_people`, reuses top-of-page `_existing`)
   - `3_Emails.py` → "All Leads in DB" (`db_load_leads`, short read conn at render)
   - `0_Home.py` → "Pipeline Snapshot" funnel panel
5. Embeds render only when a run isn't active and only when data exists (no interference with search/qualify/find flows). No native `section_label` above them — the Jinja card carries its own titled header.

**Process notes:**
- User explicitly **overrode** the `.cursorrules` "one page per chat / no batch redesign" guardrail for this session.
- Verified: all pages compile; all partials render; browser check on `:8599` confirmed Home snapshot + Domains 105-row DB table render live and match the design.
- Also recreated Desktop/Start Menu shortcuts to the new `Setup/` path (`Setup/Create LocReach Shortcut.bat`).

---

## Session 34 (2026-07-15 → 2026-07-16) — Step 1 volume, bugs, UI, coverage

### Throughput / funnel
1. **`check_budget`:** `target×3` → **`target×25`** (cap 15 000, floor 800) — fixed premature 13/100 stop.
2. **Expansion + deep pagination** — more terms/pages for large targets.
3. **SERP pre-filter relaxed**; qualify gate loosened (possible kept; LinkedIn optional).
4. **Skip set** = blocked + qualified only; **`db_promote_stale_rejects`**.
5. **Parallel free-engine race**; workers **16/32/48** (default 32); pipelined qualify.

### Critical bugfixes (Egypt 100)
1. **Query-loop indent bug** in `1_Domains.py` — search body sat **outside** `for query` → only **one** term ran → false `search_exhausted`. **Fixed.**
2. **OpenSERP** `NameError: results is not defined` in `sources/utils.py` — missing `results = []`. **Fixed.**
3. **Clean re-test:** wiped `leads.db`; after fixes → **105/100 `target_met`** (~5 min, 6 terms, SearXNG+OpenSERP healthy).

### Coverage (no import)
- **Auto-rotate** unused template bank (`_build_template_bank` / `_rotation_extra_queries`).
- Stop **`diminishing_returns`** when unique-new qualified rate collapses (&lt;12/hour over 15 min, ≥3 terms).
- **Import domain list** was prototyped then **removed** — product stays discover → export.

### UI / logging
- Debug expander + verbose engine status → **`logs/step1_search.log`** (7‑day autoclean).
- One custom progress bar; `step_indicator` = **current step only**.
- Status captions → **DB stats** for selected industry/country (not check-budget prose).
- Junk domain blocks expanded in config as needed.

### Install / disk
- Verified install bats 1–4; **6** auto-starts SearXNG + OpenSERP; Desktop/Start Menu shortcuts.
- Disk cleanup: Chrome profile caches / temp docs removed; **venv kept**.

### Tooling cleanup (repo root)
- Deleted Claude / Z.ai / Repowise folders: `.claude`, `localization-leads/.claude`, `.zcode`, `.repowise*`, `.repowise-workspace.yaml`. LocReach runtime unchanged.

---

## Session 31 (2026-07-10) — bug fixes + UI stabilisation

### Bugs fixed
1. **`export_excel.py`** — use `domains` (was legacy tables).
2. **`1_Domains.py`** — worker uses own `wconn` (thread-safe).
3. **`3_Emails.py`** — always drain queue; L2 gate via `lead_gate.py`.
4. **`ui_theme.py`** — remove duplicate nav from `inject_theme()`.
5. **`1_Domains.py`** — count `unverified` in Failed.

### Tests added
- `tests/test_export_excel.py`, `tests/test_email_gate.py` → **20 passing**

---

## Session 30 (2026-07-09) — qualification tightening (partially superseded)

- Original hard gate: LinkedIn **+** strong/possible — **later relaxed** (session 34): LinkedIn optional; possible still kept.
- `is_quality_site()` content keyword check; industry slug fix.
- Title filter → 3 roles; L3 removed; 45s watchdog / slower refresh.

---

## Session 29 (2026-07-09) — hamburger menu

- `.streamlit/config.toml` → `toolbarMode = minimal`

---

## Sessions 17–28 — historical notes (condensed)

<details>
<summary>Old 4-step architecture (superseded)</summary>

Before the 2026-06/07 rebuild: Domain Discovery → Site Scanner → People → Email (with L3 PatVfy). Fully superseded by unified 3-step + `domains` table.
</details>

<details>
<summary>Key historical fixes still relevant</summary>

- **dnspython:** required for L2 SMTP
- **SearXNG `- json`:** in `Sales_Tool/searxng/settings.yml` only
- **Install bats:** `cd /d "%~dp0..\localization-leads"`
- **LinkedIn auto-login** + `.chrome_profile/LocReach`
- **Heartbeat** must bind `window.parent` or page-switch kills the app
</details>

---

## Pending / open items

| Item | Notes |
|------|-------|
| Jinja interactive templates | Still unused Flask-oriented mockups; read-only embeds only |
| Same-market re-runs | Skip-all-seen + dim-returns → often **0 new** when DB saturated (expected) |
| Industry false positives | Weak keyword hits can still score `possible` (e.g. news sites); SERP prefilter helps but not perfect |
| Geo false negatives | Local firms lacking city/phone/HQ text may be rejected |
| Google CAPTCHA | Still limits gap-fill |
| Country filter on exports | Open question from session 36 — still deferred |
| Pipeline card click UX | Transparent button overlay over cards — works; may need polish if hit-area drifts |
| `.cursorrules` location | User deferred (User vs Project rule) |

---

## Session 37 (2026-07-21 → 2026-07-22) — geo always-on, SERP filter, DB view, nav, ETA, heartbeat, geo demote

### Step 1 / qualify
1. Removed **"Only companies based…"** checkbox → `strict_location = True` always.
2. SERP title/snippet prefilter in `cheap_screen_candidate` (junk/listicle/irrelevant/foreign ccTLD); Arabic allow-path; persist SERP rejects.
3. Persist **failed** + **unreachable** to DB; skip via `db_load_all_domain_names`.
4. ETA recalibrated (`_KEEP_RATE_TYPICAL` 0.10, wall sec/check @48); UI = one Estimated + one Consumed.
5. Removed workers pipeline caption + auto-cities caption + redundant ETA boxes.
6. **`db_promote_stale_rejects` disabled**; **`db_demote_geo_rejects`** added — cleaned 169 geo_fail “qualified” (tuko.co.ke etc.).

### UI / nav
1. `pages/4_Database.py` — full DB browser; Home Excel whole-DB button replaced with link.
2. Sidebar nav restored via `inject_theme`; Home shortcut except on Home.
3. Pipeline cards clickable (`switch_page`); Open Step footer removed.
4. `pandas` added to `requirements.txt`.

### Stability
1. Heartbeat on `window.parent` with parent-scoped ping/interval.
2. `SHUTDOWN_TIMEOUT` 180s; shutdown reason logged in `run_app.log`.

### Live observations
- Saturated Egypt Localization DB → second run 0 qualified + `diminishing_returns` (expected).
- UI “this run” ≠ cumulative DB counts.
- Connection error was watchdog kill, not user close.

---

## Strategic context (from user chats — not fully implemented)

- Autonomous BD platform vision (discover → qualify → outreach → CRM) — **out of current scope**
- **Current scope:** Steps 1–3 + export only
- **Markets:** LSPs first (e.g. Localization + Egypt validated at 100+), then adjacent industries

---

## Quick troubleshooting

| Problem | Fix |
|---------|-----|
| Step 1 stops ~13/100 early | Ensure code has `check_budget` ×25; **full app restart** |
| Step 1 ends in ~40s with 1 TERM in log | Old indent bug — update `1_Domains.py`; log must show many `TERM` lines |
| `OpenSERP unavailable — name 'results' is not defined` | Fixed in `utils.py` (`results = []`); restart app |
| Excel export fails | Session 31 domains fix — update code / reinstall deps |
| Orange/empty SearXNG | Docker + `6` or `5`; check `settings.yml` has json |
| Step 3 no emails | dnspython; port 25 blocked → rely on L1/L4 |
| Connection error mid-run | Was iframe heartbeat + 45s watchdog — fixed session 37 (parent heartbeat, 180s). Check `logs/run_app.log` for shutdown reason. Restart via `6 - Start LocReach.bat` |
| App dies mid-scan | Don’t close LocReach tab; after fix, remounts shouldn’t kill. Memory Saver: exclude localhost |
| Foreign domains in qualified | Run Step 1 once (auto `db_demote_geo_rejects`) or call demote; promote path disabled |
| Clean Step 1 market test | Home Danger Zone reset / delete `leads.db` → restart → re-run |
| Chrome/LinkedIn weird | Delete `.chrome_profile/`, re-login |
| Second run 0 qualified | Expected if market already in DB (skip-all + dim-returns) |

**Step 1 diagnosis:** read `localization-leads/logs/step1_search.log` after each run (not the UI).

---

## Test command

```powershell
cd D:\LocHere\Sales_Tool\localization-leads
venv\Scripts\python.exe -m pytest tests/ -q
# Expected: 20 passed
```
