"""Monthly용 가역 Adapter.

CLAUDE.md §17: 개발/테스트 단계의 가역 Adapter이며 최종 PostgreSQL 구현과
동일시하지 않는다.

`save_count`를 노출하는 이유는 Golden Set의 `plan_persisted: false`를 검증하려면
저장 호출 여부를 관찰해야 하기 때문이다. Yearly `InMemoryPlanRepository`와 같다.

**활성화 판정**은 파일의 `review.domain_owner_approval`에서만 파생한다.
외부 요청자가 지정할 수 없다.
"""

from __future__ import annotations

import json
from pathlib import Path

from ..planning.domain.monthly_plan import MonthlyPlan
from ..planning.domain.monthly_template import MonthlyTemplate
from ..planning.domain.safety_legal_rule import SafetyLegalRule
from .monthly_template_schema import (
    MonthlyTemplateSchemaError,
    parse_monthly_template_payload,
)
from .safety_legal_rule_schema import (
    SafetyLegalRuleSchemaError,
    parse_safety_legal_rule_payload,
)

__all__ = [
    "DEFAULT_SAFETY_RULE_PATH",
    "DEFAULT_TEMPLATE_PATH",
    "WEEK_EXPERIENCE_TEMPLATE_PATH",
    "production_monthly_template_repository",
    "InMemoryMonthlyPlanRepository",
    "JsonMonthlyTemplateRepository",
    "JsonSafetyLegalRuleRepository",
    "MonthlyTemplateSchemaError",
    "SafetyLegalRuleSchemaError",
    "load_safety_legal_rule_from_dict",
    "load_template_from_dict",
]

_DATA_ROOT = Path(__file__).resolve().parents[3] / "data"
DEFAULT_TEMPLATE_PATH = _DATA_ROOT / "templates" / "monthly_template_a.json"
"""Template A v0.1.0. **RULE_ONLY 호환용 기본값이며 바뀌지 않는다.**"""

WEEK_EXPERIENCE_TEMPLATE_PATH = (
    _DATA_ROOT / "templates" / "monthly_template_a_v0_2_0.json"
)
"""Template A v0.2.0. `focus`를 활성화해 **주차별 중심 경험**을 담는다(OD-N18).

v0.1.0을 **대체하지 않는다.** 두 version이 공존하며, RULE_ONLY는 계속 v0.1.0을
쓰고 LLM Planner 경로가 이 version을 명시적으로 선택한다. Use Case가 Mode를 보고
Template을 몰래 바꾸지 않는다.
"""

DEFAULT_SAFETY_RULE_PATH = _DATA_ROOT / "rules" / "safety_education_legal_v1.json"


def load_template_from_dict(
    payload: object, *, approval_override: str | None = None
) -> MonthlyTemplate:
    return parse_monthly_template_payload(payload, approval_override=approval_override)


def load_safety_legal_rule_from_dict(
    payload: object, *, approval_override: str | None = None
) -> SafetyLegalRule:
    return parse_safety_legal_rule_payload(
        payload, approval_override=approval_override
    )


class InMemoryMonthlyPlanRepository:
    """MonthlyPlanRepository의 InMemory 구현."""

    def __init__(self) -> None:
        self._plans: dict[str, MonthlyPlan] = {}
        self.save_count = 0

    def save(self, plan: MonthlyPlan) -> None:
        self._plans[plan.plan_id.value] = plan
        self.save_count += 1

    def get(self, plan_id: str) -> MonthlyPlan | None:
        return self._plans.get(plan_id)

    def find_monthly(
        self, classroom_ref: str, target_month: str
    ) -> MonthlyPlan | None:
        for plan in self._plans.values():
            if (
                plan.classroom_ref == classroom_ref
                and plan.target_month.value == target_month
            ):
                return plan
        return None

    @property
    def stored_count(self) -> int:
        return len(self._plans)


class JsonMonthlyTemplateRepository:
    """JSON 파일 기반 MonthlyTemplateRepository.

    `approval_override`는 테스트가 승인 상태를 주입하기 위한 경로다.
    파일을 수정하지 않는다.
    """

    def __init__(
        self,
        path: Path | str = DEFAULT_TEMPLATE_PATH,
        *,
        approval_override: str | None = None,
        additional_paths: "tuple[Path, ...] | None" = None,
    ) -> None:
        """Args:
        additional_paths: 함께 서빙할 다른 version. **fallback이 아니다** —
            요청된 template_version과 정확히 일치할 때만 반환하고, 못 찾으면
            default로 대체하지 않고 None을 돌려준다.
        """
        self._paths = (Path(path), *(additional_paths or ()))
        self._approval_override = approval_override
        self._cached: dict[tuple[str, str], MonthlyTemplate] | None = None

    def _load(self) -> dict[tuple[str, str], MonthlyTemplate]:
        if self._cached is None:
            loaded: dict[tuple[str, str], MonthlyTemplate] = {}
            for path in self._paths:
                payload = json.loads(path.read_text(encoding="utf-8"))
                template = parse_monthly_template_payload(
                    payload, approval_override=self._approval_override
                )
                ref = template.template_ref
                key = (ref.template_id, ref.template_version)
                if key in loaded:
                    raise MonthlyTemplateSchemaError(
                        f"같은 template version이 두 번 로드됐다: {key}"
                    )
                loaded[key] = template
            self._cached = loaded
        return self._cached

    def get_template(
        self, template_id: str, template_version: str
    ) -> MonthlyTemplate | None:
        return self._load().get((template_id, template_version))


class JsonSafetyLegalRuleRepository:
    """JSON 파일 기반 SafetyLegalRuleRepository."""

    def __init__(
        self,
        path: Path | str = DEFAULT_SAFETY_RULE_PATH,
        *,
        approval_override: str | None = None,
    ) -> None:
        self._path = Path(path)
        self._approval_override = approval_override
        self._cached: SafetyLegalRule | None = None

    def _load(self) -> SafetyLegalRule:
        if self._cached is None:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
            self._cached = parse_safety_legal_rule_payload(
                payload, approval_override=self._approval_override
            )
        return self._cached

    def get_legal_rule(self, legal_rule_version: str) -> SafetyLegalRule | None:
        rule = self._load()
        if rule.legal_rule_version != legal_rule_version:
            return None
        return rule


def production_monthly_template_repository(
    *, approval_override: str | None = None
) -> JsonMonthlyTemplateRepository:
    """두 승인 Template version을 함께 서빙한다.

        v0.1.0   RULE_ONLY 호환. 기존 Plan과 Golden이 쓰는 그대로
        v0.2.0   `focus` 활성. LLM Planner의 주차별 중심 경험을 담는다

    **fallback이 아니다.** 요청한 version과 정확히 일치할 때만 반환한다.
    어느 version을 쓸지는 호출자가 `template_ref`로 명시한다.
    """
    return JsonMonthlyTemplateRepository(
        DEFAULT_TEMPLATE_PATH,
        approval_override=approval_override,
        additional_paths=(WEEK_EXPERIENCE_TEMPLATE_PATH,),
    )
