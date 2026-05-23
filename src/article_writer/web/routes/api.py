from __future__ import annotations

from dataclasses import asdict
import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from pydantic import BaseModel

from article_writer.article_options import normalize_article_language, normalize_article_platform
from article_writer.config import filter_supported_article_llm_options
from article_writer.logging_setup import RunLogHandler
from article_writer.ranking.llm_ranker import llm_rank


router = APIRouter(prefix="/api", tags=["api"])
SECRET_CONFIG_FIELDS = {"gemini_api_key", "github_token", "product_hunt_token"}


class ArticleCreatePayload(BaseModel):
    trend_id: int
    language: str
    target_outlet: str
    llm_name: str
    custom_prompt: str | None = None


class SummarizePayload(BaseModel):
    language: str | None = None
    llm_name: str | None = None


class KeywordCreatePayload(BaseModel):
    keyword: str
    tier: str = "MEDIUM"


class KeywordTierPayload(BaseModel):
    tier: str


class KeywordSuggestPayload(BaseModel):
    count: int = 8
    llm_name: str | None = None


def _background_run(pipeline, app_state=None) -> None:
    lines: list[str] = []
    handler: RunLogHandler | None = None
    captured_run_id: int | None = None

    if app_state is not None:
        lines = app_state.live_log_lines
        lines.clear()
        app_state.live_run_id = None
        handler = RunLogHandler(lines)
        logging.getLogger().addHandler(handler)

    try:
        def _on_run_created(rid: int) -> None:
            if app_state is not None:
                app_state.live_run_id = rid

        captured_run_id = pipeline.run("manual", on_run_created=_on_run_created)
    except Exception:
        pass
    finally:
        if handler is not None:
            logging.getLogger().removeHandler(handler)
        if app_state is not None and captured_run_id is not None and lines:
            app_state.store.save_run_log(captured_run_id, "\n".join(lines))


def _public_settings(request: Request) -> dict:
    payload = asdict(request.app.state.settings)
    payload["article_llm_options"] = filter_supported_article_llm_options(payload.get("article_llm_options", []))
    for key in SECRET_CONFIG_FIELDS:
        if key in payload:
            payload[key] = None
    return payload


@router.get("/runs")
def list_runs(request: Request, limit: int = 20):
    return request.app.state.store.list_runs(limit=limit)


@router.get("/runs/latest")
def latest_run(request: Request):
    latest = request.app.state.store.get_latest_run()
    if latest is None:
        raise HTTPException(status_code=404, detail="No runs found")
    payload = request.app.state.store.get_run(latest["id"])
    if payload is None:
        raise HTTPException(status_code=404, detail="Latest run missing")
    return payload


@router.get("/runs/live-log")
def live_log(request: Request):
    state = request.app.state
    return {
        "is_running": state.pipeline.is_running,
        "run_id": getattr(state, "live_run_id", None),
        "lines": list(getattr(state, "live_log_lines", [])),
    }


@router.get("/runs/{run_id}")
def get_run(request: Request, run_id: int):
    payload = request.app.state.store.get_run(run_id)
    if payload is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return payload


@router.get("/trends/{trend_id}")
def get_trend(request: Request, trend_id: int):
    payload = request.app.state.store.get_trend(trend_id)
    if payload is None:
        raise HTTPException(status_code=404, detail="Trend not found")
    return payload


@router.get("/drafts/{run_id}")
def get_drafts(request: Request, run_id: int):
    run = request.app.state.store.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return run.get("drafts", [])


@router.get("/articles")
def list_articles(request: Request, run_id: int | None = None, limit: int = 50):
    return request.app.state.store.list_articles(run_id=run_id, limit=limit)


@router.get("/articles/{article_id}")
def get_article(request: Request, article_id: int):
    payload = request.app.state.store.get_article(article_id)
    if payload is None:
        raise HTTPException(status_code=404, detail="Article not found")
    return payload


