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
    codes = ["도담", "누리", "하람", "가온"]  # 받침이 이름과 같아야 한다
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
    res = _create(klass, kid, [record])
    assert res.status_code == 201, res.text


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


# ── 걸린 문장 고쳐 쓰기 (AI ②) ──────────────────────────────────────────────

_INTERPRETATION = "이가명은 개미를 매일 오래 바라본다. 작은 생물의 움직임에 관심을 보인다."


def _drafted(session):
    klass, (kid,) = _room(session)
    record = _record(session, klass, kid, 5, "이가명이 개미를 오래 바라보았다.")
    made = _create(klass, kid, [record]).json()
    sections = [
        {**s, "body": _INTERPRETATION} if s["heading"] == "해석" else s for s in made["sections"]
    ]
    return made, sections


@pytest.fixture
def writer(monkeypatch):
    from app.features.documents import rewrite as rewrite_module

    seen = {}

    def install(answer):
        def fake(payload):
            seen["payload"] = payload
            return answer

        monkeypatch.setattr(rewrite_module, "_write", fake)

    return install, seen


def _rewrite(doc_id, sections, **extra):
    return client.post(
        f"/api/documents/{doc_id}/rewrite",
        json={
            "heading": "해석",
            "sentence": "이가명은 개미를 매일 오래 바라본다.",
            "style": "fix",
            "reason": "기록에 없는 일이 사실처럼 적혀 있어요.",
            "sections": sections,
            **extra,
        },
    )


def test_고친_문장이_규칙_검사를_지나면_보여_주고_저장하지_않는다(db_session, writer):
    install, seen = writer
    install("도담은 개미를 오래 바라본다.")
    made, sections = _drafted(db_session)

    res = _rewrite(made["id"], sections)

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["sentence"] == "이가명은 개미를 오래 바라본다."
    assert body["blocked"] == []
    # mock 이면 판정하지 않았다고 알린다 — 「확인할 곳 없음」으로 보이지 않게.
    assert body["judge"] == "mock"
    # 모델에는 가명만 간다.
    sent = str(seen["payload"])
    assert "이가명" not in sent and "도담" in sent
    # 저장하지 않는다. 바꿀지는 교사가 고른다.
    detail = client.get(f"/api/documents/{made['id']}").json()
    assert detail["sections"] == made["sections"]


def test_고쳐_쓰기는_이유_칸에_적힌_이름도_가명으로_보낸다(db_session, writer):
    install, seen = writer
    install("도담은 개미를 오래 바라본다.")
    made, sections = _drafted(db_session)

    res = _rewrite(made["id"], sections, reason="가명이가 매일 봤다는 말이 기록에 없어요.")

    assert res.status_code == 200, res.text
    assert seen["payload"]["이유"] == "도담이가 매일 봤다는 말이 기록에 없어요."


def test_고쳐_쓰기도_반_연령_만_4세는_2단에_걸리지_않는다(db_session, writer):
    """다른 다섯 길처럼 반 연령을 넘긴다. 반은 만 4세다(_room)."""
    install, _ = writer
    install("만 4세답게 도담은 개미를 오래 바라본다.")
    made, sections = _drafted(db_session)

    body = _rewrite(made["id"], sections).json()

    assert body["blocked"] == []
    assert body["sentence"] == "만 4세답게 이가명은 개미를 오래 바라본다."


def test_규칙_검사에_걸린_문장은_보여_주지_않는다(db_session, writer):
    install, _ = writer
    install("도담은 개미를 3번 오래 바라본다.")  # 기록에 없는 숫자
    made, sections = _drafted(db_session)

    body = _rewrite(made["id"], sections).json()

    assert body["sentence"] is None
    assert body["blocked"] == ["sections.해석"]


def test_jev_가_짚어도_거르지_않고_확인할_곳으로_같이_준다(db_session, writer, jev):
    install, _ = writer
    install("도담은 개미를 오래 바라본다.")
    made, sections = _drafted(db_session)

    body = _rewrite(made["id"], sections).json()

    assert body["sentence"] == "이가명은 개미를 오래 바라본다."
    assert body["judge"] == "jev"
    assert [i["code"] for i in body["issues"]] == ["UNSUPPORTED_FACT"]
    assert body["issues"][0]["sentence"] == "이가명은 개미를 오래 바라본다."


def test_칸에_없는_문장이나_확정본은_고쳐_쓰지_않는다(db_session, writer):
    install, _ = writer
    install("도담은 개미를 오래 바라본다.")
    made, sections = _drafted(db_session)

    missing = _rewrite(made["id"], sections, sentence="없는 문장이다.")
    assert missing.status_code == 422
    assert missing.json()["error"]["fields"] == ["sentence"]

    db_session.get(Document, made["id"]).status = "CONFIRMED"
    db_session.flush()
    assert _rewrite(made["id"], sections).status_code == 409


