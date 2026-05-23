from __future__ import annotations

from datetime import timedelta

from article_writer.models import SourceItem, utc_now
from article_writer.ranking.scorer import KEYWORD_SCORE_CAP, _keyword_match_weights, rank_items


def _item(title: str, summary: str = "") -> SourceItem:
    return SourceItem(
        source_name="fake",
        external_id=title,
        title=title,
        url=f"https://example.com/{title}",
        summary=summary,
        author="t",
        published_at=utc_now() - timedelta(hours=2),
        engagement_score=50.0,
    )


def test_match_weights_empty_list_returns_no_weights():
    item = _item("LLM agent benchmark")
    assert _keyword_match_weights(item, []) == []


def test_match_weights_uses_tier_weight():
    item = _item("RAG at scale needs eval")
    weights = _keyword_match_weights(item, [("rag", "HIGH"), ("eval", "LOW"), ("absent", "MEDIUM")])
    assert sorted(weights) == [0.3, 1.0]


def test_score_saturates_at_cap(settings):
    item = _item("rag llm agent eval benchmark", summary="rag llm agent")
    keywords = [(k, "HIGH") for k in ["rag", "llm", "agent", "eval", "benchmark"]]
    ranked, _all = rank_items([item], settings, keywords)
    # All five HIGH matches sum to 5.0 but the cap is 3.0; full score should reflect that.
    # We can't isolate the keyword component exactly, but we can compare to a no-match baseline.
    ranked_none, _ = rank_items([item], settings, [("absent", "HIGH")])
    diff = ranked[0].score - ranked_none[0].score
    assert abs(diff - KEYWORD_SCORE_CAP) < 0.01


def test_score_low_tier_lifts_less_than_high_tier(settings):
    item = _item("rag pipeline")
    high_ranked, _ = rank_items([item], settings, [("rag", "HIGH")])
    low_ranked, _ = rank_items([item], settings, [("rag", "LOW")])
    assert high_ranked[0].score > low_ranked[0].score


def test_evidence_string_includes_weight(settings):
    item = _item("rag eval")
    ranked, _ = rank_items([item], settings, [("rag", "HIGH"), ("eval", "MEDIUM")])
    evidence_lines = ranked[0].evidence
    keyword_line = next(line for line in evidence_lines if line.startswith("Keyword matches"))
    assert "weight 1.60" in keyword_line
