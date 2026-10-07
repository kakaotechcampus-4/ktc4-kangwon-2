"""양식 등록 · 목록 · 삭제를 진짜 Postgres 로 확인한다 (docs/api-spec.md §8 · ADR-020).

`db_session` 을 받는 테스트는 끝나면 전부 롤백된다(`conftest.py`).
"""

import io
import zipfile
from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.features.centers.models import Center
from app.features.forms.models import Form
from app.features.plans.models import Plan
from app.main import app

client = TestClient(app)


def _hwpx(*cells: str) -> bytes:
    """표 하나짜리 hwpx. 셀을 주지 않으면 표가 없는 양식이다."""
    row = "".join(f"<hp:tc><hp:t>{c}</hp:t></hp:tc>" for c in cells)
    xml = f"<hp:tbl><hp:tr>{row}</hp:tr></hp:tbl>" if cells else "<hp:p>표 없음</hp:p>"
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("Contents/section0.xml", xml)
    return buffer.getvalue()


def _center(session, name: str) -> Center:
    center = Center(
        name=name, director_name="김원장", region_sido="강원특별자치도", region_sigungu="춘천시"
    )
    session.add(center)
    session.flush()
    return center


def _register(center_id: int, filename: str = "월간계획안.hwpx", content: bytes | None = None):
    content = _hwpx("주제", "우리 반") if content is None else content
    return client.post(f"/api/centers/{center_id}/forms", files={"file": (filename, content)})


def _count(session) -> int:
    return session.scalar(select(func.count()).select_from(Form))


@pytest.fixture
def mine(db_session, teacher):
    """로그인한 교사의 원 하나와 남의 원 하나."""
    center = _center(db_session, "쓱싹 어린이집")
    teacher.center_id = center.id
    return {"center": center, "other": _center(db_session, "옆 동네 어린이집")}


def test_등록하면_201_이고_파싱_결과가_원에_남는다(db_session, mine):
    center = mine["center"]

    response = _register(center.id)

    assert response.status_code == 201
    body = response.json()
    assert body["center_id"] == center.id
    assert body["name"] == body["filename"] == "월간계획안.hwpx"
    assert body["label_map"] == {"주제": "topic", "우리 반": None}
    assert body["tables"][0][0][0] == {"text": "주제", "rowspan": 1, "colspan": 1}
    assert db_session.get(Form, body["id"]).center_id == center.id


def test_목록은_created_at_최신순이고_같은_시각이면_id_순이다(db_session, mine):
    """id 순서와 시각 순서를 일부러 엇갈리게 넣는다 — id 로만 정렬해도 통과하면 안 된다."""
    center = mine["center"]

    def add(name: str, created_at: str) -> int:
        form = Form(
            center_id=center.id,
            name=name,
            filename=name,
            tables=[],
            labels=[],
            label_map={},
            created_at=datetime.fromisoformat(created_at),
        )
        db_session.add(form)
        db_session.flush()
        return form.id

    newest = add("가을.hwpx", "2026-09-29T12:00:00+09:00")
    oldest = add("봄.hwpx", "2026-09-01T09:00:00+09:00")
    tie_low = add("여름1.hwpx", "2026-09-15T09:00:00+09:00")
    tie_high = add("여름2.hwpx", "2026-09-15T09:00:00+09:00")

    response = client.get(f"/api/centers/{center.id}/forms")

    assert response.status_code == 200
    assert [item["id"] for item in response.json()["items"]] == [newest, tie_high, tie_low, oldest]


def test_지우면_204_이고_목록에서_사라진다(db_session, mine):
    center = mine["center"]
    form_id = _register(center.id).json()["id"]

    assert client.delete(f"/api/forms/{form_id}").status_code == 204
    assert client.get(f"/api/centers/{center.id}/forms").json() == {"items": []}


