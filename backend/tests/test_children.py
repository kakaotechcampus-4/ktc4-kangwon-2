"""아동 명단 API 의 요청 검증·에러 봉투·code 발급 배선 (docs/api-spec.md §2-1).

**라우터 단위 테스트다.** 세션을 스텁으로 갈아끼워 DB 없이 흐름만 본다 — 스텁 방식은
tests/test_centers.py 의 `_MissingCenterSession` 과 같다.
실제 PostgreSQL 저장과 반 사이 격리는 이 파일이 보지 않는다. 별도 통합 테스트가 맡을 몫이고
아직 이 브랜치에 없다 — 아래 TODO 참고.
"""

from datetime import UTC, datetime

import pytest
import yaml
from fastapi.testclient import TestClient

from app.db import get_session
from app.features.centers.models import Class
from app.main import app
from app.shared.childCode import _POOL_PATH

POOL = yaml.safe_load(_POOL_PATH.read_text(encoding="utf-8"))
client = TestClient(app)


class _Rows(list):
    """`session.scalars(...)` 가 돌려주는 것의 최소 대역."""

    def all(self) -> list:
        return list(self)


class _FakeSession:
    """한 반만 다루는 최소 스텁. 반 사이 격리는 DB 가 필요해 여기서 보지 않는다."""

    def __init__(self, class_exists: bool = True, children: list | None = None):
        self.class_exists = class_exists
        self.children = list(children or [])
        self.commits = 0

    def get(self, model, pk):
        if model is Class:
            return Class() if self.class_exists else None
        return next((c for c in self.children if c.id == pk), None)

    def scalars(self, statement):
        return _Rows(self.children)

    def add(self, obj):
        obj.id = len(self.children) + 1
        obj.created_at = datetime.now(UTC)
        self.children.append(obj)

    def delete(self, obj):
        self.children.remove(obj)

    def commit(self):
        self.commits += 1

    def refresh(self, obj):
        pass


@pytest.fixture
def session():
    """스텁 세션을 주입한 상태로 한 테스트를 돌린다. 오버라이드는 반드시 되돌린다."""
    fake = _FakeSession()
    app.dependency_overrides[get_session] = lambda: fake
    try:
        yield fake
    finally:
        app.dependency_overrides.clear()


def test_registering_a_child_issues_a_pseudonym_from_the_pool(session):
    response = client.post("/api/classes/1/children", json={"name": "이승석"})

    assert response.status_code == 201
    body = response.json()
    assert body["class_id"] == 1
    assert body["name"] == "이승석"
    assert body["created_at"]
    # 실명에서 파생하지 않는다 — 받침이 같은 쪽 Pool 에서 나온다 (ADR-004).
    assert body["code"] in POOL["with_final"]
    assert session.commits == 1


def test_a_name_without_a_final_consonant_gets_a_matching_pseudonym(session):
    code = client.post("/api/classes/1/children", json={"name": "김하나"}).json()["code"]

    assert code in POOL["without_final"]


def test_codes_do_not_repeat_inside_one_class(session):
    codes = [
        client.post("/api/classes/1/children", json={"name": "박서준"}).json()["code"]
        for _ in range(5)
    ]

    assert len(set(codes)) == 5


def test_client_supplied_code_is_reported_not_ignored(session):
    # code 는 서버가 발급한다. 조용히 버리면 FE 가 보낸 값이 쓰인 줄 안다.
    response = client.post("/api/classes/1/children", json={"name": "이승석", "code": "승석"})

    assert response.status_code == 422
    assert response.json()["error"]["fields"] == ["code"]


@pytest.mark.parametrize("blank", ["", " ", "\t"])
def test_blank_name_is_rejected(session, blank):
    response = client.post("/api/classes/1/children", json={"name": blank})

    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_FAILED"
    assert body["error"]["fields"] == ["name"]


def test_registering_into_a_missing_class_returns_not_found(session):
    session.class_exists = False

    response = client.post("/api/classes/999/children", json={"name": "이승석"})

    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "NOT_FOUND",
            "message": "반을 찾을 수 없습니다.",
            "fields": ["class_id"],
        }
    }


def test_a_class_with_no_children_returns_an_empty_items_envelope(session):
    response = client.get("/api/classes/1/children")

    assert response.status_code == 200
    # count 를 따로 보내지 않는다 (§2-1).
    assert response.json() == {"items": []}


def test_listing_children_of_a_missing_class_returns_not_found(session):
    session.class_exists = False

    response = client.get("/api/classes/999/children")

    assert response.status_code == 404
    assert response.json()["error"]["fields"] == ["class_id"]


def test_deleting_a_child_returns_204_and_drops_it_from_the_list(session):
    child_id = client.post("/api/classes/1/children", json={"name": "이승석"}).json()["id"]

    assert client.delete(f"/api/children/{child_id}").status_code == 204
    assert client.get("/api/classes/1/children").json() == {"items": []}


def test_deleting_a_missing_child_returns_not_found(session):
    response = client.delete("/api/children/999")

    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "NOT_FOUND",
            "message": "아동을 찾을 수 없습니다.",
            "fields": ["child_id"],
        }
    }


# TODO: 아래는 실제 PostgreSQL 통합 테스트로 확인한다. 스텁 세션은 SQL 을 해석하지 않아
# WHERE·ORDER BY 가 실제로 걸리는지, 행이 정말 남는지를 볼 수 없다.
#   - POST → children 행 저장, 응답 code 와 DB row 의 code 가 같다
#   - GET 은 그 반의 아동만 준다 — 다른 반 아동이 섞이지 않는다
#   - 다른 반에서는 같은 code 를 다시 발급할 수 있다
#   - DELETE 후 행이 사라지고, 그 code 가 다시 후보가 된다
