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
| 1 | Personalization: config + persona | `done` | `sources.json` trimmed to my domains + arXiv enabled; `prompts/linkedin_system_prompt.txt` replaced with Yaniv's persona; a test post sounds like me |
| 2 | Add LLM provider (Azure OpenAI) | `done` | Azure OpenAI provider wired (default `azure/gpt-4o`); LinkedIn post generated in Hebrew end-to-end; scheduler off by default |
| 3 | UX sharpening (RTL + on-demand summary) | `done` | Hebrew renders RTL in the dashboard; per-item Summarize button calls Azure and shows a short summary inline; LLM usage + cumulative cost displayed per call and on article-detail pages. **Smart Rank (the full-article re-ranker) was de-scoped mid-stage** and will be its own future stage if needed. |
| 4 | Keyword management UI + LLM suggestions | `pending` | `/keywords` page lists keywords ordered by importance with drag-reorder, inline edit, delete, add; ordering affects `rank_score` on the next run; "Get suggestions" returns LLM-generated keyword recommendations matched to Yaniv's persona + latest trends |
| 5 | (Later/optional) Automatic LinkedIn publishing | `pending` | OAuth + `w_member_social` + approval gate before publishing |

## Decision log
- **Personal** use only → Reddit's free tier is legal and sufficient (non-commercial).
- In v1 there is **no automatic publishing** — manual copy only.
- We build **on the fork** `yanivgilad/Post_Creator` (fork of `razamit/article_writer`), not from scratch.
- Ranking without an LLM-as-judge — kept as the code already does it.
- Provider: code default = Gemini. Target = OpenAI and/or Claude (Stage 2). Keys live in `.env` only, never in git/chat.
- Sources: everything I asked for (Reddit, HN, arXiv, GitHub, RSS/blogs).

## Open questions
- ~~Does `reddit.py` use OAuth or only public endpoints?~~ → **Answered in Stage 0**: public `.json` only, no OAuth, generic User-Agent. With ~40 subreddits in the current `sources.json`, 429/block risk is real. Stage-1 choice: trim list + unique UA, or switch to OAuth.
- ~~OpenAI or Claude as primary provider?~~ → **Resolved in Stage 2**: neither — Azure OpenAI (Kaleidoo org), default deployment `azure/gpt-4o`. Gemini stays available-but-off (no key configured). Direct OpenAI ruled out by a 401 from the existing key.
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

## Stage 1 notes (done)
- **Persona:** All three platforms (LinkedIn, Twitter/X, Reddit) now use Yaniv's CTO-positioning persona. Canonical edit location: `prompts/linkedin_system_prompt.txt`, `prompts/twitter_system_prompt.txt`, `prompts/reddit_system_prompt.txt`. These override the `*_SYSTEM_PROMPT` constants in `src/article_writer/generation/article_generator.py` at runtime (constants marked `# Fallback only`). LinkedIn defaults to Hebrew; Twitter and Reddit default to English (community language). Reddit enforces an anti-brand rule (no mention of Yaniv/Kaleidoo).
- **Sources trimmed:** `sources.json` now populates only the `software` stream. Reddit subreddits: 5 (`MachineLearning, LocalLLaMA, artificial, claudeAI, cursor`). RSS software feeds: 20 (removed 3 quant/finance feeds + Tesla IR). Gaming and hardware streams removed across every source.
- **arxiv enabled** (`false` → `true`); feeds `cs.AI` and `cs.LG`.
- **Keywords:** 85 substring-friendly phrases anchored to LLM/RAG/agents discussions, comparisons, and provocative framings (e.g. "RAG is dead", "long context kills RAG", "you don't need RAG"). No "X just launched" style.
- **Test post deferred to Stage 2:** end-to-end generation needs a working provider key, and the `.env` has none today. The DoD in `docs/stages/stage-1.md` explicitly allows this deferral.
- Zero "Amit"/"rzailabs" strings remain under `src/` or `prompts/` (verified via `findstr /S /I /M`).
- No commit performed by Claude — Yaniv will commit manually after final review.

## Stage 3 notes (done)
- **Three features were planned: RTL + on-demand summary + Smart Rank.** Yaniv reviewed the Smart Rank feature mid-stage and chose to **de-scope it** — it would be the slowest and most expensive action in the tool, and the value gap vs. the existing source-weight + freshness ranking did not justify the cost in his current workflow. If reintroduced it will be its own stage.
- **Feature 1 — RTL (`1071c7c`):** added `dir="auto"` to dynamic-content elements in 5 templates (`article_detail`, `article_form`, `articles`, `index`, `run_detail`). Per-element auto-detection keeps the English UI chrome LTR while Hebrew posts and titles flip right-aligned. No CSS or JS change.
- **Patch (`add0d95`):** restored the test suite. `tests/conftest.py` was missing four `Settings` fields added in Stage 2 (`scheduler_enabled`, `azure_openai_api_key/endpoint/api_version`), and `test_article_generator.py` still asserted the pre-Stage-1 "Amit Raz" persona. All 15 tests green again — necessary safety net for Feature 2 onwards.
- **Feature 2 — On-demand summary (`fc2ca22`):** added per-item Summarize button on `index.html` Top 10 and on `run_detail.html` table rows. New `POST /api/trends/{id}/summarize` endpoint calls Azure with a tight 2-3 sentence prompt (`max_tokens=300`, `temperature=0.3`). New `summarize()` and `_chat()` helper on `ManualArticleGenerator` keep `generate()` untouched. No DB persistence — on-demand only, refreshed per click.
- **Cost tracking (`600054c`):** new `generation/llm_usage.py` with `LLMUsageTracker`, persists token/cost totals to `data/llm_usage.json` (atomic write + lock). gpt-4o pricing hardcoded from OpenAI list ($2.50/1M input, $10.00/1M output, treated as uncached). Both `summarize()` and `generate()` paths record usage; `generate()` stores per-call usage in `article.metadata` so the detail page can render it. New `GET /api/llm-usage` exposes cumulative totals. Drive-by fix: `article_form.html`'s LLM dropdown defaulted to the hardcoded `google/gemini-2.5-pro`; switched to `llm_options[0]` so `azure/gpt-4o` (the active provider since Stage 2) is the default.

