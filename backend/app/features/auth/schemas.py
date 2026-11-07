"""회원가입·로그인 요청·응답 (docs/api-spec.md §0)."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints

TeacherName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]
# 길이만 본다. 대소문자·특수문자를 강제하면 교사가 메모지에 적어 모니터에 붙인다.
Password = Annotated[str, Field(min_length=8, max_length=128)]


class SignupRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    name: TeacherName
    password: Password


class PasswordChangeRequest(BaseModel):
    """지금 비밀번호를 확인한 뒤에 바꾼다."""

    model_config = ConfigDict(extra="forbid")

    current_password: str
    new_password: Password


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: str


class MeResponse(BaseModel):
    """로그인한 교사. `center_id` 가 null 이면 온보딩을 아직 안 끝냈다."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    name: str
    center_id: int | None


class TokenResponse(BaseModel):
    """`token` 을 Authorization: Bearer <token> 으로 실어 보낸다."""

    token: str
    user: MeResponse


# 브라우저가 만든 무작위 값. 카카오가 그대로 돌려주고, 화면이 자기가 만든 값과 맞춰 본다(CSRF).
KakaoState = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_-]{16,128}$")]
# 카카오 인가 코드. 길이는 문서에 없다 — 실제 값은 80자 안팎이라 넉넉히 512 로 막는다.
KakaoCode = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=512)]


class KakaoAuthorizeResponse(BaseModel):
    """이 주소로 브라우저를 보낸다. 카카오 동의 화면이 뜬다."""

    url: str


class KakaoLoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: KakaoCode
