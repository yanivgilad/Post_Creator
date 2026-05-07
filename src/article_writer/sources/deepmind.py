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


class DeepMindSource(SourceAdapter):
    name = "deepmind"

    def enabled(self, settings: Settings) -> bool:
        return settings.enable_deepmind

    def fetch(self, since: datetime, settings: Settings) -> list[SourceItem]:
        items: dict[str, SourceItem] = {}
        for feed_url in settings.deepmind_feeds:
            try:
                xml_text = self._get_text(
                    feed_url,
                    settings,
                    headers={"Accept": "application/rss+xml, application/xml, */*"},
                )
                entries = list(iter_xml_entries(xml_text))
            except Exception as exc:
                logger.warning("[deepmind] feed failed %s: %s", feed_url, exc)
                continue

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
                summary = strip_html(child_text(entry, "summary", "description", "content") or "")
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
                items[item.dedup_key] = item
        return list(items.values())
