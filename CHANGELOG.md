# Changelog

## 4.0.0 — in progress

### Phase 1: unified acquisition
- `orchestrator.py`: one "Discover opportunities" run executes every adapter (jobs, government, exams,
  news once a day, re-verification); a failing adapter never stops the others. Scheduled refresh uses it,
  replacing the older single-search jobs path.
- `job_sources/registry.py` + `base.py`: source definitions (category, method, capabilities, pagination,
  geography, access restrictions, rate limits, alternatives), persisted state (attempts, successes,
  extraction and verification rates, reliability, consecutive failures, exponential backoff), per-source
  enable/disable. Run states: successful / partial / failed / access restricted / not attempted.
- Paginated board enumeration (Lever skip/limit, SmartRecruiters offset/total); partial reads are
  reported and never cached.
- Incremental scans: boards read completely reconcile stored listings (still listed → verified, missing
  on two fresh complete reads → closed; cached or partial reads change nothing).
- Re-verification selects any active listing whose last check is over 3 days old.

### Phase 2: Indian company and startup coverage
- Startup-hub search path rotating across Bengaluru, Hyderabad, Pune, Mumbai, Delhi NCR, Chennai, Kochi,
  Ahmedabad and Jaipur; employer discovery runs once a day in full/scheduled runs with city-hub,
  YC directory, Tracxn and career-page queries.
- Public feed adapter (`job_sources/feeds.py`, Hasjob Atom feed; robots.txt respected; feed dates are
  labelled "feed entry date").
- Portal policies for iimjobs, WorkIndia and Hasjob.
- Career discovery stage D2: common career paths (/careers, /jobs, /join-us, /work-with-us,
  /company/careers, /open-positions) with homepage-redirect and soft-404 guards.
- `job_sources/geo.py`: India-based / hybrid / remote from India / remote restricted elsewhere /
  relocation / outside India — only from location evidence.
- Employer registry (schema v8): city, stage, verification status, followed flag.

## 3.3.0 — 2026-11-09

### Audit (v3.2 run: 5,804 results → 88 stored)
- 5,724 of the 5,804 "results" were openings from 25 built-in, mostly US company boards; only 60
  came from web search (6 calls) and 10 pages were fetched.
- ~1,200 real Greenhouse openings were discarded as "search pages" because their URLs are hosted on
  company domains (`stripe.com/jobs/search?gh_jid=…`, `jobs.elastic.co/jobs?gh_jid=…`).
- Employer discovery only ran for "startup" requests; career pages were found from static HTML only
  (5 of 15 checked employers: "no career link found").
- Relevant listings beyond the pool size were dropped; exclusions were counted but not inspectable;
  "50 of 54 sources" counted targeted sources, not ones that returned data.

### Acquisition (`app/services/job_sources/`)
- `safe_http.py` SSRF-safe polite fetcher (DNS check of every address, per-hop redirect validation,
  robots.txt with wildcards + crawl-delay, per-host interval, size cap, ETag/Last-Modified disk cache,
  bot-challenge detection — reported, never bypassed). `robots.py`.
- `browser.py` bounded Playwright renderer using system Chrome; private-network sub-requests aborted;
  images/fonts/media blocked; one context, pages closed after use; memory and clean-shutdown stats.
- `career_discovery.py` stages A–F with outcomes: verified, candidate, public jobs endpoint, ATS
  identified, not found, rendering failed, access denied, domain unavailable, search exhausted.
- `structured.py` JSON-LD JobPosting, `__NEXT_DATA__`/app JSON, job objects in public JSON, sitemaps.
- `ats_registry.py` 23 providers; Recruitee added to the public-API readers.
- `portals.py` access policies; `coverage.py` per-session reports, funnel, exclusions; `firecrawl.py`
  optional, off by default.
- Job search: ATS-board, city and remote search paths, near-duplicate query removal, boards revealed by
  search results are read through their APIs and saved as employers, unknown employers in results are
  resolved (domain → career discovery → ATS), due career re-discoveries run each search, verified
  career pages are re-read. Every relevant listing is stored (cap 500), not only the pool size.
- Cheap relevance gate before full assessment (ranking 112 s → 8 s for ~6,000 candidates).

