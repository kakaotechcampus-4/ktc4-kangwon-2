"""Monthly Plan Validation.

Yearly `validate_yearly_plan.py`와 같은 구조이되 Monthly 의미를 검사한다.
`ViolationCollector`는 domain/errors.py의 것을 그대로 재사용한다.

**빈 Cell 전체에 non-blank validation을 걸지 않는다.** OD-M01이
`RENDER_EMPTY_CELL`을 확정했고 "값이 없다는 사실만으로 생성·저장·확정을
차단하지 않는다"고 명시했다. non-blank는 Section 의미에 따라 개별로만 요구한다.
M1에서 non-blank가 필요한 Section은 `theme` 하나다.
"""

from __future__ import annotations

from ..domain.constraint import CellState, ConstraintKind, ConstraintVerification
from ..domain.errors import FailureCategory, ViolationCollector
from ..domain.identifiers import PeriodKey
from ..domain.monthly_plan import MonthlyPlan, MonthlySection
from ..domain.monthly_template import DisplayMode, MonthlyTemplate, SectionRole
from ..domain.plan import PlanStatus
from ..domain.provenance import AuditEventType, EvidenceSourceType
from ..rules.monthly_week_periods import canonical_week_periods

THEME_SECTION_KEY = "theme"
SAFETY_SECTION_KEY = "safety_education"
OUTDOOR_SECTION_KEY = "outdoor_play"


def validate_monthly_plan(
    plan: MonthlyPlan,
    *,
    template: MonthlyTemplate,
    expected_school_year: int,
    expected_classroom_ref: str,
) -> None:
    """Monthly Plan을 검증한다. 위반이 있으면 PlanningError를 던진다."""
    v = ViolationCollector()

    _validate_identity(plan, expected_school_year, expected_classroom_ref, v)
    _validate_lineage(plan, v)
    _validate_week_periods(plan, v)
    _validate_sections(plan, template, v)
    _validate_cells(plan, v)
    _validate_cell_states(plan, v)
    _validate_constraints(plan, v)

    v.raise_if_any()


# --------------------------------------------------------------- 신원


def _validate_identity(
    plan: MonthlyPlan,
    expected_school_year: int,
    expected_classroom_ref: str,
    v: ViolationCollector,
) -> None:
    if plan.status is not PlanStatus.DRAFT:
        v.add(
            FailureCategory.PLAN_STATE_GATE,
            "generated_monthly_plan_starts_as_draft",
            f"생성 결과 상태가 {plan.status.value}다",
        )
    if plan.school_year != expected_school_year:
        v.add(
            FailureCategory.INPUT_VALIDATION,
            "school_year_is_preserved",
            f"{plan.school_year} != {expected_school_year}",
        )
    if plan.classroom_ref != expected_classroom_ref:
        v.add(
            FailureCategory.INPUT_VALIDATION,
            "plan_owner_classroom_matches",
            f"{plan.classroom_ref} != {expected_classroom_ref}",
        )
    if not plan.daycare_ref.strip():
        v.add(
            FailureCategory.INPUT_VALIDATION,
            "daycare_ref_is_required",
            "daycare_ref가 비어 있다",
        )
    if not plan.template_ref.template_version.strip():
        v.add(
            FailureCategory.REFERENCE_VALIDATION,
            "template_ref_is_required",
            "template_ref가 비어 있다",
        )


# ------------------------------------------------------------ lineage


