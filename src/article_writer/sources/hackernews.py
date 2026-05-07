from __future__ import annotations

from datetime import datetime
import logging

from article_writer.config import Settings
from article_writer.models import SourceItem
from article_writer.sources.base import SourceAdapter, encoded_query, matches_keywords, parse_datetime, truncate_text


logger = logging.getLogger(__name__)


class HackerNewsSource(SourceAdapter):
    name = "hackernews"

    def enabled(self, settings: Settings) -> bool:
        return settings.enable_hackernews

    def fetch(self, since: datetime, settings: Settings) -> list[SourceItem]:
        hits: dict[str, SourceItem] = {}
        timestamp = int(since.timestamp())
        for query in settings.hackernews_queries:
            url = (
                "https://hn.algolia.com/api/v1/search_by_date"
                f"?query={encoded_query(query)}&tags=story&hitsPerPage=20&numericFilters=created_at_i>{timestamp}"
            )
            try:
                payload = self._get_json(url, settings)
            except Exception as exc:
                logger.warning("[hackernews] query failed %r: %s", query, exc)
                continue
            for hit in payload.get("hits", []):
                title = hit.get("title") or hit.get("story_title") or ""
                article_url = hit.get("url") or hit.get("story_url")
                if not title or not article_url:
                    continue
                body = f"{title} {hit.get('story_text') or ''}"
                if not matches_keywords(body, settings.keywords):
                    continue
                published_at = parse_datetime(hit.get("created_at"))
                if published_at is None or published_at < since:
                    continue
                external_id = str(hit.get("objectID") or article_url)
                points = float(hit.get("points") or 0)
                comments = float(hit.get("num_comments") or 0)
                item = SourceItem(
                    source_name=self.name,
                    external_id=external_id,
                    title=title,
                    url=article_url,
                    summary=truncate_text(title),
                    author=hit.get("author"),
                    published_at=published_at,
                    engagement_score=points + comments * 0.6,
                    metadata={"points": points, "comments": comments, "query": query},
                )
                hits[item.dedup_key] = item
        return list(hits.values())
