"""평가제 대조가 쓰는 계획안 조회 (§12 · 지표 4-1).

`evaluation` 이 이것을 부른다. **반대 방향으로 부르지 않는다** — `plans` 는 평가제를 모른다.
"""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.features.plans.models import Plan


@dataclass(frozen=True)
class ConfirmedMonthlyPlan:
    """지표 4-1 이 보는 것만 담는다. `evaluation.judge.PlanFact` 와 칸이 같다."""

    plan_id: int
    class_id: int
    year: int
    month: int


def confirmed_monthly_plans(session: Session, center_id: int) -> list[ConfirmedMonthlyPlan]:
    """그 원의 **확정된** 월간계획안. 초안은 주지 않는다 — 확정 전에는 한 적이 없는 것과 같다.

    대상 월을 `body` 에서 꺼낸다. `target_month` 컬럼이 아니라 `body` 를 보는 이유는,
    그 컬럼을 더하는 마이그레이션 자신이 `body` 에서 값을 채우기 때문이다(#126) —
    `body` 가 원본이고 컬럼은 유도값이다. 여기서 원본을 보면 컬럼이 들어오기 전에도 돈다.

    ponytail: 원 전체를 한 번에 읽는다. 기간으로 거르는 건 부르는 쪽(judge)이 한다 —
              한 원의 월간은 반 수 × 12 라 P0 규모에서 문제가 안 된다. 원이 커지면
              `target_month` 컬럼에 기간 조건을 걸어 좁힌다.
    """
    rows = session.scalars(
        select(Plan).where(
            Plan.center_id == center_id,
            Plan.kind == "monthly",
            Plan.status == "CONFIRMED",
        )
    ).all()
    plans = []
    for row in rows:
        target = (row.body or {}).get("target_month") or {}
        year, month = target.get("calendar_year"), target.get("calendar_month")
        # 대상 월이나 반을 못 읽는 행은 건너뛴다. 평가제가 조용히 틀린 숫자를 내는 것보다
        # 그 행을 안 세는 쪽이 낫다 — 「부족」은 교사가 보고 고칠 수 있다.
        if not isinstance(year, int) or not isinstance(month, int):
            continue
        try:
            class_id = int(row.classroom_ref)
        except (TypeError, ValueError):
            continue
        plans.append(ConfirmedMonthlyPlan(row.id, class_id, year, month))
    return plans
