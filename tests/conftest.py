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
        source_config_file=str(tmp_path / "sources.json"),
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
        enable_arxiv=False,
        enable_deepmind=False,
        enable_lobsters=False,
        enable_netlify=False,
        hackernews_queries=["AI", "LLM", "agent", "open source ai"],
        rss_feeds=[
            "https://openai.com/news/rss.xml",
            "https://huggingface.co/blog/feed.xml",
        ],
        github_queries=["llm", "ai agent", "open source ai"],
        arxiv_feeds=[
            "https://rss.arxiv.org/rss/cs.AI",
            "https://rss.arxiv.org/rss/cs.LG",
        ],
        deepmind_feeds=["https://deepmind.google/blog/rss"],
        lobsters_endpoints=[
            "https://lobste.rs/t/ai.json",
            "https://lobste.rs/t/ml.json",
        ],
        reddit_subreddits=["MachineLearning", "LocalLLaMA", "artificial"],
        keywords=["ai", "llm", "agent", "model", "robotics"],
        source_weights={
            "hackernews": 1.0,
            "reddit": 0.9,
            "github": 1.1,
            "product_hunt": 1.0,
            "rss": 0.8,
            "fake": 1.3,
        },
        article_llm_options=["local-template", "google/gemini-2.5-pro"],
        gemini_api_key=None,
        github_token=None,
        product_hunt_token=None,
        twitter_prompt_file=None,
        linkedin_prompt_file=None,
        reddit_prompt_file=None,
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
