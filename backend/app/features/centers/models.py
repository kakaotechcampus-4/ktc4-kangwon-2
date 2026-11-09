from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
    false,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
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
    trends_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default=false(),
        nullable=False,
        comment="트렌드봇을 켤지 (FR-808). **기본은 꺼짐** — 부가 기능은 원하는 원이 켠다",
    )
    weekly_saturday_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default=false(),
        nullable=False,
        comment="주간계획안에 토요일을 넣을지 (ADR-030 WQ-01). **기본은 꺼짐** — 월~금",
    )
    observation_axis: Mapped[str] = mapped_column(
        String(16),
        default="NURI_5",
        server_default="NURI_5",
        nullable=False,
        comment=(
            "관찰 기록의 영역 축 (observations/models.py AXES). "
            "NURI_5 는 누리과정 5영역, DAILY_PLAY_2 는 일상생활·놀이활동. "
            "**기본은 NURI_5** — 교사 문서 3건 중 2건이 2축이라 둘 다 받는다"
        ),
    )
    reflect_mark: Mapped[str] = mapped_column(
        String(10),
        default="(반영)",
        server_default="(반영)",
        nullable=False,
        comment=(
            "어제 지원을 반영한 일과 줄에 종이가 붙이는 글자 (ADR-085). "
            "「(반영)」 · 「(놀이반영)」 · 빈 문자열(붙이지 않음)"
        ),
    )
    region_sigungu: Mapped[str] = mapped_column(
        String(30), comment="시·군·구. 지역사회 연계 활동 선별에 쓴다"
    )
    registry_key: Mapped[str | None] = mapped_column(
        String(300),
        unique=True,
        comment=(
            "정부 어린이집 목록의 열쇠(시도|시군구|이름|주소, ADR-068). "
            "같은 열쇠를 고른 교사는 이 원으로 든다. 직접 적은 원은 NULL"
        ),
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Greetings(Base):
    """원별 성품인사. 12개월을 한 번에 교체한다 (docs/api-spec.md §3)."""

    __tablename__ = "greetings"

    center_id: Mapped[int] = mapped_column(ForeignKey("centers.id"), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    items: Mapped[list[dict[str, int | str]]] = mapped_column(JSONB)


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
        ForeignKey("users.id"),
        index=True,
        comment="반 주인 — 반을 만든 계정(ADR-059). NULL 은 이 결정 전에 만든 옛 반이다",
    )
    consent_confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        comment="동의 확인 시각. 아동 0명이면 아동 수로 복원할 수 없다 (docs/PRD.md S2)",
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ClassAccessRequest(Base):
    """남의 반을 보겠다는 요청 한 줄 (ADR-059). 한 계정이 한 반에 줄 하나만 갖는다.

    거절 · 취소 뒤에 다시 요청하면 새 줄이 아니라 같은 줄을 PENDING 으로 되돌린다.
    """

    __tablename__ = "class_access_requests"
    __table_args__ = (
        UniqueConstraint("class_id", "requester_id"),
        CheckConstraint("status IN ('PENDING','APPROVED','REJECTED','REVOKED')", name="status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    class_id: Mapped[int] = mapped_column(
        ForeignKey("classes.id"), index=True, comment="보고 싶은 반"
    )
    requester_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), index=True, comment="요청한 계정"
    )
    status: Mapped[str] = mapped_column(
        String(10), comment="PENDING | APPROVED | REJECTED | REVOKED. 승인은 보기만 허락한다"
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
    call_name: Mapped[str | None] = mapped_column(
        String(50), comment="외자 아이를 부르는 이름(김민 -> 민이). 가명표에 넣는다. ADR-004 보완"
    )
    code: Mapped[str] = mapped_column(
        String(20),
        comment="LLM 에 나가는 가명. 받침 있는 더미 한글 이름 (ADR-004). 반 안에서 유일하다",
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
