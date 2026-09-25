"""비밀번호 해싱. 표준 라이브러리만 쓴다.

`hashlib.scrypt` 는 파이썬이 들고 있는 정식 키 유도 함수다. 새 의존성을 붙이지 않고도
제대로 된 해싱이 된다 — sha256 한 번 돌리는 것과 다르다. GPU 로 몰아쳐도 느리게 만든다.

**직접 만든 방식을 쓰지 않는다.** 비밀번호는 「일단 되게」가 통하지 않는 영역이다.
"""

import hashlib
import hmac
import secrets

# OWASP 권장값 계열. n 을 올리면 느려지고 안전해진다 — 로그인이 체감으로 느려지면 낮춘다.
_N = 2**14
_R = 8
_P = 1
_SALT_BYTES = 16
_HASH_BYTES = 64


def hash_password(password: str) -> tuple[bytes, bytes]:
    """(해시, salt) 를 준다. salt 는 계정마다 새로 만든다."""
    salt = secrets.token_bytes(_SALT_BYTES)
    return _derive(password, salt), salt


def verify_password(password: str, expected: bytes, salt: bytes) -> bool:
    """맞는 비밀번호인가.

    `==` 로 비교하지 않는다. 앞에서 몇 글자가 맞았는지에 따라 걸리는 시간이 달라져
    한 글자씩 맞춰 나갈 수 있다(타이밍 공격). `compare_digest` 는 시간이 일정하다.
    """
    return hmac.compare_digest(_derive(password, salt), expected)


def _derive(password: str, salt: bytes) -> bytes:
    return hashlib.scrypt(password.encode("utf-8"), salt=salt, n=_N, r=_R, p=_P, dklen=_HASH_BYTES)
