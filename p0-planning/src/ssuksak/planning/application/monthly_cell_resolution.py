"""MonthlyCellAddress 해석.

2026-09-11 Cell Address 결정(B안)을 실제 입력 Contract로 강제한다.

    WEEKLY_CELLS            target_month + section_key + week_id
    MONTHLY_MERGED_SUMMARY  target_month + section_key + week_id=None

**`semantic_key` 문자열을 파싱해 week 위치를 찾지 않는다.**
**배열 index를 주소로 쓰지 않는다.**

Edit과 Regenerate가 같은 해석기를 쓴다. 두 경로의 주소 규칙이 갈라지면
"선택한 Cell만 바뀐다"를 보장할 수 없기 때문이다.
"""

from __future__ import annotations

from ..domain.errors import FailureCategory, validation_failed
from ..domain.monthly_plan import MonthlyPlan, MonthlyPlanItem, MonthlySection
from ..domain.monthly_template import DisplayMode, SectionRole
from .monthly_dto import MonthlyCellAddress

__all__ = ["resolve_cell"]


def resolve_cell(
    plan: MonthlyPlan, address: MonthlyCellAddress
) -> tuple[MonthlySection, MonthlyPlanItem]:
    """주소를 하나의 Cell로 해석한다. 모호하거나 없으면 실패한다."""
    if address.target_month != plan.target_month.value:
        raise validation_failed(
            "cell_address_target_month_must_match_plan",
            FailureCategory.INPUT_VALIDATION,
            f"주소의 target_month {address.target_month}가 "
            f"Plan의 {plan.target_month.value}와 다르다",
            period_key=address.target_month,
        )

    section = plan.section(address.section_key)
    if section is None:
        raise validation_failed(
            "cell_address_section_must_exist",
            FailureCategory.INPUT_VALIDATION,
            f"Section을 찾을 수 없다: {address.section_key}",
        )

    if not section.activated:
        raise validation_failed(
            "cell_address_section_must_be_activated",
            FailureCategory.INPUT_VALIDATION,
            f"비활성 Section은 주소로 쓸 수 없다: {address.section_key}",
        )

    if section.role is SectionRole.AXIS:
        raise validation_failed(
            "axis_section_has_no_addressable_cell",
            FailureCategory.INPUT_VALIDATION,
            f"AXIS Section에는 Cell이 없다: {address.section_key}",
        )

    _require_week_shape(section, address)

    if address.week_id is not None:
        week = plan.week_period(address.week_id)
        if week is None:
            raise validation_failed(
                "cell_address_week_id_must_exist_in_plan",
                FailureCategory.PERIOD_VALIDATION,
                f"Plan의 canonical WeekPeriod에 없는 week_id다: {address.week_id}",
            )
        if not week.active:
            raise validation_failed(
                "cell_address_week_must_be_active",
                FailureCategory.PERIOD_VALIDATION,
                f"비활성 WeekPeriod는 주소로 쓸 수 없다: {address.week_id}",
            )

    matches = [
        item
        for item in section.items
        if (item.week_id.value if item.week_id else None) == address.week_id
    ]
    if not matches:
        raise validation_failed(
            "cell_address_must_resolve_to_existing_cell",
            FailureCategory.INPUT_VALIDATION,
            f"주소에 해당하는 Cell이 없다: {address}",
        )
    if len(matches) > 1:  # pragma: no cover - Generate가 중복을 만들지 않는다
        raise validation_failed(
            "cell_address_must_not_be_ambiguous",
            FailureCategory.STRUCTURE_VALIDATION,
            f"주소가 {len(matches)}개 Cell에 해당한다: {address}",
        )

    item = matches[0]
    if address.item_id is not None and address.item_id != item.item_id.value:
        raise validation_failed(
            "cell_address_item_id_must_match_resolved_cell",
            FailureCategory.INPUT_VALIDATION,
            f"주소의 item_id {address.item_id}가 "
            f"해석된 Cell {item.item_id.value}과 다르다",
        )
    return section, item


def _require_week_shape(
    section: MonthlySection, address: MonthlyCellAddress
) -> None:
    """display_mode와 week_id 유무가 맞는지 확인한다."""
    if section.display_mode is DisplayMode.WEEKLY_CELLS and address.week_id is None:
        raise validation_failed(
            "weekly_section_address_requires_week_id",
            FailureCategory.INPUT_VALIDATION,
            f"{section.section_key}는 주별 Cell이므로 week_id가 필요하다",
        )
    if (
        section.display_mode is DisplayMode.MONTHLY_MERGED_SUMMARY
        and address.week_id is not None
    ):
        raise validation_failed(
            "merged_section_address_must_omit_week_id",
            FailureCategory.INPUT_VALIDATION,
            f"{section.section_key}는 월간 병합 Cell이므로 week_id가 없어야 한다: "
            f"{address.week_id}",
        )
