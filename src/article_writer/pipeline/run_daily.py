from __future__ import annotations

from datetime import timedelta
import logging
from threading import Lock

logger = logging.getLogger(__name__)

from article_writer.config import Settings
from article_writer.models import PipelineSnapshot
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

    def run(self, triggered_by: str = "scheduler", *, on_run_created=None) -> int:
        if not self._lock.acquire(blocking=False):
            raise RuntimeError("A pipeline run is already in progress")

        run_id = self.store.create_run(triggered_by)
        if on_run_created is not None:
            on_run_created(run_id)
        errors: list[str] = []
        all_items = []

        logger.info("Run %d started (triggered_by=%s)", run_id, triggered_by)

        try:
            since = self._since_timestamp()
            keyword_tuples = self.store.list_keywords_for_matching()
            keyword_strings = [kw for kw, _ in keyword_tuples]
            for source in self.sources:
                try:
                    fetched = source.fetch(since, self.settings, keywords=keyword_strings)
                    all_items.extend(fetched)
                    logger.info("[%s] fetched %d items", source.name, len(fetched))
                except Exception as exc:
                    logger.warning("[%s] fetch failed: %s", source.name, exc)
                    errors.append(f"{source.name}: {exc}")

            unique_count = len({item.dedup_key for item in all_items})
            logger.info("Ranking %d items (%d unique)...", len(all_items), unique_count)
            ranked, all_scored = rank_items(all_items, self.settings, keyword_tuples)
            snapshot = PipelineSnapshot(
                ranked_trends=ranked,
                all_scored_items=all_scored,
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

    @staticmethod
    def _now():
        from article_writer.models import utc_now

        return utc_now()
