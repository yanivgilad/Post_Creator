from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
import json
import os
from pathlib import Path
from typing import Any


DEFAULT_ARTICLE_LLM_OPTIONS = [
    "local-template",
    "google/gemini-2.5-pro",
]

DEFAULT_SOURCE_CONFIG_FILE = "sources.json"


def _default_source_catalog() -> dict[str, Any]:
    return {
        "keywords": [
            "ai",
            "agent",
            "agents",
            "llm",
            "model",
            "models",
            "machine learning",
            "openai",
            "anthropic",
            "gemini",
            "claude",
            "chatgpt",
            "copilot",
            "benchmark",
            "inference",
            "rag",
            "autonomy",
            "autonomous",
            "self-driving",
            "robotics",
            "multimodal",
        ],
        "sources": {
            "hackernews": {
                "enabled": True,
                "weight": 1.0,
                "queries": ["AI", "LLM", "agent", "open source ai"],
            },
            "reddit": {
                "enabled": True,
                "weight": 0.9,
                "subreddits": ["MachineLearning", "LocalLLaMA", "artificial"],
            },
            "github": {
                "enabled": True,
                "weight": 1.1,
                "queries": ["llm", "ai agent", "open source ai"],
            },
            "product_hunt": {
                "enabled": False,
                "weight": 1.0,
            },
            "rss": {
                "enabled": True,
                "weight": 0.8,
                "feeds": [
                    "https://openai.com/news/rss.xml",
                    "https://huggingface.co/blog/feed.xml",
                    "https://blogs.microsoft.com/feed/",
                    "https://www.apple.com/newsroom/rss-feed.rss",
                    "https://simonwillison.net/atom/everything/",
                    "https://lastweekin.ai/feed",
                    "https://ir.tesla.com/rss.xml",
                ],
            },
            "arxiv": {
                "enabled": True,
                "weight": 1.2,
                "feeds": [
                    "https://rss.arxiv.org/rss/cs.AI",
                    "https://rss.arxiv.org/rss/cs.LG",
                ],
            },
            "deepmind": {
                "enabled": True,
                "weight": 0.9,
                "feeds": ["https://deepmind.google/blog/rss"],
            },
            "lobsters": {
                "enabled": True,
                "weight": 0.85,
                "endpoints": [
                    "https://lobste.rs/t/ai.json",
                    "https://lobste.rs/t/ml.json",
                ],
            },
        },
    }


def _is_supported_article_llm_option(llm_name: str) -> bool:
    return llm_name == "local-template" or llm_name.startswith("google/")


def filter_supported_article_llm_options(llm_options: list[str]) -> list[str]:
    filtered: list[str] = []
    for llm_name in llm_options:
        if _is_supported_article_llm_option(llm_name) and llm_name not in filtered:
            filtered.append(llm_name)
    return filtered or list(DEFAULT_ARTICLE_LLM_OPTIONS)


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


def _as_json_bool(raw: Any, default: bool) -> bool:
    if raw is None:
        return default
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, (int, float)):
        return bool(raw)
    if isinstance(raw, str):
        return raw.strip().lower() in {"1", "true", "yes", "on"}
    return default


def _as_json_float(raw: Any, default: float) -> float:
    if raw is None:
        return default
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default


def _as_json_list(raw: Any, default: list[str]) -> list[str]:
    if raw is None:
        return list(default)
    if isinstance(raw, str):
        return _as_list(raw, default)
    if not isinstance(raw, list):
        return list(default)
    values = [str(item).strip() for item in raw if str(item).strip()]
    return values or list(default)


def _resolve_source_config_path(raw: str | None) -> Path:
    config_path = Path(raw or DEFAULT_SOURCE_CONFIG_FILE)
    if not config_path.is_absolute():
        config_path = Path.cwd() / config_path
    return config_path


def _load_source_catalog(path: Path) -> dict[str, Any]:
    catalog = _default_source_catalog()
    if not path.exists():
        return catalog

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return catalog

    if not isinstance(payload, dict):
        return catalog

    catalog["keywords"] = _as_json_list(payload.get("keywords"), catalog["keywords"])

    raw_sources = payload.get("sources")
    if not isinstance(raw_sources, dict):
        return catalog

    for source_name, default_section in catalog["sources"].items():
        section = raw_sources.get(source_name)
        if not isinstance(section, dict):
            continue
        merged_section = dict(default_section)
        merged_section.update(section)
        catalog["sources"][source_name] = merged_section
    return catalog


