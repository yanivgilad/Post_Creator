from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from article_writer.config import Settings
    from article_writer.models import RankedTrend

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You are a relevance ranker. Given a list of AI/tech news article titles and a set of "
    "topic keywords, rate each article's relevance to those topics on a scale from 1 (irrelevant) "
    "to 10 (highly relevant). Return ONLY valid JSON — no explanation, no markdown."
)


def _build_prompt(trends: list[RankedTrend], keywords: list[str]) -> str:
    kw_line = ", ".join(keywords) if keywords else "AI, LLM, RAG"
    lines = [
        f"Topics of interest: {kw_line}",
        "",
        "Rate each article's relevance (1-10):",
    ]
    for i, trend in enumerate(trends, start=1):
        lines.append(f"{i}. {trend.source_item.title} [{trend.source_item.source_name}]")
    lines += [
        "",
        'Return only JSON: {"rankings": [{"index": 1, "score": 8.5}, ...]}',
    ]
    return "\n".join(lines)


def _make_azure_client(settings: Settings):
    from openai import AzureOpenAI
    return AzureOpenAI(
        api_key=settings.azure_openai_api_key,
        azure_endpoint=settings.azure_openai_endpoint,
        api_version=settings.azure_openai_api_version,
    )


def llm_rank(
    trends: list[RankedTrend],
    keywords: list[str],
    settings: Settings,
    llm_name: str = "azure/gpt-4o",
) -> dict[int, float]:
    """Return {0-based index: score 1-10} for each trend. Empty dict on failure."""
    if not trends:
        return {}

    if not (
        settings.azure_openai_api_key
        and settings.azure_openai_endpoint
        and settings.azure_openai_api_version
    ):
        logger.warning("llm_rank: Azure OpenAI not configured — skipping")
        return {}

    _, model_name = llm_name.split("/", 1)
    user_prompt = _build_prompt(trends, keywords)

    try:
        client = _make_azure_client(settings)
        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.0,
            max_tokens=512,
            response_format={"type": "json_object"},
        )
        raw = response.choices[0].message.content or ""
        data = json.loads(raw)
        rankings = data.get("rankings", [])
        return {int(entry["index"]) - 1: float(entry["score"]) for entry in rankings}
    except Exception as exc:
        logger.warning("llm_rank failed: %s", exc)
        return {}
