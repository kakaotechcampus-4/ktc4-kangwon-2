"""POST /api/documents/{id}/verify — 3단 게이트 3단(ADR-071). 실제 DB, jev 는 가짜로 바꾼다."""

import json
from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.features.centers.models import Center, Child, Class
from app.features.documents import verify as verify_module
from app.features.documents.models import Document, DocumentSection, DocumentSource
from app.main import app
from app.shared.gates import judge as J

client = TestClient(app)

FACTS = ["이가명이 블록으로 탑을 3층까지 쌓았다.", "이가명이 점심에 당근을 남겼다."]
INTERPRETATION = "이가명은 블록 대신 퍼즐 놀이만 했다. 이가명은 끈기 있게 놀이에 머물렀다."
SUPPORT = "다음 블록 놀이에서 높이를 재어 볼 수 있는 자를 함께 놓아 준다."


@pytest.fixture(autouse=True)
def _logged_in(db_session, teacher):
    db_session.info["teacher"] = teacher


def _document(session, *, kind="observation", origin="AI"):
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
    child = Child(class_id=klass.id, name="이가명", code="도담")
    session.add(child)
    session.flush()
    session.info["teacher"].center_id = center.id
    doc = Document(
        kind=kind,
        title="관찰일지",
        class_id=klass.id,
        child_id=child.id if kind in ("observation", "assessment") else None,
        start_date=date(2026, 11, 3),
        end_date=date(2026, 11, 3) if kind == "dailyLog" else date(2026, 11, 7),
        status="DRAFT",
        origin=origin,
        stale=False,
        review_note="",
    )
    session.add(doc)
    session.flush()
    for i, text in enumerate(FACTS):
        session.add(
            DocumentSource(
                document_id=doc.id,
                source_kind="observation",
                source_id=200 + i,
                class_id=klass.id,
                child_id=child.id,
                date=date(2026, 11, 3 + i),
                text=text,
            )
        )
    ids = [200, 201]
    for heading, body in [
        ("사실", "\n\n".join(FACTS)),
        ("해석", INTERPRETATION),
        ("지원", SUPPORT),
    ]:
        session.add(DocumentSection(document_id=doc.id, heading=heading, body=body, source_ids=ids))
    session.flush()
    return doc


def _answers(questions, *, conflict_on="s1", conflict_rec="r1"):
    """모든 질문에 「문제없음」으로 답하고, 한 문장만 기록과 어긋난다고 답한다."""
    out = {}
    for name in questions:
        key = name.split(".")[0]
        if name.endswith(".대조"):
            hit = key == conflict_on
            out[name] = {
                "type": "choice",
                "choice": J.CONFLICT if hit else J.SAME,
                "probabilities": {
                    J.CONFLICT: 0.97 if hit else 0.01,
                    J.SAME: 0.03 if hit else 0.97,
                    J.NEW_FACT: 0.0,
                    J.INTERPRETATION: 0.02,
                },
            }
        elif name.endswith(".근거"):
            out[name] = {"type": "choice", "choice": conflict_rec if key == conflict_on else "없음"}
        elif name == "지원.구체":
            out[name] = {"type": "noul", "noul": 0.95}
        else:
            out[name] = {"type": "noul", "noul": 0.02}
    return out


@pytest.fixture
def real(monkeypatch):
    seen = []

    def fake_decide(state, questions):
        seen.append(json.dumps({"state": state, "questions": questions}, ensure_ascii=False))
        return _answers(questions)

    monkeypatch.setattr(verify_module, "is_mock", lambda: False)
    monkeypatch.setattr(verify_module, "decide", fake_decide)
    return seen


def _sections(interpretation=INTERPRETATION):
    return [
        {"heading": "사실", "body": "\n\n".join(FACTS), "source_ids": [200, 201]},
        {"heading": "해석", "body": interpretation, "source_ids": [200, 201]},
        {"heading": "지원", "body": SUPPORT, "source_ids": [200, 201]},
    ]


def test_mock_does_not_judge_and_says_so(db_session, monkeypatch):
    doc = _document(db_session)
    monkeypatch.setattr(verify_module, "decide", lambda *_: pytest.fail("mock 에서 부르면 안 된다"))
    res = client.post(f"/api/documents/{doc.id}/verify")
    assert res.status_code == 200
    # 빈 목록만 주면 화면이 「통과」로 읽는다. 판정하지 않았다는 표시가 같이 와야 한다.
    assert res.json() == {"issues": [], "judge": "mock"}


