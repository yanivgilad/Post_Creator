from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

import pytest

from article_writer.config import Settings
from article_writer.models import SourceItem, utc_now


def make_settings(tmp_path):
    return Settings(
        host="127.0.0.1",
        port=8000,
        database_url=f"sqlite:///{tmp_path / 'article_writer.db'}",
        source_config_file=str(tmp_path / "sources.json"),
        since_hours=72,
        top_n=5,
        draft_count=3,
        dedup_days=21,
        schedule_hour=9,
        schedule_minute=0,
        scheduler_enabled=False,
        enable_hackernews=False,
        enable_reddit=False,
        enable_github=False,
        enable_product_hunt=False,
        enable_rss=False,
        enable_arxiv=False,
        enable_deepmind=False,
        enable_lobsters=False,
        enable_netlify=False,
        hackernews_queries={"software": ["AI", "LLM"], "gaming": [], "hardware": []},
        rss_feeds={"software": [], "gaming": [], "hardware": []},
        github_queries={"software": ["llm"], "gaming": [], "hardware": []},
        reddit_subreddits={"software": ["MachineLearning"], "gaming": [], "hardware": []},
        lobsters_endpoints={"software": [], "gaming": [], "hardware": []},
        arxiv_feeds=[],
        arxiv_stream="software",
        deepmind_feeds=[],
        deepmind_stream="software",
        netlify_stream="software",
        product_hunt_stream="software",
        keywords=["ai", "llm", "agent"],
        source_weights={"hackernews": 1.0, "reddit": 0.9, "github": 1.1},
        article_llm_options=["azure/gpt-4o"],
        gemini_api_key=None,
        azure_openai_api_key=None,
        azure_openai_endpoint=None,
        azure_openai_api_version=None,
        github_token=None,
        product_hunt_token=None,
        twitter_prompt_file=None,
        linkedin_prompt_file=None,
        reddit_prompt_file=None,
    )


@pytest.fixture
def settings(tmp_path):
    return make_settings(tmp_path)


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
