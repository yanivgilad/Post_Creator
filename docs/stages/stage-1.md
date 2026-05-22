# Stage 1 — Personalization (config + persona)

**Goal:** Make the tool *Yaniv's*. Trim the sources to his domains, enable arXiv, and replace every trace of the "Amit Raz" persona with Yaniv's CTO-positioning persona, in all three places it lives. By the end, a generated test post should sound like Yaniv and rank items relevant to AI / LLM / RAG / agents.

**Branch off:** main (after Stage 0 commit `53487dd`).
**Provider note:** We are NOT touching the provider in this stage. Generation still runs on the existing Google/Gemini path; OpenAI is Stage 2. A real end-to-end test post that needs an API call may therefore be deferred to Stage 2 — see DoD note.

---

## Tasks

### 1. Replace the LinkedIn persona
- Replace the full contents of `prompts/linkedin_system_prompt.txt` with Yaniv's new persona file (provided separately, `linkedin_system_prompt.txt`).
- Verify no "Amit" / "Amit Raz" / "rzailabs" strings remain in that file.

### 2. Replace the embedded personas in code
The Stage 0 mapping found that Amit's persona is ALSO hardcoded in two more prompts inside `src/article_writer/generation/article_generator.py` (around line 18): `TWITTER_SYSTEM_PROMPT` and `REDDIT_SYSTEM_PROMPT`.
- Update both so they describe **Yaniv**, not Amit, consistent with the new LinkedIn persona (same credibility, same voice, same "no buzzwords / no em dashes", Hebrew-default behavior).
- Keep them shorter than the LinkedIn one (Twitter/Reddit are different formats), but the persona identity must be Yaniv.
- Confirm no "Amit" strings remain anywhere under `src/` or `prompts/`. (A repo-wide search for "Amit" should return only git history / blame, not file contents.)

### 3. Trim and refocus `sources.json`
- Remove the `gaming` and `hardware` streams and their keywords (xbox, ps5, gta, nvidia consumer, etc.) — anything not relevant to AI / LLM / RAG / agents / enterprise AI.
- Keep and focus the AI-relevant sources: Reddit (AI/ML/LocalLLaMA-type subreddits), Hacker News, arXiv, GitHub, and the AI RSS blogs.
- Set `arxiv.enabled = true` (currently `false` at sources.json:265).
- Tune the keyword list. Framing: surface the **popular, actively-debated questions, tensions, and reflective discussions** in LLM/AI/RAG that Yaniv can add his angle to, NOT product-launch news. Keywords are in **English** (that's how titles/posts on Reddit/HN/arXiv are written; Hebrew search returns almost nothing there). Avoid pure product/model-name keywords ("X just launched").
  - **This exact list is approved by Yaniv. Claude Code must enter it as-is and must NOT trim, drop, or "consolidate" it.** Claude Code may only SUGGEST *additional* keywords, which Yaniv approves. Every phrase stays anchored to LLM/RAG/agents/retrieval so it pulls relevant discussion, not generic noise.
    - **Problems & tradeoffs:** RAG limitations / when RAG fails, RAG vs fine-tuning vs long-context, when to use RAG vs an LLM alone, LLM hallucination and grounding, retrieval quality / chunking problems.
    - **Reliability & scale:** agentic systems reliability, enterprise RAG at scale, evaluation of LLM/RAG systems.
    - **Lessons & what works:** RAG/LLM best practices, lessons learned building RAG, what doesn't work in production, RAG/agent antipatterns, what people realized doesn't work.
    - **Direction & open problems:** still-unsolved problems in LLM/RAG, where LLM/RAG is heading, what to adopt vs avoid in LLM systems, techniques/angles worth knowing.
    - **Solutions & alternatives:** emerging RAG/LLM solutions and approaches, alternative architectures to RAG, new retrieval/agent techniques, how teams are solving LLM/RAG problems.
  - Ranking stays engagement-based (popular = interesting to people), no LLM quality/novelty layer — matches Yaniv's decision. Novelty/angle comes from Yaniv in the post, not from the ranker.
  - **Yaniv is the final selector.** The ranking is only a sort order to help him scan the feed; nothing is filtered out or discarded. He picks what interests him and acts on it. Because he filters by eye, a broad keyword list is safe and welcome.

### 4. (No code beyond the above)
Do not refactor, do not add the provider, do not change the web UI. Stay in scope.

---

## Definition of Done
- `prompts/linkedin_system_prompt.txt` = Yaniv's persona; zero "Amit" in file contents.
- `TWITTER_SYSTEM_PROMPT` and `REDDIT_SYSTEM_PROMPT` in `article_generator.py` = Yaniv; zero "Amit" under `src/`.
- `sources.json` trimmed to AI/LLM/RAG domains, `gaming`/`hardware` removed, `arxiv.enabled = true`.
- Yaniv has reviewed and approved the new keyword list.
- **Test post:** if an OpenAI/Gemini key is available, generate one test post and confirm it sounds like Yaniv (sharp, senior, Hebrew default, his angle). If no working provider key yet, this single check is deferred to Stage 2 and noted in PROGRESS.md.

## Approval ritual (same as always)
When done → Yaniv reviews → updates Stage 1 status to `done` in PROGRESS.md → `git add . && git commit` → `git push` → open a fresh chat for Stage 2.
