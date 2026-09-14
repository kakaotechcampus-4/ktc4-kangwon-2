"""Planning Core의 실패 분류.

tests/golden/yearly_cases.json의 `failure_category`와 `violated_rule`은
Golden Set 내부 의미 식별자다. CLAUDE.md §20 / assertion_policy에 따라
공개 HTTP 오류 코드로 자동 승격하지 않는다. 공개 오류 코드는 OD-N08에서 정한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Outcome(str, Enum):
    """Use Case 실행 결과의 분류."""

    SUCCESS = "SUCCESS"
    BLOCKED = "BLOCKED"
    VALIDATION_FAILED = "VALIDATION_FAILED"


class FailureCategory(str, Enum):
    PREREQUISITE_GATE = "PREREQUISITE_GATE"
    CONFIRMATION_GATE = "CONFIRMATION_GATE"
    PLAN_STATE_GATE = "PLAN_STATE_GATE"
    INPUT_VALIDATION = "INPUT_VALIDATION"
    ACTOR_VALIDATION = "ACTOR_VALIDATION"
    REFERENCE_VALIDATION = "REFERENCE_VALIDATION"
    REFERENCE_CANDIDATE_EMPTY = "REFERENCE_CANDIDATE_EMPTY"
    STRUCTURE_VALIDATION = "STRUCTURE_VALIDATION"
    PERIOD_VALIDATION = "PERIOD_VALIDATION"
    REQUIRED_VALUE_VALIDATION = "REQUIRED_VALUE_VALIDATION"
    PROVENANCE_VALIDATION = "PROVENANCE_VALIDATION"
    LLM_OUTPUT_VALIDATION = "LLM_OUTPUT_VALIDATION"
    LLM_FAILURE = "LLM_FAILURE"
    LLM_CONFIG_ERROR = "LLM_CONFIG_ERROR"


@dataclass(frozen=True, slots=True)
class Violation:
    """단일 위반 사항."""

    category: FailureCategory
    violated_rule: str
    detail: str = ""
    period_key: str | None = None
    item_id: str | None = None

    def __str__(self) -> str:
        where = f" [{self.period_key}]" if self.period_key else ""
        return f"{self.category.value}:{self.violated_rule}{where} {self.detail}".rstrip()


class PlanningError(Exception):
    """Planning Core가 명확한 실패 상태로 반환하는 오류.

    docs/demo-source-of-truth.md §26: Validation 실패를 성공으로 저장하거나
    조용히 통과시키지 않는다.
    """

    def __init__(self, outcome: Outcome, violations: list[Violation]) -> None:
        if not violations:
            raise ValueError("PlanningError에는 최소 하나의 Violation이 필요하다")
        self.outcome = outcome
        self.violations = list(violations)
        super().__init__("; ".join(str(v) for v in self.violations))

    @property
    def primary(self) -> Violation:
        return self.violations[0]

    @property
    def failure_category(self) -> FailureCategory:
        return self.primary.category

    @property
    def violated_rule(self) -> str:
        return self.primary.violated_rule


def blocked(violated_rule: str, category: FailureCategory, detail: str = "") -> PlanningError:
    return PlanningError(Outcome.BLOCKED, [Violation(category, violated_rule, detail)])


def validation_failed(
    violated_rule: str,
    category: FailureCategory,
    detail: str = "",
    period_key: str | None = None,
) -> PlanningError:
    return PlanningError(
        Outcome.VALIDATION_FAILED,
        [Violation(category, violated_rule, detail, period_key=period_key)],
    )


@dataclass(slots=True)
class ViolationCollector:
    """Validator가 여러 위반을 모아서 보고할 때 사용."""

    violations: list[Violation] = field(default_factory=list)

    def add(
        self,
        category: FailureCategory,
        violated_rule: str,
        detail: str = "",
        period_key: str | None = None,
        item_id: str | None = None,
    ) -> None:
        self.violations.append(
            Violation(category, violated_rule, detail, period_key=period_key, item_id=item_id)
        )

    def __bool__(self) -> bool:
        return bool(self.violations)

    def raise_if_any(self) -> None:
        if self.violations:
            raise PlanningError(Outcome.VALIDATION_FAILED, self.violations)
