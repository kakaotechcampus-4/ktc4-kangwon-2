"""원·반을 진짜 Postgres 로 확인한다 (docs/api-spec.md §1 · §2).

`test_centers.py` 는 요청·검증·에러 봉투를 본다. 저장이 실제로 되는지는 가짜 세션으로
확인할 수 없다 — 여기가 그 절반이다.

`db_session` 을 받는 테스트는 끝나면 전부 롤백된다(`conftest.py`).
"""

from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.features.centers.models import Center, Class
from app.main import app
from app.shared.school_year import school_year_of

client = TestClient(app)

CENTER = {
    "name": "쓱싹 어린이집",
    "director_name": "김원장",
    "region_sido": "충청북도",
    "region_sigungu": "충주시",
}
CLASSROOM = {
    "name": "햇님반",
    "age_min": 3,
    "age_max": 4,
    "child_count": 18,
    "teacher_name": "김선생",
    "consent_confirmed": True,
}


def create_center(**overrides) -> int:
    response = client.post("/api/centers", json={**CENTER, **overrides})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_원을_만들면_행이_남고_지역이_두_칸으로_저장된다(db_session):
    center_id = create_center()

    row = db_session.get(Center, center_id)
    assert (row.region_sido, row.region_sigungu) == ("충청북도", "충주시")
    assert row.director_name == "김원장"


def test_반이_없는_원은_빈_배열이다(db_session):
    """없는 원(404)과 구분한다 — 같은 응답이면 FE 가 「반을 추가해 주세요」를 없는 원에도 띄운다."""
    center_id = create_center()

    response = client.get(f"/api/centers/{center_id}/classes")

    assert response.status_code == 200
    assert response.json() == {"items": []}


def test_없는_원의_반_목록은_404_다(db_session):
    response = client.get("/api/centers/999999/classes")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_다른_원의_반이_섞이지_않는다(db_session):
    first, second = create_center(), create_center(name="다른 어린이집")
    client.post(f"/api/centers/{first}/classes", json=CLASSROOM)
    client.post(f"/api/centers/{second}/classes", json={**CLASSROOM, "name": "달님반"})

    items = client.get(f"/api/centers/{first}/classes").json()["items"]

    assert [item["name"] for item in items] == ["햇님반"]


def test_반을_만들면_행이_남고_학년도를_서버가_채운다(db_session):
    center_id = create_center()

    response = client.post(f"/api/centers/{center_id}/classes", json=CLASSROOM)

    assert response.status_code == 201, response.text
    row = db_session.get(Class, response.json()["id"])
    assert row.center_id == center_id
    assert row.name == "햇님반"
    assert (row.age_min, row.age_max) == (3, 4)
    assert row.child_count == 18
    assert row.teacher_name == "김선생"
    # 화면에 고르는 칸이 없다. FE 가 보낸 값이 아니라 서버가 계산한 값이어야 한다.
    assert row.school_year == school_year_of(datetime.now(UTC))
    assert response.json()["school_year"] == row.school_year


def test_동의를_확인하면_시각이_남고_아니면_null_이다(db_session):
    center_id = create_center()

    confirmed = client.post(f"/api/centers/{center_id}/classes", json=CLASSROOM).json()
    skipped = client.post(
        f"/api/centers/{center_id}/classes",
        json={**CLASSROOM, "name": "달님반", "consent_confirmed": False},
    ).json()

    assert confirmed["consent_confirmed_at"] is not None
    # 아동 명단을 건너뛰는 경로가 정상이다. 검증 실패가 아니다 (§2-1).
    assert skipped["consent_confirmed_at"] is None

    row = db_session.get(Class, confirmed["id"])
    # 시각대가 없으면 나중에 KST 인지 UTC 인지 못 가린다.
    assert row.consent_confirmed_at.tzinfo is not None


def test_학년도가_같으면_같은_이름의_반을_두_번_못_만든다(db_session):
    """`UNIQUE(center_id, name, school_year)` 위반을 409 로 바꾼다 (docs/api-spec.md §2).

    먼저 조회해서 막지 않는다 — 조회와 INSERT 사이 틈으로 들어온 요청도 결국 여기로 온다.
    """
    center_id = create_center()
    client.post(f"/api/centers/{center_id}/classes", json=CLASSROOM)

    response = client.post(f"/api/centers/{center_id}/classes", json=CLASSROOM)

    assert response.status_code == 409
    assert response.json() == {
        "error": {
            "code": "ALREADY_EXISTS",
            "message": "같은 이름의 반이 이미 있습니다.",
            # 학년도는 서버가 채우므로 교사가 고칠 수 있는 칸은 name 하나다.
            "fields": ["name"],
        }
    }
    rows = db_session.scalars(
        select(Class).where(Class.center_id == center_id, Class.name == "햇님반")
    ).all()
    assert len(rows) == 1


def test_중복으로_409_가_나도_세션이_살아_있다(db_session):
    """제약 위반 뒤 rollback 을 빠뜨리면 그 세션의 다음 질의가 전부 죽는다.

    Postgres 는 실패한 트랜잭션 안의 후속 질의를 InFailedSqlTransaction 으로 막는다.
    한 요청이 실패한 뒤 다음 요청까지 같이 죽으면 원인을 찾기 어렵다.
    """
    center_id = create_center()
    client.post(f"/api/centers/{center_id}/classes", json=CLASSROOM)
    assert client.post(f"/api/centers/{center_id}/classes", json=CLASSROOM).status_code == 409

    assert client.get(f"/api/centers/{center_id}/classes").status_code == 200
    created = client.post(f"/api/centers/{center_id}/classes", json={**CLASSROOM, "name": "달님반"})

    assert created.status_code == 201, created.text
    assert db_session.get(Class, created.json()["id"]) is not None


def test_같은_이름이라도_원이_다르면_따로_만들어진다(db_session):
    first, second = create_center(), create_center(name="다른 어린이집")

    client.post(f"/api/centers/{first}/classes", json=CLASSROOM)
    response = client.post(f"/api/centers/{second}/classes", json=CLASSROOM)

    assert response.status_code == 201
