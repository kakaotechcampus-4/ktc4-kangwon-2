"""실제 PostgreSQL에서 비교·재확정·실패 보존·재시도를 검증한다."""

from datetime import UTC, date, datetime, time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from test_documents import _make_center_class_child, _make_document, _make_sections

from app.features.centers.models import Center, Class
from app.features.documents.models import (
    Document,
    DocumentReconfirmation,
    DocumentSection,
    DocumentSource,
    DocumentSourceResolution,
)
from app.features.routines.models import RoutineRecord
from app.main import app

client = TestClient(app)
CHECKS = {"fact": True, "interpretation": True, "support": True}


@pytest.fixture
def reviewable(db_session, teacher):
    db_session.info["teacher"] = teacher
    # 감사 기록(document_source_resolutions.actor_user_id)이 users 를 가리킨다 — 진짜 행이어야 한다.
    db_session.add(teacher)
    db_session.flush()
    _, klass, _ = _make_center_class_child(db_session)
    day = date(2026, 10, 19)
    routines = []
    for i in range(2):
        r = RoutineRecord(
            class_id=klass.id,
            date=day,
            position=i,
            start_time=time(9 + i, 16, 25),
            end_time=time(10 + i, 20),
            name="낙엽놀이",
            plan="",
            execution="취소하고 블록놀이로 대체함",
        )
        db_session.add(r)
        db_session.flush()
        routines.append(r)
    doc = _make_document(
        db_session,
        klass,
        kind="dailyLog",
        start_date=day,
        end_date=day,
        status="CONFIRMED",
        stale=True,
        review_note="교사가 남긴 메모",
    )
    copies = []
    for r in routines:
        c = DocumentSource(
            document_id=doc.id,
            source_kind="routine",
            source_id=r.id,
            class_id=klass.id,
            date=day,
            text=r.fact_text(),
        )
        db_session.add(c)
        copies.append(c)
    db_session.flush()
    _make_sections(db_session, doc, copies)
    for r in routines:
        r.execution = "아이들이 낙엽놀이를 즐겁게 진행함"
    db_session.commit()
    return doc, routines


def comparison(doc):
    response = client.get(f"/api/documents/{doc.id}/source-comparison")
    assert response.status_code == 200, response.text
    return response.json()


def payload(doc, viewed):
    detail = client.get(f"/api/documents/{doc.id}").json()
    sections = detail["sections"]
    next(s for s in sections if s["heading"] == "사실")["body"] = "\n\n".join(
        s["after"] or "" for s in viewed["sources"]
    )
    return {
        "review_token": viewed["review_token"],
        "updated_at": viewed["updated_at"],
        "checks": CHECKS,
        "sections": sections,
    }


def post(doc, body):
    return client.post(f"/api/documents/{doc.id}/reconfirm", json=body)


def test_comparison_all_rows_and_atomic_reconfirm_with_retry(db_session, reviewable):
    doc, routines = reviewable
    viewed = comparison(doc)
    assert viewed["can_reconfirm"]
    assert [s["id"] for s in viewed["sources"]] == [r.id for r in routines]
    assert all(
        s["state"] == "changed" and "취소" in s["before"] and "즐겁게" in s["after"]
        for s in viewed["sources"]
    )
    before = client.get(f"/api/documents/{doc.id}").json()
    body = payload(doc, viewed)
    result = post(doc, body)
    assert result.status_code == 200, result.text
    after = result.json()
    assert (after["status"], after["stale"]) == ("CONFIRMED", False)
    assert after["sections"][0]["body"] == body["sections"][0]["body"]
    assert after["sections"][1:] == before["sections"][1:]
    assert after["review_note"] == "교사가 남긴 메모"
    assert post(doc, body).json() == after
    assert (
        db_session.scalar(
            select(func.count())
            .select_from(DocumentReconfirmation)
            .where(DocumentReconfirmation.document_id == doc.id)
        )
        == 1
    )
    assert all(s["state"] == "unchanged" for s in comparison(doc)["sources"])
    assert client.get(f"/api/documents/{doc.id}").json() == after


