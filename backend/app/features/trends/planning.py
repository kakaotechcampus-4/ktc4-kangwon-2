"""계획안 생성이 읽는 트렌드 (ADR-072).

실시간 수집이 아니다. 저장소에 머지된 주 파일을 읽는다(ADR-016). 원이 껐거나 · 파일이 없거나 ·
깨졌으면 트렌드 없이 만든다 — 결과 객체로 알리고 예외를 내지 않는다(CLAUDE.md §7).

넘기는 것: 지금도 승인 목록에 있는 유튜브 채널 자료. 다시 거르지 않는다 — 머지된 파일은 사람이
수집 PR 에서 2단 위험 표시 · 3단 판정을 보고 지운 뒤 승인한 것이다(트렌드 화면과 같다, ADR-016).
기사는 놀이 서술이 아니라 넘기지 않는다(ADR-016 「소재 발굴 · 확인용」).
링크 · 조회수도 넘기지 않는다.

그림책(ADR-072 2026-11-10 보완): 수집 PR 에서 사람이 승인한 도서관 정보나루 목록 파일을
주간에만 동화로 넘긴다. 제목에 그 주 주제 낱말(2자 이상)이 있는 책만. 제목 · 소개 200자만 —
표지 · 링크 · 대출 수는 넘기지 않는다.
"""

from __future__ import annotations

import json
import logging
import re
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
from app.features.trends.item import COLLECTED_DIR, RawItem, load, week_label

logger = logging.getLogger(__name__)

BOOKS_FILE = COLLECTED_DIR.parent / "books" / "picture_books.json"
# 관련 낱말 묶음. 사람이 APPROVED 로 바꾼 뒤에만 쓴다(그 전에는 주제 낱말 그대로만 대조).
RELATED_WORDS_FILE = COLLECTED_DIR.parent / "books" / "related_words.json"


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
        if kind is None:
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


# 제목 대조에서 빼는 일반어 — 「우리 집 …」 「… 놀이」처럼 아무 책에나 걸린다.
_BOOK_STOPWORDS = frozenset(
    {"우리", "함께", "놀이", "활동", "이야기", "친구들", "알아보기", "주제"}
)
# 낱말 끝 조사. 떼고도 2자 이상일 때만 뗀다(「가을과」 → 「가을」, 「열매를」 → 「열매」).
# ponytail: 형태소 분석이 아니다 — 「고양이」 → 「고양」처럼 짧아져도
# 부분 문자열 대조라 제목은 그대로 걸린다.
_PARTICLES = (
    "에서",
    "으로",
    "과",
    "와",
    "의",
    "을",
    "를",
    "은",
    "는",
    "이",
    "가",
    "에",
    "도",
    "랑",
)


def _strip_particle(word: str) -> str:
    for p in _PARTICLES:
        if word.endswith(p) and len(word) - len(p) >= 2:
            return word[: -len(p)]
    return word


def theme_words(text: str) -> tuple[str, ...]:
    """주 주제 글의 낱말(조사 뗌) 중 2자 이상, 일반어 뺌. 그림책 제목과 대조하는 Rule 낱말."""
    words = (_strip_particle(w) for w in re.findall(r"[가-힣A-Za-z0-9]+", text))
    return tuple(dict.fromkeys(w for w in words if len(w) >= 2 and w not in _BOOK_STOPWORDS))


def book_words_for(text: str, related_file: Path | None = None) -> tuple[str, ...]:
    """그림책 제목과 대조할 낱말: 주 주제 낱말 + 승인된 관련 낱말 묶음.

    묶음 이름이 주제 글에 있거나(「봄」처럼 한 글자도) 묶음 낱말이 주제 낱말과 같으면 그 묶음
    낱말(2자 이상)을 더한다. 파일이 없거나 · 깨졌거나 · APPROVED 가 아니면 주제 낱말만.
    """
    words = theme_words(text)
    path = related_file or RELATED_WORDS_FILE
    try:
        body = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        groups = body["groups"] if body.get("status") == "APPROVED" else []
        extra = [
            w
            for group in groups
            if group["name"] in text or any(w in words for w in group["words"])
            for w in group["words"]
            if len(w) >= 2
        ]
    except Exception:  # 깨진 묶음 파일은 넓히기만 뺀다.
        logger.warning("book related words unreadable", exc_info=True)
        extra = []
    return tuple(dict.fromkeys((*words, *extra)))


def book_items(raw: list[RawItem], words: tuple[str, ...], today: date) -> list[TrendItem]:
    """제목에 주제 낱말이 있는 승인 그림책 → 동화 트렌드.

    수집 주 · 게시일을 오늘로 두어 최근 4주 안에 들고, 동화 줄에서 유튜브보다 앞에 선다(새것부터).
    ponytail: 오늘 올라온 유튜브 동화와는 trend_id 순으로 유튜브가 앞선다 — 주 1회 수집이라 드물다.
    """
    return [
        TrendItem(
            trend_id=f"{row.source}:{row.source_id}",
            kind=TrendKind.STORY,
            title=row.title.strip(),
            summary=" ".join(row.description.split())[:SUMMARY_MAX_LENGTH],
            source_name="도서관 정보나루",
            week=week_label(today),
            published_on=today,
        )
        for row in raw
        if row.source == "data4library" and any(word in row.title for word in words)
    ]


class TrendContextProvider:
    """OptionalContextProvider: 이름 `trend` 에 tuple[TrendItem, ...] 을 준다.

    book_words 가 비면(놀이 중심 월간) 그림책을 읽지 않는다.
    """

    def __init__(
        self,
        *,
        enabled: bool,
        today: date,
        directory: Path | None = None,
        book_words: tuple[str, ...] = (),
        books_file: Path | None = None,
    ) -> None:
        self._enabled = enabled
        self._today = today
        self._directory = directory or COLLECTED_DIR
        self._book_words = book_words
        self._books_file = books_file or BOOKS_FILE

    def _books(self) -> list[TrendItem]:
        if not self._book_words or not self._books_file.exists():
            return []
        try:
            return book_items(load(self._books_file), self._book_words, self._today)
        except Exception:  # 깨진 그림책 파일은 그림책만 뺀다. 유튜브 트렌드 · 생성은 그대로다.
            logger.warning("picture book file unreadable", exc_info=True)
            return []

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
            picked = select_trends(items + self._books(), self._today)
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
