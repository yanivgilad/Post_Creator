from __future__ import annotations

from datetime import datetime
import logging

from article_writer.config import Settings
from article_writer.models import SourceItem
from article_writer.sources.base import SourceAdapter, matches_keywords, parse_datetime, strip_html, truncate_text


logger = logging.getLogger(__name__)


class RedditSource(SourceAdapter):
    name = "reddit"

    def enabled(self, settings: Settings) -> bool:
        return settings.enable_reddit

    def fetch(self, since: datetime, settings: Settings) -> list[SourceItem]:
        items: dict[str, SourceItem] = {}
        for subreddit in settings.reddit_subreddits:
            url = f"https://www.reddit.com/r/{subreddit}/new.json?limit=25"
            try:
                payload = self._get_json(url, settings)
            except Exception as exc:
                logger.warning("[reddit] subreddit failed r/%s: %s", subreddit, exc)
                continue
            children = payload.get("data", {}).get("children", [])
            for child in children:
                data = child.get("data", {})
                title = data.get("title") or ""
                permalink = data.get("permalink")
                if not title or not permalink:
                    continue
                published_at = parse_datetime(data.get("created_utc"))
                if published_at is None or published_at < since:
                    continue
                selftext = strip_html(data.get("selftext") or "")
                haystack = f"{title} {selftext}"
                if not matches_keywords(haystack, settings.keywords):
                    continue
                item = SourceItem(
                    source_name=self.name,
                    external_id=data.get("name") or data.get("id") or permalink,
                    title=title,
                    url=f"https://www.reddit.com{permalink}",
                    summary=truncate_text(selftext or title),
                    author=data.get("author"),
                    published_at=published_at,
                    engagement_score=float(data.get("ups") or 0) + float(data.get("num_comments") or 0) * 0.4,
                    metadata={
                        "subreddit": subreddit,
                        "ups": data.get("ups") or 0,
                        "comments": data.get("num_comments") or 0,
                    },
                )
                items[item.dedup_key] = item
        return list(items.values())
