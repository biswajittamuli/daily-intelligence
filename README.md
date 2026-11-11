# Daily Intelligence

Daily Intelligence is a local-first personal intelligence and opportunity-discovery
assistant for Fedora KDE. It finds and tracks **jobs, government/PSU recruitment,
examinations, AI news and research papers**, and can answer arbitrary research
requests. Search/fetch uses dynamically discovered Parallel MCP tools; all language
work runs on a **local Ollama model that is already installed**. No model is
downloaded and there is no cloud LLM fallback.

Version 2 makes discovery **preference-driven and dynamic**: there are no hardcoded
organizations, notices, exam names, or fixed result lists. You edit your preferences
once, and every discovery run builds its own query plan from them.

## What's new in 4.3

Accuracy over volume. Every listing passes one validation gate before it is ranked or shown:
document classification (vacancy, internship, graduate, government/PSU notice, or talent network,
candidate registration, careers homepage, search page, article, news, agency), publication-date
freshness, fail-closed geography (India-based · Remote with India explicitly eligible · Remote with
unknown restrictions · Remote not open to India · Relocation · Outside), vacancy status and verification
level. The home feed shows only verified, in-geography vacancies as matches; the rest are labelled
(verification pending, stretch, outside geography, not a vacancy). A first-discovered time is never shown
as a publication date ("Publication date not disclosed · First discovered today"). New sources: the
Himalayas remote-jobs API (no key). See `docs/V4.3_DISCOVERY_DIAGNOSIS.md`.

