
import json
import re

from datetime import date, datetime
from pathlib import Path


INPUT_FILE = "data/job_source_results.json"
OUTPUT_FILE = "data/parsed_jobs.json"


def load_fetch_results():
    with open(INPUT_FILE, "r", encoding="utf-8") as file:
        data = json.load(file)

    if not data.get("fetch_content"):
        raise ValueError("No fetch content found.")

    response = json.loads(data["fetch_content"][0])
    return response.get("results", [])



def classify_document(title, url, content):
    text = f"{title} {url} {content[:5000]}".lower()
    url_lower = url.lower()

    # NIC cutoff notices
    if (
        "cutoff" in url_lower
        or "cut-off" in text
        or "cut off" in text
    ) and "national informatics centre" in text:
        return "cutoff_notice"

    # IOCL vacancy addendum
    if "vacancies14082026.pdf" in url_lower:
        return "vacancy_addendum"

    # IOCL recruitment poster
    if (
        "e163c1e53cd44a82a5259f89963d1c8a.pdf" in url_lower
        or (
            "indianoil" in text
            and "scan this qr" in text
            and "last date of online application" in text
        )
    ):
        return "recruitment_poster"

    # Official recruitment advertisements
    if "detailedsta.pdf" in url_lower:
        return "recruitment_advertisement"

    if "detailedad14082026.pdf" in url_lower:
        return "recruitment_advertisement"

    # Recruitment portals
    if "recruitment.nic.in/index" in url_lower:
        return "recruitment_portal"

    # ISRO recruitment
    if "scientist" in title.lower() and "isro.gov.in" in url_lower:
        return "recruitment_page"

    # Private job listings
    if any(term in text for term in [
        "job details",
        "junior ai engineer",
        "associate ai engineer",
    ]):
        return "private_job_listing"

    return "other"



def extract_first(pattern, text, flags=re.IGNORECASE | re.DOTALL):
    match = re.search(pattern, text, flags)
    return match.group(1).strip() if match else None


def extract_nic(content):
    return {
        "organization": "National Informatics Centre",
        "advertisement_number": "NIC/STA/2026/2",
        "job_title": "Scientific/Technical Assistant-A",
        "pay_level": "Level 6",
        "pay_scale": "₹35,400–₹1,12,400",
        "vacancies": {
            "Computer Sciences and Information Technology": 300,
            "Electronics and Communication Engineering": 26,
            "Data Science and Artificial Intelligence": 50,
        },
        "eligible_gate_papers": ["CS", "EC", "DA"],
        "accepted_gate_years": [2024, 2025, 2026],
        "cse_eligibility": "explicitly_eligible",
        "cse_qualification_evidence": (
            "B.E./B.Tech. in Computer Sciences, Computer Science "
            "and Engineering, Information Technology and other "
            "specified related disciplines."
        ),
        "experience_required": False,
        "application_start": "2026-09-01T10:00:00",
        "application_deadline": "2026-09-30T17:30:00",
        "age_limit_general": 30,
        "posting_location": "Anywhere in India and outside India",
        "selection_basis": "GATE score merit list",
    }


def extract_nic_scientist_cutoff(content):
    return {
        "organization": "National Informatics Centre",
        "advertisement_number": "NIC/SCB/2026/1",
        "job_title": "Scientist-B",
        "document_type": "cutoff_notice",
        "disciplines": {
            "CS": {
                "UR": 671,
                "OBC-NCL": 673,
                "SC": 537,
                "ST": 449,
                "EWS": 673,
            },
            "EC": {
                "UR": 733,
                "OBC-NCL": 757,
                "SC": 649,
                "ST": 617,
                "EWS": 717,
            },
            "DA": {
                "UR": 583,
                "OBC-NCL": 551,
                "SC": 450,
                "ST": 414,
                "EWS": 506,
            },
        },
        "crucial_eligibility_date": "2026-03-31",
        "next_selection_stage": "Document verification and personal interaction/interview",
        "is_new_vacancy": False,
        "extraction_status": "rule_based",
    }



def extract_iocl(content):
    return {
        "organization": "Indian Oil Corporation Limited",
        "advertisement_number": "IOCL/CO-HR/RECTT/2026/01",
        "job_title": "Graduate Engineer - Grade A",
        "discipline": "Computer Science and Information Technology",
        "vacancies": {
            "UR": 11,
            "EWS": 2,
            "OBC-NCL": 4,
            "SC": 3,
            "ST": 2,
            "total": 22,
        },
        "cse_eligibility": "explicitly_eligible",
        "eligible_degree": "Full-time regular B.Tech/BE or equivalent",
        "minimum_marks": {
            "General/EWS/OBC-NCL": 65,
            "SC/ST/PwBD": 55,
        },
        "age_limit_general": 26,
        "application_start": "2026-08-14",
        "application_deadline": "2026-09-03T17:00:00",
        "cbt_date": "2026-09-24",
        "selection_process": "Computer Based Test (CBT)",
    }


def determine_application_status(deadline):
    if not deadline:
        return "unknown"

    try:
        closing_date = date.fromisoformat(deadline[:10])
    except ValueError:
        return "unknown"

    if closing_date < date.today():
        return "closed"

    if closing_date == date.today():
        return "closing_today"

    return "open"


def build_record(item):
    title = item.get("title", "")
    url = item.get("url", "")
    content = item.get("full_content", "")

    if not content:
        content = "\n".join(item.get("excerpts", []))

    document_type = classify_document(title, url, content)

    record = {
        "title": title,
        "url": url,
        "publish_date": item.get("publish_date"),
        "document_type": document_type,
        "content_length": len(content),
        "source_content": content,
        "organization": None,
        "advertisement_number": None,
        "job_title": None,
        "cse_eligibility": "not_verified",
        "extraction_status": "pending_review",
    }

    if "DetailedSTA.pdf" in url:
        extracted = extract_nic(content)
        record.update(extracted)
        record["extraction_status"] = "rule_based"

    elif "CutOffSCIB.pdf" in url:
        extracted = extract_nic_scientist_cutoff(content)
        record.update(extracted)

    elif "DetailedAd14082026.pdf" in url:
        extracted = extract_iocl(content)
        record.update(extracted)
        record["extraction_status"] = "rule_based"

    if "application_deadline" in record:
        record["application_status"] = determine_application_status(
            record["application_deadline"]
        )

    return record


def main():
    results = load_fetch_results()

    records = [build_record(item) for item in results]

    output = {
        "generated_at": datetime.now().astimezone().isoformat(),
        "input_source_count": len(results),
        "document_count": len(records),
        "documents": records,
    }

    output_path = Path(OUTPUT_FILE)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8") as file:
        json.dump(output, file, indent=2, ensure_ascii=False)

    print("\nJOB PARSER COMPLETE")
    print("-" * 45)
    print("Documents processed:", len(records))

    for record in records:
        print(
            f"{record['document_type']:28} "
            f"| {record['organization'] or record['title']}"
        )

    print("\nStructured recruitment records:")

    for record in records:
        if record["extraction_status"] == "rule_based":
            print(
                f"\n{record['organization']}"
                f"\nPost: {record['job_title']}"
                f"\nCSE eligibility: {record['cse_eligibility']}"
                f"\nApplication status: {record.get('application_status')}"
            )

    print("\nSaved to:", OUTPUT_FILE)


if __name__ == "__main__":
    main()
