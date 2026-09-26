"""관찰 기록 모델. 계약은 docs/api-spec.md §10 이다."""

import datetime

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    String,
    Text,
    column,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

# 누리과정 5영역. 계약이 값을 고정한다 (docs/api-spec.md §10).
# schemas.py 가 이 튜플을 그대로 Literal 로 쓰고 아래 CheckConstraint 도 같은 값을 본다 —
# 목록을 두 군데 적으면 한쪽만 고쳐진 채로 통과한다.
DOMAINS = (
    "신체운동·건강",
    "의사소통",
    "사회관계",
    "예술경험",
    "자연탐구",
)


class Observation(Base):
    """교사가 본 것을 그대로 적은 사실. 3층 규격의 ① 사실 층이다.

    **AI 가 쓰지 않는다** — 사실기록형이라 모델이 채우면 위조다 (CLAUDE.md 문서 5분류).
    생성 엔드포인트가 없는 이유고, 이 테이블에 generation·evidence 축을 두지 않는 이유다.
    §11 의 문서가 이 행을 `sources` 로 인용한다.

    아동 실명이 `fact` 본문에 그대로 들어온다 (계약 §10 「개인정보」). 치환은 §11 이
    LLM 을 부르기 직전에 `shared/childCode` 로 하고, 이 테이블은 평문을 든다 — 교사 화면에는
    실명이 보여야 한다 (ADR-004).

    이 파일만 `import datetime` 을 쓴다. 계약이 칸 이름을 `date` 로 고정해서
    `from datetime import date` 를 하면 컬럼 이름과 타입 이름이 겹친다.
    """

    __tablename__ = "observations"
    __table_args__ = (
        # 5영역 밖의 값을 DB 가 막는다. pydantic Literal 이 이미 막지만 스크립트·수동 INSERT 는
        # 라우터를 지나지 않는다. 문자열로 SQL 을 적지 않고 DOMAINS 하나만 본다.
        CheckConstraint(column("domain").in_(DOMAINS), name="domain"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    class_id: Mapped[int] = mapped_column(ForeignKey("classes.id"), index=True)
    child_id: Mapped[int] = mapped_column(ForeignKey("children.id"), index=True)
    date: Mapped[datetime.date] = mapped_column(
        Date, comment="관찰한 날. 목록 정렬은 이 값 내림차순 고정 (docs/api-spec.md §10)"
    )
    domain: Mapped[str] = mapped_column(String(20), comment="누리과정 5영역 중 하나")
    context: Mapped[str] = mapped_column(
        String(50),
        server_default="",
        comment="상황. 선택이라 빈 문자열을 허용한다 — NULL 을 쓰지 않아 FE 가 분기하지 않는다",
    )
    fact: Mapped[str] = mapped_column(
        Text, comment="교사가 입력한 관찰 사실. 길이를 계약이 정하지 않아 Text 다"
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
