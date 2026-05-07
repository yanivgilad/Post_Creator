from __future__ import annotations

from datetime import datetime
import logging

from article_writer.config import Settings
from article_writer.models import SourceItem
from article_writer.sources.base import (
    SourceAdapter,
    child_text,
    iter_xml_entries,
    parse_datetime,
    strip_html,
    truncate_text,
)


logger = logging.getLogger(__name__)


class RSSSource(SourceAdapter):
    name = "rss"

    def enabled(self, settings: Settings) -> bool:
        return settings.enable_rss and bool(settings.rss_feeds)

    def fetch(self, since: datetime, settings: Settings) -> list[SourceItem]:
        items: dict[str, SourceItem] = {}
        for feed_url in settings.rss_feeds:
            try:
                xml_text = self._get_text(
                    feed_url,
                    settings,
                    headers={"Accept": "application/rss+xml, application/atom+xml"},
                )
                entries = list(iter_xml_entries(xml_text))
            except Exception as exc:
                logger.warning("[rss] feed failed %s: %s", feed_url, exc)
                continue

            feed_item_count = 0
            for entry in entries:
                title = child_text(entry, "title") or ""
                url = child_text(entry, "link") or ""
                if not url:
                    for child in entry:
                        local_name = child.tag.split("}")[-1].lower()
                        if local_name == "link":
                            url = child.attrib.get("href") or child.text or ""
                            if url:
                                break
                if not title or not url:
                    continue
                summary = child_text(entry, "summary", "description", "content") or ""
                summary = strip_html(summary)
                published_at = parse_datetime(
                    child_text(entry, "published", "updated", "pubdate", "dc:date")
                )
                if published_at is None or published_at < since:
                    continue
                item = SourceItem(
                    source_name=self.name,
                    external_id=url,
                    title=title,
                    url=url,
                    summary=truncate_text(summary or title),
                    author=child_text(entry, "author", "creator"),
                    published_at=published_at,
                    engagement_score=1.0,
                    metadata={"feed_url": feed_url},
                )
                if item.dedup_key not in items:
                    feed_item_count += 1
                items[item.dedup_key] = item
            logger.info("[rss] feed %s fetched %d items", feed_url, feed_item_count)
        return list(items.values())
