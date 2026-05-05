from __future__ import annotations

import json
from dataclasses import replace

from article_writer.generation.article_generator import ManualArticleGenerator


TREND = {
    "id": 1,
    "title": "Gemini adds direct article generation",
    "source_name": "fake",
    "url": "https://example.com/gemini-direct",
    "summary": "A direct Gemini integration for article generation.",
    "reason_summary": "It removes the proxy dependency for Gemini.",
    "evidence": ["Direct provider routing is now supported."],
}


class FakeResponse:
    def __init__(self, payload: dict):
        self.payload = payload

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_generator_falls_back_without_gemini_key(settings):
    generator = ManualArticleGenerator()

    article = generator.generate(
        TREND,
        language="English",
        target_outlet="LinkedIn",
        llm_name="google/gemini-2.5-pro",
        settings=settings,
    )

    assert article.llm_name == "google/gemini-2.5-pro"
    assert article.metadata["mode"] == "local-template"
    assert "Gemini API key" in article.metadata["fallback_reason"]


def test_generator_calls_gemini_directly(settings, monkeypatch):
    captured: dict[str, str | bytes] = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["data"] = request.data
        captured["timeout"] = str(timeout)
        return FakeResponse(
            {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {"text": "# Generated Gemini title\n\nGenerated Gemini body."},
                            ]
                        }
                    }
                ]
            }
        )

    monkeypatch.setattr("article_writer.generation.article_generator.urlopen", fake_urlopen)
    generator = ManualArticleGenerator()

    article = generator.generate(
        TREND,
        language="English",
        target_outlet="LinkedIn",
        llm_name="google/gemini-2.5-pro",
        settings=replace(settings, gemini_api_key="gemini-test-key"),
    )

    assert article.metadata["mode"] == "gemini"
    assert article.title == "Generated Gemini title"
    assert article.body.startswith("# Generated Gemini title")
    assert captured["url"] == (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        "gemini-2.5-pro:generateContent?key=gemini-test-key"
    )
    payload = json.loads(captured["data"])
    assert payload["contents"][0]["parts"][0]["text"].startswith("Write a complete article in English.")