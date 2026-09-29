"""p0-planning 의 `PlanRepository` 포트를 Postgres 로 구현한다.

**연간·월간이 같은 클래스를 쓴다.** 포트가 `PlanRepository[TPlan]` 제네릭이라
저장할 타입만 바꿔 끼우면 된다. 월간용을 따로 만들지 않는다.

**원 하나에 묶인다.** `center_id` 를 생성자에서 받고 모든 조회에 건다. 라우터가
매번 "내 원인가"를 확인하는 방식이면 엔드포인트가 늘 때 반드시 하나를 빠뜨린다.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session
from ssuksak.planning.domain.errors import InvalidDomainValueError
from ssuksak.planning.domain.identifiers import PlanId

from app.features.plans.codec import from_jsonable, to_jsonable
from app.features.plans.models import Plan


class PostgresPlanRepository[TPlan]:
    """한 원의 계획안을 읽고 쓴다.

    `plan_type` 은 되돌릴 때 필요하다 — JSONB 에는 어떤 클래스였는지가 없다.
    """

    def __init__(self, session: Session, *, center_id: int, kind: str, plan_type: type[TPlan]):
        self._session = session
        self._center_id = center_id
        self._kind = kind
        self._plan_type = plan_type

    def save(self, plan_id: PlanId, plan: TPlan) -> None:
        if not isinstance(plan_id, PlanId):
            raise InvalidDomainValueError("PostgresPlanRepository requires PlanId keys")
        body = to_jsonable(plan)
        row = self._session.scalar(select(Plan).where(Plan.plan_ref == plan_id.value))
        values = {
            "center_id": self._center_id,
            "kind": self._kind,
            # 연간·월간 모두 이 두 칸을 가진다 (YearlyPlan · MonthlyPlan).
            "school_year": int(plan.school_year),
            "classroom_ref": str(plan.classroom_ref),
            # body 에서 꺼낸다. 인자로 따로 받으면 본문과 칸이 어긋난다.
            "status": body["status"],
            "body": body,
        }
        if row is None:
            self._session.add(Plan(plan_ref=plan_id.value, sub_themes={}, **values))
        else:
            # 남의 원 계획안을 같은 id 로 덮어쓰지 못하게 한다.
            if row.center_id != self._center_id:
                raise InvalidDomainValueError("다른 원의 계획안이다")
            for key, value in values.items():
                setattr(row, key, value)
        self._session.flush()

    def get(self, plan_id: PlanId) -> TPlan | None:
        if not isinstance(plan_id, PlanId):
            raise InvalidDomainValueError("PostgresPlanRepository requires PlanId keys")
        row = self._session.scalar(
            select(Plan).where(
                Plan.plan_ref == plan_id.value,
                Plan.center_id == self._center_id,
                Plan.kind == self._kind,
            )
        )
        # 남의 원 것은 없는 것과 같다 — shared/auth/ownership.py 와 같은 이유다.
        return None if row is None else from_jsonable(self._plan_type, row.body)
