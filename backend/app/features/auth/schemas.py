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