### Data (schema v6, automatic backup)
- New tables `source_reports`, `source_health`, `job_exclusions`.
- `job_listings`: extraction method, evidence confidence, ATS reference, salary currency, education,
  conflicts, retrieved/verification source. `employers`: career discovery result, outcome, next retry.

### Verification
- Employer page first (direct, robots-respecting); search-results-only portals are never fetched
  ("not checked"); new states pending verification, open · third-party only, open · verified on
  employer page, inaccessible (two unreachable checks), conflicting sources.

### UI
- Jobs: coverage dashboard (funnel, per-source state table, inaccessible sources, resources,
  click-through exclusions), filters for listing status, verified in 7 days, ATS/career/portal/web,
  internships, fresher roles, remote; "Where this listing came from" panel; tentative score styling
  when evidence is low or eligibility uncertain.
- Startups: career-discovery outcome, methods tried and next check per employer, re-check buttons;
  funding/hiring articles clustered into events.

## 3.2.0 — 2026-11-09

### Job matching repair
- `requirements.py`: mandatory / preferred / listed skills, experience range, degree (the lowest of
  listed alternatives, e.g. "B.Tech, BE or M.Tech" means Bachelor's), batch, work authorization,
  location rules, deadline and requisition ID, each with evidence.
- `assessment.py`: four separate measures (profile match with configurable weights, eligibility gate,
  freshness, evidence confidence), with a per-requirement status and a "why" explanation. Never
  strong with a mandatory miss.
- Resume reading: compound entries ("Deep Learning (CNNs, Transformers)") are parsed; a specific
  skill demonstrates its general parent (PostgreSQL → SQL, PyTorch → Deep Learning → Machine
  Learning), never the reverse (Python does not imply FastAPI). Programming languages named in the
  resume's keywords count; the local model can no longer replace programming languages with spoken
  ones.
- Search pages ("Python Developer Jobs", job-portal pages, `/role/…`) and fraud/credit roles are
  excluded with reasons.

### Employers, startups and lifecycle (schema v5, automatic backup)
- `employer_discovery.py`: publications, directories/accelerators, VC portfolios and job platforms →
  companies → websites (verified to mention the company) → career pages (real links) → ATS
  detection → verified public boards. Signals are stored separately from vacancies.
- Employer names inferred only from evidence: Naukri URL slug, recruitment subdomain (Zoho Recruit,
  iCIMS, …), page title, Indeed/Wellfound company links. The source is recorded.
- Startup requests put startup employers' listings first; internship requests search intern titles.
- `verification.py`: board presence / two-miss closure / page wording / deadlines; scheduled and
  manual re-verification; "verified on employer board" vs "listing page checked".
- Cross-source dedup by employer|title|city that respects requisition IDs; reposts linked.

### UI
- Jobs: separate match / eligibility / freshness / confidence badges, requirement table, score
  breakdown, listing status and verification history, links to the original listing and the
  official application page, per-job re-verify; filters for location, role, experience, employment
  type, source, freshness, eligibility, minimum match and Indian startups; sorting by rank, match,
  posted date, discovery date and confidence; aging/stale listings shaded, closed ones struck through;
  a collapsed "not eligible (stretch)" section.
- Source coverage table: targeted → returned → fetched → extracted → stored → verified, plus
  inaccessible sources and the reasons listings were narrowed or excluded.
- New Startups page (employers, signals, career pages, vacancies, discovery coverage).
- Applications editor with reminders; Skills Market v2 panels; actionable 10-section briefing.

### Fixes
- Skills Market: a nested helper shadowed the portal matrix (the Skills × source heatmap crashed);
  city spelling variants are merged (Bangalore = Bengaluru); the skill gap uses the matcher's reading
  of the resume.
- Today's plan never suggests applying to an ineligible job; application follow-up suggestions work
  with the new applications table.

## 3.1.0 — 2026-11-08

### Two-stage job discovery
- **Stage A, broad discovery** (`app/services/broad_search.py`): role-title variations (from the
  request, preferences and the active resume's inferred titles); bounded Parallel MCP searches mixing
  job-portal `site:` queries (two portals per call, bare domains only), company-career-page queries
  and open-web queries; index pages fetched in small chunks and expanded into individual listings.
- **Company career boards** (`app/services/ats_sources.py`): public Greenhouse / Lever / Ashby
  job-board APIs for 25 verified employers (editable in Settings). The idea is credited to
  [Career-Ops](https://github.com/santifer/career-ops) (MIT); no code was copied (Career-Ops is Node.js).
- Configurable candidate pool: 50 / 100 / 200 (3 / 6 / 10 web searches + company boards).
- Cross-source dedup keeps every source reference (`job_listings.sources_json`).
- Per-platform coverage report (queries, results, blocked/not-found/no-results) and failures.
- **Stage B, personalised ranking** against the **active resume** (`job_matching.rank_listing`):
  role relevance (titles + role family), skill coverage, experience, India-aware location
  (cities/states → India, Bangalore = Bengaluru, remote roles restricted to other countries
  excluded), employment type, freshness. Explicit exclusions: articles, search pages,
  non-technical roles, seniority, experience requirement, location. Tiers: strong / possible.

### Resume manager
- Dedicated Resumes page: upload PDF/DOCX (original files kept in `data/resumes/`), list with
  filename/date/status, one **active** resume, switch/rename/delete/reprocess/replace file,
  edit extracted profile (incl. inferred job titles). Extraction errors are stored and shown.
- Switching the active resume re-ranks every stored listing.

### Central search
- Daily Briefing search box: intent detection (keyword rules + optional Qwen refinement,
  validated), per-section clause splitting, shared engines for every section, Scan All.
- Live progress log (sources attempted, results, pages fetched, failures).

### Themes and UI
- Three themes: **Minimal Light** (default), **Minimal Dark**, **Soft Neutral**; selectable in
  Settings or the top bar; persisted. Compact job rows, consistent SVG icons, collapsed filters.

### Desktop launcher
- `scripts/install-desktop.sh` installs the launcher and icon for the user; the KDE menu entry
  launches `scripts/daily-intelligence-launcher.sh` (single instance, launch lock, health check,
  persistent logs in `~/.local/state/daily-intelligence/logs`, dedicated app window, clean
  shutdown when the window closes, idle timeout fallback). `scripts/daily-intelligence-stop.sh`.

### Data
- `PRAGMA user_version` schema versioning; the database is backed up to `data/backups/` before
  any migration. New columns: `resumes.stored_path/status/error/file_size/processed_at`,
  `job_listings.sources_json/eligibility_json/discovered_via`.

## 3.0.0 — 2026-11-08

### Jobs
- Multi-pass **market scan**: one bounded discovery per role family (configurable
  `jobs.scan_roles`), sequential, cancellable, stops early on retrieval errors.
- **Index-page expansion** (`app/services/listing_links.py`): individual listing links
  are harvested from job-board and career index pages; newest are detail-fetched.
- **Relative posting dates** ("3 days ago", "30+ days ago", "today").
- **Batched extraction**: ≤2 sources per local-model call instead of one 3,000-char prompt.
- Deterministic skill scan on every listing; skill names normalised.
- Fresh-only listing view (hides expired/closed, older than 45 days, unseen for 21 days).
- Added foundit, Instahyre, Cutshort, Hirist portals; career-page queries survive truncation.

### Skills market
- Skill gap vs your resumes, skills × role family, job boards vs company career pages,
  weekly hiring trend, top employers, resume fit by role family.

### Resumes
- Multiple resumes (`resumes` table; legacy profile migrated in place).
- Every listing is scored against every resume; best resume, covered and missing
  skills are stored; re-scored automatically on any resume change.
- Optional local-model tailoring hints per listing.

### AI news
- Region/topic taxonomy (`app/services/news_taxonomy.py`); region detected from
  content and publisher; region-specific publishers in queries (India: AIM, Inc42,
  YourStory, ET, Mint, MediaNama, IndiaAI/MeitY).

### Planning
- Free-form notes normalised into tasks (intent prefixes removed, natural dates and
  times, recurrence, categories).
- Notes are the source of truth: changed lines update tasks, removed lines archive them.
- In-app notes editor, local-model interpretation, Today's plan, `.ics` export.
- The briefing reads every note file and includes Today's plan.

### Other
- Applications tracker (saved → applied → interview → offer/rejected) with follow-up tasks.
- CSV export, "new since last visit" badges, optional scheduled daily refresh.
- Mid-century modern UI (light/dark), responsive to phone width.

## 2.0.0 — 2026-11-08
- Baseline: preference-driven discovery for jobs, government/PSU, exams, news and
  papers; local resume profile; stored-intel briefing.
