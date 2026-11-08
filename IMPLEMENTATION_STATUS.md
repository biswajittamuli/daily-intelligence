# Implementation Status

Updated: 2026-11-08 (v3.0.0)

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
