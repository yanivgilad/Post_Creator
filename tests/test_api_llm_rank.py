import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch
from datetime import datetime, timezone


def test_llm_rank_endpoint_returns_ok(tmp_path):
    from tests.conftest import make_settings
    from article_writer.storage.sqlite_store import SQLiteStore, TrendRecord, PipelineRunRecord
    from article_writer.web.app import create_app

    settings = make_settings(tmp_path)
    store = SQLiteStore(settings)
    store.init_db()

    with store.session() as session:
        run = PipelineRunRecord(status="completed", triggered_by="test",
                                started_at=datetime.now(timezone.utc))
        session.add(run)
        session.commit()
        run_id = run.id
        row = TrendRecord(
            run_id=run_id, source_name="hn", external_id="e1",
            title="LLM news", url="https://example.com", summary="",
            published_at=datetime.now(timezone.utc),
            rank_score=1.0, reason_summary="",
        )
        session.add(row)
        session.commit()

    app = create_app(settings=settings, start_scheduler=False)

    with patch("article_writer.web.routes.api.llm_rank", return_value={0: 7.5}):
        with TestClient(app) as client:
            response = client.post(f"/api/runs/{run_id}/llm-rank")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["ranked_count"] == 1


def test_llm_rank_endpoint_404_on_unknown_run(tmp_path):
    from tests.conftest import make_settings
    from article_writer.web.app import create_app

    settings = make_settings(tmp_path)
    app = create_app(settings=settings, start_scheduler=False)
    with TestClient(app) as client:
        response = client.post("/api/runs/9999/llm-rank")
    assert response.status_code == 404
