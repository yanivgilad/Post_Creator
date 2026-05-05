from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import os
from pathlib import Path


def _as_bool(raw: str | None, default: bool) -> bool:
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _as_int(raw: str | None, default: int) -> int:
    if raw is None or raw.strip() == "":
        return default
    return int(raw)


def _as_list(raw: str | None, default: list[str]) -> list[str]:
    if raw is None or raw.strip() == "":
        return list(default)
    return [item.strip() for item in raw.split(",") if item.strip()]


def _as_source_weights(raw: str | None) -> dict[str, float]:
    default = {
        "hackernews": 1.0,
        "reddit": 0.9,
        "github": 1.1,
        "product_hunt": 1.0,
        "rss": 0.8,
    }
    if raw is None or raw.strip() == "":
        return default

    parsed: dict[str, float] = {}
    for item in raw.split(","):
        if ":" not in item:
            continue
        name, value = item.split(":", 1)
        name = name.strip()
        value = value.strip()
        if not name or not value:
            continue
        parsed[name] = float(value)
    return parsed or default


@dataclass(frozen=True)
class Settings:
    host: str
    port: int
    database_url: str
    since_hours: int
    top_n: int
    draft_count: int
    dedup_days: int
    schedule_hour: int
    schedule_minute: int
    enable_hackernews: bool
    enable_reddit: bool
    enable_github: bool
    enable_product_hunt: bool
    enable_rss: bool
    rss_feeds: list[str]
    reddit_subreddits: list[str]
    keywords: list[str]
    source_weights: dict[str, float]
    article_llm_options: list[str]
    openrouter_api_key: str | None
    github_token: str | None
    product_hunt_token: str | None

    @property
    def data_dir(self) -> Path:
        if self.database_url.startswith("sqlite:///"):
            raw_path = self.database_url.removeprefix("sqlite:///")
            db_path = Path(raw_path)
            if not db_path.is_absolute():
                db_path = Path.cwd() / db_path
            return db_path.parent
        return Path.cwd() / "data"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings(
        host=os.getenv("ARTICLE_WRITER_HOST", "127.0.0.1"),
        port=_as_int(os.getenv("ARTICLE_WRITER_PORT"), 8000),
        database_url=os.getenv("ARTICLE_WRITER_DATABASE_URL", "sqlite:///./data/article_writer.db"),
        since_hours=_as_int(os.getenv("ARTICLE_WRITER_SINCE_HOURS"), 72),
        top_n=_as_int(os.getenv("ARTICLE_WRITER_TOP_N"), 5),
        draft_count=_as_int(os.getenv("ARTICLE_WRITER_DRAFT_COUNT"), 3),
        dedup_days=_as_int(os.getenv("ARTICLE_WRITER_DEDUP_DAYS"), 21),
        schedule_hour=_as_int(os.getenv("ARTICLE_WRITER_SCHEDULE_HOUR"), 9),
        schedule_minute=_as_int(os.getenv("ARTICLE_WRITER_SCHEDULE_MINUTE"), 0),
        enable_hackernews=_as_bool(os.getenv("ARTICLE_WRITER_ENABLE_HACKERNEWS"), True),
        enable_reddit=_as_bool(os.getenv("ARTICLE_WRITER_ENABLE_REDDIT"), True),
        enable_github=_as_bool(os.getenv("ARTICLE_WRITER_ENABLE_GITHUB"), True),
        enable_product_hunt=_as_bool(os.getenv("ARTICLE_WRITER_ENABLE_PRODUCT_HUNT"), False),
        enable_rss=_as_bool(os.getenv("ARTICLE_WRITER_ENABLE_RSS"), True),
        rss_feeds=_as_list(
            os.getenv("ARTICLE_WRITER_RSS_FEEDS"),
            [
                "https://openai.com/news/rss.xml",
                "https://huggingface.co/blog/feed.xml",
                "https://simonwillison.net/atom/everything/",
            ],
        ),
        reddit_subreddits=_as_list(
            os.getenv("ARTICLE_WRITER_REDDIT_SUBREDDITS"),
            ["MachineLearning", "LocalLLaMA", "artificial"],
        ),
        keywords=_as_list(
            os.getenv("ARTICLE_WRITER_KEYWORDS"),
            [
                "ai",
                "agent",
                "agents",
                "llm",
                "model",
                "models",
                "openai",
                "anthropic",
                "gemini",
                "claude",
                "chatgpt",
                "benchmark",
                "inference",
                "rag",
                "robotics",
                "multimodal",
            ],
        ),
        source_weights=_as_source_weights(os.getenv("ARTICLE_WRITER_SOURCE_WEIGHTS")),
        article_llm_options=_as_list(
            os.getenv("ARTICLE_WRITER_LLM_OPTIONS"),
            [
                "local-template",
                "openai/gpt-4.1-mini",
                "anthropic/claude-sonnet-4",
                "google/gemini-2.5-pro",
            ],
        ),
        openrouter_api_key=os.getenv("ARTICLE_WRITER_OPENROUTER_API_KEY") or None,
        github_token=os.getenv("ARTICLE_WRITER_GITHUB_TOKEN") or None,
        product_hunt_token=os.getenv("ARTICLE_WRITER_PRODUCT_HUNT_TOKEN") or None,
    )
