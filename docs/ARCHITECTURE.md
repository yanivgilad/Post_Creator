# ARCHITECTURE — Short Fork Mapping

Read-first doc, written as part of Stage 0. Three logical layers: **Ingestion → Ranking → Presentation**, plus scheduler and storage.

---

## 1. Sources (`src/article_writer/sources/`)

### How a source is registered and called
- `base.py` defines `SourceAdapter` (ABC) with `enabled(settings)` and `fetch(since, settings) -> list[SourceItem]`, plus shared helpers: `_get_text`, `_get_json`, `_post_json` (all via `urllib`, `timeout=20s`, fixed User-Agent `article-writer/0.1 (+http://localhost)`), `parse_datetime`, `strip_html`, `truncate_text` (320 chars), `matches_keywords` (keyword filtering against the list in `sources.json`).
- `__init__.py` holds `ALL_SOURCE_ADAPTERS` — a static tuple of every adapter: HackerNews, Reddit, GitHub, ProductHunt, RSS, Arxiv, DeepMind, Lobsters, Netlify. `build_enabled_sources(settings)` instantiates each one and filters by `enabled(...)`. There is no dynamic discovery — adding a source requires editing this tuple.
- `rss.py` is the most generic adapter: takes a list of feeds per "stream", fetches XML, parses with `iter_xml_entries`, and builds a `SourceItem` per entry with `engagement_score=1.0` (no real signal). A single-feed failure is logged as a warning and the loop continues.

### Reddit — answer to the open question in PROGRESS
- `reddit.py` uses **only the public endpoint** `https://www.reddit.com/r/{subreddit}/new.json?limit=25`. **No OAuth**, no `oauth.reddit.com`, no `client_id/secret`, no `Authorization` header.
- The User-Agent is the generic base UA (`article-writer/0.1 (+http://localhost)`) — exactly the kind of UA Reddit actively rate-limits in practice. Reddit's default for unidentified UAs: very low rate-limit (≈10 req/min), occasionally an outright `429`/`403`.
- No retry, no backoff, no `Retry-After` handling. A subreddit failure is logged as a warning, then the loop continues.
- The current `sources.json` lists ~40 subreddits across `software/gaming/hardware`. A full run is ~40 sequential requests — close to the ceiling for an anonymous UA.
- **For personal use**: this works reliably only if we trim the subreddit list and swap the UA for a unique string, or move to OAuth (script app, free, allowed for non-commercial use).

---

## 2. Configuration (`config.py` + `.env.example`)

