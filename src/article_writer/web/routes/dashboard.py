from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Form, HTTPException, Request
from fastapi.responses import RedirectResponse

from article_writer.article_options import (
    ARTICLE_LANGUAGE_OPTIONS,
    ARTICLE_PLATFORM_OPTIONS,
    normalize_article_language,
    normalize_article_platform,
)
from article_writer.config import STREAMS
from article_writer.web.routes.api import _background_run


router = APIRouter(include_in_schema=False)


def _normalize_stream(value: str | None) -> str | None:
    if value is None:
        return None
    candidate = value.strip().lower()
    if not candidate or candidate == "all":
        return None
    if candidate in STREAMS:
        return candidate
    return None


def _latest_full_run(request: Request, stream: str | None = None) -> dict | None:
    latest = request.app.state.store.get_latest_run()
    if latest is None:
        return None
    return request.app.state.store.get_run(latest["id"], stream=stream)


def _selected_run(request: Request, run_id: int | None, stream: str | None = None) -> dict | None:
    if run_id is None:
        return _latest_full_run(request, stream=stream)
    return request.app.state.store.get_run(run_id, stream=stream)


def _article_form_context(request: Request, trend: dict, *, error: str | None = None, values: dict | None = None) -> dict:
    settings = request.app.state.settings
    return {
        "request": request,
        "trend": trend,
        "message": request.query_params.get("message"),
        "error": error,
        "values": values or {},
        "language_options": ARTICLE_LANGUAGE_OPTIONS,
        "platform_options": ARTICLE_PLATFORM_OPTIONS,
        "default_language": ARTICLE_LANGUAGE_OPTIONS[0],
        "default_platform": "LinkedIn",
        "llm_options": settings.supported_article_llm_options,
        "is_running": request.app.state.pipeline.is_running,
    }



@router.get("/")
def dashboard_view(request: Request):
    latest_run = _latest_full_run(request)
    recent_runs = request.app.state.store.list_runs(limit=10)
    recent_articles = request.app.state.store.list_articles(limit=5)
    return request.app.state.templates.TemplateResponse(
        request,
        "index.html",
        {
            "latest_run": latest_run,
            "recent_runs": recent_runs,
            "recent_articles": recent_articles,
            "message": request.query_params.get("message"),
            "is_running": request.app.state.pipeline.is_running,
        },
    )


@router.get("/history")
def history_view(request: Request):
    return request.app.state.templates.TemplateResponse(
        request,
        "history.html",
        {
            "runs": request.app.state.store.list_runs(limit=50),
            "is_running": request.app.state.pipeline.is_running,
        },
    )


@router.get("/trends")
def trends_redirect(request: Request, run_id: int | None = None, stream: str | None = None):
    """Legacy alias — every run lives on /runs/{id}."""
    target_run_id = run_id
    if target_run_id is None:
        latest = request.app.state.store.get_latest_run()
        if latest is None:
            return RedirectResponse(url="/history", status_code=307)
        target_run_id = latest["id"]
    target = f"/runs/{target_run_id}"
    selected_stream = _normalize_stream(stream)
    if selected_stream:
        target = f"{target}?stream={selected_stream}"
    return RedirectResponse(url=target, status_code=307)


@router.get("/articles")
def articles_view(request: Request, run_id: int | None = None, stream: str | None = None):
    selected_stream = _normalize_stream(stream)
    run = _selected_run(request, run_id, stream=selected_stream)
    articles = request.app.state.store.list_articles(run_id=run_id, stream=selected_stream)
    extra_query_parts = []
    if run_id is not None:
        extra_query_parts.append(f"run_id={run_id}")
    extra_query = "&".join(extra_query_parts)
    return request.app.state.templates.TemplateResponse(
        request,
        "articles.html",
        {
            "run": run,
            "articles": articles,
            "is_running": request.app.state.pipeline.is_running,
            "message": request.query_params.get("message"),
            "streams": list(STREAMS),
            "current_stream": selected_stream,
            "stream_counts": (run or {}).get("stream_counts", {}),
            "base_url": "/articles",
            "extra_query": extra_query,
        },
    )


@router.get("/keywords")
def keywords_view(request: Request):
    settings = request.app.state.settings
    return request.app.state.templates.TemplateResponse(
        request,
        "keywords.html",
        {
            "keywords": request.app.state.store.list_keywords(),
            "llm_options": settings.supported_article_llm_options,
            "default_llm": settings.supported_article_llm_options[0]
            if settings.supported_article_llm_options
            else "azure/gpt-4o",
            "is_running": request.app.state.pipeline.is_running,
            "tiers": ["HIGH", "MEDIUM", "LOW"],
        },
    )


