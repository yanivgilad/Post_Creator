import pytest
from article_writer.storage.sqlite_store import SQLiteStore
from tests.conftest import make_settings


def test_llm_rank_score_column_exists(tmp_path):
    settings = make_settings(tmp_path)
    store = SQLiteStore(settings)
    store.init_db()
    from sqlalchemy import inspect
    cols = {c["name"] for c in inspect(store._engine).get_columns("trends")}
    assert "llm_rank_score" in cols


def test_llm_rank_score_defaults_to_none(tmp_path):
    from article_writer.storage.sqlite_store import TrendRecord
    from datetime import datetime, timezone
    settings = make_settings(tmp_path)
    store = SQLiteStore(settings)
    store.init_db()
    run_id = store.create_run("test")
    with store.session() as session:
        row = TrendRecord(
            run_id=run_id,
            source_name="hn",
            external_id="x1",
            title="Test",
            url="https://example.com",
            summary="",
            published_at=datetime.now(timezone.utc),
            rank_score=1.0,
            reason_summary="",
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        assert row.llm_rank_score is None
