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
    PasswordChangeRequest,
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


@router.patch("/password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(body: PasswordChangeRequest, user: CurrentUser, session: DbSession) -> None:
    """비밀번호를 바꾼다.

    **다른 곳에서 쓰던 비밀번호로 가입한 교사에게 바꿀 길이 있어야 한다.** 크롬은 자기가
    저장해 둔 비밀번호가 다른 주소의 입력 칸에 들어가면 그것을 피싱 신호로 보고 구글에
    알린다. 바꿀 자리가 없으면 그 교사는 계정을 새로 만드는 수밖에 없다.
    """
    if not verify_password(body.current_password, user.password_hash, user.password_salt):
        # 401 이 아니라 422 다. 401 은 「토큰을 못 믿겠다」는 뜻으로 이미 쓰고 있어서,
        # 화면이 이것을 로그인 만료로 읽고 교사를 로그인 화면으로 내보낸다.
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "VALIDATION_FAILED",
                "message": "지금 비밀번호가 올바르지 않습니다.",
                "fields": ["current_password"],
            },
        )
    if verify_password(body.new_password, user.password_hash, user.password_salt):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "VALIDATION_FAILED",
                "message": "지금 쓰는 비밀번호와 같습니다. 다른 비밀번호를 적어 주세요.",
                "fields": ["new_password"],
            },
        )
    user.password_hash, user.password_salt = hash_password(body.new_password)
    session.commit()


@router.get("/me", response_model=MeResponse)
def me(user: CurrentUser) -> User:
    """새로고침한 브라우저가 「나 아직 로그인돼 있나」를 묻는 자리다."""
    return user


def _token_for(user: User) -> TokenResponse:
    return TokenResponse(
        token=issue(user.id, settings.secret_key), user=MeResponse.model_validate(user)
    )