@pytest.mark.parametrize("failure", ["checks", "short", "fact", "source_ids", "duplicate_sections"])
def test_failed_validation_preserves_entire_confirmed_document(db_session, reviewable, failure):
    doc, _ = reviewable
    before = client.get(f"/api/documents/{doc.id}").json()
    body = payload(doc, comparison(doc))
    if failure == "checks":
        body["checks"] = {**CHECKS, "support": False}
    elif failure == "short":
        body["sections"][1]["body"] = "짧음"
    elif failure == "fact":
        body["sections"][0]["body"] = "임의 사실"
    elif failure == "source_ids":
        body["sections"][1]["source_ids"] = [999999]
    else:
        body["sections"] = [body["sections"][0]] * 3
    assert post(doc, body).status_code == 422
    assert client.get(f"/api/documents/{doc.id}").json() == before
    assert not db_session.scalar(
        select(DocumentReconfirmation).where(DocumentReconfirmation.document_id == doc.id)
    )


@pytest.mark.parametrize("change", ["deleted", "empty", "other_date", "other_class"])
def test_missing_or_ineligible_source_never_reconfirms(db_session, reviewable, change):
    doc, routines = reviewable
    r = routines[0]
    if change == "deleted":
        db_session.delete(r)
    elif change == "empty":
        r.execution = ""
    elif change == "other_date":
        r.date = date(2026, 10, 20)
    else:
        previous_center_id = db_session.info["teacher"].center_id
        _, other, _ = _make_center_class_child(db_session)
        r.class_id = other.id
        db_session.info["teacher"].center_id = previous_center_id
    db_session.commit()
    before = client.get(f"/api/documents/{doc.id}").json()
    viewed = comparison(doc)
    assert viewed["sources"][0]["state"] == "missing"
    assert viewed["sources"][0]["after"] is None
    assert not viewed["can_reconfirm"]
    assert post(doc, payload(doc, viewed)).status_code == 409
    assert client.get(f"/api/documents/{doc.id}").json() == before


@pytest.mark.parametrize("change", ["routine", "seconds", "document", "unconfirm"])
def test_changed_since_view_conflicts_without_touching_confirmed_data(
    db_session, reviewable, change
):
    doc, routines = reviewable
    body = payload(doc, comparison(doc))
    if change == "routine":
        routines[0].name = "바뀐 일과 이름"
    elif change == "seconds":
        routines[0].start_time = time(9, 16, 26)
    elif change == "document":
        doc.updated_at = datetime.now(UTC)
        doc.review_note = "다른 교사의 메모"
    else:
        doc.status = "DRAFT"
        doc.updated_at = datetime.now(UTC)
    db_session.commit()
    before = client.get(f"/api/documents/{doc.id}").json()
    result = post(doc, body)
    assert result.status_code == 409
    assert result.json()["error"]["code"] == "STALE_WRITE"
    assert client.get(f"/api/documents/{doc.id}").json() == before


def test_edited_interpretation_support_and_dependent_stale(db_session, reviewable):
    doc, _ = reviewable
    parent = Document(
        kind="weeklyLog",
        title="주간",
        class_id=doc.class_id,
        start_date=doc.start_date,
        end_date=doc.end_date,
        status="CONFIRMED",
        origin="AI",
        stale=False,
        review_note="",
    )
    db_session.add(parent)
    db_session.flush()
    db_session.add(
        DocumentSource(
            document_id=parent.id,
            source_kind="document",
            source_id=doc.id,
            class_id=doc.class_id,
            date=doc.start_date,
            text="이전 사실",
        )
    )
    db_session.commit()
    body = payload(doc, comparison(doc))
    body["sections"][1]["body"] = "교사가 바뀐 사실을 대조하고 직접 수정한 해석 문장입니다."
    body["sections"][2]["body"] = "교사가 놀이 자료를 추가로 준비하고 활동을 지원할 계획입니다."
    after = post(doc, body).json()
    assert after["sections"][1:] == body["sections"][1:]
    db_session.refresh(parent)
    assert parent.stale


def test_other_center_cannot_compare_or_reconfirm(db_session, reviewable, teacher):
    doc, _ = reviewable
    body = payload(doc, comparison(doc))
    teacher.center_id = None
    assert client.get(f"/api/documents/{doc.id}/source-comparison").status_code == 404
    assert post(doc, body).status_code == 404


def test_reverse_inserted_sections_always_return_fact_interpretation_support(
    db_session, reviewable
):
    doc, _ = reviewable
    # 실제 PG의 행 번호/삽입 순서와 무관하게 상세 응답의 읽는 순서를 확인한다.
    sections = list(
        db_session.scalars(select(DocumentSection).where(DocumentSection.document_id == doc.id))
    )
    values = [(s.heading, s.body, s.source_ids) for s in sections]
    for s in sections:
        db_session.delete(s)
    db_session.flush()
    for heading, body, ids in sorted(values, reverse=True):
        db_session.add(
            DocumentSection(document_id=doc.id, heading=heading, body=body, source_ids=ids)
        )
    db_session.commit()
    for _ in range(3):
        assert [
            s["heading"] for s in client.get(f"/api/documents/{doc.id}").json()["sections"]
        ] == ["사실", "해석", "지원"]


