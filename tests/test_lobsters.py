from __future__ import annotations

from datetime import timedelta

from article_writer.models import utc_now
from article_writer.sources.lobsters import LobstersSource


def test_lobsters_fetch_accepts_string_submitter_user(settings, monkeypatch):
    source = LobstersSource()

    def fake_get_json(url, current_settings):
        if url.endswith("/ai.json"):
            return [
                "unexpected",
                {
                    "title": "AI observability tooling",
                    "url": "https://example.com/ai-observability",
                    "short_id": "abc123",
                    "description": "A new AI debugging workflow.",
                    "created_at": utc_now().isoformat(),
                    "score": 42,
                    "comment_count": 5,
                    "submitter_user": "jedisct1",
                },
            ]
        return []

    monkeypatch.setattr(source, "_get_json", fake_get_json)

    items = source.fetch(utc_now() - timedelta(days=1), settings)

    assert len(items) == 1
    assert items[0].author == "jedisct1"
    assert items[0].engagement_score == 45.0