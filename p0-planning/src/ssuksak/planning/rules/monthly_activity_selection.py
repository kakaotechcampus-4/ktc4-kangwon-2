"""Monthly Activity 선택 Rule (Sample-derived P0 Rule).

**이 Rule은 국가가 정한 월별 활동을 뜻하지 않는다.**
`data/activities/activity_reference_v0.json`의 `normative_status`는
`SAMPLE_DERIVED_NON_NORMATIVE`이고, 2019 개정 누리과정 고시문은 활동·주제·계획
양식을 규정하지 않고 기관 자율에 위임한다. 아래 우선순위는 실측 Sample에서
파생된 제품 Rule이다.

**순수 Rule이다.** Repository·JSON·MonthlyPlan·LLM에 접근하지 않는다. 이미
resolve된 eligible candidate와 context만 입력으로 받는다. Catalog 조회와 승인
판정은 Adapter가, hard filter는 `ActivityCatalog.eligible_candidates()`가
담당하며 이 모듈은 **ranking만** 한다.

승인된 선택 우선순위 (2026-09-11 M2-B 결정):

    1. 같은 월 다른 주차 Activity 반복 회피 (+ Regenerate의 현재 Activity 회피)
    2. Parent anchor theme_id 매칭
    3. 같은 월 Curriculum Domain 반복 회피
    4. 해당 월 Evidence strength
    5. activity_id stable tie-break

1~4는 전부 **penalty이며 hard filter가 아니다.** 그래서 다음이 자동으로 지켜진다.

- 후보가 하나뿐이면 penalty가 있어도 그 후보가 선택된다.
- 모든 후보가 이미 사용됐어도 후보가 0이 되지 않는다.
- theme match가 없는 후보도 제거되지 않는다.
- `curriculum_links`가 비어 있으면 그 축이 모든 후보에 대해 0이 되어 자동으로
  중립이 된다. 현재 v0 seed catalog가 정확히 이 상태다.

후보가 0이면 Activity를 만들어내지 않고 `NO_ELIGIBLE_CANDIDATE` 결과를 반환한다.
예외를 던지지 않는다 — `outdoor_play`는 Monthly 최소 Contract의 필수값 Section이
아니며 빈 Cell이 정상 상태이기 때문이다. Cell 반영은 M2-C의 몫이다.

Regenerate는 반드시 다른 Activity를 선택해야 하는 Contract가 아니다. 대체 후보가
없으면 현재 Activity를 다시 선택할 수 있다.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from ..application.monthly_dto import ActivitySelectionTrace
from ..domain.activity_reference import ActivityCandidate

__all__ = [
    "RULE_ID",
    "RULE_VERSION",
    "ActivitySelection",
    "context_ranking_sort_key",
    "REASON_AVOIDED_CURRICULUM_REPEAT",
    "REASON_AVOIDED_DISPLAY_QUALITY_ISSUE",
    "REASON_AVOIDED_REPEAT_IN_MONTH",
    "REASON_KEPT_PENALIZED_CANDIDATE",
    "REASON_MATCHED_PARENT_THEME",
    "REASON_NO_ELIGIBLE_CANDIDATE",
    "REASON_ONLY_CANDIDATE",
    "REASON_STRONGER_MONTH_EVIDENCE",
    "REASON_TIE_BREAK_ACTIVITY_ID",
    "select_activity_for_cell",
]

RULE_ID = "monthly.activity.reference_candidate_selection"
RULE_VERSION = "v2"

REASON_NO_ELIGIBLE_CANDIDATE = "NO_ELIGIBLE_CANDIDATE"
REASON_ONLY_CANDIDATE = "ONLY_ELIGIBLE_CANDIDATE"
REASON_AVOIDED_REPEAT_IN_MONTH = "AVOIDED_REPEAT_IN_MONTH"
REASON_MATCHED_PARENT_THEME = "MATCHED_PARENT_THEME"
REASON_AVOIDED_CURRICULUM_REPEAT = "AVOIDED_CURRICULUM_DOMAIN_REPEAT"
REASON_STRONGER_MONTH_EVIDENCE = "STRONGER_MONTH_EVIDENCE"
REASON_TIE_BREAK_ACTIVITY_ID = "TIE_BREAK_STABLE_ACTIVITY_ID"
REASON_KEPT_PENALIZED_CANDIDATE = "KEPT_PENALIZED_CANDIDATE_NO_ALTERNATIVE"
REASON_AVOIDED_DISPLAY_QUALITY_ISSUE = "AVOIDED_CONFIRMED_DISPLAY_QUALITY_ISSUE"


@dataclass(frozen=True, slots=True)
class ActivitySelection:
    """선택 결과. 후보가 없으면 `candidate`가 None이다.

    후보 0을 예외로 표현하지 않는다. 호출자가 결과를 보고 Cell을 비울지
    결정한다(M2-C).
    """

    candidate: ActivityCandidate | None
    trace: ActivitySelectionTrace

    @property
    def has_selection(self) -> bool:
        return self.candidate is not None


def _repeat_penalty(
    candidate: ActivityCandidate,
    used_activity_ids: frozenset[str],
    current_activity_id: str | None,
) -> int:
    """우선순위 1. 같은 월 재사용과 현재 Activity 재선택을 합산한다.

    두 값을 같은 level로 합산하는 이유: 둘 다 "같은 활동의 반복을 피한다"는 하나의
    의도이며, 합산하면 `둘 다 해당(2) > 하나만 해당(1) > 신규(0)` 순서가 자연스럽게
    나온다. hard exclusion이 아니므로 모든 후보가 penalty를 받아도 후보는 남는다.

    Regenerate에서 `used_activity_ids`는 **형제 주차**의 activity_id 집합이며 대상
    Cell 자신은 제외한다. 그 분리는 호출자(Application)가 한다.
    """
    penalty = 0
    if candidate.activity_id in used_activity_ids:
        penalty += 1
    if current_activity_id is not None and candidate.activity_id == current_activity_id:
        penalty += 1
    return penalty


def _theme_penalty(candidate: ActivityCandidate, parent_theme_id: str | None) -> int:
    """우선순위 2. parent anchor theme_id와 매칭되면 0, 아니면 1.

    `theme_id`만 비교한다. label 문자열 비교나 유사도 매칭을 하지 않는다.
    `parent_theme_id`가 없으면 이 축은 전 후보에 대해 중립이다.
    """
    if parent_theme_id is None:
        return 0
    return 0 if candidate.links_theme(parent_theme_id) else 1


def _display_quality_penalty(candidate: ActivityCandidate) -> int:
    """우선순위 3. 사람이 확정한 표시 품질 문제가 있으면 1, 아니면 0.

    **Binary다.** 품질 유형별 가중치를 두지 않는다 — 유형 간 상대 심각도를
    뒷받침할 근거가 아직 없기 때문이다.

    **Hard Filter가 아니다.** 후보를 제거하지 않는다. 모든 후보가 penalty를
    받아도 후보 집합은 그대로 남는다.

    `AUTO_CANDIDATE` / `UNREVIEWED` / 필드 부재(legacy v0.2.0)는 전부 0이다.
    자동 탐지기에 아직 False Positive가 있어, 사람이 확정하지 않은 판정이
    선택을 바꾸면 안 된다.
    """
    return 1 if candidate.has_confirmed_display_issue else 0


def _curriculum_penalty(
    candidate: ActivityCandidate, used_curriculum_domains: Mapping[str, int]
) -> int:
    """우선순위 3. 후보의 영역이 해당 월에서 이미 쓰인 횟수의 합.

    `curriculum_links`가 비어 있으면 0이므로 이 축이 자동으로 중립이 된다. 빈
    링크를 이유로 후보를 차단하거나 오류를 내거나 임의 domain을 만들지 않는다.
    사람이 검토한 링크가 들어오면 그때부터 자연스럽게 작동한다.
    """
    if not used_curriculum_domains:
        return 0
    return sum(
        used_curriculum_domains.get(link.domain, 0) for link in candidate.curriculum_links
    )


def _sort_key(
    candidate: ActivityCandidate,
    *,
    calendar_month: int,
    used_activity_ids: frozenset[str],
    current_activity_id: str | None,
    parent_theme_id: str | None,
    used_curriculum_domains: Mapping[str, int],
):
    """(반복, theme, display quality, curriculum, evidence ↓, activity_id ↑)

    앞에 오는 축이 항상 뒤의 축을 지배한다. 전부 penalty이므로 후보 집합을 줄이지
    않는다.

    **v2에서 display quality 축이 theme 뒤, curriculum 앞에 들어왔다.** theme은
    상위 Plan에서 내려온 의미 제약이므로 표시 품질보다 우선한다. 반대로
    curriculum과 evidence 개수는 표시 품질보다 약한 선호이므로 뒤에 둔다.
    사람이 확정하지 않은 품질 판정은 0이라 **legacy Catalog에서는 v1과 동일한
    순서가 나온다.**
    """
    return (
        _repeat_penalty(candidate, used_activity_ids, current_activity_id),
        _theme_penalty(candidate, parent_theme_id),
        _display_quality_penalty(candidate),
        _curriculum_penalty(candidate, used_curriculum_domains),
        -candidate.evidence_strength_for_month(calendar_month),
        candidate.activity_id,
    )


def context_ranking_sort_key(
    candidate: ActivityCandidate,
    *,
    calendar_month: int,
    parent_theme_id: str | None = None,
):
    """LLM Context 후보 pre-ranking용 정렬 키 (L2에서 추가).

    `select_activity_for_cell`이 쓰는 것과 **정확히 같은 축**을 노출한다. Rule의
    의미를 바꾸지 않는다 — Cell을 고르는 것이 아니라, Context Packet에 넣을
    canonical 후보의 순서를 같은 기준으로 정할 뿐이다.

    Cell 단위 상태(같은 달에 이미 쓴 activity, 재생성 대상의 현재 activity,
    이미 쓴 누리과정 영역)는 Retrieval 시점에 존재하지 않으므로 중립값을 넣는다.
    그 결과 남는 축은 다음과 같다.

        (theme mismatch, display quality, curriculum, evidence ↓, activity_id ↑)
    """
    return _sort_key(
        candidate,
        calendar_month=calendar_month,
        used_activity_ids=frozenset(),
        current_activity_id=None,
        parent_theme_id=parent_theme_id,
        used_curriculum_domains={},
    )


def select_activity_for_cell(
    *,
    candidates: Sequence[ActivityCandidate],
    target_month: str,
    section_key: str,
    week_id: str | None = None,
    parent_theme_id: str | None = None,
    used_activity_ids: frozenset[str] = frozenset(),
    used_curriculum_domains: Mapping[str, int] | None = None,
    current_activity_id: str | None = None,
) -> ActivitySelection:
    """Cell 하나에 쓸 Activity를 결정론적으로 선택한다.

    Args:
        candidates: **이미 hard filter를 통과한** eligible candidate.
            `ActivityCatalog.eligible_candidates()`의 반환값을 그대로 넘긴다.
            승인·연령·월·slot·setting은 여기서 다시 판정하지 않는다.
        target_month: `YYYY-MM`. 달력 월은 여기서 파생한다.
        section_key: 대상 Section. P0에서는 `outdoor_play`.
        week_id: 주차 Cell이면 `YYYY-MM-Wn`, 병합 Cell이면 None.
        parent_theme_id: 상위 Plan의 anchor theme_id. 없으면 theme 축이 중립이다.
        used_activity_ids: 같은 월의 다른 Cell에 이미 배정된 activity_id.
        used_curriculum_domains: 같은 월에서 이미 쓰인 누리과정 영역별 사용 횟수.
        current_activity_id: Regenerate 대상 Cell의 현재 activity_id.
            **hard exclusion이 아니라 penalty다.**

    Returns:
        ActivitySelection. 후보가 없으면 `candidate`가 None이고 trace의 reason이
        `NO_ELIGIBLE_CANDIDATE`다. 예외를 던지지 않는다.
    """
    domains: Mapping[str, int] = used_curriculum_domains or {}
    calendar_month = _calendar_month_of(target_month)

    if not candidates:
        return ActivitySelection(
            candidate=None,
            trace=ActivitySelectionTrace(
                target_month=target_month,
                section_key=section_key,
                week_id=week_id,
                reason=REASON_NO_ELIGIBLE_CANDIDATE,
                rule_id=RULE_ID,
                rule_version=RULE_VERSION,
                candidate_count=0,
                parent_theme_id=parent_theme_id,
            ),
        )

    ranked = sorted(
        candidates,
        key=lambda c: _sort_key(
            c,
            calendar_month=calendar_month,
            used_activity_ids=used_activity_ids,
            current_activity_id=current_activity_id,
            parent_theme_id=parent_theme_id,
            used_curriculum_domains=domains,
        ),
    )
    chosen = ranked[0]

    repeat = _repeat_penalty(chosen, used_activity_ids, current_activity_id)
    theme_pen = _theme_penalty(chosen, parent_theme_id)
    quality_pen = _display_quality_penalty(chosen)
    curriculum_pen = _curriculum_penalty(chosen, domains)
    strength = chosen.evidence_strength_for_month(calendar_month)
    all_penalized = all(
        _repeat_penalty(c, used_activity_ids, current_activity_id) > 0 for c in candidates
    )

    reason = _classify(
        chosen=chosen,
        ranked=ranked,
        calendar_month=calendar_month,
        used_activity_ids=used_activity_ids,
        current_activity_id=current_activity_id,
        parent_theme_id=parent_theme_id,
        used_curriculum_domains=domains,
    )

    return ActivitySelection(
        candidate=chosen,
        trace=ActivitySelectionTrace(
            target_month=target_month,
            section_key=section_key,
            week_id=week_id,
            reason=reason,
            rule_id=RULE_ID,
            rule_version=RULE_VERSION,
            candidate_count=len(candidates),
            selected_activity_id=chosen.activity_id,
            selected_label=chosen.label,
            repeat_penalty=repeat,
            reused_in_month=chosen.activity_id in used_activity_ids,
            is_current_activity=(
                current_activity_id is not None
                and chosen.activity_id == current_activity_id
            ),
            theme_matched=(parent_theme_id is not None and theme_pen == 0),
            parent_theme_id=parent_theme_id,
            display_quality_penalty=quality_pen,
            curriculum_repeat_penalty=curriculum_pen,
            selected_curriculum_domains=tuple(
                link.domain for link in chosen.curriculum_links
            ),
            evidence_strength=strength,
            all_candidates_penalized=all_penalized,
        ),
    )


def _classify(
    *,
    chosen: ActivityCandidate,
    ranked: list[ActivityCandidate],
    calendar_month: int,
    used_activity_ids: frozenset[str],
    current_activity_id: str | None,
    parent_theme_id: str | None,
    used_curriculum_domains: Mapping[str, int],
) -> str:
    """선택 이유를 분류한다. GenerationRun metadata로 추적된다.

    **실효 회피만 기록한다.** 회피 대상이 애초에 후보 집합에 없었으면 회피가
    일어난 것이 아니므로 실제 이유를 기록한다. 이 판정은 reason에만 영향을 주며
    선택 결과를 바꾸지 않는다.
    """
    if len(ranked) == 1:
        return REASON_ONLY_CANDIDATE

    repeat = _repeat_penalty(chosen, used_activity_ids, current_activity_id)
    if repeat > 0:
        # 선택된 후보조차 penalty를 받았다면 회피할 대안이 없었다는 뜻이다.
        return REASON_KEPT_PENALIZED_CANDIDATE

    penalized = [
        c
        for c in ranked
        if _repeat_penalty(c, used_activity_ids, current_activity_id) > 0
    ]
    if penalized:
        return REASON_AVOIDED_REPEAT_IN_MONTH

    if parent_theme_id is not None and chosen.links_theme(parent_theme_id):
        mismatched = [c for c in ranked if not c.links_theme(parent_theme_id)]
        if mismatched:
            return REASON_MATCHED_PARENT_THEME

    if _display_quality_penalty(chosen) == 0:
        # 같은 theme 조건에서 품질 문제가 확정된 후보를 실제로 피했는지
        avoided = [
            c
            for c in ranked
            if _display_quality_penalty(c) > 0
            and _theme_penalty(c, parent_theme_id)
            == _theme_penalty(chosen, parent_theme_id)
            and _repeat_penalty(c, used_activity_ids, current_activity_id) == repeat
        ]
        if avoided:
            return REASON_AVOIDED_DISPLAY_QUALITY_ISSUE

    chosen_curriculum = _curriculum_penalty(chosen, used_curriculum_domains)
    if chosen_curriculum == 0:
        worse = [
            c
            for c in ranked
            if _curriculum_penalty(c, used_curriculum_domains) > 0
            and _theme_penalty(c, parent_theme_id)
            == _theme_penalty(chosen, parent_theme_id)
        ]
        if worse:
            return REASON_AVOIDED_CURRICULUM_REPEAT

    # 앞선 축이 모두 같은 후보들 사이에서 evidence 강도로 갈렸는지 확인한다.
    same_rank = [
        c
        for c in ranked[1:]
        if _repeat_penalty(c, used_activity_ids, current_activity_id) == repeat
        and _theme_penalty(c, parent_theme_id) == _theme_penalty(chosen, parent_theme_id)
        and _display_quality_penalty(c) == _display_quality_penalty(chosen)
        and _curriculum_penalty(c, used_curriculum_domains) == chosen_curriculum
    ]
    if same_rank:
        top = chosen.evidence_strength_for_month(calendar_month)
        if same_rank[0].evidence_strength_for_month(calendar_month) == top:
            return REASON_TIE_BREAK_ACTIVITY_ID
        return REASON_STRONGER_MONTH_EVIDENCE

    return REASON_STRONGER_MONTH_EVIDENCE


def _calendar_month_of(target_month: str) -> int:
    """`YYYY-MM`에서 달력 월을 읽는다.

    형식 검증은 Application 경계(`MonthlyCellAddress`)가 이미 수행한다. 여기서는
    Rule 입력이 잘못됐을 때 조용히 잘못된 월로 계산하지 않도록만 확인한다.
    """
    parts = target_month.split("-")
    if len(parts) != 2 or not parts[1].isdigit():
        raise ValueError(f"target_month는 YYYY-MM이어야 한다: {target_month!r}")
    month = int(parts[1])
    if not 1 <= month <= 12:
        raise ValueError(f"target_month의 월은 1~12여야 한다: {target_month!r}")
    return month
