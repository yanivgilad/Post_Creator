from __future__ import annotations

from datetime import datetime

from article_writer.config import Settings
from article_writer.models import SourceItem
from article_writer.sources.base import SourceAdapter, matches_keywords, parse_datetime, truncate_text


class ProductHuntSource(SourceAdapter):
    name = "product_hunt"

    def enabled(self, settings: Settings) -> bool:
        return settings.enable_product_hunt and bool(settings.product_hunt_token)

    def fetch(self, since: datetime, settings: Settings) -> list[SourceItem]:
        if not settings.product_hunt_token:
            return []

        query = {
            "query": "query Posts($postedAfter: DateTime!) { posts(first: 10, postedAfter: $postedAfter) { edges { node { id name tagline url createdAt votesCount website } } } }",
            "variables": {"postedAfter": since.isoformat()},
        }
        headers = {
            "Authorization": f"Bearer {settings.product_hunt_token}",
            "Accept": "application/json",
        }
        payload = self._post_json("https://api.producthunt.com/v2/api/graphql", query, settings, headers=headers)
        edges = payload.get("data", {}).get("posts", {}).get("edges", [])
        items: dict[str, SourceItem] = {}
        for edge in edges:
            node = edge.get("node", {})
            title = node.get("name") or ""
            tagline = node.get("tagline") or ""
            url = node.get("url") or node.get("website")
            if not title or not url:
                continue
            if not matches_keywords(f"{title} {tagline}", settings.keywords):
                continue
            published_at = parse_datetime(node.get("createdAt"))
            if published_at is None or published_at < since:
                continue
            item = SourceItem(
                source_name=self.name,
                external_id=str(node.get("id") or url),
                title=title,
                url=url,
                summary=truncate_text(tagline or title),
                author=None,
                published_at=published_at,
                engagement_score=float(node.get("votesCount") or 0),
                metadata={"votes": node.get("votesCount") or 0, "stream": settings.product_hunt_stream},
                stream=settings.product_hunt_stream,
            )
            items[item.dedup_key] = item
        return list(items.values())
