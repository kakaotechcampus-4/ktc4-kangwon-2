"""회원가입·로그인·인증·인가 (docs/api-spec.md §0).

멘토 리뷰(PR #52) — "실제 아동명이 내려올 수도 있어서 전역적인 인증 처리가 있으면 좋을 거 같네요"
"""

import time

import pytest
from fastapi.testclient import TestClient

from app.features.auth.models import User
from app.main import app
from app.shared.auth.passwords import hash_password, verify_password
from app.shared.auth.tokens import TOKEN_TTL_SECONDS, TokenError, issue, read

client = TestClient(app)

ACCOUNT = {"email": "teacher@example.com", "name": "김선생", "password": "sseuksak-2026"}
# 로그인은 email·password 만 받는다 — name 을 같이 보내면 422 다(extra="forbid").
CREDENTIALS = {"email": ACCOUNT["email"], "password": ACCOUNT["password"]}
CENTER = {
    "name": "쓱싹 어린이집",
    "director_name": "김원장",
    "region_sido": "충청북도",
    "region_sigungu": "충주시",
}
CLASSROOM = {"name": "햇님반", "age_min": 3, "age_max": 4, "teacher_name": "김선생"}


def signup(db_session, **overrides) -> str:
    response = client.post("/api/auth/signup", json={**ACCOUNT, **overrides})
    assert response.status_code == 201, response.text
    return response.json()["token"]


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ── 비밀번호 ──────────────────────────────────────────


def test_비밀번호는_계정마다_다른_salt_를_쓴다():
    """같은 비밀번호라도 저장된 값이 달라야 한다. 같으면 한 번 깨질 때 전부 깨진다."""
    first_hash, first_salt = hash_password("sseuksak-2026")
    second_hash, second_salt = hash_password("sseuksak-2026")

    assert first_salt != second_salt
    assert first_hash != second_hash
    assert verify_password("sseuksak-2026", first_hash, first_salt)
    assert verify_password("sseuksak-2026", second_hash, second_salt)


def test_틀린_비밀번호는_통과하지_못한다():
    password_hash, salt = hash_password("sseuksak-2026")

    assert verify_password("sseuksak-2027", password_hash, salt) is False
    assert verify_password("", password_hash, salt) is False


# ── 토큰 ─────────────────────────────────────────────


def test_토큰은_발급한_사람을_되찾아_준다():
    assert read(issue(7, "secret"), "secret") == 7


def test_다른_열쇠로_서명한_토큰은_거부한다():
    """열쇠가 새면 누구나 토큰을 만들 수 있다. 서명 검증이 그걸 막는 유일한 장치다."""
    with pytest.raises(TokenError):
        read(issue(7, "secret"), "another-secret")


def test_본문을_고친_토큰은_거부한다():
    body, _, signature = issue(7, "secret").partition(".")
    with pytest.raises(TokenError):
        read(f"{body}x.{signature}", "secret")


def test_만료된_토큰은_거부한다():
    past = int(time.time()) - TOKEN_TTL_SECONDS - 1
    with pytest.raises(TokenError):
        read(issue(7, "secret", now=past), "secret")


@pytest.mark.parametrize("broken", ["", ".", "abc", "abc.", ".abc"])
def test_모양이_틀린_토큰은_거부한다(broken):
    with pytest.raises(TokenError):
        read(broken, "secret")


# ── 회원가입·로그인 ───────────────────────────────────


def test_가입하면_바로_로그인된다(db_session):
    response = client.post("/api/auth/signup", json=ACCOUNT)

    assert response.status_code == 201
    body = response.json()
    assert body["user"]["email"] == ACCOUNT["email"]
    # 온보딩 전이라 아직 원이 없다.
    assert body["user"]["center_id"] is None
    assert client.get("/api/auth/me", headers=bearer(body["token"])).status_code == 200


def test_비밀번호를_저장하지도_돌려주지도_않는다(db_session):
    token = signup(db_session)

    assert ACCOUNT["password"] not in client.get("/api/auth/me", headers=bearer(token)).text
    stored = db_session.query(User).one()
    assert ACCOUNT["password"].encode() not in stored.password_hash


def test_같은_이메일로_두_번_가입할_수_없다(db_session):
    signup(db_session)

    response = client.post("/api/auth/signup", json=ACCOUNT)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "ALREADY_EXISTS"


def test_없는_이메일과_틀린_비밀번호가_같은_응답이다(db_session):
    """나누면 어느 이메일이 가입돼 있는지 확인하는 수단이 된다."""
    signup(db_session)

    missing = client.post("/api/auth/login", json={"email": "nobody@example.com", "password": "x"})
    wrong = client.post("/api/auth/login", json={**CREDENTIALS, "password": "wrong-password"})

    assert missing.status_code == wrong.status_code == 401
    assert missing.json() == wrong.json()


