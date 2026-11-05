"""확정한 계획안은 확정할 때의 반 이름 · 담임 이름을 쓴다 (ADR-010 결정 1 · ADR-062).

반 수정 API 가 들어와도 제출한 문서의 이름이 바뀌지 않아야 한다. 내보내기는 hwpx 로 열어
양식에 실제로 적힌 글자를 본다. 세계(원 · 반 · 연간)는 월간 API 테스트의 것을 쓴다.
"""

import pytest
import test_monthly_plans_api as monthly
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from app.features.centers.models import Class
from app.features.plans.models import Plan
from app.main import app

client = TestClient(app)

# 세계(원 · 반 · 프로필)와 승인 고정은 월간 API 테스트의 픽스처를 그대로 쓴다.
world = monthly.world
_approved = monthly._approved


def _rename(session, class_id: int, name: str, teacher_name: str) -> None:
    session.execute(
        update(Class).where(Class.id == class_id).values(name=name, teacher_name=teacher_name)
    )
    session.commit()


def _row(session, plan_id: int) -> Plan:
    session.expire_all()
    return session.scalar(select(Plan).where(Plan.id == plan_id))


def _texts(path: str) -> str:
    response = client.get(path)
    assert response.status_code == 200, response.text
    return "\n".join(t or "" for t in monthly._exported_table(response.content)[1])


def test_연간을_확정하면_그_순간의_반_이름이_찍히고_반을_고쳐도_내보내기는_그대로다(world):
    session, class_id = world["session"], world["class_a"]
    old = session.get(Class, class_id)
    old_name, old_teacher = old.name, old.teacher_name
    annual_id = monthly._annual(world["class_a"])

    row = _row(session, annual_id)
    assert (row.class_name, row.teacher_name) == (old_name, old_teacher)

    _rename(session, class_id, "새싹반", "박선생")
    text = _texts(f"/api/plans/{annual_id}/export/hwp")
    assert old_name in text
    assert "새싹반" not in text


def test_확정을_풀었다_다시_확정하면_새_반_이름으로_덮는다(world):
    session, class_id = world["session"], world["class_a"]
    annual_id = monthly._annual(class_id)
    confirmed = _row(session, annual_id)
    before = (confirmed.class_name, confirmed.teacher_name)
    _rename(session, class_id, "새싹반", "박선생")

    assert client.post(f"/api/plans/annual/{annual_id}/unconfirm").status_code == 200
    # 풀어도 값은 남는다 — 지워졌으면(None) 여기서 걸린다
    unconfirmed = _row(session, annual_id)
    assert (unconfirmed.class_name, unconfirmed.teacher_name) == before
    assert client.post(f"/api/plans/annual/{annual_id}/confirm").status_code == 200

    row = _row(session, annual_id)
    assert (row.class_name, row.teacher_name) == ("새싹반", "박선생")
    assert "새싹반" in _texts(f"/api/plans/{annual_id}/export/hwp")


def test_확정인_행에_반_이름이_없으면_DB_가_막는다(world):
    session = world["session"]
    annual_id = monthly._annual(world["class_a"])

    with pytest.raises(IntegrityError):
        session.execute(update(Plan).where(Plan.id == annual_id).values(class_name=None))
        session.flush()
    session.rollback()


def test_초안을_고치는_동안에는_반_이름이_찍히지_않는다(world):
    session = world["session"]
    annual_id = monthly._annual(world["class_a"], confirm=False)
    month = client.get(f"/api/plans/annual/{annual_id}").json()["months"][0]
    edited = client.put(
        f"/api/plans/annual/{annual_id}/months/3",
        json={"theme": "봄 나들이", "sub_themes": month["sub_themes"]},
    )
    assert edited.status_code == 200, edited.text

    row = _row(session, annual_id)
    assert (row.status, row.class_name, row.teacher_name) == ("DRAFT", None, None)


def test_월간_내보내기도_확정_때_찍은_반_이름을_쓴다(world):
    session, class_id = world["session"], world["class_a"]
    old_name = session.get(Class, class_id).name
    plan = monthly._confirmed(world)

    _rename(session, class_id, "새싹반", "박선생")
    text = _texts(f"/api/plans/monthly/{plan['id']}/export/hwp")
    assert old_name in text
    assert "새싹반" not in text