def test_commit_failure_rolls_back_original_confirmed_document(db_session, reviewable, monkeypatch):
    doc, _ = reviewable
    before = client.get(f"/api/documents/{doc.id}").json()
    body = payload(doc, comparison(doc))

    def failed_commit():
        # flush 이후 실패도 원본·섹션·영수증을 함께 되돌려야 한다.
        db_session.flush()
        raise RuntimeError("injected commit failure")

    with monkeypatch.context() as patch:
        patch.setattr(db_session, "commit", failed_commit)
        response = TestClient(app, raise_server_exceptions=False).post(
            f"/api/documents/{doc.id}/reconfirm", json=body
        )
        assert response.status_code == 500
    assert client.get(f"/api/documents/{doc.id}").json() == before
    assert not db_session.scalar(
        select(DocumentReconfirmation).where(DocumentReconfirmation.document_id == doc.id)
    )


def deleted_source(db_session, doc, routines, spare=False):
    """근거 하나를 지운다. `spare` 면 같은 반·날짜에 쓰지 않은 일과를 하나 남겨 둔다."""
    extra = None
    if spare:
        extra = RoutineRecord(
            class_id=routines[0].class_id,
            date=routines[0].date,
            position=9,
            start_time=time(13, 0),
            end_time=time(13, 40),
            name="오후 바깥놀이",
            plan="",
            execution="모래밭에서 물길을 만들며 친구에게 삽을 건네주었다.",
        )
        db_session.add(extra)
    gone = routines[0]
    client.delete(f"/api/routines/{gone.id}")
    db_session.commit()
    return gone, extra


def resolved_payload(doc, viewed, resolutions):
    """사라진 근거를 빼거나 바꾼 뒤의 `사실` 과 `source_ids` 를 화면이 하듯 다시 만든다."""
    by_source = {r["source_id"]: r for r in resolutions}
    texts, ids = [], []
    picked = {c["id"]: c["text"] for c in viewed["candidates"]}
    for row in viewed["sources"]:
        choice = by_source.get(row["id"])
        if choice is None:
            texts.append(row["after"] or "")
            ids.append(row["id"])
        elif choice["action"] == "replace":
            # 서버가 거절할 선택도 그대로 보낸다 — 화면이 아니라 서버가 막는지 보는 것이다.
            texts.append(picked.get(choice["replacement_id"], "서버가 거절해야 하는 대체본"))
            ids.append(choice["replacement_id"])
    sections = client.get(f"/api/documents/{doc.id}").json()["sections"]
    for section in sections:
        section["source_ids"] = ids
    next(s for s in sections if s["heading"] == "사실")["body"] = "\n\n".join(texts)
    return {
        "review_token": viewed["review_token"],
        "updated_at": viewed["updated_at"],
        "checks": CHECKS,
        "sections": sections,
        "resolutions": resolutions,
    }


def test_refresh_rejects_a_confirmed_document_and_a_deleted_source(db_session, reviewable):
    doc, routines = reviewable
    confirmed = client.post(f"/api/documents/{doc.id}/refresh")
    assert confirmed.status_code == 409
    assert confirmed.json()["error"]["code"] == "ALREADY_CONFIRMED"
    gone, _ = deleted_source(db_session, doc, routines)
    client.post(f"/api/documents/{doc.id}/unconfirm")
    blocked = client.post(f"/api/documents/{doc.id}/refresh")
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "GATE_BLOCKED"
    assert blocked.json()["error"]["fields"] == [f"sources.{gone.id}"]


def test_reconfirm_drops_a_deleted_source_and_keeps_the_rest(db_session, reviewable):
    doc, routines = reviewable
    gone, _ = deleted_source(db_session, doc, routines)
    viewed = comparison(doc)
    assert not viewed["can_reconfirm"]
    assert [s["state"] for s in viewed["sources"]] == ["missing", "changed"]
    assert viewed["candidates"] == []
    before = client.get(f"/api/documents/{doc.id}").json()
    body = resolved_payload(doc, viewed, [{"source_id": gone.id, "action": "drop"}])
    result = post(doc, body)
    assert result.status_code == 200, result.text
    after = result.json()
    assert (after["id"], after["status"], after["stale"]) == (doc.id, "CONFIRMED", False)
    assert [s["id"] for s in after["sources"]] == [routines[1].id]
    assert [s["body"] for s in after["sections"][1:]] == [s["body"] for s in before["sections"][1:]]
    assert all(s["source_ids"] == [routines[1].id] for s in after["sections"])
    assert gone.fact_text() not in after["sections"][0]["body"]
    receipt = db_session.scalar(
        select(DocumentReconfirmation).where(DocumentReconfirmation.document_id == doc.id)
    )
    assert receipt.resolutions == [
        {
            "source_id": gone.id,
            "action": "drop",
            "replacement_id": None,
            "before": "[낙엽놀이 09:16~10:20] 취소하고 블록놀이로 대체함",
        }
    ]


