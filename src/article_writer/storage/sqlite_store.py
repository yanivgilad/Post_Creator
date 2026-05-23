from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timezone
import json
from pathlib import Path

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker

from article_writer.config import Settings
from article_writer.models import ArticleArtifact, PipelineSnapshot


TIER_WEIGHTS: dict[str, float] = {"LOW": 0.3, "MEDIUM": 0.6, "HIGH": 1.0}
TIER_ORDER: dict[str, int] = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}
VALID_TIERS = frozenset(TIER_WEIGHTS.keys())


class Base(DeclarativeBase):
    pass


class PipelineRunRecord(Base):
    __tablename__ = "pipeline_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    status: Mapped[str] = mapped_column(String(32), default="queued")
    triggered_by: Mapped[str] = mapped_column(String(64), default="scheduler")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source_count: Mapped[int] = mapped_column(Integer, default=0)
    raw_item_count: Mapped[int] = mapped_column(Integer, default=0)
    unique_item_count: Mapped[int] = mapped_column(Integer, default=0)
    error_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    log_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    trends: Mapped[list[TrendRecord]] = relationship(back_populates="run", cascade="all, delete-orphan")
    drafts: Mapped[list[DraftRecord]] = relationship(back_populates="run", cascade="all, delete-orphan")


class TrendRecord(Base):
    __tablename__ = "trends"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("pipeline_runs.id"), index=True)
    source_name: Mapped[str] = mapped_column(String(64), index=True)
    stream: Mapped[str] = mapped_column(String(32), default="software", index=True)
    external_id: Mapped[str] = mapped_column(String(256))
    title: Mapped[str] = mapped_column(String(512))
    url: Mapped[str] = mapped_column(String(1024), index=True)
    summary: Mapped[str] = mapped_column(Text)
    author: Mapped[str | None] = mapped_column(String(256), nullable=True)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    engagement_score: Mapped[float] = mapped_column(Float, default=0.0)
    rank_score: Mapped[float] = mapped_column(Float, default=0.0)
    is_ranked: Mapped[bool] = mapped_column(Boolean, default=True)
    reason_summary: Mapped[str] = mapped_column(Text)
    evidence_json: Mapped[str] = mapped_column(Text, default="[]")
    supporting_urls_json: Mapped[str] = mapped_column(Text, default="[]")
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    llm_rank_score: Mapped[float | None] = mapped_column(Float, nullable=True, default=None)

    run: Mapped[PipelineRunRecord] = relationship(back_populates="trends")
    articles: Mapped[list[ArticleRecord]] = relationship(back_populates="trend", cascade="all, delete-orphan")


class DraftRecord(Base):
    __tablename__ = "drafts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("pipeline_runs.id"), index=True)
    platform: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(String(256))
    body: Mapped[str] = mapped_column(Text)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")

    run: Mapped[PipelineRunRecord] = relationship(back_populates="drafts")


class ArticleRecord(Base):
    __tablename__ = "articles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trend_id: Mapped[int] = mapped_column(ForeignKey("trends.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    language: Mapped[str] = mapped_column(String(64))
    target_outlet: Mapped[str] = mapped_column(String(255))
    llm_name: Mapped[str] = mapped_column(String(128))
    title: Mapped[str] = mapped_column(String(512))
    body: Mapped[str] = mapped_column(Text)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")

    trend: Mapped[TrendRecord] = relationship(back_populates="articles")