- `Settings` is a `@dataclass(frozen=True)`, built by `get_settings()` which is wrapped in `lru_cache` — **loaded once per process lifetime**. Changing `.env` or `sources.json` requires a restart.
- Sources, keywords, queries, feeds, subreddits, weights — all live in `sources.json` at the repo root, **not in `.env`**. `.env` covers runtime only (host/port/DB/scheduler/keys).
- Required `.env` values for a minimal run: **none**. Every setting has a default. The DB defaults to `data/article_writer.db`.
- Optional but meaningful: `ARTICLE_WRITER_AZURE_OPENAI_API_KEY` + `_ENDPOINT` + `_API_VERSION` (the active provider for post generation — default deployment `azure/gpt-4o`; loaded automatically from `.env` by `python-dotenv` in `cli.main()`), `ARTICLE_WRITER_GEMINI_API_KEY` (Gemini available-but-off — pick a `google/...` model in the form to use it), `ARTICLE_WRITER_SCHEDULER_ENABLED` (default `false`; see Section 3), `ARTICLE_WRITER_GITHUB_TOKEN` (raises GitHub's API ceiling), `ARTICLE_WRITER_PRODUCT_HUNT_TOKEN` (only if enabling that source — off by default), `ARTICLE_WRITER_LINKEDIN_PROMPT_FILE` (override `prompts/linkedin_system_prompt.txt`).
- `STREAMS = ("software", "gaming", "hardware")` — a fixed three-stream model. Each item is stored with its `stream` so the dashboard can filter. For a personal AI-only setup, `gaming` and `hardware` are noise.

---

## 3. Pipeline and Scheduler

- `pipeline/run_daily.py` → `DailyPipeline.run(triggered_by)`:
  1. `Lock` to prevent concurrent runs (`is_running`).
  2. `store.create_run(triggered_by)` → returns `run_id` (status `running`).
  3. Loops over every adapter: `source.fetch(since=now-since_hours, settings)`. A single failure = warning + continue; errors are accumulated in `errors`.
  4. `rank_items(all_items, settings)` (in `ranking/scorer.py`) returns `ranked` and `all_scored`.
  5. `store.complete_run(run_id, snapshot, source_count)` — persists everything. On exception: `store.fail_run(run_id, errors)` + `raise`.
- `pipeline/scheduler.py` → `SchedulerService` wraps APScheduler's `BackgroundScheduler` in UTC. Daily `cron` at `schedule_hour:schedule_minute`. `_safe_run` swallows exceptions and logs them.
- `serve` can start the scheduler, but **off by default since Stage 2**. Priority: CLI flag → env → `False`. `--scheduler` / `--no-scheduler` on `serve` overrides `ARTICLE_WRITER_SCHEDULER_ENABLED`, which itself defaults to `false`. The CLI passes the resolved bool to `create_app(..., start_scheduler=<bool>)` in `web/app.py`.

---

## 4. Storage (`storage/sqlite_store.py`)

Tables (SQLAlchemy ORM):
- `pipeline_runs` — id, status, triggered_by, created/started/completed_at, source_count, raw/unique_item_count, error_text, log_text.
- `trends` — every item ingested (not just the top-N): run_id, source_name, stream, external_id, title, url, summary, author, published_at, engagement_score, rank_score, **is_ranked** (whether the item made the top-N), reason_summary, evidence_json, supporting_urls_json, metadata_json.
- `drafts` — table exists but **is empty in practice** under the current flow. `complete_run` persists `snapshot.drafts` which is always `[]` in `DailyPipeline.run` (see `run_daily.py:65` — `drafts=[]`).
- `articles` — the real "create post" output: trend_id, language, target_outlet, llm_name, title, body, metadata_json.

Run flow: `create_run` (running) → only log activity during the run → `complete_run` (writes every trend in one batch, status `completed`) or `fail_run` (`failed`). There is also a lightweight `_migrate()` that adds missing columns (`log_text`, `is_ranked`, `stream`) without Alembic.

---

## 5. Web Layer — The Actual Path

### Routes
- `dashboard.py` — HTML pages (Jinja2). `api.py` — JSON under `/api`. Both pull `store`, `pipeline`, and `article_generator` from `app.state`, populated by `web/app.py` (`lifespan`).
- `POST /runs/trigger` (UI) → `_background_run` as a FastAPI BackgroundTask. Streams a live log into `app.state.live_log_lines` (in-memory ring), and at the end persists it via `save_run_log`.

### Practical flow: feed → open → post → draft

| Step | URL | Template | What's there |
|---|---|---|---|
| Short feed | `/` | `index.html` | KPIs + "Latest Top 10 Recommendations" (title + external URL + `reason_summary` + "Create Article"). |
| Full feed for a run | `/runs/{id}` | `run_detail.html` | A table of **all** scored items, grouped into source tabs. Title links to the original URL; `summary` is truncated to 160 chars in the table. No internal "item detail" page. |
| Article-creation form | `/articles/new?trend_id=X` | `article_form.html` | Language dropdown (Hebrew/English), platform dropdown (Twitter/LinkedIn/Reddit/Hashnode), LLM dropdown, `custom_prompt` textarea. |
| Output | `/articles/{id}` | `article_detail.html` | Title + meta + body inside `<pre>`, Copy button (clipboard API + fallback). "Create Another Version" sends you back to the form with the same trend. |
| Article index | `/articles` | `articles.html` | List of every article (filterable by stream/run_id). |

### Current support for the features I asked for

| Feature | Status |
|---|---|
| **Short summary in feed** | ✅ Yes — `reason_summary` in `index.html`, and 160 chars of `summary` in `run_detail`. |
| **Full item summary** | ❌ No internal item-detail page. The DB stores `summary` (up to 320 chars from the source) and `reason_summary`. Article body is never fetched. |
| **Language toggle** | ⚠️ Only on the creation form (dropdown). Once a post exists there is no toggle; you have to use "Create Another Version". |
| **Notes (`custom_prompt`)** | ✅ Yes — `textarea` on the form; saved into `article.metadata.custom_prompt` and rendered on `article_detail.html`. |
| **Manual editing of the post** | ❌ No. `body` is rendered inside `<pre>` only; there is no editable field. |
| **Copy button** | ✅ Yes — `article_detail.html`, JS with the Clipboard API and an `execCommand` fallback. |

---

## Gaps vs My Requirements (Yaniv)

**Personal persona** — ✅ **closed in Stage 1.**
- All three personas (`LinkedIn`, `Twitter/X`, `Reddit`) are now Yaniv Gilad: senior tech leader / AI architect, CTO-positioning voice. LinkedIn defaults to Hebrew; Twitter and Reddit default to English (community language). Reddit explicitly forbids any mention of "Yaniv" or "Kaleidoo" per the anti-brand rule.
- **Where personas live (canonical edit location): `prompts/linkedin_system_prompt.txt`, `prompts/twitter_system_prompt.txt`, `prompts/reddit_system_prompt.txt`.** At runtime, `_load_prompt_file` in `article_generator.py` reads each file first and only falls back to the `*_SYSTEM_PROMPT` constant in code if the file is missing. The constants carry a `# Fallback only` comment for this reason. **To edit a persona in the future, edit the `.txt` file, not the constant.** Optional env overrides: `ARTICLE_WRITER_{LINKEDIN,TWITTER,REDDIT}_PROMPT_FILE`.
- Default UI language is `language_options[0]` = `Hebrew`, which matches the LinkedIn default. Twitter and Reddit prompts honor whatever language the form passes (default English).

**Narrower sources for my domains** — ✅ **closed in Stage 1.**
- `sources.json` now populates only the `software` stream. The `gaming` and `hardware` blocks were removed from every source (the code's `STREAMS = ("software","gaming","hardware")` tuple is untouched per Stage 1's "JSON only" rule; the unused streams simply resolve to empty lists at runtime).
- `arxiv.enabled` flipped `false` → `true`. Feeds: `cs.AI`, `cs.LG`.
- Reddit subreddits trimmed from ~40 (across three streams) to 5: `MachineLearning, LocalLLaMA, artificial, claudeAI, cursor`.
- RSS software feeds trimmed from 24 to 20 (removed three quant/finance feeds and the Tesla IR feed).
- Keywords list rewritten end-to-end: 85 substring-friendly phrases anchored to LLM/RAG/agents discussions, comparisons, and provocative framings (e.g. "RAG is dead", "long context kills RAG", "you don't need RAG"). No "X just launched" style.
- Out of Stage-1 scope: the generic User-Agent on Reddit is unchanged. With 5 subreddits the 429 risk is lower but not zero. Tracked for a future stage.

**Provider for post generation** — ✅ **closed in Stage 2.**
- Active provider is **Azure OpenAI** (Kaleidoo org), NOT direct OpenAI. `_generate_with_azure_openai` in `article_generator.py` uses `from openai import AzureOpenAI` with `api_key + azure_endpoint + api_version` from `.env`. The deployment name is the part after `azure/` in the model id; default is `azure/gpt-4o`.
- `filter_supported_article_llm_options` now accepts both `google/...` and `azure/...`. `DEFAULT_ARTICLE_LLM_OPTIONS = ["azure/gpt-4o", "google/gemini-2.5-pro"]`.
- Gemini is available-but-off — no key configured. Missing-config raises a clear `RuntimeError` (`"Azure OpenAI is not configured — set ARTICLE_WRITER_AZURE_OPENAI_* in .env"`), not a 401 stack trace.
- `.env` is loaded by `load_dotenv()` at the top of `cli.main()` (Stage 2 added `python-dotenv` to `pyproject.toml`). Before this, `os.getenv(...)` returned `None` even with a populated `.env`.
- Stage-1 "test post" requirement satisfied: a real LinkedIn post in Hebrew was generated end-to-end via `azure/gpt-4o`.

**Full read+post flow** — ❌ **still open (Stage 3).**
- Missing a "full item summary" view for opening a feed item. Right now "open" = clicking the title which pops out to an external tab. Without an internal read step, `custom_prompt` is written based only on title + short summary.
- Missing manual editing of the post after creation. Only `Copy` + "Create Another Version". This is the central gap for Stage 3.
- Missing a language toggle on an existing post — need a decision: is this "create another post in English" (already exists) or "translate this post" (does not exist)?
- No `regenerate with the same custom_prompt + new notes` flow — you have to copy `custom_prompt` by hand into a new form.

---

## Local Run — Steps (no code changes)

1. `python -m venv .venv` and activate it (PowerShell: `.\.venv\Scripts\Activate.ps1`).
2. `pip install -e ".[dev]"` — pulls `openai` and `python-dotenv` in Stage 2.
3. `copy .env.example .env` — fill `ARTICLE_WRITER_AZURE_OPENAI_API_KEY` + `_ENDPOINT` + `_API_VERSION` if you want to generate posts (Azure values, not direct OpenAI). Keys never go into chat or git.
4. `py -m article_writer init-db` — creates `data/article_writer.db` and the directory. (`article-writer.exe` works too if `Scripts/` is on `PATH`; on Windows defaults it usually isn't.)
5. Option A — one-off pipeline run with no server: `py -m article_writer run-once`. Logs to console, prints `Completed run N` at the end.
6. Option B — local website: `py -m article_writer serve` → open `http://127.0.0.1:8000`. **Scheduler is off by default since Stage 2**; pass `--scheduler` (or set `ARTICLE_WRITER_SCHEDULER_ENABLED=true` in `.env`) to enable the daily cron. The dashboard's "Run Now" button always triggers a manual run regardless.
7. Stage-0 Definition of Done: `init-db` and `run-once` run without exceptions, and `http://127.0.0.1:8000` shows a feed with real items.

---

## Open Notes From the Mapping

- Every source shares the same generic User-Agent. For Reddit and GitHub this is a real 429 risk. Out of Stage-1 scope, tracked for a future stage.
- The `drafts` table exists but `DailyPipeline` always feeds it `drafts=[]`. The name is misleading: the real output is `articles`, and the UI already redirects `/drafts` → `/articles`.
