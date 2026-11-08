"""Deterministic region and topic taxonomy for AI news.

Region is detected from the story itself (publisher domain, country keywords) rather
than stamped from the search request, so the region filter reflects content.
"""
from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

NEWS_REGIONS: dict[str, dict[str, Any]] = {
    "India": {
        "keywords": r"\b(india|indian|bengaluru|bangalore|mumbai|delhi|hyderabad|pune|chennai|"
                    r"meity|indiaai|niti aayog|nasscom|rbi|sebi|isro|iit|iisc|reliance jio|"
                    r"infosys|tcs|wipro|hcltech|krutrim|sarvam|bhashini|ola|zoho|flipkart|"
                    r"rupees?|₹|crore|lakh)\b",
        "domains": ("analyticsindiamag.com", "inc42.com", "yourstory.com", "economictimes.indiatimes.com",
                    "livemint.com", "medianama.com", "thehindu.com", "thehindubusinessline.com",
                    "business-standard.com", "moneycontrol.com", "indianexpress.com",
                    "hindustantimes.com", "timesofindia.indiatimes.com", "entrackr.com", "the-ken.com",
                    "pib.gov.in", "indiaai.gov.in", "financialexpress.com", "ndtv.com", "news18.com"),
        "tlds": (".in",),
        "sources": ["analyticsindiamag.com", "inc42.com", "yourstory.com", "economictimes.indiatimes.com",
                    "livemint.com", "medianama.com"],
        "query": "India",
    },
    "US": {
        "keywords": r"\b(united states|u\.s\.|us government|white house|washington|silicon valley|"
                    r"san francisco|new york|california|congress|senate|ftc|nist|pentagon|"
                    r"department of (?:defense|commerce|energy))\b",
        "domains": ("nytimes.com", "wsj.com", "washingtonpost.com", "theverge.com", "techcrunch.com",
                    "wired.com", "axios.com", "cnbc.com", "bloomberg.com", "arstechnica.com"),
        "tlds": (".us",),
        "sources": ["techcrunch.com", "theverge.com", "axios.com"],
        "query": "United States",
    },
    "Europe/UK": {
        "keywords": r"\b(europe|european|eu ai act|european union|brussels|european commission|"
                    r"uk|united kingdom|britain|british|london|germany|german|france|french|paris|"
                    r"berlin|mistral|deepmind|aleph alpha|netherlands|spain|italy|ofcom|cma)\b",
        "domains": ("sifted.eu", "euractiv.com", "theguardian.com", "bbc.co.uk", "bbc.com", "ft.com",
                    "techzine.eu", "politico.eu", "thenextweb.com", "computerweekly.com"),
        "tlds": (".eu", ".uk", ".de", ".fr", ".nl", ".es", ".it", ".se"),
        "sources": ["sifted.eu", "euractiv.com", "theguardian.com"],
        "query": "Europe EU UK",
    },
    "China": {
        "keywords": r"\b(china|chinese|beijing|shanghai|shenzhen|alibaba|baidu|tencent|bytedance|"
                    r"deepseek|moonshot|zhipu|huawei|qwen|kimi|minimax)\b",
        "domains": ("scmp.com", "technode.com", "caixinglobal.com", "pandaily.com", "chinadaily.com.cn"),
        "tlds": (".cn",),
        "sources": ["scmp.com", "technode.com"],
        "query": "China",
    },
    "Asia-Pacific": {
        "keywords": r"\b(japan|japanese|tokyo|korea|korean|seoul|singapore|australia|indonesia|"
                    r"vietnam|taiwan|tsmc|samsung|sk hynix|softbank|asean|malaysia|philippines)\b",
        "domains": ("techinasia.com", "nikkei.com", "asia.nikkei.com", "koreaherald.com",
                    "straitstimes.com", "e27.co", "itnews.com.au"),
        "tlds": (".jp", ".kr", ".sg", ".au", ".tw", ".id", ".my"),
        "sources": ["techinasia.com", "asia.nikkei.com"],
        "query": "Asia Pacific",
    },
    "Middle East": {
        "keywords": r"\b(uae|dubai|abu dhabi|saudi|riyadh|qatar|israel|g42|mbzuai|falcon llm|"
                    r"neom|middle east|gulf)\b",
        "domains": ("thenationalnews.com", "arabnews.com", "gulfnews.com", "khaleejtimes.com",
                    "zawya.com", "wamda.com"),
        "tlds": (".ae", ".sa", ".qa", ".il"),
        "sources": ["thenationalnews.com", "wamda.com"],
        "query": "Middle East UAE Saudi",
    },
}