def _validate_lineage(plan: MonthlyPlan, v: ViolationCollector) -> None:
    lineage = plan.parent_lineage
    if lineage is None:  # pragma: no cover - 타입상 None이 될 수 없다
        v.add(
            FailureCategory.REFERENCE_VALIDATION,
            "monthly_plan_requires_parent_yearly_lineage",
            "parent_lineage가 없다",
        )
        return

    if lineage.parent_yearly_period_key != plan.target_month.value:
        v.add(
            FailureCategory.PERIOD_VALIDATION,
            "parent_period_key_matches_target_month",
            f"{lineage.parent_yearly_period_key} != {plan.target_month.value}",
            period_key=plan.target_month.value,
        )

    theme_section = plan.section(THEME_SECTION_KEY)
    if theme_section is None or not theme_section.items:
        return

    for item in theme_section.items:
        refs = item.evidence_of_type(EvidenceSourceType.THEME_REFERENCE)
        if not refs:
            v.add(
                FailureCategory.PROVENANCE_VALIDATION,
                "theme_cell_requires_theme_reference_evidence",
                "theme Cell에 THEME_REFERENCE Evidence가 없다",
                item_id=item.item_id.value,
            )
            continue
        if refs[0].source_id != lineage.parent_yearly_theme_id:
            v.add(
                FailureCategory.REFERENCE_VALIDATION,
                "parent_theme_id_is_immutable_anchor",
                f"theme Evidence의 theme_id {refs[0].source_id}가 "
                f"anchor {lineage.parent_yearly_theme_id}와 다르다",
                item_id=item.item_id.value,
            )
        if refs[0].source_version != lineage.reference_version:
            v.add(
                FailureCategory.REFERENCE_VALIDATION,
                "parent_reference_version_is_snapshotted",
                f"{refs[0].source_version} != {lineage.reference_version}",
                item_id=item.item_id.value,
            )
        if not item.evidence_of_type(EvidenceSourceType.PARENT_PLAN):
            v.add(
                FailureCategory.PROVENANCE_VALIDATION,
                "theme_cell_requires_parent_plan_evidence",
                "theme Cell에 PARENT_PLAN Evidence가 없다",
                item_id=item.item_id.value,
            )


# -------------------------------------------------------- WeekPeriod


def _validate_week_periods(plan: MonthlyPlan, v: ViolationCollector) -> None:
    expected = canonical_week_periods(PeriodKey(plan.target_month.value))
    actual = plan.week_periods

    if len(actual) != len(expected):
        v.add(
            FailureCategory.PERIOD_VALIDATION,
            "week_periods_match_canonical_policy",
            f"canonical {len(expected)}주인데 Plan은 {len(actual)}주다",
            period_key=plan.target_month.value,
        )
        return

    ids = [w.week_id.value for w in actual]
    if len(set(ids)) != len(ids):
        v.add(
            FailureCategory.PERIOD_VALIDATION,
            "week_ids_are_unique",
            f"week_id가 중복된다: {ids}",
        )

    for index, (got, want) in enumerate(zip(actual, expected), start=1):
        if got.week_id.value != want.week_id.value:
            v.add(
                FailureCategory.PERIOD_VALIDATION,
                "week_ids_match_canonical_policy",
                f"{index}번째 week_id {got.week_id.value} != {want.week_id.value}",
            )
        if got.week_id.ordinal != index:
            v.add(
                FailureCategory.PERIOD_VALIDATION,
                "week_periods_are_ordered",
                f"{index}번째 순번이 {got.week_id.ordinal}이다",
            )
        if got.start_date != want.start_date or got.end_date != want.end_date:
            v.add(
                FailureCategory.PERIOD_VALIDATION,
                "week_dates_are_not_clipped_to_month",
                f"{got.week_id.value} {got.start_date}~{got.end_date} != "
                f"{want.start_date}~{want.end_date}",
            )


# ---------------------------------------------------------- Section


def _validate_sections(
    plan: MonthlyPlan, template: MonthlyTemplate, v: ViolationCollector
) -> None:
    expected_keys = [s.section_key for s in template.activated_sections]
    actual_keys = [s.section_key for s in plan.sections]

    if actual_keys != expected_keys:
        v.add(
            FailureCategory.STRUCTURE_VALIDATION,
            "active_sections_match_template_exactly",
            f"Template 활성 {expected_keys} != Plan {actual_keys}",
        )

    inactive = {s.section_key for s in template.inactive_sections}
    leaked = [k for k in actual_keys if k in inactive]
    if leaked:
        v.add(
            FailureCategory.STRUCTURE_VALIDATION,
            "inactive_sections_are_not_generated",
            f"비활성 Section이 생성됐다: {leaked}",
        )

    for section in plan.sections:
        if section.role is SectionRole.CONTENT and section.display_mode is None:
            v.add(
                FailureCategory.STRUCTURE_VALIDATION,
                "every_active_section_has_explicit_display_mode",
                f"{section.section_key}에 display_mode가 없다",
            )
        if section.role is SectionRole.AXIS and section.items:
            v.add(
                FailureCategory.STRUCTURE_VALIDATION,
                "axis_section_has_no_items",
                f"AXIS Section {section.section_key}에 Item이 {len(section.items)}개 있다",
            )


