"""소스 어댑터 (ADR-015).

**사실만 옮긴다.** API 가 준 값을 그대로 담고, 없는 값을 채우지 않는다.

각 함수는 `fetch` 를 받는다. 실제로는 HTTP 를 타고, 테스트에서는 녹화한 응답을 준다.
망을 타는 코드를 테스트가 부르면 결과가 그날 유행에 따라 달라져 고정할 수가 없다.
"""

from __future__ import annotations

import html
import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import urlparse

from app.features.trends.approved import ApprovedChannel, ApprovedOutlet
from app.features.trends.item import RawItem

# (url, params, headers) -> 파싱된 JSON
Fetch = Callable[[str, Mapping[str, str], Mapping[str, str]], Any]

YOUTUBE = "https://www.googleapis.com/youtube/v3"
NAVER_NEWS = "https://openapi.naver.com/v1/search/news.json"

# videos.list 는 한 번에 50개까지 받는다. 나눠 부르면 호출 수만 는다.
_VIDEO_BATCH = 50

_TAGS = re.compile(r"<[^>]+>")


def youtube_uploads(
    fetch: Fetch,
    api_key: str,
    channels: Sequence[ApprovedChannel],
    per_channel: int = 20,
) -> list[RawItem]:
    """승인 채널의 최근 업로드를 긁는다.

    검색(search.list)을 쓰지 않는다. 호출당 100 units 라 하루 100회면 끝나는데,
    어차피 승인 채널 것만 쓰므로 검색해서 긁어와도 전부 걸러진다.
    playlistItems.list 는 1 unit 이다 (ADR-015 근거).
    """
    collected: list[RawItem] = []
    for channel in channels:
        page = fetch(
            f"{YOUTUBE}/playlistItems",
            {
                "part": "snippet,contentDetails",
                "playlistId": channel.uploads_playlist_id,
                "maxResults": str(per_channel),
                "key": api_key,
            },
            {},
        )
        for entry in page.get("items") or []:
            snippet = entry.get("snippet") or {}
            video_id = (entry.get("contentDetails") or {}).get("videoId")
            if not video_id:
                continue
            collected.append(
                RawItem(
                    source="youtube",
                    source_id=video_id,
                    title=(snippet.get("title") or "").strip(),
                    description=(snippet.get("description") or "").strip(),
                    url=f"https://www.youtube.com/watch?v={video_id}",
                    published_at=_iso_day(snippet.get("publishedAt")),
                    origin=channel.name,
                    facts={"channel_id": channel.channel_id},
                )
            )
    return _with_video_status(fetch, api_key, collected)


def _with_video_status(fetch: Fetch, api_key: str, items: list[RawItem]) -> list[RawItem]:
    """madeForKids 와 조회수를 채운다.

    유튜브는 업로더에게 아동용 여부 표시를 강제하고 그 값이 API 에 나온다.
    다른 소스에는 이에 대응하는 값이 없다 — 검열 1단이 여기 기댄다.
    **여기서는 채우기만 한다.** 걸러내는 것은 PR ② 의 일이다.
    """
    by_id = {item.source_id: item for item in items}
    status: dict[str, dict[str, Any]] = {}
    ids = list(by_id)
    for start in range(0, len(ids), _VIDEO_BATCH):
        batch = ids[start : start + _VIDEO_BATCH]
        page = fetch(
            f"{YOUTUBE}/videos",
            {"part": "status,statistics", "id": ",".join(batch), "key": api_key},
            {},
        )
        for entry in page.get("items") or []:
            status[entry["id"]] = {
                # 표시가 없으면 None 이다. False 로 바꾸지 않는다 —
                # "아동용이 아니다" 와 "모른다" 는 다르다.
                "made_for_kids": (entry.get("status") or {}).get("madeForKids"),
                "view_count": _as_int((entry.get("statistics") or {}).get("viewCount")),
            }
    return [_merge_facts(item, status.get(item.source_id, {})) for item in items]


def _merge_facts(item: RawItem, extra: Mapping[str, Any]) -> RawItem:
    if not extra:
        return item
    return RawItem(
        source=item.source,
        source_id=item.source_id,
        title=item.title,
        description=item.description,
        url=item.url,
        published_at=item.published_at,
        origin=item.origin,
        facts={**item.facts, **extra},
    )


def naver_news(
    fetch: Fetch,
    client_id: str,
    client_secret: str,
    queries: Iterable[str],
    outlets: Sequence[ApprovedOutlet],
    per_query: int = 50,
) -> list[RawItem]:
    """승인 언론사 기사만 남긴다.

    네이버가 `originallink` 로 원문 주소를 주므로 도메인으로 대조할 수 있다.
    블로그·카페는 쓰지 않는다 — 협찬 글을 구분할 방법이 없다 (ADR-015).
    """
    allowed = {outlet.domain: outlet for outlet in outlets}
    headers = {"X-Naver-Client-Id": client_id, "X-Naver-Client-Secret": client_secret}
    collected: list[RawItem] = []
    seen: set[str] = set()
    for query in queries:
        page = fetch(
            NAVER_NEWS,
            {"query": query, "display": str(per_query), "sort": "date"},
            headers,
        )
        for entry in page.get("items") or []:
            original = (entry.get("originallink") or "").strip()
            outlet = allowed.get(_domain(original))
            if outlet is None or original in seen:
                continue
            seen.add(original)
            collected.append(
                RawItem(
                    source="naver_news",
                    source_id=original,
                    title=_plain(entry.get("title")),
                    description=_plain(entry.get("description")),
                    url=original,
                    published_at=_rfc_day(entry.get("pubDate")),
                    origin=outlet.domain,
                    facts={"outlet": outlet.name, "query": query},
                )
            )
    return collected


def _plain(text: str | None) -> str:
    """네이버는 검색어에 <b> 를 감아서 주고 따옴표를 HTML 로 이스케이프한다."""
    return html.unescape(_TAGS.sub("", text or "")).strip()


def _domain(url: str) -> str:
    return urlparse(url).netloc.lower().removeprefix("www.")


def _iso_day(value: str | None) -> str:
    """2026-09-18T07:00:00Z -> 2026-09-18. 못 읽으면 빈 문자열이다."""
    if not value:
        return ""
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return ""


def _rfc_day(value: str | None) -> str:
    """Mon, 22 Sep 2026 10:00:00 +0900 -> 2026-09-22."""
    if not value:
        return ""
    try:
        return parsedate_to_datetime(value).date().isoformat()
    except (TypeError, ValueError):
        return ""


def _as_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
