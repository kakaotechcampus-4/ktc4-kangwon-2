"""연간계획안 API. 계약(docs/api-spec.md §4~§7)대로 답하는지 본다.

**생성 규칙을 여기서 확인하지 않는다.** 12개월 주제를 어떻게 고르는지는
p0-planning 의 테스트가 본다. 이 파일은 「계약대로 내려주나 · 남의 원을 막나 ·
확정 뒤 수정을 막나」만 본다.
"""

import pytest
from fastapi.testclient import TestClient

from app.features.centers.models import Center, Class
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _logged_in(teacher):
    """이 파일은 인증을 다루지 않는다. 로그인한 교사로 고정한다 (인증은 test_auth.py)."""
    return teacher


@pytest.fixture
def mine(db_session, teacher):
    """교사의 원과 반 하나. 계획안은 반이 있어야 만들 수 있다."""
    center = Center(
        name="테스트어린이집",
        director_name="김원장",
        region_sido="강원특별자치도",
        region_sigungu="춘천시",
    )
    db_session.add(center)
    db_session.flush()
    klass = Class(
        center_id=center.id,
        name="햇살반",
        school_year=2026,
        age_min=3,
        age_max=3,
        teacher_name="김선생",
    )
    db_session.add(klass)
    db_session.flush()
    teacher.center_id = center.id
    return klass


def _create(klass) -> dict:
    response = client.post("/api/plans/annual", json={"class_id": klass.id, "form_id": None})
    assert response.status_code == 201, response.text
    return response.json()


def test_만들면_12개월치가_DRAFT_로_내려온다(db_session, mine):
    body = _create(mine)

    assert body["class_id"] == mine.id
    assert body["school_year"] == 2026
    assert body["status"] == "DRAFT"
    # 3월 시작 익년 2월 끝. 순서가 흔들리면 화면이 다른 달을 그린다.
    assert [month["month"] for month in body["months"]] == [3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 1, 2]


def test_달마다_근거가_정확히_하나씩_붙는다(db_session, mine):
    body = _create(mine)

    for month in body["months"]:
        assert month["theme"].strip()
        themes = [e for e in month["evidence"] if e["source_type"] == "THEME_REFERENCE"]
        assert len(themes) == 1, month
        assert themes[0]["source_id"]
        assert month["generation"]["method"]


def test_안전교육은_빈_배열이되_이유를_같이_준다(db_session, mine):
    """빈 배열만으로는 「안 한다」와 「아직 모른다」를 구분하지 못한다(§4)."""
    body = _create(mine)

    for month in body["months"]:
        assert month["safety_education"] == []
        assert month["safety_education_state"] == "SOURCE_REQUIRED"


def test_목록은_요약만_주고_상세는_단건이_준다(db_session, mine):
    created = _create(mine)

    listed = client.get("/api/plans/annual", params={"class_id": mine.id}).json()
    assert [item["id"] for item in listed["items"]] == [created["id"]]
    assert "months" not in listed["items"][0]
    assert listed["items"][0]["confirmed_at"] is None

    detail = client.get(f"/api/plans/annual/{created['id']}").json()
    assert len(detail["months"]) == 12


def test_칸을_고치면_그_달만_돌아오고_근거는_그대로다(db_session, mine):
    created = _create(mine)
    before = created["months"][0]

    response = client.put(
        f"/api/plans/annual/{created['id']}/months/3",
        json={"theme": "고친 주제", "sub_themes": ["첫째 주", "둘째 주"]},
    )

    assert response.status_code == 200, response.text
    after = response.json()
    assert after["month"] == 3
    assert after["theme"] == "고친 주제"
    assert after["sub_themes"] == ["첫째 주", "둘째 주"]
    # 교사가 문구를 고쳐도 그 칸의 근거는 안 바뀐다(§6).
    assert after["evidence"] == before["evidence"]
    assert after["generation"]["method"] == "TEACHER_EDIT"


def test_소주제를_빼고_보내면_422_이고_아무것도_저장되지_않는다(db_session, mine):
    created = _create(mine)

    response = client.put(
        f"/api/plans/annual/{created['id']}/months/3", json={"theme": "고친 주제"}
    )

    assert response.status_code == 422
    assert response.json()["error"]["fields"] == ["sub_themes"]
    unchanged = client.get(f"/api/plans/annual/{created['id']}").json()
    assert unchanged["months"][0]["theme"] == created["months"][0]["theme"]


def test_확정하면_상태가_바뀌고_그_뒤로는_못_고친다(db_session, mine):
    created = _create(mine)

    confirmed = client.post(f"/api/plans/annual/{created['id']}/confirm")
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["status"] == "CONFIRMED"
    assert confirmed.json()["confirmed_at"]

    blocked = client.put(
        f"/api/plans/annual/{created['id']}/months/3",
        json={"theme": "또 고침", "sub_themes": []},
    )
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "ALREADY_CONFIRMED"


