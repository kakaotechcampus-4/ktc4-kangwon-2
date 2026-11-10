"""로그인 토큰. 표준 라이브러리만 쓴다.

서버가 서명한 문자열이다. 안에 「누구인지」와 「언제까지인지」만 들어 있고, 서명이
맞아야 받아들인다. 토큰을 DB 에 저장하지 않으므로 로그인 때마다 조회가 없다.

    <본문>.<서명>
    본문   {"sub": 7, "ver": 0, "exp": 1790000000}   base64
    서명   HMAC-SHA256(secret, 본문)                  base64

**비밀번호와 달리 여기는 HMAC 이 맞다.** 비밀번호는 느려야 하고(scrypt), 서명은 매 요청
검증하므로 빨라야 한다.

**`ver` 는 계정의 `users.token_version` 이다(ADR-092).** 비밀번호를 바꾸거나 카카오를 이으면
계정 쪽 값이 올라가고, 그 전에 나간 토큰은 `dependency.py` 가 401 로 막는다. 토큰마다 저장소를
두지 않고 계정 하나에 숫자 하나로 「그 전 것 전부」를 끊는다. 로그아웃은 여전히 브라우저가
토큰을 버리는 것이다. `ver` 가 없는 옛 토큰은 0 으로 읽는다 — 배포 순간 모두가 튕기지 않게.
"""

import base64
import hashlib
import hmac
import json
import time

# 교사가 하루를 일한다. 더 길면 잃어버린 토큰이 오래 살고, 짧으면 작업 중에 끊긴다.
TOKEN_TTL_SECONDS = 12 * 60 * 60


class TokenError(Exception):
    """서명이 틀렸거나 만료됐다. 왜인지는 응답에 싣지 않는다."""


def issue(user_id: int, secret: str, *, version: int = 0, now: int | None = None) -> str:
    now = now if now is not None else int(time.time())
    payload = {"sub": user_id, "ver": version, "exp": now + TOKEN_TTL_SECONDS}
    body = _b64(json.dumps(payload).encode())
    return f"{body}.{_sign(body, secret)}"


def read(token: str, secret: str, *, now: int | None = None) -> tuple[int, int]:
    """토큰이 가리키는 (user id, 토큰 버전). 못 믿으면 TokenError 다."""
    body, _, signature = token.partition(".")
    if not body or not signature:
        raise TokenError("모양이 토큰이 아니다")
    # 서명을 먼저 본다. 본문을 먼저 파싱하면 서명 없는 값으로 파서를 두드릴 수 있다.
    if not hmac.compare_digest(_sign(body, secret), signature):
        raise TokenError("서명이 맞지 않는다")
    try:
        payload = json.loads(_unb64(body))
        user_id, expires_at = int(payload["sub"]), int(payload["exp"])
        version = int(payload.get("ver", 0))
    except (ValueError, KeyError, TypeError, AttributeError) as error:
        raise TokenError("본문을 읽을 수 없다") from error
    if (now if now is not None else int(time.time())) >= expires_at:
        raise TokenError("만료됐다")
    return user_id, version


def _sign(body: str, secret: str) -> str:
    return _b64(hmac.new(secret.encode(), body.encode(), hashlib.sha256).digest())


def _b64(raw: bytes) -> str:
    # URL-safe 에 = 패딩을 뺀다. 헤더·쿼리 어디에 실려도 깨지지 않는다.
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))
