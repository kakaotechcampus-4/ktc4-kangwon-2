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
    교사의 관찰 기록(observations, §10)과 일과 기록(routines, §10-1)에서 나온다.
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
        String(20), default="DRAFT", comment="DRAFT <-> CONFIRMED. 되돌리기는 unconfirm (§11)"
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
    class_note: Mapped[str] = mapped_column(
        Text,
        default="",
        server_default="",
        comment=(
            "반 운영 특이사항 — 결석 · 부모면담 · 감염병 · 안전사고처럼 그날 반에 "
            "있었던 일. 교사가 직접 적는다. "
            "근거에서 나오지 않아 stale 판정에 들어가지 않는다"
        ),
    )
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
        # 「첨부 원문」은 증빙 등록(origin=IMPORT)만 쓴다 — 우리가 만든 문서가 아니라
        # 사실 · 해석 · 지원 3층이 없다 (api-spec §11 「증빙 등록」).
        CheckConstraint("heading IN ('사실', '해석', '지원', '첨부 원문')", name="heading"),
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


class DocumentReconfirmation(Base):
    """비교 토큰별 완료 영수증. 응답을 잃은 같은 요청의 재시도를 구분한다."""

    __tablename__ = "document_reconfirmations"
    __table_args__ = (UniqueConstraint("document_id", "review_token"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), index=True)
    review_token: Mapped[str] = mapped_column(String(64))
    request_hash: Mapped[str] = mapped_column(String(64))
    source_hash: Mapped[str] = mapped_column(String(64))
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # 뺀·바꾼 근거를 사람이 읽을 수 있게 남긴다. 사본 행은 사라지므로 여기가 유일한 흔적이다.
    resolutions: Mapped[list[dict] | None] = mapped_column(JSONB, nullable=True)


class DocumentSourceResolution(Base):
    """초안에서 사라진 근거를 **빼거나 바꾼 흔적** (`POST /documents/{id}/refresh`).

    `document_reconfirmations` 와 섞지 않는다 — 저쪽은 **확정본 재확정**의 완료 영수증이고
    토큰마다 한 줄이다. 이쪽은 확정 전 초안에서 일어난 일이라 영수증이 없고, 문서가 나중에
    확정돼도 그대로 남는다. 사본 행(`document_sources`)은 빼면 사라지므로 **여기가 유일한
    흔적이다.** 아동 실명이 담길 수 있어 `before` 는 로그나 화면에 뿌리지 않는다 (ADR-013).
    """

    __tablename__ = "document_source_resolutions"
    __table_args__ = (CheckConstraint("action IN ('drop', 'replace')", name="action"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), index=True)
    source_id: Mapped[int] = mapped_column(comment="사라진 근거. FK 없음 — 이미 지워진 행이다")
    action: Mapped[str] = mapped_column(String(10), comment="drop(화면의 '제외') · replace")
    replacement_id: Mapped[int | None] = mapped_column(comment="replace 일 때 고른 일과. FK 없음")
    before: Mapped[str] = mapped_column(Text, comment="사라지기 전 사본 원문")
    actor_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DocumentSource(Base):
    """생성 시점 원문 사본 (docs/api-spec.md §11 'document_sources 에 원문을 복사해 둔다').

    observations 를 참조만 하면 원본이 바뀔 때 문서의 `사실` 이 조용히 같이 바뀐다.
    무효 판정(`stale`)은 여기 저장된 사본과 원본을 비교해서 정한다.

    `source_kind` · `source_id` 는 다형 참조다 — observations, routine_records,
    documents(주간 보육일지가 근거로 쓰는 확정된 일일 보육일지) 중 하나를 가리키므로
    단일 FK 를 걸 수 없다.
    """

    __tablename__ = "document_sources"
    __table_args__ = (
        CheckConstraint(
            "source_kind IN ('observation', 'document', 'routine')", name="source_kind"
        ),
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
