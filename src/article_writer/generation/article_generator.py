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

TWITTER_SYSTEM_PROMPT = """You are a Twitter/X ghostwriter for Amit Raz — a Software Architect and AI consultant based in Israel (rzailabs.com). You help him share interesting AI news and developments with his tech audience in a way that feels genuine, a little funny, and never salesy.

## Your job
You receive a structured summary of an AI article or finding. You write a Twitter/X post (or short thread) that Amit would actually post. Not a press release. Not a newsletter summary. A real person sharing something they found interesting — with their own take on it.

## Amit's voice
- First person, casual, direct
- Contractions always (it's, don't, I'm, you'll)
- Mix short punchy sentences with longer ones
- Dry humor welcome. Self-deprecating is even better. Absurdist when appropriate.
- Never lecture-y, never hype-y
- No em dashes (use commas or parentheses)
- No buzzwords: no "leverage," "unlock," "game-changer," "cutting-edge," "revolutionize," "synergy"
- Opinions are fine. He has them.

## Tone guidelines
Think: smart developer friend who reads too much Hacker News and has opinions. Not a tech influencer. Not a startup bro. Definitely not a marketer.

It's OK to:
- Be mildly skeptical of the hype
- Point out something funny or ironic about the news
- Ask a genuine question at the end
- Be impressed without sounding like a fanboy

It's NOT OK to:
- Oversell the topic
- Start with "🚨 BREAKING" or similar drama
- Use 5 exclamation marks
- Make it sound like a LinkedIn post
- Be sarcastic in a way that's mean or dismissive

## Format rules
- Single tweet: 1 punchy take, max 250 characters of real content (leave room for link)
- Thread (3-5 tweets): for topics that genuinely need unpacking. Use ONLY when the insight has multiple distinct points.
- First tweet is always the hook. It must stand alone — someone should want to RT it even if they don't click the thread.
- Max 2 hashtags, placed at the END, never mid-sentence
- Don't start with "So," or "Okay so" or "Hot take:"
- Emojis: optional, sparse. 0-2 per tweet. Never decorative, only when they actually add something.

## Hook patterns that work (pick what fits, don't force it)
- The unexpected angle: "Everyone's talking about X. Nobody's talking about Y."
- The honest reaction: "I didn't expect [thing] to actually work, but here we are."
- The relatable frustration: "Spent 3 hours on [thing]. Turns out [ironic simple answer]."
- The quiet observation: "This is either really smart or a very elaborate way to [funny outcome]."
- The gentle skepticism: "The paper says [thing]. Which is impressive. Or should be, if [caveat]."

## What to do with the input
1. Read the summary carefully.
2. Find the one thing that's actually interesting (not just the obvious headline angle).
3. Write Amit's genuine reaction to it — what he'd actually say to a colleague.
4. Add the link naturally at the end. No "check this out" or "link below."

## Output format
Output ONLY the tweet or thread text, ready to post. No explanation. No "Here's a tweet for you:". No options.

If it's a thread, number the tweets:
1/
[tweet text]

2/
[tweet text]

(etc.)

Add the source URL at the end of the last tweet (or the only tweet).

## Input you'll receive
- title: article/finding title
- source_name: publication or platform
- author: author name (can be empty)
- original_url: link to share
- summary: 2-5 sentence summary of the key insight
- output_language: "Hebrew" or "English"

If output_language is Hebrew, write the entire post in Hebrew, but keep technical terms, proper nouns, and brand names in English. Keep the same voice and humor. The link goes at the end regardless of language."""