NEWS_TOPICS: dict[str, dict[str, Any]] = {
    "Models & LLMs": {"query": "new AI model release LLM launch benchmark",
                      "pattern": r"\b(llm|model|gpt|claude|gemini|llama|qwen|mistral|deepseek|benchmark|"
                                 r"release[sd]?|launch(?:es|ed)?|open-weight|parameters)\b"},
    "AI agents": {"query": "AI agents agentic AI launch enterprise",
                  "pattern": r"\b(agents?|agentic|autonomous|copilot|assistant|mcp|tool use)\b"},
    "Policy & regulation": {"query": "AI policy regulation government law",
                            "pattern": r"\b(policy|regulat\w*|law|act|bill|government|ministry|guidelines?|"
                                       r"compliance|governance|ban|framework|mission)\b"},
    "Funding & startups": {"query": "AI startup funding raises round investment",
                           "pattern": r"\b(raises?|raised|funding|series [a-e]|seed|valuation|invest\w*|"
                                      r"startup|acquir\w*|ipo|unicorn)\b"},
    "Research": {"query": "AI research breakthrough paper study",
                 "pattern": r"\b(research\w*|paper|study|scientists?|breakthrough|arxiv|lab)\b"},
    "Chips & hardware": {"query": "AI chips GPU semiconductor data center",
                         "pattern": r"\b(chips?|gpus?|nvidia|amd|semiconductor|data cent(?:er|re)s?|"
                                    r"compute|tpu|fab|tsmc|hardware)\b"},
    "Open source": {"query": "open source AI model release",
                    "pattern": r"\b(open[- ]source|open weights?|hugging ?face|github|apache 2\.0|mit license)\b"},
    "Jobs & skills": {"query": "AI jobs hiring skills workforce",
                      "pattern": r"\b(jobs?|hiring|layoffs?|workforce|skills?|talent|upskill\w*|employment)\b"},
    "Security & safety": {"query": "AI security safety risk",
                          "pattern": r"\b(security|safety|vulnerab\w*|attack|jailbreak|deepfake|risk|threat)\b"},
}


def _host(url: Any) -> str:
    return (urlparse(str(url or "")).hostname or "").lower().removeprefix("www.")


def classify_region(url: Any, *texts: Any, requested: str = "") -> str:
    """Return the best-supported region, or "Global" when nothing specific is stated."""
    host = _host(url)
    body = " ".join(str(text or "") for text in texts)[:6000]
    scores: dict[str, int] = {}
    for region, spec in NEWS_REGIONS.items():
        score = 0
        if any(host == domain or host.endswith("." + domain) for domain in spec["domains"]):
            score += 3
        if any(host.endswith(tld) for tld in spec["tlds"]):
            score += 2
        hits = len(re.findall(spec["keywords"], body, re.I))
        score += min(hits, 4)
        if score:
            scores[region] = score
    if not scores:
        return "Global"
    best = max(scores.values())
    leaders = [region for region, value in scores.items() if value == best]
    if best >= 2:
        return requested if requested in leaders else leaders[0]
    # A single passing mention only counts when it agrees with the requested region.
    return requested if requested in scores else "Global"


def classify_topic(*texts: Any, fallback: Any = None) -> str | None:
    body = " ".join(str(text or "") for text in texts)[:4000]
    best, best_hits = None, 0
    for topic, spec in NEWS_TOPICS.items():
        hits = len(re.findall(spec["pattern"], body, re.I))
        if hits > best_hits:
            best, best_hits = topic, hits
    if best:
        return best
    clean = " ".join(str(fallback or "").split())[:60]
    return clean or None


def region_query(region: str) -> str:
    spec = NEWS_REGIONS.get(region)
    return spec["query"] if spec else region


def region_sources(region: str) -> list[str]:
    spec = NEWS_REGIONS.get(region)
    return list(spec["sources"]) if spec else []


def topic_query(topic: str) -> str:
    spec = NEWS_TOPICS.get(topic)
    return spec["query"] if spec else topic
