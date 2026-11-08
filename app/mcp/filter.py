
import json
import re

from datetime import date, datetime
from pathlib import Path
from urllib.parse import urlparse


INPUT_FILE = "data/quality_results.json"
OUTPUT_FILE = "data/filtered_results.json"

TODAY = date.today()


# Official domains are used as a source-quality signal,
# not as proof that every page is an official recruitment notice.
OFFICIAL_DOMAINS = {
    "iocl.com",
    "ongcindia.com",
    "oil-india.com",
    "nrl.co.in",
    "gailonline.com",
    "hindustanpetroleum.com",
    "bharatpetroleum.in",
    "ntpc.co.in",
    "powergrid.in",
    "bel-india.in",
    "ecil.co.in",
    "drdo.gov.in",
    "isro.gov.in",
    "barc.gov.in",
    "nielit.gov.in",
    "nic.in",
    "cdac.in",
    "gate2027.iitm.ac.in",
}


FRESHER_TERMS = (
    "fresher",
    "freshers",
    "entry-level",
    "entry level",
    "graduate trainee",
    "graduate engineer trainee",
    "0-1 year",
    "0–1 year",
    "0 to 1 year",
    "no experience",
)


CSE_TERMS = (
    "computer science",
    "computer engineering",
    "computer science and engineering",
    "information technology",
    "information systems",
    "software engineering",
    "b.tech cse",
    "b.e. cse",
    "btech cse",
    "b.tech in computer",
    "b.e. in computer",
)


RESEARCH_TERMS = (
    "arxiv",
    "doi.org",
    "paper",
    "research",
    "proceedings",
    "conference",
    "journal",
    "benchmark",
    "dataset",
    "preprint",
    "technical report",
)


PEER_REVIEW_TERMS = (
    "accepted at",
    "accepted to",
    "published in",
    "proceedings of",
    "neurips",
    "neural information processing systems",
    "icml",
    "international conference on machine learning",
    "iclr",
    "international conference on learning representations",
    "acl",
    "emnlp",
    "cvpr",
    "aaai",
    "mlsys",
)


JOB_BOARD_DOMAINS = {
    "weekday.works",
    "dailyremote.com",
    "myjobb.ai",
    "indeed.com",
    "linkedin.com",
    "naukri.com",
}


AGGREGATOR_TITLE_TERMS = (
    "jobs in india",
    "jobs in india:",
    "job listings",
    "vacancies",
    "jobs – page",
    "jobs - page",
)


def get_text(record):
    """Combine title and excerpts into searchable text."""

    excerpts = record.get("excerpts", [])

    if isinstance(excerpts, str):
        excerpts = [excerpts]

    return " ".join(
        [str(record.get("title", ""))]
        + [str(item) for item in excerpts]
    ).lower()


def get_domain(url):
    try:
        return (
            urlparse(url)
            .netloc.lower()
            .removeprefix("www.")
        )
    except (TypeError, ValueError):
        return ""


def is_official_domain(domain):
    return any(
        domain == official or domain.endswith("." + official)
        for official in OFFICIAL_DOMAINS
    )


def parse_date(value):
    if not value:
        return None

    if isinstance(value, date):
        return value

    try:
        return datetime.fromisoformat(
            str(value).replace("Z", "+00:00")
        ).date()
    except (ValueError, TypeError):
        return None


def find_expiry_date(text):
    """
    Detect explicit application closing dates.
    Do not infer expiry from publication or acquisition dates.
    """

    patterns = [
        r"application\s+ends?\s*[:\-]?\s*(\d{4}-\d{2}-\d{2})",
        r"last\s+date\s+(?:to\s+apply|of\s+application)\s*[:\-]?\s*(\d{4}-\d{2}-\d{2})",
        r"application\s+deadline\s*[:\-]?\s*(\d{4}-\d{2}-\d{2})",
        r"closing\s+date\s*[:\-]?\s*(\d{4}-\d{2}-\d{2})",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)

        if match:
            return parse_date(match.group(1))

    return None


def extract_experience_years(text):
    """Return the lowest stated experience requirement."""

    patterns = [
        r"(\d+)\s*(?:\+|plus)\s*years?",
        r"(\d+)\s*(?:-|–|to)\s*(\d+)\s*years?",
        r"(\d+)\s*years?\s+(?:of\s+)?experience",
    ]

    values = []

    for pattern in patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            try:
                values.append(int(match.group(1)))
            except (ValueError, IndexError):
                continue

    return min(values) if values else None


def classify_experience(text):
    if any(term in text for term in FRESHER_TERMS):
        return "fresher_or_entry_level"

    years = extract_experience_years(text)

    if years is None:
        return "experience_not_clear"

    if years <= 1:
        return "fresher_or_entry_level"

    if years <= 2:
        return "junior_possible"

    return "experienced_role"


def classify_cse_eligibility(text):
    if any(term in text for term in CSE_TERMS):
        return "explicit_cse_or_it_mention"

    return "needs_eligibility_verification"


def is_job_aggregator(record):
    url = record.get("url", "")
    title = record.get("title", "").lower()
    domain = get_domain(url)

    if any(
        domain == board or domain.endswith("." + board)
        for board in JOB_BOARD_DOMAINS
    ):
        return True

    if any(term in title for term in AGGREGATOR_TITLE_TERMS):
        return True

    return False


