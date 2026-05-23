# LLM Re-ranking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a second ranking signal (LLM relevance score 1–10) alongside the existing popularity score, stored in DB and displayed in both the dashboard and run-detail view with a sort toggle and a re-rank button.

**Architecture:** A new `ranking/llm_ranker.py` module sends one LLM call with all trend titles + active keywords and returns a `{index: score}` dict. The pipeline attaches scores to `RankedTrend` items before saving. A new `POST /api/runs/{run_id}/llm-rank` endpoint enables on-demand re-ranking after keyword changes. UI adds a sort toggle and LLM score badges in both `run_detail.html` and `index.html`.

**Tech Stack:** Python 3.12, SQLAlchemy ORM, FastAPI, Jinja2, Azure OpenAI via `openai` SDK, vanilla JS

---

## File Map

| Action | File | Purpose |
|--------|------|---------|
| Modify | `src/article_writer/models.py` | Add `llm_rank_score` field to `RankedTrend` |
| Modify | `src/article_writer/storage/sqlite_store.py` | ORM column, migration, serialize, new update method |
| Create | `src/article_writer/ranking/llm_ranker.py` | Single-call LLM ranking function |
| Modify | `src/article_writer/pipeline/run_daily.py` | Attach LLM scores after `rank_items()` |
| Modify | `src/article_writer/web/routes/api.py` | New `POST /api/runs/{run_id}/llm-rank` endpoint |
| Modify | `src/article_writer/web/templates/run_detail.html` | LLM score column + sort toggle + re-rank button |
| Modify | `src/article_writer/web/templates/index.html` | LLM badge per trend + sort toggle |
| Create | `tests/test_llm_ranker.py` | Unit tests for `llm_ranker.py` |

---

## Task 1: DB — add `llm_rank_score` column

**Files:**
- Modify: `src/article_writer/storage/sqlite_store.py`

- [ ] **Step 1: Write the failing test**

In `tests/test_keywords_store.py` (or a new `tests/test_llm_rank_store.py`), add:

```python
# tests/test_llm_rank_store.py
import pytest
from article_writer.storage.sqlite_store import SQLiteStore
from tests.conftest import make_settings  # reuse existing helper


def test_llm_rank_score_column_exists(tmp_path):
    settings = make_settings(tmp_path)
    store = SQLiteStore(settings)
    store.init_db()
    from sqlalchemy import inspect
    cols = {c["name"] for c in inspect(store._engine).get_columns("trends")}
    assert "llm_rank_score" in cols


def test_llm_rank_score_defaults_to_none(tmp_path):
    """TrendRecord rows saved without llm_rank_score have NULL."""
    from article_writer.storage.sqlite_store import TrendRecord
    from sqlalchemy.orm import Session
    settings = make_settings(tmp_path)
    store = SQLiteStore(settings)
    store.init_db()
    with store.session() as session:
        run_id = store.create_run("test")
        from datetime import datetime, timezone
        row = TrendRecord(
            run_id=run_id,
            source_name="hn",
            external_id="x1",
            title="Test",
            url="https://example.com",
            summary="",
            published_at=datetime.now(timezone.utc),
            rank_score=1.0,
            reason_summary="",
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        assert row.llm_rank_score is None
```

- [ ] **Step 2: Check `make_settings` exists in conftest**

```bash
grep -n "make_settings" tests/conftest.py
```

If it doesn't exist, look for the fixture that creates a `Settings` object with a temp DB path and use that pattern instead.

- [ ] **Step 3: Run tests to verify they fail**

```bash
pytest tests/test_llm_rank_store.py -v
```

Expected: FAIL with `"llm_rank_score" not in cols` or `AttributeError`.

- [ ] **Step 4: Add `llm_rank_score` to `TrendRecord` ORM**

In `src/article_writer/storage/sqlite_store.py`, in the `TrendRecord` class after line 62 (`metadata_json`):

```python
    llm_rank_score: Mapped[float | None] = mapped_column(Float, nullable=True, default=None)
```

- [ ] **Step 5: Add migration in `_migrate()`**

In `_migrate()` in `sqlite_store.py`, after the `stream` migration block:

