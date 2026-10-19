"""계획안 테이블. 연간·월간이 한 테이블을 쓴다.

**본문을 행으로 펼치지 않는다.** `YearlyPlan` 은 12개월 × (테마 · 근거 · 생성이력 ·
감사기록)이고 `MonthlyPlan` 은 Template 과 활성 주차에 따라 칸 수가 달라진다. 이걸
테이블로 펼치면 p0-planning 이 칸을 하나 더할 때마다 마이그레이션이 따라붙는다.

그래서 `body` JSONB 하나에 통째로 넣고, **조회에 쓰는 값만 칸으로 꺼낸다.**
꺼낸 칸은 항상 `body` 에서 유도한다 — 따로 받으면 둘이 어긋난다.

펼칠 시점은 「칸 하나만 SQL 로 고쳐야 할 때」다. 지금은 읽고-고치고-통째로 쓴다.
두 사람이 같은 계획안을 고칠 때 나중 저장이 먼저 저장을 덮지 않게 하는 것은
`revision` 이다(결정 문서 12.4 D-3). 비교와 409 는 편집 API 가 한다.
"""

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    func,
    text,
)
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
        # 연간은 반 하나에 하나다. 라우터가 먼저 보고 409 를 내지만 **최종 보장은 여기다** —
        # 두 요청이 동시에 오면 둘 다 「없다」를 보고 둘 다 만든다. 학년도는 걸지 않는다:
        # `classes` 행이 학년도마다 새로 생기므로 `classroom_ref` 가 이미 학년도를 가른다.
        # 월간은 한 반에 12개라 조건을 annual 로 좁힌다.
        Index(
            "uq_plans_annual_per_classroom",
            "center_id",
            "classroom_ref",
            unique=True,
            postgresql_where=text("kind = 'annual'"),
        ),
        # 월간은 반 · 월당 하나다(결정 문서 12.5). 연간과 같은 이유로 최종 보장은 여기다.
        Index(
            "uq_plans_monthly_per_classroom_month",
            "center_id",
            "classroom_ref",
            "target_month",
            unique=True,
            postgresql_where=text("kind = 'monthly'"),
        ),
        CheckConstraint(
            "(kind = 'monthly') = (target_month IS NOT NULL)", name="target_month_kind"
        ),
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
    target_month: Mapped[str | None] = mapped_column(
        String(7), comment="월간의 대상 월 YYYY-MM. body 의 target_month 에서 꺼낸 값이다"
    )
    status: Mapped[str] = mapped_column(
        String(20), comment="DRAFT | CONFIRMED. body 의 status 에서 꺼낸 값이다"
    )
    revision: Mapped[int] = mapped_column(
        default=1, server_default="1", comment="저장할 때마다 +1. 읽은 값과 다르면 그 사이 바뀐 것"
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
    # 어느 양식에서 나온 계획안인지. **복사하지 않고 번호만 든다** — 양식은 원본 하나만
    # 두고 계획안은 그걸 가리킨다. FK 라서 파생 계획안이 남아 있는 양식은 지워지지 않는다
    # (지우려면 forms 쪽에서 숨김 처리를 해야 한다).
    form_id: Mapped[int | None] = mapped_column(
        ForeignKey("forms.id"), index=True, comment="원이 올린 양식. 없으면 우리 기본 서식"
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        comment="확정 시각. body 의 감사 기록에서 꺼낸 값이다 — 목록이 12개월치를 "
        "매번 되돌리지 않게 한다",
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
