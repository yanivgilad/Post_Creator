from __future__ import annotations

import logging

from apscheduler.schedulers.background import BackgroundScheduler

from article_writer.config import Settings
from article_writer.pipeline.run_daily import DailyPipeline


logger = logging.getLogger(__name__)


class SchedulerService:
    def __init__(self, settings: Settings, pipeline: DailyPipeline) -> None:
        self.settings = settings
        self.pipeline = pipeline
        self.scheduler = BackgroundScheduler(timezone="UTC")
        self._started = False

    def start(self) -> None:
        if self._started:
            return
        self.scheduler.add_job(
            self._safe_run,
            trigger="cron",
            id="daily-ai-trends-run",
            replace_existing=True,
            hour=self.settings.schedule_hour,
            minute=self.settings.schedule_minute,
        )
        self.scheduler.start()
        self._started = True

    def shutdown(self) -> None:
        if not self._started:
            return
        self.scheduler.shutdown(wait=False)
        self._started = False

    def _safe_run(self) -> None:
        try:
            self.pipeline.run("scheduler")
        except Exception:
            logger.exception("Scheduled daily run failed")