@router.post("/articles")
def create_article(request: Request, payload: ArticleCreatePayload):
    trend = request.app.state.store.get_trend(payload.trend_id)
    if trend is None:
        raise HTTPException(status_code=404, detail="Trend not found")
    if payload.llm_name not in request.app.state.settings.supported_article_llm_options:
        raise HTTPException(status_code=400, detail="Choose a supported LLM target.")
    try:
        language = normalize_article_language(payload.language)
        target_outlet = normalize_article_platform(payload.target_outlet)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        article = request.app.state.article_generator.generate(
            trend,
            language=language,
            target_outlet=target_outlet,
            llm_name=payload.llm_name,
            settings=request.app.state.settings,
            custom_prompt=payload.custom_prompt,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Article generation failed: {exc}") from exc
    article_id = request.app.state.store.create_article(article)
    return request.app.state.store.get_article(article_id)


@router.post("/trends/{trend_id}/summarize")
def summarize_trend(request: Request, trend_id: int, payload: SummarizePayload):
    trend = request.app.state.store.get_trend(trend_id)
    if trend is None:
        raise HTTPException(status_code=404, detail="Trend not found")
    settings = request.app.state.settings
    supported = settings.supported_article_llm_options
    llm_name = payload.llm_name or (supported[0] if supported else "azure/gpt-4o")
    if llm_name not in supported:
        raise HTTPException(status_code=400, detail="Choose a supported LLM target.")
    try:
        language = normalize_article_language(payload.language or "Hebrew")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        summary, usage = request.app.state.article_generator.summarize(
            trend,
            language=language,
            llm_name=llm_name,
            settings=settings,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Summarization failed: {exc}") from exc
    cumulative = request.app.state.usage_tracker.get_totals()
    return {
        "summary": summary,
        "language": language,
        "llm_name": llm_name,
        "usage": usage,
        "cumulative": cumulative,
    }


@router.post("/runs/{run_id}/llm-rank")
async def llm_rank_run(run_id: int, request: Request):
    store = request.app.state.store
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


@router.get("/keywords")
def list_keywords(request: Request):
    return request.app.state.store.list_keywords()


@router.post("/keywords")
def create_keyword(request: Request, payload: KeywordCreatePayload):
    store = request.app.state.store
    try:
        return store.create_keyword(payload.keyword, payload.tier)
    except ValueError as exc:
        message = str(exc)
        status_code = 409 if "already exists" in message else 400
        raise HTTPException(status_code=status_code, detail=message) from exc


@router.patch("/keywords/{keyword_id}")
def update_keyword(request: Request, keyword_id: int, payload: KeywordTierPayload):
    store = request.app.state.store
    try:
        updated = store.update_keyword_tier(keyword_id, payload.tier)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if updated is None:
        raise HTTPException(status_code=404, detail="Keyword not found")
    return updated


@router.delete("/keywords/{keyword_id}")
def delete_keyword(request: Request, keyword_id: int):
    store = request.app.state.store
    if not store.delete_keyword(keyword_id):
        raise HTTPException(status_code=404, detail="Keyword not found")
    return {"status": "deleted", "id": keyword_id}


@router.post("/keywords/suggestions")
def suggest_keywords(request: Request, payload: KeywordSuggestPayload):
    settings = request.app.state.settings
    supported = settings.supported_article_llm_options
    llm_name = payload.llm_name or (supported[0] if supported else "azure/gpt-4o")
    if llm_name not in supported:
        raise HTTPException(status_code=400, detail="Choose a supported LLM target.")
    if payload.count < 1 or payload.count > 20:
        raise HTTPException(status_code=400, detail="`count` must be between 1 and 20.")
    store = request.app.state.store
    existing = store.list_keywords()
    latest_run = store.get_latest_run()
    recent_trends: list[dict] = []
    if latest_run is not None:
        full = store.get_run(latest_run["id"])
        if full is not None:
            recent_trends = list((full.get("trends") or [])[:10])
    try:
        suggestions, usage = request.app.state.keyword_suggester.suggest(
            existing=existing,
            recent_trends=recent_trends,
            count=payload.count,
            llm_name=llm_name,
            settings=settings,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Suggestion failed: {exc}") from exc
    cumulative = request.app.state.usage_tracker.get_totals()
    return {
        "suggestions": suggestions,
        "llm_name": llm_name,
        "usage": usage,
        "cumulative": cumulative,
    }


@router.get("/llm-usage")
def llm_usage(request: Request):
    return request.app.state.usage_tracker.get_totals()


@router.get("/config")
def get_config(request: Request):
    return _public_settings(request)


@router.post("/runs/trigger")
def trigger_run(request: Request, background_tasks: BackgroundTasks):
    if request.app.state.pipeline.is_running:
        raise HTTPException(status_code=409, detail="A pipeline run is already in progress")
    background_tasks.add_task(_background_run, request.app.state.pipeline, request.app.state)
    return {"status": "scheduled"}
