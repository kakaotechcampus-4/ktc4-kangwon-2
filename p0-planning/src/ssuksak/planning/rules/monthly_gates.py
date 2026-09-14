"""Monthly 생성 선행조건 Gate.

이 Gate들은 Optional Context 조회와 저장보다 **먼저** 실행되어야 한다.
실패 시 Monthly Plan 저장 0회 / LLM 호출 0회 / partial Plan 저장 없음이어야 한다.

Application은 Gate 순서를 조립하고 Rule이 판정을 담당한다. 기존 Yearly
`gates.py` 패턴과 같다. `require_confirmed_parent_yearly`는 그것을 재사용한다.
"""

from __future__ import annotations

from ..domain.errors import FailureCategory, blocked, validation_failed
from ..domain.activity_reference import ActivityCatalog
from ..domain.monthly_plan import MonthlyPlan
from ..domain.monthly_template import MonthlyTemplate, TemplateRef
from ..domain.plan import MonthPeriod, PlanItem, YearlyPlan
from ..domain.provenance import EvidenceSource, EvidenceSourceType
from ..domain.safety_legal_rule import SafetyLegalRule
from .periods import expected_period_key_values

__all__ = [
    "require_matching_classroom_owner",
    "require_target_month_in_parent_academic_year",
    "require_parent_month_period",
    "require_parent_theme_reference_evidence",
    "require_catalog_matches_parent_evidence",
    "require_resolved_template",
    "require_active_template_instance",
    "require_resolved_safety_rule",
    "require_active_safety_rule",
    "require_resolved_activity_catalog",
    "require_active_activity_catalog",
    "require_unique_monthly_plan",
]


def require_matching_classroom_owner(parent: YearlyPlan, classroom_ref: str) -> None:
    """Monthly는 상위 Yearly와 같은 classroom을 소유해야 한다(OD-Y03)."""
    if parent.classroom_ref != classroom_ref:
        raise blocked(
            "monthly_plan_owner_must_match_parent_yearly_classroom",
            FailureCategory.CONFIRMATION_GATE,
            f"상위 Yearly의 classroom_ref는 {parent.classroom_ref}인데 "
            f"요청은 {classroom_ref}다",
        )


def require_target_month_in_parent_academic_year(
    parent: YearlyPlan, target_month: str
) -> None:
    """대상 월이 상위 학년도 12개월 안에 있어야 한다.

    학년도는 3월~다음 해 2월이고 1·2월은 school_year + 1이므로
    달력 연도만으로 판단할 수 없다. rules/periods.py를 재사용한다.
    """
    allowed = expected_period_key_values(parent.school_year)
    if target_month not in allowed:
        raise validation_failed(
            "target_month_must_belong_to_parent_academic_year",
            FailureCategory.PERIOD_VALIDATION,
            f"{target_month}는 학년도 {parent.school_year}의 12개월"
            f"({allowed[0]}~{allowed[-1]})에 속하지 않는다",
            period_key=target_month,
        )


def require_parent_month_period(parent: YearlyPlan, target_month: str) -> MonthPeriod:
    """상위 Yearly에 해당 월의 MonthPeriod가 실제로 있어야 한다."""
    period = parent.period(target_month)
    if period is None:
        raise validation_failed(
            "parent_yearly_month_period_must_exist",
            FailureCategory.PERIOD_VALIDATION,
            f"상위 Yearly에 {target_month} MonthPeriod가 없다",
            period_key=target_month,
        )
    return period


def require_parent_theme_reference_evidence(
    theme: PlanItem, target_month: str
) -> EvidenceSource:
    """상위 Theme과 그 Theme Reference Evidence가 유효해야 한다.

    `parent_yearly_theme_id`는 immutable parent anchor이므로 여기서 확정된
    Evidence에서만 읽는다. LLM 응답이나 요청자 입력에서 읽지 않는다.
    """
    if not theme.value or not theme.value.strip():
        raise validation_failed(
            "parent_yearly_theme_must_be_non_blank",
            FailureCategory.REFERENCE_VALIDATION,
            f"상위 Yearly {target_month}의 theme 값이 비어 있다",
            period_key=target_month,
        )
    refs = theme.evidence_of_type(EvidenceSourceType.THEME_REFERENCE)
    if not refs:
        raise validation_failed(
            "parent_yearly_theme_requires_theme_reference_evidence",
            FailureCategory.REFERENCE_VALIDATION,
            f"상위 Yearly {target_month} theme에 THEME_REFERENCE Evidence가 없다",
            period_key=target_month,
        )
    anchor = refs[0]
    if not anchor.source_version:
        raise validation_failed(
            "parent_theme_reference_requires_source_version",
            FailureCategory.REFERENCE_VALIDATION,
            "상위 Theme Evidence에 source_version이 없어 lineage를 snapshot할 수 없다",
            period_key=target_month,
        )
    return anchor


def require_catalog_matches_parent_evidence(
    anchor: EvidenceSource, catalog_id: str, catalog_version: str, target_month: str
) -> None:
    """요청한 catalog가 상위 Theme Evidence와 일치하는지 확인한다.

    Yearly Plan은 `catalog_id`를 저장하지 않으므로 lineage의
    `reference_catalog_id`는 요청자가 명시해야 한다. 그 값이 임의로 들어오지
    못하게 `catalog_version`을 Evidence의 `source_version`과 대조한다.
    """
    if not catalog_id.strip():
        raise validation_failed(
            "monthly_generation_requires_parent_catalog_id",
            FailureCategory.REFERENCE_VALIDATION,
            "상위 Theme Reference catalog_id가 비어 있다",
            period_key=target_month,
        )
    if anchor.source_version != catalog_version:
        raise validation_failed(
            "requested_catalog_version_must_match_parent_theme_evidence",
            FailureCategory.REFERENCE_VALIDATION,
            f"상위 Theme Evidence의 source_version은 {anchor.source_version}인데 "
            f"요청 catalog_version은 {catalog_version}다",
            period_key=target_month,
        )


