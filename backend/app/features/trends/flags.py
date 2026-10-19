"""위험 표시 (ADR-016 검열 2단).

**거르지 않는다. 표시만 한다.**

원래는 금칙 낱말이 걸리면 탈락시키기로 했다. 승인 채널 15곳에서 315건을 긁어
실제로 훑어 보니(2026-10-16) 적중 0 · 오탐 4 였고, 오탐 하나가
「젤리인 줄 알고 세제 삼켰을 때, 진짜 올바른 대처법」이었다 — 탈락 규칙이었으면
아이에게 위험을 가르치는 영상이 제일 먼저 버려졌다.

위험한 콘텐츠와 안전교육 콘텐츠는 **같은 낱말을 쓴다.** 글자 대조로는 못 가른다.
가르는 것은 3단(LLM Judge)과 사람이다. 2단은 「여기를 보라」고 가리키기만 한다.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

from app.features.trends.item import RawItem

RISK_PATH = Path(__file__).resolve().parents[3] / "resources" / "trends" / "risk-words.yaml"


@dataclass(frozen=True, slots=True)
class RiskGroup:
    name: str
    why: str
    words: tuple[str, ...]


@lru_cache(maxsize=1)
def load(path: Path | None = None) -> tuple[RiskGroup, ...]:
    body = yaml.safe_load((path or RISK_PATH).read_text(encoding="utf-8")) or {}
    return tuple(
        RiskGroup(
            name=str(group["name"]),
            why=str(group.get("why", "")),
            words=tuple(str(word) for word in group.get("words") or ()),
        )
        for group in body.get("groups") or ()
    )


def flags(item: RawItem, groups: tuple[RiskGroup, ...] | None = None) -> list[str]:
    """걸린 무리 이름. 제목과 설명을 같이 본다.

    **설명까지 본다.** 위험한 동작은 제목에 안 나온다 (ADR-016 3단과 같은 이유).
    """
    text = f"{item.title}\n{item.description}"
    found = [group.name for group in (groups or load()) if any(w in text for w in group.words)]
    # 같은 무리가 여러 낱말로 걸려도 한 번만 적는다 — 세어서 순위를 매기지 않는다.
    return found