def test_contradiction_points_at_the_record_and_keeps_teacher_names(db_session, real):
    doc = _document(db_session)
    res = client.post(f"/api/documents/{doc.id}/verify")
    assert res.status_code == 200
    body = res.json()
    assert body["judge"] == "jev"
    [issue] = body["issues"]
    assert issue["code"] == "CONTRADICTS_SOURCE"
    assert issue["source_id"] == 200  # r1 → 첫 근거
    assert issue["source_text"] == FACTS[0]  # 화면이 「기록에는 ○○」로 띄우는 원문
    assert issue["sentence"] == "이가명은 블록 대신 퍼즐 놀이만 했다."  # 화면에는 교사가 쓴 이름
    # jev 로 나간 글에는 실명이 없다 (CLAUDE.md 「개인정보」)
    assert "이가명" not in real[0]
    assert "도담" in real[0]


def test_weekday_is_part_of_the_record_line(db_session, real):
    doc = _document(db_session)
    client.post(f"/api/documents/{doc.id}/verify")
    # 11/3 은 화요일이다. 「화요일에 했다」 같은 문장을 가리려면 기록에 요일이 있어야 한다.
    assert "11/3(화)" in real[0]


def test_unsaved_sections_are_judged_but_not_saved(db_session, real):
    doc = _document(db_session)
    edited = "이가명은 블록으로 탑을 쌓으며 높이를 세어 보았다. 이가명은 무너져도 다시 쌓았다."
    res = client.post(f"/api/documents/{doc.id}/verify", json={"sections": _sections(edited)})
    assert res.status_code == 200
    assert "높이를 세어 보았다" in real[0]
    stored = db_session.query(DocumentSection).filter_by(document_id=doc.id, heading="해석").one()
    assert stored.body == INTERPRETATION


def test_gate_one_and_two_run_first(db_session, real):
    doc = _document(db_session)
    res = client.post(f"/api/documents/{doc.id}/verify", json={"sections": _sections("짧다.")})
    assert res.status_code == 422
    assert res.json()["error"]["fields"] == ["sections.해석"]
    assert real == []  # 1 · 2단에 걸리면 jev 를 부르지 않는다


def test_missing_answer_is_a_failure_not_a_pass(db_session, monkeypatch):
    doc = _document(db_session)
    monkeypatch.setattr(verify_module, "is_mock", lambda: False)
    monkeypatch.setattr(verify_module, "decide", lambda state, questions: {})
    res = client.post(f"/api/documents/{doc.id}/verify")
    assert res.status_code == 500
    assert res.json()["error"]["code"] == "GENERATION_FAILED"


def test_no_jev_address_is_dependency_unavailable(db_session, monkeypatch):
    doc = _document(db_session)
    monkeypatch.setattr(verify_module, "is_mock", lambda: False)
    monkeypatch.setattr(settings, "elice_jev_base_url", None)
    res = client.post(f"/api/documents/{doc.id}/verify")
    assert res.status_code == 503
    assert res.json()["error"]["code"] == "DEPENDENCY_UNAVAILABLE"


def test_imported_evidence_is_not_judged(db_session, real):
    doc = _document(db_session, origin="IMPORT")
    res = client.post(f"/api/documents/{doc.id}/verify")
    assert res.status_code == 422
    assert real == []


# --- shared/gates/judge.py ---------------------------------------------------------------


def _all_clear(questions):
    return _answers(questions, conflict_on="none")


def test_new_fact_counts_only_in_interpretation():
    sentences = [
        ("해석", "아이가 미끄럼틀도 탔다."),
        ("지원", "다음에는 미끄럼틀 놀이를 함께 해 본다."),
    ]
    _state, questions = J.build_questions("관찰일지", sentences, {"r1": "아이가 블록을 쌓았다"})
    answers = _all_clear(questions)
    for key in ("s1", "s2"):
        answers[f"{key}.대조"]["probabilities"] = {J.NEW_FACT: 0.9, J.CONFLICT: 0.0}
    codes = [(i.heading, i.code) for i in J.read_issues(sentences, answers, {"r1": 1}, None)]
    # 해석 칸은 기록에 있는 사실만 쓴다. 지원 칸의 「다음에 ~」는 계획이라 새 사실이 아니다.
    assert codes == [("해석", "UNSUPPORTED_FACT")]


def test_vague_support_is_flagged():
    sentences = [("지원", "앞으로도 관심을 가지고 지켜보겠다.")]
    _state, questions = J.build_questions("관찰일지", sentences, {"r1": "아이가 블록을 쌓았다"})
    questions["지원.구체"] = J.support_question(sentences[0][1])
    answers = _all_clear(questions)
    answers["지원.구체"]["noul"] = 0.1
    codes = [i.code for i in J.read_issues(sentences, answers, {"r1": 1}, sentences[0][1])]
    assert codes == ["SUPPORT_NOT_CONCRETE"]


