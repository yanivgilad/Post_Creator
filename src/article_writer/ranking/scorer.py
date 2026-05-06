from __future__ import annotations

from datetime import datetime, timezone
import math

from article_writer.config import Settings
from article_writer.models import RankedTrend, SourceItem


def rank_items(
    items: list[SourceItem], settings: Settings
) -> tuple[list[RankedTrend], list[RankedTrend]]:
    """Return (top_n_ranked, all_scored) — all_scored is sorted by score desc."""
    now = datetime.now(timezone.utc)
    unique_items: dict[str, SourceItem] = {}
    for item in items:
        existing = unique_items.get(item.dedup_key)
        if existing is None or item.engagement_score > existing.engagement_score:
            unique_items[item.dedup_key] = item

    scored: list[tuple[float, SourceItem, list[str], str]] = []
    for item in unique_items.values():
        age_hours = max((now - item.published_at).total_seconds() / 3600, 0.1)
        recency_score = max(settings.since_hours - age_hours, 0.0) / max(settings.since_hours, 1) * 5.0
        engagement_score = min(item.engagement_score, 500.0) / 50.0
        source_weight = settings.source_weights.get(item.source_name, 1.0) * 3.0
        keyword_hits = _keyword_hits(item, settings)
        keyword_score = min(keyword_hits, 5) * 0.45
        novelty_bonus = 1.0 / math.sqrt(age_hours)
        total = source_weight + recency_score + engagement_score + keyword_score + novelty_bonus
        evidence = [
            f"Source weight: {settings.source_weights.get(item.source_name, 1.0):.2f}",
            f"Age: {age_hours:.1f}h",
            f"Engagement: {item.engagement_score:.1f}",
        ]
        if keyword_hits:
            evidence.append(f"Keyword matches: {keyword_hits}")
        if item.metadata:
            for key in ("points", "comments", "stars", "forks", "ups", "votes", "subreddit", "query"):
                if key in item.metadata:
                    evidence.append(f"{key.replace('_', ' ').title()}: {item.metadata[key]}")
        reason_summary = _reason_summary(item, age_hours, keyword_hits)
        scored.append((total, item, evidence, reason_summary))

    scored.sort(key=lambda value: value[0], reverse=True)
    all_scored = [
        RankedTrend(
            source_item=item,
            score=round(score, 2),
            reason_summary=reason_summary,
            evidence=evidence,
            supporting_urls=[item.url],
        )
        for score, item, evidence, reason_summary in scored
    ]
    top_n = all_scored[: settings.top_n]
    return top_n, all_scored


def _keyword_hits(item: SourceItem, settings: Settings) -> int:
    haystack = f"{item.title} {item.summary}".lower()
    return sum(1 for keyword in settings.keywords if keyword.lower() in haystack)


def _reason_summary(item: SourceItem, age_hours: float, keyword_hits: int) -> str:
    parts = [f"Fresh from {item.source_name}", f"{age_hours:.1f}h old"]
    if item.engagement_score:
        parts.append(f"engagement {item.engagement_score:.0f}")
    if keyword_hits:
        parts.append(f"{keyword_hits} AI keyword hits")
    return ", ".join(parts)
