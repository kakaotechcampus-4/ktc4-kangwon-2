"""유튜브 핸들(@ebskids)을 채널 ID 와 업로드 재생목록 ID 로 바꾼다.

승인 목록(`backend/resources/trends/approved-sources.yaml`)에 붙일 줄을 찍어준다.
**사람이 유튜브에서 채널을 고르고, 이 스크립트가 ID 만 확인한다** — 채널 선택을
AI 나 자동화에 맡기지 않는다 (ADR-015).

    YOUTUBE_API_KEY=... python backend/scripts/resolve_channels.py @ebskids @pinkfong

핸들을 모르면 채널 주소창의 @뒤를 그대로 쓰면 된다.
"""

from __future__ import annotations

import os
import sys

import httpx

API = "https://www.googleapis.com/youtube/v3/channels"


def resolve(handle: str, api_key: str) -> dict[str, str] | None:
    response = httpx.get(
        API,
        params={"part": "snippet,contentDetails", "forHandle": handle, "key": api_key},
        timeout=20.0,
    )
    response.raise_for_status()
    items = response.json().get("items") or []
    if not items:
        return None
    channel = items[0]
    uploads = (channel.get("contentDetails") or {}).get("relatedPlaylists", {}).get("uploads")
    if not uploads:
        return None
    return {
        "name": (channel.get("snippet") or {}).get("title", handle),
        "channel_id": channel["id"],
        "uploads_playlist_id": uploads,
    }


def main(handles: list[str]) -> int:
    api_key = os.environ.get("YOUTUBE_API_KEY")
    if not api_key:
        print("YOUTUBE_API_KEY 가 없다", file=sys.stderr)
        return 1
    if not handles:
        print("핸들을 하나 이상 넘긴다. 예: @ebskids", file=sys.stderr)
        return 1

    missing: list[str] = []
    print("youtube_channels:")
    for handle in handles:
        row = resolve(handle if handle.startswith("@") else f"@{handle}", api_key)
        if row is None:
            missing.append(handle)
            continue
        print(f"  - name: {row['name']}")
        print(f"    channel_id: {row['channel_id']}")
        print(f"    uploads_playlist_id: {row['uploads_playlist_id']}")

    if missing:
        # 못 찾은 것을 조용히 빼면 목록이 조용히 짧아진다.
        print(f"\n못 찾았다: {', '.join(missing)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
