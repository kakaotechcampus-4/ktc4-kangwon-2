from datetime import date as date_
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Document(Base):
    """일지 계열 문서 — 일일 보육일지·주간 보육일지·관찰일지·영유아 평가 (docs/api-spec.md §11).

    계획안(plans, §4~§7)과 다른 테이블이다. 계획안은 참조자료에서, 이 문서들은
    교사의 관찰 기록(observations, §10)에서 나온다.
    """

    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('dailyLog', 'weeklyLog', 'observation', 'assessment')", name="kind"
        ),
        CheckConstraint("status IN ('DRAFT', 'CONFIRMED')", name="status"),
        CheckConstraint("origin IN ('AI', 'TEACHER', 'TEMPLATE', 'IMPORT')", name="origin"),
        CheckConstraint("start_date <= end_date", name="date_range"),
        CheckConstraint("kind != 'dailyLog' OR start_date = end_date", name="daily_log_single_day"),
        CheckConstraint(
            "kind NOT IN ('observation', 'assessment') OR child_id IS NOT NULL",
            name="child_scoped_kind_requires_child",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(
        String(20),
        comment="dailyLog · weeklyLog · observation · assessment 중 하나 (docs/api-spec.md §11)",
    )
    title: Mapped[str] = mapped_column(
        String(200),
        comment="서버 생성 — '{아이 이름} {문서 종류} ({기간})'. PUT 으로 교사가 덮어쓸 수 있다",
    )
    class_id: Mapped[int] = mapped_column(ForeignKey("classes.id"), index=True)
    child_id: Mapped[int | None] = mapped_column(
        ForeignKey("children.id"), index=True, comment="dailyLog · weeklyLog 는 반 단위라 NULL"
    )
    start_date: Mapped[date_] = mapped_column(
        Date, comment="계약의 `start`. 컬럼명만 다르다 — `end` 는 SQL 예약어라 피했다"
    )
    end_date: Mapped[date_] = mapped_column(Date, comment="계약의 `end`")
    status: Mapped[str] = mapped_column(
        String(20), default="DRAFT", comment="DRAFT -> CONFIRMED. 한 방향이다. 되돌리기는 P1"
    )
    origin: Mapped[str] = mapped_column(String(20), comment="AI · TEACHER · TEMPLATE · IMPORT")
    stale: Mapped[bool] = mapped_column(
        default=False, comment="근거(observations · documents)가 수정·삭제된 뒤 아직 안 봤다"
    )
    generation_method: Mapped[str | None] = mapped_column(
        String(20), comment="예: RULE_LLM. origin 이 AI 가 아니면 NULL"
    )
    generation_rule_id: Mapped[str | None] = mapped_column(String(80))
    generation_rule_version: Mapped[str | None] = mapped_column(String(20))
    review_note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class DocumentSection(Base):
    """문서 본문 — 사실 · 해석 · 지원 셋뿐이다 (docs/api-spec.md §11 '3층 규격').

    `사실` 은 LLM 이 만지지 않고 서버가 sources 원문을 그대로 붙인다.
    """

    __tablename__ = "document_sections"
    __table_args__ = (
        CheckConstraint("heading IN ('사실', '해석', '지원')", name="heading"),
        UniqueConstraint("document_id", "heading"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), index=True)
    heading: Mapped[str] = mapped_column(String(10))
    body: Mapped[str] = mapped_column(Text)
    source_ids: Mapped[list[int]] = mapped_column(
        JSONB,
        default=list,
        comment="이 항목이 실제로 근거로 삼은 document_sources.source_id 의 부분집합",
    )


class DocumentSource(Base):
    """생성 시점 원문 사본 (docs/api-spec.md §11 'document_sources 에 원문을 복사해 둔다').

    observations 를 참조만 하면 원본이 바뀔 때 문서의 `사실` 이 조용히 같이 바뀐다.
    무효 판정(`stale`)은 여기 저장된 사본과 원본을 비교해서 정한다.

    `source_kind` · `source_id` 는 다형 참조다 — observations 나 documents(주간 보육일지가
    근거로 쓰는 확정된 일일 보육일지) 중 하나를 가리키므로 단일 FK 를 걸 수 없다.
    """

    __tablename__ = "document_sources"
    __table_args__ = (
        CheckConstraint("source_kind IN ('observation', 'document')", name="source_kind"),
        CheckConstraint(
            "source_status IS NULL OR source_status IN ('DRAFT', 'CONFIRMED')",
            name="source_status",
        ),
        UniqueConstraint("document_id", "source_kind", "source_id"),
        Index("ix_document_sources_source_kind_source_id", "source_kind", "source_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), index=True)
    source_kind: Mapped[str] = mapped_column(String(20))
    source_id: Mapped[int] = mapped_column(
        comment="observations.id 또는 documents.id. FK 없음 — 다형 참조라 걸 수 없다"
    )
    class_id: Mapped[int] = mapped_column(
        ForeignKey("classes.id"), comment="무효화 판정용 스냅샷. 렌더링엔 안 쓴다 (ADR-010 결정 1)"
    )
    child_id: Mapped[int | None] = mapped_column(ForeignKey("children.id"))
    date: Mapped[date_ | None] = mapped_column(
        Date,
        comment=(
            "근거 시점 — observation 근거면 그 기록의 date, document 근거(주간->일일)면 "
            "그 문서의 start_date (리뷰 반영: PR #50, LEEseungseok-01)"
        ),
    )
    source_status: Mapped[str | None] = mapped_column(
        String(20),
        comment=(
            "document 근거일 때 그 문서의 생성 시점 status 스냅샷(DRAFT/CONFIRMED). "
            "observation 근거면 NULL — 관찰 기록엔 status 가 없다 (리뷰 반영: PR #50)"
        ),
    )
    text: Mapped[str] = mapped_column(
        Text, comment="생성 시점 원문 복사본. 원본이 나중에 바뀌어도 이 값은 안 바뀐다"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
