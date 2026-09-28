"""계획안 테이블. 연간·월간이 한 테이블을 쓴다.

**본문을 행으로 펼치지 않는다.** `YearlyPlan` 은 12개월 × (테마 · 근거 · 생성이력 ·
감사기록)이고 `MonthlyPlan` 은 43칸이다. 이걸 테이블로 펼치면 p0-planning 이 칸을
하나 더할 때마다 마이그레이션이 따라붙는다. 도메인이 아직 매주 바뀌는 중이다.

그래서 `body` JSONB 하나에 통째로 넣고, **조회에 쓰는 값만 칸으로 꺼낸다.**
꺼낸 칸은 항상 `body` 에서 유도한다 — 따로 받으면 둘이 어긋난다.

펼칠 시점은 「칸 하나만 SQL 로 고쳐야 할 때」다. 지금은 교사 한 명이 자기 계획안을
읽고-고치고-통째로 쓴다. 동시에 같은 계획안을 고치는 사람이 없다.
"""

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

KINDS = ("annual", "monthly")
STATUSES = ("DRAFT", "CONFIRMED")


class Plan(Base):
    """연간 또는 월간 계획안 하나."""

    __tablename__ = "plans"
    __table_args__ = (
        CheckConstraint("kind IN ('annual','monthly')", name="kind"),
        CheckConstraint("status IN ('DRAFT','CONFIRMED')", name="status"),
    )

    # p0-planning 의 PlanId 가 그대로 들어온다. 자동 증가 정수를 쓰지 않는다 —
    # 도메인이 id 를 먼저 만들고 저장은 나중이라, DB 가 번호를 매기면 둘이 달라진다.
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    center_id: Mapped[int] = mapped_column(
        ForeignKey("centers.id"),
        index=True,
        comment="원 격리용. 조회가 항상 이 값으로 먼저 걸린다",
    )
    kind: Mapped[str] = mapped_column(String(10), comment="annual | monthly")
    school_year: Mapped[int] = mapped_column(comment="학년도. 3월~익년 2월")
    classroom_ref: Mapped[str] = mapped_column(
        String(50), index=True, comment="도메인이 쓰는 반 참조. classes.id 를 문자열로 담는다"
    )
    status: Mapped[str] = mapped_column(
        String(20), comment="DRAFT | CONFIRMED. body 의 status 에서 꺼낸 값이다"
    )
    body: Mapped[dict] = mapped_column(
        JSONB, comment="도메인 객체 전체. 이것이 원본이고 위 칸들은 여기서 유도한다"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
