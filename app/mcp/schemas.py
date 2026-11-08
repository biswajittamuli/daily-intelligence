"""Common source record schema used by retrieval and processing stages."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class Evidence(BaseModel):
    text: str
    source_url: str | None = None
    locator: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)


class SourceRecord(BaseModel):
    model_config = ConfigDict(extra="allow")

    title: str = ""
    original_url: HttpUrl | str
    canonical_url: str | None = None
    domain: str | None = None
    published_at: str | None = None
    retrieved_at: datetime | str | None = None
    source_type: str = "unknown"
    content: str = ""
    excerpts: list[str] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    classification: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
