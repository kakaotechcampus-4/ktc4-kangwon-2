"""소스 어댑터 (ADR-016).

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
# 네이버가 2026 에 검색 API 를 개발자센터에서 네이버 클라우드 플랫폼(API HUB)으로
# 옮겼다. 옛 주소 openapi.naver.com/v1/search/news.json 와 X-Naver-Client-* 헤더는
# 새 키로 부르면 401 errorCode 024 로 떨어진다. 주소와 헤더를 같이 바꿔야 한다.
NAVER_NEWS = "https://naverapihub.apigw.ntruss.com/search/v1/news"

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
    playlistItems.list 는 1 unit 이다 (ADR-016 근거).
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
                    description=_body(snippet.get("description")),
                    url=f"https://www.youtube.com/watch?v={video_id}",
                    published_at=_iso_day(snippet.get("publishedAt")),
                    origin=channel.name,
                    facts={"channel_id": channel.channel_id},
                )
            )
    return _with_video_status(fetch, api_key, collected)


# 설명 꼬리를 자르는 기준.
# 유튜브 설명은 놀이 서술 몇 줄 뒤에 **구독 안내 · SNS 링크 · 해시태그 더미**가 붙는다.
# 실측 315건에서 설명이 전체 글자의 92% 였고 그 안에 링크 1,069개 · 해시태그 1,892개였다.
# 그대로 두면 ① 사람이 읽는 승인 PR 이 매주 4,400줄이 되고 ② 3단 Judge 토큰이 그만큼 나간다.
# 링크가 **들어 있는** 줄은 통째로 버린다 — "알짜닷컴 : http://..." 처럼 안내 문구가
# 앞에 붙어 있어서, 링크만 도려내면 뜻 없는 꼬리가 남는다.
_NOISE_LINE = re.compile(r"^\s*(?:[-=*_~·]{3,}|(?:#\S+\s*)+)\s*$|https?://")
_BODY_MAX = 600


def _body(text: str | None) -> str:
    """놀이 서술만 남긴다. 링크·해시태그·구분선 줄은 버린다.

    **낱말을 지우지 않고 줄 단위로만 버린다.** 문장 중간의 링크까지 손대면
    원문이 바뀌어, 나중에 "왜 걸렀나" 를 설명할 수 없다 (ADR-016).
    """
    kept: list[str] = []
    for line in (text or "").splitlines():
        if _NOISE_LINE.search(line):  # match 가 아니다 — 링크는 줄 가운데에도 온다
            continue
        kept.append(line.rstrip())
    body = "\n".join(kept).strip()
    # 줄을 버려도 긴 것이 남는다. 앞쪽에 놀이 서술이 오므로 뒤를 자른다.
    return body if len(body) <= _BODY_MAX else body[:_BODY_MAX].rstrip() + "…"


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
    블로그·카페는 쓰지 않는다 — 협찬 글을 구분할 방법이 없다 (ADR-016).
    """
    allowed = {outlet.domain: outlet for outlet in outlets}
    headers = {"X-NCP-APIGW-API-KEY-ID": client_id, "X-NCP-APIGW-API-KEY": client_secret}
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
