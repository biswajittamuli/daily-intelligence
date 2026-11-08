"""One-request research workflow: plan locally, search/fetch remotely, synthesize locally."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable

from app.agent.search_planner import SearchPlan, SearchPlanner
from app.config import Settings
from app.llm import OllamaProvider
from app.mcp.retrieval import ParallelWebRetriever
from app.services.extraction import EvidenceExtractor, render_extraction
from app.services.domain_intelligence import DomainIntelligence
from app.services.date_verification import verify_publication_dates


@dataclass
class ResearchResult:
    request: str
    plan: SearchPlan
    sources: list[dict[str, Any]]
    answer: str
    domain_records: list[dict[str, Any]] | None = None


class ResearchAgent:
    def __init__(self, *, planner: SearchPlanner | None = None,
                 retriever: Any | None = None,
                 extractor: EvidenceExtractor | None = None,
                 domain_intelligence: DomainIntelligence | None = None,
                 provider: OllamaProvider | None = None,
                 settings: Settings | None = None) -> None:
        self.settings = settings or Settings.from_env()
        self.provider = provider or OllamaProvider(
            host=self.settings.ollama_host,
            preferred_model=self.settings.ollama_model,
            timeout=self.settings.ollama_timeout,
        )
        self.planner = planner or SearchPlanner(self.provider, self.settings)
        self.retriever = retriever
        self.extractor = extractor or EvidenceExtractor(self.provider, self.settings)
        self.domain_intelligence = domain_intelligence or DomainIntelligence(self.provider, self.settings)

    async def research(self, request: str, *, fetch_limit: int = 5,
                       include_domain: bool = True,
                       progress: Callable[[str], None] | None = None) -> ResearchResult:
        progress = progress or (lambda _: None)
        progress("Planning one bounded search with local Ollama")
        plan = await self.planner.plan(request)
        if not plan.needs_search:
            answer = await self.provider.generate_text(
                request,
                system=("Answer the user's general question directly using local model knowledge. "
                        "Do not claim to have checked current sources. State uncertainty when appropriate."),
                temperature=0.3,
                context_length=4096,
            )
            return ResearchResult(request=request, plan=plan, sources=[], answer=answer,
                                  domain_records=[])
        progress("Running one web search")
        owns_context = self.retriever is None
        retriever = self.retriever or ParallelWebRetriever(settings=self.settings)
        if owns_context:
            await retriever.__aenter__()
        try:
            sources = await retriever.search(
                plan.search_queries[:1],
                plan.objective,
                source_guidance=plan.source_guidance,
                freshness_days=plan.freshness_days,
            )
            cap = max(0, min(fetch_limit, self.settings.max_fetch_urls, 2))
            # Search backends often return several near-duplicates. Rank by
            # request terms before spending retrieval/context budget.
            sources = self._rank_sources(request, sources)[:cap]
            progress(f"Fetching up to {cap} source pages")
            fetched = await retriever.fetch(
                [item["url"] for item in sources],
                plan.objective,
                search_queries=plan.search_queries,
                full_content=True,
            ) if cap and sources else []
            self._merge_fetched_content(sources, fetched)
            for source in sources:
                verify_publication_dates(source)
        finally:
            if owns_context:
                await retriever.__aexit__(None, None, None)
        progress(f"Retrieved {len(sources)} sources; running the local evidence summary")
        domain_records = []
        if sources:
            extracted = await self.extractor.extract(request, sources)
            if include_domain and self.settings.max_llm_calls >= 3:
                domain_records = await self.domain_intelligence.extract(request, sources)
            assessments = {item.source_id: item for item in extracted.source_assessments}
            for index, source in enumerate(sources, 1):
                assessment = assessments.get(f"S{index}")
                if assessment:
                    source["classification"] = assessment.content_type
                    source["source_role"] = assessment.source_role
                    if assessment.evidence_quote:
                        source["source_role_evidence"] = assessment.evidence_quote
            answer = render_extraction(extracted)
            progress("Local evidence summary complete")
        else:
            answer = "No useful sources were retrieved for this request."
        if domain_records:
            answer += "\n\n**Structured recruitment and examination records:**\n"
            for record in domain_records:
                fields = ", ".join(f"{key}: {value['value']}" for key, value in record["fields"].items())
                answer += f"\n- {record['kind']} — {record.get('title')}: {fields or 'No fields with validated supporting quotes.'}"
        return ResearchResult(request=request, plan=plan, sources=sources, answer=answer,
                              domain_records=domain_records)

    @staticmethod
    def _rank_sources(request: str, sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
        stop_words = {"the", "and", "for", "from", "with", "about", "find", "latest",
                      "what", "when", "where", "how", "does", "that", "this", "summarize",
                      "official", "information", "status"}

        def terms(text: str) -> set[str]:
            found = set()
            for token in re.findall(r"[a-z0-9]+", text.lower()):
                if len(token) < 3 or token in stop_words:
                    continue
                token = re.sub(r"(ing|ed|es|s)$", "", token)
                if token:
                    found.add(token)
            return found

        wanted = terms(request)

        def score(source: dict[str, Any]) -> tuple[int, int]:
            title = terms(str(source.get("title", "")))
            body = terms(" ".join(str(x) for x in source.get("excerpts", [])))
            domain = terms(str(source.get("domain", "")))
            return (len(wanted & title) * 5 + len(wanted & body) * 2 + len(wanted & domain),
                    -sources.index(source))

        return sorted(sources, key=score, reverse=True)

    @staticmethod
    def _merge_fetched_content(sources: list[dict[str, Any]],
                               fetched: list[dict[str, Any]]) -> None:
        by_url = {item.get("canonical_url") or item.get("url"): item for item in sources}
        for item in fetched:
            url = str(item.get("url", "")).strip()
            if not url:
                continue
            from app.mcp.normalizer import canonicalize_url
            source = by_url.get(canonicalize_url(url)) or by_url.get(url)
            if source is None:
                continue
            source["content"] = str(item.get("full_content") or item.get("content") or "")
            excerpts = item.get("excerpts", [])
            if isinstance(excerpts, str):
                excerpts = [excerpts]
            if excerpts:
                source["excerpts"] = excerpts
                source["evidence"] = [
                    {"text": str(part), "source_url": source["url"]}
                    for part in excerpts
                ]
            source["retrieval_metadata"] = {
                key: value for key, value in item.items()
                if key not in {"url", "full_content", "content", "excerpts"}
            }

def render_markdown(result: ResearchResult) -> str:
    lines = [result.answer.strip(), "", "### Sources"]
    for index, source in enumerate(result.sources, 1):
        title = source.get("title") or source.get("domain") or source.get("url")
        date = source.get("publish_date")
        date_status = source.get("date_verification", "unverified" if date else "not_available")
        suffix = f" ({date}; {date_status.replace('_', ' ')})" if date else " (date unavailable)"
        role = source.get("source_role", "unknown")
        lines.append(f"- [S{index}] [{title}]({source['url']}){suffix} — {role} source")
    if not result.sources:
        lines.append("No sources were retrieved.")
    return "\n".join(lines)