# -------------------------------------------------------------- Cell


def _validate_cells(plan: MonthlyPlan, v: ViolationCollector) -> None:
    active_week_ids = [w.week_id.value for w in plan.active_week_periods]
    seen_item_ids: set[str] = set()

    for section in plan.sections:
        _validate_section_cells(plan, section, active_week_ids, seen_item_ids, v)


def _validate_section_cells(
    plan: MonthlyPlan,
    section: MonthlySection,
    active_week_ids: list[str],
    seen_item_ids: set[str],
    v: ViolationCollector,
) -> None:
    for item in section.items:
        if not item.item_id.value.strip():
            v.add(
                FailureCategory.STRUCTURE_VALIDATION,
                "every_cell_has_stable_item_id",
                "item_id가 비어 있다",
            )
        elif item.item_id.value in seen_item_ids:
            v.add(
                FailureCategory.STRUCTURE_VALIDATION,
                "item_id_is_unique_within_plan",
                f"item_id가 중복된다: {item.item_id.value}",
                item_id=item.item_id.value,
            )
        else:
            seen_item_ids.add(item.item_id.value)

        if item.week_id is not None:
            if item.week_id.target_month != plan.target_month.value:
                v.add(
                    FailureCategory.PERIOD_VALIDATION,
                    "cell_week_id_belongs_to_target_month",
                    f"{item.week_id.value}는 {plan.target_month.value}의 주가 아니다",
                    item_id=item.item_id.value,
                )
            elif item.week_id.value not in active_week_ids:
                v.add(
                    FailureCategory.PERIOD_VALIDATION,
                    "cell_week_id_resolves_to_active_week_period",
                    f"{item.week_id.value}를 활성 WeekPeriod에서 찾을 수 없다",
                    item_id=item.item_id.value,
                )

        if (
            plan.find_cell(
                section_key=section.section_key,
                week_id=item.week_id.value if item.week_id else None,
            )
            is None
        ):
            v.add(
                FailureCategory.STRUCTURE_VALIDATION,
                "every_cell_address_resolves",
                f"주소로 되찾을 수 없는 Cell이다: {section.section_key}",
                item_id=item.item_id.value,
            )

        if not item.audit.contains(AuditEventType.CREATED):
            v.add(
                FailureCategory.PROVENANCE_VALIDATION,
                "cell_audit_contains_created",
                "Cell Audit에 CREATED가 없다",
                item_id=item.item_id.value,
            )

    _validate_cell_count(section, active_week_ids, v)


def _validate_cell_count(
    section: MonthlySection, active_week_ids: list[str], v: ViolationCollector
) -> None:
    if section.role is SectionRole.AXIS:
        return
    if section.display_mode is DisplayMode.MONTHLY_MERGED_SUMMARY:
        if len(section.items) != 1:
            v.add(
                FailureCategory.STRUCTURE_VALIDATION,
                "merged_section_has_exactly_one_cell",
                f"{section.section_key}에 Cell이 {len(section.items)}개다",
            )
        elif section.items[0].week_id is not None:
            v.add(
                FailureCategory.STRUCTURE_VALIDATION,
                "merged_cell_has_no_week_id",
                f"{section.section_key}의 merged Cell에 week_id가 있다",
            )
    elif section.display_mode is DisplayMode.WEEKLY_CELLS:
        if len(section.items) != len(active_week_ids):
            v.add(
                FailureCategory.STRUCTURE_VALIDATION,
                "weekly_section_cell_count_matches_active_weeks",
                f"{section.section_key}에 Cell이 {len(section.items)}개인데 "
                f"활성 주는 {len(active_week_ids)}개다",
            )
        missing = [
            w for w in active_week_ids if section.item_for_week(w) is None
        ]
        if missing:
            v.add(
                FailureCategory.STRUCTURE_VALIDATION,
                "weekly_section_covers_every_active_week",
                f"{section.section_key}에 빠진 주가 있다: {missing}",
            )


