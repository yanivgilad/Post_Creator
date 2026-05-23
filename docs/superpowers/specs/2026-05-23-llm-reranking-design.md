# LLM Re-ranking Design

**Date:** 2026-05-23  
**Status:** Approved

## Goal

Add a second ranking signal alongside the existing popularity-based score. The LLM receives all trend titles + the active keyword list and returns a relevance score (1–10) per trend. Both scores are stored and displayed in the dashboard with a toggle to sort by either.

## Approach: Automatic + On-Demand (C)

LLM ranking runs automatically at the end of every pipeline run. A "Re-rank" button in the dashboard allows re-running without a full pipeline run — useful after keyword changes.

## Components

### 1. DB Schema

Add nullable column to `TrendRecord`:

```sql
ALTER TABLE trends ADD COLUMN llm_rank_score REAL DEFAULT NULL
```

SQLAlchemy: `Column(Float, nullable=True)`. NULL = not yet ranked.

### 2. `ranking/llm_ranker.py` (new file)

Single public function:

```python
def llm_rank(
    items: list[RankedTrend],
    keywords: list[str],
    settings: Settings,
) -> dict[int, float]:
    ...
```

- Builds a numbered list of titles + source names
- Sends one LLM call (Azure gpt-4o, same provider as rest of app)
- Prompt asks for JSON `{"rankings": [{"index": 1, "score": 8.5}, ...]}`
- Returns `{item_index: score}` (1–10)
- On LLM error: logs warning, returns `{}` — pipeline does not fail

**Prompt template:**

```
You are ranking AI/tech news articles by relevance to these topics: {keywords}.

Rate each article's relevance from 1 (irrelevant) to 10 (highly relevant):
{numbered list of "N. {title} [{source}]"}

Return only JSON: {"rankings": [{"index": 1, "score": 8.5}, ...]}
```

**Token estimate:** ~800 input + ~200 output ≈ $0.003 per run at gpt-4o pricing.

### 3. `models.py`

`RankedTrend` dataclass gets new field:

```python
llm_rank_score: float | None = None
```

### 4. Pipeline (`pipeline/run_daily.py`)

After `rank_items()` returns `(top_n, all_scored)`:

1. Extract keyword strings from DB
2. Call `llm_rank(all_scored, keywords, settings)`
3. Attach scores to each `RankedTrend` in `all_scored`
4. Pass through to `save_run_results()`

### 5. `storage/sqlite_store.py`

- `save_run_results()`: persist `llm_rank_score` per trend row
- New method `update_trends_llm_rank(run_id: int, scores: dict[int, float])`: for the re-rank endpoint; updates by trend DB id
- `get_run()` already returns trend dicts — add `llm_rank_score` field

### 6. API (`web/routes/api.py`)

New endpoint:

```
POST /api/runs/{run_id}/llm-rank
```

1. Load all trends for the run from DB
2. Load active keywords
3. Call `llm_rank()`
4. Call `store.update_trends_llm_rank()`
5. Return `{"status": "ok", "ranked_count": N}`

### 7. UI

**`run_detail.html`:**
- New column `LLM Score` in the trends table (shows `—` when NULL)
- Toggle button: "Sort by Popularity / Sort by LLM"
- Button: "Re-rank with LLM" → calls `POST /api/runs/{id}/llm-rank` → page refresh

**`index.html` (Top 10):**
- Each trend card shows both scores: popularity badge + LLM badge
- Toggle to sort Top 10 list by either score

## Error Handling

- LLM call fails → `llm_rank_score` stays NULL, pipeline completes normally
- Partial JSON response → parse what's valid, leave rest NULL
- Re-rank on a run with no trends → 400 response

## Out of Scope

- Per-run LLM cost tracking for re-rank calls (existing `LLMUsageTracker` covers it automatically)
- Caching LLM rank between runs (each run is independent)
