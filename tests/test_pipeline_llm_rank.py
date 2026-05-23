from unittest.mock import MagicMock, patch
from article_writer.pipeline.run_daily import DailyPipeline
from article_writer.models import RankedTrend, SourceItem
from datetime import datetime, timezone


def _make_source_item(title: str) -> SourceItem:
    return SourceItem(
        source_name="hn", external_id="x", title=title,
        url="https://example.com", summary="", author=None,
        published_at=datetime.now(timezone.utc),
    )


def test_pipeline_attaches_llm_rank_scores(tmp_path):
    from tests.conftest import make_settings
    from article_writer.storage.sqlite_store import SQLiteStore
    settings = make_settings(tmp_path)
    store = SQLiteStore(settings)
    store.init_db()

    fake_trend = RankedTrend(
        source_item=_make_source_item("RAG at scale"),
        score=5.0, reason_summary="", evidence=[], supporting_urls=[],
    )

    mock_source = MagicMock()
    mock_source.name = "mock"
    mock_source.fetch.return_value = []

    with patch("article_writer.pipeline.run_daily.rank_items", return_value=([fake_trend], [fake_trend])):
        with patch("article_writer.pipeline.run_daily.llm_rank", return_value={0: 8.5}) as mock_llm_rank:
            pipeline = DailyPipeline(settings, store, sources=[mock_source])
            run_id = pipeline.run("test")

    mock_llm_rank.assert_called_once()
    run = store.get_run(run_id)
    assert run is not None
    all_trends = run["all_scored_items"]
    assert len(all_trends) == 1
    assert all_trends[0]["llm_rank_score"] == 8.5