@router.get("/runs/live")
def run_live_view(request: Request):
    state = request.app.state
    return state.templates.TemplateResponse(
        request,
        "run_live.html",
        {
            "is_running": state.pipeline.is_running,
            "live_run_id": getattr(state, "live_run_id", None),
        },
    )


@router.get("/runs/{run_id}")
def run_detail_view(request: Request, run_id: int, stream: str | None = None):
    selected_stream = _normalize_stream(stream)
    run = request.app.state.store.get_run(run_id, stream=selected_stream)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    all_keywords = request.app.state.store.list_keywords()
    high_keywords = [kw["keyword"] for kw in all_keywords if kw["tier"] == "HIGH"]
    return request.app.state.templates.TemplateResponse(
        request,
        "run_detail.html",
        {
            "run": run,
            "is_running": request.app.state.pipeline.is_running,
            "streams": list(STREAMS),
            "current_stream": selected_stream,
            "stream_counts": run.get("stream_counts", {}),
            "high_keywords": high_keywords,
            "base_url": f"/runs/{run_id}",
            "extra_query": "",
        },
    )


@router.get("/drafts")
def drafts_redirect(request: Request, run_id: int | None = None):
    target = "/articles"
    if run_id is not None:
        target = f"/articles?run_id={run_id}"
    return RedirectResponse(url=target, status_code=307)


@router.get("/articles/new")
def article_form(request: Request, trend_id: int):
    trend = request.app.state.store.get_trend(trend_id)
    if trend is None:
        raise HTTPException(status_code=404, detail="Trend not found")
    return request.app.state.templates.TemplateResponse(
        request,
        "article_form.html",
        _article_form_context(request, trend),
    )


@router.post("/articles")
def create_article(
    request: Request,
    trend_id: int = Form(...),
    language: str = Form(...),
    target_outlet: str = Form(...),
    llm_name: str = Form(...),
    custom_prompt: str = Form(""),
):
    trend = request.app.state.store.get_trend(trend_id)
    if trend is None:
        raise HTTPException(status_code=404, detail="Trend not found")

    values = {
        "language": language,
        "target_outlet": target_outlet,
        "llm_name": llm_name,
        "custom_prompt": custom_prompt,
    }
    if llm_name not in request.app.state.settings.supported_article_llm_options:
        return request.app.state.templates.TemplateResponse(
            request,
            "article_form.html",
            _article_form_context(request, trend, error="Choose a supported LLM target.", values=values),
            status_code=400,
        )
    try:
        language = normalize_article_language(language)
        target_outlet = normalize_article_platform(target_outlet)
    except ValueError as exc:
        return request.app.state.templates.TemplateResponse(
            request,
            "article_form.html",
            _article_form_context(request, trend, error=str(exc), values=values),
            status_code=400,
        )

    try:
        article = request.app.state.article_generator.generate(
            trend,
            language=language,
            target_outlet=target_outlet,
            llm_name=llm_name,
            settings=request.app.state.settings,
            custom_prompt=custom_prompt,
        )
    except Exception as exc:
        return request.app.state.templates.TemplateResponse(
            request,
            "article_form.html",
            _article_form_context(request, trend, error=f"Article generation failed: {exc}", values=values),
            status_code=502,
        )
    article_id = request.app.state.store.create_article(article)
    return RedirectResponse(url=f"/articles/{article_id}?message=article-created", status_code=303)


@router.get("/articles/{article_id}")
def article_detail(request: Request, article_id: int):
    article = request.app.state.store.get_article(article_id)
    if article is None:
        raise HTTPException(status_code=404, detail="Article not found")
    return request.app.state.templates.TemplateResponse(
        request,
        "article_detail.html",
        {
            "article": article,
            "is_running": request.app.state.pipeline.is_running,
            "message": request.query_params.get("message"),
        },
    )


@router.post("/runs/trigger")
def trigger_run(request: Request, background_tasks: BackgroundTasks):
    if request.app.state.pipeline.is_running:
        return RedirectResponse(url="/?message=run-already-in-progress", status_code=303)
    background_tasks.add_task(_background_run, request.app.state.pipeline, request.app.state)
    return RedirectResponse(url="/runs/live", status_code=303)