# --------------------------------------------------------- CellState


def _validate_cell_states(plan: MonthlyPlan, v: ViolationCollector) -> None:
    """Section 의미에 따른 값 정책.

    빈 Cell 전체에 non-blank를 요구하지 않는다. theme만 non-blank다.
    """
    theme = plan.section(THEME_SECTION_KEY)
    if theme is not None:
        for item in theme.items:
            if not item.value.strip():
                v.add(
                    FailureCategory.REQUIRED_VALUE_VALIDATION,
                    "theme_cell_is_required_and_non_blank",
                    "theme Cell 값이 비어 있다",
                    item_id=item.item_id.value,
                )
            elif item.cell_state is not CellState.FILLED:
                v.add(
                    FailureCategory.STRUCTURE_VALIDATION,
                    "filled_cell_state_matches_value",
                    f"theme Cell 상태가 {item.cell_state.value}다",
                    item_id=item.item_id.value,
                )

    safety = plan.section(SAFETY_SECTION_KEY)
    if safety is not None:
        for item in safety.items:
            if item.value.strip():
                continue  # source가 생겨 값이 채워진 경우는 M2 범위다
            if item.cell_state is not CellState.EMPTY_UNRESOLVED:
                v.add(
                    FailureCategory.STRUCTURE_VALIDATION,
                    "empty_safety_cell_is_unresolved_not_valid",
                    f"배치 source 없는 안전교육 Cell 상태가 {item.cell_state.value}다",
                    item_id=item.item_id.value,
                )

    outdoor = plan.section(OUTDOOR_SECTION_KEY)
    if outdoor is not None:
        for item in outdoor.items:
            if not item.value.strip() and item.cell_state is CellState.FILLED:
                v.add(
                    FailureCategory.STRUCTURE_VALIDATION,
                    "empty_cell_state_matches_value",
                    f"빈 Cell 상태가 {item.cell_state.value}다",
                    item_id=item.item_id.value,
                )


# ------------------------------------------------------- Constraint


def _validate_constraints(plan: MonthlyPlan, v: ViolationCollector) -> None:
    """안전교육 Section이 있으면 Constraint 평가 결과가 있어야 한다.

    `EMPTY_UNRESOLVED` Cell만 있고 설명이 없으면 사용자가 왜 비었는지 알 수 없다.
    """
    safety = plan.section(SAFETY_SECTION_KEY)
    if safety is None:
        return
    assessment = plan.constraint(ConstraintKind.STATUTORY_SAFETY_EDUCATION)
    if assessment is None:
        v.add(
            FailureCategory.STRUCTURE_VALIDATION,
            "safety_section_requires_constraint_assessment",
            "안전교육 Section이 활성인데 ConstraintAssessment가 없다",
        )
        return
    unresolved_cells = [
        i for i in safety.items if i.cell_state is CellState.EMPTY_UNRESOLVED
    ]
    if unresolved_cells and not assessment.is_unresolved:
        v.add(
            FailureCategory.STRUCTURE_VALIDATION,
            "unresolved_cells_match_constraint_verification",
            f"미해결 Cell이 {len(unresolved_cells)}개인데 검증 상태는 "
            f"{assessment.verification.value}다",
        )
    if (
        assessment.verification is ConstraintVerification.NOT_VERIFIED_SOURCE_REQUIRED
        and SAFETY_SECTION_KEY not in assessment.affected_section_keys
    ):
        v.add(
            FailureCategory.STRUCTURE_VALIDATION,
            "constraint_names_affected_sections",
            "미검증 Constraint가 영향 Section을 명시하지 않는다",
        )
