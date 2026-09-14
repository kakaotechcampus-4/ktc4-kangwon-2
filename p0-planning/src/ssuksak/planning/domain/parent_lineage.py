"""Yearly → Monthly lineage.

docs/demo-source-of-truth.md §21.1 (2026-09-11 확정):

    parent_yearly_theme_id는 immutable parent anchor다.

    하지만 Yearly value/theme을 Monthly Cell에 문자 그대로 1:1 복사해야 한다는
    Contract는 아니다. Monthly에서 세부 theme/focus 분화는 허용된다.

    단 parent anchor 자체는 Generate / Edit / Regenerate / Confirm 전 과정에서
    변경 불가이며, LLM이 교체하려 하면 Validation에서 실패해야 한다.

이 타입은 **immutable snapshot**이다. `frozen=True`이고 MonthlyPlan이 이 값을
재대입하는 경로를 두지 않는 것이 anchor 불변성의 구조적 보장이다.

Provenance 4번째 축을 만들지 않는다. lineage는 1축 Evidence Source
(`EvidenceSourceType.PARENT_PLAN`)로 표현되며 이 타입은 Aggregate 편의 필드다.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class ParentYearlyLineage:
    """확정된 상위 Yearly Plan에서 가져온 snapshot.

    `reference_version`을 snapshot으로 두는 이유: Theme Reference는 새 version이
    발행될 수 있으므로 **생성 시점 version을 고정**해야 과거 Monthly의 근거 표시가
    재현된다. reference로 두면 catalog가 갱신될 때 과거 Plan의 근거가 달라진다.
    """

    parent_yearly_plan_id: str
    parent_yearly_period_key: str
    parent_yearly_theme_id: str
    parent_yearly_value: str
    reference_catalog_id: str
    reference_version: str
    confirmed_at: datetime
    confirmed_by: str

    def __post_init__(self) -> None:
        required = {
            "parent_yearly_plan_id": self.parent_yearly_plan_id,
            "parent_yearly_period_key": self.parent_yearly_period_key,
            "parent_yearly_theme_id": self.parent_yearly_theme_id,
            "parent_yearly_value": self.parent_yearly_value,
            "reference_catalog_id": self.reference_catalog_id,
            "reference_version": self.reference_version,
            "confirmed_by": self.confirmed_by,
        }
        for name, value in required.items():
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"ParentYearlyLineage.{name}는 비어 있을 수 없다")
        if not isinstance(self.confirmed_at, datetime):
            raise TypeError("ParentYearlyLineage.confirmed_at은 datetime이어야 한다")

    @property
    def anchor_theme_id(self) -> str:
        """변경 불가 parent anchor. 이름으로 의도를 드러낸다."""
        return self.parent_yearly_theme_id
