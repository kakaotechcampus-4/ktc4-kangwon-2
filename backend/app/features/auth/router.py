"""회원가입·로그인 (docs/api-spec.md §0).

**이 라우터만 인증 없이 열린다.** 나머지는 main.py 가 전부 막는다.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_session
from app.features.auth.models import User
from app.features.auth.schemas import (
    LoginRequest,
    MeResponse,
    SignupRequest,
    TokenResponse,
)
from app.shared.auth.dependency import CurrentUser
from app.shared.auth.passwords import hash_password, verify_password
from app.shared.auth.tokens import issue

router = APIRouter(prefix="/auth", tags=["auth"])

DbSession = Annotated[Session, Depends(get_session)]

_BAD_CREDENTIALS = {
    "code": "UNAUTHENTICATED",
    "message": "이메일 또는 비밀번호가 올바르지 않습니다.",
    "fields": [],
}


@router.post("/signup", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def signup(body: SignupRequest, session: DbSession) -> TokenResponse:
    """교사 계정을 만들고 바로 로그인시킨다.

    가입 직후 온보딩으로 넘어가므로 토큰을 여기서 준다. 다시 로그인하게 만들면
    교사가 같은 비밀번호를 두 번 친다.
    """
    if session.scalar(select(User).where(User.email == body.email)) is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={
                "code": "ALREADY_EXISTS",
                "message": "이미 가입된 이메일입니다.",
                "fields": ["email"],
            },
        )
    password_hash, salt = hash_password(body.password)
    user = User(
        email=body.email,
        name=body.name,
        password_hash=password_hash,
        password_salt=salt,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return _token_for(user)


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, session: DbSession) -> TokenResponse:
    """**없는 이메일과 틀린 비밀번호를 같은 응답으로 돌려준다.**

    나누면 어느 이메일이 가입돼 있는지 확인하는 수단이 된다.
    """
    user = session.scalar(select(User).where(User.email == body.email))
    if user is None or not verify_password(body.password, user.password_hash, user.password_salt):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=_BAD_CREDENTIALS)
    return _token_for(user)


@router.get("/me", response_model=MeResponse)
def me(user: CurrentUser) -> User:
    """새로고침한 브라우저가 「나 아직 로그인돼 있나」를 묻는 자리다."""
    return user


def _token_for(user: User) -> TokenResponse:
    return TokenResponse(
        token=issue(user.id, settings.secret_key), user=MeResponse.model_validate(user)
    )
