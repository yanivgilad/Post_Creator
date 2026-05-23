from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime

from fastapi.testclient import TestClient

from article_writer.pipeline.run_daily import DailyPipeline
from article_writer.sources.base import SourceAdapter
from article_writer.web.app import create_app


class _FakeGeminiResponse:
    def __init__(self, text: str = "# Test article title\n\nTest article body."):
        self._payload = {
            "candidates": [
                {"content": {"parts": [{"text": text}]}}
            ]
        }

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeSource(SourceAdapter):
    name = "fake"

    def enabled(self, settings):
        return True

    def fetch(self, since: datetime, settings, *, keywords=None):
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
                stream="software",
            )
        ]


class _MultiStreamFakeSource(SourceAdapter):
    name = "fake_multi"

    def enabled(self, settings):
        return True

    def fetch(self, since: datetime, settings, *, keywords=None):
        from article_writer.models import SourceItem, utc_now

        now = utc_now()
        return [
            SourceItem(
                source_name="fake_multi",
                external_id="sw-1",
                title="AI agent breakthrough",
                url="https://example.com/ai-agent",
                summary="A new AI agent benchmark.",
                author="alice",
                published_at=now,
                engagement_score=10.0,
                stream="software",
            ),
            SourceItem(
                source_name="fake_multi",
                external_id="gm-1",
                title="Xbox handheld leaks",
                url="https://example.com/xbox-handheld",
                summary="A new Xbox handheld is rumored.",
                author="bob",
                published_at=now,
                engagement_score=20.0,
                stream="gaming",
            ),
            SourceItem(
                source_name="fake_multi",
                external_id="hw-1",
                title="NVIDIA Blackwell shipping",
                url="https://example.com/blackwell",
                summary="NVIDIA Blackwell GPUs ship in volume.",
                author="carol",
                published_at=now,
                engagement_score=30.0,
                stream="hardware",
            ),
        ]


def test_run_detail_filters_by_stream(settings):
    app = create_app(settings, start_scheduler=False)

    with TestClient(app) as client:
        pipeline: DailyPipeline = client.app.state.pipeline
        pipeline.sources = [_MultiStreamFakeSource()]
        run_id = pipeline.run("test-streams")

        all_view = client.get(f"/runs/{run_id}")
        gaming_view = client.get(f"/runs/{run_id}?stream=gaming")
        hardware_view = client.get(f"/runs/{run_id}?stream=hardware")

        assert all_view.status_code == 200
        assert "Xbox handheld leaks" in all_view.text
        assert "NVIDIA Blackwell shipping" in all_view.text
        assert "AI agent breakthrough" in all_view.text
        assert 'class="stream-tabs"' in all_view.text

        assert gaming_view.status_code == 200
        assert "Xbox handheld leaks" in gaming_view.text
        assert "NVIDIA Blackwell shipping" not in gaming_view.text
        assert "AI agent breakthrough" not in gaming_view.text

        assert hardware_view.status_code == 200
        assert "NVIDIA Blackwell shipping" in hardware_view.text
        assert "Xbox handheld leaks" not in hardware_view.text


def test_trends_legacy_route_redirects_to_run(settings):
    app = create_app(settings, start_scheduler=False)

    with TestClient(app) as client:
        pipeline: DailyPipeline = client.app.state.pipeline
        pipeline.sources = [_MultiStreamFakeSource()]
        run_id = pipeline.run("test-streams")

        redirect = client.get(f"/trends?run_id={run_id}&stream=hardware", follow_redirects=False)

        assert redirect.status_code == 307
        assert redirect.headers["location"] == f"/runs/{run_id}?stream=hardware"


def test_web_routes_render_and_api_returns_latest_run(settings, monkeypatch):
    monkeypatch.setattr(
        "article_writer.generation.article_generator.urlopen",
        lambda request, timeout: _FakeGeminiResponse(),
    )
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
        trends_page = client.get(f"/runs/{run_id}")
        article_form = client.get(f"/articles/new?trend_id={trend_id}")
        article_create = client.post(
            "/articles",
            data={
                "trend_id": str(trend_id),
                "language": "English",
                "target_outlet": "LinkedIn",
                "llm_name": "google/gemini-2.5-pro",
                "custom_prompt": "Focus on practical engineering impact and rollout risks.",
            },
            follow_redirects=False,
        )
        api_article_create = client.post(
            "/api/articles",
            json={
                "trend_id": trend_id,
                "language": "English",
                "target_outlet": "Reddit",
                "llm_name": "google/gemini-2.5-pro",
                "custom_prompt": "Focus on the evidence and likely benchmarks people will ask about.",
            },
        )
        invalid_article_create = client.post(
            "/articles",
            data={
                "trend_id": str(trend_id),
                "language": "German",
                "target_outlet": "Newsletter",
                "llm_name": "google/gemini-2.5-pro",
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
        assert '<textarea name="custom_prompt"' in article_form.text
        assert article_create.status_code == 303
        article_detail = client.get(article_create.headers["location"])
        assert article_detail.status_code == 200
        assert "LinkedIn" in article_detail.text
        assert "google/gemini-2.5-pro" in article_detail.text
        assert "Focus on practical engineering impact and rollout risks." in article_detail.text
        assert api_article_create.status_code == 200
        assert api_article_create.json()["metadata"]["custom_prompt"] == (
            "Focus on the evidence and likely benchmarks people will ask about."
        )
        assert invalid_article_create.status_code == 400
        assert "Choose English or Hebrew." in invalid_article_create.text
        assert trigger.status_code == 200
        assert trigger.json()["status"] == "scheduled"


def test_article_form_filters_unsupported_llm_targets(settings):
    app = create_app(
        replace(
            settings,
            article_llm_options=[
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
        assert "google/gemini-2.5-pro" in article_form.text
        assert "openai/gpt-4.1-mini" not in article_form.text
        assert "anthropic/claude-sonnet-4" not in article_form.text
        assert invalid_article_create.status_code == 400
        assert "Choose a supported LLM target." in invalid_article_create.text
