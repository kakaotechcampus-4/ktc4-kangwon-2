from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Center(Base):
    """원. 계획안 결재란과 지역 연계 활동에 쓰는 값을 든다."""

    __tablename__ = "centers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), comment="원 이름")
    director_name: Mapped[str] = mapped_column(
        String(50), comment="결재란 「원장」. 계획안에 인쇄된다 (docs/PRD.md S1)"
    )
    region_sido: Mapped[str] = mapped_column(
        String(30), comment="시·도. 화면이 2단으로 받는다 (docs/PRD.md S1)"
    )
    region_sigungu: Mapped[str] = mapped_column(
        String(30), comment="시·군·구. 지역사회 연계 활동 선별에 쓴다"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Class(Base):
    """반. 학년도마다 새 행이다 — 2026 씨앗반과 2027 씨앗반은 다른 반이다.

    담임·연령대가 해마다 바뀌므로 행을 재사용하면 작년 값이 덮어써진다.
    plans 는 여기 값을 생성 시점에 스냅샷한다 (ADR-010).
    """

    __tablename__ = "classes"
    __table_args__ = (
        UniqueConstraint("center_id", "name", "school_year"),
        CheckConstraint("age_min <= age_max", name="age_range"),
        CheckConstraint("age_min BETWEEN 3 AND 5", name="age_min_range"),
        CheckConstraint("age_max BETWEEN 3 AND 5", name="age_max_range"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    center_id: Mapped[int] = mapped_column(ForeignKey("centers.id"))
    name: Mapped[str] = mapped_column(String(50), comment="반 이름")
    school_year: Mapped[int] = mapped_column(comment="학년도. 3월 시작 — 2026 은 2026-03~2027-02")
    age_min: Mapped[int] = mapped_column(comment="반 최저 연령. 학년도 기준 연 나이")
    age_max: Mapped[int] = mapped_column(comment="단일 연령반은 age_min 과 같은 값")
    teacher_name: Mapped[str] = mapped_column(
        String(50),
        comment="담임 이름. 계획안에 인쇄된다. teacher_id 와 다르다 (ADR-010 결과)",
    )
    child_count: Mapped[int | None] = mapped_column(
        comment="현재 원아 수. 선택. 아동 명단 입력 진행률에 쓴다 (docs/PRD.md S2)"
    )
    teacher_id: Mapped[int | None] = mapped_column(
        comment="담임 계정. users.id 예정. FK 와 인덱스는 인증 PR(8주차)에서"
    )
    consent_confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        comment="동의 확인 시각. 아동 0명이면 아동 수로 복원할 수 없다 (docs/PRD.md S2)",
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Child(Base):
    """아동. 실명을 평문 저장한다 (ADR-004).

    개발 DB 에 실제 아동 실명을 넣지 않는다. 테스트는 가명으로 (ADR-004:77).
    """

    __tablename__ = "children"
    __table_args__ = (UniqueConstraint("class_id", "code"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    class_id: Mapped[int] = mapped_column(ForeignKey("classes.id"), index=True)
    name: Mapped[str] = mapped_column(String(50), comment="평문 실명. ADR-004")
    code: Mapped[str] = mapped_column(
        String(20),
        comment="LLM 에 나가는 가명. 받침 있는 더미 한글 이름 (ADR-004). 반 안에서 유일하다",
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
