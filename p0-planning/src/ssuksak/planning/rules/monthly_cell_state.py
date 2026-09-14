"""Section 의미에 따른 Cell 값 정책과 CellState 전이.

2026-09-11 확정:

    RENDER_EMPTY_CELL은 표시·구조 정책이며 **모든 semantic content가 선택사항이라는
    의미가 아니다.**

| Section            | 빈 문자열 | 빈 경우 CellState                     |
|--------------------|-----------|---------------------------------------|
| `theme`            | 금지      | —                                     |
| `outdoor_play`     | 허용      | `EMPTY_VALID`                         |
| `safety_education` | 허용      | Constraint 상태로 결정                |
| 그 밖              | 허용      | `EMPTY_VALID`                         |

`safety_education`은 **교사가 값을 지웠다는 이유만으로 `EMPTY_VALID`로 바꾸지
않는다.** 배치 source가 여전히 없으면 `EMPTY_UNRESOLVED`를 유지한다.
VERIFIED source가 있는 경우의 상세 전이는 M2에서 source integration과 함께
확장한다. M1-C는 현재 존재하는 Constraint 상태만 본다.
"""

from __future__ import annotations

from ..domain.constraint import CellState, ConstraintKind
from ..domain.errors import FailureCategory, validation_failed
from ..domain.monthly_plan import MonthlyPlan

THEME_SECTION_KEY = "theme"
SAFETY_SECTION_KEY = "safety_education"
OUTDOOR_SECTION_KEY = "outdoor_play"

NON_BLANK_REQUIRED_SECTIONS: frozenset[str] = frozenset({THEME_SECTION_KEY})
"""빈 문자열을 허용하지 않는 Section.

`theme`은 Monthly의 의미 anchor content이므로 FILLED 상태를 유지해야 한다.
"""

CONSTRAINT_DRIVEN_SECTIONS: dict[str, ConstraintKind] = {
    SAFETY_SECTION_KEY: ConstraintKind.STATUTORY_SAFETY_EDUCATION,
}
"""빈 Cell 상태가 Constraint 검증 결과로 결정되는 Section."""


def require_value_allowed(section_key: str, value: str) -> None:
    """Section 의미상 빈 문자열이 허용되는지 확인한다."""
    if section_key in NON_BLANK_REQUIRED_SECTIONS and not value.strip():
        raise validation_failed(
            "theme_cell_is_required_and_non_blank",
            FailureCategory.REQUIRED_VALUE_VALIDATION,
            f"{section_key} Cell은 빈 값으로 둘 수 없다",
        )


def resolve_cell_state(
    plan: MonthlyPlan, section_key: str, value: str
) -> CellState:
    """새 값에 대응하는 CellState를 계산한다.

    무조건 `EMPTY_VALID`로 고정하지 않는다. Section 의미와 Constraint 상태를 본다.
    """
    if value.strip():
        return CellState.FILLED

    kind = CONSTRAINT_DRIVEN_SECTIONS.get(section_key)
    if kind is not None:
        assessment = plan.constraint(kind)
        if assessment is not None and assessment.is_unresolved:
            return CellState.EMPTY_UNRESOLVED

    return CellState.EMPTY_VALID
