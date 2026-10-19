"""교사가 보는 트렌드 (ADR-016 · docs/api-spec.md §3-2).

**여기서는 거르지 않는다.** 저장소에 들어 있는 것이 이미 사람이 본 것이다 —
주간 수집 PR 을 사람이 읽고 이상한 줄을 지운 뒤 머지한 것만 파일에 남는다.

**원이 껐으면 주지 않는다** (FR-808). 403 이다 — 빈 목록이 아니다. 「아직 모인 게
없다」와 「원이 껐다」는 화면이 다르게 그려야 한다.

계획안 생성은 아직 트렌드를 스스로 읽지 않는다. 교사가 트렌드 화면에서 옮겨 적는
길뿐이고, 그 화면이 이 응답으로 막힌다.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db import get_session
from app.features.centers.models import Center
from app.features.trends.item import COLLECTED_DIR, RawItem, load
from app.features.trends.schemas import TrendItem, TrendsResponse
from app.shared.auth.dependency import CurrentUser

DbSession = Annotated[Session, Depends(get_session)]

router = APIRouter(prefix="/trends", tags=["trends"])

#: 한 번에 주는 개수. 교사가 훑어보는 목록이라 많을수록 안 읽힌다.
LIMIT = 20


def latest_week() -> RawItem | None:
    """가장 최근 주 파일. 없으면 None."""
    files = sorted(COLLECTED_DIR.glob("*.json"))
    return files[-1] if files else None


def _summary(description: str) -> str:
    """설명 앞부분만. 교사 화면은 제목 아래 두 줄이 전부다."""
    lines = [line for line in description.splitlines() if line.strip()]
    return " ".join(lines[:2])[:200]


@router.get("", response_model=TrendsResponse)
def get_trends(session: DbSession, user: CurrentUser) -> TrendsResponse:
    if user.center_id is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail={"code": "NOT_FOUND", "message": "원을 찾을 수 없습니다.", "fields": []},
        )
    center = session.get(Center, user.center_id)
    if center is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail={"code": "NOT_FOUND", "message": "원을 찾을 수 없습니다.", "fields": []},
        )
    if not center.trends_enabled:
        # 빈 목록이 아니라 403 이다. 「없다」와 「껐다」는 화면이 다르게 그려야 한다.
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail={
                "code": "TRENDS_DISABLED",
                "message": "트렌드봇이 꺼져 있어요. 설정에서 켜면 쓸 수 있어요.",
                "fields": [],
            },
        )
    path = latest_week()
    if path is None:
        # 수집이 아직 안 돈 것이다. 오류가 아니라 **빈 목록**이다.
        return TrendsResponse(week="", items=[])
    items = load(path)
    # 새것부터. 같은 날이면 들어온 순서를 지킨다.
    items.sort(key=lambda item: item.published_at, reverse=True)
    return TrendsResponse(
        week=path.stem,
        items=[
            TrendItem(
                source=item.source,
                title=item.title,
                summary=_summary(item.description),
                url=item.url,
                published_at=item.published_at,
                origin=item.origin,
            )
            for item in items[:LIMIT]
        ],
    )
