from __future__ import annotations

import json
from dataclasses import replace

from article_writer.generation.article_generator import ManualArticleGenerator


TREND = {
    "id": 1,
    "run_id": 7,
    "external_id": "abc123",
    "title": "Gemini adds direct article generation",
    "source_name": "fake",
    "url": "https://example.com/gemini-direct",
    "summary": "A direct Gemini integration for article generation.",
    "reason_summary": "It removes the proxy dependency for Gemini.",
    "author": "Amit",
    "published_at": "2026-05-05T10:30:00+00:00",
    "engagement_score": 42.5,
    "rank_score": 9.3,
    "evidence": ["Direct provider routing is now supported."],
    "supporting_urls": ["https://example.com/context"],
    "metadata": {"source": "test"},
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
    assert "ghostwriter" in payload["system_instruction"]["parts"][0]["text"]
    assert "Amit Raz" in payload["system_instruction"]["parts"][0]["text"]
    user_text = payload["contents"][0]["parts"][0]["text"]
    user_data = json.loads(user_text)
    assert user_data["title"] == TREND["title"]
    assert user_data["output_language"] == "English"
    assert user_data["goal"] == "thought_leadership"


def test_build_prompt_lists_available_information():
    generator = ManualArticleGenerator()

    prompt = generator._build_prompt(TREND, language="Hebrew", target_outlet="Hashnode/Dev.to")

    assert "Provided information:" in prompt
    assert "- Trend id: 1" in prompt
    assert "- Run id: 7" in prompt
    assert "- External id: abc123" in prompt
    assert "- Author: Amit" in prompt
    assert "- Published at: 2026-05-05T10:30:00+00:00" in prompt
    assert "- Engagement score: 42.5" in prompt
    assert "- Rank score: 9.3" in prompt
    assert "- Requested language: Hebrew" in prompt
    assert "- Requested target outlet: Hashnode/Dev.to" in prompt
    assert "- Source metadata: {\"source\": \"test\"}" in prompt


def test_build_prompt_reddit_uses_social_payload():
    generator = ManualArticleGenerator()

    prompt = generator._build_prompt(TREND, language="English", target_outlet="Reddit")
    data = json.loads(prompt)

    assert data["title"] == TREND["title"]
    assert data["source_name"] == TREND["source_name"]
    assert data["original_url"] == TREND["url"]
    assert data["summary"] == TREND["summary"]
    assert data["output_language"] == "English"


def test_build_system_prompt_varies_by_platform(settings):
    generator = ManualArticleGenerator()

    twitter_prompt = generator._build_system_prompt("Twitter/X", settings)
    linkedin_prompt = generator._build_system_prompt("LinkedIn", settings)

    assert "ghostwriter" in twitter_prompt
    assert "Amit Raz" in twitter_prompt
    assert "Target outlet: Twitter/X." not in twitter_prompt

    assert "ghostwriter" in linkedin_prompt
    assert "Amit Raz" in linkedin_prompt
    assert "Target outlet: LinkedIn." not in linkedin_prompt