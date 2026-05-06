from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Form, HTTPException, Request
from fastapi.responses import RedirectResponse

from article_writer.article_options import (
    ARTICLE_LANGUAGE_OPTIONS,
    ARTICLE_PLATFORM_OPTIONS,
    normalize_article_language,
    normalize_article_platform,
)
from article_writer.web.routes.api import _background_run


router = APIRouter(include_in_schema=False)


def _latest_full_run(request: Request) -> dict | None:
    latest = request.app.state.store.get_latest_run()
    if latest is None:
        return None
    return request.app.state.store.get_run(latest["id"])


def _selected_run(request: Request, run_id: int | None) -> dict | None:
    if run_id is None:
        return _latest_full_run(request)
    return request.app.state.store.get_run(run_id)


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
            "article_count": len(recent_articles) if not latest_run else len(latest_run.get("articles", [])),
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
def trends_view(request: Request, run_id: int | None = None):
    run = _selected_run(request, run_id)
    return request.app.state.templates.TemplateResponse(
        request,
        "trends.html",
        {
            "run": run,
            "is_running": request.app.state.pipeline.is_running,
        },
    )


@router.get("/articles")
def articles_view(request: Request, run_id: int | None = None):
    run = _selected_run(request, run_id)
    articles = request.app.state.store.list_articles(run_id=run_id)
    return request.app.state.templates.TemplateResponse(
        request,
        "articles.html",
        {
            "run": run,
            "articles": articles,
            "is_running": request.app.state.pipeline.is_running,
            "message": request.query_params.get("message"),
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
def run_detail_view(request: Request, run_id: int):
    run = request.app.state.store.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return request.app.state.templates.TemplateResponse(
        request,
        "run_detail.html",
        {
            "run": run,
            "is_running": request.app.state.pipeline.is_running,
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
):
    trend = request.app.state.store.get_trend(trend_id)
    if trend is None:
        raise HTTPException(status_code=404, detail="Trend not found")

    values = {
        "language": language,
        "target_outlet": target_outlet,
        "llm_name": llm_name,
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

    article = request.app.state.article_generator.generate(
        trend,
        language=language,
        target_outlet=target_outlet,
        llm_name=llm_name,
        settings=request.app.state.settings,
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
