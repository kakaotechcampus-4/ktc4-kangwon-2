"""생성 선행조건 Gate와 Confirmation Gate.

이 Gate들은 LLM 호출과 저장보다 **먼저** 실행되어야 한다.
tests/golden/yearly_cases.json의 case 5·6·13·14는 모두
`plan_persisted: false`와 `llm_called: false`를 요구한다.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..application.dto import AgeMode, ClassroomContext, PlanningSetup
from ..domain.errors import FailureCategory, blocked, validation_failed
from ..domain.plan import PlanStatus, YearlyPlan
from ..domain.theme_reference import ThemeCatalog

if TYPE_CHECKING:  # pragma: no cover - 타입 전용
    from ..domain.monthly_plan import MonthlyPlan


def require_planning_setup_complete(setup: PlanningSetup) -> None:
    """docs/screen-spec.md §11.1: 계획안 최초 세팅 완료가 생성 조건이다."""
    if not setup.completed:
        raise blocked(
            "planning_initial_setup_must_be_complete",
            FailureCategory.PREREQUISITE_GATE,
            "계획안 최초 세팅이 완료되지 않았다",
        )


SUPPORTED_AGES: frozenset[int] = frozenset({3, 4, 5})
"""P0가 지원하는 연령.

docs/demo-source-of-truth.md §10 / CLAUDE.md §4·§11: 만 3·4·5세.
만 0~2세 영아반은 P0 제외 범위다.
"""


def require_valid_age_configuration(classroom: ClassroomContext) -> None:
    """연령 입력을 검증한다(CLAUDE.md §11).

    - 비어 있을 수 없다.
    - 지원하지 않는 연령은 거부한다.
    - SINGLE이면 정확히 1개, MIXED이면 서로 다른 연령 2개 이상.
    - 명시된 age_mode와 ages가 모순되면 생성하지 않는다.
    """
    ages = classroom.ages

    if not ages:
        raise validation_failed(
            "classroom_requires_at_least_one_age",
            FailureCategory.INPUT_VALIDATION,
            "반 연령이 비어 있다",
        )

    unsupported = sorted(set(ages) - SUPPORTED_AGES)
    if unsupported:
        raise validation_failed(
            "classroom_ages_must_be_supported_by_p0",
            FailureCategory.INPUT_VALIDATION,
            f"P0 지원 연령은 {sorted(SUPPORTED_AGES)}이며 "
            f"{unsupported}는 지원하지 않는다",
        )

    declared = classroom.age_mode

    if declared is AgeMode.MIXED and len(ages) < 2:
        raise validation_failed(
            "mixed_age_requires_at_least_two_distinct_supported_ages",
            FailureCategory.INPUT_VALIDATION,
            f"혼합연령인데 연령이 {sorted(ages)} 하나뿐이다",
        )

    if declared is AgeMode.SINGLE and len(ages) != 1:
        raise validation_failed(
            "single_age_mode_requires_exactly_one_age",
            FailureCategory.INPUT_VALIDATION,
            f"단일연령인데 연령이 {sorted(ages)}로 {len(ages)}개다",
        )

    # age_mode를 명시하지 않은 경우에도 파생 모드가 성립해야 한다.
    if declared is None and classroom.effective_age_mode is AgeMode.MIXED and len(ages) < 2:
        raise validation_failed(
            "mixed_age_requires_at_least_two_distinct_supported_ages",
            FailureCategory.INPUT_VALIDATION,
            f"연령 {sorted(ages)}로는 혼합연령이 성립하지 않는다",
        )


def require_resolved_catalog(
    catalog: ThemeCatalog | None, catalog_id: str, catalog_version: str
) -> ThemeCatalog:
    """catalog_id + catalog_version이 정확히 일치해야 한다."""
    if catalog is None:
        raise validation_failed(
            "catalog_id_and_version_must_resolve_exactly",
            FailureCategory.REFERENCE_VALIDATION,
            f"Catalog를 찾을 수 없다: {catalog_id} / {catalog_version}",
        )
    if catalog.catalog_id != catalog_id or catalog.catalog_version != catalog_version:
        raise validation_failed(
            "catalog_id_and_version_must_resolve_exactly",
            FailureCategory.REFERENCE_VALIDATION,
            f"요청 {catalog_id}/{catalog_version} != 반환 "
            f"{catalog.catalog_id}/{catalog.catalog_version}",
        )
    return catalog


def require_human_approved_catalog(catalog: ThemeCatalog) -> None:
    """CLAUDE.md §8: 사람이 승인한 versioned Catalog만 활성 후보로 취급한다.

    승인 상태는 Repository가 반환한 Catalog의 신뢰 가능한 metadata에서만 읽는다.
    외부 요청자가 이 값을 지정할 수 없다.
    """
    if not catalog.is_active:
        raise blocked(
            "only_human_approved_versioned_theme_reference_is_eligible",
            FailureCategory.PREREQUISITE_GATE,
            f"Catalog {catalog.catalog_version}의 승인 상태가 "
            f"{catalog.activation_status.value}다",
        )


def require_confirmed_parent_yearly(parent: YearlyPlan | None) -> None:
    """월간 생성은 연간 Plan이 CONFIRMED일 때만 허용한다.

    CLAUDE.md §2 / docs/screen-spec.md §8.3.
    이 Slice는 Monthly를 구현하지 않고 Gate만 제공한다
    (tests/golden/yearly_cases.json case 15의 scope_note).
    """
    if parent is None:
        raise blocked(
            "monthly_generation_requires_confirmed_yearly_plan",
            FailureCategory.CONFIRMATION_GATE,
            "상위 연간 Plan이 없다",
        )
    if parent.status is not PlanStatus.CONFIRMED:
        raise blocked(
            "monthly_generation_requires_confirmed_yearly_plan",
            FailureCategory.CONFIRMATION_GATE,
            f"상위 연간 Plan 상태가 {parent.status.value}다",
        )


def require_confirmed_parent_monthly(parent: "MonthlyPlan | None") -> None:
    """주간 생성은 월간 Plan이 CONFIRMED일 때만 허용한다.

    CLAUDE.md §2 / docs/screen-spec.md §8.3.
    이 Slice는 Weekly를 구현하지 않고 Gate만 제공한다.
    `require_confirmed_parent_yearly`와 같은 패턴이다.

    **판정 대상은 "부모 Monthly가 교사에 의해 CONFIRMED 되었는가" 하나뿐이다.**
    Safety compliance / Activity completeness / outdoor Cell completeness /
    ConstraintVerification / LLM 수행 여부는 판정하지 않는다.

    특히 `ConstraintAssessment`가 `NOT_VERIFIED_SOURCE_REQUIRED`라는 이유로
    Gate를 막지 않는다. 2026-09-11 확정 Product Contract상
    `CONFIRMED != Safety verified`이기 때문이다.
    """
    if parent is None:
        raise blocked(
            "weekly_generation_requires_confirmed_monthly_plan",
            FailureCategory.CONFIRMATION_GATE,
            "상위 월간 Plan이 없다",
        )
    if parent.status is not PlanStatus.CONFIRMED:
        raise blocked(
            "weekly_generation_requires_confirmed_monthly_plan",
            FailureCategory.CONFIRMATION_GATE,
            f"상위 월간 Plan 상태가 {parent.status.value}다",
        )