def require_resolved_template(
    template: MonthlyTemplate | None, ref: TemplateRef
) -> MonthlyTemplate:
    """template_id + template_version이 정확히 일치해야 한다."""
    if template is None:
        raise validation_failed(
            "template_id_and_version_must_resolve_exactly",
            FailureCategory.REFERENCE_VALIDATION,
            f"Template을 찾을 수 없다: {ref}",
        )
    if template.template_ref != ref:
        raise validation_failed(
            "template_id_and_version_must_resolve_exactly",
            FailureCategory.REFERENCE_VALIDATION,
            f"요청 {ref} != 반환 {template.template_ref}",
        )
    return template


def require_active_template_instance(template: MonthlyTemplate) -> None:
    """사람이 승인해 활성화된 Template만 사용한다.

    승인 상태는 Repository가 반환한 Template의 신뢰 가능한 metadata에서만 읽는다.
    """
    if not template.is_active:
        raise blocked(
            "only_human_approved_template_instance_is_eligible",
            FailureCategory.PREREQUISITE_GATE,
            f"Template {template.template_ref}가 활성 상태가 아니다",
        )


def require_resolved_safety_rule(
    rule: SafetyLegalRule | None, legal_rule_version: str
) -> SafetyLegalRule:
    if rule is None:
        raise validation_failed(
            "safety_legal_rule_version_must_resolve_exactly",
            FailureCategory.REFERENCE_VALIDATION,
            f"법정 Safety Rule을 찾을 수 없다: {legal_rule_version}",
        )
    if rule.legal_rule_version != legal_rule_version:
        raise validation_failed(
            "safety_legal_rule_version_must_resolve_exactly",
            FailureCategory.REFERENCE_VALIDATION,
            f"요청 {legal_rule_version} != 반환 {rule.legal_rule_version}",
        )
    return rule


def require_active_safety_rule(rule: SafetyLegalRule) -> None:
    """사람이 승인해 활성화된 법정 Rule만 사용한다."""
    if not rule.is_active:
        raise blocked(
            "only_human_approved_safety_legal_rule_is_eligible",
            FailureCategory.PREREQUISITE_GATE,
            f"법정 Safety Rule {rule.legal_rule_version}가 활성 상태가 아니다",
        )


def require_resolved_activity_catalog(
    catalog: ActivityCatalog | None, catalog_id: str, catalog_version: str
) -> ActivityCatalog:
    """catalog_id + catalog_version이 정확히 일치해야 한다.

    Template / Safety Rule Gate와 같은 규칙이다. 근사 일치나 최신 version
    자동 승격을 하지 않는다. 해소되지 않으면 Reference 실패이며, **후보 0과
    구분된다.** 후보 0은 Catalog가 정상 해소된 뒤의 정상 결과다(M2-C §13).
    """
    if catalog is None:
        raise validation_failed(
            "activity_catalog_id_and_version_must_resolve_exactly",
            FailureCategory.REFERENCE_VALIDATION,
            f"Activity Catalog을 찾을 수 없다: {catalog_id}@{catalog_version}",
        )
    if (catalog.catalog_id, catalog.catalog_version) != (catalog_id, catalog_version):
        raise validation_failed(
            "activity_catalog_id_and_version_must_resolve_exactly",
            FailureCategory.REFERENCE_VALIDATION,
            f"요청 {catalog_id}@{catalog_version} != 반환 "
            f"{catalog.catalog_id}@{catalog.catalog_version}",
        )
    return catalog


def require_active_activity_catalog(catalog: ActivityCatalog) -> None:
    """사람이 승인해 활성화된 Activity Catalog만 사용한다.

    `is_active`는 `domain_owner_approval == HUMAN_APPROVED`에서 파생된다.
    요청자가 승인 상태를 지정하거나 우회하는 경로는 없다.
    """
    if not catalog.is_active:
        raise blocked(
            "only_human_approved_activity_catalog_is_eligible",
            FailureCategory.PREREQUISITE_GATE,
            f"Activity Catalog {catalog.catalog_id}@{catalog.catalog_version}가 "
            "활성 상태가 아니다",
        )


def require_unique_monthly_plan(
    existing: "MonthlyPlan | None", classroom_ref: str, target_month: str
) -> None:
    """동일 (classroom_ref, target_month)에 MonthlyPlan은 최대 1개다.

    2026-09-11 확정된 **SSUKSAK P0 Product Contract**이며 국가·법정 규칙이 아니다.
    `target_month`가 `YYYY-MM`이므로 `school_year`를 uniqueness key에 중복
    포함하지 않는다.

    기존 Plan이 DRAFT면 새로 만들지 말고 그 Plan을 Edit / Regenerate한다.
    CONFIRMED면 read-only다. 어느 경우에도 새 plan_id로 duplicate를 저장해
    revision/version 기능을 흉내 내지 않는다. Plan Revision은 별도 결정이다.
    """
    if existing is None:
        return
    raise blocked(
        "monthly_plan_is_unique_per_classroom_and_target_month",
        FailureCategory.PREREQUISITE_GATE,
        f"{classroom_ref}의 {target_month} MonthlyPlan이 이미 있다"
        f"(plan_id={existing.plan_id.value}, status={existing.status.value}). "
        "새 Plan을 만들지 않는다. 기존 Plan을 편집하거나 재생성한다.",
    )
