"""계획안 생성이 요구하는 Clock · IdGenerator 의 실제 구현.

p0-planning 에 있는 `FixedClock` · `DeterministicIdGenerator` 는 **테스트용이다.**
그대로 운영에 쓰면 모든 계획안이 같은 시각과 같은 id 를 받는다.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from ssuksak.planning.domain.identifiers import ItemId, PlanId


class SystemClock:
    """실제 시각. 항상 timezone 을 붙여서 준다 — 붙지 않은 시각은 비교할 때 터진다."""

    def now(self) -> datetime:
        return datetime.now(UTC)


class UuidGenerator:
    """충돌하지 않는 id. 교사 여러 명이 같은 순간에 만들어도 안 겹친다."""

    def new_plan_id(self) -> PlanId:
        return PlanId(f"plan_{uuid.uuid4().hex}")

    def new_item_id(self) -> ItemId:
        return ItemId(f"item_{uuid.uuid4().hex}")
