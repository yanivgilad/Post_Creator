from __future__ import annotations

from datetime import datetime, timezone
import math
import re

from article_writer.config import Settings
from article_writer.models import RankedTrend, SourceItem
from article_writer.storage.sqlite_store import TIER_WEIGHTS


KEYWORD_SCORE_CAP = 3.0


def rank_items(
    items: list[SourceItem],
    settings: Settings,
    keywords: list[tuple[str, str]] | None = None,
) -> tuple[list[RankedTrend], list[RankedTrend]]:
    """Return (top_n_ranked, all_scored) — all_scored is sorted by score desc.

    `keywords` is a list of `(keyword, tier)` tuples from the live DB. When not
    provided, falls back to `settings.keywords` treated as MEDIUM (legacy path
    for tests / direct callers).
    """
    if keywords is None:
        keywords = [(kw, "MEDIUM") for kw in settings.keywords]

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
        matched = _keyword_matches(item, keywords)
        keyword_score = min(sum(w for _, w in matched), KEYWORD_SCORE_CAP)
        novelty_bonus = 1.0 / math.sqrt(age_hours)
        total = source_weight + recency_score + engagement_score + keyword_score + novelty_bonus
        matched_names = [kw for kw, _ in matched]
        evidence = [
            f"Source weight: {settings.source_weights.get(item.source_name, 1.0):.2f}",
            f"Age: {age_hours:.1f}h",
            f"Engagement: {item.engagement_score:.1f}",
        ]
        if matched_names:
            evidence.append(
                f"Keyword matches: {', '.join(matched_names)} (weight {sum(w for _, w in matched):.2f})"
            )
        if item.metadata:
            for key in ("points", "comments", "stars", "forks", "ups", "votes", "subreddit", "query"):
                if key in item.metadata:
                    evidence.append(f"{key.replace('_', ' ').title()}: {item.metadata[key]}")
        reason_summary = _reason_summary(item, age_hours, matched_names)
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


def _keyword_matches(item: SourceItem, keywords: list[tuple[str, str]]) -> list[tuple[str, float]]:
    haystack = f"{item.title} {item.summary}".lower()
    result = []
    for keyword, tier in keywords:
        kw_lower = keyword.lower()
        base = TIER_WEIGHTS.get(tier, TIER_WEIGHTS["MEDIUM"])
        words = kw_lower.split()
        if len(words) <= 1:
            if re.search(r"\b" + re.escape(kw_lower) + r"\b", haystack):
                result.append((keyword, base))
        elif kw_lower in haystack:
            # Full phrase match → full weight
            result.append((keyword, base))
        else:
            # Partial: proportion of individual words that appear
            matched_count = sum(
                1 for w in words if re.search(r"\b" + re.escape(w) + r"\b", haystack)
            )
            if matched_count > 0:
                result.append((keyword, base * matched_count / len(words)))
    return result


def _reason_summary(item: SourceItem, age_hours: float, matched_keywords: list[str]) -> str:
    age = f"{age_hours:.1f}h old"
    if matched_keywords:
        return f"{age} · {', '.join(matched_keywords)}"
    return age