@dataclass(frozen=True)
class Settings:
    host: str
    port: int
    database_url: str
    source_config_file: str
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
    enable_arxiv: bool
    enable_deepmind: bool
    enable_lobsters: bool
    hackernews_queries: list[str]
    rss_feeds: list[str]
    github_queries: list[str]
    arxiv_feeds: list[str]
    deepmind_feeds: list[str]
    lobsters_endpoints: list[str]
    reddit_subreddits: list[str]
    keywords: list[str]
    source_weights: dict[str, float]
    article_llm_options: list[str]
    gemini_api_key: str | None
    github_token: str | None
    product_hunt_token: str | None
    twitter_prompt_file: str | None
    linkedin_prompt_file: str | None
    reddit_prompt_file: str | None
    log_dir: str = field(default="data/logs")
    log_level: str = field(default="INFO")

    @property
    def supported_article_llm_options(self) -> list[str]:
        return filter_supported_article_llm_options(self.article_llm_options)

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
    source_config_path = _resolve_source_config_path(os.getenv("ARTICLE_WRITER_SOURCE_CONFIG_FILE"))
    source_catalog = _load_source_catalog(source_config_path)
    source_sections = source_catalog["sources"]
    return Settings(
        host=os.getenv("ARTICLE_WRITER_HOST", "127.0.0.1"),
        port=_as_int(os.getenv("ARTICLE_WRITER_PORT"), 8000),
        database_url=os.getenv("ARTICLE_WRITER_DATABASE_URL", "sqlite:///./data/article_writer.db"),
        source_config_file=str(source_config_path),
        since_hours=_as_int(os.getenv("ARTICLE_WRITER_SINCE_HOURS"), 72),
        top_n=_as_int(os.getenv("ARTICLE_WRITER_TOP_N"), 10),
        draft_count=_as_int(os.getenv("ARTICLE_WRITER_DRAFT_COUNT"), 3),
        dedup_days=_as_int(os.getenv("ARTICLE_WRITER_DEDUP_DAYS"), 21),
        schedule_hour=_as_int(os.getenv("ARTICLE_WRITER_SCHEDULE_HOUR"), 9),
        schedule_minute=_as_int(os.getenv("ARTICLE_WRITER_SCHEDULE_MINUTE"), 0),
        enable_hackernews=_as_json_bool(source_sections["hackernews"].get("enabled"), True),
        enable_reddit=_as_json_bool(source_sections["reddit"].get("enabled"), True),
        enable_github=_as_json_bool(source_sections["github"].get("enabled"), True),
        enable_product_hunt=_as_json_bool(source_sections["product_hunt"].get("enabled"), False),
        enable_rss=_as_json_bool(source_sections["rss"].get("enabled"), True),
        enable_arxiv=_as_json_bool(source_sections["arxiv"].get("enabled"), True),
        enable_deepmind=_as_json_bool(source_sections["deepmind"].get("enabled"), True),
        enable_lobsters=_as_json_bool(source_sections["lobsters"].get("enabled"), True),
        hackernews_queries=_as_json_list(source_sections["hackernews"].get("queries"), []),
        rss_feeds=_as_json_list(source_sections["rss"].get("feeds"), []),
        github_queries=_as_json_list(source_sections["github"].get("queries"), []),
        arxiv_feeds=_as_json_list(source_sections["arxiv"].get("feeds"), []),
        deepmind_feeds=_as_json_list(source_sections["deepmind"].get("feeds"), []),
        lobsters_endpoints=_as_json_list(source_sections["lobsters"].get("endpoints"), []),
        reddit_subreddits=_as_json_list(source_sections["reddit"].get("subreddits"), []),
        keywords=_as_json_list(source_catalog.get("keywords"), []),
        source_weights={
            source_name: _as_json_float(section.get("weight"), 1.0)
            for source_name, section in source_sections.items()
        },
        article_llm_options=filter_supported_article_llm_options(
            _as_list(
                os.getenv("ARTICLE_WRITER_LLM_OPTIONS"),
                DEFAULT_ARTICLE_LLM_OPTIONS,
            )
        ),
        gemini_api_key=os.getenv("ARTICLE_WRITER_GEMINI_API_KEY") or None,
        github_token=os.getenv("ARTICLE_WRITER_GITHUB_TOKEN") or None,
        product_hunt_token=os.getenv("ARTICLE_WRITER_PRODUCT_HUNT_TOKEN") or None,
        twitter_prompt_file=os.getenv("ARTICLE_WRITER_TWITTER_PROMPT_FILE") or None,
        linkedin_prompt_file=os.getenv("ARTICLE_WRITER_LINKEDIN_PROMPT_FILE") or None,
        reddit_prompt_file=os.getenv("ARTICLE_WRITER_REDDIT_PROMPT_FILE") or None,
        log_dir=os.getenv("ARTICLE_WRITER_LOG_DIR", "data/logs"),
        log_level=os.getenv("ARTICLE_WRITER_LOG_LEVEL", "INFO"),
    )
