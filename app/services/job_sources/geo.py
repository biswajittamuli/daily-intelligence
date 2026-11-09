"""Work arrangement relative to India, from evidence in the listing only.

Never says a job is available in India without a location or remote statement that supports it.
"""
from __future__ import annotations

import re
from typing import Any

INDIA = re.compile(r"\b(india|bengaluru|bangalore|hyderabad|pune|mumbai|delhi|new delhi|ncr|gurgaon|gurugram|noida|"
                   r"chennai|kochi|cochin|ahmedabad|jaipur|kolkata|chandigarh|indore|coimbatore|trivandrum|"
                   r"thiruvananthapuram|mysuru|mysore|nagpur|vadodara|lucknow|bhubaneswar|guwahati|karnataka|"
                   r"maharashtra|telangana|tamil nadu|kerala|gujarat|haryana|uttar pradesh)\b", re.I)
REMOTE = re.compile(r"\b(remote|work from home|wfh|anywhere|distributed)\b", re.I)
HYBRID = re.compile(r"\bhybrid\b", re.I)
RELOCATION = re.compile(r"\b(relocation (?:assistance|support|package|provided|offered)|visa sponsorship|willing to relocate|"
                        r"relocate to)\b", re.I)
FOREIGN = re.compile(r"\b(united states|usa|u\.s\.|us only|canada|united kingdom|uk|london|europe|eu only|emea|germany|"
                     r"berlin|france|paris|netherlands|amsterdam|singapore|australia|sydney|japan|tokyo|brazil|mexico|"
                     r"new york|san francisco|seattle|austin|boston|toronto|dublin|ireland|poland|spain|"
                     r"americas|latam|north america)\b", re.I)
GLOBAL = re.compile(r"\b(worldwide|global|anywhere in the world|any country|apac|asia)\b", re.I)

LABELS = {"india": "India-based", "india_hybrid": "Hybrid · India", "remote_india": "Remote from India",
          "remote_restricted": "Remote · restricted to another country", "relocation": "Relocation offered",
          "abroad": "Outside India", "unknown": "Location not stated"}


def work_arrangement(location: str | None, remote: str | None = None, text: str = "") -> dict[str, Any]:
    loc = " ".join(str(part or "") for part in (location, remote)).strip()
    body = str(text or "")[:6000]
    in_india = bool(INDIA.search(loc))
    is_remote = bool(REMOTE.search(loc))
    foreign = bool(FOREIGN.search(loc))
    if is_remote:
        if in_india or re.search(r"remote[^,;]*\bindia\b", f"{loc} {body[:1500]}", re.I):
            kind = "remote_india"
        elif GLOBAL.search(loc) and not foreign:
            kind = "remote_india"
        elif foreign:
            kind = "remote_restricted"
        else:
            kind = "unknown"
    elif in_india:
        kind = "india_hybrid" if HYBRID.search(f"{loc} {body[:800]}") else "india"
    elif foreign:
        kind = "relocation" if RELOCATION.search(body) else "abroad"
    else:
        kind = "unknown"
    evidence = loc or None
    return {"kind": kind, "label": LABELS[kind], "evidence": evidence,
            "india_eligible": kind in {"india", "india_hybrid", "remote_india"}}
