from __future__ import annotations

import html as html_lib
import re
from datetime import datetime, timezone

from article_writer.config import Settings
from article_writer.models import SourceItem
from article_writer.sources.base import (
    SourceAdapter,
    parse_datetime,
    truncate_text,
)

BLOG_BASE = "https://www.netlify.com"
BLOG_URL = "https://www.netlify.com/blog/"

# /blog/<slug> — one path segment only, no sub-paths like /blog/tags/ or /blog/authors/
_HREF_RE = re.compile(r'href="(/blog/[^/"]+)"', re.I)
_H_TEXT_RE = re.compile(r"<h[2-4][^>]*>(.*?)</h[2-4]>", re.DOTALL | re.I)
_DATE_TEXT_RE = re.compile(
    r"\b(January|February|March|April|May|June|July|August|September|October|November|December)"
    r"\s+(\d{1,2}),\s+(\d{4})\b"
)
_MONTH_MAP = {
    "January": 1, "February": 2, "March": 3, "April": 4,
    "May": 5, "June": 6, "July": 7, "August": 8,
    "September": 9, "October": 10, "November": 11, "December": 12,
}
_TAGS_RE = re.compile(r"<[^>]+>")

_SKIP_PATHS = {"/blog", "/blog/"}


def _strip(html: str) -> str:
    return html_lib.unescape(" ".join(_TAGS_RE.sub(" ", html).split()))


class NetlifyBlogSource(SourceAdapter):
    name = "netlify"

    def enabled(self, settings: Settings) -> bool:
        return settings.enable_netlify

    def fetch(self, since: datetime, settings: Settings) -> list[SourceItem]:
        try:
            html = self._get_text(BLOG_URL, settings, headers={"Accept": "text/html, */*"})
        except Exception:
            return []

        # Collect unique blog post URLs and their positions, preserving order
        seen: set[str] = set()
        url_positions: list[tuple[str, int]] = []
        for m in _HREF_RE.finditer(html):
            path = m.group(1).rstrip("/")
            if path in seen or path in _SKIP_PATHS:
                continue
            seen.add(path)
            url_positions.append((path, m.start()))

        items: dict[str, SourceItem] = {}

        for i, (path, start) in enumerate(url_positions):
            # Each card's HTML runs from this href to the next one (or end).
            # Include a small lookback so titles that appear just before the href
            # (heading-wraps-link pattern) are also captured.
            end = url_positions[i + 1][1] if i + 1 < len(url_positions) else len(html)
            chunk = html[max(0, start - 300) : end]

            h_match = _H_TEXT_RE.search(chunk)
            if not h_match:
                continue
            title = _strip(h_match.group(1))
            if not title:
                continue

            d_match = _DATE_TEXT_RE.search(chunk)
            if d_match:
                month = _MONTH_MAP[d_match.group(1)]
                date_str = f"{d_match.group(3)}-{month:02d}-{int(d_match.group(2)):02d}"
                published_at = parse_datetime(date_str)
            else:
                published_at = None
            if published_at is None:
                published_at = datetime.now(tz=timezone.utc)
            if published_at < since:
                continue

            url = BLOG_BASE + path
            item = SourceItem(
                source_name=self.name,
                external_id=url,
                title=title,
                url=url,
                summary=truncate_text(title),
                author=None,
                published_at=published_at,
                engagement_score=1.0,
                metadata={"scraped_from": BLOG_URL, "stream": settings.netlify_stream},
                stream=settings.netlify_stream,
            )
            items[item.dedup_key] = item

        return list(items.values())
