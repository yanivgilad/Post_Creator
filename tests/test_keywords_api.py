from __future__ import annotations

import json
from dataclasses import replace

from fastapi.testclient import TestClient

from article_writer.web.app import create_app


def _client(settings):
    return TestClient(create_app(replace(settings, keywords=[]), start_scheduler=False))


def test_list_keywords_empty(settings):
    with _client(settings) as client:
        resp = client.get("/api/keywords")
        assert resp.status_code == 200
        assert resp.json() == []


def test_create_list_update_delete_flow(settings):
    with _client(settings) as client:
        created = client.post("/api/keywords", json={"keyword": "rag at scale", "tier": "HIGH"})
        assert created.status_code == 200
        body = created.json()
        assert body["keyword"] == "rag at scale"
        assert body["tier"] == "HIGH"
        assert body["weight"] == 1.0

        listing = client.get("/api/keywords")
        assert [r["keyword"] for r in listing.json()] == ["rag at scale"]

        kid = body["id"]
        updated = client.patch(f"/api/keywords/{kid}", json={"tier": "LOW"})
        assert updated.status_code == 200
        assert updated.json()["tier"] == "LOW"

        deleted = client.delete(f"/api/keywords/{kid}")
        assert deleted.status_code == 200
        assert deleted.json() == {"status": "deleted", "id": kid}

        assert client.get("/api/keywords").json() == []


def test_create_duplicate_returns_409(settings):
    with _client(settings) as client:
        client.post("/api/keywords", json={"keyword": "alpha", "tier": "MEDIUM"})
        dup = client.post("/api/keywords", json={"keyword": "ALPHA", "tier": "HIGH"})
        assert dup.status_code == 409


def test_create_invalid_tier_returns_400(settings):
    with _client(settings) as client:
        bad = client.post("/api/keywords", json={"keyword": "beta", "tier": "URGENT"})
        assert bad.status_code == 400


def test_update_and_delete_missing_returns_404(settings):
    with _client(settings) as client:
        miss = client.patch("/api/keywords/9999", json={"tier": "HIGH"})
        assert miss.status_code == 404
        miss_del = client.delete("/api/keywords/9999")
        assert miss_del.status_code == 404


def test_suggestions_endpoint_returns_filtered_suggestions(settings, monkeypatch):
    app_settings = replace(
        settings,
        article_llm_options=["azure/gpt-4o"],
        azure_openai_api_key="dummy",
        azure_openai_endpoint="https://example",
        azure_openai_api_version="2024-02-15",
    )

    canned = {
        "suggestions": [
            {"keyword": "long context kills rag", "suggested_tier": "HIGH", "reasoning": "Hot debate."},
            {"keyword": "alpha", "suggested_tier": "MEDIUM", "reasoning": "duplicate"},
            {"keyword": "agent eval harness", "suggested_tier": "MEDIUM", "reasoning": "Eval focus."},
            {"keyword": "irrelevant", "suggested_tier": "URGENT", "reasoning": "bad tier"},
        ]
    }

    def fake_chat(self, system_prompt, user_prompt, *, llm_name, settings, temperature, max_tokens):
        return json.dumps(canned), {"prompt_tokens": 10, "completion_tokens": 20}

    monkeypatch.setattr(
        "article_writer.generation.article_generator.ManualArticleGenerator._chat",
        fake_chat,
    )

    with _client(app_settings) as client:
        client.post("/api/keywords", json={"keyword": "alpha", "tier": "LOW"})
        resp = client.post("/api/keywords/suggestions", json={"count": 5})
        assert resp.status_code == 200
        payload = resp.json()
        keywords = [s["keyword"] for s in payload["suggestions"]]
        assert "alpha" not in keywords
        assert "irrelevant" not in keywords
        assert keywords == ["long context kills rag", "agent eval harness"]
        assert payload["suggestions"][0]["suggested_tier"] == "HIGH"


def test_suggestions_endpoint_rejects_unsupported_llm(settings):
    with _client(settings) as client:
        resp = client.post(
            "/api/keywords/suggestions",
            json={"count": 5, "llm_name": "openai/banana"},
        )
        assert resp.status_code == 400
