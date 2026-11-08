"""Canonical skill names, aliases and detection.

- Original wording is preserved by callers; ``canonical()`` is used only for comparison
  and aggregation (LLM = LLMs = Large Language Models).
- Technically distinct skills are never merged (Java != JavaScript, PyTorch != Python).
- Users can add aliases through preferences ("skill_aliases": {"alias": "Canonical"}).
"""
from __future__ import annotations

import re
from typing import Any, Iterable

# canonical -> aliases (case-insensitive). Keep entries technically precise.
CANONICAL: dict[str, list[str]] = {
    "Python": ["python3", "py"], "Java": ["core java", "java 8", "java 11", "java 17"],
    "JavaScript": ["js", "ecmascript", "es6"], "TypeScript": ["ts"], "C": [], "C++": ["cpp", "c plus plus"],
    "C#": ["c sharp", "csharp"], "Go": ["golang"], "Rust": [], "Ruby": [], "Ruby on Rails": ["rails", "ror"],
    "Kotlin": [], "Swift": [], "Scala": [], "Haskell": [], "Elixir": [], "Erlang": [], "PHP": [], "R": [],
    "Dart": [], "Lua": [], "Perl": [], "Julia": [], "Solidity": [], "Bash": ["shell scripting", "shell"],
    "SQL": ["structured query language"], "NoSQL": [], "PL/pgSQL": ["plpgsql"],
    "HTML": ["html5"], "CSS": ["css3"], "React": ["react.js", "reactjs"], "Next.js": ["nextjs"],
    "Vue": ["vue.js", "vuejs"], "Angular": ["angularjs", "angular.js"], "Svelte": [], "Redux": [],
    "Tailwind CSS": ["tailwind", "tailwindcss"], "Node.js": ["node", "nodejs"], "Express": ["express.js", "expressjs"],
    "NestJS": [], "Django": [], "Flask": [], "FastAPI": [], "Spring Boot": ["springboot"], "Spring": ["spring framework"],
    ".NET": ["dotnet", "asp.net"], "GraphQL": [], "REST APIs": ["rest", "rest api", "restful", "restful apis", "apis", "api"],
    "gRPC": [], "Microservices": ["microservice"], "WebSockets": ["websocket"], "Kafka": ["apache kafka"],
    "RabbitMQ": [], "Redis": [], "PostgreSQL": ["postgres", "postgresql"], "MySQL": [], "MongoDB": ["mongo"],
    "Elasticsearch": ["elastic search"], "Cassandra": [], "DynamoDB": [], "SQLite": [], "Snowflake": [],
    "BigQuery": [], "Databricks": [], "Spark": ["apache spark", "pyspark"], "Hadoop": [], "Airflow": ["apache airflow"],
    "dbt": [], "ETL": [], "Pandas": [], "NumPy": [], "scikit-learn": ["sklearn", "scikit learn"],
    "PyTorch": ["torch"], "TensorFlow": ["tf"], "Keras": [], "JAX": [], "Hugging Face": ["huggingface", "hf transformers"],
    "Transformers": [], "LangChain": [], "LangGraph": [], "LlamaIndex": ["llama index"], "OpenAI API": ["openai"],
    "vLLM": [], "ONNX": [], "CUDA": [], "TensorRT": [],
    "Machine Learning": ["ml"], "Deep Learning": ["dl"], "NLP": ["natural language processing"],
    "Computer Vision": ["cv"], "LLMs": ["llm", "large language model", "large language models"],
    "Generative AI": ["genai", "gen ai", "generative artificial intelligence"], "RAG": ["retrieval augmented generation",
                                                                                     "retrieval-augmented generation"],
    "Agentic AI": ["ai agents", "agents", "agentic", "multi-agent systems"], "MCP": ["model context protocol"],
    "Prompt Engineering": [], "Fine-tuning": ["finetuning", "fine tuning", "lora", "peft"], "Vector Databases": [
        "vector database", "vector db", "vector search", "vector indexing & search", "vector indexing", "pinecone",
        "weaviate", "faiss", "chroma", "qdrant", "milvus"],
    "MLOps": ["ml ops"], "Reinforcement Learning": ["rl"], "Statistics": [], "Data Science": [], "Data Engineering": [],
    "Data Structures": ["data structures & algorithms", "dsa"], "Algorithms": ["algorithm design"],
    "System Design": [], "Object-Oriented Design": ["oop", "oops", "object oriented programming"],
    "Operating Systems": ["os"], "Computer Networks": ["networking"], "DBMS": ["database management systems"],
    "Multithreading": ["multithreading & concurrency", "concurrency"],
    "Docker": [], "Kubernetes": ["k8s"], "Terraform": [], "Ansible": [], "Helm": [], "AWS": ["amazon web services"],
    "Azure": ["microsoft azure"], "GCP": ["google cloud", "google cloud platform"], "Linux": ["linux cli"],
    "Git": ["github", "gitlab"], "CI/CD": ["ci/cd pipelines", "continuous integration", "continuous deployment",
                                         "github actions", "jenkins"],
    "Prometheus": [], "Grafana": [], "Observability": [], "Nginx": [],
    "Android": [], "iOS": [], "Flutter": [], "React Native": [],
    "Selenium": [], "Playwright": [], "Cypress": [], "Jest": [], "Pytest": [], "Unit Testing": ["unit tests"],
    "Tableau": [], "Power BI": ["powerbi"], "Excel": ["ms excel", "microsoft excel"], "Figma": [],
    "Security": ["application security", "appsec", "cybersecurity"], "Blockchain": [],
}

