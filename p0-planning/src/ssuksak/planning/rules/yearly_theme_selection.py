"""Yearly Theme 선택 Rule (Sample-derived P0 Rule).

**이 Rule은 국가가 정한 월별 주제를 뜻하지 않는다.**
data/themes/theme_reference_v0.json의 `normative_status`는
`SAMPLE_DERIVED_NON_NORMATIVE`이고, 2019 개정 누리과정 고시문에는
`주제`·`생활주제`·`연간`·`월간`이 한 번도 등장하지 않는다.
따라서 아래 우선순위는 실측 Sample에서 파생된 제품 Rule이다.

승인된 선택 우선순위 (2026-09-10 결정 2·3, Regenerate 보강 반영):

    1. month / age 조건으로 eligible candidate 필터링
    2. 인접 MonthPeriod Theme과 중복되지 않는 후보 우선
    3. (Regenerate) 그 안에서 현재 Theme과 다른 후보 우선
    4. 현재 월에서 실제 Sample evidence가 더 강한 후보 우선
    5. 최종 동률만 theme_id stable sort로 deterministic tie-break

인접 회피와 현재 Theme 제외는 모두 **hard filter가 아니라 penalty**로 구현한다.
그래서 다음 두 규정이 자동으로 지켜진다.

- "대체 가능한 후보가 없는 경우 동일 Theme 사용은 허용한다"
- "현재 Theme과 다른 후보가 존재하더라도 그 후보가 인접 월 Theme과 충돌하고
  다른 안전한 후보가 없다면, 기존 theme_id를 유지하고 표현만 재생성한다"

penalty 순서상 인접 중복 회피가 현재 Theme 제외보다 앞선다. 즉 인접 충돌을
일으키는 새 후보보다 인접 안전한 현재 Theme을 선호한다.

**reason 분류 기준**
`AVOIDED_ADJACENT_REPEAT`은 `adjacent_theme_ids ∩ eligible_theme_ids`가 비어 있지
않고 그 후보를 penalty 때문에 선택하지 않은 경우에만 기록한다. 인접 Theme이 해당
월의 후보 집합에 아예 없으면 회피가 일어난 것이 아니므로 실제 이유(evidence 강도,
tie-break 등)를 기록한다. 이 판정은 reason과 trace flag에만 영향을 주며 선택 결과를
바꾸지 않는다 — penalty는 후보에만 적용되기 때문이다.

Regenerate는 반드시 theme_id를 변경해야 하는 Contract가 아니다.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..application.dto import ThemeSelectionTrace
from ..domain.errors import FailureCategory, validation_failed
from ..domain.theme_reference import ThemeCandidate, ThemeCatalog

RULE_ID = "yearly.theme.sample_derived_candidate_selection"
RULE_VERSION = "v2"

REASON_ONLY_CANDIDATE = "ONLY_ELIGIBLE_CANDIDATE"
REASON_STRONGER_EVIDENCE = "STRONGER_MONTH_EVIDENCE"
REASON_AVOIDED_ADJACENT_REPEAT = "AVOIDED_ADJACENT_REPEAT"
REASON_EXCLUDED_CURRENT = "EXCLUDED_CURRENT_THEME_ON_REGENERATE"
REASON_KEPT_CURRENT_TO_AVOID_ADJACENT = "KEPT_CURRENT_THEME_TO_AVOID_ADJACENT_REPEAT"
REASON_KEPT_SOLE_CANDIDATE = "KEPT_SOLE_CANDIDATE_NO_ALTERNATIVE"
REASON_TIE_BREAK_THEME_ID = "TIE_BREAK_STABLE_THEME_ID"


@dataclass(frozen=True, slots=True)
class ThemeSelection:
    candidate: ThemeCandidate
    trace: ThemeSelectionTrace


def _sort_key(
    candidate: ThemeCandidate,
    calendar_month: int,
    adjacent: frozenset[str],
    exclude: frozenset[str],
):
    """(인접 중복 penalty, 현재 Theme penalty, evidence 강도 ↓, theme_id ↑)"""
    adjacent_penalty = 1 if candidate.theme_id in adjacent else 0
    current_penalty = 1 if candidate.theme_id in exclude else 0
    strength = candidate.evidence_strength_for_month(calendar_month)
    return (adjacent_penalty, current_penalty, -strength, candidate.theme_id)


def select_theme_for_period(
    *,
    catalog: ThemeCatalog,
    period_key: str,
    calendar_month: int,
    ages: frozenset[int],
    adjacent_theme_ids: frozenset[str] = frozenset(),
    exclude_theme_id: str | None = None,
) -> ThemeSelection:
    """한 기간의 Theme을 결정론적으로 선택한다.

    Args:
        adjacent_theme_ids: 인접 MonthPeriod에서 이미 확정된 theme_id 집합.
            Generate는 직전 월만, Regenerate는 직전·직후 월 모두 전달한다.
        exclude_theme_id: Regenerate에서 현재 Theme을 후순위로 밀기 위한 값.

    Raises:
        PlanningError: eligible 후보가 하나도 없는 경우
            (REFERENCE_CANDIDATE_EMPTY). LLM에 대체 Theme 생성을 요청하지 않는다.
    """
    eligible = catalog.eligible_candidates(calendar_month, ages)
    eligible_ids = tuple(sorted(c.theme_id for c in eligible))

    if not eligible:
        raise validation_failed(
            "rule_must_select_from_eligible_reference_candidates",
            FailureCategory.REFERENCE_CANDIDATE_EMPTY,
            f"{period_key}(월={calendar_month}, 연령={sorted(ages)})에 적용 가능한 "
            f"Theme 후보가 없다",
            period_key=period_key,
        )

    adjacent = frozenset(adjacent_theme_ids)
    exclude = frozenset({exclude_theme_id}) if exclude_theme_id else frozenset()

    ranked = sorted(
        eligible, key=lambda c: _sort_key(c, calendar_month, adjacent, exclude)
    )
    chosen = ranked[0]
    strength = chosen.evidence_strength_for_month(calendar_month)

    # **실효 회피 대상만 센다.**
    # `adjacent`/`exclude`에 들어 있어도 해당 월의 eligible 후보가 아니면 애초에
    # 선택될 수 없으므로 회피가 일어난 것이 아니다. penalty는 후보에만 적용되므로
    # 아래 교집합이 실제로 회피·제외가 발생한 집합이다.
    eligible_id_set = {c.theme_id for c in eligible}
    effective_adjacent = frozenset(adjacent & eligible_id_set)
    effective_exclude = frozenset(exclude & eligible_id_set)

    reason = _classify(
        chosen=chosen,
        ranked=ranked,
        eligible=eligible,
        calendar_month=calendar_month,
        adjacent=effective_adjacent,
        exclude=effective_exclude,
    )

    trace = ThemeSelectionTrace(
        period_key=period_key,
        selected_theme_id=chosen.theme_id,
        reason=reason,
        rule_id=RULE_ID,
        rule_version=RULE_VERSION,
        eligible_theme_ids=eligible_ids,
        evidence_strength=strength,
        avoided_adjacent_repeat=bool(effective_adjacent)
        and chosen.theme_id not in effective_adjacent,
        # 요청된 회피·제외 대상 전체를 기록한다(후보가 아니었던 것도 포함).
        excluded_theme_ids=tuple(sorted(adjacent | exclude)),
    )
    return ThemeSelection(candidate=chosen, trace=trace)


def _classify(
    *,
    chosen: ThemeCandidate,
    ranked: list[ThemeCandidate],
    eligible: tuple[ThemeCandidate, ...],
    calendar_month: int,
    adjacent: frozenset[str],
    exclude: frozenset[str],
) -> str:
    """선택 이유를 분류한다. GenerationRun metadata로 추적된다.

    `adjacent`와 `exclude`는 **eligible 후보와 교집합을 취한 실효 집합**을 받는다.
    후보가 아니었던 theme_id는 회피 대상이 될 수 없으므로 호출자가 미리 걸러낸다.
    그래서 회피가 일어나지 않았는데 AVOIDED_ADJACENT_REPEAT로 기록되지 않는다.
    """
    if len(eligible) == 1:
        return REASON_ONLY_CANDIDATE

    ids = {c.theme_id for c in eligible}
    adjacent_safe = ids - adjacent

    # 인접 충돌을 피하려고 현재 Theme을 유지한 경우
    if chosen.theme_id in exclude and chosen.theme_id not in adjacent:
        other_safe = adjacent_safe - exclude
        if not other_safe:
            return REASON_KEPT_CURRENT_TO_AVOID_ADJACENT

    # 인접·현재 penalty를 모두 받는 후보만 남은 경우
    if chosen.theme_id in adjacent and chosen.theme_id in exclude:
        return REASON_KEPT_SOLE_CANDIDATE
    if chosen.theme_id in adjacent and not adjacent_safe:
        return REASON_KEPT_SOLE_CANDIDATE

    if exclude and chosen.theme_id not in exclude:
        return REASON_EXCLUDED_CURRENT

    if adjacent and chosen.theme_id not in adjacent:
        return REASON_AVOIDED_ADJACENT_REPEAT

    same_penalty = [
        c
        for c in ranked[1:]
        if (c.theme_id in adjacent) == (chosen.theme_id in adjacent)
        and (c.theme_id in exclude) == (chosen.theme_id in exclude)
    ]
    if same_penalty:
        top_strength = chosen.evidence_strength_for_month(calendar_month)
        if same_penalty[0].evidence_strength_for_month(calendar_month) == top_strength:
            return REASON_TIE_BREAK_THEME_ID

    return REASON_STRONGER_EVIDENCE


def adjacent_theme_ids_for(plan, target_period_key: str) -> frozenset[str]:
    """Plan에서 대상 기간의 직전·직후 MonthPeriod Theme id를 모은다.

    Regenerate가 인접 중복을 회피하기 위해 사용한다.
    """
    from ..domain.provenance import EvidenceSourceType

    keys = [mp.period_key.value for mp in plan.month_periods]
    if target_period_key not in keys:
        return frozenset()

    index = keys.index(target_period_key)
    neighbours: set[str] = set()

    for offset in (-1, 1):
        pos = index + offset
        if 0 <= pos < len(plan.month_periods):
            theme = plan.month_periods[pos].theme
            refs = theme.evidence_of_type(EvidenceSourceType.THEME_REFERENCE)
            if refs:
                neighbours.add(refs[0].source_id)

    return frozenset(neighbours)
