"""p0-planning 의 `PlanRepository` 포트를 Postgres 로 구현한다.

**연간·월간이 같은 클래스를 쓴다.** 포트가 `PlanRepository[TPlan]` 제네릭이라
저장할 타입만 바꿔 끼우면 된다. 월간용을 따로 만들지 않는다.

**원 하나에 묶인다.** `center_id` 를 생성자에서 받고 모든 조회에 건다. 라우터가
매번 "내 원인가"를 확인하는 방식이면 엔드포인트가 늘 때 반드시 하나를 빠뜨린다.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session
from ssuksak.planning import InvalidDomainValueError, PlanId

from app.features.plans.codec import from_jsonable, to_jsonable
from app.features.plans.models import Plan


def _confirmed_at(body: dict) -> datetime | None:
    """확정 시각은 감사 기록에만 있다. 따로 받으면 본문과 갈라진다."""
    for event in reversed(body.get("audit", {}).get("events", [])):
        if event.get("event_type") == "CONFIRMED":
            return datetime.fromisoformat(event["occurred_at"])
    return None


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
        month = getattr(plan, "target_month", None)  # 월간만 가진다 (MonthlyPlan)
        values = {
            "center_id": self._center_id,
            "kind": self._kind,
            # 연간·월간 모두 이 두 칸을 가진다 (YearlyPlan · MonthlyPlan).
            "school_year": int(plan.school_year),
            "classroom_ref": str(plan.classroom_ref),
            "target_month": None if month is None else month.value,
            # body 에서 꺼낸다. 인자로 따로 받으면 본문과 칸이 어긋난다.
            "status": body["status"],
            "confirmed_at": _confirmed_at(body),
            "body": body,
        }
        if row is None:
            self._session.add(Plan(plan_ref=plan_id.value, sub_themes={}, **values))
        else:
            # 남의 원 계획안을 같은 id 로 덮어쓰지 못하게 한다.
            if row.center_id != self._center_id:
                raise InvalidDomainValueError("다른 원의 계획안이다")
            # 월간 저장소로 같은 id 의 연간을 덮어써 종류를 바꾸지 못하게 한다.
            if row.kind != self._kind:
                raise InvalidDomainValueError("다른 종류의 계획안이다")
            for key, value in values.items():
                setattr(row, key, value)
            # Python 이 아니라 DB 가 더한다 — 동시 저장 둘이 같은 값을 읽고 둘 다 2 를 쓰지 않게.
            row.revision = Plan.revision + 1
        self._session.flush()

    def update_if_revision(
        self, plan_id: PlanId, plan: TPlan, *, expected_revision: int
    ) -> int | None:
        """DRAFT 이고 revision 이 읽은 값 그대로일 때만 덮어쓴다. 새 revision, 못 썼으면 None.

        **비교와 +1 이 UPDATE 한 문장이다**(결정 문서 12.4 D-3 · 12.10). 같은 revision 을 본 두
        요청 중 하나만 지나간다 — 조회해 보고 쓰면 그 사이에 다른 요청이 끼어든다.
        조건의 `status` 는 저장 전 상태다. 확정도 DRAFT → CONFIRMED 저장이라 같은 조건을 탄다.
        None 이면 왜 못 썼는지(없음 · 확정됨 · revision 다름)는 부르는 쪽이 다시 읽어 가른다.
        `save()` 의 +1 은 타지 않는다 — 한 번 저장에 한 번만 오른다.
        """
        if not isinstance(plan_id, PlanId):
            raise InvalidDomainValueError("PostgresPlanRepository requires PlanId keys")
        body = to_jsonable(plan)
        statement = (
            update(Plan)
            .where(
                Plan.plan_ref == plan_id.value,
                Plan.center_id == self._center_id,
                Plan.kind == self._kind,
                Plan.status == "DRAFT",
                Plan.revision == expected_revision,
            )
            .values(
                body=body,
                status=body["status"],
                confirmed_at=_confirmed_at(body),
                revision=Plan.revision + 1,
            )
            .returning(Plan.revision)
            .execution_options(synchronize_session=False)
        )
        return self._session.execute(statement).scalar_one_or_none()

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
