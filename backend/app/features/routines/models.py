"""일과 기록 모델. 계약은 docs/api-spec.md §10-1 이다 (ADR-025)."""

import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    Time,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
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
        when = self.time_range()
        if when:
            when = f" {when}"
        return f"[{self.name.strip()}{when}] {self.execution.strip()}"

    def time_range(self) -> str:
        """`09:20~10:40`. 한쪽만 있으면 `09:20~` · `~10:40`, 둘 다 없으면 빈 문자열."""
        if self.start_time and self.end_time:
            return f"{self.start_time:%H:%M}~{self.end_time:%H:%M}"
        if self.start_time:
            return f"{self.start_time:%H:%M}~"
        if self.end_time:
            return f"~{self.end_time:%H:%M}"
        return ""


# 날씨 · 미세먼지 값. 화면 · 종이 · DB CHECK 가 같은 글자를 쓴다 (ADR-089).
SKIES = ("맑음", "구름많음", "흐림", "비", "눈", "비나 눈")
DUSTS = ("좋음", "보통", "나쁨", "매우나쁨")


def _one_of(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class RegionWeather(Base):
    """원 지역 하루의 **자동** 날씨 (ADR-089).

    기상청 · 에어코리아를 지역 · 날짜마다 한 번만 부르려고 둔다.

    받은 값만 남긴다. 둘 다 못 받았으면 행을 만들지 않는다 — 다음 조회 때 다시 부른다.
    한쪽만 받았으면 받은 쪽만 채워 남기고, 그날은 다시 부르지 않는다.
    """

    __tablename__ = "region_weather"
    __table_args__ = (
        UniqueConstraint("region_sido", "region_sigungu", "date"),
        CheckConstraint(f"sky IS NULL OR {_one_of('sky', SKIES)}", name="sky_value"),
        CheckConstraint(f"dust IS NULL OR {_one_of('dust', DUSTS)}", name="dust_value"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    # 원이 적은 글자가 아니라 격자 표(resources/weather/kma_grid.csv)의 이름이다 — 「강원 · 춘천」과
    # 「강원특별자치도 · 춘천시」가 같은 행을 쓴다 (weather.region_of).
    region_sido: Mapped[str] = mapped_column(String(30), comment="격자 표의 시도 이름")
    region_sigungu: Mapped[str] = mapped_column(String(30), comment="격자 표의 시군구 이름")
    date: Mapped[datetime.date] = mapped_column(Date)
    sky: Mapped[str | None] = mapped_column(String(10), comment="기상청 단기예보로 만든 낮 날씨")
    dust: Mapped[str | None] = mapped_column(
        String(10), comment="에어코리아 실시간 측정 등급 — PM10 · PM2.5 중 나쁜 쪽"
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class RoutineWeather(Base):
    """교사가 고른 그날 날씨 — 반 × 날짜 하나 (ADR-089). 있으면 자동 값보다 이긴다."""

    __tablename__ = "routine_weather"
    __table_args__ = (
        UniqueConstraint("class_id", "date"),
        CheckConstraint(_one_of("sky", SKIES), name="sky_value"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    class_id: Mapped[int] = mapped_column(ForeignKey("classes.id"))
    date: Mapped[datetime.date] = mapped_column(Date)
    sky: Mapped[str] = mapped_column(String(10))
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class RoutineDraft(Base):
    """일과 기록 화면의 **임시본** — 반 × 날짜 하나 (ADR-082).

    교사가 쓰는 대로 화면 줄 전체를 여기에 둔다. **일과 기록(`routine_records`)이 아니다** —
    근거로 올리는 것은 화면을 떠날 때와 「오늘 일지 만들기」 때다. 쓰는 대로 일과 기록에 쓰면
    글자 하나마다 그 기록을 쓴 확정 일지가 `stale` 이 되고, 열어 보기만 한 날에도 빈 줄이 쌓인다.

    `revision` 은 하루치 한 덩어리의 판 번호다. 한 교사가 폰과 PC 를 같이 쓰면 옛 탭이 새 글을
    덮을 수 있어, 저장할 때마다 맞춰 본다.
    """

    __tablename__ = "routine_drafts"
    __table_args__ = (UniqueConstraint("class_id", "date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    class_id: Mapped[int] = mapped_column(ForeignKey("classes.id"))
    date: Mapped[datetime.date] = mapped_column(Date)
    revision: Mapped[int] = mapped_column(server_default="1", default=1)
    # 화면 줄 그대로다. 줄 수 · 글자 수는 저장 요청 스키마가 막는다(schemas.DraftSave).
    rows: Mapped[list[dict]] = mapped_column(JSONB, comment="화면 줄 전체 — 깔아 둔 줄 포함")
    removed: Mapped[list[int]] = mapped_column(
        JSONB, default=list, server_default="[]", comment="지우기로 표시한 일과 기록 id"
    )
    promoted: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default="false",
        comment="지금 줄이 일과 기록에 올라갔나. 저장할 때마다 false 로 돌아간다",
    )
    promoted_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), comment="마지막으로 올린 때. 정리 작업이 30일을 센다"
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ClassRoutineTemplate(Base):
    """반 기본 일과표 — 반마다 하나 (ADR-084).

    새 날을 열면 이 표로 줄을 깐다. 고정 줄(`weekday` 없음)과, 그 요일에만 더하는 줄
    (특별활동 — `weekday` 0=월 … 5=토)이 함께 들어 있다. 순서 · 시간 · 이름만 둔다.
    """

    __tablename__ = "class_routine_templates"

    id: Mapped[int] = mapped_column(primary_key=True)
    class_id: Mapped[int] = mapped_column(ForeignKey("classes.id"), unique=True)
    # 줄 수 · 글자 수는 저장 요청 스키마가 막는다(schemas.TemplateSave).
    rows: Mapped[list[dict]] = mapped_column(JSONB, comment="[{name, start, end, weekday}]")
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