def classify_job(record):
    text = get_text(record)
    domain = get_domain(record.get("url", ""))

    if is_job_aggregator(record):
        return {
            "status": "job_listing_source",
            "priority": "review",
            "reason": "Aggregator page: extract individual vacancies first",
            "experience_fit": "not_assessed",
            "cse_eligibility": "not_assessed",
            "official_source": False,
            "expiry_date": None,
        }

    expiry_date = find_expiry_date(text)

    if expiry_date and expiry_date < TODAY:
        return {
            "status": "expired",
            "priority": "discard",
            "reason": f"Application deadline passed: {expiry_date}",
            "experience_fit": classify_experience(text),
            "cse_eligibility": classify_cse_eligibility(text),
            "official_source": is_official_domain(domain),
            "expiry_date": expiry_date.isoformat(),
        }

    experience_fit = classify_experience(text)
    cse_eligibility = classify_cse_eligibility(text)
    official = is_official_domain(domain)

    task = record.get("task", "").upper()
    is_psu = "PSU" in task or "GOVERNMENT" in task

    if experience_fit == "fresher_or_entry_level":
        priority = "high"
    elif experience_fit == "junior_possible":
        priority = "medium"
    elif experience_fit == "experienced_role":
        priority = "low"
    else:
        priority = "review"

    if is_psu and not official:
        priority = "review"

    if is_psu and cse_eligibility != "explicit_cse_or_it_mention":
        priority = "review"

    return {
        "status": "active_or_unverified",
        "priority": priority,
        "reason": "Requires individual advertisement verification",
        "experience_fit": experience_fit,
        "cse_eligibility": cse_eligibility,
        "official_source": official,
        "expiry_date": expiry_date.isoformat() if expiry_date else None,
    }


def classify_research(record):
    text = get_text(record)
    url = record.get("url", "").lower()
    domain = get_domain(record.get("url", ""))

    research_domains = (
        "arxiv.org",
        "openreview.net",
        "aclanthology.org",
        "proceedings.mlr.press",
        "ieeexplore.ieee.org",
        "dl.acm.org",
        "link.springer.com",
    )

    is_research = (
        any(term in text for term in RESEARCH_TERMS)
        or any(
            domain == source or domain.endswith("." + source)
            for source in research_domains
        )
    )

    if not is_research:
        return {
            "status": "general_resource",
            "research_quality": "not_assessed",
            "priority": "review",
        }

    peer_review_signals = [
        term for term in PEER_REVIEW_TERMS
        if term in text
    ]

    if peer_review_signals:
        quality = "possible_peer_reviewed"
    elif "arxiv.org" in url or "preprint" in text:
        quality = "preprint"
    else:
        quality = "publication_status_unverified"

    return {
        "status": "research_candidate",
        "research_quality": quality,
        "peer_review_signals": peer_review_signals,
        "priority": (
            "high"
            if quality == "possible_peer_reviewed"
            else "medium"
        ),
    }


def filter_records(records):
    output = {
        "generated_at": datetime.now().astimezone().isoformat(),
        "jobs": [],
        "job_sources": [],
        "research": [],
        "general_intelligence": [],
        "expired_jobs": [],
    }

    for record in records:
        if not isinstance(record, dict):
            continue

        if not record.get("url"):
            continue

        task = record.get("task", "").upper()
        enriched = dict(record)

        # Job and recruitment categories
        if (
            "JOB" in task
            or "RECRUITMENT" in task
            or "GOVERNMENT" in task
        ):
            assessment = classify_job(record)
            enriched["assessment"] = assessment

            if assessment["status"] == "expired":
                output["expired_jobs"].append(enriched)

            elif assessment["status"] == "job_listing_source":
                output["job_sources"].append(enriched)

            else:
                output["jobs"].append(enriched)

        # Research papers and research resources
        elif "RESEARCH" in task:
            assessment = classify_research(record)
            enriched["assessment"] = assessment

            if assessment["status"] == "research_candidate":
                output["research"].append(enriched)

            else:
                output["general_intelligence"].append(enriched)

        # Exams, news, AI agent technology, etc.
        else:
            output["general_intelligence"].append(enriched)

    return output


def main():
    input_path = Path(INPUT_FILE)

    if not input_path.exists():
        raise FileNotFoundError(
            f"Input file not found: {INPUT_FILE}"
        )

    with input_path.open("r", encoding="utf-8") as file:
        records = json.load(file)

    filtered = filter_records(records)

    output_path = Path(OUTPUT_FILE)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8") as file:
        json.dump(
            filtered,
            file,
            indent=2,
            ensure_ascii=False,
        )

    print("\nFILTERING COMPLETE")
    print(f"Input records: {len(records)}")
    print(f"Job candidates: {len(filtered['jobs'])}")
    print(f"Job listing sources: {len(filtered['job_sources'])}")
    print(f"Research candidates: {len(filtered['research'])}")
    print(f"Expired jobs: {len(filtered['expired_jobs'])}")
    print(
        "General intelligence:",
        len(filtered["general_intelligence"]),
    )

    total_classified = sum(
        len(filtered[key])
        for key in (
            "jobs",
            "job_sources",
            "research",
            "general_intelligence",
            "expired_jobs",
        )
    )

    print(f"Total classified: {total_classified}")

    if total_classified != len(records):
        print("WARNING: Some records were not classified.")

    print(f"Saved to: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
