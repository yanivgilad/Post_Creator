from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from article_writer.config import Settings
from article_writer.models import ArticleArtifact


SYSTEM_PROMPT = (
    "You write clear, factual, opinionated articles about AI news. "
    "Return markdown only. Start with a title on the first line prefixed by '# '."
)

# Fallback only — the .txt files in prompts/ override these at runtime.
TWITTER_SYSTEM_PROMPT = """You are a Twitter/X ghostwriter for Yaniv Gilad, a senior technology leader and AI architect based in Israel (20+ years in software, AI/ML, large-scale systems; CEO/CTO/VP R&D background; co-founded X-Trader; now leading enterprise AI direction at Kaleidoo, focused on massive-scale RAG and autonomous agents). Your job is to position him as a top-tier authority in AI/LLMs/large-scale system architecture, so the right people (founders, investors, R&D leaders, hiring execs) recognize him as the kind of person who leads AI at scale.

Positioning, not job-hunting. Posts read like someone already operating at that level. Seniority shows through the depth of the take, not by listing credentials.

## Voice
- First person, direct, plain-spoken. Calm confidence of someone who has built at scale and seen multiple cycles.
- Contractions are fine.
- Mix short punchy lines with longer ones.
- Takes a clear, reasoned position. Willing to challenge a popular approach, but always backed by experience, never with heat for its own sake.
- Grounded in practice: connects findings to building real systems at scale, R&D leadership, business impact (RAG at scale, agent systems, data infrastructure).
- Never lecture-y, never hype-y, never corporate, never insecure.
- No em dashes (use commas or parentheses).
- No buzzwords: no "leverage," "unlock," "game-changer," "cutting-edge," "revolutionize," "synergy," "disruptive," "paradigm shift."

## The bar
Every tweet must do at least one of:
- Surface something genuinely new or early in LLM / AI / RAG.
- Point at the non-obvious implication of a popular topic, the angle the crowd is missing.
- Challenge a comfortable assumption with reasoning from having built real systems at scale.

A plain summary of someone else's article reads like an aggregator and will NOT position him. The source is raw material; the value is Yaniv's read on it.

## Format
- Single tweet: one sharp take, ~250 characters of real content max (leave room for the link).
- Thread (3-5 tweets): only when the insight has multiple distinct points worth unpacking.
- First tweet is the hook and must stand alone.
- No "BREAKING", no "Hot take:", no "So,". Start with the idea.
- Max 2 hashtags at the very end, never mid-sentence.
- Emojis: 0-1, only when it genuinely adds something. Default to none.
- If a thread, number tweets: "1/", "2/", etc. Place source URL at end of the last (or only) tweet.

## Language
Default is English. Keep technical terms, model names, and brand names in English regardless. If output_language is "Hebrew," write in Hebrew with the same voice and sharpness; it must not read like a translation.

## Input you'll receive
- title, source_name, author, original_url, summary
- output_language: "Hebrew" or "English" (default: English)
- custom_focus (optional): a specific angle from Yaniv, prioritize it while staying factual.

## Output
Output ONLY the tweet (or thread) text, ready to post. No explanation, no options."""