```python
            if "llm_rank_score" not in trend_cols:
                conn.execute(sa_text("ALTER TABLE trends ADD COLUMN llm_rank_score REAL"))
```

- [ ] **Step 6: Add `llm_rank_score` to `_serialize_trend()`**

In `_serialize_trend()`, after `"rank_score": row.rank_score,`:

```python
            "llm_rank_score": row.llm_rank_score,
```

- [ ] **Step 7: Run tests — expect pass**

```bash
pytest tests/test_llm_rank_store.py -v
```

Expected: PASS

- [ ] **Step 8: Run full test suite**

```bash
pytest
```

Expected: all existing tests still pass.

- [ ] **Step 9: Commit**

```bash
git add src/article_writer/storage/sqlite_store.py tests/test_llm_rank_store.py
git commit -m "feat: add llm_rank_score column to TrendRecord"
```

---

## Task 2: `models.py` — add field to `RankedTrend`

**Files:**
- Modify: `src/article_writer/models.py`

- [ ] **Step 1: Add field to `RankedTrend`**

`RankedTrend` uses `@dataclass(slots=True)`. Add after `supporting_urls`:

```python
@dataclass(slots=True)
class RankedTrend:
    source_item: SourceItem
    score: float
    reason_summary: str
    evidence: list[str]
    supporting_urls: list[str]
    llm_rank_score: float | None = None
```

- [ ] **Step 2: Run full suite to verify no regression**

```bash
pytest
```

Expected: all green (field has default so existing callsites unaffected).

- [ ] **Step 3: Commit**

```bash
git add src/article_writer/models.py
git commit -m "feat: add llm_rank_score field to RankedTrend"
```

---

## Task 3: `ranking/llm_ranker.py` — LLM ranking module

**Files:**
- Create: `src/article_writer/ranking/llm_ranker.py`
- Create: `tests/test_llm_ranker.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_llm_ranker.py
import json
import pytest
from unittest.mock import MagicMock, patch
from article_writer.ranking.llm_ranker import llm_rank, _build_prompt
from article_writer.models import RankedTrend, SourceItem
from datetime import datetime, timezone


def _make_trend(title: str, source: str = "hn") -> RankedTrend:
    item = SourceItem(
        source_name=source,
        external_id="x",
        title=title,
        url="https://example.com",
        summary="",
        author=None,
        published_at=datetime.now(timezone.utc),
    )
    return RankedTrend(source_item=item, score=1.0, reason_summary="", evidence=[], supporting_urls=[])


def test_build_prompt_includes_titles():
    trends = [_make_trend("RAG is dead"), _make_trend("GPT-5 launches")]
    keywords = ["RAG", "LLM", "agents"]
    prompt = _build_prompt(trends, keywords)
    assert "RAG is dead" in prompt
    assert "GPT-5 launches" in prompt
    assert "RAG, LLM, agents" in prompt


def test_build_prompt_numbered():
    trends = [_make_trend("A"), _make_trend("B"), _make_trend("C")]
    prompt = _build_prompt(trends, ["llm"])
    assert "1." in prompt
    assert "2." in prompt
    assert "3." in prompt


def test_llm_rank_returns_scores_for_all_items():
    trends = [_make_trend("RAG at scale"), _make_trend("Python update")]
    keywords = ["RAG", "LLM"]

    fake_response_json = json.dumps({
        "rankings": [{"index": 1, "score": 9.0}, {"index": 2, "score": 2.5}]
    })

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content=fake_response_json))],
        usage=MagicMock(prompt_tokens=100, completion_tokens=50),
    )

    with patch("article_writer.ranking.llm_ranker._make_azure_client", return_value=mock_client):
        from tests.conftest import make_settings
        import tempfile, pathlib
        with tempfile.TemporaryDirectory() as tmp:
            settings = make_settings(pathlib.Path(tmp))
            settings = settings.__class__(
                **{**settings.__dict__,
                   "azure_openai_api_key": "key",
                   "azure_openai_endpoint": "https://x.openai.azure.com",
                   "azure_openai_api_version": "2024-02-01"}
            )
            result = llm_rank(trends, keywords, settings, llm_name="azure/gpt-4o")

    assert result[0] == pytest.approx(9.0)
    assert result[1] == pytest.approx(2.5)


def test_llm_rank_returns_empty_on_error():
    trends = [_make_trend("Something")]
    keywords = ["LLM"]

    with patch("article_writer.ranking.llm_ranker._make_azure_client", side_effect=Exception("timeout")):
        from tests.conftest import make_settings
        import tempfile, pathlib
        with tempfile.TemporaryDirectory() as tmp:
            settings = make_settings(pathlib.Path(tmp))
            result = llm_rank(trends, keywords, settings, llm_name="azure/gpt-4o")

    assert result == {}


def test_llm_rank_empty_trends():
    from tests.conftest import make_settings
    import tempfile, pathlib
    with tempfile.TemporaryDirectory() as tmp:
        settings = make_settings(pathlib.Path(tmp))
        result = llm_rank([], ["LLM"], settings, llm_name="azure/gpt-4o")
    assert result == {}
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_llm_ranker.py -v
```

