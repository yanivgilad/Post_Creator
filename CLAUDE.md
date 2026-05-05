# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install package + dev dependencies
pip install -e ".[dev]"

# Initialize the SQLite database
article-writer init-db

# Start web server + background scheduler
article-writer serve

# Trigger a single pipeline run immediately
article-writer run-once

# Run all tests
pytest

# Run a single test
pytest tests/path/to/test_file.py::test_function_name
```

## Architecture

Local-first AI trend scouting pipeline with three logical layers: **Ingestion → Ranking → Presentation**.

1. **Sources** (`sources/`): Each source (HackerNews, Reddit, GitHub, Product Hunt, RSS) fetches `SourceItem` dataclasses covering the last `ARTICLE_WRITER_SINCE_HOURS` hours. Sources are individually togglable via env vars.

2. **Ranking** (`ranking/`): Items are deduplicated by SHA-256 of `source_name|normalized_url|slugified_title` (see `SourceItem.dedup_key()`), scored using per-source weights (`ARTICLE_WRITER_SOURCE_WEIGHTS`), and filtered against recent runs within `ARTICLE_WRITER_DEDUP_DAYS` days. Top-N become `RankedTrend` dataclasses.

3. **Generation** (`generation/`): Produces `DraftArtifactData` (platform-specific content) from ranked trends. Currently template-based; designed for an LLM provider to slot in behind the existing interface.

4. **Web** (`web/`): FastAPI app with Jinja2 templates (`web/routes/`, `web/templates/`). Serves the dashboard at `http://127.0.0.1:8000`.

5. **Scheduler** (`pipeline/`): APScheduler triggers the full pipeline daily at `ARTICLE_WRITER_SCHEDULE_HOUR:ARTICLE_WRITER_SCHEDULE_MINUTE`.

### Key files

- `models.py`: Dataclasses (`SourceItem`, `RankedTrend`, `DraftArtifactData`, `PipelineSnapshot`) **and** SQLAlchemy ORM models (`RunRecord`, `TrendRecord`, `DraftRecord`) are defined together here.
- `config.py`: Frozen `Settings` dataclass populated from env vars by `get_settings()` (LRU-cached). All vars use the `ARTICLE_WRITER_` prefix — see `.env.example` for the full list.
- `storage/sqlite_store.py`: `SQLiteStore` is the sole DB interface. It auto-creates the `data/` directory from the `DATABASE_URL` path and owns the full run lifecycle: `create_run()` → `save_run_results()` / `fail_run()`, plus dedup key and dashboard read queries.

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

All settings come from environment variables (no config files). Copy `.env.example` to `.env` and source it before running. `get_settings()` is cached for the process lifetime — restart to pick up env changes.

Product Hunt ingestion is off by default and only activates when `ARTICLE_WRITER_PRODUCT_HUNT_TOKEN` is set.
