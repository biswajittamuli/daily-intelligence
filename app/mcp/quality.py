
import json

from pathlib import Path
from urllib.parse import (
    urlparse,
    urlunparse,
    parse_qsl,
    urlencode,
)


INPUT_FILE = "data/normalized_results.json"
OUTPUT_FILE = "data/quality_results.json"


# Official recruitment and government sources
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


# Primary research repositories and publication platforms
RESEARCH_DOMAINS = {
    "arxiv.org",
    "openreview.net",
    "aclanthology.org",
    "proceedings.mlr.press",
    "ieeexplore.ieee.org",
    "dl.acm.org",
    "link.springer.com",
    "nature.com",
    "sciencedirect.com",
    "pubmed.ncbi.nlm.nih.gov",
}


# Established technology organizations and research publishers

TECH_DOMAINS = {
    "openai.com",
    "anthropic.com",
    "deepmind.google",
    "ai.google",
    "blog.google",
    "microsoft.com",
    "blogs.microsoft.com",
    "ai.meta.com",
    "huggingface.co",
    "nvidia.com",
    "developer.nvidia.com",
    "github.com",
    "modelcontextprotocol.io",
    "langchain.com",
    "epoch.ai",
    "ibm.com",
    "research.ibm.com",
    "docs.anthropic.com",
    "platform.openai.com",
    "openai.github.io",
}



# Job boards and recruitment aggregators
JOB_DOMAINS = {
    "linkedin.com",
    "indeed.com",
    "naukri.com",
    "weekday.works",
    "dailyremote.com",
    "myjobb.ai",
    "tixeljobs.com",
}

EMPLOYER_CAREER_DOMAINS = {
    "jobs.ametek.com",
    "rezifi.com",
    "getfirsthire.com",
}



# Remove common tracking parameters.
TRACKING_PARAMETERS = {
    "fbclid",
    "gclid",
    "dclid",
    "msclkid",
    "ref",
    "ref_src",
    "source",
    "campaign",
}


def domain_matches(domain, known_domains):
    """Match a domain or its subdomain against a known domain."""

    return any(
        domain == known
        or domain.endswith("." + known)
        for known in known_domains
    )


def canonicalize_url(url):
    """
    Normalize a URL for deduplication.

    The original URL is never overwritten.
    """

    try:
        parsed = urlparse(url.strip())

        if parsed.scheme.lower() not in ("http", "https"):
            return url.strip()

        scheme = parsed.scheme.lower()
        domain = parsed.netloc.lower()

        if domain.startswith("www."):
            domain = domain[4:]

        # Remove default ports
        if scheme == "https" and domain.endswith(":443"):
            domain = domain[:-4]
        elif scheme == "http" and domain.endswith(":80"):
            domain = domain[:-3]

        path = parsed.path.rstrip("/") or "/"

        # Remove tracking parameters but retain meaningful parameters.
        query_parameters = []

        for key, value in parse_qsl(
            parsed.query,
            keep_blank_values=True,
        ):
            lower_key = key.lower()

            if lower_key.startswith("utm_"):
                continue

            if lower_key in TRACKING_PARAMETERS:
                continue

            query_parameters.append((key, value))

        query_parameters.sort()

        query = urlencode(query_parameters, doseq=True)

        return urlunparse((
            scheme,
            domain,
            path,
            "",
            query,
            "",
        ))

    except (ValueError, AttributeError):
        return url



def assess_source(url):
    """Assign a transparent source-quality score."""

    domain = urlparse(url).netloc.lower().removeprefix("www.")

    if domain_matches(domain, OFFICIAL_DOMAINS):
        return {
            "score": 100,
            "category": "official_source",
            "reason": "Recognized official government or recruitment domain",
        }

    if domain_matches(domain, RESEARCH_DOMAINS):
        return {
            "score": 95,
            "category": "research_platform",
            "reason": "Recognized research repository or publication platform",
        }

    if domain_matches(domain, TECH_DOMAINS):
        return {
            "score": 90,
            "category": "technology_organization",
            "reason": "Recognized technology organization or documentation platform",
        }

    if domain_matches(domain, EMPLOYER_CAREER_DOMAINS):
        return {
            "score": 85,
            "category": "employer_or_career_source",
            "reason": "Recognized employer or career website; vacancy still requires verification",
        }

    if domain_matches(domain, JOB_DOMAINS):
        return {
            "score": 70,
            "category": "job_platform",
            "reason": "Job board or recruitment listing platform",
        }

    return {
        "score": 40,
        "category": "unverified_source",
        "reason": "Source has not yet been assigned a recognized trust category",
    }



def process_records(records):
    unique_records = {}

    duplicates_removed = 0

    for record in records:
        if not isinstance(record, dict):
            continue

        original_url = record.get("url", "").strip()

        if not original_url:
            continue

        canonical_url = canonicalize_url(original_url)

        source = assess_source(original_url)

        enriched = dict(record)

        enriched["canonical_url"] = canonical_url
        enriched["source_quality"] = source

        key = canonical_url

        if key not in unique_records:
            enriched["also_found_in"] = []
            enriched["original_urls"] = [original_url]

            unique_records[key] = enriched

        else:
            duplicates_removed += 1

            existing = unique_records[key]

            # Preserve every original URL encountered.
            if original_url not in existing["original_urls"]:
                existing["original_urls"].append(original_url)

            # Preserve category provenance.
            previous_tasks = set(existing["also_found_in"])

            if existing.get("task"):
                previous_tasks.add(existing["task"])

            if record.get("task"):
                previous_tasks.add(record["task"])

            existing["also_found_in"] = sorted(previous_tasks)

            # Keep the better-scoring record as the primary record.
            if (
                source["score"]
                > existing["source_quality"]["score"]
            ):
                enriched["also_found_in"] = sorted(previous_tasks)
                enriched["original_urls"] = existing["original_urls"]

                unique_records[key] = enriched

    results = list(unique_records.values())

    results.sort(
        key=lambda item: item["source_quality"]["score"],
        reverse=True,
    )

    return results, duplicates_removed


def main():
    input_path = Path(INPUT_FILE)

    if not input_path.exists():
        raise FileNotFoundError(
            f"Input file not found: {INPUT_FILE}"
        )

    with input_path.open("r", encoding="utf-8") as file:
        records = json.load(file)

    print(f"Input records: {len(records)}")
    print("\nProcessing URLs and source quality...")

    results, duplicates_removed = process_records(records)

    output_path = Path(OUTPUT_FILE)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8") as file:
        json.dump(
            results,
            file,
            indent=2,
            ensure_ascii=False,
        )

    # Source category statistics
    categories = {}

    for record in results:
        category = record["source_quality"]["category"]
        categories[category] = categories.get(category, 0) + 1

    print("\nQUALITY PROCESSING COMPLETE")
    print(f"Original records: {len(records)}")
    print(f"Duplicates removed: {duplicates_removed}")
    print(f"Unique records: {len(results)}")

    print("\nSource categories:")

    for category, count in sorted(categories.items()):
        print(f"{category}: {count}")

    print(f"\nSaved to: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
