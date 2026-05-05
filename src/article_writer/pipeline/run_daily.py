from __future__ import annotations

from datetime import timedelta
from threading import Lock

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

        try:
            since = self._since_timestamp()
            for source in self.sources:
                try:
                    all_items.extend(source.fetch(since, self.settings))
                except Exception as exc:
                    errors.append(f"{source.name}: {exc}")

            recent_urls = {normalize_url(url) for url in self.store.recent_urls(self.settings.dedup_days)}
            ranked = rank_items(all_items, self.settings, recent_urls)
            unique_count = len({item.dedup_key for item in all_items})
            snapshot = PipelineSnapshot(
                ranked_trends=ranked,
                drafts=[],
                raw_item_count=len(all_items),
                unique_item_count=unique_count,
                errors=errors,
            )
            self.store.complete_run(run_id, snapshot, source_count=len(self.sources))
            return run_id
        except Exception as exc:
            errors.append(f"pipeline: {exc}")
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
