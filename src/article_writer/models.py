from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any
from urllib.parse import urlsplit, urlunsplit


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def normalize_url(url: str) -> str:
    parts = urlsplit(url.strip())
    return urlunsplit(parts._replace(fragment=""))


@dataclass(slots=True)
class SourceItem:
    source_name: str
    external_id: str
    title: str
    url: str
    summary: str
    author: str | None
    published_at: datetime
    engagement_score: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)
    stream: str = "software"

    @property
    def dedup_key(self) -> str:
        payload = f"{self.source_name}|{normalize_url(self.url)}|{' '.join(self.title.lower().split())}"
        return sha256(payload.encode("utf-8")).hexdigest()


@dataclass(slots=True)
class RankedTrend:
    source_item: SourceItem
    score: float
    reason_summary: str
    evidence: list[str]
    supporting_urls: list[str]


@dataclass(slots=True)
class DraftArtifact:
    platform: str
    title: str
    body: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ArticleArtifact:
    trend_id: int
    language: str
    target_outlet: str
    llm_name: str
    title: str
    body: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class PipelineSnapshot:
    ranked_trends: list[RankedTrend]
    drafts: list[DraftArtifact]
    raw_item_count: int
    unique_item_count: int
    errors: list[str] = field(default_factory=list)
    all_scored_items: list[RankedTrend] = field(default_factory=list)
