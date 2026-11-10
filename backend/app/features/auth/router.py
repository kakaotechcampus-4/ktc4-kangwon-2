"""회원가입·로그인 (docs/api-spec.md §0).

**이 라우터만 인증 없이 열린다.** 나머지는 main.py 가 전부 막는다.
"""

import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_session
from app.features.auth import kakao
from app.features.auth.models import User
from app.features.auth.schemas import (
    KakaoAuthorizeResponse,
    KakaoLoginRequest,
    KakaoState,
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


@router.patch("/password", response_model=TokenResponse)
def change_password(
    body: PasswordChangeRequest, user: CurrentUser, session: DbSession
) -> TokenResponse:
    """비밀번호를 바꾸고, 이 브라우저에 쓸 새 토큰을 준다.

    **다른 곳에서 쓰던 비밀번호로 가입한 교사에게 바꿀 길이 있어야 한다.** 크롬은 자기가
    저장해 둔 비밀번호가 다른 주소의 입력 칸에 들어가면 그것을 피싱 신호로 보고 구글에
    알린다. 바꿀 자리가 없으면 그 교사는 계정을 새로 만드는 수밖에 없다.

    **바꾸기 전에 나간 토큰은 모두 끊는다(ADR-091).** 비밀번호가 샌 것 같아 바꾸는데 그 비밀번호로
    들어와 있던 사람이 12시간 더 머물면 바꾼 뜻이 없다. 바꾼 본인은 응답의 새 토큰으로 이어 간다.
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
    user.token_version += 1
    session.commit()
    session.refresh(user)
    return _token_for(user)


@router.get("/me", response_model=MeResponse)
def me(user: CurrentUser) -> User:
    """새로고침한 브라우저가 「나 아직 로그인돼 있나」를 묻는 자리다."""
    return user


_KAKAO_NOT_READY = {
    "code": "DEPENDENCY_UNAVAILABLE",
    "message": "지금은 카카오로 로그인할 수 없습니다. 이메일로 로그인해 주세요.",
    "fields": [],
}


@router.get("/kakao/authorize", response_model=KakaoAuthorizeResponse)
def kakao_authorize(state: Annotated[KakaoState, Query()]) -> KakaoAuthorizeResponse:
    """카카오 동의 화면 주소를 만든다.

    **REST API 키를 화면 번들에 넣지 않으려고 서버가 만든다**(`NEXT_PUBLIC_` 금지). 주소에 키가
    보이는 것은 카카오 방식이라 어쩔 수 없지만, 키를 바꿀 때 화면을 다시 빌드할 일은 없다.
    """
    try:
        return KakaoAuthorizeResponse(url=kakao.authorize_url(state))
    except kakao.KakaoNotConfigured:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=_KAKAO_NOT_READY) from None


@router.post("/kakao", response_model=TokenResponse)
def kakao_login(body: KakaoLoginRequest, session: DbSession) -> TokenResponse:
    """카카오 인가 코드로 로그인한다. 처음이면 계정을 만든다 (ADR-069).

    ```
    카카오 회원번호로 이어진 계정   → 그 계정
    없고, 같은 이메일 계정이 있다   → 그 계정에 회원번호를 잇고, 비밀번호 · 그 전 토큰을 끊는다
    둘 다 없다                    → 새 계정
    ```

    **이메일이 없으면 받지 않는다.** 화면의 계정 기록 · 반 설정이 모두 이메일을 열쇠로 쓴다.

    **이을 때 기존 비밀번호를 버린다(ADR-091).** 이메일 가입은 메일 주인인지 확인하지 않는다.
    남의 이메일로 먼저 가입해 둔 사람이 있으면, 카카오가 확인한 진짜 주인이 들어온 뒤에도 그
    비밀번호와 이미 받은 토큰으로 계속 들어온다. 어느 쪽이 먼저 가입한 사람인지 서버는 모르므로
    확인된 쪽(카카오)만 남긴다. 이은 뒤에는 카카오로만 들어온다.
    """
    try:
        profile = kakao.fetch_profile(body.code)
    except kakao.KakaoNotConfigured:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=_KAKAO_NOT_READY) from None
    except kakao.KakaoCodeRejected:
        # 401 이 아니다 — 401 은 「토큰을 못 믿겠다」라 화면이 로그인 만료로 읽는다.
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "VALIDATION_FAILED",
                "message": "카카오 로그인 시간이 지났습니다. 처음부터 다시 시도해 주세요.",
                "fields": ["code"],
            },
        ) from None
    except kakao.KakaoUnavailable:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=_KAKAO_NOT_READY) from None

    user = session.scalar(select(User).where(User.kakao_id == profile.kakao_id))
    if user is None:
        if profile.email is None:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "code": "VALIDATION_FAILED",
                    "message": "카카오 계정 이메일 제공에 동의해야 가입할 수 있습니다.",
                    "fields": ["email"],
                },
            )
        user = session.scalar(select(User).where(User.email == profile.email))
        if user is not None and user.kakao_id is not None:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail={
                    "code": "ALREADY_EXISTS",
                    "message": (
                        "이 이메일은 다른 카카오 계정에 연결돼 있습니다. 이메일로 로그인해 주세요."
                    ),
                    "fields": ["email"],
                },
            )
        if user is None:
            # 카카오로만 들어온 계정은 비밀번호를 모른다. 아무도 모르는 값을 넣어
            # 비밀번호 로그인을 막는다 — 칸을 nullable 로 바꾸면 검사하는 곳이 다 바뀐다.
            password_hash, salt = hash_password(secrets.token_urlsafe(32))
            user = User(
                email=profile.email,
                name=(profile.nickname or profile.email.split("@")[0])[:50],
                password_hash=password_hash,
                password_salt=salt,
            )
            session.add(user)
        else:
            # 이메일로 먼저 가입한 계정이다. 그 비밀번호를 누가 만들었는지 모른다(ADR-091).
            user.password_hash, user.password_salt = hash_password(secrets.token_urlsafe(32))
            user.token_version += 1
        user.kakao_id = profile.kakao_id
        session.commit()
        session.refresh(user)
    return _token_for(user)


def _token_for(user: User) -> TokenResponse:
    return TokenResponse(
        token=issue(user.id, settings.secret_key, version=user.token_version),
        user=MeResponse.model_validate(user),
    )