def test_감사_기록에_생성과_확정이_남는다(db_session, mine):
    created = _create(mine)
    client.put(
        f"/api/plans/annual/{created['id']}/months/3",
        json={"theme": "고친 주제", "sub_themes": []},
    )
    client.post(f"/api/plans/annual/{created['id']}/confirm")

    events = client.get(f"/api/plans/annual/{created['id']}/audit").json()["items"]
    types = [event["type"] for event in events]
    assert "TEACHER_EDITED" in types
    assert "CONFIRMED" in types


def test_남의_반으로는_만들지_못하고_남의_계획안은_안_보인다(db_session, mine, teacher):
    created = _create(mine)
    other = Center(
        name="남의어린이집",
        director_name="박원장",
        region_sido="강원특별자치도",
        region_sigungu="원주시",
    )
    db_session.add(other)
    db_session.flush()
    teacher.center_id = other.id

    assert client.get(f"/api/plans/annual/{created['id']}").status_code == 404
    assert client.post(f"/api/plans/annual/{created['id']}/confirm").status_code == 404
    assert client.get("/api/plans/annual").json()["items"] == []
    assert client.post("/api/plans/annual", json={"class_id": mine.id}).status_code == 404


def test_없는_달은_404(db_session, mine):
    created = _create(mine)

    response = client.put(
        f"/api/plans/annual/{created['id']}/months/13", json={"theme": "x", "sub_themes": []}
    )
    assert response.status_code == 404


def test_로그인_없이는_전부_401(db_session, mine):
    """라우터를 main.py 에 인증 없이 등록하는 실수를 막는다.

    다른 테스트는 전부 로그인 상태라, 등록을 빠뜨려도 통과한다.
    """
    created = _create(mine)
    app.dependency_overrides.clear()
    try:
        for method, path in [
            ("POST", "/api/plans/annual"),
            ("GET", "/api/plans/annual"),
            ("GET", f"/api/plans/annual/{created['id']}"),
            ("PUT", f"/api/plans/annual/{created['id']}/months/3"),
            ("POST", f"/api/plans/annual/{created['id']}/confirm"),
            ("GET", f"/api/plans/annual/{created['id']}/audit"),
        ]:
            response = client.request(method, path, json={})
            assert response.status_code == 401, f"{method} {path} -> {response.status_code}"
            assert response.json()["error"]["code"] == "UNAUTHENTICATED"
    finally:
        app.dependency_overrides.clear()


# ── 생성이 실패했을 때 ──────────────────────────────────────────────────────


def _breaks(monkeypatch, error):
    """생성기를 **만드는 단계**가 실패하게 한다 (설정이 없을 때)."""

    def boom():
        raise error

    monkeypatch.setattr("app.features.plans.router.theme_text_generator", boom)


def _generator_raises(monkeypatch, error):
    """생성기를 만들기는 하는데 **부를 때** 실패하게 한다 (호출이 깨질 때).

    p0-planning 이 이 오류를 YearlyApplicationError 로 감싸므로, 라우터가
    `__cause__` 를 보고 코드를 갈라야 한다.
    """

    class _Broken:
        def generate(self, requests):
            raise error

    monkeypatch.setattr("app.features.plans.router.theme_text_generator", lambda: _Broken())


def test_설정이_없으면_503_이고_재시도_버튼을_띄우지_않는다(db_session, mine, monkeypatch):
    """교사가 고칠 수 없다. 100번 눌러도 같다(api-spec 공통)."""
    from app.features.plans.llm import ThemeTextUnavailable

    _breaks(monkeypatch, ThemeTextUnavailable("키가 없다"))

    response = client.post("/api/plans/annual", json={"class_id": mine.id})

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "DEPENDENCY_UNAVAILABLE"


def test_한도에_걸리면_운영_문의_코드로_나온다(db_session, mine, monkeypatch):
    from app.features.plans.llm import ThemeTextBudgetExceeded

    _generator_raises(monkeypatch, ThemeTextBudgetExceeded("429"))

    response = client.post("/api/plans/annual", json={"class_id": mine.id})

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "LLM_BUDGET_EXCEEDED"


def test_생성이_실패하면_부분_결과가_남지_않는다(db_session, mine, monkeypatch):
    """§4 · 공통 GENERATION_FAILED — 반쯤 만들어진 계획안을 저장하지 않는다."""
    from app.features.plans.llm import ThemeTextFailed

    _generator_raises(monkeypatch, ThemeTextFailed("빠진 달이 있다"))

    response = client.post("/api/plans/annual", json={"class_id": mine.id})

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "GENERATION_FAILED"
    assert client.get("/api/plans/annual").json()["items"] == []
