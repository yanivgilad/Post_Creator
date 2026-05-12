from __future__ import annotations

import json

from article_writer.config import get_settings


def test_source_catalog_file_controls_source_settings(monkeypatch, tmp_path):
    source_catalog = tmp_path / "sources.json"
    source_catalog.write_text(
        json.dumps(
            {
                "keywords": ["ai", "copilot", "autonomy"],
                "sources": {
                    "hackernews": {"enabled": False, "weight": 1.4},
                    "reddit": {"subreddits": ["MachineLearning", "singularity"]},
                    "rss": {
                        "enabled": True,
                        "weight": 1.5,
                        "feeds": [
                            "https://blogs.microsoft.com/feed/",
                            "https://www.apple.com/newsroom/rss-feed.rss",
                            "https://ir.tesla.com/rss.xml",
                        ],
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("ARTICLE_WRITER_SOURCE_CONFIG_FILE", str(source_catalog))
    get_settings.cache_clear()

    try:
        settings = get_settings()
        assert settings.enable_hackernews is False
        assert settings.enable_rss is True
        assert settings.source_config_file == str(source_catalog)
        assert settings.hackernews_queries["software"] == ["AI", "LLM", "agent", "open source ai"]
        assert settings.github_queries["software"] == ["llm", "ai agent", "open source ai"]
        assert settings.arxiv_feeds == [
            "https://rss.arxiv.org/rss/cs.AI",
            "https://rss.arxiv.org/rss/cs.LG",
        ]
        assert settings.rss_feeds["software"] == [
            "https://blogs.microsoft.com/feed/",
            "https://www.apple.com/newsroom/rss-feed.rss",
            "https://ir.tesla.com/rss.xml",
        ]
        assert settings.reddit_subreddits["software"] == ["MachineLearning", "singularity"]
        assert settings.source_weights["hackernews"] == 1.4
        assert settings.source_weights["rss"] == 1.5
        assert settings.source_weights["deepmind"] == 0.9

        assert "ai" in settings.keywords
        assert "copilot" in settings.keywords
        assert "autonomy" in settings.keywords
    finally:
        get_settings.cache_clear()