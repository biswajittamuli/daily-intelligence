# Implementation Status

Updated: 2026-11-09 (v3.2.0)

## V3.2 results (2026-11-09, this host)

Automated tests: `./.venv/bin/python -m unittest discover -q` → **132 pass**, including
`tests/test_v32_features.py`, which covers the 17 Indian job scenarios with the network mocked
(Parallel MCP, ATS APIs and company websites are fakes; nothing is fetched live).

Live verification ran through the real app on port 8799, on a scratch copy of the real data, with
Parallel MCP (free tier) and Ollama `qwen3:4b`. The v4→v5 migration ran there first, with an
automatic backup (`backups/…-schema4.sqlite3`). These are live observations, separate from the
mocked tests:

| Scenario | Live result |
| --- | --- |
| Employer discovery "Indian AI startups" (6 searches) | 52.8 s · 60 results from 4 source categories (inc42, entrackr, yourstory/economictimes, peakxv, antler, wellfound, ycombinator…) → 14 new companies, 7 websites, 1 career page, 8 funding/launch signals |
| "entry-level AI engineer jobs at Indian startups in Bengaluru" (pool 100) | 263 s · 5,891 raw → 4,938 unique → 4,593 excluded with reasons, 232 not eligible (experience 145, seniority 172, education 12, batch 2, work authorization 1) → 120 stored. Inner employer discovery: 12 companies, 5 career pages, 3 readable boards |
| "AI engineer jobs at recently funded Indian startups" (after startup-first ranking) | 256 s · 120 stored, **27 from startup employers placed first** (previously 4) |
| Fresher Python backend, India (pool 50) | 248 s · 4,899 unique → 95 relevant, 265 not eligible → 60 stored |
| Remote AI internships, India (pool 50) | 207 s · real intern roles (Finzo AI, Fluexy, CRUV, Certa, The AI Signal, Langslide, GetKarta.ai) |
| PSU technical recruitment, CSE eligible | 20 s · 10 sources, 4 pages, 4 records; CSE eligibility is explicit only when the notice states it (DRDO explicit; 3 not eligible; 4 not verified) |
| Re-verify 40 listings | 253 s · 14 open (listing page checked), **1 closed on evidence** (NTT DATA: "this position has been filled"), 25 unreachable (MCP fetch timeouts on Indeed; left unchanged, not closed) |
| Daily briefing | 10 sections; 32 new items since the previous briefing; closed/expired jobs excluded |
| UI | Every view checked in headless Chrome (console clean) at 1400 px and 400 px; interactions driven through DevTools: requirement panel, filters, applications create → status change → history and Planning reminders |