def test_reconfirm_replaces_a_deleted_source_with_another_routine(db_session, reviewable):
    doc, routines = reviewable
    gone, extra = deleted_source(db_session, doc, routines, spare=True)
    viewed = comparison(doc)
    assert [c["id"] for c in viewed["candidates"]] == [extra.id]
    body = resolved_payload(
        doc, viewed, [{"source_id": gone.id, "action": "replace", "replacement_id": extra.id}]
    )
    result = post(doc, body)
    assert result.status_code == 200, result.text
    after = result.json()
    assert sorted(s["id"] for s in after["sources"]) == sorted([extra.id, routines[1].id])
    assert extra.fact_text() in after["sections"][0]["body"]
    receipt = db_session.scalar(
        select(DocumentReconfirmation).where(DocumentReconfirmation.document_id == doc.id)
    )
    assert receipt.resolutions[0]["replacement_id"] == extra.id


def receipts(db_session, doc) -> int:
    return db_session.scalar(
        select(func.count())
        .select_from(DocumentReconfirmation)
        .where(DocumentReconfirmation.document_id == doc.id)
    )


@pytest.mark.parametrize("choice", ["drop", "replace"])
def test_retrying_a_resolved_reconfirm_returns_the_same_result_once(db_session, reviewable, choice):
    """근거를 빼거나 바꾼 재확정도 **같은 요청을 다시 보내면 같은 200** 이다 (F5).

    예전에는 영수증에 변경 **전** 근거 해시를 적어 두어, 재시도가 다시 잰 값과 영영
    어긋나고 409 STALE_WRITE 가 났다. 첫 요청은 이미 반영된 뒤였다.
    """
    doc, routines = reviewable
    gone, extra = deleted_source(db_session, doc, routines, spare=choice == "replace")
    resolution = (
        {"source_id": gone.id, "action": "drop"}
        if choice == "drop"
        else {"source_id": gone.id, "action": "replace", "replacement_id": extra.id}
    )
    body = resolved_payload(doc, comparison(doc), [resolution])
    first = post(doc, body)
    assert first.status_code == 200, first.text
    again = post(doc, body)
    assert again.status_code == 200, again.text
    # 두 번째가 첫 번째를 그대로 되돌려준다 = 다시 적용되지 않았다.
    assert again.json() == first.json()
    assert (again.json()["status"], again.json()["stale"]) == ("CONFIRMED", False)
    assert receipts(db_session, doc) == 1
    assert client.get(f"/api/documents/{doc.id}").json() == first.json()
    assert db_session.scalar(
        select(func.count()).select_from(DocumentSource).where(DocumentSource.document_id == doc.id)
    ) == len(first.json()["sources"])
    # 새로 비교해 받은 토큰으로는 다시 확정되지 않는다 — 이미 확정이고 stale 도 아니다.
    fresh = post(doc, resolved_payload(doc, comparison(doc), []))
    assert fresh.status_code == 409
    assert fresh.json()["error"]["code"] == "GATE_BLOCKED"
    assert receipts(db_session, doc) == 1


@pytest.mark.parametrize(
    "retry",
    ["other_body", "other_resolution", "other_center", "document_changed", "source_changed"],
)
def test_completed_reconfirm_accepts_only_the_identical_request(db_session, reviewable, retry):
    """영수증이 있어도 **똑같은 요청일 때만** 200 이다 (F5). 나머지는 막고 문서는 그대로다."""
    doc, routines = reviewable
    gone, extra = deleted_source(db_session, doc, routines, spare=True)
    body = resolved_payload(doc, comparison(doc), [{"source_id": gone.id, "action": "drop"}])
    assert post(doc, body).status_code == 200
    retried = dict(body)
    if retry == "other_body":
        retried["review_note"] = "다시 보내면서 바꾼 메모"
    elif retry == "other_resolution":
        retried["resolutions"] = [
            {"source_id": gone.id, "action": "replace", "replacement_id": extra.id}
        ]
    elif retry == "other_center":
        db_session.info["teacher"].center_id = None
    elif retry == "document_changed":
        doc.review_note = "다른 교사의 메모"
        doc.updated_at = datetime.now(UTC)
        db_session.commit()
    else:
        routines[1].name = "바뀐 일과 이름"
        db_session.commit()
    if retry == "other_center":
        assert post(doc, retried).status_code == 404
        assert receipts(db_session, doc) == 1
        return
    settled = client.get(f"/api/documents/{doc.id}").json()
    result = post(doc, retried)
    assert result.status_code == 409, result.text
    assert result.json()["error"]["code"] == "STALE_WRITE"
    assert client.get(f"/api/documents/{doc.id}").json() == settled
    assert receipts(db_session, doc) == 1


