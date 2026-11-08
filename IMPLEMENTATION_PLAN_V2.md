# Daily Intelligence V2 — Implementation Plan

## Audit findings (2026-11-08)

- Working: Ollama provider (installed-model only, thinking disabled by default), Parallel MCP
  search/fetch with URL safety, research agent, evidence extraction with verbatim-quote
  validation, SQLite tasks/history/briefings/source snapshots, background job runner,
  local web dashboard, KDE launcher.
- Broken/incomplete: Jobs, Government & PSU, Exams, AI News and Research Papers views are
  client-side filters over sources captured by briefings/research. With no briefing yet they
  are empty, and they cannot run a category search. There is no persisted job/exam/news
  record, no job/exam preferences, no freshness engine for listings, no resume support, and
  no saved/dismissed state.
- Legacy standalone scripts (`app/mcp/pipeline.py`, `parallel_search.py`, `parallel_fetch.py`,
  `job_intelligence.py`, `job_parser.py`, `filter.py`, `quality.py`) contain hardcoded
  organisations and fixed queries. They are not wired into the app. They are retained
  unchanged for provenance but are not used by the runtime.

## Design

1. **SQLite extension (additive migrations only)**
   - `preferences(key, value_json, updated_at)`
   - `job_listings`, `recruitment_notices`, `exam_events`, `intel_items`
   - `exam_watchlist`, `organization_watchlist`, `saved_items`, `search_sessions`
   - `candidate_profile`
   - All `CREATE TABLE IF NOT EXISTS`; existing tables/data untouched.

2. **Dynamic discovery engine** (`app/services/discovery.py`)
   - Deterministic, preference-driven query builder (`query_plan.py`). Site-targeted queries
     come from editable preferences, never from fixed result lists.
   - One bounded Parallel `web_search` per run with multiple focused queries, then bounded
     `web_fetch` of ranked, deduplicated, freshness-filtered candidates.
   - One structured local-LLM extraction call per run (compact 4B-safe prompt), followed by
     deterministic validation of every field and evidence quote.
   - Category-specific validation/persistence for jobs, government/PSU, exams, news, papers.
   - Explicit failure/empty states: search failed, no results, fetch failed, freshness filtered.

3. **Job intelligence**
   - Editable preferences: roles, experience, employment type, locations, salary, skills,
     portals, custom sites, freshness.
   - Listing vs news separation via deterministic classification + extraction schema.
   - Explainable deterministic match score with reasons; no fabricated percentage when evidence
     is insufficient.
   - Status: open/closed/expired/unverified/unknown from explicit evidence and deadlines only.

4. **Exam intelligence**
   - Editable watchlist plus on-demand search.
   - Chronological event extraction with announced vs tentative date status.

5. **Resume (optional)**
   - Local PDF/DOCX text extraction, deterministic profile extraction, editable profile stored
     in SQLite. Resume text is never sent to Parallel MCP.

6. **Briefing**
   - Personalized assembly from stored intel, tasks, watchlists and deadlines; one bounded LLM
     synthesis call. Falls back to the existing bounded live research when no intel exists.

7. **API + UI**
   - New endpoints for category search, persisted results, preferences, watchlists, resume and
     item state. Existing endpoints preserved.
   - Real Jobs/Government/Exams/News/Papers views with search, filters, source links, freshness,
     match reasons and empty/failure states. Settings gains preference/resume sections.

8. **Testing**
   - Unit tests for migrations, query plans, freshness, scoring, validation, resume parsing,
     API wiring and briefing assembly.
   - Live Fedora checks: Ollama generation, Parallel MCP search/fetch, one jobs discovery and
     one exams discovery.

## Staged delivery

1. Store + preferences + freshness
2. Query planning + discovery engine + category extractors
3. Jobs / government / exams persistence and scoring
4. Resume
5. Briefing integration
6. API + UI
7. Tests and live verification
