"""승인된 소스 목록 (ADR-016).

승인은 화면이 아니라 **저장소 파일**이다. 이 파일을 고치는 PR 이 승인 절차다.
목록에 없는 채널·언론사에서는 아예 수집하지 않는다 — 검열 1단이 수집 단계에서 끝난다.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml
from ssuksak.planning.domain.trend import TrendKind

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
    # 계획안 생성에 넘길 때 제목에 종류 낱말이 없으면 쓰는 종류(ADR-072). 빈 값 = 제목으로만 판단.
    # 「제외」 = 이 채널 자료는 생성에 넘기지 않는다(배경음악 · 타이머).
    kind: str = ""
    # 계획안 글에 나오면 고쳐 쓰게 하는 채널 · 캐릭터 낱말(ADR-072 결정 11). PR 이 승인이다.
    name_words: tuple[str, ...] = ()


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
            kind=_kind(row),
            name_words=_name_words(row),
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


def is_approved(source: str, origin: str) -> bool:
    """ADR-016 4단: 지금 승인 목록에 있는 곳에서 왔는가.

    목록에서 뺀 출처의 지난 주 자료를 걸러낸다.

    유튜브는 채널 이름, 기사는 언론사 도메인이 `RawItem.origin` 이다(sources.py).
    모르는 소스는 아니다.
    """
    sources = load()
    if source == "youtube":
        return any(c.name == origin for c in sources.channels)
    if source == "naver_news":
        return any(o.domain == origin for o in sources.outlets)
    return False


def _required(row: dict, key: str) -> str:
    value = str(row.get(key, "")).strip()
    if not value:
        # 빈 채로 두면 수집은 도는데 결과가 0건이고 원인이 안 보인다.
        raise ApprovalError(f"{key} 가 비어 있다: {row}")
    return value


CHANNEL_KINDS = ("", "제외", *(kind.value for kind in TrendKind))


def _kind(row: dict) -> str:
    kind = str(row.get("kind") or "").strip()
    if kind not in CHANNEL_KINDS:
        raise ApprovalError(f"kind 는 {', '.join(k for k in CHANNEL_KINDS if k)} 중 하나다: {row}")
    return kind


def _name_words(row: dict) -> tuple[str, ...]:
    words = row.get("name_words") or []
    if not isinstance(words, list) or any(not str(w).strip() for w in words):
        raise ApprovalError(f"name_words 는 빈 낱말 없는 목록이다: {row}")
    return tuple(str(w).strip() for w in words)


def _require_unique(values: list[str], label: str) -> None:
    seen = set()
    # mypy 는 set.add 의 None 을 값으로 쓴다고 본다 — 처음 본 값만 남기는 관용구다.
    duplicated = sorted({v for v in values if v in seen or seen.add(v)})  # type: ignore[func-returns-value]
    if duplicated:
        raise ApprovalError(f"{label} 가 중복됐다: {', '.join(duplicated)}")