@pytest.mark.parametrize("bad", ["unresolved", "all_dropped", "unknown_pick", "used_pick", "alien"])
def test_reconfirm_refuses_bad_resolutions_and_keeps_the_document(db_session, reviewable, bad):
    doc, routines = reviewable
    gone, extra = deleted_source(db_session, doc, routines, spare=True)
    before = client.get(f"/api/documents/{doc.id}").json()
    viewed = comparison(doc)
    drop = {"source_id": gone.id, "action": "drop"}
    if bad == "unresolved":
        body = payload(doc, viewed)
    elif bad == "all_dropped":
        body = resolved_payload(
            doc, viewed, [drop, {"source_id": routines[1].id, "action": "drop"}]
        )
    elif bad == "unknown_pick":
        body = resolved_payload(
            doc, viewed, [{"source_id": gone.id, "action": "replace", "replacement_id": 99999}]
        )
    elif bad == "used_pick":
        body = resolved_payload(
            doc,
            viewed,
            [{"source_id": gone.id, "action": "replace", "replacement_id": routines[1].id}],
        )
    else:
        body = resolved_payload(doc, viewed, [drop])
        body["resolutions"] = [drop, {"source_id": routines[1].id, "action": "drop"}]
    result = post(doc, body)
    assert result.status_code in (409, 422), result.text
    db_session.expire_all()
    assert client.get(f"/api/documents/{doc.id}").json() == before
    assert (
        db_session.scalar(
            select(func.count())
            .select_from(DocumentReconfirmation)
            .where(DocumentReconfirmation.document_id == doc.id)
        )
        == 0
    )


def test_resolutions_need_a_confirmed_stale_document(db_session, reviewable):
    doc, routines = reviewable
    gone, _ = deleted_source(db_session, doc, routines)
    viewed = comparison(doc)
    body = resolved_payload(doc, viewed, [{"source_id": gone.id, "action": "drop"}])
    client.post(f"/api/documents/{doc.id}/unconfirm")
    result = post(doc, body)
    assert result.status_code == 409
    assert result.json()["error"]["code"] in ("GATE_BLOCKED", "STALE_WRITE")
    db_session.expire_all()
    assert db_session.get(Document, doc.id).status == "DRAFT"


def test_another_class_routine_is_never_offered_as_a_replacement(db_session, reviewable):
    doc, routines = reviewable
    # 교사의 원을 바꾸지 않고 다른 원·다른 반만 만든다 — 헬퍼는 teacher.center_id 를 옮긴다.
    other_center = Center(
        name="다른어린이집",
        director_name="이원장",
        region_sido="강원특별자치도",
        region_sigungu="원주시",
    )
    db_session.add(other_center)
    db_session.flush()
    other = Class(
        center_id=other_center.id,
        name="달님반",
        school_year=2026,
        age_min=4,
        age_max=4,
        teacher_name="박선생",
    )
    db_session.add(other)
    db_session.flush()
    alien = RoutineRecord(
        class_id=other.id,
        date=routines[0].date,
        position=0,
        start_time=time(9, 0),
        end_time=time(9, 30),
        name="다른 반 일과",
        plan="",
        execution="다른 반에서 있었던 일",
    )
    db_session.add(alien)
    gone, _ = deleted_source(db_session, doc, routines)
    viewed = comparison(doc)
    assert alien.id not in {c["id"] for c in viewed["candidates"]}
    body = resolved_payload(doc, viewed, [{"source_id": gone.id, "action": "drop"}])
    body["resolutions"] = [{"source_id": gone.id, "action": "replace", "replacement_id": alien.id}]
    result = post(doc, body)
    assert result.status_code == 409
    assert result.json()["error"]["code"] == "GATE_BLOCKED"


