"""평가요소 자기 점검 모델. 계약은 docs/api-spec.md §12, ADR-022 결정 6·7 이다."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class EvaluationCheck(Base):
    """원·학년도·평가요소마다 남기는 체크 시각(§12 · ADR-022 결정 6·7).

    줄을 지우지 않아 지난 학년도와 10초 복원 시각을 보존한다. 누가 체크했는지는 남기지 않는다.
    """

    __tablename__ = "evaluation_checks"
    __table_args__ = (UniqueConstraint("center_id", "school_year", "element"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    center_id: Mapped[int] = mapped_column(ForeignKey("centers.id"))
    school_year: Mapped[int]
    element: Mapped[str] = mapped_column(String(20), comment="평가요소 키 — 예: 6-3-1")
    checked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), comment="☐ 에서 ☑ 로 바뀐 시각"
    )
    unchecked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        comment="NULL 이면 ☑. 값이 있으면 ☐ — 10초 안 재체크면 checked_at 을 되살린다",
    )
