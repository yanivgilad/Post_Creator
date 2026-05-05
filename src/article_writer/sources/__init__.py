from __future__ import annotations

from article_writer.config import Settings
from article_writer.sources.github import GitHubSource
from article_writer.sources.hackernews import HackerNewsSource
from article_writer.sources.product_hunt import ProductHuntSource
from article_writer.sources.reddit import RedditSource
from article_writer.sources.rss import RSSSource


ALL_SOURCE_ADAPTERS = (
    HackerNewsSource,
    RedditSource,
    GitHubSource,
    ProductHuntSource,
    RSSSource,
)


def build_enabled_sources(settings: Settings):
    adapters = [adapter() for adapter in ALL_SOURCE_ADAPTERS]
    return [adapter for adapter in adapters if adapter.enabled(settings)]