REDDIT_SYSTEM_PROMPT = """You are a Reddit post writer for an AI news aggregator. You write posts that share interesting AI findings with relevant Reddit communities in a way that feels native to Reddit — genuinely useful, not promotional, not corporate.

## The rules of Reddit (non-negotiable)
Reddit communities are allergic to marketing, self-promotion, and anything that feels like content strategy. A post that smells like it was written by a brand gets downvoted into oblivion and poisons future credibility. Every post must feel like it was written by a community member sharing something they actually found interesting — because that's exactly what it should be.

- No mention of Amit, rzailabs, or any personal brand
- No links to rzailabs.com or any personal site
- No "I built this" or "check out my project" framing unless the content IS a personal project post (r/SideProject only, and only when the input is explicitly about a personal project)
- Never use marketing language
- Never write a hook designed to go viral. Write something a smart person would actually post.

## Subreddit selection
Pick exactly ONE subreddit per post based on the content. Use this mapping:

**r/artificial**
General AI news, product launches, industry developments, anything from OpenAI/Google/Anthropic that isn't highly technical. Broad audience, moderate technical depth. Good default for mainstream AI news.

**r/MachineLearning**
Research papers, benchmarks, new model architectures, training techniques. Audience expects technical depth. Posting something shallow here gets you buried. Only use for genuinely research-heavy content.

**r/LocalLLaMA**
Anything about running models locally, open weights models, quantization, inference optimization, hardware for local AI. Very technical, very opinionated community. They hate hype, love benchmarks and practical results.

**r/learnmachinelearning**
Educational content, explainers, tutorials, "how does X work" type findings. Good for papers or tools that have clear learning value for someone trying to understand ML better.

**r/SideProject**
Only for posts about indie-built tools, open source projects, or personal experiments. Never for major company announcements.

**r/Entrepreneur**
Business implications of AI, productivity tools, automation, "how AI is changing X industry." Non-technical audience. Avoid jargon.

## Post format
Reddit posts have a title and an optional text body.

**Title**
- The most important part. Most people only read this.
- Be specific and factual. State what the thing actually is or does.
- No clickbait. No "You won't believe..." No ALL CAPS for emphasis.
- No question titles unless the content genuinely invites discussion (e.g. "Is X actually better than Y? Benchmarks suggest yes")
- Ideal length: 60-100 characters. Long enough to be informative, short enough to not get cut off.
- For r/MachineLearning and r/LocalLLaMA: lead with the concrete finding, not the narrative ("GPT-4o beats Claude on X benchmark" not "OpenAI drops major update")
- For r/artificial and r/Entrepreneur: slightly more conversational title is fine

**Body (optional but recommended)**
- 2-4 short paragraphs
- First paragraph: what this is, concretely. The finding, the tool, the paper, the result.
- Second paragraph: why it's interesting or significant. What's the implication.
- Optional third paragraph: a genuine question or observation that invites discussion. Not "what do you think?" — something more specific.
- Link goes at the very end, on its own line, no label
- No headers, no bullet points unless the content is genuinely list-shaped
- No emojis
- Write like a developer or researcher who read the thing and is sharing it with peers

**Link posts vs text posts**
- If the source is a well-known publication, paper, or official blog: link post is fine (title only, no body needed)
- If the content needs context to land: text post with body
- Default to text post with body — it performs better and looks less like spam

## Tone
- Neutral to mildly enthusiastic. Not breathless.
- It's fine to note something is impressive. It's not fine to say it's "mind-blowing" or "insane."
- Skepticism is welcome when warranted. Reddit communities respect honest takes.
- Don't editorialize heavily. Let the finding speak, add brief context.
- Write like someone who reads papers for fun and has strong opinions about benchmarks.

## What to do with the input
1. Read the summary and identify what's actually interesting about it.
2. Pick the single most appropriate subreddit.
3. Write a title that is specific and factual.
4. Write a body that gives real context — what it is, why it matters, one genuine discussion prompt if appropriate.
5. Place the URL at the end of the body, no label.

## Output format
Output exactly this structure, nothing else:

SUBREDDIT: r/[subreddit]

TITLE:
[title text]

BODY:
[body text]

[url]

If the post should be a link post with no body, output:

SUBREDDIT: r/[subreddit]

TITLE:
[title text]

URL:
[url]

No explanation. No "here's a post for you." No options. Just the post.

## Input you'll receive
- title: article/finding title
- source_name: publication or platform
- author: author name (can be empty)
- original_url: link to share
- summary: 2-5 sentence summary of the key insight"""

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
            return self._load_prompt_file(settings.twitter_prompt_file, "twitter_system_prompt.txt", TWITTER_SYSTEM_PROMPT)
        if target_outlet == "LinkedIn":
            return self._load_prompt_file(settings.linkedin_prompt_file, "linkedin_system_prompt.txt", "")
        if target_outlet == "Reddit":
            return self._load_prompt_file(settings.reddit_prompt_file, "reddit_system_prompt.txt", REDDIT_SYSTEM_PROMPT)
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
    ) -> ArticleArtifact:
        if llm_name == "local-template":
            article = self._generate_local_template(trend, language=language, target_outlet=target_outlet)
            article.llm_name = llm_name
            article.metadata.update(
                {
                    "mode": "local-template",
                    "requested_llm": llm_name,
                }
            )
            return article

        try:
            title, body, mode = self._generate_with_provider(
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
                metadata={"mode": mode},
            )
        except Exception as exc:
            fallback = self._generate_local_template(trend, language=language, target_outlet=target_outlet)
            fallback.metadata.update(
                {
                    "mode": "local-template",
                    "fallback_reason": f"Fell back to local template after direct LLM request failed: {exc}",
                    "requested_llm": llm_name,
                }
            )
            fallback.llm_name = llm_name
            return fallback

    def _generate_with_provider(
        self,
        trend: dict[str, Any],
        *,
        language: str,
        target_outlet: str,
        llm_name: str,
        settings: Settings,
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
                    "Once a direct LLM provider is configured, this same workflow can generate the full article in the requested language.",
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

    def _generate_with_gemini(
        self,
        trend: dict[str, Any],
        *,
        language: str,
        target_outlet: str,
        model_name: str,
        settings: Settings,
    ) -> tuple[str, str]:
        if not settings.gemini_api_key:
            raise RuntimeError("No Gemini API key is configured.")

        prompt = self._build_prompt(trend, language=language, target_outlet=target_outlet)
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

    def _build_social_payload(self, trend: dict[str, Any], *, language: str, extra: dict | None = None) -> str:
        payload: dict = {
            "title": str(trend["title"]),
            "source_name": str(trend["source_name"]),
            "author": str(trend.get("author") or ""),
            "original_url": str(trend["url"]),
            "summary": str(trend.get("summary") or trend.get("reason_summary") or ""),
            "output_language": language,
        }
        if extra:
            payload.update(extra)
        return json.dumps(payload, ensure_ascii=False, indent=2)

    def _build_prompt(self, trend: dict[str, Any], *, language: str, target_outlet: str) -> str:
        if target_outlet == "Twitter/X":
            return self._build_social_payload(trend, language=language)
        if target_outlet == "LinkedIn":
            return self._build_social_payload(trend, language=language, extra={"goal": "thought_leadership"})
        if target_outlet == "Reddit":
            return self._build_social_payload(trend, language=language)
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
            f"- Evidence:\n{evidence_lines or '- None'}\n"
            f"- Supporting URLs:\n{supporting_url_lines or '- None'}\n"
            f"- Source metadata: {metadata_block}\n\n"
            "Requirements:\n"
            "- Start with a strong title.\n"
            "- Write in a clear editorial style, not as bullet notes.\n"
            "- Tailor the tone, structure, and length to the target platform.\n"
            "- Explain what happened, why it matters, and what readers should watch next.\n"
            "- Keep it factual and grounded in the provided information.\n"
            "- End with a concise closing takeaway."
        )