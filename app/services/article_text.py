"""Main-body extraction for fetched articles (markdown or plain text).

Removes navigation, menus, link lists, cookie/consent and subscription prompts,
advertisements, share bars, author boxes and "related / also read" sections, and keeps
the article's prose paragraphs. Publication and update dates are reported separately.
"""
from __future__ import annotations

import re
from typing import Any

from app.services.freshness import parse_date

BOILERPLATE = re.compile(
    r"\b(cookie|cookies|consent|accept all|privacy policy|terms of (?:use|service)|subscribe|newsletter|sign up|"
    r"sign in|log ?in|advertisement|sponsored|share (?:this|on)|follow us|whatsapp|telegram|download (?:the )?app|"
    r"all rights reserved|copyright ©|©\s*\d{4}|skip to (?:main )?content|toggle navigation|menu|breadcrumb|"
    r"read more|click here|tags?:|filed under|you may also like|recommended for you|trending now|most read|"
    r"also read|related (?:articles|stories|posts|news)|more from|leave a comment|comments? \(\d+\))\b", re.I)
SECTION_STOP = re.compile(r"^\s*(?:#+\s*)?(related (?:articles|stories|posts|news)|also read|more from|you may also like|"
                          r"recommended|trending|most (?:read|popular)|latest news|popular stories|about the author|"
                          r"comments)\b", re.I)
LINK_ONLY = re.compile(r"^\s*(?:[-*•|]\s*)?(?:\[[^\]]*\]\([^)]*\)\s*[|·•,-]?\s*)+$")
MD_LINK = re.compile(r"!?\[([^\]]*)\]\([^)]*\)")
UPDATED = re.compile(r"\b(?:updated|last updated|modified)\s*(?:on|:)?\s*([A-Z][a-z]{2,8}\.? \d{1,2},? \d{4}|\d{1,2} [A-Z][a-z]{2,8},? \d{4}|"
                     r"\d{4}-\d{2}-\d{2})", re.I)
PUBLISHED = re.compile(r"\b(?:published|posted|first published)\s*(?:on|:)?\s*([A-Z][a-z]{2,8}\.? \d{1,2},? \d{4}|"
                       r"\d{1,2} [A-Z][a-z]{2,8},? \d{4}|\d{4}-\d{2}-\d{2})", re.I)


def clean_article(text: str, *, max_chars: int = 12000) -> str:
    lines = (text or "").splitlines()
    kept: list[str] = []
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        if SECTION_STOP.match(line) and len(" ".join(kept)) > 150:
            break  # everything after "Related articles" etc. is not the story
        if LINK_ONLY.match(line):
            continue
        plain = MD_LINK.sub(r"\1", line)
        plain = re.sub(r"[#*_>`]+", " ", plain)
        plain = " ".join(plain.split())
        words = plain.split()
        if len(words) < 6 and not re.search(r"[.!?]$", plain):
            continue  # menus, labels, buttons, bylines
        if BOILERPLATE.search(plain) and len(words) < 40:
            continue
        link_chars = sum(len(match.group(0)) for match in MD_LINK.finditer(line))
        if link_chars > 0.6 * max(len(line), 1):
            continue
        kept.append(plain)
    body = "\n".join(dict.fromkeys(kept))
    return body[:max_chars]


def article_dates(text: str) -> dict[str, Any]:
    head = (text or "")[:6000]
    published = PUBLISHED.search(head)
    updated = UPDATED.search(head)
    def parse(value):
        return parse_date(value) or parse_date(value.replace(",", "")) or parse_date(value.replace(".", ""))
    pub = parse(published.group(1)) if published else None
    upd = parse(updated.group(1)) if updated else None
    return {"published": pub.isoformat() if pub else None, "updated": upd.isoformat() if upd else None}