def draft_with_deleted_source(db_session, doc, routines, spare=False):
    """확정을 풀어 초안으로 만든 뒤 근거 하나를 지운다 — 교사가 실제로 겪는 순서다."""
    gone, extra = deleted_source(db_session, doc, routines, spare=spare)
    assert client.post(f"/api/documents/{doc.id}/unconfirm").status_code == 200
    db_session.expire_all()
    return gone, extra


def refresh(doc, body=None):
    return client.post(f"/api/documents/{doc.id}/refresh", json=body)


def test_draft_refresh_without_a_choice_still_refuses_a_deleted_source(db_session, reviewable):
    doc, routines = reviewable
    gone, _ = draft_with_deleted_source(db_session, doc, routines)
    for body in (None, {}, {"resolutions": []}):
        result = refresh(doc, body)
        assert result.status_code == 409, body
        assert result.json()["error"]["code"] == "GATE_BLOCKED"
        assert result.json()["error"]["fields"] == [f"sources.{gone.id}"]
    db_session.expire_all()
    assert (
        len(
            db_session.scalars(
                select(DocumentSource).where(DocumentSource.document_id == doc.id)
            ).all()
        )
        == 2
    )


def test_draft_refresh_drops_a_deleted_source_and_keeps_the_draft(db_session, reviewable):
    doc, routines = reviewable
    gone, _ = draft_with_deleted_source(db_session, doc, routines)
    before = client.get(f"/api/documents/{doc.id}").json()
    result = refresh(doc, {"resolutions": [{"source_id": gone.id, "action": "drop"}]})
    assert result.status_code == 200, result.text
    after = result.json()
    # 초안으로 남는다 — 교사가 다시 읽고 확정한다.
    assert (after["id"], after["status"], after["stale"]) == (doc.id, "DRAFT", False)
    assert [s["id"] for s in after["sources"]] == [routines[1].id]
    assert after["sections"][0]["body"] == routines[1].fact_text()
    assert [s["body"] for s in after["sections"][1:]] == [s["body"] for s in before["sections"][1:]]
    assert all(s["source_ids"] == [routines[1].id] for s in after["sections"])
    # 이제 보통 문서다 — 교사가 확정할 수 있다.
    confirmed = client.post(
        f"/api/documents/{doc.id}/confirm",
        json={"checks": {"fact": True, "interpretation": True, "support": True}},
    )
    assert confirmed.status_code == 200, confirmed.text
    db_session.expire_all()
    assert db_session.get(Document, doc.id).status == "CONFIRMED"


def test_draft_refresh_replaces_a_deleted_source_with_another_routine(db_session, reviewable):
    doc, routines = reviewable
    gone, extra = draft_with_deleted_source(db_session, doc, routines, spare=True)
    result = refresh(
        doc,
        {"resolutions": [{"source_id": gone.id, "action": "replace", "replacement_id": extra.id}]},
    )
    assert result.status_code == 200, result.text
    after = result.json()
    assert after["status"] == "DRAFT"
    assert sorted(s["id"] for s in after["sources"]) == sorted([extra.id, routines[1].id])
    assert extra.fact_text() in after["sections"][0]["body"]
    assert gone.fact_text() not in after["sections"][0]["body"]
    assert all(
        sorted(s["source_ids"]) == sorted([extra.id, routines[1].id]) for s in after["sections"]
    )


@pytest.mark.parametrize("bad", ["all_dropped", "alien", "unknown_pick", "not_missing"])
def test_draft_refresh_refuses_bad_choices_and_keeps_the_draft(db_session, reviewable, bad):
    doc, routines = reviewable
    gone, extra = draft_with_deleted_source(db_session, doc, routines, spare=True)
    before = client.get(f"/api/documents/{doc.id}").json()
    drop = {"source_id": gone.id, "action": "drop"}
    if bad == "all_dropped":
        body = {"resolutions": [drop, {"source_id": routines[1].id, "action": "drop"}]}
    elif bad == "alien":
        other_center = Center(
            name="옆집어린이집",
            director_name="최원장",
            region_sido="경기도",
            region_sigungu="성남시",
        )
        db_session.add(other_center)
        db_session.flush()
        other = Class(
            center_id=other_center.id,
            name="별님반",
            school_year=2026,
            age_min=4,
            age_max=4,
            teacher_name="정선생",
        )
        db_session.add(other)
        db_session.flush()
        alien = RoutineRecord(
            class_id=other.id,
            date=routines[1].date,
            position=0,
            start_time=time(9, 0),
            end_time=time(9, 30),
            name="다른 반 일과",
            plan="",
            execution="다른 반에서 있었던 일",
        )
        db_session.add(alien)
        db_session.commit()
        body = {
            "resolutions": [{"source_id": gone.id, "action": "replace", "replacement_id": alien.id}]
        }
    elif bad == "unknown_pick":
        body = {
            "resolutions": [{"source_id": gone.id, "action": "replace", "replacement_id": 99999}]
        }
    else:
        body = {
            "resolutions": [
                drop,
                {"source_id": routines[1].id, "action": "drop", "replacement_id": None},
            ]
        }
    result = refresh(doc, body)
    assert result.status_code in (409, 422), result.text
    db_session.expire_all()
    assert client.get(f"/api/documents/{doc.id}").json() == before