Expected: FAIL with `ModuleNotFoundError: ranking.llm_ranker`.

- [ ] **Step 3: Create `src/article_writer/ranking/llm_ranker.py`**

```python
from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from article_writer.config import Settings
    from article_writer.models import RankedTrend

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You are a relevance ranker. Given a list of AI/tech news article titles and a set of "
    "topic keywords, rate each article's relevance to those topics on a scale from 1 (irrelevant) "
    "to 10 (highly relevant). Return ONLY valid JSON — no explanation, no markdown."
)


def _build_prompt(trends: list[RankedTrend], keywords: list[str]) -> str:
    kw_line = ", ".join(keywords) if keywords else "AI, LLM, RAG"
    lines = [
        f"Topics of interest: {kw_line}",
        "",
        "Rate each article's relevance (1-10):",
    ]
    for i, trend in enumerate(trends, start=1):
        lines.append(f"{i}. {trend.source_item.title} [{trend.source_item.source_name}]")
    lines += [
        "",
        'Return only JSON: {"rankings": [{"index": 1, "score": 8.5}, ...]}',
    ]
    return "\n".join(lines)


def _make_azure_client(settings: Settings):
    from openai import AzureOpenAI
    return AzureOpenAI(
        api_key=settings.azure_openai_api_key,
        azure_endpoint=settings.azure_openai_endpoint,
        api_version=settings.azure_openai_api_version,
    )


def llm_rank(
    trends: list[RankedTrend],
    keywords: list[str],
    settings: Settings,
    llm_name: str = "azure/gpt-4o",
) -> dict[int, float]:
    """Return {0-based index: score 1-10} for each trend. Empty dict on failure."""
    if not trends:
        return {}

    if not (
        settings.azure_openai_api_key
        and settings.azure_openai_endpoint
        and settings.azure_openai_api_version
    ):
        logger.warning("llm_rank: Azure OpenAI not configured — skipping")
        return {}

    _, model_name = llm_name.split("/", 1)
    user_prompt = _build_prompt(trends, keywords)

    try:
        client = _make_azure_client(settings)
        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.0,
            max_tokens=512,
            response_format={"type": "json_object"},
        )
        raw = response.choices[0].message.content or ""
        data = json.loads(raw)
        rankings = data.get("rankings", [])
        return {int(entry["index"]) - 1: float(entry["score"]) for entry in rankings}
    except Exception as exc:
        logger.warning("llm_rank failed: %s", exc)
        return {}
```

- [ ] **Step 4: Run tests — expect pass**

```bash
pytest tests/test_llm_ranker.py -v
```

Expected: all 5 tests PASS.

- [ ] **Step 5: Run full suite**