# Display/alias -> canonical (built once; extended at runtime from preferences).
_ALIAS: dict[str, str] = {}


def _build(extra: dict[str, str] | None = None) -> None:
    _ALIAS.clear()
    for canonical_name, aliases in CANONICAL.items():
        _ALIAS[canonical_name.casefold()] = canonical_name
        for alias in aliases:
            _ALIAS.setdefault(alias.casefold(), canonical_name)
    for alias, target in (extra or {}).items():
        if str(alias).strip() and str(target).strip():
            _ALIAS[str(alias).strip().casefold()] = str(target).strip()


_build()


def configure(extra_aliases: dict[str, str] | None) -> None:
    """Apply user aliases from preferences (alias -> canonical)."""
    _build(extra_aliases if isinstance(extra_aliases, dict) else None)


def canonical(name: Any) -> str:
    clean = " ".join(str(name or "").split()).strip(" .,;:-")
    if not clean:
        return ""
    return _ALIAS.get(clean.casefold(), clean)


def canonical_set(values: Iterable[Any]) -> set[str]:
    return {canonical(value).casefold() for value in values or [] if canonical(value)}


# Ambiguous short names need list-like, case-sensitive context.
_SPECIAL = {
    "C": re.compile(r"(?<![A-Za-z0-9+#/.\-])C(?![A-Za-z0-9+#])(?=\s*(?:,|/|\)|\band\b|\bor\b|language|programming|\+\+))"),
    "R": re.compile(r"(?<![A-Za-z0-9])R(?=\s*(?:,|/|\)|programming|language|\band\b))"),
    "Go": re.compile(r"(?<![A-Za-z0-9])(?:Go(?=\s*(?:,|/|\)|lang\b|language|programming|developer|engineer|\band\b|\bor\b|services|\(golang\)))|Golang)"),
    "Rust": re.compile(r"(?<![A-Za-z0-9])Rust(?![a-z])"),
    "Swift": re.compile(r"(?<![A-Za-z0-9])Swift(?=\s*(?:,|/|\)|\band\b|\bor\b|UI|language|programming|developer))"),
    "Dart": re.compile(r"(?<![A-Za-z0-9])Dart(?![a-z])"),
    "Spring": re.compile(r"(?<![A-Za-z0-9])Spring(?=\s*(?:,|/|\)|framework|\band\b|boot))", re.I),
    "Excel": re.compile(r"\b(?:MS[- ]?|Microsoft\s+)Excel\b|\bExcel(?=\s*(?:,|/|\)|spreadsheets?\b))"),
    "Security": re.compile(r"\b(application security|appsec|cybersecurity|security engineering)\b", re.I),
    "Statistics": re.compile(r"\bstatistic(s|al)\b", re.I),
    "Agentic AI": re.compile(r"\b(agentic|ai agents?|multi-agent|llm agents?)\b", re.I),
    "Observability": re.compile(r"\bobservability\b", re.I),
    "ETL": re.compile(r"\bETL\b"),
    "Operating Systems": re.compile(r"\boperating systems?\b", re.I),
    "Computer Networks": re.compile(r"\bcomputer networks?\b", re.I),
    "REST APIs": re.compile(r"\b(rest(ful)?\s*apis?|rest\b(?=\s*(?:,|/|\)|and)))", re.I),
    "Git": re.compile(r"\bgit\b|\bgithub\b", re.I),
    "Machine Learning": re.compile(r"\bmachine learning\b|\bML\b(?![- ]?ops)"),
    "Deep Learning": re.compile(r"\bdeep learning\b", re.I),
    "Computer Vision": re.compile(r"\bcomputer vision\b", re.I),
    "Data Structures": re.compile(r"\bdata structures?\b|\bDSA\b", re.I),
    "Algorithms": re.compile(r"\balgorithms?\b", re.I),
    "Multithreading": re.compile(r"\bmultithread\w*|\bconcurrency\b", re.I),
    "Unit Testing": re.compile(r"\bunit test\w*", re.I),
    "Fine-tuning": re.compile(r"\bfine[- ]?tun\w*|\bLoRA\b|\bPEFT\b"),
    "CI/CD": re.compile(r"\bCI/CD\b|\bcontinuous (integration|deployment|delivery)\b|\bGitHub Actions\b|\bJenkins\b", re.I),
}
_SKIP_GENERIC = {"Go", "R", "C", "Swift", "Dart", "Spring", "Excel", "Security", "Statistics", "Agentic AI",
                 "Observability", "ETL", "Operating Systems", "Computer Networks", "REST APIs", "Git",
                 "Machine Learning", "Deep Learning", "Computer Vision", "Data Structures", "Algorithms",
                 "Multithreading", "Unit Testing", "Fine-tuning", "CI/CD", "Rust"}
