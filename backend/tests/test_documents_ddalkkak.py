"""관찰일지 딸깍(묶음 B) — 반 전체 초안이 기대는 서버 동작. 실제 DB, 모델은 mock 이다.

- 같은 아이 · 같은 기간 · 같은 종류 초안은 하나다. 다시 누르면 있던 것을 돌려준다.
- 「넣어서 다시」(`replace_draft`)는 새 초안을 만든 뒤에만 옛 초안을 지운다.
"""

from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.features.centers.models import Center, Child, Class
from app.features.documents.models import Document
from app.features.observations.models import Observation
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _logged_in(db_session, teacher):
    db_session.info["teacher"] = teacher


def _room(session, names=("이가명",)):
    center = Center(
        name="테스트어린이집",
        director_name="김원장",
        region_sido="충청북도",
        region_sigungu="충주시",
    )
    session.add(center)
    session.flush()
    klass = Class(
        center_id=center.id,
        name="햇살반",
        school_year=2026,
        age_min=4,
        age_max=4,
        teacher_name="김선생",
    )
    session.add(klass)
    session.flush()
    codes = ["도담", "하람", "누리", "가온"]
    kids = []
    for name, code in zip(names, codes, strict=False):
        kid = Child(class_id=klass.id, name=name, code=code)
        session.add(kid)
        kids.append(kid)
    session.flush()
    session.info["teacher"].center_id = center.id
    return klass, kids


def _record(session, klass, child, day, fact):
    row = Observation(
        class_id=klass.id,
        child_id=child.id,
        date=date(2026, 9, day),
        domain="자연탐구",
        context="바깥놀이",
        fact=fact,
    )
    session.add(row)
    session.flush()
    return row


def _create(klass, child, records, **extra):
    return client.post(
        "/api/documents",
        json={
            "kind": "observation",
            "class_id": klass.id,
            "child_id": child.id,
            "start": "2026-09-01",
            "end": "2026-09-30",
            "source_ids": [r.id for r in records],
            **extra,
        },
    )


# ── 같은 초안은 하나 ─────────────────────────────────────────────────────────


def test_같은_아이_같은_기간_초안이_있으면_새로_만들지_않고_돌려준다(db_session, monkeypatch):
    klass, (kid,) = _room(db_session)
    first = _record(db_session, klass, kid, 5, "개미를 오래 바라보았다.")
    made = _create(klass, kid, [first])
    assert made.status_code == 201

    def must_not_call(*args, **kwargs):
        raise AssertionError("이미 있으면 모델을 부르지 않는다")

    monkeypatch.setattr("app.features.documents.router.draft_sections", must_not_call)
    again = _create(klass, kid, [first])

    # 새로 만든 것이 아니라서 201 이 아니다. 있던 초안을 그대로 준다.
    assert again.status_code == 200
    assert again.json()["id"] == made.json()["id"]
    assert db_session.query(Document).count() == 1


def test_기간이_다르거나_확정본이면_새로_만든다(db_session):
    klass, (kid,) = _room(db_session)
    record = _record(db_session, klass, kid, 5, "개미를 오래 바라보았다.")
    week = _create(klass, kid, [record], start="2026-09-01", end="2026-09-07")
    assert week.status_code == 201
    month = _create(klass, kid, [record])
    assert month.status_code == 201

    db_session.get(Document, month.json()["id"]).status = "CONFIRMED"
    db_session.flush()
    # 확정본은 덮지 않는다 — 같은 기간의 새 초안은 따로 생긴다.
    assert _create(klass, kid, [record]).status_code == 201


def test_넣어서_다시는_새_기록까지_넣어_만들고_옛_초안을_지운다(db_session):
    klass, (kid,) = _room(db_session)
    first = _record(db_session, klass, kid, 5, "개미를 오래 바라보았다.")
    old = _create(klass, kid, [first]).json()
    second = _record(db_session, klass, kid, 9, "무당벌레를 손바닥에 올렸다.")

    redo = _create(klass, kid, [first, second], replace_draft=True)

    assert redo.status_code == 201
    assert [s["id"] for s in redo.json()["sources"]] == [first.id, second.id]
    assert db_session.get(Document, old["id"]) is None
    assert db_session.query(Document).count() == 1


def test_넣어서_다시가_실패하면_옛_초안은_남는다(db_session, monkeypatch):
    from app.features.documents.draft import DraftFailed

    klass, (kid,) = _room(db_session)
    first = _record(db_session, klass, kid, 5, "개미를 오래 바라보았다.")
    old = _create(klass, kid, [first]).json()

    def fails(*args, **kwargs):
        raise DraftFailed("AI 초안을 만들지 못했습니다.")

    monkeypatch.setattr("app.features.documents.router.draft_sections", fails)
    redo = _create(klass, kid, [first], replace_draft=True)

    assert redo.status_code == 500
    assert db_session.get(Document, old["id"]) is not None


