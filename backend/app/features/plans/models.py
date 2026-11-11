"""계획안 테이블. 연간·월간·주간이 한 테이블을 쓴다.

**본문을 행으로 펼치지 않는다.** `YearlyPlan` 은 12개월 × (테마 · 근거 · 생성이력 ·
감사기록)이고 `MonthlyPlan` 은 Template 과 활성 주차에 따라 칸 수가 달라진다. 이걸
테이블로 펼치면 p0-planning 이 칸을 하나 더할 때마다 마이그레이션이 따라붙는다.

그래서 `body` JSONB 하나에 통째로 넣고, **조회에 쓰는 값만 칸으로 꺼낸다.**
꺼낸 칸은 항상 `body` 에서 유도한다 — 따로 받으면 둘이 어긋난다.

펼칠 시점은 「칸 하나만 SQL 로 고쳐야 할 때」다. 지금은 읽고-고치고-통째로 쓴다.
두 사람이 같은 계획안을 고칠 때 나중 저장이 먼저 저장을 덮지 않게 하는 것은
`revision` 이다(결정 문서 12.4 D-3). 비교와 409 는 편집 API 가 한다.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

KINDS = ("annual", "monthly", "weekly")
STATUSES = ("DRAFT", "CONFIRMED")


class Plan(Base):
    """연간 · 월간 · 주간 계획안 하나."""

    __tablename__ = "plans"
    __table_args__ = (
        UniqueConstraint("plan_ref"),
        CheckConstraint("kind IN ('annual','monthly','weekly')", name="kind"),
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
        # 주간은 반 · 주당 하나다(주간 계약 §4-1 G5). 같은 이유로 최종 보장은 여기다.
        Index(
            "uq_plans_weekly_per_classroom_week",
            "center_id",
            "classroom_ref",
            "week_id",
            unique=True,
            postgresql_where=text("kind = 'weekly'"),
        ),
        # 월간 · 주간은 대상 달을 가진다 — 주간은 그 주가 속한 달이다(목록을 달로 거른다).
        CheckConstraint("(kind = 'annual') = (target_month IS NULL)", name="target_month_kind"),
        CheckConstraint("(kind = 'weekly') = (week_id IS NOT NULL)", name="week_id_kind"),
        # 확정본은 반 이름 · 담임 이름을 들고 있어야 한다 — 내보내기가 반을 새로 읽지 않는다.
        CheckConstraint(
            "status <> 'CONFIRMED' OR (class_name IS NOT NULL AND teacher_name IS NOT NULL)",
            name="confirmed_has_class_snapshot",
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
    kind: Mapped[str] = mapped_column(String(10), comment="annual | monthly | weekly")
    school_year: Mapped[int] = mapped_column(comment="학년도. 3월~익년 2월")
    classroom_ref: Mapped[str] = mapped_column(
        String(50), index=True, comment="도메인이 쓰는 반 참조. classes.id 를 문자열로 담는다"
    )
    target_month: Mapped[str | None] = mapped_column(
        String(7),
        comment="월간 · 주간의 대상 월 YYYY-MM. body 의 target_month(주간은 week_id 의 달)에서 "
        "꺼낸 값이다",
    )
    week_id: Mapped[str | None] = mapped_column(
        String(10), comment="주간의 주 YYYY-MM-Wn. body 의 week_id 에서 꺼낸 값이다"
    )
    status: Mapped[str] = mapped_column(
        String(20), comment="DRAFT | CONFIRMED. body 의 status 에서 꺼낸 값이다"
    )
    class_name: Mapped[str | None] = mapped_column(
        String(50),
        comment="확정할 때 찍은 반 이름. 내보내기가 쓴다 (ADR-010 결정 1 · ADR-062)",
    )
    teacher_name: Mapped[str | None] = mapped_column(
        String(50),
        comment="확정할 때 찍은 담임 이름. 지금 찍는 문서는 없다 (ADR-010 결정 1 · ADR-062)",
    )
    revision: Mapped[int] = mapped_column(
        default=1, server_default="1", comment="저장할 때마다 +1. 읽은 값과 다르면 그 사이 바뀐 것"
    )
    body: Mapped[dict] = mapped_column(
        JSONB, comment="도메인 객체 전체. 이것이 원본이고 위 칸들은 여기서 유도한다"
    )
    # Core 의 주제 포트를 유지하고 서버가 문서 단위로 생성·저장한다(ADR-041).
    # 교사 수정도 이 칸에 저장한다. 소주제는 상위 주제의 근거·생성 방식을 물려받는다.
    sub_themes: Mapped[dict] = mapped_column(
        JSONB, default=dict, server_default="{}", comment='월 -> 소주제 배열. {"3": ["..."]}'
    )
    annual_safety: Mapped[dict] = mapped_column(
        JSONB,
        default=dict,
        server_default="{}",
        comment="교사 안전교육 배치. months(월→구분 배열)와 audit(변경 전후·행위자·UTC 시각)",
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


class GenerationRun(Base):
    """생성 요청 한 번의 기록 — 어디까지 갔고 어떻게 끝났는지. **숫자와 이름만 든다** (ADR-096).

    프롬프트 · 응답 본문 · 반 이름 · 아이 정보 · 요청 사항 원문 · 예외 문장 · 트렌드 상태는 없다.
    작업 큐가 아니다 — 생성은 요청 스레드가 처음부터 끝까지 하고, 이 표는 그 자취를 적을 뿐이다.
    `class_id` · `center_id` 에 FK 가 없는 것은 진짜 commit 하는 테스트가 반 · 원을 지우기 때문이다.
    """

    __tablename__ = "generation_runs"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('annual_theme','annual_play','monthly_theme','monthly_play','weekly')",
            name="kind",
        ),
        CheckConstraint("status IN ('RUNNING','SUCCEEDED','FAILED','STOPPED')", name="status"),
        CheckConstraint("mode IN ('mock','real')", name="mode"),
        CheckConstraint("(status = 'RUNNING') = (finished_at IS NULL)", name="finished_when_done"),
        Index("ix_generation_runs_class_id_started_at", "class_id", "started_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, comment="화면이 X-Generation-Run-Id 로 준 값. 없으면 서버가 만든다"
    )
    kind: Mapped[str] = mapped_column(
        String(20), comment="annual_theme | annual_play | monthly_theme | monthly_play | weekly"
    )
    center_id: Mapped[int] = mapped_column(
        Integer, comment="원 격리용. 단건 조회가 먼저 이 값으로 거른다. FK 없음"
    )
    class_id: Mapped[int] = mapped_column(Integer, comment="classes.id. FK 없음")
    plan_id: Mapped[int | None] = mapped_column(
        ForeignKey("plans.id", ondelete="SET NULL"),
        index=True,
        comment="만들어진 계획안. 계획안을 지워도 기록은 남는다",
    )
    status: Mapped[str] = mapped_column(
        String(20), comment="RUNNING | SUCCEEDED | FAILED | STOPPED. UNKNOWN 은 읽을 때 만든다"
    )
    stage: Mapped[str] = mapped_column(
        String(20), comment="종류별 단계 키. 앞으로만 간다. 실패하면 실패한 단계가 남는다"
    )
    error_code: Mapped[str | None] = mapped_column(
        String(50), comment="계약 오류 코드. 문장은 저장하지 않는다"
    )
    mode: Mapped[str] = mapped_column(String(10), comment="mock | real. 첫 줄을 쓸 때의 LLM_MODE")
    model: Mapped[str | None] = mapped_column(
        String(100), comment="LLM 을 한 번이라도 불렀으면 그 모델. 끝날 때만 채운다"
    )
    prompt_versions: Mapped[list | None] = mapped_column(
        JSONB(none_as_null=True),
        comment="이 실행이 만든 LLM 요청의 프롬프트 판 이름들. 처음 쓴 순서, 중복 없이",
    )
    llm_calls: Mapped[int | None] = mapped_column(
        Integer, comment="LLM 시도 수(재시도 포함). 끝날 때 채운다"
    )
    phase_ms: Mapped[dict | None] = mapped_column(
        JSONB(none_as_null=True), comment="구간 이름 -> 걸린 ms. 끝날 때 채운다"
    )
    attempts: Mapped[list | None] = mapped_column(
        JSONB(none_as_null=True),
        comment="요청 안의 다시 하기 — 구간 · 전송 · 수리 시도. 이름 · 번호만 (ADR-096)",
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), comment="끝난 시각. RUNNING 이면 NULL"
    )
