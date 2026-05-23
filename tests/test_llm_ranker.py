import json
import pytest
from unittest.mock import MagicMock, patch
from article_writer.ranking.llm_ranker import llm_rank, _build_prompt
from article_writer.models import RankedTrend, SourceItem
from datetime import datetime, timezone


def _make_trend(title: str, source: str = "hn") -> RankedTrend:
    item = SourceItem(
        source_name=source,
        external_id="x",
        title=title,
        url="https://example.com",
        summary="",
        author=None,
        published_at=datetime.now(timezone.utc),
    )
    return RankedTrend(source_item=item, score=1.0, reason_summary="", evidence=[], supporting_urls=[])


def test_build_prompt_includes_titles():
    trends = [_make_trend("RAG is dead"), _make_trend("GPT-5 launches")]
    keywords = ["RAG", "LLM", "agents"]
    prompt = _build_prompt(trends, keywords)
    assert "RAG is dead" in prompt
    assert "GPT-5 launches" in prompt
    assert "RAG, LLM, agents" in prompt


def test_build_prompt_numbered():
    trends = [_make_trend("A"), _make_trend("B"), _make_trend("C")]
    prompt = _build_prompt(trends, ["llm"])
    assert "1." in prompt
    assert "2." in prompt
    assert "3." in prompt


def test_llm_rank_returns_scores_for_all_items():
    from tests.conftest import make_settings
    import tempfile, pathlib, dataclasses
    trends = [_make_trend("RAG at scale"), _make_trend("Python update")]
    keywords = ["RAG", "LLM"]
    fake_response_json = json.dumps({
        "rankings": [{"index": 1, "score": 9.0}, {"index": 2, "score": 2.5}]
    })
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content=fake_response_json))],
        usage=MagicMock(prompt_tokens=100, completion_tokens=50),
    )
    with patch("article_writer.ranking.llm_ranker._make_azure_client", return_value=mock_client):
        with tempfile.TemporaryDirectory() as tmp:
            settings = make_settings(pathlib.Path(tmp))
            settings = dataclasses.replace(
                settings,
                azure_openai_api_key="key",
                azure_openai_endpoint="https://x.openai.azure.com",
                azure_openai_api_version="2024-02-01",
            )
            result = llm_rank(trends, keywords, settings, llm_name="azure/gpt-4o")
    assert result[0] == pytest.approx(9.0)
    assert result[1] == pytest.approx(2.5)


def test_llm_rank_returns_empty_on_error():
    from tests.conftest import make_settings
    import tempfile, pathlib
    trends = [_make_trend("Something")]
    keywords = ["LLM"]
    with patch("article_writer.ranking.llm_ranker._make_azure_client", side_effect=Exception("timeout")):
        with tempfile.TemporaryDirectory() as tmp:
            settings = make_settings(pathlib.Path(tmp))
            result = llm_rank(trends, keywords, settings, llm_name="azure/gpt-4o")
    assert result == {}


def test_llm_rank_empty_trends():
    from tests.conftest import make_settings
    import tempfile, pathlib
    with tempfile.TemporaryDirectory() as tmp:
        settings = make_settings(pathlib.Path(tmp))
        result = llm_rank([], ["LLM"], settings, llm_name="azure/gpt-4o")
    assert result == {}