def test_만드는_동안_같은_초안이_먼저_저장되면_그것을_돌려준다(db_session, monkeypatch):
    # 두 번 누른 요청이 앞단 검사를 둘 다 지나 모델을 부르는 동안 하나가 먼저 저장된 상황.
    import app.features.documents.router as documents_router

    klass, (kid,) = _room(db_session)
    record = _record(db_session, klass, kid, 5, "개미를 오래 바라보았다.")
    real = documents_router.draft_sections
    landed = {}

    def first_one_lands_meanwhile(*args, **kwargs):
        doc = Document(
            kind="observation",
            title="먼저 온 초안",
            class_id=klass.id,
            child_id=kid.id,
            start_date=date(2026, 9, 1),
            end_date=date(2026, 9, 30),
            status="DRAFT",
            origin="AI",
            stale=False,
            review_note="",
        )
        db_session.add(doc)
        db_session.flush()
        landed["id"] = doc.id
        return real(*args, **kwargs)

    monkeypatch.setattr(documents_router, "draft_sections", first_one_lands_meanwhile)
    response = _create(klass, kid, [record])

    assert response.status_code == 200
    assert response.json()["id"] == landed["id"]
    assert db_session.query(Document).count() == 1


# ── 초안에 AI 검토 붙여 오기 ────────────────────────────────────────────────


def _answers(questions, flag="s1"):
    """한 문장만 기록에 없는 일을 덧붙였다고 답하고 나머지는 문제없음."""
    from app.shared.gates import judge as J

    out = {}
    for name in questions:
        key = name.split(".")[0]
        if name.endswith(".대조"):
            hit = key == flag
            out[name] = {
                "type": "choice",
                "choice": J.NEW_FACT if hit else J.SAME,
                "probabilities": {
                    J.CONFLICT: 0.0,
                    J.SAME: 0.1 if hit else 0.98,
                    J.NEW_FACT: 0.9 if hit else 0.0,
                    J.INTERPRETATION: 0.0 if hit else 0.02,
                },
            }
        elif name.endswith(".근거"):
            out[name] = {"type": "choice", "choice": "없음"}
        elif name == "지원.구체":
            out[name] = {"type": "noul", "noul": 0.95}
        else:
            out[name] = {"type": "noul", "noul": 0.02}
    return out


@pytest.fixture
def jev(monkeypatch):
    from app.features.documents import verify as verify_module

    calls = []

    def fake_decide(state, questions):
        calls.append(questions)
        return _answers(questions)

    monkeypatch.setattr(verify_module, "is_mock", lambda: False)
    monkeypatch.setattr(verify_module, "decide", fake_decide)
    return calls


def test_mock_초안은_검토_못_함으로_붙는다(db_session):
    # mock 판정을 「문제없음」으로 보이게 하지 않는다(ADR-071 결정 7).
    klass, (kid,) = _room(db_session)
    record = _record(db_session, klass, kid, 5, "개미를 오래 바라보았다.")

    made = _create(klass, kid, [record]).json()

    assert made["ai_review"]["state"] == "mock"
    assert made["ai_review"]["issues"] == []
    items = client.get("/api/documents", params={"kind": "observation"}).json()["items"]
    assert items[0]["ai_review_state"] == "mock"


def test_초안을_만들면_검토_결과가_붙고_글을_고치면_떨어진다(db_session, jev):
    klass, (kid,) = _room(db_session)
    record = _record(db_session, klass, kid, 5, "개미를 오래 바라보았다.")

    made = _create(klass, kid, [record]).json()

    assert jev, "만들 때 검토를 같이 돌린다"
    review = made["ai_review"]
    assert review["state"] == "done"
    assert [i["code"] for i in review["issues"]] == ["UNSUPPORTED_FACT"]
    assert review["issues"][0]["heading"] == "해석"
    detail = client.get(f"/api/documents/{made['id']}").json()
    assert detail["ai_review"] == review

    # 검토한 글과 지금 글이 다르면 옛 결과를 지금 글의 결과로 보이지 않는다.
    sections = [
        {**s, "body": "개미를 오래 바라보며 작은 생물에 관심을 보인다."}
        if s["heading"] == "해석"
        else s
        for s in detail["sections"]
    ]
    put = client.put(
        f"/api/documents/{made['id']}",
        json={"sections": sections, "updated_at": detail["updated_at"]},
    )
    assert put.status_code == 200, put.text
    assert put.json()["ai_review"] is None
    items = client.get("/api/documents", params={"kind": "observation"}).json()["items"]
    assert items[0]["ai_review_state"] is None


def test_검토가_실패해도_초안은_남고_검토_못_함이_붙는다(db_session, monkeypatch):
    from app.features.documents import verify as verify_module
    from app.shared.llm import LlmFailed

    def broken(state, questions):
        raise LlmFailed("jev 가 답하지 않았다")

    monkeypatch.setattr(verify_module, "is_mock", lambda: False)
    monkeypatch.setattr(verify_module, "decide", broken)
    klass, (kid,) = _room(db_session)
    record = _record(db_session, klass, kid, 5, "개미를 오래 바라보았다.")

    made = _create(klass, kid, [record])

    assert made.status_code == 201
    review = made.json()["ai_review"]
    assert review["state"] == "failed"
    assert review["message"]


def test_다시_검토하면_결과를_그_글에_묶어_둔다(db_session, jev):
    klass, (kid,) = _room(db_session)
    record = _record(db_session, klass, kid, 5, "개미를 오래 바라보았다.")
    made = _create(klass, kid, [record]).json()
    db_session.get(Document, made["id"]).ai_review = None
    db_session.flush()

    verified = client.post(f"/api/documents/{made['id']}/verify")

    assert verified.status_code == 200
    detail = client.get(f"/api/documents/{made['id']}").json()
    assert detail["ai_review"]["state"] == "done"
    assert detail["ai_review"]["issues"] == verified.json()["issues"]