# Fallback only — the .txt files in prompts/ override these at runtime.
REDDIT_SYSTEM_PROMPT = """You write Reddit posts that share interesting AI findings with the right Reddit communities in a way that feels native to Reddit: substantive, not promotional, not corporate.

## Non-negotiable rules
Reddit is allergic to marketing and self-promotion. A post that smells like a brand wrote it gets downvoted and poisons future credibility. Write like a community member sharing something they actually found interesting.

- No mention of Yaniv, Kaleidoo, or any personal brand.
- No "I built this" or "check out my project" framing.
- No marketing language. No viral hooks.

## Subreddit selection
Pick exactly ONE based on the content.

- **r/artificial**: general AI news, product launches, industry developments. Broad audience, moderate depth. Good default for mainstream AI news.
- **r/MachineLearning**: research papers, benchmarks, model architectures, training techniques. Expects deep technicality. Shallow posts get buried.
- **r/LocalLLaMA**: local models, open weights, quantization, inference, local hardware. Technical, opinionated, hates hype, loves benchmarks.
- **r/learnmachinelearning**: explainers, tutorials, papers with clear learning value.

## Title
- Most important part. Many readers only see this.
- Specific and factual. State what the thing is or does.
- No clickbait, no all-caps, no question titles unless the content genuinely invites discussion.
- 60-100 characters ideal.
- For r/MachineLearning and r/LocalLLaMA: lead with the concrete finding, not the narrative ("GPT-4o beats Claude on X benchmark", not "OpenAI drops major update").

## Body (when used)
- 2-4 short paragraphs.
- (1) What this is, concretely. (2) Why it matters or what the implication is. (3) Optional: one specific, genuine question that invites discussion.
- URL on its own line at the very end, no label.
- No headers, no bullet points unless content is list-shaped. No emojis.

## Link vs text post
- Well-known paper or official blog: link post is fine (title only).
- Anything that needs context: text post with body.
- Default to text post with body.

## Tone
Neutral to mildly enthusiastic. "Impressive" yes; "mind-blowing" no. Skepticism welcome when warranted. Let the finding speak. Brief context, not heavy editorializing.

## Language
Default is English (most communities are English-speaking). Keep technical terms, model names, and brand names in English regardless. If output_language is "Hebrew," write in Hebrew with the same voice.

## Input
- title, source_name, author, original_url, summary
- output_language: "Hebrew" or "English" (default: English)
- custom_focus (optional): a specific angle to consider while writing.

## Output
Output exactly this structure, nothing else:

SUBREDDIT: r/[subreddit]

TITLE:
[title text]

BODY:
[body text]

[url]

For a link post (no body):

SUBREDDIT: r/[subreddit]

TITLE:
[title text]

URL:
[url]

No explanation, no options."""

PLATFORM_SYSTEM_PROMPTS = {
    "LinkedIn": (
        "Write for a professional audience that wants business relevance and practical implications. "
        "Use a polished editorial tone, connect the news to strategy or execution, and end with a concrete takeaway."
    ),
    "Reddit": (
        "Write for a skeptical community that values substance over branding. "
        "Be direct, grounded, and specific. Avoid hype, acknowledge uncertainty when needed, and make the analysis worth discussing."
    ),
    "Hashnode/Dev.to": (
        "Write like a developer publication. Use clear structure, explain the technical or product significance, and make the piece useful for builders. "
        "Prefer concrete details over marketing language."
    ),
}


