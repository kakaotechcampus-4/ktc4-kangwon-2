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

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

KINDS = ("annual", "monthly")
STATUSES = ("DRAFT", "CONFIRMED")


class Plan(Base):
    """연간 또는 월간 계획안 하나."""

    __tablename__ = "plans"
    __table_args__ = (
        UniqueConstraint("plan_ref"),
        CheckConstraint("kind IN ('annual','monthly')", name="kind"),
        CheckConstraint("status IN ('DRAFT','CONFIRMED')", name="status"),
    )

    # 계약의 id 는 정수다(api-spec §4). 화면이 이미 정수로 만들어져 있다.
    id: Mapped[int] = mapped_column(primary_key=True)
    # 도메인이 쓰는 id. 저장하기 전에 도메인이 먼저 만들어 자기 안에 박아두므로
    # DB 가 매긴 번호로 대신할 수 없다. 둘을 같은 칸에 담으려 하면 하나가 거짓이 된다.
    plan_ref: Mapped[str] = mapped_column(
        String(64), index=True, comment="p0-planning 의 PlanId. body 안의 값과 같다"
    )
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
    # 계약에는 있는데 도메인에는 없다(api-spec §4 · §6). 도메인의 ThemeTextGenerator 는
    # 주제 문장 하나만 돌려준다. 도메인을 건드리지 않고 서버가 따로 든다 —
    # 소주제는 별도 근거가 없고 상위 주제의 evidence·generation 을 물려받으므로
    # 도메인 객체 안에 들어갈 자리가 없다.
    sub_themes: Mapped[dict] = mapped_column(
        JSONB, default=dict, server_default="{}", comment='월 -> 소주제 배열. {"3": ["..."]}'
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
