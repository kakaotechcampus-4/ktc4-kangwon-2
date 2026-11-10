"""일지 초안을 못 만들면 사실만 채운 초안을 준다 — fail-closed 폴백 (ADR-093).

모델이 실패하거나 1·2단 검사에 걸려도 교사는 빈손이 아니다. 201 로 초안을 받고,
해석 · 지원은 빈 칸이며 **모델이 쓴 글은 어디에도 남지 않는다.**
"""

import json
import logging

import pytest
from test_documents import (
    _ALL_CHECKED,
    _create_body,
    _make_center_class_child,
    _observation,
    client,
)

from app.features.documents import draft as draft_module
from app.features.documents.models import Document, DocumentSection
from app.shared.llm import LlmBudgetExceeded, LlmCallCapExceeded, LlmFailed, LlmUnavailable

FACT = "개미를 3분 동안 바라보았다."
# 모델이 쓴 글이 새어 나왔는지 찾는 표지. 사실에 없는 숫자(7개)라 2단에 걸린다.
LEAKED = "블록을 7개 쌓으며 수에 관심을 보인다 — 새면 안 되는 글."
SUPPORT = "다음 바깥놀이에서 돋보기를 건네며 무엇을 보았는지 묻겠다."


@pytest.fixture(autouse=True)
def _logged_in(db_session, teacher):
    db_session.info["teacher"] = teacher


def _model(monkeypatch, answer):
    """모델 자리에 `answer` 를 둔다. 예외면 던지고, 글이면 그대로 돌려준다."""

    def fake(system_prompt, user_content, **_):
        if isinstance(answer, Exception):
            raise answer
        return answer

    monkeypatch.setattr(draft_module, "is_mock", lambda: False)
    monkeypatch.setattr(draft_module, "complete_json", fake)


def _make(db_session):
    _, klass, child = _make_center_class_child(db_session)
    record = _observation(db_session, klass, child, 5, FACT)
    return client.post("/api/documents", json=_create_body(klass, child, [record]))


def _saved_bodies(db_session, doc_id):
    rows = db_session.query(DocumentSection).filter_by(document_id=doc_id).all()
    return {r.heading: r.body for r in rows}


@pytest.mark.parametrize(
    ("answer", "reason"),
    [
        (LlmFailed("timeout"), "llm_failed"),
        (LlmCallCapExceeded("cap"), "llm_failed"),
        (LlmUnavailable("키가 없습니다"), "llm_unavailable"),
        (LlmBudgetExceeded("429"), "budget_exceeded"),
        ("약속한 JSON 이 아니다", "llm_failed"),
    ],
)
def test_모델이_실패하면_사실만_채운_초안을_201_로_준다(db_session, monkeypatch, answer, reason):
    _model(monkeypatch, answer)

    res = _make(db_session)

    assert res.status_code == 201, res.text
    payload = res.json()
    assert payload["status"] == "DRAFT"
    assert payload["generation"]["fallback"]["reason"] == reason
    assert payload["generation"]["fallback"]["at"]
    bodies = {s["heading"]: s["body"] for s in payload["sections"]}
    assert bodies == {"사실": FACT, "해석": "", "지원": ""}
    assert _saved_bodies(db_session, payload["id"]) == bodies
    # 검토를 붙이지 않는다 — 볼 글이 없다.
    assert db_session.get(Document, payload["id"]).ai_review is None
    # 목록에도 같은 표시가 간다.
    listed = client.get("/api/documents", params={"kind": "observation"}).json()["items"]
    assert listed[0]["generation"]["fallback"]["reason"] == reason


def test_검사에_걸린_글은_버리고_사실만_채운_초안을_준다(db_session, monkeypatch):
    _model(monkeypatch, json.dumps({"해석": LEAKED, "지원": SUPPORT}, ensure_ascii=False))

    res = _make(db_session)

    assert res.status_code == 201, res.text
    assert res.json()["generation"]["fallback"]["reason"] == "gate_rejected"
    assert LEAKED not in res.text and SUPPORT not in res.text
    saved = _saved_bodies(db_session, res.json()["id"])
    assert saved == {"사실": FACT, "해석": "", "지원": ""}


def test_정상_초안은_폴백_표시가_없다(db_session, monkeypatch):
    interpretation = "작은 생물을 오래 지켜보며 자연에 관심을 보인다."
    _model(monkeypatch, json.dumps({"해석": interpretation, "지원": SUPPORT}, ensure_ascii=False))

    res = _make(db_session)

    assert res.status_code == 201, res.text
    assert res.json()["generation"]["fallback"] is None
    bodies = {s["heading"]: s["body"] for s in res.json()["sections"]}
    assert bodies["해석"] == interpretation


def test_빈_칸인_폴백_초안은_교사가_쓰기_전에는_확정되지_않는다(db_session, monkeypatch):
    _model(monkeypatch, LlmFailed("timeout"))
    doc_id = _make(db_session).json()["id"]

    res = client.post(f"/api/documents/{doc_id}/confirm", json={"checks": _ALL_CHECKED})

    assert res.status_code != 200
    assert db_session.get(Document, doc_id).status == "DRAFT"


def test_폴백은_까닭만_서버_로그에_남긴다(db_session, monkeypatch, caplog):
    _model(monkeypatch, LlmFailed("timeout"))

    # main 이 이 logger 를 서버 handler 로 보낸다(propagate 끔). caplog 를 직접 단다.
    # _schema 의 Alembic fileConfig 가 기존 logger 를 꺼 두는 간섭도 푼다(test_error_logging).
    logger = logging.getLogger("app.features.documents.router")
    monkeypatch.setattr(logger, "disabled", False)
    logger.addHandler(caplog.handler)
    try:
        _make(db_session)
    finally:
        logger.removeHandler(caplog.handler)

    lines = [r.getMessage() for r in caplog.records if "document_draft_fallback" in r.getMessage()]
    assert len(lines) == 1
    assert "reason=llm_failed" in lines[0]
    assert FACT not in lines[0]