class KeywordRecord(Base):
    __tablename__ = "keywords"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    keyword: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    tier: Mapped[str] = mapped_column(String(8), default="MEDIUM", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class SQLiteStore:
    def __init__(self, settings: Settings):
        self._settings = settings
        self._ensure_parent_dir(settings)
        connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
        self._engine = create_engine(settings.database_url, future=True, connect_args=connect_args)
        self._session_factory = sessionmaker(bind=self._engine, future=True, expire_on_commit=False)

    def _ensure_parent_dir(self, settings: Settings) -> None:
        Path(settings.data_dir).mkdir(parents=True, exist_ok=True)

    def init_db(self) -> None:
        Base.metadata.create_all(self._engine)
        self._migrate()

    def _migrate(self) -> None:
        from sqlalchemy import inspect, text as sa_text

        run_cols = {c["name"] for c in inspect(self._engine).get_columns("pipeline_runs")}
        trend_cols = {c["name"] for c in inspect(self._engine).get_columns("trends")}
        with self._engine.begin() as conn:
            if "log_text" not in run_cols:
                conn.execute(sa_text("ALTER TABLE pipeline_runs ADD COLUMN log_text TEXT"))
            if "is_ranked" not in trend_cols:
                conn.execute(sa_text("ALTER TABLE trends ADD COLUMN is_ranked INTEGER NOT NULL DEFAULT 1"))
            if "stream" not in trend_cols:
                conn.execute(sa_text("ALTER TABLE trends ADD COLUMN stream TEXT NOT NULL DEFAULT 'software'"))
            if "llm_rank_score" not in trend_cols:
                conn.execute(sa_text("ALTER TABLE trends ADD COLUMN llm_rank_score REAL"))

    def create_run(self, triggered_by: str) -> int:
        with self.session() as session:
            run = PipelineRunRecord(
                triggered_by=triggered_by,
                status="running",
                started_at=datetime.now(timezone.utc),
            )
            session.add(run)
            session.commit()
            return run.id

    def complete_run(self, run_id: int, snapshot: PipelineSnapshot, source_count: int) -> None:
        with self.session() as session:
            run = session.get(PipelineRunRecord, run_id)
            if run is None:
                raise ValueError(f"Unknown run id: {run_id}")

            run.status = "completed"
            run.completed_at = datetime.now(timezone.utc)
            run.source_count = source_count
            run.raw_item_count = snapshot.raw_item_count
            run.unique_item_count = snapshot.unique_item_count
            run.error_text = "\n".join(snapshot.errors) if snapshot.errors else None

            ranked_keys = {r.source_item.dedup_key for r in snapshot.ranked_trends}
            items_to_save = snapshot.all_scored_items if snapshot.all_scored_items else snapshot.ranked_trends
            for trend in items_to_save:
                session.add(
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
                )

            for draft in snapshot.drafts:
                session.add(
                    DraftRecord(
                        run_id=run.id,
                        platform=draft.platform,
                        title=draft.title,
                        body=draft.body,
                        metadata_json=json.dumps(draft.metadata),
                    )
                )

            session.commit()

    def fail_run(self, run_id: int, errors: Iterable[str]) -> None:
        with self.session() as session:
            run = session.get(PipelineRunRecord, run_id)
            if run is None:
                raise ValueError(f"Unknown run id: {run_id}")
            run.status = "failed"
            run.completed_at = datetime.now(timezone.utc)
            run.error_text = "\n".join(errors)
            session.commit()

    def list_runs(self, limit: int = 20) -> list[dict[str, object]]:
        with self.session() as session:
            rows = session.scalars(
                select(PipelineRunRecord).order_by(PipelineRunRecord.created_at.desc()).limit(limit)
            ).all()
            return [self._serialize_run(row) for row in rows]

    def get_latest_run(self) -> dict[str, object] | None:
        runs = self.list_runs(limit=1)
        if not runs:
            return None
        return runs[0]

    def get_run(self, run_id: int, stream: str | None = None) -> dict[str, object] | None:
        with self.session() as session:
            row = session.get(PipelineRunRecord, run_id)
            if row is None:
                return None
            payload = self._serialize_run(row)
            all_trends = sorted(
                [self._serialize_trend(item) for item in row.trends],
                key=lambda t: t["rank_score"],
                reverse=True,
            )
            if stream is not None:
                all_trends = [t for t in all_trends if t["stream"] == stream]
            payload["trends"] = [t for t in all_trends if t["is_ranked"]]
            payload["all_scored_items"] = all_trends
            payload["drafts"] = [self._serialize_draft(item) for item in row.drafts]
            payload["articles"] = self.list_articles(run_id=run_id, stream=stream)
            payload["stream_counts"] = self._stream_counts(row.trends)
            payload["stream"] = stream
            return payload

    @staticmethod
    def _stream_counts(trends: Iterable[TrendRecord]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for trend in trends:
            if not trend.is_ranked:
                continue
            counts[trend.stream] = counts.get(trend.stream, 0) + 1
        return counts

    def list_trends(self, run_id: int | None = None, limit: int = 50) -> list[dict[str, object]]:
        with self.session() as session:
            query = select(TrendRecord).order_by(TrendRecord.rank_score.desc(), TrendRecord.published_at.desc())
            if run_id is not None:
                query = query.where(TrendRecord.run_id == run_id)
            rows = session.scalars(query.limit(limit)).all()
            return [self._serialize_trend(row) for row in rows]

    def get_trend(self, trend_id: int) -> dict[str, object] | None:
        with self.session() as session:
            row = session.get(TrendRecord, trend_id)
            if row is None:
                return None
            return self._serialize_trend(row)

    def list_drafts(self, run_id: int | None = None) -> list[dict[str, object]]:
        with self.session() as session:
            query = select(DraftRecord).order_by(DraftRecord.id.asc())
            if run_id is not None:
                query = query.where(DraftRecord.run_id == run_id)
            rows = session.scalars(query).all()
            return [self._serialize_draft(row) for row in rows]

    def create_article(self, article: ArticleArtifact) -> int:
        with self.session() as session:
            trend = session.get(TrendRecord, article.trend_id)
            if trend is None:
                raise ValueError(f"Unknown trend id: {article.trend_id}")

            record = ArticleRecord(
                trend_id=article.trend_id,
                language=article.language,
                target_outlet=article.target_outlet,
                llm_name=article.llm_name,
                title=article.title,
                body=article.body,
                metadata_json=json.dumps(article.metadata),
            )
            session.add(record)
            session.commit()
            return record.id

    def get_article(self, article_id: int) -> dict[str, object] | None:
        with self.session() as session:
            row = session.get(ArticleRecord, article_id)
            if row is None:
                return None
            return self._serialize_article(row)

    def list_articles(
        self,
        run_id: int | None = None,
        limit: int = 50,
        stream: str | None = None,
    ) -> list[dict[str, object]]:
        with self.session() as session:
            query = select(ArticleRecord).join(TrendRecord).order_by(ArticleRecord.created_at.desc()).limit(limit)
            if run_id is not None:
                query = query.where(TrendRecord.run_id == run_id)
            if stream is not None:
                query = query.where(TrendRecord.stream == stream)
            rows = session.scalars(query).all()
            return [self._serialize_article(row) for row in rows]

    def save_run_log(self, run_id: int, log_text: str) -> None:
        with Session(self._engine) as session:
            run = session.get(PipelineRunRecord, run_id)
            if run is not None:
                run.log_text = log_text
                session.commit()

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

    def session(self) -> Session:
        return self._session_factory()

    def _serialize_run(self, row: PipelineRunRecord) -> dict[str, object]:
        return {
            "id": row.id,
            "status": row.status,
            "triggered_by": row.triggered_by,
            "created_at": row.created_at,
            "started_at": row.started_at,
            "completed_at": row.completed_at,
            "source_count": row.source_count,
            "raw_item_count": row.raw_item_count,
            "unique_item_count": row.unique_item_count,
            "error_text": row.error_text,
            "log_text": row.log_text,
        }

    def _serialize_trend(self, row: TrendRecord) -> dict[str, object]:
        return {
            "id": row.id,
            "run_id": row.run_id,
            "source_name": row.source_name,
            "stream": row.stream,
            "external_id": row.external_id,
            "title": row.title,
            "url": row.url,
            "summary": row.summary,
            "author": row.author,
            "published_at": row.published_at,
            "engagement_score": row.engagement_score,
            "rank_score": row.rank_score,
            "llm_rank_score": row.llm_rank_score,
            "is_ranked": row.is_ranked,
            "reason_summary": row.reason_summary,
            "evidence": json.loads(row.evidence_json),
            "supporting_urls": json.loads(row.supporting_urls_json),
            "metadata": json.loads(row.metadata_json),
        }

    def _serialize_draft(self, row: DraftRecord) -> dict[str, object]:
        return {
            "id": row.id,
            "run_id": row.run_id,
            "platform": row.platform,
            "title": row.title,
            "body": row.body,
            "metadata": json.loads(row.metadata_json),
        }

    def list_keywords(self) -> list[dict[str, object]]:
        from sqlalchemy import case

        tier_rank = case(
            {"HIGH": 3, "MEDIUM": 2, "LOW": 1},
            value=KeywordRecord.tier,
            else_=0,
        )
        with self.session() as session:
            rows = session.scalars(
                select(KeywordRecord).order_by(tier_rank.desc(), KeywordRecord.created_at.asc())
            ).all()
            return [self._serialize_keyword(row) for row in rows]

    def list_keywords_for_matching(self) -> list[tuple[str, str]]:
        with self.session() as session:
            rows = session.scalars(select(KeywordRecord)).all()
            return [(row.keyword, row.tier) for row in rows]

    def create_keyword(self, keyword: str, tier: str = "MEDIUM") -> dict[str, object]:
        normalized = self._normalize_keyword(keyword)
        normalized_tier = self._normalize_tier(tier)
        with self.session() as session:
            existing = session.scalars(
                select(KeywordRecord).where(KeywordRecord.keyword == normalized)
            ).first()
            if existing is not None:
                raise ValueError(f"Keyword already exists: {normalized}")
            record = KeywordRecord(keyword=normalized, tier=normalized_tier)
            session.add(record)
            session.commit()
            return self._serialize_keyword(record)

    def update_keyword_tier(self, keyword_id: int, tier: str) -> dict[str, object] | None:
        normalized_tier = self._normalize_tier(tier)
        with self.session() as session:
            record = session.get(KeywordRecord, keyword_id)
            if record is None:
                return None
            record.tier = normalized_tier
            record.updated_at = datetime.now(timezone.utc)
            session.commit()
            return self._serialize_keyword(record)

    def delete_keyword(self, keyword_id: int) -> bool:
        with self.session() as session:
            record = session.get(KeywordRecord, keyword_id)
            if record is None:
                return False
            session.delete(record)
            session.commit()
            return True

    def seed_keywords_if_empty(self, seed: Iterable[str]) -> int:
        with self.session() as session:
            existing = session.scalar(select(KeywordRecord).limit(1))
            if existing is not None:
                return 0
            now = datetime.now(timezone.utc)
            inserted = 0
            seen: set[str] = set()
            for raw in seed:
                normalized = self._normalize_keyword(raw)
                if not normalized or normalized in seen:
                    continue
                seen.add(normalized)
                session.add(KeywordRecord(keyword=normalized, tier="MEDIUM", created_at=now, updated_at=now))
                inserted += 1
            session.commit()
            return inserted

    @staticmethod
    def _normalize_keyword(keyword: str) -> str:
        if not isinstance(keyword, str):
            raise ValueError("Keyword must be a string")
        trimmed = keyword.strip().lower()
        if not trimmed:
            raise ValueError("Keyword cannot be empty")
        return trimmed

    @staticmethod
    def _normalize_tier(tier: str) -> str:
        if not isinstance(tier, str):
            raise ValueError("Tier must be a string")
        normalized = tier.strip().upper()
        if normalized not in VALID_TIERS:
            raise ValueError(f"Invalid tier: {tier!r}. Expected one of {sorted(VALID_TIERS)}")
        return normalized

    def _serialize_keyword(self, row: KeywordRecord) -> dict[str, object]:
        return {
            "id": row.id,
            "keyword": row.keyword,
            "tier": row.tier,
            "weight": TIER_WEIGHTS[row.tier],
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }

    def _serialize_article(self, row: ArticleRecord) -> dict[str, object]:
        return {
            "id": row.id,
            "trend_id": row.trend_id,
            "created_at": row.created_at,
            "language": row.language,
            "target_outlet": row.target_outlet,
            "llm_name": row.llm_name,
            "title": row.title,
            "body": row.body,
            "metadata": json.loads(row.metadata_json),
            "trend": self._serialize_trend(row.trend),
        }
