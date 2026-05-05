from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path

from article_writer.config import Settings


def setup_logging(settings: Settings) -> None:
    log_dir = Path(settings.log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(name)s %(levelname)s %(message)s")
    file_handler = logging.handlers.RotatingFileHandler(
        log_dir / "article_writer.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(fmt)
    root = logging.getLogger()
    root.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))
    root.addHandler(file_handler)


class RunLogHandler(logging.Handler):
    """Captures article_writer.* log records into a list for live display."""

    def __init__(self, lines: list[str]) -> None:
        super().__init__()
        self._lines = lines
        self.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))

    def emit(self, record: logging.LogRecord) -> None:
        if not record.name.startswith("article_writer"):
            return
        try:
            self._lines.append(self.format(record))
        except Exception:
            self.handleError(record)
