"""로그인 확인 (docs/api-spec.md 「인증」).

**라우터마다 붙이지 않는다.** `main.py` 가 라우터 전체에 한 번 건다 — 엔드포인트가
늘어도 자동으로 걸린다. 하나씩 붙이면 반드시 빠뜨린다.
"""

from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_session
from app.features.auth.models import User
from app.shared.auth.tokens import TokenError, read

_UNAUTHENTICATED = {
    "code": "UNAUTHENTICATED",
    "message": "로그인이 필요합니다.",
    "fields": [],
}


def current_user(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
) -> User:
    """토큰이 가리키는 교사. 없거나 못 믿으면 401 이다.

    **왜 401 인지는 응답에 싣지 않는다.** 「만료됐다」와 「서명이 틀렸다」를 구분해 주면
    토큰을 맞춰 보는 쪽에 힌트가 된다.
    """
    header = request.headers.get("Authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=_UNAUTHENTICATED)
    try:
        user_id = read(token.strip(), settings.secret_key)
    except TokenError as error:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=_UNAUTHENTICATED) from error

    user = session.get(User, user_id)
    if user is None:
        # 토큰은 멀쩡한데 계정이 지워진 경우다. 서명이 맞아도 통과시키지 않는다.
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=_UNAUTHENTICATED)
    return user


CurrentUser = Annotated[User, Depends(current_user)]
