"""주 1회 수집 (ADR-016).

월요일 새벽에 돈다. 교사가 버튼을 누를 때 돌지 않는다 — 느리고, API 한도가 오전에
끝나고, 위험한 놀이가 검열을 못 거치고 교사에게 간다.

**여기서는 거르지 않는다.** 승인 목록에 없는 곳에서 안 긁어올 뿐이다.
금칙 대조와 LLM 판정은 다음 단계다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from app.config import settings
from app.features.trends import approved as approved_module
from app.features.trends import sources
from app.features.trends.approved import ApprovedSources
from app.features.trends.item import RawItem, save


@dataclass(frozen=True, slots=True)
class CollectResult:
    items: list[RawItem]
    failures: list[str] = field(default_factory=list)


def http_fetch(url, params, headers):  # pragma: no cover - 망을 타는 유일한 곳
    import httpx

    response = httpx.get(url, params=dict(params), headers=dict(headers), timeout=20.0)
    response.raise_for_status()
    return response.json()


def collect(
    fetch: sources.Fetch,
    approved: ApprovedSources,
    *,
    youtube_key: str | None,
    naver_id: str | None,
    naver_secret: str | None,
    per_channel: int = 20,
) -> CollectResult:
    """소스를 하나씩 돈다. 하나가 죽어도 나머지는 계속한다.

    트렌드는 부가 기능이다. 유튜브 한도가 터졌다고 뉴스까지 못 모을 이유가 없다.
    대신 무엇이 죽었는지는 failures 로 남겨 사람이 본다 — 조용히 0건이 되면
    "이번 주는 유행이 없나 보다" 로 읽힌다.
    """
    items: list[RawItem] = []
    failures: list[str] = []

    if approved.channels:
        if not youtube_key:
            failures.append("youtube: 키가 없다 (YOUTUBE_API_KEY)")
        else:
            try:
                items += sources.youtube_uploads(fetch, youtube_key, approved.channels, per_channel)
            except Exception as error:
                failures.append(f"youtube: {type(error).__name__} {error}")

    if approved.outlets and approved.news_queries:
        if not (naver_id and naver_secret):
            failures.append("naver_news: 키가 없다 (NAVER_CLIENT_ID · NAVER_CLIENT_SECRET)")
        else:
            try:
                items += sources.naver_news(
                    fetch, naver_id, naver_secret, approved.news_queries, approved.outlets
                )
            except Exception as error:
                failures.append(f"naver_news: {type(error).__name__} {error}")

    return CollectResult(items=items, failures=failures)


def run(day: date | None = None) -> CollectResult:  # pragma: no cover - 망을 탄다
    """주간 작업이 부르는 입구. 파일까지 쓴다."""
    day = day or date.today()
    result = collect(
        http_fetch,
        approved_module.load(),
        youtube_key=settings.youtube_api_key,
        naver_id=settings.naver_client_id,
        naver_secret=settings.naver_client_secret,
    )
    path = save(result.items, day)
    print(f"{len(result.items)}건 수집 — {path}")
    for failure in result.failures:
        print(f"  실패 {failure}")
    return result


if __name__ == "__main__":  # pragma: no cover
    run()
