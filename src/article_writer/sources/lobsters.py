from __future__ import annotations

from datetime import datetime
import logging

from article_writer.config import Settings
from article_writer.models import SourceItem
from article_writer.sources.base import SourceAdapter, matches_keywords, parse_datetime, truncate_text


logger = logging.getLogger(__name__)


class LobstersSource(SourceAdapter):
    name = "lobsters"

    def enabled(self, settings: Settings) -> bool:
        return settings.enable_lobsters

    def fetch(
        self,
        since: datetime,
        settings: Settings,
        *,
        keywords: list[str] | None = None,
    ) -> list[SourceItem]:
        active_keywords = settings.keywords if keywords is None else keywords
        items: dict[str, SourceItem] = {}
        for stream, endpoints in settings.lobsters_endpoints.items():
            for endpoint in endpoints:
                try:
                    stories = self._get_json(endpoint, settings)
                except Exception as exc:
                    logger.warning("[lobsters] endpoint failed %s: %s", endpoint, exc)
                    continue
                if not isinstance(stories, list):
                    logger.warning("[lobsters] endpoint returned unexpected format %s", endpoint)
                    continue
                for story in stories:
                    if not isinstance(story, dict):
                        continue
                    title = story.get("title") or ""
                    url = story.get("url") or story.get("short_id_url") or ""
                    if not title or not url:
                        continue
                    description = story.get("description") or ""
                    if not matches_keywords(f"{title} {description}", active_keywords):
                        continue
                    published_at = parse_datetime(story.get("created_at"))
                    if published_at is None or published_at < since:
                        continue
                    score = float(story.get("score") or 0)
                    comment_count = float(story.get("comment_count") or 0)
                    submitter_user = story.get("submitter_user")
                    author = submitter_user or None
                    if isinstance(submitter_user, dict):
                        author = submitter_user.get("username")
                    item = SourceItem(
                        source_name=self.name,
                        external_id=story.get("short_id") or url,
                        title=title,
                        url=url,
                        summary=truncate_text(description or title),
                        author=author,
                        published_at=published_at,
                        engagement_score=score + comment_count * 0.6,
                        metadata={"score": score, "comments": comment_count, "endpoint": endpoint, "stream": stream},
                        stream=stream,
                    )
                    items[item.dedup_key] = item
        return list(items.values())
