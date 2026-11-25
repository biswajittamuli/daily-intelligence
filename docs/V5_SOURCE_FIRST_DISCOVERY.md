# v5 — source-first, eligibility-first discovery

v5 changes the order of work. Instead of searching the web and hoping an official advertisement
surfaces, the app polls a **catalogue of official sources**. Search is a fallback for gaps and for
employers that are not in the catalogue. Every recruiting claim is tied to a document that was read,
and every eligibility verdict is deterministic and quote-backed.

The upgrade is deliberately additive: existing search, ATS and career-page paths keep working.

## Why the order changed

The old government path ran one web search per category and extracted whatever the results
contained. That missed most state PSCs, PSU boards and examination calendars, and it could not tell a
real advertisement from an aggregator article. v5 inverts that:

```text
official source catalogue
  -> listing page (incremental: ETag / Last-Modified / content hash / link fingerprint)
  -> new notification links only
  -> bounded document fetch (HTML or PDF)
  -> structured fields + evidence quotes
  -> deterministic eligibility verdict
  -> store, alert, digest
search engine
  -> only for a named gap, or as a discovery lead that must resolve to an official document
```

An aggregator or news item is stored as a **signal**. It points at an opportunity; it is never the
organization, the canonical document, or the application record.

## Sources

`app/services/gov_sources.py` is the catalogue. Each row records what one polite request actually
showed on `VERIFIED_ON`:

| access | meaning |
| --- | --- |
| `direct` | readable HTML/XML with notice links; polled incrementally |
| `render` | JavaScript shell; read with the local headless browser during a Discover run |
| `provider` | incomplete TLS chain; read through the search provider during a Discover run |
| `search` | bot challenge; only search-engine results are used, never the challenged page |
| `unavailable` | robots.txt disallows it, or the site refuses/has no reachable careers page |

Current coverage: **73 catalogue entries, 64 official organizations, 41 official direct sources
enabled**, including central exam bodies, PSUs, science agencies, finance institutions and seven
state public service commissions (APSC, UPPSC, BPSC, TNPSC, UKPSC, TPSC, NPSC). State PSCs are
polled every 24 hours. A source only counts as successful when it produced records.

### Incremental crawling

`app/services/gov_crawler.py`:

- revalidates a listing page with conditional headers and a content hash;
- hashes the set of notice links, so reordering the page changes nothing;
- fetches only documents that are new, or whose link changed;
- caps detail fetches per run (`max_details`, `first_scan_details`) and has a wall-clock budget;
- backs off exponentially after failures, capped at seven days;
- reads PDFs with `pypdf`, with optional local OCR (`pdftoppm` + `tesseract`) only when a PDF has no
  text layer;
- merges a corrigendum into the notice it names (same organization + advertisement number) and
  records the date change in history instead of creating a second notice;
- reads RSS/Atom feeds and examination calendars into dated `exam_events`.

Links are classified before fetching: `advertisement`, `corrigendum`, `result`, `admit_card`,
`answer_key`, `schedule`, `calendar`, `syllabus`, `other`. Hindi duplicates, tenders, annual reports,
navigation and social links are dropped. When a row labels its link "Click here", the row's context
becomes the title. When the row itself is only metadata or a pile of dates (UKPSC), the PDF's own
headline is used instead.

## Deterministic eligibility

`app/services/eligibility.py` and `app/services/requirements.py` implement the rules. They never call
a model.

Inputs are the candidate's **declared** profile (`schema = 1`, stored in `candidate_eligibility`) and
the requirements read from the notification. Resume facts are suggestions until the user saves them;
nothing is inferred from a resume behind the user's back.

Rules cover:

- age, including category relaxation (General / OBC-NCL / SC / ST / EWS / PwBD) and `as on` dates;
- GATE paper, score, year and validity;
- degree level and branch/discipline;
- minimum percentage or CGPA, and graduation year;
- experience, domicile, nationality, PwD and gender where the notice states them;
- application window (open / closing soon / closed);
- advertisement number and post name, when stated.

Verdicts:

| status | meaning |
| --- | --- |
| `eligible` | every stated mandatory rule passed |
| `likely_eligible` | no rule failed, but at least one requirement is stated only approximately |
| `uncertain` | at least one **required fact is missing**; the missing fact is named |
| `not_eligible` | a stated mandatory rule failed; the failed rule and its quote are shown |

