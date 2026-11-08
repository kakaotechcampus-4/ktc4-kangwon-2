"""트렌드봇 수집 자료를 생성에 넘기는 Rule (ADR-070).

수집 · 승인 · 위험 표시는 백엔드 트렌드봇이 한다(ADR-016). 여기는 그 뒤의 Rule 이다 —
제목으로 종류를 달고, 최근 4주에서 종류별로 고르게 30건까지 고른다. LLM 은 이 안에서만 반영한다.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from enum import Enum
from typing import Iterable

from .errors import InvalidDomainValueError
from .provenance import EvidenceSource, EvidenceSourceType

# OptionalContextProvider 에서 이 이름으로 읽는다. 값은 tuple[TrendItem, ...].
TREND_CONTEXT = "trend"
TREND_WEEKS = 4
TREND_LIMIT = 30
SUMMARY_MAX_LENGTH = 200


class TrendKind(str, Enum):
    """LLM 이 칸을 고르는 데 쓰는 종류. 값이 프롬프트에 그대로 나간다."""

    STORY = "동화"
    SONG = "동요"
    CRAFT = "만들기"
    MOVEMENT = "신체"
    ROLE = "역할"
    GAME = "게임"
    PLAY = "놀이"  # 위 어디에도 안 맞는 일반 놀이 — 자유놀이 · 실내놀이 쪽이다


# 앞에서부터 처음 맞는 종류. 「동물 동요 동화」처럼 둘 다 있으면 앞의 것이다.
_KIND_WORDS: tuple[tuple[TrendKind, tuple[str, ...]], ...] = (
    (TrendKind.STORY, ("동화", "이야기", "그림책", "읽어주")),
    (TrendKind.SONG, ("동요", "노래")),  # 「송」은 「방송」에 걸린다
    (TrendKind.CRAFT, ("만들기", "접기", "미술", "도안", "꾸미기")),
    (TrendKind.MOVEMENT, ("요가", "체조", "율동", "동작", "체육", "스트레칭", "댄스", "춤")),
    (TrendKind.ROLE, ("병원놀이", "역할놀이", "시장놀이", "가게놀이", "요리놀이", "소꿉")),
    (TrendKind.GAME, ("게임", "술래", "꼬리잡기", "보물찾기")),
    (TrendKind.PLAY, ("놀이",)),
)
# 놀이 칸에 옮길 수 없는 것: 배경음악 · 타이머 · 생방송 · 시청자 이벤트.
_EXCLUDED_WORDS = ("타이머", "놀이음악", "BGM", "라이브", "시청자", "당첨")
# 「놀이」 낱말을 보기 전에 지우는 이름: 「[EBS놀이터]」는 놀이가 아니라 프로그램 꼬리표다.
_NOT_PLAY = ("놀이터",)


def trend_kind(title: str, channel_kind: TrendKind | None = None) -> TrendKind | None:
    """제목 낱말로 종류를 단다. 낱말이 없으면 채널 종류, 그것도 없으면 None(넘기지 않는다)."""

    if any(word in title for word in _EXCLUDED_WORDS):
        return None
    text = title
    for word in _NOT_PLAY:
        text = text.replace(word, "")
    for kind, words in _KIND_WORDS:
        if any(word in text for word in words):
            return kind
    return channel_kind


@dataclass(frozen=True, slots=True)
class TrendItem:
    """생성에 넘기는 수집 자료 한 건. 링크 · 조회수는 넘기지 않는다."""

    trend_id: str  # <source>:<source_id>  예) youtube:abc123
    kind: TrendKind
    title: str
    summary: str
    source_name: str  # 승인 채널 이름
    week: str  # 수집 주  예) 2026-W44
    published_on: date

    def __post_init__(self) -> None:
        for name in ("trend_id", "title", "source_name", "week"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise InvalidDomainValueError(f"TrendItem.{name} must be non-blank")
        if not isinstance(self.kind, TrendKind):
            raise InvalidDomainValueError("TrendItem.kind is invalid")
        if not isinstance(self.summary, str) or len(self.summary) > SUMMARY_MAX_LENGTH:
            raise InvalidDomainValueError("TrendItem.summary is too long")
        if not isinstance(self.published_on, date):
            raise InvalidDomainValueError("TrendItem.published_on must be a date")

    def payload(self) -> dict[str, str]:
        return {"trend_id": self.trend_id, "kind": self.kind.value, "title": self.title, "summary": self.summary}


def week_label(day: date) -> str:
    year, week, _ = day.isocalendar()
    return f"{year}-W{week:02d}"


def recent_weeks(today: date, weeks: int = TREND_WEEKS) -> tuple[str, ...]:
    """오늘이 든 주부터 거슬러 weeks 개 주."""
    return tuple(week_label(today - timedelta(days=7 * k)) for k in range(weeks))


def select_trends(items: Iterable[TrendItem], today: date, limit: int = TREND_LIMIT) -> tuple[TrendItem, ...]:
    """최근 4주에서 같은 자료는 한 번만, 종류마다 새것부터 번갈아 limit 건까지.

    번갈아 고르는 까닭: 동요 채널이 한 주에 수십 건을 올려 새것순만으로는 30건이 노래로 찬다.
    """

    weeks = set(recent_weeks(today))
    newest: dict[str, TrendItem] = {}
    for item in items:
        if item.week in weeks and (item.trend_id not in newest or item.week > newest[item.trend_id].week):
            newest[item.trend_id] = item
    by_kind: dict[TrendKind, list[TrendItem]] = defaultdict(list)
    for item in sorted(newest.values(), key=lambda i: (i.published_on, i.trend_id), reverse=True):
        by_kind[item.kind].append(item)
    queues = [by_kind[kind] for kind in TrendKind if by_kind[kind]]
    picked: list[TrendItem] = []
    while queues and len(picked) < limit:
        for queue in list(queues):
            if len(picked) == limit:
                break
            picked.append(queue.pop(0))
            if not queue:
                queues.remove(queue)
    return tuple(picked)


def trend_evidence(item: TrendItem) -> EvidenceSource:
    return EvidenceSource(
        EvidenceSourceType.TREND,
        item.trend_id,
        item.week,
        effective_date=item.published_on,
        display_name=f"{item.source_name} · {item.title}",
    )
