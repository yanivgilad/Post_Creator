from __future__ import annotations

from datetime import timedelta
import logging
from threading import Lock

logger = logging.getLogger(__name__)

SOURCE_LOG_PREVIEW_LIMIT = 5
RANKED_LOG_PREVIEW_LIMIT = 10

from article_writer.config import Settings
from article_writer.models import PipelineSnapshot, normalize_url
from article_writer.ranking.scorer import rank_items
from article_writer.sources import build_enabled_sources
from article_writer.sources.base import SourceAdapter
from article_writer.storage.sqlite_store import SQLiteStore


class DailyPipeline:
    def __init__(
        self,
        settings: Settings,
        store: SQLiteStore,
        sources: list[SourceAdapter] | None = None,
    ) -> None:
        self.settings = settings
        self.store = store
        self.sources = list(sources) if sources is not None else build_enabled_sources(settings)
        self._lock = Lock()

    @property
    def is_running(self) -> bool:
        return self._lock.locked()

    def run(self, triggered_by: str = "scheduler") -> int:
        if not self._lock.acquire(blocking=False):
            raise RuntimeError("A pipeline run is already in progress")

        run_id = self.store.create_run(triggered_by)
        errors: list[str] = []
        all_items = []

        logger.info("Run %d started (triggered_by=%s)", run_id, triggered_by)

        try:
            since = self._since_timestamp()
            for source in self.sources:
                try:
                    fetched = source.fetch(since, self.settings)
                    all_items.extend(fetched)
                    logger.info("[%s] fetched %d items", source.name, len(fetched))
                    self._log_source_preview(source.name, fetched)
                except Exception as exc:
                    logger.warning("[%s] fetch failed: %s", source.name, exc)
                    errors.append(f"{source.name}: {exc}")

            recent_urls = {normalize_url(url) for url in self.store.recent_urls(self.settings.dedup_days)}
            unique_count = len({item.dedup_key for item in all_items})
            logger.info("Ranking %d items (%d unique)...", len(all_items), unique_count)
            ranked = rank_items(all_items, self.settings, recent_urls)
            self._log_ranked_preview(ranked)
            snapshot = PipelineSnapshot(
                ranked_trends=ranked,
                drafts=[],
                raw_item_count=len(all_items),
                unique_item_count=unique_count,
                errors=errors,
            )
            self.store.complete_run(run_id, snapshot, source_count=len(self.sources))
            logger.info("Run %d completed: %d trends, %d source errors", run_id, len(ranked), len(errors))
            return run_id
        except Exception as exc:
            errors.append(f"pipeline: {exc}")
            logger.exception("Run %d failed: %s", run_id, exc)
            self.store.fail_run(run_id, errors)
            raise
        finally:
            self._lock.release()

    def _since_timestamp(self):
        return self._now() - timedelta(hours=self.settings.since_hours)

    def _log_source_preview(self, source_name: str, items) -> None:
        if not items:
            logger.info("[%s] no items matched the configured filters", source_name)
            return

        preview_items = sorted(
            items,
            key=lambda item: (item.engagement_score, item.published_at),
            reverse=True,
        )[:SOURCE_LOG_PREVIEW_LIMIT]
        for index, item in enumerate(preview_items, start=1):
            logger.info(
                "[%s] preview %02d: %s | engagement %.1f | %s | %s",
                source_name,
                index,
                self._preview_text(item.title),
                item.engagement_score,
                item.published_at.isoformat(),
                item.url,
            )

    def _log_ranked_preview(self, ranked) -> None:
        if not ranked:
            logger.info("[ranking] no fresh items survived dedup and ranking")
            return

        for index, trend in enumerate(ranked[:RANKED_LOG_PREVIEW_LIMIT], start=1):
            logger.info(
                "[ranking] top %02d: [%s] score %.2f | %s | %s",
                index,
                trend.source_item.source_name,
                trend.score,
                self._preview_text(trend.source_item.title),
                trend.source_item.url,
            )

    @staticmethod
    def _preview_text(value: str, limit: int = 140) -> str:
        compact = " ".join(value.split())
        if len(compact) <= limit:
            return compact
        return f"{compact[: limit - 3].rstrip()}..."

    @staticmethod
    def _now():
        from article_writer.models import utc_now

        return utc_now()
