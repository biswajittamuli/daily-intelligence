# Changelog

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