def test_계획안이_걸린_양식은_409_IN_USE_로_막고_둘_다_남긴다(db_session, mine):
    center = mine["center"]
    form_id = _register(center.id).json()["id"]
    plan = Plan(
        plan_ref="form-in-use",
        center_id=center.id,
        kind="annual",
        school_year=2026,
        classroom_ref="1",
        status="DRAFT",
        body={},
        form_id=form_id,
    )
    db_session.add(plan)
    db_session.flush()
    plan_id = plan.id
    # 세이브포인트를 해제해 삭제 요청의 rollback 에 계획안까지 사라지지 않게 한다.
    db_session.commit()

    response = client.delete(f"/api/forms/{form_id}")

    assert response.status_code == 409
    assert response.json() == {
        "error": {
            "code": "IN_USE",
            "message": "이 양식으로 만든 계획안이 있어 지울 수 없습니다.",
            "fields": [],
        }
    }
    listed = client.get(f"/api/centers/{center.id}/forms")
    assert listed.status_code == 200
    assert form_id in [item["id"] for item in listed.json()["items"]]
    db_session.expire_all()
    assert db_session.scalar(select(Plan.form_id).where(Plan.id == plan_id)) == form_id


def test_다른_DB_거부는_409_로_숨기지_않는다(db_session, mine, monkeypatch):
    form_id = _register(mine["center"].id).json()["id"]

    def fail_commit():
        orig = Exception("different constraint")
        orig.diag = SimpleNamespace(constraint_name="some_other_constraint")
        raise IntegrityError("DELETE FROM forms", {}, orig)

    monkeypatch.setattr(db_session, "commit", fail_commit)
    with TestClient(app, raise_server_exceptions=False) as error_client:
        response = error_client.delete(f"/api/forms/{form_id}")
    assert response.status_code == 500


def test_남의_원은_등록도_목록도_삭제도_404_다(db_session, mine):
    other = mine["other"]
    theirs = Form(
        center_id=other.id,
        name="남의 양식",
        filename="남의 양식.hwpx",
        tables=[],
        labels=[],
        label_map={},
    )
    db_session.add(theirs)
    db_session.flush()

    for response, field in [
        (_register(other.id), "center_id"),
        (client.get(f"/api/centers/{other.id}/forms"), "center_id"),
        (client.delete(f"/api/forms/{theirs.id}"), "form_id"),
    ]:
        assert response.status_code == 404
        assert response.json()["error"]["fields"] == [field]
    assert db_session.get(Form, theirs.id) is not None
    assert _count(db_session) == 1


def test_토큰이_없으면_401_이고_parse_는_여전히_열려_있다(db_session):
    for response in [
        _register(1),
        client.get("/api/centers/1/forms"),
        client.delete("/api/forms/1"),
    ]:
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "UNAUTHENTICATED"

    parse = client.post("/api/forms/parse", files={"file": ("a.hwpx", _hwpx("주제"))})
    assert parse.status_code == 200


def test_읽지_못하면_행이_생기지_않는다(db_session, mine):
    """표 없음 · 손상 · 긴 이름은 422, 형식 틀림은 400. 어느 쪽도 저장하지 않는다."""
    center = mine["center"]

    for response, status_code in [
        (_register(center.id, content=_hwpx()), 422),
        (_register(center.id, content=b"not a zip"), 422),
        (_register(center.id, filename="가" * 251 + ".hwpx"), 422),
        (_register(center.id, filename="양식.pdf"), 400),
    ]:
        assert response.status_code == status_code
        assert response.json()["error"]["fields"] == ["file"]
    assert _count(db_session) == 0


def test_긴_한글_파일명도_등록된다(db_session, mine):
    """임시 파일 이름을 고정한 이유다 — 한글 100자는 300바이트라 리눅스 파일명 한도를 넘는다.

    macOS 는 글자 수로 세서 로컬에선 옛 코드도 통과한다. 서버 · CI(ubuntu)가 리눅스다.
    """
    filename = "가" * 100 + ".hwpx"

    response = _register(mine["center"].id, filename)

    assert response.status_code == 201
    assert response.json()["filename"] == filename