A missing fact never becomes a yes. For example, an age limit with no date of birth in the profile
produces `uncertain` + `date_of_birth`, not `eligible`. The UI exposes `eligible`, `likely`,
`needs a fact` and `not eligible` filters, plus the evidence quote behind each rule.

## Companies, GCCs and startups

`app/services/company_seeds.py` seeds a company registry with three provenances:

- verified public ATS boards from `ats_sources.DEFAULT_COMPANIES` (tenant known);
- Indian startup and product career sites from `ats_sources.INDIAN_CAREER_SITES`;
- GCC / corporate / IT-services career pages.

The current seed is **278 companies** (25 startup, 106 product, 115 GCC, 32 services), **42 with a
verified ATS tenant**. The catalogue is deduplicated by registrable domain with the precedence
`verified board > corporate > startup site`.

`app/services/company_registry.py` scans due companies in rotation:

1. read a known ATS tenant through its public API (`app/services/job_sources/ats_readers.py`);
2. otherwise read the careers page, detect the ATS from the page itself, and parse schema.org
   `JobPosting` data;
3. record the outcome honestly: `extraction_successful`, `no_results`, `fetch_successful`,
   `bot_challenge`, `access_denied`, `timeout`, and so on.

A tenant is **detected, never guessed**. An empty India board is a success (`no_results`), not a
failure. A reached career page with no roles is also not a failure. Failures back off exponentially;
the next scan of a followed company is twice as frequent.

## Storage

Schema v12 is additive. New tables:

| Table | Purpose |
| --- | --- |
| `candidate_eligibility` | single-row declared profile |
| `gov_sources` | per-source ETag, hash, next due time, failures, counts |
| `gov_documents` | every page/PDF read, with extracted text and content hash |
| `opportunity_signals` | aggregator/news leads, never canonical records |
| `company_registry` | scan state, ATS, segment, coverage counters |
| `missed_reports` | user-reported missed opportunities |
| `query_coverage` | which planned queries have actually run |

`recruitment_notices` and `exam_events` gain source, document, requirement, eligibility/missing-fact
and provenance columns (`requirements_json`, `age_min`, `age_max`, `qualification_level`,
`branches_json`, `min_percentage`, `gate_required`, `gate_score_min`, `dedup_key`, `history_json`).
Existing rows are preserved.

## API and UI

New endpoints (loopback-only, same origin checks as the rest of the app):

```text
GET  /api/coverage            company + government coverage, missed reports
GET  /api/companies           company registry with scan state
GET  /api/gov/sources         official source catalogue with state
GET  /api/monitoring          monitoring status
GET  /api/missed              missed-opportunity reports
POST /api/missed              report a missed opportunity
POST /api/companies/<id>/update   enable / follow / priority
POST /api/monitoring/run      run the due source batch
```

Settings holds the eligibility profile. Government and Exams show the verdict, the missing fact and
the evidence. Home shows coverage panels and a one-click monitoring run.

## Honest limits

- The seed is 278 companies, not the 500+ once sketched. Every row has a known official domain; the
  list is not padded with guessed ATS tenants or invented companies.
- Some official sites block automated access (bot challenge, TLS chain, robots.txt). They are marked
  `unavailable` or `search` and are never bypassed.
- Legacy-font Hindi PDFs may extract as transliterated text. Such a notice is still stored with its
  official link, but the post name may be blank rather than guessed.
- A source can be reachable and still have no current openings. That is `no_results`, not a failure,
  and not an eligibility claim.
- Search-based fallbacks remain subject to search-provider quota and are reported as such.

## Tests

- `tests/test_v5_eligibility.py` — profile cleaning, each eligibility rule, missing facts, buckets.
- `tests/test_v5_gov.py` — listing parsing/classification, junk titles, notice build, evidence,
  corrigendum merge, RSS/Atom, exam calendars, backoff.
- `tests/test_v5_companies.py` — Workday parsing, board detection, seed integrity, rotation, backoff,
  coverage, scan outcomes with an injected fetcher.

Everything is offline: fixtures and a temporary SQLite store, no network and no model.