Job APIs (4.4): without any key, discovery also reads AI Dev Jobs (India-filtered AI/ML and backend roles),
Artificial Intelligence Jobs (AI-company roles in Asia-Pacific, from the companies' own career pages) and
Remote OK (one feed call per run; listings keep their Remote OK link, as its terms require). Two optional
free keys add more: Jooble, a job search engine that indexes Indian portals and company sites (the compliant
route to listings that LinkedIn and Naukri also carry), and Findwork (developer jobs).

Optional keys: open **Settings → API keys**, paste the key and press **Save & test**. The app checks the
key with the provider right away (the Firecrawl check spends no credits; the Jooble and Findwork checks run
one search), keeps it only if the provider accepts it, and uses it from the next discovery run with no
restart. Providers: Jooble (free key, at most 4 searches per run), Findwork (free key, at most 3 per run),
Firecrawl (renders JavaScript career pages when the local browser cannot) and Parallel (optional token for
higher search limits). Keys are stored in `data/secrets.json` (permissions 0600, git-ignored), never sent
back to the browser in full and never logged; the key endpoints accept requests only from the app's own page.
Environment variables with the same names (`JOOBLE_API_KEY`, `FINDWORK_API_KEY`, `FIRECRAWL_API_KEY`,
`PARALLEL_MCP_AUTH_TOKEN`) still work; a key saved in Settings takes precedence. Without a key a source
reports "Not configured" and discovery continues with the rest. Only role titles and a location are sent to
these providers, never resume content.

## What's new in 4.0

Daily Intelligence opens on a personal home: a greeting, today's numbers, and one prioritised
**opportunity feed** built from a single shared database. One action — **Discover** (top bar, or
Ctrl K → "Discover opportunities") — runs every enabled source:

- job search paths (portal site searches, public ATS hosts, career pages, open web, startup hubs across
  nine Indian cities, remote-from-India), public ATS boards read through their APIs with pagination,
  career-page discovery (static → browser → embedded data → sitemaps → common paths → search), the Hasjob
  public feed, employer discovery once a day;
- government & PSU notices, exam notifications and AI news (once a day);
- re-verification of active listings that are due.

Jobs, Startups, Government, Exams and News are views of that database (menu ☰ or Ctrl K); none of them
needs its own search. A targeted search (Ctrl K → type a role → "Search roles") uses the same engine.

Each listing carries its provenance (every source that found it), how its posting date was obtained and
how reliable that is, its verification and vacancy status, India work arrangement, and a match against
your active resume (or your best-fitting resume) with a four-level eligibility label. Sources & coverage
(menu) shows what every source did on the last run — successful, partial, no results, failed, access
restricted or not attempted — with reasons and legitimate alternatives.

Coverage is never complete: LinkedIn, Indeed, Glassdoor, Naukri, Wellfound and YC Work at a Startup are
used only through search-engine results (their terms forbid automated access), and some employer sites
block automated requests. Those limits are reported, never bypassed.

## What's new in 3.3

- **Multi-engine acquisition** (`app/services/job_sources/`): Parallel MCP search (kept as is) plus
  public ATS job-board APIs, employer career pages, a polite SSRF-safe direct fetcher (robots.txt,
  crawl-delay, per-host rate limits, on-disk ETag cache) and bounded Playwright rendering that drives
  the installed Google Chrome (one page at a time, private-network requests blocked).
- **JavaScript career-page discovery** in stages: static HTML → rendered DOM (with permitted
  "careers"/menu reveal clicks) → embedded `__NEXT_DATA__`/JSON-LD/public JSON the page loads →
  sitemaps → verification → search fallback. Nine precise outcomes, every method recorded, bounded
  retry schedule. Nothing is invented.
- **ATS registry** of 23 providers (6 read through documented public APIs, the rest identified and
  read as career pages). `site:` searches on ATS hosts reveal boards of employers you did not know.
- **Portal access policies**: LinkedIn, Indeed, Glassdoor, Naukri, Wellfound and YC Work at a
  Startup are used through search-engine results only and never fetched; other portals only via the
  search provider. Coverage never claims a portal was searched when nothing came back.
- **Coverage dashboard**: per-source states (17 distinct states), an 11-stage funnel, resource usage
  and an exclusion browser with a reason for every discarded result.
- **Canonical job schema, cross-source dedup** with the employer page as canonical destination,
  contradiction tracking, new lifecycle states (pending, third-party only, inaccessible) and
  employer-page-first re-verification.
- Fixed: Greenhouse listings hosted on company domains (`…/jobs/search?gh_jid=…`) were discarded as
  "search pages" (≈1,200 real openings per run); ranking is ~14× faster.

## What's new in 3.2

- **Honest job scoring.** Every job shows four separate measures: **profile match** (weighted,
  configurable), an **eligibility gate** (experience, degree, graduation batch, location, work
  authorization, deadline), **freshness** and **evidence confidence**. Requirements are split into
  mandatory and preferred, and each is marked satisfied / partial / not satisfied / unknown, with the
  listing's own wording as evidence. A job that fails a mandatory requirement is never a strong match.
- **Indian startup intelligence.** A new *Startups* page discovers employers dynamically from startup
  publications, directories and accelerators, VC portfolios and job platforms. It resolves each one's
  website, career page and public job board (Greenhouse, Lever, Ashby, Workable, SmartRecruiters;
  Workday, Freshteam, Zoho Recruit and others are detected and reported). Funding, launch and hiring
  news is stored as **signals**, never as vacancies. Requests that mention startups put startup
  employers' listings first.
- **Listing lifecycle.** First seen, posted, updated, last verified, deadline and status, with
  re-verification on a schedule or on request. *Open · verified on employer board* is reserved for
  listings read from the employer's own job system; a third-party page with an apply button is
  *Open · listing page checked*. A listing is closed only on evidence (page wording, or two
  consecutive misses from the employer's board). Reposts are linked; the same job on several portals
  is merged with every source kept, and different requisition IDs are never merged.
- **Source coverage.** For each source, the Jobs page shows whether it was targeted, returned
  results, was fetched, yielded extracted listings, was stored and was verified.
- **Applications.** Ten statuses, resume used, recruiter, interview and follow-up dates, next action,
  notes and status history. Follow-ups and interviews become Planning tasks. Nothing is ever
  submitted for you.
- **Skills Market v2.** Deduplicated counts, sample sizes and date range, skills by location /
  experience / employer, skills in new listings, week-by-week changes, and a skill gap that is hidden
  when the resume extraction looks incomplete.
- **AI News:** ten topic categories and cleaner article text. **Daily Briefing:** ten actionable
  sections showing only what changed since the previous briefing.

## What's new in 3.1

- **Broad discovery, smart shortlist.** Each job search collects a large candidate pool
  (50/100/200) from job portals, company career pages, the open web, and the public
  Greenhouse/Lever/Ashby career boards of 25 employers. It then ranks the pool against your
  **active resume** into *Strong* and *Possible* matches. Articles, search pages, senior roles,
  over-experienced roles and out-of-region jobs are excluded, and the reason is counted for each.
  The coverage report shows what was searched and what each platform returned.
- **Resumes page.** Upload several PDF/DOCX resumes, choose the active one (shown in the sidebar
  and on the Jobs page), and rename, delete, reprocess or edit them. Files stay in `data/resumes/`.
- **Central search** on the Daily Briefing page, plus **Scan all**.
- **Themes:** Minimal Light (default), Minimal Dark, Soft Neutral.
- **KDE launcher:** run `./scripts/install-desktop.sh` once. Then start *Daily Intelligence* from the
  application menu and pin it to the taskbar. Closing the window stops the server.

## What's new in 3.0

- **Fresher, more jobs.** A *market scan* runs one bounded search per role family
  (configurable in Settings → Market scan roles). Job-board and career index pages
  are expanded into the individual listings they link to, with relative posting
  dates ("3 days ago") parsed, so the Jobs page shows newest-first, dated listings
  instead of a few undated search pages. Stale, expired and closed listings are hidden.
- **Skills Market page.** Infographics of the most-requested skills, your skill gap,
  skills × role family, job boards vs company career pages, a 12-week hiring trend,
  top employers and resume fit by role family.
- **Multiple resumes, best one picked per job.** Upload a resume per direction (SDE,
  AI/ML, Backend…). Every job shows the best-fitting resume, which skills it covers
  and which it misses, plus optional tailoring hints from the local model.
- **Regional, topical AI news.** Region (India, US, Europe/UK, China, Asia-Pacific,
  Middle East, Global) and topic chips; searches target that region's publishers;
  each story's region is detected from its content and publisher.
- **Planning that understands notes.** "i want to walk my dog every evening" becomes
  the task *Walk my dog* (daily, 18:00, health). Notes are the source of truth (edit
  or delete a line and the task follows), notes can be edited in the app, and a
  *Today's plan* merges tasks, deadlines and suggested job/learning actions.
- **Applications tracker** (kanban), follow-up reminders, `.ics` calendar export,
  CSV job export, "new since last visit" badges, optional scheduled daily refresh.
- **Mid-century modern UI** in light (cream) and dark (walnut) themes.

## Requirements

- Fedora Linux, Python 3.14 and `uv`.
- Ollama running locally with at least one model installed (the app discovers
  installed models; it never pulls one). Tested with `qwen3:4b`.
- Network access to the configured Parallel MCP endpoint for live research.

## Install

```bash
uv sync
```

Optional environment settings:

```bash
export OLLAMA_HOST=http://localhost:11434
export OLLAMA_MODEL=qwen3:4b       # must already be installed; omit to auto-select
export OLLAMA_TIMEOUT=120
export OLLAMA_THINK=0             # default; set 1 to enable model "thinking" (much slower)
export PARALLEL_MCP_URL=https://mcp.parallel.ai/mcp
export PARALLEL_MCP_AUTH_TOKEN=   # only if the endpoint requires a bearer token
export DAILY_INTELLIGENCE_DATA_DIR="$PWD/data"
export DAILY_INTELLIGENCE_NOTES_DIR="$PWD/notes"
```

The web interface binds only to `127.0.0.1`; the port defaults to `8765` and can be
changed with `DAILY_INTELLIGENCE_PORT`.

## Start

Install the desktop launcher once (adds *Daily Intelligence* to the KDE application menu):

```bash
./scripts/install-desktop.sh
```

The launcher starts one server (it reuses a running one), opens a dedicated app window, and
stops the server when the window closes. Logs: `~/.local/state/daily-intelligence/logs/`.
Stop manually with `./scripts/daily-intelligence-stop.sh` or the *Quit* button in the sidebar.


One-click startup from KDE:

```bash
./scripts/start-desktop.sh
```

Or install the desktop entry into your user application menu:

```bash
mkdir -p ~/.local/share/applications
cp desktop/daily-intelligence.desktop ~/.local/share/applications/
chmod +x scripts/start-desktop.sh
```

Then search for **Daily Intelligence** in KDE's application launcher. The script
checks Ollama, starts the local server, and opens the browser. Run from this checkout
because the desktop entry points to its current absolute path.

### Backup and rollback

The database is copied to `data/backups/daily-intelligence-<time>-schema<N>.sqlite3` automatically before
any schema upgrade (4.0 upgrades schema 6 → 10). To take a manual backup (no `sqlite3` CLI needed):

```bash
cd ~/projects/daily-intelligence
./.venv/bin/python -c "import sqlite3,datetime;s=sqlite3.connect('data/daily-intelligence.sqlite3');d=sqlite3.connect(f'data/backups/manual-{datetime.datetime.now():%Y%m%d-%H%M%S}.sqlite3');s.backup(d);print('ok')"
```

Roll back to 3.3:

```bash
./scripts/daily-intelligence-stop.sh                     # stop the app first
git switch --detach v3.3.0                               # previous release (git switch main to return)
cp data/backups/daily-intelligence-<time>-schema6.sqlite3 data/daily-intelligence.sqlite3   # optional: exact pre-4.0 data
./scripts/daily-intelligence-launcher.sh
```

Schema changes are additive, so 3.3 also runs on a 4.0 database (it ignores the new tables and columns);
restoring the backup is only needed to return to the exact earlier state.

### Logs and inspection

```bash
tail -f ~/.local/state/daily-intelligence/logs/*.log         # launcher + server logs
curl -s http://127.0.0.1:8765/api/sources/health | python3 -m json.tool | less   # per-source health, policies
curl -s "http://127.0.0.1:8765/api/sources/exclusions?reason=Duplicate%20of%20another%20listing" | python3 -m json.tool | less
```

Optional settings (preferences JSON). `jobs`: `browser_rendering` (default true), `browser_concurrency` (1),
`browser_timeout_ms` (15000), `http_concurrency` (6), `store_cap` (500), `match_mode` (`active` or `best`),
`firecrawl_enabled` (false; also needs `FIRECRAWL_API_KEY`, sends only public employer URLs),
`target_country` (default: India, or the first preferred location's country).
`discovery.sections` (jobs, government, exams, news). `automation`: `daily_refresh`, `refresh_time`,
`followed_hours` (12), `reverify_batch` (30), `notify` (true), `notify_min_score` (70).
Sources can be enabled or disabled under Sources & coverage.

```bash
curl -s http://127.0.0.1:8765/api/feed | python3 -m json.tool | less       # the unified feed
curl -s http://127.0.0.1:8765/api/sources | python3 -m json.tool | less    # registry + per-source state
curl -s -X POST http://127.0.0.1:8765/api/discover -d '{}'                 # start a full discovery
```

### Manual server (development)

```bash
nohup ./.venv/bin/python -c "from app.web import serve; serve(open_browser=False)" \
  > /tmp/opencode/di-serve.log 2>&1 &
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8765/
```

Stop it by PID (find it with `ss -ltnp | grep 8765`) rather than `pkill -f` on the
launch command.

## What V2 does

### Discovery pipeline

Each discovery run is bounded and deterministic around the model:

```text
preferences + request
  -> dynamic query plan (role/location/skill/site queries, freshness window)
  -> ONE Parallel MCP web_search
  -> deterministic filter / rank / de-duplicate
  -> bounded web_fetch (small page budget)
  -> ONE local-LLM structured extraction (JSON)
  -> deterministic validation (quote grounding, enums, dates)
  -> SQLite upsert
```

- Every non-empty field must be supported by retrieved text. Missing fields are
  omitted, never invented.
- Jobs are real listings; employment news is separated and never shown as a vacancy.
  A listing is `open`/`closed`/`expired` only when the page wording supports it,
  otherwise `unverified`.
- Exams are populated as dated **events** (application open/close, admit card, exam,
  result, …) with per-event evidence. Tentative status is derived from each event's
  own quote.
- Mirror PDFs are collapsed by `(exam, event type, date)` so duplicates don't clutter
  the view.
- When extraction yields nothing, the engine stores honest `unverified` source
  records instead of fabricated details.

### Editable, persisted preferences

Open **Settings** to edit and save (all stored in SQLite, not code):

- **Jobs** — roles, experience level, employment types, locations, remote,
  salary range, skills, enabled job portals, custom sites, freshness.
- **Government & PSU** — disciplines, GATE paper, locations, freshness.
- **Exams** — freshness window.
- **News / Papers** — interests, sources, freshness.
- **Watchlists** — followed exams and organizations.
- **Profile / resume** — optional.

Defaults are suggestions only (e.g. role and skill chips); the user decides what is
active. Default job portals are Wellfound, Naukri, Indeed, LinkedIn Jobs, YC Work at a
Startup and company career pages.

### Local resume processing (optional)

Upload a PDF, DOCX or TXT resume. Text is extracted **locally** with `pypdf` /
`python-docx` and turned into a profile used for explainable job matching. The resume
and profile are **never sent to MCP or any external service**.

### Daily briefing

The briefing assembles already-stored intelligence locally (jobs, exam events,
deadlines, changes, recommended actions) and performs **zero** live searches when
stored intel exists. It only falls back to live research when there is nothing stored.

## Usage

The dark dashboard has: Daily Briefing, Jobs, Government & PSU, Exams, AI News,
Research Papers, Planning, History and Settings.

- **Discover** on any intelligence view runs a live, preference-aware search.
- Long requests run in a single background slot; the UI polls progress, rejects
  duplicate submissions and supports cancellation.
- **Ask Intelligence / Research** accepts arbitrary requests, including unfamiliar
  organizations and websites.
- Findings retain original source links and supporting quotes.

Planning notes are read from the configured notes directory. Markdown uses task
checkboxes:

```markdown
- [ ] Submit an application due: 2026-12-10
- [x] Review the notification
```

JSON accepts an array or an object with a `tasks` array. Each task can use `text` (or
`title`), `due_date` (or `deadline`) and `status`. Notes are never sent to MCP.

## API (loopback only)

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/bootstrap` | Full UI state: counts, records, preferences, watchlists, saved items |
| GET | `/api/state` | Active job state |
| GET | `/api/jobs/{id}` | Job status/progress/result |
| POST | `/api/intel/search` | Start a discovery job (`category`, `query`, `freshness`) |
| GET | `/api/intel?category=` | Stored intel for a category |
| GET/POST | `/api/preferences` | Read/save discovery preferences |
| GET/POST | `/api/exams/watchlist`, `/api/organizations/watchlist` | Watchlists |
| POST | `/api/resume` | Upload and parse a resume locally |
| GET/POST | `/api/resume/profile` | Read/save the candidate profile |
| POST | `/api/items/state` | Save / hide / track an item |
| GET | `/api/saved` | Saved items and item states |
| GET | `/api/search/sessions` | Recent discovery sessions |
| POST | `/api/data/clear-intel` | Clear intelligence records (keeps tasks/history/briefings) |
| GET | `/api/export` | Export local data as JSON |
| POST | `/api/briefings`, `/api/research` | Briefing and arbitrary research jobs |
| POST | `/api/diagnostics/mcp` | Live MCP diagnostic job |
| POST | `/api/jobs/{id}/cancel` | Cancel a running job |
| POST | `/api/intel/search` with `scan: true` | Multi-role job market scan |
| GET | `/api/insights/jobs` | Skills-market aggregates |
| GET | `/api/resumes` | All stored resumes |
| POST | `/api/resumes/{id}/default\|label\|profile\|delete` | Manage a resume (jobs are re-scored) |
| POST | `/api/listings/{id}/tailor` | Resume tailoring hints for one listing |
| POST | `/api/jobs/rescore` | Re-score every job against all resumes |
| GET | `/api/tracker` | Application pipeline |
| GET | `/api/planning/today` | Today's plan |
| GET, PUT | `/api/notes`, `/api/notes/{name}` | List / read / write `.txt`/`.md` notes |
| POST | `/api/planning/interpret` | Local-model note interpretation (suggestions) |
| POST | `/api/tasks/{id}/delete` | Delete a manual task |
| GET | `/api/export/calendar.ics`, `/api/export/jobs.csv` | Calendar and CSV exports |
| POST | `/api/employers/discover` | Employer discovery job (`request`, `topic`, `search_calls`) |
| GET | `/api/employers` | Employers and hiring signals |
| POST | `/api/jobs/reverify` | Re-verify saved/shortlisted listings (`job_ids` or `limit`) |
| GET/POST | `/api/applications`, `/api/applications/{id}/delete` | Application records |
| POST | `/api/visit` | Record a visit for "new since last visit" |

## Data

SQLite history is stored at `data/daily-intelligence.sqlite3` (or under
`DAILY_INTELLIGENCE_DATA_DIR`). Schema changes are **additive**
(`CREATE TABLE IF NOT EXISTS`); existing tasks, history, briefings and source
snapshots are preserved. Before a schema upgrade the database is copied to `data/backups/`;
the five newest backups are kept. JSON files left in `data/` by the legacy standalone MCP
scripts (removed in 4.1; they remain in git history) are never read or deleted.

## CLI

```bash
uv run python -m app.main models
uv run python -m app.main research "Research recent developments in agent memory architectures"
uv run python -m app.main serve
uv run python -m app.main diagnostics mcp
uv run python -m app.main discover                  # one full discovery run without the UI, prints metrics
uv run python -m app.main sources-report            # source-by-source health of the last run (--json)
```

The MCP diagnostic performs a real endpoint preflight, tool discovery, a search and a
fetch, and prints per-stage timing. Credentials are never printed.

## Tests

```bash
uv sync --dev                                         # installs pytest
./.venv/bin/python -m pytest -q                       # 226 tests (network mocked; browser tests use a local fixture site)
./.venv/bin/python -m unittest discover -s tests -q   # same suite without pytest
./.venv/bin/python -m compileall -q app tests
```

## Troubleshooting

- **Ollama unavailable:** start the local service and confirm `OLLAMA_HOST`; use
  `python -m app.main models` to inspect installed models.
- **Configured model missing:** unset `OLLAMA_MODEL` to auto-select, or set it to an
  exact installed name. The app will not download it.
- **Research unavailable:** check network access and `PARALLEL_MCP_URL`. Free-tier
  rate limits can occur transiently and reset.
- **Local model generation timed out / invalid JSON:** thinking is disabled by
  default (`OLLAMA_THINK=0`). Dense PDFs can be token-heavy; the engine caps input
  and output and salvages complete JSON records from truncated responses.
- **Port unavailable:** set `DAILY_INTELLIGENCE_PORT`.
- **KDE launcher path stale:** edit `Exec=` in
  `desktop/daily-intelligence.desktop` and `PROJECT_DIR` in
  `scripts/start-desktop.sh`.

## Current limitations

- Coverage is never complete. LinkedIn, Indeed, Glassdoor, Naukri and Wellfound are deliberately
  limited to search-engine results (their terms forbid automated access), so their listings stay
  "third-party / unverified" unless the same vacancy is found on the employer's own page.
- Workday, Keka, Darwinbox, Zoho Recruit and similar systems have no documented public API; they are
  read as rendered career pages, which is slower and less complete than the API-backed boards.
- Browser rendering takes ~5–15 s per page and Chrome uses up to ~1 GB while open; it is used only
  when static HTML is insufficient and is closed at the end of each run.
- Company names in startup news are extracted by patterns plus one small local-model pass. A few
  foreign companies covered by Indian publications may be tagged India; the evidence is shown.
- Discovery quality depends on the local model and on what MCP returns. Index pages
  are expanded into individual listings where their links are recognisable; pages
  that cannot be expanded are kept in a collapsed "Search pages to check" group.
- A market scan of 6 roles takes roughly 3–6 minutes (one search, two fetches and up
  to three small model calls per role) and may stop early on MCP rate limits.
- The MCP service performs remote fetches; the client cannot enforce DNS/redirect
  policy at that remote hop.
- Cross-source contradiction analysis is not implemented.
- Local extraction uses a small model (`qwen3:4b`) with a 4096-token context, so very
  long PDFs are truncated to the first bounded excerpt.
- Live jobs, exams, news and briefing flows have been verified end-to-end on this host
  (see `docs/history/IMPLEMENTATION_STATUS.md`). Live papers discovery currently stores honest
  fallback records rather than structured summaries.