```bash
pytest
```

Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add src/article_writer/ranking/llm_ranker.py tests/test_llm_ranker.py
git commit -m "feat: add llm_ranker module — single LLM call for keyword relevance scoring"
```

---

## Task 4: Store — `update_trends_llm_rank()` + `complete_run()` save

**Files:**
- Modify: `src/article_writer/storage/sqlite_store.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_llm_rank_store.py`:

```python
def test_update_trends_llm_rank(tmp_path):
    from datetime import datetime, timezone
    from article_writer.storage.sqlite_store import TrendRecord
    settings = make_settings(tmp_path)
    store = SQLiteStore(settings)
    store.init_db()
    run_id = store.create_run("test")

    with store.session() as session:
        row = TrendRecord(
            run_id=run_id, source_name="hn", external_id="x1",
            title="T1", url="https://a.com", summary="",
            published_at=datetime.now(timezone.utc),
            rank_score=1.0, reason_summary="",
        )
        session.add(row)
        session.commit()
        trend_id = row.id

    store.update_trends_llm_rank({trend_id: 8.5})

    trend = store.get_trend(trend_id)
    assert trend["llm_rank_score"] == pytest.approx(8.5)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_llm_rank_store.py::test_update_trends_llm_rank -v
```

Expected: FAIL with `AttributeError: 'SQLiteStore' has no attribute 'update_trends_llm_rank'`.

- [ ] **Step 3: Add `update_trends_llm_rank()` to `SQLiteStore`**

Add after `save_run_log()` in `sqlite_store.py`:

```python
    def update_trends_llm_rank(self, scores: dict[int, float]) -> None:
        """Update llm_rank_score for the given trend DB ids."""
        if not scores:
            return
        with self.session() as session:
            for trend_id, score in scores.items():
                row = session.get(TrendRecord, trend_id)
                if row is not None:
                    row.llm_rank_score = score
            session.commit()
```

- [ ] **Step 4: Run test — expect pass**

```bash
pytest tests/test_llm_rank_store.py -v
```

Expected: all PASS.

- [ ] **Step 5: Update `complete_run()` to persist `llm_rank_score`**

In `complete_run()` in `sqlite_store.py`, find the `TrendRecord(...)` constructor call and add `llm_rank_score=trend.llm_rank_score,` after `rank_score=trend.score,`:

```python
                    TrendRecord(
                        run_id=run.id,
                        source_name=trend.source_item.source_name,
                        stream=trend.source_item.stream,
                        external_id=trend.source_item.external_id,
                        title=trend.source_item.title,
                        url=trend.source_item.url,
                        summary=trend.source_item.summary,
                        author=trend.source_item.author,
                        published_at=trend.source_item.published_at,
                        engagement_score=trend.source_item.engagement_score,
                        rank_score=trend.score,
                        llm_rank_score=trend.llm_rank_score,
                        is_ranked=trend.source_item.dedup_key in ranked_keys,
                        reason_summary=trend.reason_summary,
                        evidence_json=json.dumps(trend.evidence),
                        supporting_urls_json=json.dumps(trend.supporting_urls),
                        metadata_json=json.dumps(trend.source_item.metadata),
                    )
```

- [ ] **Step 6: Run full suite**

```bash
pytest
```

Expected: all green.

- [ ] **Step 7: Commit**

```bash
git add src/article_writer/storage/sqlite_store.py tests/test_llm_rank_store.py
git commit -m "feat: store llm_rank_score in TrendRecord; add update_trends_llm_rank()"
```

---

## Task 5: Pipeline integration

**Files:**
- Modify: `src/article_writer/pipeline/run_daily.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_pipeline_llm_rank.py`:

```python
from unittest.mock import MagicMock, patch
from article_writer.pipeline.run_daily import DailyPipeline
from article_writer.models import RankedTrend, SourceItem, PipelineSnapshot
from datetime import datetime, timezone


def _make_source_item(title: str) -> SourceItem:
    return SourceItem(
        source_name="hn", external_id="x", title=title,
        url="https://example.com", summary="", author=None,
        published_at=datetime.now(timezone.utc),
    )


