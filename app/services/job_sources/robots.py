"""Small robots.txt parser with wildcard support (``*`` and ``$``), longest-match rules and crawl-delay.

The standard library's ``urllib.robotparser`` treats ``*`` literally inside paths, which makes it
wrongly permissive or restrictive on many modern sites, so this module implements the RFC 9309
matching rules directly.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urlsplit

AGENT_TOKEN = "dailyintelligence"


@dataclass
class _Group:
    agents: list[str] = field(default_factory=list)
    rules: list[tuple[bool, str]] = field(default_factory=list)  # (allow, pattern)
    crawl_delay: float | None = None


def _pattern(path: str) -> re.Pattern[str]:
    anchored = path.endswith("$")
    body = re.escape(path[:-1] if anchored else path).replace(r"\*", ".*")
    return re.compile("^" + body + ("$" if anchored else ""))


class RobotsPolicy:
    def __init__(self, text: str = "", *, status: int | None = 200) -> None:
        self.status = status
        self.sitemaps: list[str] = []
        self.groups: list[_Group] = []
        # RFC 9309: 4xx -> no restrictions; 5xx/unreachable -> assume complete disallow.
        self.unreachable = status is None or (status is not None and status >= 500)
        if status is not None and 200 <= status < 300:
            self._parse(text or "")

    def _parse(self, text: str) -> None:
        current: _Group | None = None
        last_was_agent = False
        for raw in text.splitlines():
            line = raw.split("#", 1)[0].strip()
            if not line or ":" not in line:
                continue
            key, value = (part.strip() for part in line.split(":", 1))
            key = key.casefold()
            if key == "user-agent":
                if current is None or not last_was_agent:
                    current = _Group()
                    self.groups.append(current)
                current.agents.append(value.casefold())
                last_was_agent = True
                continue
            last_was_agent = False
            if key == "sitemap" and value:
                self.sitemaps.append(value)
                continue
            if current is None:
                continue
            if key in {"allow", "disallow"}:
                if value or key == "allow":
                    current.rules.append((key == "allow", value))
            elif key == "crawl-delay":
                try:
                    current.crawl_delay = max(0.0, min(float(value), 60.0))
                except ValueError:
                    pass

    def _group(self, agent: str) -> _Group | None:
        agent = agent.casefold()
        specific = [g for g in self.groups if any(a != "*" and a in agent for a in g.agents)]
        if specific:
            return specific[0]
        return next((g for g in self.groups if "*" in g.agents), None)

    def allowed(self, url: str, agent: str = AGENT_TOKEN) -> bool:
        if self.unreachable:
            return False
        group = self._group(agent)
        if group is None:
            return True
        parts = urlsplit(url)
        path = (parts.path or "/") + (f"?{parts.query}" if parts.query else "")
        best: tuple[int, bool] | None = None
        for allow, rule in group.rules:
            if rule == "":
                continue
            if _pattern(rule).match(path):
                length = len(rule)
                # Longest match wins; on a tie, allow wins.
                if best is None or length > best[0] or (length == best[0] and allow):
                    best = (length, allow)
        return True if best is None else best[1]

    def crawl_delay(self, agent: str = AGENT_TOKEN) -> float | None:
        group = self._group(agent)
        return group.crawl_delay if group else None
