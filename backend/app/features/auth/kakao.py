"""카카오 로그인 — 인가 코드를 카카오 계정 정보로 바꾼다 (ADR-063 · docs/api-spec.md §0-1).

카카오가 돌려준 `code` 로 카카오 토큰을 받고(kauth), 그 토큰으로 계정 정보를 읽는다(kapi).
**카카오 토큰은 여기서 쓰고 버린다** — 저장하지 않는다. 우리가 카카오 API 를 다시 부를 일이 없다.
"""

from dataclasses import dataclass
from urllib.parse import urlencode

import httpx

from app.config import settings

AUTHORIZE_URL = "https://kauth.kakao.com/oauth/authorize"
TOKEN_URL = "https://kauth.kakao.com/oauth/token"
PROFILE_URL = "https://kapi.kakao.com/v2/user/me"
TIMEOUT = 10.0


class KakaoNotConfigured(Exception):
    """서버에 REST API 키 · Redirect URI 가 없다."""


class KakaoCodeRejected(Exception):
    """카카오가 인가 코드를 받지 않았다 — 만료 · 이미 씀 · 다른 Redirect URI."""


class KakaoUnavailable(Exception):
    """카카오에 닿지 못했거나 알 수 없는 응답이 왔다."""


@dataclass(frozen=True)
class KakaoProfile:
    kakao_id: int
    # 검증된 이메일만 담는다. 동의하지 않았거나 검증 안 된 이메일이면 None.
    email: str | None
    nickname: str | None


def configured() -> bool:
    return bool(settings.kakao_rest_api_key and settings.kakao_redirect_uri)


def authorize_url(state: str) -> str:
    if not configured():
        raise KakaoNotConfigured
    query = urlencode(
        {
            "client_id": settings.kakao_rest_api_key,
            "redirect_uri": settings.kakao_redirect_uri,
            "response_type": "code",
            "state": state,
        }
    )
    return f"{AUTHORIZE_URL}?{query}"


def fetch_profile(code: str, client: httpx.Client | None = None) -> KakaoProfile:
    """`client` 는 테스트가 가짜 transport 를 끼우는 자리다."""
    if not configured():
        raise KakaoNotConfigured
    form = {
        "grant_type": "authorization_code",
        "client_id": settings.kakao_rest_api_key,
        "redirect_uri": settings.kakao_redirect_uri,
        "code": code,
    }
    # Client Secret 은 콘솔에서 켰을 때만 필요하다. 켰는데 안 보내면 카카오가 401 이다.
    if settings.kakao_client_secret:
        form["client_secret"] = settings.kakao_client_secret
    with client or httpx.Client(timeout=TIMEOUT) as http:
        try:
            token = http.post(TOKEN_URL, data=form)
            # 코드가 틀리면 400(KOE320 등)이다. 5xx · 그 밖은 카카오 쪽 문제로 본다.
            if token.status_code == 400:
                raise KakaoCodeRejected
            token.raise_for_status()
            access = token.json()["access_token"]
            me = http.get(PROFILE_URL, headers={"Authorization": f"Bearer {access}"})
            me.raise_for_status()
            body = me.json()
        except (httpx.HTTPError, KeyError, ValueError) as error:
            raise KakaoUnavailable from error
    return _profile(body)


def _profile(body: dict) -> KakaoProfile:
    try:
        kakao_id = int(body["id"])
    except (KeyError, TypeError, ValueError) as error:
        raise KakaoUnavailable from error
    account = body.get("kakao_account") or {}
    email = account.get("email")
    # 검증 안 된 이메일로 기존 계정에 붙으면 남의 계정을 가져갈 수 있다. 둘 다 참일 때만 쓴다.
    if not (email and account.get("is_email_valid") and account.get("is_email_verified")):
        email = None
    nickname = (account.get("profile") or {}).get("nickname")
    return KakaoProfile(
        kakao_id=kakao_id,
        email=email.strip().lower() if email else None,
        nickname=nickname.strip() if isinstance(nickname, str) and nickname.strip() else None,
    )