def test_sentence_split_keeps_each_sentence():
    assert J.split_sentences("하나다. 둘이다!\n셋이다") == ["하나다.", "둘이다!", "셋이다"]


def test_daily_log_record_line_has_no_weekday_prefix():
    src = J.Source(1, date(2026, 11, 3), "[바깥놀이 10:00~10:40] 모래놀이")
    assert J.record_line(src, "dailyLog") == "[바깥놀이 10:00~10:40] 모래놀이"
    assert J.record_line(src, "weeklyLog").startswith("11/3(화) ")


def test_long_text_is_judged_in_chunks_not_cut():
    """24문장 뒤를 버리면 뒷부분이 「통과」로 보인다. 6문장씩 나눠 전부 묻는다."""
    body = " ".join(f"문장 {i}번은 블록 놀이 이야기다." for i in range(14))
    calls = []

    def decide(state, questions):
        calls.append(len(state["문장"]))
        return _answers(questions, conflict_on="s2")

    issues = J.judge("observation", "관찰일지", {"해석": body}, [J.Source(1, None, "기록")], decide)
    assert calls == [6, 6, 2]
    # 묶음마다 2번째 문장이 어긋남 → 3건, 문장은 각 묶음의 2번째(1 · 7 · 13번)
    assert [i.sentence for i in issues] == [
        "문장 1번은 블록 놀이 이야기다.",
        "문장 7번은 블록 놀이 이야기다.",
        "문장 13번은 블록 놀이 이야기다.",
    ]


def test_too_many_sentences_is_refused():
    body = " ".join(f"문장 {i}번." for i in range(J.MAX_SENTENCES + 1))
    with pytest.raises(J.TooLong):
        J.judge("observation", "관찰일지", {"해석": body}, [], lambda *_: {})


# --- 리뷰에서 짚은 빈틈 ---------------------------------------------------------------------


def test_masking_failure_never_calls_jev(db_session, real, monkeypatch):
    from app.shared.childCode import SubstitutionError

    doc = _document(db_session)

    def fail(*_):
        raise SubstitutionError("받침이 다르다")

    monkeypatch.setattr(verify_module, "name_table", fail)
    res = client.post(f"/api/documents/{doc.id}/verify")
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "VALUE_INVALID"
    assert real == []


ONE_SYLLABLE_FACT = "이가명이 민이와 블록으로 탑을 3층까지 쌓았다."


def _with_one_syllable_child(session, doc, call_name, text=ONE_SYLLABLE_FACT):
    """같은 반 외자 아이 김민을 넣고, 첫 기록에 그 아이를 적는다(기본 「민이와」)."""
    session.add(Child(class_id=doc.class_id, name="김민", code="가람", call_name=call_name))
    source = session.query(DocumentSource).filter_by(document_id=doc.id, source_id=200).one()
    source.text = text
    fact = session.query(DocumentSection).filter_by(document_id=doc.id, heading="사실").one()
    fact.body = "\n\n".join([source.text, FACTS[1]])
    session.flush()


def test_one_syllable_call_name_is_masked_before_jev(db_session, real):
    doc = _document(db_session)
    _with_one_syllable_child(db_session, doc, "민이")
    res = client.post(f"/api/documents/{doc.id}/verify")
    assert res.status_code == 200, res.json()
    assert "민이와" not in real[0] and "가람이와" in real[0]


@pytest.mark.parametrize("call_name", [None, "민이"])
def test_other_one_syllable_forms_are_masked_before_jev(db_session, real, call_name):
    # 부르는 이름(민이)을 등록해도 「민은」 · 「민아」가 원문으로 나가면 안 된다(3차 점검 2번).
    doc = _document(db_session)
    text = "이가명이 민아 하고 불렀다. 민은 블록으로 탑을 3층까지 쌓았다."
    _with_one_syllable_child(db_session, doc, call_name, text)
    res = client.post(f"/api/documents/{doc.id}/verify")
    assert res.status_code == 200, res.json()
    assert "민아" not in real[0] and "민은" not in real[0]
    assert "가람아" in real[0] and "가람은" in real[0]