def test_draft_refresh_resolutions_are_only_for_routine_daily_logs(db_session, reviewable):
    doc, routines = reviewable
    gone, _ = draft_with_deleted_source(db_session, doc, routines)
    db_session.get(Document, doc.id).kind = "weeklyLog"
    db_session.commit()
    result = refresh(doc, {"resolutions": [{"source_id": gone.id, "action": "drop"}]})
    assert result.status_code == 409
    assert result.json()["error"]["code"] == "GATE_BLOCKED"
    assert result.json()["error"]["fields"] == ["kind"]


def trail(db_session, doc):
    return list(
        db_session.scalars(
            select(DocumentSourceResolution)
            .where(DocumentSourceResolution.document_id == doc.id)
            .order_by(DocumentSourceResolution.id)
        )
    )


def test_draft_refresh_records_who_dropped_which_source_and_keeps_it_after_confirming(
    db_session, reviewable, teacher
):
    """초안에서 뺀 근거의 흔적이 남고, 나중에 확정해도 지워지지 않는다 (F6)."""
    doc, routines = reviewable
    gone, _ = draft_with_deleted_source(db_session, doc, routines)
    assert (
        refresh(doc, {"resolutions": [{"source_id": gone.id, "action": "drop"}]}).status_code == 200
    )
    db_session.expire_all()
    (row,) = trail(db_session, doc)
    assert (row.source_id, row.action, row.replacement_id) == (gone.id, "drop", None)
    # 원본이 아니라 **사본에 적혀 있던 문구** 다 — 원본은 이미 지워졌다.
    assert row.before == "[낙엽놀이 09:16~10:20] 취소하고 블록놀이로 대체함"
    assert row.actor_user_id == teacher.id
    assert row.created_at is not None
    # 영수증 테이블과 섞이지 않는다 — 저쪽은 확정본 재확정 전용이다.
    assert receipts(db_session, doc) == 0
    assert db_session.get(Document, doc.id).status == "DRAFT"
    confirmed = client.post(f"/api/documents/{doc.id}/confirm", json={"checks": CHECKS})
    assert confirmed.status_code == 200, confirmed.text
    db_session.expire_all()
    assert [r.id for r in trail(db_session, doc)] == [row.id]


def test_draft_refresh_records_the_replacement_it_chose(db_session, reviewable):
    doc, routines = reviewable
    gone, extra = draft_with_deleted_source(db_session, doc, routines, spare=True)
    body = {
        "resolutions": [{"source_id": gone.id, "action": "replace", "replacement_id": extra.id}]
    }
    assert refresh(doc, body).status_code == 200
    db_session.expire_all()
    (row,) = trail(db_session, doc)
    assert (row.action, row.replacement_id) == ("replace", extra.id)


@pytest.mark.parametrize("bad", ["all_dropped", "alien", "unknown_pick", "not_missing"])
def test_a_refused_draft_refresh_leaves_no_trace(db_session, reviewable, bad):
    """같은 트랜잭션이라 거절되면 흔적도 남지 않는다 (F6)."""
    doc, routines = reviewable
    gone, extra = draft_with_deleted_source(db_session, doc, routines, spare=True)
    drop = {"source_id": gone.id, "action": "drop"}
    if bad == "all_dropped":
        body = {"resolutions": [drop, {"source_id": routines[1].id, "action": "drop"}]}
    elif bad == "alien":
        other = RoutineRecord(
            class_id=routines[0].class_id,
            date=date(2026, 10, 18),
            position=3,
            start_time=time(9, 0),
            end_time=time(9, 30),
            name="다른 날 일과",
            plan="",
            execution="다른 날에 한 활동이다.",
        )
        db_session.add(other)
        db_session.commit()
        body = {
            "resolutions": [{"source_id": gone.id, "action": "replace", "replacement_id": other.id}]
        }
    elif bad == "unknown_pick":
        body = {
            "resolutions": [{"source_id": gone.id, "action": "replace", "replacement_id": 10**7}]
        }
    else:
        body = {"resolutions": [{"source_id": routines[1].id, "action": "drop"}]}
    assert refresh(doc, body).status_code in (409, 422)
    db_session.expire_all()
    assert trail(db_session, doc) == []
    assert db_session.get(Document, doc.id).status == "DRAFT"


