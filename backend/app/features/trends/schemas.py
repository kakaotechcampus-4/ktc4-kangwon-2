"""교사 화면에 주는 모양 (docs/api-spec.md §3-2)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class TrendItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str  # youtube · naver_news
    title: str
    summary: str
    url: str
    published_at: str
    origin: str  # 채널 이름 · 언론사 도메인


class TrendsResponse(BaseModel):
    """`week` 는 어느 주에 모은 것인지다 (2026-W42).

    교사에게 「언제 모은 자료인지」를 보여줘야 한다 — 두 달 전 것을 이번 주 유행으로
    읽으면 안 된다.
    """

    model_config = ConfigDict(extra="forbid")

    week: str
    items: list[TrendItem]
