"""Yearly Plan Validator — 독립 호출 가능한 컴포넌트.

tests/golden/yearly_cases.json의 case 7·8·10·11·12는 `operation`이
`ValidateGeneratedYearlyPlan`이며, 정상 Plan을 만든 뒤 출력을 변조하고
이 Validator를 **단독으로** 호출한다. 그래서 생성 로직과 분리했다.

docs/demo-source-of-truth.md §26 / CLAUDE.md §14:
Validation 실패를 성공으로 저장하거나 조용히 통과시키지 않는다.
"""

from __future__ import annotations

from ..domain.errors import FailureCategory, ViolationCollector
from ..domain.plan import YearlyPlan
from ..domain.provenance import (
    AuditEventType,
    EvidenceSourceType,
    GenerationMethod,
)
from ..domain.theme_reference import ThemeCatalog
from ..rules.periods import expected_period_key_values

_ALLOWED_GENERATED_METHODS = (GenerationMethod.RULE_ONLY, GenerationMethod.RULE_LLM)


def validate_yearly_plan(
    plan: YearlyPlan,
    *,
    catalog: ThemeCatalog | None = None,
    expected_school_year: int | None = None,
    expected_classroom_ref: str | None = None,
    require_theme_reference_evidence: bool = True,
) -> None:
    """Yearly Plan을 검증한다. 위반이 있으면 PlanningError를 던진다.

    Args:
        catalog: Reference resolve 검증에 사용한다. `require_theme_reference_evidence`
            가 True인 동안에는 생략할 수 없다.
        require_theme_reference_evidence: 생성된 Plan은 THEME_REFERENCE Evidence를
            요구한다. Import(`IMPORTED`)나 직접 작성(`MANUAL`) Item이 섞이는
            경로에서는 호출자가 명시적으로 끌 수 있다.

    Raises:
        ValueError: Theme Reference Evidence를 요구하면서 catalog를 주지 않은 경우.
            Reference Validation을 조용히 우회하는 것을 구조적으로 막는다.
    """
    if catalog is None and require_theme_reference_evidence:
        raise ValueError(
            "catalog 없이 Reference Validation을 생략할 수 없다. "
            "Reference 검증을 의도적으로 건너뛰려면 "
            "require_theme_reference_evidence=False를 명시해야 한다."
        )

    v = ViolationCollector()

    _validate_identity(plan, expected_school_year, expected_classroom_ref, v)
    _validate_periods(plan, v)
    _validate_items(plan, v)
    if catalog is not None:
        _validate_reference(plan, catalog, require_theme_reference_evidence, v)
    _validate_provenance(plan, require_theme_reference_evidence, v)

    v.raise_if_any()


# ---------------------------------------------------------------- 개별 검증


def _validate_identity(
    plan: YearlyPlan,
    expected_school_year: int | None,
    expected_classroom_ref: str | None,
    v: ViolationCollector,
) -> None:
    if expected_school_year is not None and plan.school_year != expected_school_year:
        v.add(
            FailureCategory.STRUCTURE_VALIDATION,
            "school_year_is_preserved",
            f"기대 {expected_school_year} != 실제 {plan.school_year}",
        )
    if not plan.classroom_ref or not plan.classroom_ref.strip():
        v.add(
            FailureCategory.STRUCTURE_VALIDATION,
            "classroom_ref_is_required",
            "Plan 소유 classroom_ref가 비어 있다",
        )
    if expected_classroom_ref is not None and plan.classroom_ref != expected_classroom_ref:
        v.add(
            FailureCategory.STRUCTURE_VALIDATION,
            "plan_owner_classroom_matches",
            f"기대 {expected_classroom_ref} != 실제 {plan.classroom_ref}",
        )


def _validate_periods(plan: YearlyPlan, v: ViolationCollector) -> None:
    actual = [mp.period_key.value for mp in plan.month_periods]

    if len(actual) != 12:
        v.add(
            FailureCategory.STRUCTURE_VALIDATION,
            "yearly_plan_has_exactly_twelve_month_periods",
            f"MonthPeriod가 {len(actual)}개다",
        )

    expected = list(expected_period_key_values(plan.school_year))

    duplicates = sorted({k for k in actual if actual.count(k) > 1})
    missing = [k for k in expected if k not in actual]
    unexpected = [k for k in actual if k not in expected]

    if duplicates or missing or unexpected or actual != expected:
        detail_parts = []
        if duplicates:
            detail_parts.append(f"중복={duplicates}")
        if missing:
            detail_parts.append(f"누락={missing}")
        if unexpected:
            detail_parts.append(f"범위 밖={unexpected}")
        if not detail_parts and actual != expected:
            detail_parts.append(f"순서 불일치: {actual}")
        v.add(
            FailureCategory.PERIOD_VALIDATION,
            "academic_months_are_complete_unique_and_ordered",
            "; ".join(detail_parts),
        )


