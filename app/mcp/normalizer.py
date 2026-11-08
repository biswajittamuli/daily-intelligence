from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode
from datetime import datetime, timezone
import json
from pathlib import Path


TRACKING_KEYS = {
    "fbclid", "gclid", "dclid", "msclkid", "ref", "source",
    "featured_on", "w",
}


def canonicalize_url(url):
    """Build a stable deduplication key while retaining the original URL."""
    try:
        parsed = urlparse(url.strip())
        if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
            return url.strip()
        host = parsed.netloc.lower().removeprefix("www.")
        if parsed.scheme == "https" and host.endswith(":443"):
            host = host[:-4]
        if parsed.scheme == "http" and host.endswith(":80"):
            host = host[:-3]
        query = [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True)
                 if k and "." not in k and not k.lower().startswith("utm_")
                 and k.lower() not in TRACKING_KEYS]
        path = "/" + "/".join(part for part in parsed.path.split("/") if part)
        return urlunparse((parsed.scheme.lower(), host, path or "/",
                           "", urlencode(sorted(query), doseq=True), ""))
    except (TypeError, ValueError, AttributeError):
        return str(url or "")


def normalize_fetch_results(raw_results):
    normalized = []
    seen = set()
    retrieved_at = datetime.now(timezone.utc).isoformat()

    for task_result in raw_results:
        if not isinstance(task_result, dict):
            continue

        if "error" in task_result:
            continue

        for content in task_result.get("content", []):
            try:
                extracted = json.loads(content)
            except (json.JSONDecodeError, TypeError):
                continue
            if not isinstance(extracted, dict):
                continue

            for item in extracted.get("results", []):
                if not isinstance(item, dict):
                    continue
                url = str(item.get("url", "")).strip()
                title = str(item.get("title", "")).strip()
                excerpts = item.get("excerpts", [])

                if not url:
                    continue

                canonical_url = canonicalize_url(url)
                if canonical_url in seen:
                    continue

                seen.add(canonical_url)

                if isinstance(excerpts, str):
                    excerpts = [excerpts]
                if not isinstance(excerpts, list):
                    excerpts = []

                normalized.append({
                    "task": task_result.get("task"),
                    "url": url,
                    "original_url": url,
                    "canonical_url": canonical_url,
                    "title": title,
                    "publish_date": item.get("publish_date"),
                    "excerpts": excerpts,
                    "acquired_at": item.get("acquired_at"),
                    "retrieved_at": item.get("acquired_at") or retrieved_at,
                    "source_name": urlparse(url).netloc.removeprefix("www."),
                    "domain": urlparse(url).hostname,
                    "source_type": "unknown",
                    "evidence": [
                        {"text": str(excerpt), "source_url": url}
                        for excerpt in excerpts if str(excerpt).strip()
                    ],
                })

    return normalized


def save_results(results, output_path="data/normalized_results.json"):
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as file:
        json.dump(results, file, indent=2, ensure_ascii=False)

    print(f"Saved {len(results)} normalized results to {path}")


if __name__ == "__main__":
    print("Normalizer module ready.")
