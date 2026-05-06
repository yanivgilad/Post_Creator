from __future__ import annotations

from article_writer.ranking.scorer import rank_items


def test_rank_items_prefers_fresher_high_signal_items(settings, sample_items):
    ranked, all_scored = rank_items(sample_items, settings, prior_urls=set())

    assert ranked
    assert ranked[0].source_item.title == "New AI agent benchmark released"
    assert ranked[0].score > ranked[-1].score
    assert len(all_scored) >= len(ranked)
    assert all_scored[0].score >= all_scored[-1].score


def test_rank_items_skips_recently_seen_urls(settings, sample_items):
    ranked, all_scored = rank_items(sample_items, settings, prior_urls={"https://example.com/agent-benchmark"})

    assert len(ranked) == 1
    assert ranked[0].source_item.title == "Old robotics note"
