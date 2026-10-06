"""일과 기록 모델. 계약은 docs/api-spec.md §10-1 이다 (ADR-025)."""

import datetime

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Index, String, Text, Time, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class RoutineRecord(Base):
    """반 하루의 일과 한 줄 — 일일 보육일지 격자의 한 행이다. 3층 규격의 ① 사실 층이다.

    **행 수를 고정하지 않는다.** 같은 반도 특별활동이 있는 날은 행이 하나 더 있다 [실측, ADR-024].
    일과 이름도 교사가 적는다 — 원마다 다르다.

    **AI 가 쓰지 않는다.** 식사 · 낮잠처럼 있었던 일을 적는 칸이라 모델이 채우면 위조다
    (CLAUDE.md 문서 5분류). §11 의 일일 보육일지가 이 행을 `sources` 로 인용한다.

    이 파일은 `import datetime` 을 쓴다 — 칸 이름이 `date` 라 observations 와 같은 이유다.
    """

    __tablename__ = "routine_records"
    __table_args__ = (
        CheckConstraint(
            "start_time IS NULL OR end_time IS NULL OR start_time < end_time", name="time_range"
        ),
        CheckConstraint("length(btrim(name)) > 0", name="name_not_blank"),
        CheckConstraint("position >= 0", name="position_not_negative"),
        # 하루치를 반 · 날짜로 꺼낸다. 앞 칸이 class_id 라 반만 거르는 조회도 이 인덱스를 쓴다.
        Index("ix_routine_records_class_id_date", "class_id", "date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    class_id: Mapped[int] = mapped_column(ForeignKey("classes.id"))
    date: Mapped[datetime.date] = mapped_column(Date)
    position: Mapped[int] = mapped_column(
        server_default="0", comment="하루 안에서 표시 순서. 같으면 시작 시간 · id 순이다"
    )
    start_time: Mapped[datetime.time | None] = mapped_column(Time)
    end_time: Mapped[datetime.time | None] = mapped_column(Time)
    name: Mapped[str] = mapped_column(
        String(50), comment="일과 이름 — 「오전 실내놀이」. 원마다 달라 교사가 적는다"
    )
    plan: Mapped[str] = mapped_column(Text, server_default="", comment="활동계획")
    execution: Mapped[str] = mapped_column(
        Text, server_default="", comment="활동실행 — 사실 층이다. 교사가 쓰고 AI 가 쓰지 않는다"
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    def fact_text(self) -> str:
        """일지의 사실 한 줄. `[오전 실내놀이 09:20~10:40] 활동실행`.

        일지가 근거 사본으로 이 문자열을 남긴다. stale 판정이 이 문자열 하나를 비교하므로
        시간 · 일과 이름 · 활동실행 중 무엇이 바뀌어도 걸린다 (§11 판정 기준).
        """
        when = ""
        if self.start_time and self.end_time:
            when = f" {self.start_time:%H:%M}~{self.end_time:%H:%M}"
        elif self.start_time:
            when = f" {self.start_time:%H:%M}~"
        elif self.end_time:
            when = f" ~{self.end_time:%H:%M}"
        return f"[{self.name.strip()}{when}] {self.execution.strip()}"