# ── 말투 예시 (AI ③) ──────────────────────────────────────────────────────────


def test_말투_예시는_아이가_안_나오는_짧은_문장만_고르고_아이마다_돌려_쓴다():
    from app.features.documents.style import pick_examples

    texts = [
        "이가명은 개미를 오래 바라본다. 작은 생물의 움직임에 관심을 보인다.",
        "「같이 하자」고 말하며 친구에게 다가간다. 놀이 재료를 더 놓아 주면 좋을 것 같다.",
        "가명이가 블록을 쌓는다. 하윤이가 웃었다. 탐색을 이어 가도록 돋보기를 놓아 주겠다.",
        "다음 바깥놀이에서 관찰을 이어 가겠다.",
    ]
    own = [("이가명", "도담", None)]
    picked = pick_examples(texts, own, [], offset=0, limit=10)

    # 이름이 나온 문장(성을 뗀 「가명이」 포함) · 따옴표 · 이름처럼 보이는 「하윤이가」는 뺀다.
    assert picked == [
        "작은 생물의 움직임에 관심을 보인다.",
        "놀이 재료를 더 놓아 주면 좋을 것 같다.",
        "탐색을 이어 가도록 돋보기를 놓아 주겠다.",
        "다음 바깥놀이에서 관찰을 이어 가겠다.",
    ]
    first = pick_examples(texts, own, [], offset=0, limit=2)
    second = pick_examples(texts, own, [], offset=1, limit=2)
    assert first != second and len(first) == len(second) == 2


def test_말투_예시는_초안과_같은_가명표로_외자_부르는_이름_옆_반_아이까지_뺀다():
    """외자 아이(김민)는 「민이가」로 적힌다. 두 글자 이름 꼴 · 등록 이름으로는 못 잡았다."""
    from app.features.documents.style import pick_examples

    own = [("김민", "가람", "민이"), ("최솔", "누리", None)]
    others = [("박서준", "하준", None)]
    texts = [
        "민이가 모래를 깊게 파며 흙을 만진다.",  # 부르는 이름
        "민은 친구 옆에서 끝까지 기다린다.",  # 외자 + 조사
        "솔한테 삽을 건네며 웃는 모습을 보인다.",  # 부르는 이름 없는 외자 + 조사
        "옆 반 서준과 블록을 나누어 쓴다.",  # 옆 반 아이(성을 뗀 이름)
        "오늘은 민 혼자서 정리를 끝까지 해 본다.",  # 홀로 선 외자 — 가릴 수 없다
        "손끝으로 흙의 감촉을 느껴 본다.",
    ]

    assert pick_examples(texts, own, others, offset=0, limit=10) == [
        "손끝으로 흙의 감촉을 느껴 본다."
    ]


def test_전에_확정한_관찰일지에서_말투_예시를_골라_보낸다(db_session, monkeypatch):
    from app.features.documents.models import DocumentSection

    klass, (kid, friend, single) = _room(db_session, names=("이가명", "박친구", "김민"))
    single.call_name = "민이"
    old = Document(
        kind="observation",
        title="박친구 관찰일지 (8월)",
        class_id=klass.id,
        child_id=friend.id,
        start_date=date(2026, 8, 1),
        end_date=date(2026, 8, 31),
        status="CONFIRMED",
        origin="AI",
        stale=False,
        review_note="",
    )
    db_session.add(old)
    db_session.flush()
    db_session.add_all(
        [
            DocumentSection(
                document_id=old.id, heading="사실", body="모래를 팠다.", source_ids=[1]
            ),
            DocumentSection(
                document_id=old.id,
                heading="해석",
                body="박친구는 모래를 깊게 판다. 손끝으로 흙의 감촉을 느껴 본다.",
                source_ids=[1],
            ),
            DocumentSection(
                document_id=old.id,
                heading="지원",
                # 외자 아이를 부른 문장 — 등록 이름(김민)으로는 안 잡힌다.
                body="다음에는 삽과 체를 같이 놓아 주면 좋을 것 같다. "
                "민아 하고 부르면 삽을 들고 온다.",
                source_ids=[1],
            ),
        ]
    )
    db_session.flush()
    record = _record(db_session, klass, kid, 5, "개미를 오래 바라보았다.")
    seen = {}

    def fake_generate(kind, masked_facts, curriculum=(), examples=()):
        seen["examples"] = list(examples)
        return (
            "작은 생물의 움직임에 관심을 보이며 탐색을 경험한다.",
            "다음 바깥놀이에서 돋보기를 놓아 주면 좋을 것 같다.",
        )

    monkeypatch.setattr("app.features.documents.draft._generate", fake_generate)
    res = _create(klass, kid, [record])
    assert res.status_code == 201, res.text

    assert sorted(seen["examples"]) == [
        "다음에는 삽과 체를 같이 놓아 주면 좋을 것 같다.",
        "손끝으로 흙의 감촉을 느껴 본다.",
    ]