def test_짧은_비밀번호를_거부한다(db_session):
    assert (
        client.post("/api/auth/signup", json={**ACCOUNT, "password": "1234567"}).status_code == 422
    )


# ── 인증 ─────────────────────────────────────────────


@pytest.mark.parametrize(
    "headers",
    [{}, {"Authorization": "Bearer "}, {"Authorization": "wrong"}, {"Authorization": "Bearer xx"}],
)
def test_토큰_없이_아동_명단을_볼_수_없다(db_session, headers):
    """멘토 리뷰의 그 자리다. 아동 실명이 내려오는 API 다."""
    response = client.get("/api/classes/1/children", headers=headers)

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHENTICATED"


def test_왜_401_인지는_알려주지_않는다(db_session):
    """만료와 위조를 구분해 주면 토큰을 맞춰 보는 쪽에 힌트가 된다."""
    expired = issue(1, "test-only-not-a-secret", now=int(time.time()) - TOKEN_TTL_SECONDS - 1)

    forged = client.get("/api/classes/1/children", headers=bearer("forged.token"))
    stale = client.get("/api/classes/1/children", headers=bearer(expired))

    assert forged.json() == stale.json()


def test_회원가입과_로그인은_토큰_없이_열려_있다(db_session):
    assert client.post("/api/auth/signup", json=ACCOUNT).status_code == 201
    assert client.post("/api/auth/login", json=CREDENTIALS).status_code == 200


# ── 인가 ─────────────────────────────────────────────


def test_원을_만들면_내_원이_된다(db_session):
    token = signup(db_session)

    center = client.post("/api/centers", json=CENTER, headers=bearer(token)).json()

    assert client.get("/api/auth/me", headers=bearer(token)).json()["center_id"] == center["id"]


def test_한_계정은_원_하나다(db_session):
    token = signup(db_session)
    client.post("/api/centers", json=CENTER, headers=bearer(token))

    response = client.post("/api/centers", json=CENTER, headers=bearer(token))

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "ALREADY_EXISTS"


def test_남의_원_아동_명단을_볼_수_없다(db_session):
    """로그인만 확인하면 반쪽이다 — class_id 를 바꿔가며 전부 읽을 수 있다."""
    mine = signup(db_session)
    other = signup(db_session, email="other@example.com")

    center = client.post("/api/centers", json=CENTER, headers=bearer(mine)).json()
    classroom = client.post(
        f"/api/centers/{center['id']}/classes", json=CLASSROOM, headers=bearer(mine)
    ).json()
    client.post(
        f"/api/classes/{classroom['id']}/children", json={"name": "박서준"}, headers=bearer(mine)
    )

    stolen = client.get(f"/api/classes/{classroom['id']}/children", headers=bearer(other))

    assert stolen.status_code == 404
    assert "박서준" not in stolen.text


def test_남의_원과_없는_원이_같은_응답이다(db_session):
    """403 이면 그 id 가 존재한다는 사실을 알려준다."""
    mine = signup(db_session)
    other = signup(db_session, email="other@example.com")
    center = client.post("/api/centers", json=CENTER, headers=bearer(mine)).json()

    theirs = client.get(f"/api/centers/{center['id']}/classes", headers=bearer(other))
    missing = client.get("/api/centers/999999/classes", headers=bearer(other))

    assert theirs.status_code == missing.status_code == 404
    assert theirs.json() == missing.json()


def test_온보딩_전에는_어떤_원도_내_것이_아니다(db_session):
    """center_id 가 None 인데 통과시키면 가입만 하고 남의 원을 읽는다."""
    mine = signup(db_session)
    other = signup(db_session, email="other@example.com")
    center = client.post("/api/centers", json=CENTER, headers=bearer(mine)).json()

    assert (
        client.get(f"/api/centers/{center['id']}/classes", headers=bearer(other)).status_code == 404
    )


def test_남의_아동을_지울_수_없다(db_session):
    mine = signup(db_session)
    other = signup(db_session, email="other@example.com")
    center = client.post("/api/centers", json=CENTER, headers=bearer(mine)).json()
    classroom = client.post(
        f"/api/centers/{center['id']}/classes", json=CLASSROOM, headers=bearer(mine)
    ).json()
    child = client.post(
        f"/api/classes/{classroom['id']}/children", json={"name": "박서준"}, headers=bearer(mine)
    ).json()

    assert client.delete(f"/api/children/{child['id']}", headers=bearer(other)).status_code == 404
    assert client.delete(f"/api/children/{child['id']}", headers=bearer(mine)).status_code == 204