def test_pipeline_attaches_llm_rank_scores(tmp_path):
    from tests.conftest import make_settings
    settings = make_settings(tmp_path)

    from article_writer.storage.sqlite_store import SQLiteStore
    store = SQLiteStore(settings)
    store.init_db()

    fake_trend = RankedTrend(
        source_item=_make_source_item("RAG at scale"),
        score=5.0, reason_summary="", evidence=[], supporting_urls=[],
    )
    fake_snapshot = PipelineSnapshot(
        ranked_trends=[fake_trend],
        all_scored_items=[fake_trend],
        drafts=[], raw_item_count=1, unique_item_count=1,
    )

    mock_source = MagicMock()
    mock_source.name = "mock"
    mock_source.fetch.return_value = []

    with patch("article_writer.pipeline.run_daily.rank_items", return_value=([fake_trend], [fake_trend])):
        with patch("article_writer.pipeline.run_daily.llm_rank", return_value={0: 8.5}) as mock_llm_rank:
            pipeline = DailyPipeline(settings, store, sources=[mock_source])
            run_id = pipeline.run("test")

    mock_llm_rank.assert_called_once()
    run = store.get_run(run_id)
    assert run is not None
    all_trends = run["all_scored_items"]
    assert len(all_trends) == 1
    assert all_trends[0]["llm_rank_score"] == 8.5
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_pipeline_llm_rank.py -v
```

Expected: FAIL because `llm_rank` is not imported or called in `run_daily.py`.

- [ ] **Step 3: Update `run_daily.py`**

Add import at the top of `run_daily.py` (after the `rank_items` import):

```python
from article_writer.ranking.llm_ranker import llm_rank
```

After `ranked, all_scored = rank_items(...)` in `run()`, insert:

```python
            # LLM re-ranking: attach keyword-relevance scores (titles-only, one call)
            try:
                llm_scores = llm_rank(all_scored, keyword_strings, self.settings)
                for idx, trend in enumerate(all_scored):
                    if idx in llm_scores:
                        trend.llm_rank_score = llm_scores[idx]
            except Exception as exc:
                logger.warning("LLM re-ranking failed: %s", exc)
```

- [ ] **Step 4: Run test — expect pass**

```bash
pytest tests/test_pipeline_llm_rank.py -v
```

Expected: PASS.

- [ ] **Step 5: Run full suite**

```bash
pytest
```

Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add src/article_writer/pipeline/run_daily.py tests/test_pipeline_llm_rank.py
git commit -m "feat: attach LLM rank scores in pipeline after rank_items()"
```

---

## Task 6: API endpoint `POST /api/runs/{run_id}/llm-rank`

**Files:**
- Modify: `src/article_writer/web/routes/api.py`

- [ ] **Step 1: Find the existing summarize endpoint for reference**

```bash
grep -n "summarize" src/article_writer/web/routes/api.py | head -20
```

Note the pattern: how it fetches the trend, calls the generator, returns JSON.

- [ ] **Step 2: Write the failing test**

Create `tests/test_api_llm_rank.py`:

```python
import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch


def test_llm_rank_endpoint_returns_ok(tmp_path):
    from tests.conftest import make_settings
    settings = make_settings(tmp_path)

    from article_writer.storage.sqlite_store import SQLiteStore
    from article_writer.web.app import create_app

    store = SQLiteStore(settings)
    store.init_db()

    # Pre-seed a run with one trend via store directly
    from datetime import datetime, timezone
    from article_writer.storage.sqlite_store import TrendRecord, PipelineRunRecord
    with store.session() as session:
        run = PipelineRunRecord(status="completed", triggered_by="test",
                                started_at=datetime.now(timezone.utc))
        session.add(run)
        session.commit()
        run_id = run.id
        row = TrendRecord(
            run_id=run_id, source_name="hn", external_id="e1",
            title="LLM news", url="https://example.com", summary="",
            published_at=datetime.now(timezone.utc),
            rank_score=1.0, reason_summary="",
        )
        session.add(row)
        session.commit()

    app = create_app(settings=settings, store=store, start_scheduler=False)
    client = TestClient(app)

    with patch("article_writer.web.routes.api.llm_rank", return_value={0: 7.5}):
        response = client.post(f"/api/runs/{run_id}/llm-rank")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["ranked_count"] == 1


def test_llm_rank_endpoint_404_on_unknown_run(tmp_path):
    from tests.conftest import make_settings
    settings = make_settings(tmp_path)
    from article_writer.storage.sqlite_store import SQLiteStore
    from article_writer.web.app import create_app
    store = SQLiteStore(settings)
    store.init_db()
    app = create_app(settings=settings, store=store, start_scheduler=False)
    client = TestClient(app)
    response = client.post("/api/runs/9999/llm-rank")
    assert response.status_code == 404
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
pytest tests/test_api_llm_rank.py -v
```

