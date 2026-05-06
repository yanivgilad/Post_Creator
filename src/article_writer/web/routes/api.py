from __future__ import annotations

from dataclasses import asdict
import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from pydantic import BaseModel

from article_writer.article_options import normalize_article_language, normalize_article_platform
from article_writer.config import filter_supported_article_llm_options
from article_writer.logging_setup import RunLogHandler


router = APIRouter(prefix="/api", tags=["api"])
SECRET_CONFIG_FIELDS = {"gemini_api_key", "github_token", "product_hunt_token"}


class ArticleCreatePayload(BaseModel):
    trend_id: int
    language: str
    target_outlet: str
    llm_name: str


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
    article = request.app.state.article_generator.generate(
        trend,
        language=language,
        target_outlet=target_outlet,
        llm_name=payload.llm_name,
        settings=request.app.state.settings,
    )
    article_id = request.app.state.store.create_article(article)
    return request.app.state.store.get_article(article_id)


@router.get("/config")
def get_config(request: Request):
    return _public_settings(request)


@router.post("/runs/trigger")
def trigger_run(request: Request, background_tasks: BackgroundTasks):
    if request.app.state.pipeline.is_running:
        raise HTTPException(status_code=409, detail="A pipeline run is already in progress")
    background_tasks.add_task(_background_run, request.app.state.pipeline, request.app.state)
    return {"status": "scheduled"}