class ManualArticleGenerator:
    def _normalize_custom_prompt(self, custom_prompt: str | None) -> str | None:
        if custom_prompt is None:
            return None
        normalized = custom_prompt.strip()
        return normalized or None

    def _load_prompt_file(self, explicit_path: str | None, default_filename: str, fallback: str) -> str:
        candidates = [
            Path(explicit_path) if explicit_path else None,
            Path.cwd() / "prompts" / default_filename,
        ]
        for path in candidates:
            if path and path.is_file():
                return path.read_text(encoding="utf-8").strip()
        return fallback

    def _build_system_prompt(self, target_outlet: str, settings: Settings) -> str:
        if target_outlet == "Twitter/X":
            prompt = self._load_prompt_file(settings.twitter_prompt_file, "twitter_system_prompt.txt", TWITTER_SYSTEM_PROMPT)
            return (
                f"{prompt}\n\n"
                "If the user provides a custom focus or angle, prioritize it while staying factual and grounded in the provided information."
            )
        if target_outlet == "LinkedIn":
            prompt = self._load_prompt_file(settings.linkedin_prompt_file, "linkedin_system_prompt.txt", "")
            return (
                f"{prompt}\n\n"
                "If the user provides a custom focus or angle, prioritize it while staying factual and grounded in the provided information."
            )
        if target_outlet == "Reddit":
            prompt = self._load_prompt_file(settings.reddit_prompt_file, "reddit_system_prompt.txt", REDDIT_SYSTEM_PROMPT)
            return (
                f"{prompt}\n\n"
                "If the user provides a custom focus or angle, prioritize it while staying factual and grounded in the provided information."
            )
        platform_guidance = PLATFORM_SYSTEM_PROMPTS.get(
            target_outlet,
            "Match the tone, structure, and depth to the requested outlet while staying factual and readable.",
        )
        return (
            f"{SYSTEM_PROMPT} "
            f"Target outlet: {target_outlet}. "
            f"{platform_guidance} "
            "You will receive a 'Provided information' section listing the exact inputs available for this article. "
            "Use that information as your source of truth, do not invent missing facts, and make any uncertainty explicit in the writing when needed."
        )

    def generate(
        self,
        trend: dict[str, Any],
        *,
        language: str,
        target_outlet: str,
        llm_name: str,
        settings: Settings,
        custom_prompt: str | None = None,
    ) -> ArticleArtifact:
        custom_prompt = self._normalize_custom_prompt(custom_prompt)
        title, body, mode = self._generate_with_provider(
            trend,
            language=language,
            target_outlet=target_outlet,
            llm_name=llm_name,
            settings=settings,
            custom_prompt=custom_prompt,
        )
        metadata = {"mode": mode}
        if custom_prompt:
            metadata["custom_prompt"] = custom_prompt
        return ArticleArtifact(
            trend_id=int(trend["id"]),
            language=language,
            target_outlet=target_outlet,
            llm_name=llm_name,
            title=title,
            body=body,
            metadata=metadata,
        )

    def _generate_with_provider(
        self,
        trend: dict[str, Any],
        *,
        language: str,
        target_outlet: str,
        llm_name: str,
        settings: Settings,
        custom_prompt: str | None,
    ) -> tuple[str, str, str]:
        provider_name, model_name = self._parse_model_name(llm_name)
        if provider_name == "google":
            try:
                title, body = self._generate_with_gemini(
                    trend,
                    language=language,
                    target_outlet=target_outlet,
                    model_name=model_name,
                    settings=settings,
                    custom_prompt=custom_prompt,
                )
                return title, body, "gemini"
            except Exception as exc:
                raise RuntimeError(f"Gemini request failed: {exc}") from exc
        raise RuntimeError(
            f"Direct provider '{provider_name}' is not implemented yet for model '{llm_name}'."
        )

    def _parse_model_name(self, llm_name: str) -> tuple[str, str]:
        provider_name, separator, model_name = llm_name.partition("/")
        if not separator or not provider_name.strip() or not model_name.strip():
            raise RuntimeError(
                f"Model '{llm_name}' is invalid. Use the direct-provider format 'provider/model'."
            )
        return provider_name.strip().lower(), model_name.strip()

    def _generate_with_gemini(
        self,
        trend: dict[str, Any],
        *,
        language: str,
        target_outlet: str,
        model_name: str,
        settings: Settings,
        custom_prompt: str | None,
    ) -> tuple[str, str]:
        if not settings.gemini_api_key:
            raise RuntimeError("No Gemini API key is configured.")

        prompt = self._build_prompt(
            trend,
            language=language,
            target_outlet=target_outlet,
            custom_prompt=custom_prompt,
        )
        payload = {
            "system_instruction": {
                "parts": [{"text": self._build_system_prompt(target_outlet, settings)}],
            },
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": prompt}],
                }
            ],
            "generationConfig": {
                "temperature": 0.7,
            },
        }
        request = Request(
            (
                "https://generativelanguage.googleapis.com/v1beta/models/"
                f"{model_name}:generateContent?key={settings.gemini_api_key}"
            ),
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=60) as response:
                raw = json.loads(response.read().decode("utf-8", errors="replace"))
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"status {exc.code}: {body[:180]}") from exc
        except URLError as exc:
            raise RuntimeError(str(exc.reason)) from exc

        parts = raw.get("candidates", [{}])[0].get("content", {}).get("parts", [])
        content = "\n\n".join(
            part.get("text", "").strip()
            for part in parts
            if isinstance(part, dict) and part.get("text", "").strip()
        ).strip()
        if not content:
            raise RuntimeError("Gemini returned an empty article")

        first_line = content.splitlines()[0].strip()
        title = first_line.lstrip("# ").strip() if first_line.startswith("#") else str(trend["title"])
        return title, content

    def _build_social_payload(
        self,
        trend: dict[str, Any],
        *,
        language: str,
        extra: dict | None = None,
        custom_prompt: str | None = None,
    ) -> str:
        payload: dict = {
            "title": str(trend["title"]),
            "source_name": str(trend["source_name"]),
            "author": str(trend.get("author") or ""),
            "original_url": str(trend["url"]),
            "summary": str(trend.get("summary") or trend.get("reason_summary") or ""),
            "output_language": language,
        }
        if custom_prompt:
            payload["custom_focus"] = custom_prompt
        if extra:
            payload.update(extra)
        return json.dumps(payload, ensure_ascii=False, indent=2)

    def _build_prompt(
        self,
        trend: dict[str, Any],
        *,
        language: str,
        target_outlet: str,
        custom_prompt: str | None = None,
    ) -> str:
        custom_prompt = self._normalize_custom_prompt(custom_prompt)
        if target_outlet == "Twitter/X":
            return self._build_social_payload(trend, language=language, custom_prompt=custom_prompt)
        if target_outlet == "LinkedIn":
            return self._build_social_payload(
                trend,
                language=language,
                extra={"goal": "thought_leadership"},
                custom_prompt=custom_prompt,
            )
        if target_outlet == "Reddit":
            return self._build_social_payload(trend, language=language, custom_prompt=custom_prompt)
        evidence = trend.get("evidence") or []
        evidence_lines = "\n".join(f"- {item}" for item in evidence)
        supporting_urls = trend.get("supporting_urls") or []
        supporting_url_lines = "\n".join(f"- {item}" for item in supporting_urls)
        metadata = trend.get("metadata") or {}
        metadata_block = json.dumps(metadata, ensure_ascii=True, sort_keys=True) if metadata else "None"
        author = trend.get("author") or "Unknown"
        published_at = trend.get("published_at") or "Unknown"
        engagement_score = trend.get("engagement_score")
        rank_score = trend.get("rank_score")
        external_id = trend.get("external_id") or "Unknown"
        return (
            f"Write a complete article in {language}.\n"
            f"Target platform/publication target: {target_outlet}.\n\n"
            "Provided information:\n"
            f"- Trend id: {trend['id']}\n"
            f"- Run id: {trend.get('run_id') or 'Unknown'}\n"
            f"- External id: {external_id}\n"
            f"- Title: {trend['title']}\n"
            f"- Source name: {trend['source_name']}\n"
            f"- Author: {author}\n"
            f"- Published at: {published_at}\n"
            f"- Original link: {trend['url']}\n"
            f"- Summary: {trend.get('summary') or trend.get('reason_summary') or ''}\n"
            f"- Why it ranked highly: {trend.get('reason_summary') or ''}\n"
            f"- Engagement score: {engagement_score if engagement_score is not None else 'Unknown'}\n"
            f"- Rank score: {rank_score if rank_score is not None else 'Unknown'}\n"
            f"- Requested language: {language}\n"
            f"- Requested target outlet: {target_outlet}\n"
            f"- Custom focus from user: {custom_prompt or 'None'}\n"
            f"- Evidence:\n{evidence_lines or '- None'}\n"
            f"- Supporting URLs:\n{supporting_url_lines or '- None'}\n"
            f"- Source metadata: {metadata_block}\n\n"
            "Requirements:\n"
            "- Start with a strong title.\n"
            "- Write in a clear editorial style, not as bullet notes.\n"
            "- Tailor the tone, structure, and length to the target platform.\n"
            "- Prioritize the user's requested focus when it fits the provided facts.\n"
            "- Explain what happened, why it matters, and what readers should watch next.\n"
            "- Keep it factual and grounded in the provided information.\n"
            "- End with a concise closing takeaway."
        )