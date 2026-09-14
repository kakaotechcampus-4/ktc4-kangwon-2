"""Monthly Planning Core의 Port.

기존 `PlanRepository`는 `YearlyPlan`으로 타입이 고정돼 있다. 공용화하거나
Generic으로 바꾸면 Yearly 시그니처가 바뀌므로, Monthly는 **별도 Port**를 둔다.

`Clock` / `IdGenerator` / `OptionalContextProvider`는 ports.py의 것을 그대로
재사용한다. 여기에 다시 정의하지 않는다.
"""

from __future__ import annotations

from typing import Protocol

from ..domain.activity_reference import ActivityCatalog
from ..domain.monthly_plan import MonthlyPlan
from ..domain.monthly_template import MonthlyTemplate
from ..domain.safety_legal_rule import SafetyLegalRule

__all__ = [
    "ActivityReferenceRepository",
    "MonthlyPlanRepository",
    "MonthlyTemplateRepository",
    "SafetyLegalRuleRepository",
]


class MonthlyPlanRepository(Protocol):
    def save(self, plan: MonthlyPlan) -> None: ...

    def get(self, plan_id: str) -> MonthlyPlan | None: ...

    def find_monthly(
        self, classroom_ref: str, target_month: str
    ) -> MonthlyPlan | None: ...


class MonthlyTemplateRepository(Protocol):
    """Monthly Template instance 조회.

    반환되는 Template의 활성 여부는 Repository가 승인 상태에서 파생한 값이다.
    외부 요청자가 지정할 수 없다.
    """

    def get_template(
        self, template_id: str, template_version: str
    ) -> MonthlyTemplate | None:
        """정확히 일치하는 template_id + template_version만 반환한다."""
        ...


class SafetyLegalRuleRepository(Protocol):
    """법정 안전교육 Rule 데이터 조회."""

    def get_legal_rule(self, legal_rule_version: str) -> SafetyLegalRule | None:
        """정확히 일치하는 legal_rule_version만 반환한다."""
        ...


class ActivityReferenceRepository(Protocol):
    """Activity Catalog 조회.

    반환되는 ActivityCatalog의 `activation_status`는 Repository가 승인 상태에서
    파생한 값이다. 외부 요청자가 지정할 수 없다.

    `find_candidates(...)`를 두지 않는다. 두면 Repository가 연령·월·slot·theme
    판단을 갖게 되어 selection logic이 Adapter로 새어 나간다.
    `ThemeReferenceRepository`가 `get_catalog` 하나만 두고 hard filter를
    Domain(`ActivityCatalog.eligible_candidates`)에, 순위를 Rule 계층에 둔
    분업을 그대로 따른다.
    """

    def get_catalog(
        self, catalog_id: str, catalog_version: str
    ) -> ActivityCatalog | None:
        """정확히 일치하는 catalog_id + catalog_version만 반환한다."""
        ...