@pytest.mark.parametrize("call_name", [None, "민이"])
def test_bare_one_syllable_never_calls_jev(db_session, real, call_name):
    doc = _document(db_session)
    _with_one_syllable_child(db_session, doc, call_name, "이가명이 민 옆에서 탑을 3층까지 쌓았다.")
    res = client.post(f"/api/documents/{doc.id}/verify")
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "VALUE_INVALID"
    assert "부르는 이름" in res.json()["error"]["message"]
    assert real == []


@pytest.mark.parametrize("kind", ["dailyLog", "weeklyLog"])
def test_daily_and_weekly_logs_are_judged(db_session, real, kind):
    doc = _document(db_session, kind=kind)
    res = client.post(f"/api/documents/{doc.id}/verify")
    assert res.status_code == 200
    assert res.json()["issues"][0]["code"] == "CONTRADICTS_SOURCE"
    # 주간은 기록 줄에 요일이 붙고, 일일은 하루 기록이라 붙지 않는다.
    assert ("11/3(화)" in real[0]) is (kind == "weeklyLog")


def test_assessment_is_not_judged(db_session, real):
    doc = _document(db_session, kind="assessment")
    res = client.post(f"/api/documents/{doc.id}/verify")
    assert res.status_code == 422
    assert res.json()["error"]["fields"] == ["kind"]
    assert real == []


def test_other_centers_document_is_404(db_session, real):
    mine = _document(db_session)
    _document(db_session)  # 교사가 다른 원으로 옮겨 간다
    res = client.post(f"/api/documents/{mine.id}/verify")
    assert res.status_code == 404
    assert real == []


@pytest.mark.parametrize(
    "broken",
    [
        lambda a: a["s1.대조"].pop("probabilities"),
        lambda a: a["s1.단정"].pop("noul"),
        lambda a: a["s1.근거"].update(choice="r9"),
        lambda a: a.update({"s1.개입": "예"}),
    ],
)
def test_broken_answer_is_a_failure_not_a_pass(db_session, monkeypatch, broken):
    doc = _document(db_session)

    def decide(state, questions):
        answers = _answers(questions, conflict_on="none")
        broken(answers)
        return answers

    monkeypatch.setattr(verify_module, "is_mock", lambda: False)
    monkeypatch.setattr(verify_module, "decide", decide)
    res = client.post(f"/api/documents/{doc.id}/verify")
    assert res.status_code == 500
    assert res.json()["error"]["code"] == "GENERATION_FAILED"


def test_chosen_conflict_is_reported_even_below_half():
    sentences = [("해석", "아이가 퍼즐만 했다.")]
    _state, questions = J.build_questions("관찰일지", sentences, {"r1": "아이가 블록을 쌓았다"})
    answers = _all_clear(questions)
    answers["s1.대조"] = {
        "choice": J.CONFLICT,
        "probabilities": {J.CONFLICT: 0.4, J.SAME: 0.2, J.NEW_FACT: 0.2, J.INTERPRETATION: 0.2},
    }
    assert [i.code for i in J.read_issues(sentences, answers, {"r1": 1}, None)] == [
        "CONTRADICTS_SOURCE"
    ]


def test_support_question_is_asked_once_across_chunks():
    body = " ".join(f"문장 {i}번은 블록 놀이 이야기다." for i in range(8))
    support = "다음 블록 놀이에서 높이를 재어 볼 자를 함께 놓아 준다."
    asked = []

    def decide(state, questions):
        asked.append("지원.구체" in questions)
        return _answers(questions, conflict_on="none")

    J.judge(
        "observation",
        "관찰일지",
        {"해석": body, "지원": support},
        [J.Source(1, None, "기록")],
        decide,
    )
    # 해석 8문장 + 지원 1문장 = 9문장 → 6 · 3 두 번. 지원 칸 전체 질문은 첫 번에만.
    assert asked == [True, False]


def test_new_fact_bar_is_higher_for_class_logs():
    """관찰일지는 0.5, 일일 · 주간은 0.7 (ADR-071 실측 4 · 5회차)."""
    sentences = [("해석", "아이들이 신문지 결을 따라 찢는 느낌을 경험했다.")]
    _state, questions = J.build_questions("일일 보육일지", sentences, {"r1": "신문지 찢기"})
    answers = _all_clear(questions)
    answers["s1.대조"]["probabilities"] = {
        J.CONFLICT: 0.0,
        J.SAME: 0.0,
        J.NEW_FACT: 0.6,
        J.INTERPRETATION: 0.4,
    }
    assert J.read_issues(sentences, answers, {"r1": 1}, None, "dailyLog") == []
    flagged = J.read_issues(sentences, answers, {"r1": 1}, None, "observation")
    assert [i.code for i in flagged] == ["UNSUPPORTED_FACT"]
