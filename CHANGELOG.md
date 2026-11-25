# Changelog

## 5.0.0 — 2026-11-16

Source-first, eligibility-first discovery for government, PSU, examination and company opportunities.
Design and limits: `docs/V5_SOURCE_FIRST_DISCOVERY.md`.

### Official sources first
- New catalogue (`app/services/gov_sources.py`): 73 sources, 64 official organizations, 41 official
  direct sources enabled, each verified with one polite request on 2026-11-16. Covers central exams,
  PSUs, science agencies, finance institutions and seven state PSCs (APSC, UPPSC, BPSC, TNPSC, UKPSC,
  TPSC, NPSC). State PSCs are polled every 24 hours.
- New incremental crawler (`app/services/gov_crawler.py`): conditional revalidation, content hash,
  link fingerprint, new-document-only fetches, bounded detail budget and time budget, exponential
  backoff. Listing links are classified (advertisement, corrigendum, result, admit card, answer key,
  calendar, syllabus); tenders, annual reports, navigation and social links are dropped.
- PDFs are read with `pypdf`; local OCR (`pdftoppm` + `tesseract`) is used only for PDFs without a
  text layer. Corrigenda update the notice they name instead of duplicating it, with history.
- RSS/Atom feeds and examination calendars become dated `exam_events`.
- Search remains, but only as a fallback or as a discovery lead that must resolve to an official
  document. Aggregator and news entries are stored as signals, never as canonical records.
- Junk row titles (UKPSC metadata/date rows) are detected; the document's own headline is used.

### Deterministic eligibility
- New engine (`app/services/eligibility.py`, `app/services/requirements.py`) with a declared,
  versioned profile. Rules cover age and category relaxation, GATE paper/score/year, degree and
  branch, percentage/CGPA, graduation year, experience, domicile, nationality, PwD and gender.
- Verdicts are `eligible`, `likely_eligible`, `uncertain` or `not_eligible`. A missing required fact
  is never treated as a pass: the verdict is `uncertain` and the missing fact is named.
- Every rule keeps the notification's quote as evidence. Resume facts remain suggestions until saved.
- Government and Exams views gain eligible/likely/needs-a-fact/not-eligible filters and verdict
  details; Settings gains the profile form.

### Company coverage
- New company registry (`app/services/company_registry.py`) with rotation, per-company backoff,
  followed-company priority and honest scan states.
- New seed catalogue (`app/services/company_seeds.py`): 278 companies (25 startup, 106 product,
  115 GCC, 32 services), 42 with a verified public ATS tenant. Deduplicated by registrable domain.
- ATS tenants are detected from each company's own page, never guessed. An empty India board or a
  reached career page with no roles is `no_results`, not a failure.
- Coverage dashboard, company list, missed-opportunity reporting and a manual monitoring run.

### Data and API
- Schema v12 (additive, automatic backup): tables `candidate_eligibility`, `gov_sources`,
  `gov_documents`, `opportunity_signals`, `company_registry`, `missed_reports`, `query_coverage`;
  new notice/exam columns for source, document, requirements, eligibility and provenance.
- New endpoints: `GET /api/coverage`, `/api/companies`, `/api/gov/sources`, `/api/monitoring`,
  `/api/missed`; `POST /api/missed`, `/api/companies/<id>/update`, `/api/monitoring/run`.
- New tests: `tests/test_v5_eligibility.py`, `tests/test_v5_gov.py`, `tests/test_v5_companies.py`.

### Indian startups
- 17 Indian startups with public job boards join the built-in board list (verified 2026-11-09): Swiggy,
  Freshworks, Upstox, Unacademy, Cars24, Whatfix, ixigo (SmartRecruiters); InMobi, Glance, HighRadius, Sigmoid
  (Greenhouse); Mindtickle, FamPay, Pocket FM (Lever); Atlan, Tekion (Ashby); Apna (Workable). Same-named
  foreign boards (Lever "eternal" and "porter", Ashby "navi" and "leap", Greenhouse "slice") were excluded.
- 81 Indian startups without a public board API (Zerodha, Flipkart, Blinkit, Zomato, Razorpay, PhonePe,
  Zepto, Postman, BrowserStack, …) are seeded as employers with their official homepage only. Career discovery
  finds and verifies their careers page; verified pages are then re-read during discovery.
