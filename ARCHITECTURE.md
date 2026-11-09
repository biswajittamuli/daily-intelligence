# Daily Intelligence Architecture

## Overview

Daily Intelligence is a local-first app: a loopback-only Python HTTP server, a
single-file SPA, a local SQLite store, a local Ollama model, and dynamically
discovered Parallel MCP search/fetch tools. There is no cloud LLM and no model
downloads.

## v4 unified discovery

```text
POST /api/discover  (or the daily scheduler)
  -> DiscoveryOrchestrator (app/services/orchestrator.py)
       skip map: disabled sources + sources backing off after repeated failures (source_state)
       JobsAdapter        -> BroadJobSearch (below)
       GovernmentAdapter  -> DiscoveryEngine("government")
       ExamsAdapter       -> DiscoveryEngine("exams")
       NewsAdapter        -> DiscoveryEngine("news"), once a day
       ReverifyAdapter    -> verify_jobs(select_due_for_verification)
       -> registry state, discovery report (search_sessions category "discovery"), alerts, reminders
GET /api/feed      -> services/feed.py: one prioritised feed over jobs, notices and exam events
Scheduler (60 s)   -> daily discovery · followed companies (monitoring.check_followed) · re-verification
```

The source registry (`job_sources/registry.py`) defines every source (method, pagination, geography,
restrictions, alternatives); `source_state` (schema v7) persists attempts, successes, extraction and
verification rates, consecutive failures and backoff. Schema v8 adds employer city/stage/verification/
followed, v9 posting-date provenance, v10 listing reports.

## v3.3 acquisition layer

```text
BroadJobSearch.run (app/services/broad_search.py)
  plan: portal site: / ATS-host site: / career / open web / city / remote / startup / company paths
  1  employer discovery (startup requests)        -> EmployerDiscovery -> CareerDiscovery
  2  known ATS boards (task, cached 3 h)          -> ats_sources.fetch_company_jobs (public APIs)
  3  Parallel MCP search batches                  -> SourceReport per batch / portal
  4  classify: article | index page | listing     -> exclusions recorded
  5  boards revealed by result URLs               -> ats_registry.boards_from_urls
  6  index pages (portal policy gate)             -> Parallel fetch -> harvest_listings
  7  unknown employers -> domain -> CareerDiscovery (SafeFetcher, BrowserRenderer when needed)
     due re-discoveries; verified career pages re-read
  8  newly found boards read + saved as employers
  9  normalise (employer-owned sources first) + dedup, relevance gate, assessment, store
 10  coverage: source_reports, source_health, job_exclusions, resources
```

Access rules: `portals.may_fetch` (search-results-only portals are never fetched), robots.txt in
`SafeFetcher`, private-network blocking in both the fetcher and the browser, bot challenges reported.

## V2 request paths

### Discovery (jobs / government / exams / news / papers)

```text
Browser (static SPA)
  -> POST /api/intel/search {category, query, freshness}
      -> single-slot background executor (job id, progress, cancel)
          -> DiscoveryEngine.run
              -> load persisted preferences
              -> build_plan()            dynamic query plan (roles, locations,
                                         skills, portal site: queries, freshness)
              -> ONE MCP web_search      bounded result count
              -> deterministic filter    off-topic / old / duplicate removal, ranking
              -> bounded MCP web_fetch   small page budget, content caps
              -> ONE local-LLM extraction (JSON, bounded input + output)
              -> deterministic validation
                   - evidence-quote grounding (exact, then token overlap)
                   - re-attribute misattributed quotes to the one source containing them
                   - controlled enums, date parsing, status classification
                   - job match scoring (explainable)
              -> in-run dedup (jobs by canonical URL; exams by exam/type/date)
              -> SQLite upsert (additive tables)
              -> honest fallback records when extraction yields nothing
  <- GET /api/jobs/{id}            progress + final summary
```

One run performs exactly **one search** and **one model generation**. Fetch count,
content size and output tokens are capped so the run fits an RTX 3060 Mobile (6 GB)
and a 4096-token context.

### Briefing

```text
POST /api/briefings
  -> assemble stored intel locally (jobs, exam events, deadlines, changes, actions)
  -> live research ONLY if no stored intel exists
```

