# PROGRESS — Post_Creator (Yaniv Gilad)

Central tracking file. **This is the source of truth for status.** At the start of every new Cursor chat: pin this file plus the relevant stage doc, and say "working on Stage X".

## Project goal (short)
A personal tool that pulls items from interest areas (AI / LLM / RAG) across selected sources, ranks them by freshness + engagement + keyword fit (no LLM quality judgment), shows a feed with a short summary, and lets me generate a LinkedIn post (Hebrew default / English), edit with notes, and copy for manual publishing.

## Per-stage working ritual (mandatory)
1. Open a new chat: "working on Stage X". Pin `PROGRESS.md` + `docs/stages/stage-0X.md`.
2. Work **only** on what the stage defines. Do not touch anything else.
3. When done → run the Definition of Done.
4. **Yaniv approves.** Only after approval: update the status here to `done`, then commit to git.
5. Move to the next stage.

> Iron rule: no commit before Yaniv's approval. No stage transition before the file shows `done`.

## Stage status
| # | Stage | Status | Definition of Done |
|---|-------|--------|--------------------|
| 0 | Code mapping + first run | `done` | Short `docs/ARCHITECTURE.md` written; `init-db` + `run-once` run successfully; a real feed is visible at `http://127.0.0.1:8000` (live-run portion intentionally deferred to Stage 2) |
| 1 | Personalization: config + persona | `pending` | `sources.json` trimmed to my domains + arXiv enabled; `prompts/linkedin_system_prompt.txt` replaced with Yaniv's persona; a test post sounds like me |
| 2 | (Optional) Add provider (OpenAI/Claude) | `pending` | New provider branch in `article_generator.py`; post generation succeeds with the key from `.env` |
| 3 | Sharpen the read+post flow | `pending` | Full manual path works: short summary in feed → open → full summary → create post → language toggle → notes → revision → manual edit → copy button |
| 4 | (Later/optional) Automatic LinkedIn publishing | `pending` | OAuth + `w_member_social` + approval gate before publishing |

## Decision log
- **Personal** use only → Reddit's free tier is legal and sufficient (non-commercial).
- In v1 there is **no automatic publishing** — manual copy only.
- We build **on the fork** `yanivgilad/Post_Creator` (fork of `razamit/article_writer`), not from scratch.
- Ranking without an LLM-as-judge — kept as the code already does it.
- Provider: code default = Gemini. Target = OpenAI and/or Claude (Stage 2). Keys live in `.env` only, never in git/chat.
- Sources: everything I asked for (Reddit, HN, arXiv, GitHub, RSS/blogs).

## Open questions
- ~~Does `reddit.py` use OAuth or only public endpoints?~~ → **Answered in Stage 0**: public `.json` only, no OAuth, generic User-Agent. With ~40 subreddits in the current `sources.json`, 429/block risk is real. Stage-1 choice: trim list + unique UA, or switch to OAuth.
- OpenAI or Claude as primary provider? (Decide in Stage 2)
- Should `/articles/{id}` support in-place editing of the body, or stay with "Create Another Version"? (Stage 3)
- Should "open item" have an internal page with a full summary, or stay link-out only? (Stage 3)

## Stage 0 notes (done)
- `docs/ARCHITECTURE.md` written (~150 lines) — mapping + gaps. Approved by Yaniv.
- **Live-run portion of the DoD intentionally deferred to Stage 2** (OpenAI/Claude provider). `init-db` and `run-once` are defined as CLI subcommands in `src/article_writer/cli.py` and are ready to run when Stage 2 lands.
- Findings that need a decision before Stage 1:
  - `arxiv.enabled = false` in the current `sources.json` — contradicts the decision journal. Looks like a fork-time oversight. (Flip back in Stage 1.)
  - `sources.json` carries `gaming` + `hardware` streams with dozens of subreddits/feeds. For AI/LLM/RAG only this is noise and should be trimmed.
  - `prompts/linkedin_system_prompt.txt` is written as a ghostwriter for **Amit Raz / rzailabs.com**. Full replacement with Yaniv's persona is the core of Stage 1.
  - `article_generator.py` + `filter_supported_article_llm_options` block **every** provider other than `google/...`. Stage 2 must open both sites.
- No commit. Stage 0 status stays `pending`.