def test_confirmed_reconfirm_writes_a_receipt_not_a_draft_trail(db_session, reviewable):
    """확정본 재확정은 영수증 쪽에만 적는다 — 두 이력을 섞지 않는다 (F6)."""
    doc, routines = reviewable
    gone, _ = deleted_source(db_session, doc, routines)
    body = resolved_payload(doc, comparison(doc), [{"source_id": gone.id, "action": "drop"}])
    assert post(doc, body).status_code == 200
    db_session.expire_all()
    assert receipts(db_session, doc) == 1
    assert trail(db_session, doc) == []


def test_deleting_the_draft_also_removes_its_resolution_trail(db_session, reviewable):
    """문서를 지우면 흔적도 같이 지운다 — FK 에 CASCADE 가 없다 (ADR-010)."""
    doc, routines = reviewable
    gone, _ = draft_with_deleted_source(db_session, doc, routines)
    assert (
        refresh(doc, {"resolutions": [{"source_id": gone.id, "action": "drop"}]}).status_code == 200
    )
    db_session.expire_all()
    assert len(trail(db_session, doc)) == 1
    assert client.delete(f"/api/documents/{doc.id}").status_code == 204
    db_session.expire_all()
    assert trail(db_session, doc) == []


def test_관찰_근거가_섞인_일일_보육일지는_비교도_재확정도_막는다(db_session, reviewable):
    """#180 리뷰 — `kind` 만 보면 모자란다.

    옛 일일 보육일지는 관찰 기록을 근거로 만들어졌다. 비교는 `routine` 이 아닌 사본을
    **무조건 「사라짐」**으로 보기 때문에, 멀쩡한 관찰 근거를 빼거나 바꿔서 재확정할 수
    있었다 — 근거가 조용히 바뀐 확정본이 남는다. `refresh` 는 이미 막고 있었다.
    """
    doc, _ = reviewable
    db_session.add(
        DocumentSource(
            document_id=doc.id,
            source_kind="observation",
            source_id=99_999,
            class_id=doc.class_id,
            date=doc.start_date,
            text="관찰 기록을 근거로 만든 옛 일지",
        )
    )
    db_session.commit()

    viewing = client.get(f"/api/documents/{doc.id}/source-comparison")
    assert viewing.status_code == 409, viewing.text
    assert viewing.json()["error"]["code"] == "GATE_BLOCKED"
    assert viewing.json()["error"]["fields"] == ["kind"]

    # 확정본은 그대로다 — 막혔으니 아무것도 바뀌면 안 된다.
    db_session.expire_all()
    assert db_session.get(Document, doc.id).status == "CONFIRMED"


def test_refresh_는_살아_있는_근거를_고르면_422_이고_이미_빠진_것은_통과시킨다(
    db_session, reviewable
):
    """#180 리뷰 — `missing` 이 비어 있으면 `resolutions` 를 통째로 무시하고 200 이었다.

    교사가 고른 「빼기」가 반영되지 않았는데 성공으로 보인다. 같은 입력에 `reconfirm` 은
    422 를 내서 둘이 어긋났다.

    **이미 빠진 근거는 거절하지 않는다.** 같은 요청을 다시 보낸 것(동시 호출에서 진 쪽,
    응답을 못 받고 재시도한 쪽)이라 이미 반영돼 있다 — 거절하면 재시도가 깨진다.
    """
    doc, routines = reviewable
    doc.status = "DRAFT"
    db_session.commit()

    # ① 살아 있는 근거를 골랐다 — 사라진 것이 하나도 없어도 거절한다.
    refused = refresh(doc, {"resolutions": [{"source_id": routines[1].id, "action": "drop"}]})
    assert refused.status_code == 422, refused.text
    assert refused.json()["error"]["code"] == "VALIDATION_FAILED"

    # ② 문서에 아예 없는 근거를 골랐다 — 이미 처리된 것이므로 통과한다.
    assert (
        refresh(doc, {"resolutions": [{"source_id": 10**7, "action": "drop"}]}).status_code == 200
    )