## Stage 4 notes (in progress — all features committed, awaiting Yaniv approval)
- **Feature 1 — DB-backed keywords (`9f485de`):** new `keywords` SQLite table with `LOW/MEDIUM/HIGH` tier per keyword (weights 0.3 / 0.6 / 1.0). `init-db` and web lifespan seed from `sources.json` at MEDIUM — one-shot, never overwrites user edits. `SQLiteStore` exposes full CRUD: `list_keywords`, `list_keywords_for_matching`, `create_keyword`, `update_keyword_tier`, `delete_keyword`, `seed_keywords_if_empty`. `ranking/scorer.py` updated: `keyword_score = min(sum(matched_tier_weights), 3.0)` replaces old `hits * 0.45`. `settings.keywords` is now seed-only.
- **Feature 2 — REST API + scorer/adapter wiring (`011bee7`):** `GET/POST /api/keywords`, `PATCH/DELETE /api/keywords/{id}`, `POST /api/keywords/suggestions`. Scorer accepts `(kw, tier)` tuples; all 5 source adapters accept `keywords=` kwarg; pipeline loads from DB once per run.
- **Feature 3 — `/keywords` UI + suggestions panel (`3111076`):** table with inline tier dropdown + delete, add form, LLM suggestions panel with per-suggestion Add button, usage + cumulative cost display. Nav link added to base.html. 37/37 tests green.
- **UX fixes (post-stage-4):**
  - `display_reason` computed field: serializer extracts age + matched keyword names from `evidence_json`; templates use this instead of raw `reason_summary`. Old DB records with empty evidence fall back gracefully.
  - `_reason_summary` in scorer now stores keyword names (not a count) and drops the source-name prefix.
  - Keyword filter on run_detail uses whole-word `\b` regex — was substring, causing false positives (e.g. "rag" matching "fragmentation").
  - Summarize panel: RTL (`dir="rtl"`) + toggle open/close (second click hides; "×" button to close) + no re-fetch on re-open.

## Stage 2 notes (done)
- **Provider — Azure OpenAI, not OpenAI direct:** initial attempt against `api.openai.com` returned 401 — the Kaleidoo key is an Azure OpenAI key. Stage-2 spec was updated before any code landed. `_generate_with_azure_openai` in `article_generator.py` uses `AzureOpenAI` from the `openai` SDK with `api_key + azure_endpoint + api_version` from `.env`. Default deployment: `azure/gpt-4o`.
- **`config.py`:** `_is_supported_article_llm_option` now accepts both `google/...` and `azure/...`. `DEFAULT_ARTICLE_LLM_OPTIONS = ["azure/gpt-4o", "google/gemini-2.5-pro"]`. Three new `Settings` fields for the Azure trio. Gemini stays available-but-off (no key configured); selecting any provider without its env values raises a clear `RuntimeError`, not a 401.
- **`.env` loading micro-task:** added `python-dotenv` to `pyproject.toml` and `load_dotenv()` as the first line of `cli.main()`. The project had no env-file loader before this — `os.getenv` would have returned `None` even with `.env` populated, silently breaking the whole provider chain.
- **Scheduler off by default:** `ARTICLE_WRITER_SCHEDULER_ENABLED` (default `false`) for persistent, `--scheduler` / `--no-scheduler` on `serve` for per-invocation. Wired to `create_app(..., start_scheduler=<bool>)`. Future "turn it on" = one flag, no code change.
- **CLI convenience:** added `src/article_writer/__main__.py` so `py -m article_writer ...` works on machines where `Scripts/` is not on `PATH` (Windows default).
- **Docs:** `docs/ARCHITECTURE.md` and `CLAUDE.md` updated for Azure-default, dotenv loading, and scheduler-off-by-default.
- **Future deferral:** `azure/gpt-5.4` to be added later once the deployment name + api-version are confirmed by the org — one-line config addition, no code change.
- **Build-artifact cleanup:** `*.egg-info/` added to `.gitignore`; existing `src/article_writer.egg-info/` removed from git tracking (`git rm --cached -r`).
- **End-to-end milestone:** real LinkedIn post in Hebrew was generated via `azure/gpt-4o`, and Yaniv confirmed it sounds like him.
- No commit performed by Claude — Yaniv will commit manually after final review.
