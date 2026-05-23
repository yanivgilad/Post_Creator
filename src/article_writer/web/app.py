from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, status
from fastapi.templating import Jinja2Templates

from article_writer.config import Settings, get_settings
from article_writer.generation.article_generator import ManualArticleGenerator
from article_writer.generation.llm_usage import LLMUsageTracker
from article_writer.pipeline.run_daily import DailyPipeline
from article_writer.pipeline.scheduler import SchedulerService
from article_writer.storage.sqlite_store import SQLiteStore
from article_writer.web.routes import api, dashboard


TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"


def create_app(settings: Settings | None = None, *, start_scheduler: bool = True) -> FastAPI:
    resolved_settings = settings or get_settings()
    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        store = SQLiteStore(resolved_settings)
        store.init_db()
        store.seed_keywords_if_empty(resolved_settings.keywords)
        pipeline = DailyPipeline(resolved_settings, store)
        scheduler = SchedulerService(resolved_settings, pipeline)
        usage_tracker = LLMUsageTracker(resolved_settings.data_dir / "llm_usage.json")
        article_generator = ManualArticleGenerator(usage_tracker=usage_tracker)

        app.state.settings = resolved_settings
        app.state.store = store
        app.state.pipeline = pipeline
        app.state.scheduler = scheduler
        app.state.article_generator = article_generator
        app.state.usage_tracker = usage_tracker
        app.state.templates = templates
        app.state.live_log_lines: list[str] = []
        app.state.live_run_id: int | None = None

        if start_scheduler:
            scheduler.start()

        yield

        if start_scheduler:
            scheduler.shutdown()

    app = FastAPI(title="AI Trends Scout", lifespan=lifespan)

    @app.get("/health", tags=["api"], status_code=status.HTTP_200_OK)
    def health_check():
        return {"status": "ok"}

    app.include_router(dashboard.router)
    app.include_router(api.router)
    return app