- Seeding runs at startup whenever `ats_sources.SEED_VERSION` changes, not only on version upgrades.
- Verified careers pages are re-read oldest-first, so every page is covered in rotation (previously the same
  first few were re-read every run).
- New CLI command: `python -m app.main careers [--limit N]` seeds the lists and runs careers-page discovery
  for every due employer at once.

### Job APIs
- Removed Adzuna and Google for Jobs (SerpApi): both need card details to sign up. Keys saved for them earlier
  are ignored and dropped the next time a key is saved.
- New optional keys in Settings → API keys: **Jooble** (job search engine indexing Indian portals and company
  sites; POST API, at most 4 searches per run) and **Findwork** (developer jobs; token header, at most 3 per
  run). Each key is checked with one search when saved.
- New keyless sources: **AI Dev Jobs** (`location=India`, publication and expiry dates, employer apply link),
  **Artificial Intelligence Jobs** (`region=Asia-Pacific`, roles read from AI companies' own career pages) and
  **Remote OK** (one feed call per run, filtered by the searched roles; listings keep their Remote OK link as
  its API terms require).
- Remotive was evaluated and left out: its robots.txt disallows `/api/*`.
- The polite fetcher can send a header or a JSON POST body, but only to hosts in `KEYED_API_HOSTS`; such calls
  are never cached and redirects never carry the key.

## 4.3.0 — 2026-11-09

Accuracy, freshness and source coverage for job discovery. Diagnosis and technology selection:
`docs/V4.3_DISCOVERY_DIAGNOSIS.md`.

### Freshness is publication-based
- A first-discovered time is never a publication date. Undated listings read
  "Publication date not disclosed · First discovered today" and are never "new". "New" means a stated
  publication date within 3 days; "newly discovered" is a separate, labelled badge.
- Publication dates are read from page labels ("Date: Oct 19, 2026", "Posted on …", microdata
  `datePosted`) and closing dates from "Closing date / Last date / Apply by" during discovery and every
  re-verification. A stored date is replaced only by better evidence; future dates are rejected.
- Pages on the employer's own domain (e.g. `jobs.ametek.com`) are verified directly as employer pages.
- A failed or 404 check never closes a job and no longer counts as verified ("Possibly open · last check
  failed"); two consecutive misses close it. Status transitions are recorded in `job_status_history`.
- The default feed favours vacancies published within the last 7 days.

### Validation gate before ranking
- New `app/services/vacancy_validation.py`: document classification (14 types), vacancy validation,
  publication freshness, geography, vacancy status, verification level and result group, each with reasons.
- Talent networks and candidate-registration pages are never resume-scored; they appear under
  `other_opportunities`, not in the feed.
- Geography fails closed: "Remote" alone is "Remote — location restrictions unknown"; a remote job tied to any
  non-target place, or stating US/UK/EU residency, is "Remote — India not eligible"; a place in the title counts
  when the location is missing. Target country is configurable (`jobs.target_country`).
- Feed groups: verified strong / verified good / stretch / verification pending / outside geography /
  not a vacancy / closed. Only verified, in-geography vacancies can be strong or good matches.
- HTML entities are decoded in titles, employers and locations; trailing "Apply" / "View & Apply" removed.

### Sources
- New job APIs: Himalayas (free, explicit location restrictions, publication and expiry dates), Adzuna India
  (optional key) and Google for Jobs via SerpApi (optional key; reaches LinkedIn, Naukri, Indeed and foundit
  listings without fetching those portals).
- Portal `site:` searches rotate between runs (three portals per call) so every portal is queried.
- Source health: "successful" requires usable vacancies ("Answered · no usable vacancies" otherwise);
  terms-limited portals report "Search-engine results only"; keyless APIs report "Not configured";
  per-source stored / verified / rejected counts; Hasjob is no longer registered twice.
- Cross-source dedup no longer merges same-title openings in different cities or with different requisition
  ids; the employer's apply link is preferred and every sighting (with the query that found it) is kept.
- CLI: `python -m app.main discover` and `python -m app.main sources-report`.
- **Settings → API keys**: paste a key, it is tested with the provider immediately (free account/credit
  endpoints where available), kept only if accepted, stored locally with 0600 permissions and applied without a
  restart. Covers Adzuna, SerpApi (Google for Jobs), Firecrawl and the Parallel token. Key endpoints refuse
  cross-origin requests.
- Firecrawl is now actually used: career-page discovery falls back to it when JavaScript rendering is needed
  and the local browser is unavailable or fails (it was implemented but never connected before).
- On-demand renderers report "Standby · used only when needed" instead of "Not configured".
- Security: the whole local API now accepts requests only from the app's own page. The Host must be
  127.0.0.1/localhost on the app's port (blocks DNS rebinding), a cross-site Origin is refused, and writes
  must be JSON (blocks form-style cross-site requests). Other websites open in your browser can no longer
  trigger discovery, change preferences or read data.

### Data
- Schema v11 (additive, automatic backup): `job_listings.document_type, geo_class, vacancy_status,
  verification_level, validation_json, last_fetched_at`; table `job_status_history`.

## 4.2.0 — 2026-11-09

### More of the right jobs
- Location matching no longer discards jobs whose board lists only a work arrangement. Cloudflare's
  Greenhouse board puts "Hybrid" / "Distributed" / "In-Office" in the location for 448 of 464 openings, so
  every Cloudflare job (including its Remote India ones) was dropped as "outside your geography". The
  Greenhouse reader now uses the job's offices when the location is only an arrangement; Lever
  `allLocations` and Ashby `secondaryLocations` are kept too. A live run stored 7 Cloudflare roles
  (Software Engineer, Data Scientist, Systems Engineer… Remote India) where it had stored none.
- A preferred place in the title ("… (Based in India)") counts unless the location names a foreign one;
  a foreign place in the title of a remote-only listing ("SRE — UK") restricts it.
- "Engineering" in a non-technical title ("Director of Recruiting, Engineering & IT") no longer marks it
  technical; benefits/compensation roles are non-technical.
- Feed: listings verified on the employer's own system rank slightly above unverified or undated ones
  (trust breaks near-ties; it never overrides a much better match).
- Daily refresh: a full Discover run earlier the same day counts as that day's refresh, so opening the
  app no longer spends a second round of searches.

### Safety and reliability
- Links from scraped pages go through `safeUrl`: `javascript:` and `data:` URLs are never rendered.
- Ollama connections are closed after each request (one socket leaked per job before).
- News-signal and local-model enrichment failures are logged instead of passing silently.
- Migration backups: the five newest are kept.

### Code
- `app.js` (2,489 lines) split into `app/static/js/*.js`; HTTP routes moved to `app/http_handler.py`;
  `Store` split into mixins (`app/memory/store_parts/`); `BroadJobSearch.run` ranking and shortlist
  stages extracted and tested directly.
- Removed the unused legacy `app/mcp` scripts (~1,800 lines; still in git history).
- pytest is a dev dependency (`uv sync --dev`); ResourceWarnings fail the suite and none remain.
  202 tests.
- `IMPLEMENTATION_PLAN_V2.md` and `IMPLEMENTATION_STATUS.md` moved to `docs/history/`.

## 4.1.0 — 2026-11-09

### Calmer home
- Fewer choices: up to three "Today's picks" (new or strong, eligible, not yet acted on), then a short list
  (10 at a time) under five lenses — For you, New, Saved, Government & exams, All. Other filters sit behind
  "Refine".
- One sentence and a quiet line of facts replace the six-metric strip; two side sections (Coming up, Worth
  knowing) replace five panels; last update and coverage become a single footnote.
- Rows show title, company · city · freshness and a muted score; deadlines and saved/applied state appear
  only when they matter. Opening a row shows why it matches, what you have and miss, and plain actions
  (Open / Apply, Save, Mark applied, Not for me; follow and report under More).
- Quieter chrome: borderless icon buttons, outline Discover, connection status only when offline,
  more whitespace and a narrower reading width.

## 4.0.0 — 2026-11-09

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

### Phase 3: freshness and verification
- Posting-date provenance (schema v9): `posted_date_source` and `posting_date_confidence`
  (employer ATS / JobPosting = high; career page, feed, "3 days ago" text = medium; search-engine page
  date, model extraction = low). A re-fetch never replaces a better-evidenced date; Greenhouse
  `updated_at` is stored as the update date, not the posting date.
- Freshness buckets: new today / 24 h / 3 days / 7 days, older but still open, date unknown, closed,
  expired, verification required — from trusted posting dates, otherwise from first-seen (labelled
  "First seen …"); a listing never becomes new again by being re-fetched.
- Every vacancy exposes first_seen_at, last_seen_at, published_at, updated_at, verified_at,
  application_deadline, posting_date_confidence, verification_status, vacancy_status, source_type,
  source_url, application_url and its India work arrangement.
- Scheduled re-verification checks any active listing whose last check is due, not only saved ones.

### Phase 4: resume intelligence
- Matching mode `jobs.match_mode`: `active` (default) or `best` (each listing is assessed against every
  processed resume and ranked by the best fit; the resume used is shown).
- Four eligibility levels from the deterministic assessment: Eligible, Likely eligible (no gate failed but a
  degree/experience/location requirement could not be read), Eligibility uncertain, Not eligible.
- Resume facets: AI/ML skills, cloud/infrastructure skills, location stated in the resume header.
- Fixed: acquisition settings (`browser_rendering`, `browser_concurrency`, `browser_timeout_ms`,
  `http_concurrency`, `store_cap`, `firecrawl_enabled`) were dropped by preference validation in 3.3;
  they are now persisted, together with `discovery.sections` and new automation settings.

### Phase 5: unified feed
- `services/feed.py` + `GET /api/feed`: jobs, government notices and exam events in one prioritised
  feed (new strong matches → approaching deadlines → followed companies → fresh startup roles →
  internships → government → rank), with section tags (strong, good, stretch, internship, fresher, remote,
  startup, product, government, followed, new) used as filters — no section needs its own search.
- Summary: new opportunities, new since last visit, strong/good matches, deadlines in 14 days, exam
  updates, AI news, today's plan, last discovery report.
- Follow company (`POST /api/employers/{id}/follow`), report inaccurate listing
  (`POST /api/listings/{id}/report`, schema v10 `listing_reports`; hidden from the feed, never deleted).
  Saved/applied/hidden states survive rescans.

### Phase 6: interface redesign
- Opens on a personal home: greeting by local time, date, a one-line status, six metrics (new
  opportunities, strong matches, deadlines in 14 days, exam updates, AI developments, today's
  priorities), the opportunity feed, and small panels (deadlines, today, AI developments, last discovery).
- The permanent sidebar is gone: a compact top bar (brand, command entry, Discover, theme, menu); every
  existing view stays reachable from a menu drawer and from the command palette (Ctrl K or `/`) — discover,
  targeted role search, filter the feed, ask, jump to a view, open saved items and deadlines.
- Feed rows show match, title, company · location · work arrangement, eligibility, freshness and deadline;
  expanding a row shows why it matches, matched and missing skills, status evidence and actions (open
  listing or application page, save/applied/hide, follow company, report inaccurate).
- New Sources & coverage view: last-discovery metrics counted separately (search results are leads, not
  vacancies), and the registry with per-source state, reliability, last success, backoff, restrictions,
  legitimate alternatives and enable/disable.
- Light and dark themes, responsive to phone width without horizontal scrolling.

### Phase 7: scheduling and monitoring
- Daily orchestrated discovery is on by default for new installs (`automation.daily_refresh`, 08:00, runs
  once per day after that time — also when the app is opened later). Existing saved preferences are not
  changed; the home page offers to turn it on.
- Followed companies are re-checked every 12 h (`automation.followed_hours`): boards re-read fresh and
  reconciled (new vacancies ranked and stored, removed ones closed after two complete misses), verified
  career pages re-read.
- Deadline reminders: saved/applied listings and notices due within 3 days become planning tasks once.
- Alerts: new strong (or eligible ≥ `notify_min_score`) matches are kept as in-app alerts and shown as one
  local desktop notification via `notify-send` (`automation.notify`). Nothing leaves the machine.

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
