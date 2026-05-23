# CLAUDE.md

This file provides guidance to Claude Code when working with code in this repository.

## How to work in this project

This project moves in numbered **stages**. `PROGRESS.md` is the source of truth for status.

**At the start of every chat:**
1. Pin `PROGRESS.md` plus the relevant `docs/stages/stage-0X.md`.
2. Open with: "working on Stage X".
3. Work **only** on what that stage defines. Do not touch anything outside its scope.

**At the end of a stage:**
1. Run the Definition of Done from the stage doc.
2. **Yaniv approves the stage.** Only after approval, update the status in `PROGRESS.md` to `done`.
3. **Then, as a separate question, ask Yaniv whether to commit + push.** Show `git status` and a proposed commit message *before* executing. Stage approval and git approval are two distinct approvals — never bundle them.
4. Never `--no-verify`, never amend a published commit, never force-push.

## Language rules

- All docs (`.md`), code comments, filenames, commit messages, branch names: **English**.
- Replies to Yaniv in chat: **Hebrew**.
- Do **not** change the language of the app's own output. Post generation language is controlled by the form and the persona files, not by Claude's session language.

## Personas (Stage 1 output)

The canonical persona definitions live in `prompts/`:
- `prompts/linkedin_system_prompt.txt` — default language **Hebrew**.
- `prompts/twitter_system_prompt.txt` — default language **English** (community language).
- `prompts/reddit_system_prompt.txt` — default language **English**, with an anti-brand rule (no mention of "Yaniv" / "Kaleidoo").

At runtime, `_load_prompt_file` in `src/article_writer/generation/article_generator.py` reads the `.txt` file first and only falls back to the in-code `*_SYSTEM_PROMPT` constants if the file is missing. Those constants are marked `# Fallback only`.

**To change a persona, edit the `.txt` file — not the constant.** Optional env overrides: `ARTICLE_WRITER_{LINKEDIN,TWITTER,REDDIT}_PROMPT_FILE`.

## Docs structure

- `PROGRESS.md` — stage status + decision log + open questions. **Source of truth.**
- `docs/ARCHITECTURE.md` — read-first technical map of the repo; includes gotchas.
- `docs/stages/stage-0X.md` — per-stage spec + Definition of Done.

**Before touching code, read `docs/ARCHITECTURE.md` for gotchas.**

## Commands

```bash
# Install package + dev dependencies
pip install -e ".[dev]"

# Initialize the SQLite database
py -m article_writer init-db

# Start web server (scheduler off by default; --scheduler to enable, or ARTICLE_WRITER_SCHEDULER_ENABLED=true in .env)
py -m article_writer serve

# Trigger a single pipeline run immediately
py -m article_writer run-once

# Run all tests
pytest

# Run a single test
pytest tests/path/to/test_file.py::test_function_name
```

## Architecture (short)

Local-first AI/LLM/RAG trend scouting pipeline. Three logical layers: **Ingestion → Ranking → Presentation**, plus scheduler and storage.

1. **Sources** (`src/article_writer/sources/`): `ALL_SOURCE_ADAPTERS` is a static tuple of nine adapters — **HackerNews, Reddit, GitHub, ProductHunt, RSS, Arxiv, DeepMind, Lobsters, Netlify**. Enable flags, queries, feeds, subreddits, keywords, and per-source weights live in `sources.json` at the repo root (not in `.env`). After Stage 1, only the `software` stream is populated, scoped to AI/LLM/RAG.

2. **Ranking** (`ranking/`): SHA-256 dedup on `source_name|normalized_url|slugified_title`, scored using per-source weights, filtered against recent runs. Top-N become `RankedTrend`.

3. **Generation** (`generation/`): **LLM-based** via `article_generator.py`, with per-platform persona prompts (see Personas above). Default provider is **Azure OpenAI** (`azure/gpt-4o` deployment) via `_generate_with_azure_openai`, using `AzureOpenAI` from the `openai` SDK with `api_key + azure_endpoint + api_version` from `.env`. Gemini (`google/...`) is wired and listed, but available-but-off — no key is configured. Selecting any provider without its env values raises a clear `RuntimeError`, not a 401.

4. **Web** (`web/`): FastAPI + Jinja2. Dashboard at `http://127.0.0.1:8000`.

5. **Scheduler** (`pipeline/`): APScheduler, daily at `ARTICLE_WRITER_SCHEDULE_HOUR:ARTICLE_WRITER_SCHEDULE_MINUTE`. **Off by default since Stage 2** — enable via `ARTICLE_WRITER_SCHEDULER_ENABLED=true` or `py -m article_writer serve --scheduler`. The dashboard's "Run Now" button works regardless.

### Key files

- `models.py` — dataclasses (`SourceItem`, `RankedTrend`, `DraftArtifactData`, `PipelineSnapshot`) and SQLAlchemy ORM models (`RunRecord`, `TrendRecord`, `DraftRecord`) live side by side.
- `config.py` — frozen `Settings` dataclass populated from env + `sources.json` by `get_settings()`. Non-source settings use the `ARTICLE_WRITER_` prefix.
- `storage/sqlite_store.py` — sole DB interface; owns the full run lifecycle.

### Data flow per run

```
SQLiteStore.create_run()
  → sources fetch SourceItems
  → dedup via SQLiteStore.get_recent_dedup_keys()
  → ranking produces RankedTrend list
  → generation produces DraftArtifactData list
→ SQLiteStore.save_run_results()
```

### Configuration

Copy `.env.example` to `.env` for runtime settings. `.env` is loaded automatically by `python-dotenv` at the top of `cli.main()` (Stage 2), so `os.getenv` calls in `Settings` resolve to the file's values without manual exporting. Edit `sources.json` for source enable flags, queries, feeds, keywords, and weights.