A normal briefing does **zero** live searches and **zero** model calls when stored
intelligence is present.

### Research / Ask

`POST /api/research` keeps the bounded research path: plan → search → bounded fetch →
evidence extraction, with optional structured extraction for job/exam requests.

## Frontend and API

- `app/static/index.html`, `app/static/app.css`, `app/static/app.js`: dark-first
  responsive SPA. Delegated events, `setView`, background job polling, cancellation,
  progress boxes, empty states, resume upload, settings forms. Discovery queries are
  kept separate from display filters, so a query never hides stored results.
- `app/web.py`: loopback API, single `ThreadPoolExecutor(max_workers=1)`, job
  submission/status/cancel, bootstrap, preferences, watchlists, resume, item states,
  export, clear-intel, MCP diagnostics.
- `app/agent/briefing.py`: stored-intel briefing assembly with live fallback.
- `app/agent/research.py`, `app/agent/search_planner.py`: bounded research path.
- `app/llm.py`: installed-model-only Ollama generation; `num_predict` cap, thinking
  disabled by default, `_recover_json` salvages complete records from truncated JSON.
- `app/llm_runtime.py`: isolated hard-deadline model discovery.
- `app/mcp/retrieval.py`: runtime tool discovery, URL filtering, bounded content,
  per-call timeout, tool-call logging, live diagnostic.
- `app/mcp/diagnostic_runner.py`: TCP preflight + child-process deadline.

## V2 services

- `app/services/preferences.py`: editable defaults, validation, persistence; portal
  domains; suggestion chips that are not active preferences.
- `app/services/query_plan.py`: dynamic per-category query plans, custom sites,
  source classification (listing vs index vs news).
- `app/services/discovery.py`: the bounded engine — plan, search, filter/rank, fetch,
  extract, validate, re-attribute, dedup, fallback, persist.
- `app/services/freshness.py`: date parsing, freshness windows, event/deadline status.
- `app/services/job_matching.py`: explainable deterministic job scoring.
- `app/services/resume.py`: local PDF/DOCX/TXT extraction and profile building.
- `app/services/date_verification.py`, `extraction.py`, `domain_intelligence.py`:
  evidence-backed date handling and generic extraction (research path).

## Data model (additive)

`app/memory/store.py` uses `CREATE TABLE IF NOT EXISTS`; upgrades never drop data.

| Table | Purpose |
| --- | --- |
| `tasks`, `history`, `briefings`, `source_snapshots` | Pre-existing; preserved |
| `preferences` | Key/value JSON (includes `discovery_preferences`) |
| `job_listings` | Real listings with match score/reason, status, evidence |
| `recruitment_notices` | Government/PSU notices with eligibility, dates, links |
| `exam_events` | One row per dated exam event; canonical key includes event type + date |
| `intel_items` | News / papers / resources |
| `exam_watchlist`, `organization_watchlist` | Followed exams and organizations |
| `saved_items` | Save / hide / track state per item |
| `search_sessions` | Discovery runs: category, plan, progress, summary |
| `candidate_profile` | Single-row local resume profile |

Exam canonical keys are `<source-url>#event:<type>:<date>` so multiple events from one
page do not overwrite each other. Job canonical keys are the canonical listing URL.

## Runtime safeguards

- Web server binds only to `127.0.0.1`; active handlers capped.
- One background slot; concurrent submissions get HTTP 409; jobs carry timestamps and
  elapsed seconds; cancellation propagates through awaited stages.
- Discovery caps: one search, small fetch budget, per-run content cap, bounded prompt
  (3,000 chars total / 1,500 per source) and bounded output (1,200 tokens).
- Model selection is restricted to installed models; generation has HTTP timeout and
  `asyncio.wait_for`; calls within a request are sequential.
- MCP credentials may be supplied via `PARALLEL_MCP_AUTH_TOKEN`; never logged.
- Resume text and profile stay local; they are never sent to MCP or external services.

## Verification status

The MCP diagnostic checks endpoint TCP, tool discovery, a search and a fetch. On this
host (2026-11-08) it passed with six tools, 10 results and a successful fetch. Ollama
reported `qwen3:4b`. Live jobs, exams and briefing flows were verified through the
real UI; see `docs/history/IMPLEMENTATION_STATUS.md` for details and known limitations.
