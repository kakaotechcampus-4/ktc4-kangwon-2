from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Activity(Base):
    """활동 풀. 규칙 엔진의 선별 층이 읽는다 (ADR-005).

    리스트 컬럼은 in-place 변경이 저장되지 않는다. 항상 재할당한다.
    """

    __tablename__ = "activities"
    __table_args__ = (
        CheckConstraint("age_min <= age_max", name="age_range"),
        CheckConstraint("age_min BETWEEN 3 AND 5", name="age_min_range"),
        CheckConstraint("age_max BETWEEN 3 AND 5", name="age_max_range"),
        Index("ix_activities_tags", "tags", postgresql_using="gin"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(
        String(80), unique=True, comment="불변 슬러그. YAML 최상위 키. 한 번 정하면 고치지 않는다"
    )
    title: Mapped[str] = mapped_column(String(200))
    age_min: Mapped[int] = mapped_column(comment="학년도 기준 연 나이(3·4·5). 만 나이 아님")
    age_max: Mapped[int] = mapped_column(comment="학년도 기준 연 나이(3·4·5). 만 나이 아님")
    safety_flags: Mapped[list[str]] = mapped_column(
        JSONB, default=list, comment="resources/rules/safety_flags.yaml 의 값. 선별 3순위"
    )
    tags: Mapped[list[str]] = mapped_column(
        JSONB, default=list, comment="5영역 태그·주제 태그. ADR-001:19"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