Totals in the scratch database after these runs: **18 employers discovered** (13 startups, 9 in
India, 7 career pages, 4 readable public job boards, plus 25 built-in boards), **9 signals**,
**276 stored listings** (92 open and verified on the employer's board, 25 open by listing-page check,
3 open but not recently verified, 1 closed, 155 unverified), and 4,500+ candidates per search rejected as
irrelevant or stale (reasons listed in each search's coverage report).

Sources that returned results: Naukri, Wellfound, Indeed (via open searches), YC Work at a Startup,
startup.jobs, company career sites, 25 employer boards (Greenhouse / Lever / Ashby), plus
publications and portfolios (Inc42, Entrackr, YourStory, Economic Times, Peak XV, Antler, YC).
Targeted but returned nothing in these runs: LinkedIn (`site:` search) and Indeed (`site:` search).
Inaccessible: Applied Compute's Ashby board (404), some Wellfound detail pages, and Indeed pages
during re-verification (fetch timeouts).

Bugs found and fixed during verification: the Skills Market crash (shadowed matrix), city
spelling variants, a degree requirement read as Master's when B.Tech was an alternative, Python
not recognised from the resume (spoken languages in "languages"), PostgreSQL not satisfying SQL,
two different requisition IDs merged, ineligible jobs in "Suggested next actions", search pages and
a fraud-analyst role ranked, and web-page checks labelled as "verified".

## V3.1 acceptance results (2026-11-08, this host)

All of these were run live: on a scratch copy of the database (search tests) and on the real
installation (launcher tests).

| # | Test | Result |
| --- | --- | --- |
| 1 | Upload two different resumes, switch active | Real PDF (`Biswajit_Tamuli_Amazon_SDE.pdf`) and a synthetic Frontend DOCX both processed and stored under `data/resumes/`. Switching works via the Jobs selector, the Resumes page and the API |
| 2 | Active resume visible after restart | Server restarted: the active resume persisted (sidebar, Jobs page, API) |
| 3 | Rankings differ per resume | Same stored pool: the AI/SDE top results are AI/backend roles (Cyble, Sarvam, GitLab); the Frontend top results are frontend roles. A fresh discovery with the Frontend resume found Swiggy and Botsync frontend roles |
| 4 | Broad discovery across platforms | Pool 100: 6 MCP searches (Wellfound, Indeed, LinkedIn, YC, company careers, open web), 10 pages fetched, 169 listings expanded from Wellfound index pages, 25/25 company boards read (5,723 openings) → 5,952 raw / 4,975 unique |
| 5 | Large pool → useful shortlist | 206 ranked as relevant, 100 stored: 35 strong, 65 possible (fresher-eligible, India/remote-global) |
| 6 | Irrelevant jobs/articles excluded | 4,770 excluded with reasons: non-technical 1,390; seniority 1,466; search pages 898; location 422; remote-restricted 390; experience 136; articles 1 |
| 7 | Three themes, persisted | Each theme set via the API, server restarted, and the theme persisted. Screenshots checked; an invalid theme is rejected |
| 8 | Launch from the KDE menu | `kioclient exec` on the installed entry (the same KIO path the menu uses): the old v3.0.0 server was stopped, the DB was backed up, the new server started healthy, and the app window opened. The KWin window icon resolves to `daily-intelligence` |
| 9 | No duplicate servers | Second launch: same server PID, the existing window was focused (no new window). Closing the window: server shut down, no leftover processes |
| 10 | Central search updates sections | "latest AI startup funding news in India and GATE 2027 exam dates" → Exams + News. Exams 12→25, news 8→12, in 42 s |
| 11 | Regression + host checks | 109 unit/integration tests pass; MCP diagnostic ok (6 tools, search + fetch); Ollama `qwen3:4b` |

## V3 summary

See `CHANGELOG.md` for the full list. Live verification on this host (scratch copy of
the local database):

| Flow | Result |
| --- | --- |
| Market scan, 2 roles (Backend Developer, AI Engineer) | 72 s; 20 sources, 16 records, 2 harvested from index pages; 7 listings posted in the last 30 days (previously 1–2 dated listings in total) |
| AI news, region India, topic Funding & startups | 11 s; 4 records, 3 detected as India (Antler India, ₹ rounds), 1 China; legacy stories relabelled by content |
| UI | All views render in light and dark themes and at 400 px width; no console errors |
| Tests | `./.venv/bin/python -m unittest discover -q`: 97 tests pass |

## V2 summary

Daily Intelligence V2 is a preference-driven, dynamic opportunity/intelligence
discovery app. It preserves the existing infrastructure, JSON artifacts and SQLite
history (additive migrations only) and adds a real UI, persisted preferences, a
bounded discovery engine, local resume processing and a stored-intel briefing.

There are no hardcoded organizations, notices, exam names or fixed result lists.

## What was delivered

### Discovery engine

- `app/services/discovery.py`: plan → one MCP search → deterministic filter/rank →
  bounded fetch → one local-LLM structured extraction → deterministic validation →
  SQLite upsert. Honest fallback records when extraction yields nothing.
- Evidence grounding: every non-empty field must be supported by retrieved text.
  Exact quote matching first, then token-overlap matching for heading+date text.
- Misattributed quotes are re-attributed to the single source that literally contains
  them (small models often default to `S1`).
- Truncated model JSON is salvaged by parsing complete objects from the array.
- Markdown/PDF artifacts (`###`, `**`, `\*`) are stripped before prompting/validation.
- Exams are deduplicated in-run by `(exam_name, event_type, event_date)` so mirror
  PDFs collapse to one event.
- Jobs are separated from employment news; `open`/`closed`/`expired` require
  supporting wording, else `unverified`.
- Extraction budget: 3,000 chars total / 1,500 per source, `num_predict=1200`, to fit
  a 4096-token context and a 6 GB GPU.

### Preferences and personalization

- `app/services/preferences.py`: editable, validated, persisted defaults for jobs,
  government, exams, news and papers; portal domains; suggestion chips that are not
  active preferences.
- `app/services/query_plan.py`: dynamic query plans from roles, locations, skills,
  enabled portals, custom sites and freshness.
- `app/services/job_matching.py`: explainable deterministic scoring (role/skill/
  experience overlap, resume match).
- `app/services/resume.py`: local PDF/DOCX/TXT extraction and profile building.
  Resume/profile never leave the machine.
- Watchlists for exams and organizations; save/hide/track item states.

### Briefing

- `app/agent/briefing.py` assembles stored intelligence locally: new matching jobs,
  upcoming exam events, deadlines, changes and recommended actions.
- Live research runs only when no stored intel exists.

### UI

- `app/static/app.js` / `app.css`: full V2 SPA across Daily Briefing, Jobs,
  Government & PSU, Exams, AI News, Research Papers, Planning, History and Settings.
- Background job polling, cancellation, progress, empty states, resume upload,
  settings forms, watchlists, item actions.
- Discovery queries are separate from display filters, so a query never hides stored
  results.

### API and data

- `app/web.py`: discovery jobs, preferences, watchlists, resume, item states, saved
  items, search sessions, export, clear-intel, plus existing briefing/research/
  diagnostics routes.
- `app/memory/store.py`: additive schema for `preferences`, `job_listings`,
  `recruitment_notices`, `exam_events`, `intel_items`, watchlists, `saved_items`,
  `search_sessions`, `candidate_profile`, with CRUD/upsert/counts, `clear_intel()` and
  `export_data()`.

### Dependencies

- Added `pypdf==7.0.0` and `python-docx==1.2.0` (via `uv add`).

## Automated verification

- `./.venv/bin/python -m unittest discover -q` — **71 tests pass**.
- `./.venv/bin/python -m compileall -q app tests` — clean.
- `tests/test_v2_discovery.py` (27 tests) covers preference validation, query plans,
  freshness/date handling, job matching, resume extraction, discovery run summaries,
  jobs/exams/government extraction, quote re-attribution, dedup, fallbacks, API routes
  and briefing assembly.

## Live verification on this host (2026-11-08)

These were run through the real server and browser, not mocked:

| Flow | Result |
| --- | --- |
| MCP diagnostic | `ok: true`, 6 tools, 10 search results, fetch passed |
| Jobs discovery | ~29s; 10 sources, 4 fetched, 4 records (1 real Ametek listing correctly `expired`, 3 index pages honestly `unverified`) |
| Exams discovery | ~22s; 8 records (6 unique GATE events + 2 fallbacks), real dates (application open 2026-08-14/27, close 2026-09-21/27/10-05, result 2027-03-19), all `announced` |
| Daily briefing | 0.0s, `search_queries: 0`, `fetched_urls: 0`, sections “New matching jobs” / “Upcoming examination events”, deadline GATE result 2027-03-19, actions + 7 changes |
| News discovery | ~8s; 10 sources, 4 fetched, 4 structured records with real publishers and dates (Help Net Security, Techzine, CrowdStrike, Cymulate) |
| Papers discovery | ~12s; 10 sources, 2 fetched, 3 honest fallback records with real titles/URLs/publishers (arXiv, ACL Anthology); structured extraction returned no validated records |
| UI | All views render; no console errors; settings auto-loads `qwen3:4b`; preferences and watchlist persist |

### Bugs found and fixed during live verification

- Exam events overwrote each other on the same page → composite canonical keys.
- Graduation year outside plausible range → clamped 1980–2100.
- Custom sites were dropped from plans → carried through.
- LLM context overflow produced a 500 → bounded input/output.
- Truncated model JSON discarded → `_recover_json` salvages complete records.
- Markdown artifacts broke quote matching → stripped before prompt/validation.
- Model misattributed quotes to `S1` → deterministic re-attribution.
- Mirror PDFs duplicated events → in-run dedup.
- Discovery query hid stored results → display filters separated from query.
- Application-portal link duplicated the source → shown only when distinct.

## Known limitations

- Discovery quality depends on MCP results and the local model. Index/aggregator pages
  are honestly stored as `unverified`; they are not fabricated listings.
- `qwen3:4b` has a 4096-token context; very long PDFs are truncated to a bounded
  excerpt, so later-page details may be missed.
- Parallel MCP free-tier rate limits can occur transiently and reset.
- Live news discovery returns structured items; live papers discovery currently
  returns honest fallback records (real titles/URLs/publishers, unverified metadata)
  rather than structured summaries. This is a model/extraction-quality limitation, not
  fabricated data.
- Cross-source contradiction analysis is not implemented.
- Remote MCP fetches mean DNS/redirect policy cannot be enforced at the remote hop.

## Launch and logs

```bash
uv sync
uv run python -m app.main models
uv run python -m app.main diagnostics mcp
./scripts/start-desktop.sh
```

Development server and logs:

```bash
nohup ./.venv/bin/python -c "from app.web import serve; serve(open_browser=False)" \
  > /tmp/opencode/di-serve.log 2>&1 &
tail -f /tmp/opencode/di-serve.log
```

Test and compile:

```bash
./.venv/bin/python -m unittest discover -q
./.venv/bin/python -m compileall -q app tests
```

## Remaining tasks

1. Improve papers extraction quality so structured summaries validate (currently
   honest fallback records are stored).
2. Optionally add a scheduled/periodic discovery refresh.
3. Optionally add cross-source contradiction analysis.
4. Optionally verify resume upload with a real PDF/DOCX on the host.
