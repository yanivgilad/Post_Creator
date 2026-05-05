from __future__ import annotations

from dataclasses import replace
from datetime import datetime

from fastapi.testclient import TestClient

from article_writer.pipeline.run_daily import DailyPipeline
from article_writer.sources.base import SourceAdapter
from article_writer.web.app import create_app


class FakeSource(SourceAdapter):
    name = "fake"

    def enabled(self, settings):
        return True

    def fetch(self, since: datetime, settings):
        from article_writer.models import SourceItem, utc_now

        return [
            SourceItem(
                source_name="fake",
                external_id="run-1",
                title="Fresh AI coding workflow lands",
                url="https://example.com/coding-workflow",
                summary="A new workflow for building AI coding agents.",
                author="maintainer",
                published_at=utc_now(),
                engagement_score=66.0,
            )
        ]


def test_web_routes_render_and_api_returns_latest_run(settings):
    app = create_app(replace(settings, gemini_api_key="secret-key"), start_scheduler=False)

    with TestClient(app) as client:
        health = client.get("/health")
        pipeline: DailyPipeline = client.app.state.pipeline
        pipeline.sources = [FakeSource()]
        run_id = pipeline.run("test-web")
        latest_payload = client.app.state.store.get_run(run_id)
        trend_id = latest_payload["trends"][0]["id"]

        dashboard = client.get("/")
        latest = client.get("/api/runs/latest")
        config = client.get("/api/config")
        trends_page = client.get(f"/trends?run_id={run_id}")
        article_form = client.get(f"/articles/new?trend_id={trend_id}")
        article_create = client.post(
            "/articles",
            data={
                "trend_id": str(trend_id),
                "language": "English",
                "target_outlet": "LinkedIn",
                "llm_name": "local-template",
            },
            follow_redirects=False,
        )
        invalid_article_create = client.post(
            "/articles",
            data={
                "trend_id": str(trend_id),
                "language": "German",
                "target_outlet": "Newsletter",
                "llm_name": "local-template",
            },
            follow_redirects=False,
        )
        trigger = client.post("/api/runs/trigger")

        assert health.status_code == 200
        assert health.json() == {"status": "ok"}
        assert dashboard.status_code == 200
        assert "AI Trends Dashboard" in dashboard.text
        assert latest.status_code == 200
        assert latest.json()["id"] == run_id
        assert config.status_code == 200
        assert config.json()["gemini_api_key"] is None
        assert trends_page.status_code == 200
        assert "Fresh AI coding workflow lands" in trends_page.text
        assert "Create Article" in trends_page.text
        assert article_form.status_code == 200
        assert '<select name="language"' in article_form.text
        assert "Hebrew" in article_form.text
        assert '<select name="target_outlet"' in article_form.text
        assert "Hashnode/Dev.to" in article_form.text
        assert "google/gemini-2.5-pro" in article_form.text
        assert article_create.status_code == 303
        article_detail = client.get(article_create.headers["location"])
        assert article_detail.status_code == 200
        assert "LinkedIn" in article_detail.text
        assert "local-template" in article_detail.text
        assert invalid_article_create.status_code == 400
        assert "Choose English or Hebrew." in invalid_article_create.text
        assert trigger.status_code == 200
        assert trigger.json()["status"] == "scheduled"


def test_article_form_filters_unsupported_llm_targets(settings):
    app = create_app(
        replace(
            settings,
            article_llm_options=[
                "local-template",
                "openai/gpt-4.1-mini",
                "anthropic/claude-sonnet-4",
                "google/gemini-2.5-pro",
            ],
        ),
        start_scheduler=False,
    )

    with TestClient(app) as client:
        pipeline: DailyPipeline = client.app.state.pipeline
        pipeline.sources = [FakeSource()]
        run_id = pipeline.run("test-web")
        latest_payload = client.app.state.store.get_run(run_id)
        trend_id = latest_payload["trends"][0]["id"]

        article_form = client.get(f"/articles/new?trend_id={trend_id}")
        invalid_article_create = client.post(
            "/articles",
            data={
                "trend_id": str(trend_id),
                "language": "English",
                "target_outlet": "LinkedIn",
                "llm_name": "openai/gpt-4.1-mini",
            },
            follow_redirects=False,
        )

        assert article_form.status_code == 200
        assert "local-template" in article_form.text
        assert "google/gemini-2.5-pro" in article_form.text
        assert "openai/gpt-4.1-mini" not in article_form.text
        assert "anthropic/claude-sonnet-4" not in article_form.text
        assert invalid_article_create.status_code == 400
        assert "Choose a supported LLM target." in invalid_article_create.text
