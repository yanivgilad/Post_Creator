from __future__ import annotations

from typing import Protocol

from article_writer.config import Settings
from article_writer.models import DraftArtifact, RankedTrend


class DraftGenerator(Protocol):
    def generate(self, trends: list[RankedTrend], settings: Settings) -> list[DraftArtifact]:
        ...
