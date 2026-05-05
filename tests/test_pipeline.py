from __future__ import annotations

from datetime import datetime
import logging

from article_writer.pipeline.run_daily import DailyPipeline
from article_writer.sources.base import SourceAdapter
from article_writer.storage.sqlite_store import SQLiteStore


class FakeSource(SourceAdapter):
    name = "fake"

    def enabled(self, settings):
        return True

    def fetch(self, since: datetime, settings):
        from article_writer.models import SourceItem, utc_now

        return [
            SourceItem(
                source_name="fake",
                external_id="abc",
                title="Launch of a new AI model toolkit",
                url="https://example.com/model-toolkit",
                summary="Toolkit for testing and evaluating new AI models.",
                author="builder",
                published_at=utc_now(),
                engagement_score=88.0,
            )
        ]


def test_pipeline_persists_ranked_trends_without_auto_articles(settings):
    store = SQLiteStore(settings)
    store.init_db()
    pipeline = DailyPipeline(settings, store, sources=[FakeSource()])

    run_id = pipeline.run("test")
    payload = store.get_run(run_id)

    assert payload is not None
    assert payload["status"] == "completed"
    assert payload["raw_item_count"] == 1
    assert len(payload["trends"]) == 1
    assert payload["trends"][0]["title"] == "Launch of a new AI model toolkit"
    assert payload["drafts"] == []
    assert payload["articles"] == []


def test_pipeline_logs_source_previews_and_ranked_top_items(settings, caplog):
    store = SQLiteStore(settings)
    store.init_db()
    pipeline = DailyPipeline(settings, store, sources=[FakeSource()])

    with caplog.at_level(logging.INFO):
        pipeline.run("test")

    assert "[fake] preview 01: Launch of a new AI model toolkit" in caplog.text
    assert "[ranking] top 01: [fake]" in caplog.text