# Aliases too generic to match as free text (only used when a resume lists them).
_TEXT_EXCLUDED_ALIASES = {"py", "ts", "tf", "cv", "dl", "rl", "os", "ml", "api", "apis", "rest", "agents", "node",
                          "shell", "hf transformers", "torch", "mongo", "rails", "jenkins", "networking", "github",
                          "gitlab", "concurrency", "oop", "oops", "openai", "lora", "peft", "java 8", "java 11",
                          "java 17", "dsa", "spring framework", "chroma", "faiss"}


def _patterns() -> list[tuple[str, re.Pattern[str]]]:
    output = []
    for canonical_name, aliases in CANONICAL.items():
        if canonical_name in _SKIP_GENERIC:
            continue
        names = [canonical_name] + [alias for alias in aliases if alias.casefold() not in _TEXT_EXCLUDED_ALIASES]
        names = sorted(set(names), key=len, reverse=True)
        body = "|".join(re.escape(name) for name in names)
        output.append((canonical_name, re.compile(r"(?<![A-Za-z0-9+#.])(?:" + body + r")(?![A-Za-z0-9+#])", re.I)))
    return output


_TEXT_PATTERNS = _patterns()


def detect_skills(text: str) -> list[str]:
    """Canonical skills explicitly mentioned in ``text`` (deterministic, conservative)."""
    if not text:
        return []
    found: list[str] = []
    for name, pattern in _TEXT_PATTERNS:
        if pattern.search(text):
            found.append(name)
    for name, pattern in _SPECIAL.items():
        name = name.strip()
        if name in found:
            continue
        if pattern.search(text):
            found.append(name)
    # Java vs JavaScript: "Java" must not come only from "JavaScript".
    if "Java" in found and not re.search(r"\bJava\b(?!\s*Script)", text, re.I):
        found.remove("Java")
    return list(dict.fromkeys(found))
