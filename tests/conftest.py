from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

import pytest

from article_writer.config import Settings
from article_writer.models import SourceItem, utc_now


@pytest.fixture
def settings(tmp_path):
    return Settings(
        host="127.0.0.1",
        port=8000,
        database_url=f"sqlite:///{tmp_path / 'article_writer.db'}",
        since_hours=72,
        top_n=5,
        draft_count=3,
        dedup_days=21,
        schedule_hour=9,
        schedule_minute=0,
        enable_hackernews=False,
        enable_reddit=False,
        enable_github=False,
        enable_product_hunt=False,
        enable_rss=False,
        rss_feeds=[],
        reddit_subreddits=[],
        keywords=["ai", "llm", "agent", "model", "robotics"],
        source_weights={
            "hackernews": 1.0,
            "reddit": 0.9,
            "github": 1.1,
            "product_hunt": 1.0,
            "rss": 0.8,
            "fake": 1.3,
        },
        article_llm_options=["local-template", "openai/gpt-4.1-mini"],
        openrouter_api_key=None,
        github_token=None,
        product_hunt_token=None,
    )


@pytest.fixture
def sample_items():
    now = utc_now()
    return [
        SourceItem(
            source_name="fake",
            external_id="1",
            title="New AI agent benchmark released",
            url="https://example.com/agent-benchmark",
            summary="A fresh AI benchmark for agentic systems.",
            author="tester",
            published_at=now - timedelta(hours=4),
            engagement_score=120.0,
        ),
        SourceItem(
            source_name="fake",
            external_id="2",
            title="Old robotics note",
            url="https://example.com/robotics-note",
            summary="An older robotics note.",
            author="tester",
            published_at=now - timedelta(hours=60),
            engagement_score=20.0,
        ),
    ]
