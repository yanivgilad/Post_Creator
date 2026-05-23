from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from article_writer.config import Settings
from article_writer.generation.article_generator import ManualArticleGenerator
from article_writer.storage.sqlite_store import VALID_TIERS


_FENCE_RE = re.compile(r"^```(?:json)?\s*\n?|\n?```$", re.IGNORECASE | re.MULTILINE)
_PERSONA_EXCERPT_CHARS = 1500


class KeywordSuggester:
    def __init__(self, generator: ManualArticleGenerator) -> None:
        self._generator = generator

    def suggest(
        self,
        *,
        existing: list[dict[str, Any]],
        recent_trends: list[dict[str, Any]],
        count: int,
        llm_name: str,
        settings: Settings,
    ) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
        existing_set = {str(e.get("keyword", "")).strip().lower() for e in existing if e.get("keyword")}
        persona = self._load_persona_excerpt(settings)
        existing_block = self._format_existing(existing)
        trends_block = self._format_trends(recent_trends)

        system_prompt = (
            "You are a senior AI/tech editor helping a CTO curate a keyword list "
            "used to score article relevance from RSS / Reddit / HackerNews / arXiv / GitHub feeds. "
            "You suggest substring-friendly phrases focused on LLMs, RAG, agents, model evals, "
            "and adjacent enterprise AI topics that match the persona below. "
            "Return ONLY valid JSON in the exact shape "
            '{"suggestions":[{"keyword":"...","suggested_tier":"LOW|MEDIUM|HIGH","reasoning":"one sentence"}]}. '
            "No markdown, no commentary outside the JSON object."
        )
        user_prompt = (
            f"Persona context (excerpt):\n{persona}\n\n"
            f"Existing keywords (with tier):\n{existing_block or '(none)'}\n\n"
            f"Recent top trends from the latest run:\n{trends_block or '(no recent trends)'}\n\n"
            f"Suggest {count} new keywords that are NOT already in the existing list. "
            f"Each must include a `suggested_tier` (LOW / MEDIUM / HIGH) reflecting how strongly it "
            f"signals an article worth reading for this persona. "
            f"Prefer substring-friendly phrases (lowercase, 1-5 words) that survive partial matches. "
            f"Return JSON only."
        )

        raw, usage = self._generator._chat(
            system_prompt,
            user_prompt,
            llm_name=llm_name,
            settings=settings,
            temperature=0.5,
            max_tokens=900,
        )
        parsed = self._parse_response(raw)
        suggestions = self._validate_suggestions(parsed, existing_set)
        return suggestions, usage

    @staticmethod
    def _load_persona_excerpt(settings: Settings) -> str:
        candidates: list[Path] = []
        if settings.linkedin_prompt_file:
            candidates.append(Path(settings.linkedin_prompt_file))
        candidates.append(Path.cwd() / "prompts" / "linkedin_system_prompt.txt")
        for path in candidates:
            if path and path.is_file():
                text = path.read_text(encoding="utf-8").strip()
                return text[:_PERSONA_EXCERPT_CHARS]
        return "Senior AI/tech leader focused on LLMs, RAG at scale, autonomous agents, and enterprise AI architecture."

    @staticmethod
    def _format_existing(existing: list[dict[str, Any]]) -> str:
        lines = []
        for entry in existing:
            kw = str(entry.get("keyword", "")).strip()
            tier = str(entry.get("tier", "")).strip()
            if kw:
                lines.append(f"- {kw} ({tier or 'MEDIUM'})")
        return "\n".join(lines)

    @staticmethod
    def _format_trends(trends: list[dict[str, Any]]) -> str:
        lines = []
        for trend in trends:
            title = str(trend.get("title") or "").strip()
            summary = str(trend.get("summary") or trend.get("reason_summary") or "").strip()
            if title:
                if summary:
                    lines.append(f"- {title} — {summary[:200]}")
                else:
                    lines.append(f"- {title}")
        return "\n".join(lines)

    @staticmethod
    def _parse_response(raw: str) -> dict[str, Any]:
        stripped = raw.strip()
        stripped = _FENCE_RE.sub("", stripped).strip()
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            start = stripped.find("{")
            end = stripped.rfind("}")
            if start != -1 and end != -1 and end > start:
                return json.loads(stripped[start : end + 1])
            raise RuntimeError("Suggestion response was not valid JSON")

    @staticmethod
    def _validate_suggestions(
        parsed: dict[str, Any], existing_set: set[str]
    ) -> list[dict[str, Any]]:
        raw_list = parsed.get("suggestions")
        if not isinstance(raw_list, list):
            return []
        result: list[dict[str, Any]] = []
        seen: set[str] = set()
        for entry in raw_list:
            if not isinstance(entry, dict):
                continue
            keyword = str(entry.get("keyword", "")).strip().lower()
            tier_raw = str(entry.get("suggested_tier", "")).strip().upper()
            reasoning = str(entry.get("reasoning", "")).strip()
            if not keyword or tier_raw not in VALID_TIERS:
                continue
            if keyword in existing_set or keyword in seen:
                continue
            seen.add(keyword)
            result.append(
                {
                    "keyword": keyword,
                    "suggested_tier": tier_raw,
                    "reasoning": reasoning,
                }
            )
        return result
