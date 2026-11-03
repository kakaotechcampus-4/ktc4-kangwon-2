"""연간(월별 주제형)에 요청 사항을 남긴다(ADR-057).

주제(theme_id)는 Rule 이 고르므로 메모가 바꾸는 것은 그 달의 소주제다. 소주제는 서버가
따로 생성해 저장하므로, 메모를 반영한 달의 주제 칸에 Evidence 를 붙여 그 달을 표시한다.
"""

from __future__ import annotations

from dataclasses import replace

from ..domain.teacher_memo import MemoNotice
from ..domain.yearly_plan import YearlyPlan
from ..planner.teacher_memo import normalize_teacher_memo, with_memo_evidence


def with_yearly_memo(
    plan: YearlyPlan, memo: str, applied_months: frozenset[int], notices: tuple[MemoNotice, ...]
) -> YearlyPlan:
    memo = normalize_teacher_memo(memo)
    periods = tuple(
        replace(
            p,
            theme=replace(
                p.theme,
                evidence=with_memo_evidence(p.theme.evidence, p.period.calendar_month in applied_months),
            ),
        )
        for p in plan.periods
    )
    return replace(plan, periods=periods, teacher_memo=memo, memo_notices=notices)