def _validate_items(plan: YearlyPlan, v: ViolationCollector) -> None:
    seen_item_ids: set[str] = set()

    for mp in plan.month_periods:
        theme = mp.theme

        if theme is None:
            v.add(
                FailureCategory.REQUIRED_VALUE_VALIDATION,
                "theme_is_required_and_non_blank_for_every_period",
                "theme Item이 없다",
                period_key=mp.period_key.value,
            )
            continue

        if not theme.value or not theme.value.strip():
            v.add(
                FailureCategory.REQUIRED_VALUE_VALIDATION,
                "theme_is_required_and_non_blank_for_every_period",
                f"theme 값이 공백이다: {theme.value!r}",
                period_key=mp.period_key.value,
                item_id=theme.item_id.value,
            )

        for item in mp.items:
            if not item.item_id.value.strip():
                v.add(
                    FailureCategory.STRUCTURE_VALIDATION,
                    "every_editable_item_has_stable_item_id",
                    "item_id가 비어 있다",
                    period_key=mp.period_key.value,
                )
            if item.item_id.value in seen_item_ids:
                v.add(
                    FailureCategory.STRUCTURE_VALIDATION,
                    "item_id_is_unique_within_plan",
                    f"item_id 중복: {item.item_id.value}",
                    period_key=mp.period_key.value,
                )
            seen_item_ids.add(item.item_id.value)

            if not item.semantic_key.value.strip():
                v.add(
                    FailureCategory.STRUCTURE_VALIDATION,
                    "every_editable_item_has_stable_semantic_key",
                    "semantic_key가 비어 있다",
                    period_key=mp.period_key.value,
                )

        expected_key = f"yearly.month.{mp.period_key.calendar_month:02d}.theme"
        if theme.semantic_key.value != expected_key:
            v.add(
                FailureCategory.STRUCTURE_VALIDATION,
                "theme_semantic_key_matches_period",
                f"기대 {expected_key} != 실제 {theme.semantic_key.value}",
                period_key=mp.period_key.value,
            )


def _validate_reference(
    plan: YearlyPlan,
    catalog: ThemeCatalog,
    require_theme_reference_evidence: bool,
    v: ViolationCollector,
) -> None:
    for mp in plan.month_periods:
        theme = mp.theme
        if theme is None:
            continue

        refs = theme.evidence_of_type(EvidenceSourceType.THEME_REFERENCE)
        if not refs:
            if require_theme_reference_evidence:
                v.add(
                    FailureCategory.PROVENANCE_VALIDATION,
                    "theme_item_requires_theme_reference_evidence",
                    "THEME_REFERENCE Evidence가 없다",
                    period_key=mp.period_key.value,
                )
            continue

        for ref in refs:
            candidate = catalog.get(ref.source_id)

            if candidate is None:
                v.add(
                    FailureCategory.REFERENCE_VALIDATION,
                    "every_theme_id_must_resolve_in_exact_catalog_version",
                    f"theme_id {ref.source_id!r}를 catalog "
                    f"{catalog.catalog_version}에서 찾을 수 없다",
                    period_key=mp.period_key.value,
                )
                continue

            if ref.source_version != catalog.catalog_version:
                v.add(
                    FailureCategory.REFERENCE_VALIDATION,
                    "theme_id_and_source_version_must_resolve_in_exact_catalog_version",
                    f"source_version {ref.source_version!r} != catalog "
                    f"{catalog.catalog_version!r}",
                    period_key=mp.period_key.value,
                )

            if not candidate.supports_month(mp.period_key.calendar_month):
                v.add(
                    FailureCategory.REFERENCE_VALIDATION,
                    "selected_theme_is_applicable_to_period_month",
                    f"{candidate.theme_id}는 {mp.period_key.calendar_month}월에 "
                    f"적용 가능하지 않다 (applicable={list(candidate.applicable_months)})",
                    period_key=mp.period_key.value,
                )

            if not candidate.supports_age_set(plan.classroom_ages):
                v.add(
                    FailureCategory.REFERENCE_VALIDATION,
                    "selected_theme_supports_every_selected_age",
                    f"{candidate.theme_id}가 연령 {sorted(plan.classroom_ages)}를 "
                    f"모두 지원하지 않는다 (supported={list(candidate.supported_ages)})",
                    period_key=mp.period_key.value,
                )


def _validate_provenance(
    plan: YearlyPlan, require_generated_method: bool, v: ViolationCollector
) -> None:
    for mp in plan.month_periods:
        for item in mp.items:
            for ev in item.evidence:
                # EvidenceSourceType에 AI / TEACHER_EDIT가 존재하지 않으므로
                # 값으로는 만들 수 없다. 문자열로 우회 주입된 경우만 잡는다.
                raw = getattr(ev.source_type, "value", ev.source_type)
                if raw in ("AI", "TEACHER_EDIT"):
                    v.add(
                        FailureCategory.PROVENANCE_VALIDATION,
                        "ai_and_teacher_edit_are_not_evidence_sources",
                        f"금지된 Evidence Source: {raw}",
                        period_key=mp.period_key.value,
                    )

            if require_generated_method and item.generation.method not in _ALLOWED_GENERATED_METHODS:
                v.add(
                    FailureCategory.PROVENANCE_VALIDATION,
                    "generated_item_method_is_rule_only_or_rule_llm",
                    f"Generation Method가 {item.generation.method.value}다",
                    period_key=mp.period_key.value,
                )

            if not item.audit.contains(AuditEventType.CREATED):
                v.add(
                    FailureCategory.PROVENANCE_VALIDATION,
                    "item_audit_contains_created",
                    "Item Audit에 CREATED가 없다",
                    period_key=mp.period_key.value,
                )
