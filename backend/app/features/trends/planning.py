"""계획안 생성이 읽는 트렌드 (ADR-072).

실시간 수집이 아니다. 저장소에 머지된 주 파일을 읽는다(ADR-016). 원이 껐거나 · 파일이 없거나 ·
깨졌으면 트렌드 없이 만든다 — 결과 객체로 알리고 예외를 내지 않는다(CLAUDE.md §7).

넘기는 것: 지금도 승인 목록에 있는 유튜브 채널 자료. 노래는 채널 종류가 동요인 채널 것만.
다시 거르지 않는다 — 머지된 파일은 사람이 수집 PR 에서 2단 위험 표시 · 3단 판정을 보고 지운 뒤
승인한 것이다(트렌드 화면과 같다, ADR-016).
기사는 놀이 서술이 아니라 넘기지 않는다(ADR-016 「소재 발굴 · 확인용」).
링크 · 조회수도 넘기지 않는다.
"""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

from ssuksak.planning.application.ports import OptionalContextResult, OptionalContextStatus
from ssuksak.planning.domain.trend import (
    SUMMARY_MAX_LENGTH,
    TREND_CONTEXT,
    TrendItem,
    TrendKind,
    recent_weeks,
    select_trends,
    trend_kind,
)

from app.features.trends import approved
from app.features.trends.item import COLLECTED_DIR, RawItem, load

logger = logging.getLogger(__name__)


def _summary(description: str) -> str:
    lines = [
        line.strip() for line in description.splitlines() if line.strip() and "http" not in line
    ]
    return " ".join(lines[:2])[:SUMMARY_MAX_LENGTH]


def trend_items(raw: list[RawItem], week: str) -> list[TrendItem]:
    channels = {c.name: c for c in approved.load().channels}
    items = []
    for row in raw:
        channel = channels.get(row.origin)
        if row.source != "youtube" or channel is None or channel.kind == "제외":
            continue
        kind = trend_kind(row.title, TrendKind(channel.kind) if channel.kind else None)
        # ADR-072 결정 12: 노래는 승인 파일에서 종류가 동요인 채널 것만.
        # 다른 채널의 노래 영상은 넘기지 않는다.
        if kind is None or (kind is TrendKind.SONG and channel.kind != TrendKind.SONG.value):
            continue
        items.append(
            TrendItem(
                trend_id=f"{row.source}:{row.source_id}",
                kind=kind,
                title=row.title.strip(),
                summary=_summary(row.description),
                source_name=channel.name,
                week=week,
                published_on=date.fromisoformat(row.published_at),
                name_words=channel.name_words,
            )
        )
    return items


class TrendContextProvider:
    """OptionalContextProvider: 이름 `trend` 에 tuple[TrendItem, ...] 을 준다."""

    def __init__(self, *, enabled: bool, today: date, directory: Path | None = None) -> None:
        self._enabled = enabled
        self._today = today
        self._directory = directory or COLLECTED_DIR

    def fetch(self, name: str) -> OptionalContextResult:
        if name != TREND_CONTEXT or not self._enabled:
            return OptionalContextResult(
                name, OptionalContextStatus.UNAVAILABLE, detail="trends disabled"
            )
        try:
            items: list[TrendItem] = []
            for week in recent_weeks(self._today):
                path = self._directory / f"{week}.json"
                if path.exists():
                    items += trend_items(load(path), week)
            picked = select_trends(items, self._today)
        except Exception:  # 깨진 수집 파일이 생성을 막지 않는다.
            logger.warning("trend context unreadable", exc_info=True)
            return OptionalContextResult(
                name, OptionalContextStatus.ERROR, detail="trend files unreadable"
            )
        if not picked:
            return OptionalContextResult(
                name, OptionalContextStatus.UNAVAILABLE, detail="no recent trends"
            )
        return OptionalContextResult(name, OptionalContextStatus.AVAILABLE, picked)
