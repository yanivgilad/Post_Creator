from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from article_writer.config import Settings
from article_writer.models import ArticleArtifact


class ManualArticleGenerator:
    def generate(
        self,
        trend: dict[str, Any],
        *,
        language: str,
        target_outlet: str,
        llm_name: str,
        settings: Settings,
    ) -> ArticleArtifact:
        if llm_name != "local-template" and settings.openrouter_api_key:
            try:
                title, body = self._generate_with_openrouter(
                    trend,
                    language=language,
                    target_outlet=target_outlet,
                    llm_name=llm_name,
                    settings=settings,
                )
                return ArticleArtifact(
                    trend_id=int(trend["id"]),
                    language=language,
                    target_outlet=target_outlet,
                    llm_name=llm_name,
                    title=title,
                    body=body,
                    metadata={"mode": "openrouter"},
                )
            except Exception as exc:
                fallback = self._generate_local_template(trend, language=language, target_outlet=target_outlet)
                fallback.metadata.update(
                    {
                        "mode": "local-template",
                        "fallback_reason": f"Fell back to local template after LLM request failed: {exc}",
                        "requested_llm": llm_name,
                    }
                )
                fallback.llm_name = llm_name
                return fallback

        article = self._generate_local_template(trend, language=language, target_outlet=target_outlet)
        article.llm_name = llm_name
        article.metadata.update(
            {
                "mode": "local-template",
                "requested_llm": llm_name,
            }
        )
        if llm_name != "local-template" and not settings.openrouter_api_key:
            article.metadata["fallback_reason"] = (
                "No OpenRouter API key is configured, so a local template article was generated instead."
            )
        return article

    def _generate_local_template(
        self,
        trend: dict[str, Any],
        *,
        language: str,
        target_outlet: str,
    ) -> ArticleArtifact:
        trend_title = str(trend["title"])
        source_name = str(trend["source_name"])
        summary = str(trend.get("summary") or trend.get("reason_summary") or trend_title)
        url = str(trend["url"])
        requested_language = language.strip() or "English"
        target = target_outlet.strip() or "LinkedIn"

        title = f"{trend_title}: a {target} angle worth covering"
        lines = [
            f"# {title}",
            "",
            f"Source: {source_name}",
            f"Original link: {url}",
            "",
            f"This version is formatted for {target}.",
            "",
            "## What happened",
            summary,
            "",
            "## Why this matters now",
            (
                f"The item stood out because it was ranked highly in the latest trend scan. "
                f"That usually means it combines freshness, visible engagement, and a strong AI signal."
            ),
            "",
            f"## Best angle for {target}",
            (
                f"Position the piece around the practical implication, then shape the framing for {target}. "
                f"Instead of restating the announcement, explain what changed, why that platform's readers will care, and what action they can take next."
            ),
            "",
            "## Suggested structure",
            "1. Start with the concrete news event.",
            "2. Explain the underlying trend it points to.",
            "3. Add one opinionated take on why it matters on that platform.",
            "4. End with a practical takeaway or question that fits the platform.",
            "",
            "## Closing take",
            (
                f"If you write about this topic, focus on what makes it useful or strategically important for a {target} audience instead of just describing the release."
            ),
        ]

        metadata: dict[str, Any] = {"mode": "local-template"}
        if requested_language.lower() != "english":
            lines.extend(
                [
                    "",
                    f"Note: you requested {requested_language}. The current local fallback writes in English. "
                    "Once an external LLM provider is configured, this same workflow can generate the full article in the requested language.",
                ]
            )

        return ArticleArtifact(
            trend_id=int(trend["id"]),
            language=requested_language,
            target_outlet=target,
            llm_name="local-template",
            title=title,
            body="\n".join(lines),
            metadata=metadata,
        )

    def _generate_with_openrouter(
        self,
        trend: dict[str, Any],
        *,
        language: str,
        target_outlet: str,
        llm_name: str,
        settings: Settings,
    ) -> tuple[str, str]:
        prompt = self._build_prompt(trend, language=language, target_outlet=target_outlet)
        payload = {
            "model": llm_name,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You write clear, factual, opinionated articles about AI news. "
                        "Return markdown only. Start with a title on the first line prefixed by '# '."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.7,
        }
        request = Request(
            "https://openrouter.ai/api/v1/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {settings.openrouter_api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "http://127.0.0.1:8000",
                "X-Title": "article-writer",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=60) as response:
                raw = json.loads(response.read().decode("utf-8", errors="replace"))
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"OpenRouter request failed with status {exc.code}: {body[:180]}") from exc
        except URLError as exc:
            raise RuntimeError(f"OpenRouter request failed: {exc.reason}") from exc

        content = (
            raw.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
            .strip()
        )
        if not content:
            raise RuntimeError("OpenRouter returned an empty article")

        first_line = content.splitlines()[0].strip()
        title = first_line.lstrip("# ").strip() if first_line.startswith("#") else str(trend["title"])
        return title, content

    def _build_prompt(self, trend: dict[str, Any], *, language: str, target_outlet: str) -> str:
        evidence = trend.get("evidence") or []
        evidence_lines = "\n".join(f"- {item}" for item in evidence)
        return (
            f"Write a complete article in {language}.\n"
            f"Target platform/publication target: {target_outlet}.\n\n"
            f"News item title: {trend['title']}\n"
            f"Source: {trend['source_name']}\n"
            f"Summary: {trend.get('summary') or trend.get('reason_summary') or ''}\n"
            f"Why it ranked highly: {trend.get('reason_summary') or ''}\n"
            f"Original link: {trend['url']}\n"
            f"Supporting evidence:\n{evidence_lines or '- None'}\n\n"
            "Requirements:\n"
            "- Start with a strong title.\n"
            "- Write in a clear editorial style, not as bullet notes.\n"
            "- Tailor the tone, structure, and length to the target platform.\n"
            "- Explain what happened, why it matters, and what readers should watch next.\n"
            "- Keep it factual and grounded in the provided information.\n"
            "- End with a concise closing takeaway."
        )