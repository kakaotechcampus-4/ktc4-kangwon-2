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
    """원. region 은 활동 쪽 지역 축이 미정이라 넣지 않는다."""

    __tablename__ = "centers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), comment="원 이름")
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
    teacher_id: Mapped[int | None] = mapped_column(
        comment="담임. users.id 예정. FK 와 인덱스는 인증 PR(8주차)에서"
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

    id: Mapped[int] = mapped_column(primary_key=True)
    class_id: Mapped[int] = mapped_column(ForeignKey("classes.id"), index=True)
    name: Mapped[str] = mapped_column(String(50), comment="평문 실명. ADR-004")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