Expected: FAIL with 404 or 405 (endpoint doesn't exist yet).

- [ ] **Step 4: Add endpoint to `api.py`**

First add the import at the top of `api.py` (with other ranking imports):

```python
from article_writer.ranking.llm_ranker import llm_rank
```

Then add the endpoint (near the existing summarize endpoint):

```python
@router.post("/runs/{run_id}/llm-rank")
async def llm_rank_run(run_id: int, request: Request):
    store: SQLiteStore = request.app.state.store
    settings = request.app.state.settings

    run = store.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")

    all_trends = run.get("all_scored_items") or run.get("trends") or []
    if not all_trends:
        return {"status": "ok", "ranked_count": 0}

    keyword_tuples = store.list_keywords_for_matching()
    keyword_strings = [kw for kw, _ in keyword_tuples]

    from article_writer.models import RankedTrend, SourceItem
    from datetime import datetime, timezone

    # Build lightweight RankedTrend proxies (title + source only needed by llm_ranker)
    proxies: list[RankedTrend] = []
    trend_ids: list[int] = []
    for t in all_trends:
        item = SourceItem(
            source_name=str(t.get("source_name", "")),
            external_id=str(t.get("external_id", "")),
            title=str(t.get("title", "")),
            url=str(t.get("url", "")),
            summary="",
            author=None,
            published_at=t.get("published_at") or datetime.now(timezone.utc),
        )
        proxies.append(RankedTrend(
            source_item=item, score=float(t.get("rank_score", 0)),
            reason_summary="", evidence=[], supporting_urls=[],
        ))
        trend_ids.append(int(t["id"]))

    scores_by_index = llm_rank(proxies, keyword_strings, settings)
    scores_by_db_id = {trend_ids[idx]: score for idx, score in scores_by_index.items()}
    store.update_trends_llm_rank(scores_by_db_id)

    return {"status": "ok", "ranked_count": len(scores_by_db_id)}
```

- [ ] **Step 5: Run tests — expect pass**

```bash
pytest tests/test_api_llm_rank.py -v
```

Expected: PASS.

- [ ] **Step 6: Run full suite**

```bash
pytest
```

Expected: all green.

- [ ] **Step 7: Commit**

```bash
git add src/article_writer/web/routes/api.py tests/test_api_llm_rank.py
git commit -m "feat: add POST /api/runs/{run_id}/llm-rank endpoint"
```

---

## Task 7: `run_detail.html` — LLM score column + sort toggle + re-rank button

**Files:**
- Modify: `src/article_writer/web/templates/run_detail.html`

No automated test for UI — manual verification step at the end.

- [ ] **Step 1: Add `LLM Score` column header to `items_table` macro**

In `run_detail.html`, in the `<thead>` of `items_table`, add after the `Score` column:

```html
        <th style="width:80px;">LLM Score</th>
```

- [ ] **Step 2: Add LLM score cell in table body**

In the `{% for trend in rows %}` loop, after the existing `<td>` with `rank_score`, add:

```html
          <td>
            {% if trend.llm_rank_score is not none and trend.llm_rank_score is not none %}
              <strong style="color:var(--accent);">{{ "%.1f"|format(trend.llm_rank_score) }}</strong>
            {% else %}
              <span class="muted">—</span>
            {% endif %}
          </td>
```

- [ ] **Step 3: Add sort toggle + re-rank button to the section header**

In the `<section class="card">` that shows the items table, replace the `<h3>` header block with:

```html
  <section class="card" style="margin-top:16px;">
    <div style="display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:12px;">
      <h3 style="margin:0;">
        Collected Items
        {% if run.all_scored_items %}
          <span class="muted" style="font-size:14px;font-weight:400;margin-left:8px;">{{ run.all_scored_items | length }} scored</span>
        {% endif %}
      </h3>
      <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center;">
        <span style="font-size:13px;color:var(--muted);">Sort by:</span>
        <button id="sort-popularity-btn" class="button ghost" style="font-size:12px;padding:7px 12px;" onclick="sortItems('popularity')">Popularity</button>
        <button id="sort-llm-btn" class="button ghost" style="font-size:12px;padding:7px 12px;" onclick="sortItems('llm')">LLM Relevance</button>
        <button id="llm-rank-btn" class="button secondary" style="font-size:12px;padding:7px 12px;" data-run-id="{{ run.id }}">Re-rank with LLM</button>
      </div>
    </div>
```

- [ ] **Step 4: Add JavaScript for sort + re-rank**

Inside the `<script>` block at the bottom of `run_detail.html`, add before the closing `})();`:

```javascript
  // Sort toggle
  var currentSort = 'popularity';
  function sortItems(mode) {
    currentSort = mode;
    var tables = document.querySelectorAll('table tbody');
    tables.forEach(function(tbody) {
      var rows = Array.from(tbody.querySelectorAll('tr:not(.trend-summary-row)'));
      rows.sort(function(a, b) {
        var aScore, bScore;
        if (mode === 'llm') {
          aScore = parseFloat(a.querySelector('td:nth-child(3)').textContent) || 0;
          bScore = parseFloat(b.querySelector('td:nth-child(3)').textContent) || 0;
        } else {
          aScore = parseFloat(a.querySelector('td:nth-child(2) strong').textContent) || 0;
          bScore = parseFloat(b.querySelector('td:nth-child(2) strong').textContent) || 0;
        }
        return bScore - aScore;
      });
      rows.forEach(function(row) { tbody.appendChild(row); });
    });
    document.getElementById('sort-popularity-btn').style.background = mode === 'popularity' ? 'var(--accent)' : '';
    document.getElementById('sort-popularity-btn').style.color = mode === 'popularity' ? 'white' : '';
    document.getElementById('sort-llm-btn').style.background = mode === 'llm' ? 'var(--accent)' : '';
    document.getElementById('sort-llm-btn').style.color = mode === 'llm' ? 'white' : '';
  }

  // Re-rank button
  var reRankBtn = document.getElementById('llm-rank-btn');
  if (reRankBtn) {
    reRankBtn.addEventListener('click', function() {
      var runId = reRankBtn.dataset.runId;
      var original = reRankBtn.textContent;
      reRankBtn.disabled = true;
      reRankBtn.textContent = 'Ranking...';
      fetch('/api/runs/' + runId + '/llm-rank', { method: 'POST' })
        .then(function(r) { return r.json(); })
        .then(function(data) {
          reRankBtn.textContent = 'Done (' + data.ranked_count + ' scored)';
          setTimeout(function() { window.location.reload(); }, 1200);
        })
        .catch(function(err) {
          reRankBtn.textContent = 'Error: ' + err.message;
          reRankBtn.disabled = false;
        });
    });
  }
```

- [ ] **Step 5: Manual verification**

Start the server:
```bash
py -m article_writer serve
```

Open `http://127.0.0.1:8000/runs/<latest_id>`. Verify:
- Table has "LLM Score" column
- Sort buttons appear
- "Re-rank with LLM" button is present
- Clicking "Re-rank with LLM" calls the API and reloads (scores appear as `—` until Azure is configured)

- [ ] **Step 6: Commit**

```bash
git add src/article_writer/web/templates/run_detail.html
git commit -m "feat: add LLM score column and sort/re-rank controls to run_detail"
```

---

## Task 8: `index.html` — LLM badge + sort toggle

**Files:**
- Modify: `src/article_writer/web/templates/index.html`

- [ ] **Step 1: Add LLM score badge to each trend item**

In `index.html`, inside the `{% for trend in latest_run.trends[:10] %}` loop, find:

```html
              <span>Score {{ trend.rank_score or trend.score }}</span>
```

Replace with:

```html
              <span>Popularity {{ "%.2f"|format(trend.rank_score or trend.score or 0) }}</span>
              {% if trend.llm_rank_score is not none %}
                <span style="color:var(--accent);">LLM {{ "%.1f"|format(trend.llm_rank_score) }}/10</span>
              {% endif %}
```

- [ ] **Step 2: Add sort toggle above the Top 10 list**

Find the `<div style="display:flex;justify-content:space-between;...">` header line of the "Latest Top 10 Recommendations" section and add a sort toggle inside it:

```html
    <div style="display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap;">
      <h2>Latest Top 10 Recommendations</h2>
      <div style="display:flex;gap:8px;align-items:center;">
        {% if latest_run %}
          <button id="idx-sort-pop" class="button ghost" style="font-size:12px;padding:6px 11px;" onclick="idxSort('pop')">Popularity</button>
          <button id="idx-sort-llm" class="button ghost" style="font-size:12px;padding:6px 11px;" onclick="idxSort('llm')">LLM</button>
          <a class="button secondary" href="/runs/{{ latest_run.id }}">View All Trends</a>
        {% endif %}
      </div>
    </div>
```

- [ ] **Step 3: Add sort script to `index.html`**

Before the closing `</script>` tag in `index.html`, add:

```javascript
  function idxSort(mode) {
    var list = document.querySelector('.card .list');
    if (!list) return;
    var items = Array.from(list.querySelectorAll('article.item'));
    items.sort(function(a, b) {
      function getScore(el) {
        var spans = el.querySelectorAll('.meta span');
        for (var i = 0; i < spans.length; i++) {
          var txt = spans[i].textContent;
          if (mode === 'pop' && txt.startsWith('Popularity')) return parseFloat(txt.replace('Popularity', '')) || 0;
          if (mode === 'llm' && txt.startsWith('LLM')) return parseFloat(txt.replace('LLM', '').replace('/10', '')) || 0;
        }
        return 0;
      }
      return getScore(b) - getScore(a);
    });
    items.forEach(function(el) { list.appendChild(el); });
    document.getElementById('idx-sort-pop').style.background = mode === 'pop' ? 'var(--accent)' : '';
    document.getElementById('idx-sort-pop').style.color = mode === 'pop' ? 'white' : '';
    document.getElementById('idx-sort-llm').style.background = mode === 'llm' ? 'var(--accent)' : '';
    document.getElementById('idx-sort-llm').style.color = mode === 'llm' ? 'white' : '';
  }
```

- [ ] **Step 4: Manual verification**

Open `http://127.0.0.1:8000`. Verify:
- Each trend in Top 10 shows `Popularity X.XX` and `LLM Y.Y/10` (or no LLM badge if not yet ranked)
- "Popularity" and "LLM" sort buttons appear
- Clicking "LLM" re-orders the list by LLM score

- [ ] **Step 5: Commit**

```bash
git add src/article_writer/web/templates/index.html
git commit -m "feat: add LLM score badge and sort toggle to dashboard Top 10"
```

---

## Self-Review

**Spec coverage check:**
- ✅ DB column `llm_rank_score` (Task 1)
- ✅ `llm_rank_score` on `RankedTrend` (Task 2)
- ✅ `ranking/llm_ranker.py` — token-efficient single call, titles only (Task 3)
- ✅ Store persist + update method (Task 4)
- ✅ Pipeline auto-runs LLM ranking (Task 5)
- ✅ `POST /api/runs/{run_id}/llm-rank` re-rank endpoint (Task 6)
- ✅ `run_detail.html` — LLM column + sort toggle + re-rank button (Task 7)
- ✅ `index.html` — LLM badge + sort toggle (Task 8)
- ✅ NULL shown as `—` (Tasks 7, 8)
- ✅ LLM failure → log + empty dict, pipeline does not fail (Task 3)

**Placeholder scan:** None found.

**Type consistency:**
- `llm_rank()` returns `dict[int, float]` — index-keyed in Tasks 3, 5; id-keyed in Task 6 (converted via `trend_ids[idx]`). ✅
- `update_trends_llm_rank(scores: dict[int, float])` — called with id-keyed dict in Task 6. ✅
- `RankedTrend.llm_rank_score: float | None` — set in Task 5, read in Tasks 4, 7, 8. ✅
