from __future__ import annotations

from datetime import datetime
import logging

from article_writer.config import Settings
from article_writer.models import SourceItem
from article_writer.sources.base import SourceAdapter, encoded_query, matches_keywords, parse_datetime, truncate_text


logger = logging.getLogger(__name__)


class GitHubSource(SourceAdapter):
    name = "github"

    def enabled(self, settings: Settings) -> bool:
        return settings.enable_github

    def fetch(self, since: datetime, settings: Settings) -> list[SourceItem]:
        items: dict[str, SourceItem] = {}
        since_date = since.date().isoformat()
        headers = {"Accept": "application/vnd.github+json"}
        if settings.github_token:
            headers["Authorization"] = f"Bearer {settings.github_token}"

        for stream, queries in settings.github_queries.items():
            for query in queries:
                search = encoded_query(f"{query} created:>{since_date}")
                url = f"https://api.github.com/search/repositories?q={search}&sort=stars&order=desc&per_page=10"
                try:
                    payload = self._get_json(url, settings, headers=headers)
                except Exception as exc:
                    logger.warning("[github] query failed %r: %s", query, exc)
                    continue
                for repo in payload.get("items", []):
                    title = repo.get("full_name") or repo.get("name") or ""
                    repo_url = repo.get("html_url")
                    if not title or not repo_url:
                        continue
                    description = repo.get("description") or ""
                    haystack = f"{title} {description}"
                    if not matches_keywords(haystack, settings.keywords):
                        continue
                    published_at = parse_datetime(repo.get("created_at"))
                    if published_at is None or published_at < since:
                        continue
                    stars = float(repo.get("stargazers_count") or 0)
                    forks = float(repo.get("forks_count") or 0)
                    item = SourceItem(
                        source_name=self.name,
                        external_id=str(repo.get("id") or title),
                        title=title,
                        url=repo_url,
                        summary=truncate_text(description or title),
                        author=(repo.get("owner") or {}).get("login"),
                        published_at=published_at,
                        engagement_score=stars + forks * 0.5,
                        metadata={"stars": stars, "forks": forks, "query": query, "stream": stream},
                        stream=stream,
                    )
                    items[item.dedup_key] = item
        return list(items.values())
