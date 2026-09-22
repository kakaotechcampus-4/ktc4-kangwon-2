"""승인된 소스 목록 (ADR-015).

승인은 화면이 아니라 **저장소 파일**이다. 이 파일을 고치는 PR 이 승인 절차다.
목록에 없는 채널·언론사에서는 아예 수집하지 않는다 — 검열 1단이 수집 단계에서 끝난다.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

APPROVED_PATH = (
    Path(__file__).resolve().parents[3] / "resources" / "trends" / "approved-sources.yaml"
)


class ApprovalError(Exception):
    """승인 목록이 잘못됐다. 이 예외가 나면 수집을 시작하지 않는다."""


@dataclass(frozen=True, slots=True)
class ApprovedChannel:
    name: str
    channel_id: str
    uploads_playlist_id: str  # scripts/resolve_channels.py 가 채워준다


@dataclass(frozen=True, slots=True)
class ApprovedOutlet:
    name: str
    domain: str  # www. 를 뗀 것. 기사의 originallink 와 대조한다


@dataclass(frozen=True, slots=True)
class ApprovedSources:
    channels: tuple[ApprovedChannel, ...]
    outlets: tuple[ApprovedOutlet, ...]
    news_queries: tuple[str, ...]


def parse(body: dict) -> ApprovedSources:
    channels = tuple(
        ApprovedChannel(
            name=_required(row, "name"),
            channel_id=_required(row, "channel_id"),
            uploads_playlist_id=_required(row, "uploads_playlist_id"),
        )
        for row in body.get("youtube_channels") or []
    )
    outlets = tuple(
        ApprovedOutlet(name=_required(row, "name"), domain=_required(row, "domain").lower())
        for row in body.get("news_outlets") or []
    )
    queries = tuple(str(q).strip() for q in body.get("news_queries") or [])

    _require_unique([c.channel_id for c in channels], "채널")
    _require_unique([o.domain for o in outlets], "언론사 도메인")
    if any(not q for q in queries):
        raise ApprovalError("빈 검색어가 있다")
    return ApprovedSources(channels=channels, outlets=outlets, news_queries=queries)


@lru_cache(maxsize=1)
def load() -> ApprovedSources:
    return parse(yaml.safe_load(APPROVED_PATH.read_text(encoding="utf-8")) or {})


def _required(row: dict, key: str) -> str:
    value = str(row.get(key, "")).strip()
    if not value:
        # 빈 채로 두면 수집은 도는데 결과가 0건이고 원인이 안 보인다.
        raise ApprovalError(f"{key} 가 비어 있다: {row}")
    return value


def _require_unique(values: list[str], label: str) -> None:
    seen = set()
    duplicated = sorted({v for v in values if v in seen or seen.add(v)})
    if duplicated:
        raise ApprovalError(f"{label} 가 중복됐다: {', '.join(duplicated)}")
