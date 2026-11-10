"""카카오 로그인 (ADR-069 · docs/api-spec.md §0-1).

카카오에는 닿지 않는다. 주고받는 모양은 `httpx.MockTransport` 로, 계정 잇기는 `fetch_profile` 을
갈아 끼워 본다. **진짜 카카오와 되는지는 키를 넣고 화면에서 한 번 눌러 봐야 안다.**
"""

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import settings
from app.features.auth import kakao
from app.features.auth.models import User
from app.main import app

client = TestClient(app)
STATE = "s" * 32


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setattr(settings, "kakao_rest_api_key", "rest-key")
    monkeypatch.setattr(settings, "kakao_client_secret", None)
    monkeypatch.setattr(settings, "kakao_redirect_uri", "https://ssample.example/login/kakao")


def kakao_server(token_status=200, profile=None, seen=None):
    """카카오 두 주소를 흉내 낸다. `seen` 에 받은 요청을 쌓는다."""
    profile = profile or {
        "id": 4242,
        "kakao_account": {
            "email": "Teacher@Example.com",
            "is_email_valid": True,
            "is_email_verified": True,
            "profile": {"nickname": "김선생"},
        },
    }

    def handle(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        if request.url.path == "/oauth/token":
            if token_status != 200:
                return httpx.Response(token_status, json={"error_code": "KOE320"})
            return httpx.Response(200, json={"access_token": "kakao-access"})
        assert request.headers["Authorization"] == "Bearer kakao-access"
        return httpx.Response(200, json=profile)

    return httpx.Client(transport=httpx.MockTransport(handle))


# ── 카카오와 주고받기 ─────────────────────────────────


def test_코드를_카카오_계정으로_바꾼다(configured):
    seen = []
    profile = kakao.fetch_profile("the-code", kakao_server(seen=seen))

    assert profile == kakao.KakaoProfile(4242, "teacher@example.com", "김선생")
    form = dict(httpx.QueryParams(seen[0].content.decode()))
    assert form == {
        "grant_type": "authorization_code",
        "client_id": "rest-key",
        "redirect_uri": "https://ssample.example/login/kakao",
        "code": "the-code",
    }


def test_client_secret_은_있을_때만_보낸다(configured, monkeypatch):
    monkeypatch.setattr(settings, "kakao_client_secret", "secret")
    seen = []
    kakao.fetch_profile("c", kakao_server(seen=seen))

    assert dict(httpx.QueryParams(seen[0].content.decode()))["client_secret"] == "secret"


def test_검증_안_된_이메일은_버린다(configured):
    """검증 안 된 이메일로 기존 계정에 붙으면 남의 계정을 가져갈 수 있다."""
    profile = {"id": 1, "kakao_account": {"email": "a@b.kr", "is_email_verified": False}}

    assert kakao.fetch_profile("c", kakao_server(profile=profile)).email is None


def test_카카오가_코드를_안_받으면_CodeRejected(configured):
    with pytest.raises(kakao.KakaoCodeRejected):
        kakao.fetch_profile("c", kakao_server(token_status=400))


def test_카카오가_5xx_면_Unavailable(configured):
    with pytest.raises(kakao.KakaoUnavailable):
        kakao.fetch_profile("c", kakao_server(token_status=502))


# ── 동의 화면 주소 ────────────────────────────────────


def test_키가_없으면_503_이다(monkeypatch):
    monkeypatch.setattr(settings, "kakao_rest_api_key", None)
    response = client.get("/api/auth/kakao/authorize", params={"state": STATE})

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "DEPENDENCY_UNAVAILABLE"


def test_동의_화면_주소에_state_를_싣는다(configured):
    response = client.get("/api/auth/kakao/authorize", params={"state": STATE})

    assert response.status_code == 200
    url = httpx.URL(response.json()["url"])
    assert url.host == "kauth.kakao.com"
    assert url.params["client_id"] == "rest-key"
    assert url.params["state"] == STATE
    assert url.params["redirect_uri"] == "https://ssample.example/login/kakao"


def test_짧은_state_는_422(configured):
    assert client.get("/api/auth/kakao/authorize", params={"state": "short"}).status_code == 422


# ── 계정 잇기 ─────────────────────────────────────────


def use_profile(monkeypatch, kakao_id=4242, email="teacher@example.com", nickname="김선생"):
    profile = kakao.KakaoProfile(kakao_id, email, nickname)
    monkeypatch.setattr(kakao, "fetch_profile", lambda code: profile)


def test_처음이면_계정을_만들고_다음엔_같은_계정이다(db_session, monkeypatch):
    use_profile(monkeypatch)
    first = client.post("/api/auth/kakao", json={"code": "c1"})
    second = client.post("/api/auth/kakao", json={"code": "c2"})

    assert first.status_code == 200, first.text
    assert first.json()["user"]["name"] == "김선생"
    assert second.json()["user"]["id"] == first.json()["user"]["id"]
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {second.json()['token']}"})
    assert me.json()["email"] == "teacher@example.com"


def test_같은_이메일로_가입한_계정에_잇는다(db_session, monkeypatch):
    signup = client.post(
        "/api/auth/signup",
        json={"email": "teacher@example.com", "name": "이선생", "password": "sseuksak-2026"},
    )
    use_profile(monkeypatch)
    response = client.post("/api/auth/kakao", json={"code": "c"})

    assert response.json()["user"]["id"] == signup.json()["user"]["id"]
    # 이름은 교사가 가입 때 적은 것을 둔다. 카카오 별명으로 덮지 않는다.
    assert response.json()["user"]["name"] == "이선생"


def test_이으면_먼저_가입한_비밀번호와_토큰을_끊는다(db_session, monkeypatch):
    """남의 이메일로 먼저 가입한 사람이 진짜 주인이 카카오로 들어온 뒤에도 남지 못한다(ADR-091).

    이메일 가입은 메일 주인인지 확인하지 않는다 — 누가 만든 비밀번호인지 서버는 모른다.
    """
    squatter = client.post(
        "/api/auth/signup",
        json={"email": "teacher@example.com", "name": "가로챈사람", "password": "sseuksak-2026"},
    ).json()["token"]
    use_profile(monkeypatch)
    owner = client.post("/api/auth/kakao", json={"code": "c"}).json()["token"]

    login = client.post(
        "/api/auth/login", json={"email": "teacher@example.com", "password": "sseuksak-2026"}
    )
    assert login.status_code == 401

    def me(token):
        return client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert me(squatter).status_code == 401
    assert me(owner).status_code == 200
    # 다시 카카오로 들어와도 버전을 또 올리지 않는다 — 주인의 다른 기기가 튕기지 않는다.
    again = client.post("/api/auth/kakao", json={"code": "c2"}).json()["token"]
    assert me(owner).status_code == 200
    assert me(again).status_code == 200


def test_카카오로만_만든_계정은_비밀번호로_못_들어온다(db_session, monkeypatch):
    use_profile(monkeypatch)
    client.post("/api/auth/kakao", json={"code": "c"})

    for password in ("", "sseuksak-2026"):
        login = client.post(
            "/api/auth/login", json={"email": "teacher@example.com", "password": password}
        )
        assert login.status_code == 401


def test_이메일이_없으면_422(db_session, monkeypatch):
    use_profile(monkeypatch, email=None)
    response = client.post("/api/auth/kakao", json={"code": "c"})

    assert response.status_code == 422
    assert response.json()["error"]["fields"] == ["email"]
    assert db_session.scalar(select(User).where(User.kakao_id == 4242)) is None


def test_다른_카카오와_이어진_이메일이면_409(db_session, monkeypatch):
    use_profile(monkeypatch, kakao_id=1)
    client.post("/api/auth/kakao", json={"code": "c"})
    use_profile(monkeypatch, kakao_id=2)

    assert client.post("/api/auth/kakao", json={"code": "c"}).status_code == 409


def test_별명이_없으면_이메일_앞부분을_이름으로(db_session, monkeypatch):
    use_profile(monkeypatch, nickname=None)

    assert client.post("/api/auth/kakao", json={"code": "c"}).json()["user"]["name"] == "teacher"


def test_코드를_카카오가_거절하면_422_이고_401_이_아니다(db_session, monkeypatch):
    """401 은 화면이 「로그인 만료」로 읽는다."""

    def rejected(code):
        raise kakao.KakaoCodeRejected

    monkeypatch.setattr(kakao, "fetch_profile", rejected)
    response = client.post("/api/auth/kakao", json={"code": "c"})

    assert response.status_code == 422
    assert response.json()["error"]["fields"] == ["code"]


def test_빈_코드는_422(db_session):
    assert client.post("/api/auth/kakao", json={"code": "  "}).status_code == 422
