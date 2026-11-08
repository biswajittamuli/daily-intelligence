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

## Data

SQLite history is stored at `data/daily-intelligence.sqlite3` (or under
`DAILY_INTELLIGENCE_DATA_DIR`). Schema changes are **additive**
(`CREATE TABLE IF NOT EXISTS`); existing tasks, history, briefings and source
snapshots are preserved. Existing JSON artifacts are preserved. Legacy standalone MCP
scripts (`app/mcp/pipeline.py`, `parallel_search.py`, `parallel_fetch.py`,
`job_intelligence.py`, `job_parser.py`, `filter.py`, `quality.py`) are kept for
provenance but are not used at runtime.

## CLI

```bash
uv run python -m app.main models
uv run python -m app.main research "Research recent developments in agent memory architectures"
uv run python -m app.main serve
uv run python -m app.main diagnostics mcp
```

The MCP diagnostic performs a real endpoint preflight, tool discovery, a search and a
fetch, and prints per-stage timing. Credentials are never printed.

## Tests

```bash
./.venv/bin/python -m unittest discover -q      # 71 tests
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

- Discovery quality depends on the local model and on what MCP returns; some pages
  are index/aggregator pages and are honestly stored as `unverified`.
- The MCP service performs remote fetches; the client cannot enforce DNS/redirect
  policy at that remote hop.
- Cross-source contradiction analysis is not implemented.
- Local extraction uses a small model (`qwen3:4b`) with a 4096-token context, so very
  long PDFs are truncated to the first bounded excerpt.
- Live jobs, exams, news and briefing flows have been verified end-to-end on this host
  (see `IMPLEMENTATION_STATUS.md`). Live papers discovery currently stores honest
  fallback records rather than structured summaries.
