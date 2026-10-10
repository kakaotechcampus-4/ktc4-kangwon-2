"""월간 양식 설정(TemplateProfile) API. 계약은 docs/api-spec.md §9-2(조회) · §9-4(관리)다.

조회 둘(D-M4-02)에 BE-1 관리 API 를 더한다 — 기반 Template 목록 · Reference 기반 시작 ·
원 기본 · 반 override 지정 / 해제. DRAFT 편집 · READY 전환 · 보관은 아직 없다.
**규칙은 M2 저장소의 것이다.** 여기서는 입력 모양을 보고 오류를 공개 코드로 옮길 뿐이다.
"""

from collections.abc import Callable
from datetime import datetime
from functools import partial
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from ssuksak.planning import InvalidDomainValueError, TemplateProfileRef
from ssuksak.planning.domain.monthly_template import SemanticVariant, TemplateRef
from ssuksak.planning.domain.monthly_template_profile import (
    DEFAULT_PROFILE_SECTION_KEYS,
    INSTITUTION_INPUT_SECTION_KEYS,
    OPTIONAL_PROFILE_SECTION_KEYS,
)

from app.db import get_session
from app.features.template_profiles import service
from app.features.template_profiles.repository import (
    _TEMPLATE_KEY,
    PostgresTemplateProfileRepository,
    TemplateProfileError,
)
from app.shared.auth.dependency import CurrentUser
from app.shared.auth.ownership import require_own_center, require_own_class

router = APIRouter(tags=["template-profiles"])

DbSession = Annotated[Session, Depends(get_session)]

# Template 의 칸 이름 → Profile 의 칸 이름 (M2 `_TEMPLATE_KEY` 의 반대 방향, habits → basic_habit).
_PROFILE_KEY = {template_key: profile_key for profile_key, template_key in _TEMPLATE_KEY.items()}
# 시작할 때 고를 수 있는 칸. 기관 입력 칸(event_schedule · drill)은 생성 계약이 아직 없어
# 뺀다(BE-1 결정 ③).
SELECTABLE_KEYS = OPTIONAL_PROFILE_SECTION_KEYS - INSTITUTION_INPUT_SECTION_KEYS
# Core: 켠 focus 는 NEUTRAL 을 쓸 수 없다(TemplateProfile._validate_sections).
FOCUS_VARIANTS = tuple(v.value for v in SemanticVariant if v is not SemanticVariant.NEUTRAL)


class ProfileRefIn(BaseModel):
    profile_id: str = Field(min_length=1)
    profile_version: str = Field(min_length=1)


class TemplateRefIn(BaseModel):
    template_id: str = Field(min_length=1)
    template_version: str = Field(min_length=1)


class ProfileRefOut(BaseModel):
    profile_id: str
    profile_version: str


class TemplateRefOut(BaseModel):
    template_id: str
    template_version: str


class ProfileSectionOut(BaseModel):
    section_key: str
    label: str | None
    repeat_by: str | None
    visible: bool


class ProfileOut(BaseModel):
    profile_ref: ProfileRefOut
    status: str
    base_template_ref: TemplateRefOut
    selected_optional_keys: list[str]
    sections: list[ProfileSectionOut]
    created_at: datetime


class ProfileListOut(BaseModel):
    items: list[ProfileOut]


class ResolutionOut(BaseModel):
    source: str
    profile_ref: ProfileRefOut | None
    reason: str | None


class TemplateSectionOut(BaseModel):
    section_key: str
    label: str | None
    role: str
    repeat_by: str | None
    selection: str


class TemplateOut(BaseModel):
    template_ref: TemplateRefOut
    approved: bool
    sections: list[TemplateSectionOut]
    focus_variants: list[str]


class TemplateListOut(BaseModel):
    items: list[TemplateOut]


class StartProfile(BaseModel):
    base_template_ref: TemplateRefIn
    selected_optional_keys: list[str] = Field(default_factory=list)
    display_labels: dict[str, str] = Field(default_factory=dict)
    focus_variant: str | None = None


class PointerIn(BaseModel):
    """두 칸 모두 보내야 한다(null 이라도). `expected_profile_ref` 는 화면이 본 현재 포인터다."""

    profile_ref: ProfileRefIn | None
    expected_profile_ref: ProfileRefIn | None


class PointerOut(BaseModel):
    profile_ref: ProfileRefOut | None
    changed_by: int | None
    changed_at: datetime | None


def _error(code: int, error_code: str, message: str, fields: list[str]) -> HTTPException:
    return HTTPException(code, detail={"code": error_code, "message": message, "fields": fields})


def _invalid(*fields: str) -> HTTPException:
    return _error(422, "VALIDATION_FAILED", "입력값을 확인해주세요.", list(fields))


_NOT_APPROVED = _error(
    409,
    "GATE_BLOCKED",
    "기반 Template 이 아직 사람 승인 전이라 쓸 수 없습니다.",
    ["base_template_ref"],
)
_TEMPLATE_NOT_FOUND = _error(
    404, "NOT_FOUND", "기반 Template 을 찾을 수 없습니다.", ["base_template_ref"]
)
# 없음 · READY 아님 · 남의 원 것을 가르지 않는다(ADR-017, §9-1 profile_ref 와 같다).
_PROFILE_NOT_FOUND = _error(404, "NOT_FOUND", "고른 양식 설정을 찾을 수 없습니다.", ["profile_ref"])
_STALE = _error(
    409,
    "STALE_WRITE",
    "그 사이 다른 화면에서 설정이 바뀌었습니다. 새로 불러온 뒤 다시 해주세요.",
    ["expected_profile_ref"],
)


def _ref_out(ref) -> ProfileRefOut | None:
    if ref is None:
        return None
    return ProfileRefOut(profile_id=ref.profile_id, profile_version=ref.profile_version)


def _profile_out(profile, created_at: datetime) -> ProfileOut:
    return ProfileOut(
        profile_ref=_ref_out(profile.profile_ref),
        status="READY",
        base_template_ref=TemplateRefOut(
            template_id=profile.base_template_ref.template_id,
            template_version=profile.base_template_ref.template_version,
        ),
        selected_optional_keys=list(profile.selected_optional_keys),
        sections=[
            ProfileSectionOut(
                section_key=section.section_key,
                label=section.display_label,
                repeat_by=None if section.repeat_by is None else section.repeat_by.value,
                visible=section.visible,
            )
            for section in profile.ordered_sections
        ],
        created_at=created_at,
    )


@router.get("/classes/{class_id}/template-profile", response_model=ResolutionOut)
def resolve_class_profile(class_id: int, session: DbSession, user: CurrentUser):
    """반 override → 원 기본 → 「선택 필요」. 대상을 못 쓰면 내려가지 않는다(R3)."""
    klass = require_own_class(session, user, class_id)
    resolution = PostgresTemplateProfileRepository(session, center_id=user.center_id).resolve(
        klass.id
    )
    return ResolutionOut(
        source=resolution.source,
        profile_ref=_ref_out(resolution.profile_ref),
        reason=resolution.reason,
    )


@router.get("/centers/{center_id}/template-profiles", response_model=ProfileListOut)
def list_ready_profiles(center_id: int, session: DbSession, user: CurrentUser):
    """원의 READY 버전 목록. DRAFT · ARCHIVED 는 생성에 못 쓰므로 주지 않는다."""
    require_own_center(user, center_id)
    versions = PostgresTemplateProfileRepository(session, center_id=center_id).ready_versions()
    return ProfileListOut(items=[_profile_out(p, created_at) for p, created_at in versions])


# ── BE-1 관리 API (§9-4) ──────────────────────────────────────────────────


def _selection(profile_key: str) -> str:
    if profile_key in DEFAULT_PROFILE_SECTION_KEYS:
        return "REQUIRED"
    if profile_key in INSTITUTION_INPUT_SECTION_KEYS:
        return "INSTITUTION_INPUT"
    if profile_key in OPTIONAL_PROFILE_SECTION_KEYS:
        return "OPTIONAL"
    return "NOT_SUPPORTED"


@router.get("/monthly-templates", response_model=TemplateListOut)
def list_monthly_templates():
    """고를 수 있는 기반 Template. **승인 대기도 `approved: false` 로 보인다** — 보인다고 쓸 수 있는
    것은 아니다. 승인 여부는 데이터 파일(`runtime_active`)이 말하고 여기서 바꾸지 않는다.
    """
    items = []
    for ref in service.MONTHLY_TEMPLATE_REFS:
        template = service.TEMPLATES.get_template(ref.template_id, ref.template_version)
        if template is None:
            raise RuntimeError(f"설정한 기반 Template {ref} 를 읽을 수 없다")
        items.append(
            TemplateOut(
                template_ref=TemplateRefOut(
                    template_id=ref.template_id, template_version=ref.template_version
                ),
                approved=template.is_active,
                sections=[
                    TemplateSectionOut(
                        section_key=key,
                        label=section.display_label,
                        role=section.role.value,
                        repeat_by=None if section.repeat_by is None else section.repeat_by.value,
                        selection=_selection(key),
                    )
                    for section in template.sections
                    for key in [_PROFILE_KEY.get(section.section_key, section.section_key)]
                ],
                focus_variants=list(FOCUS_VARIANTS),
            )
        )
    return TemplateListOut(items=items)


def _check_start(body: StartProfile) -> None:
    """저장소에 넘기기 전에 입력만 본다. Core 검증은 그대로 저장소 안에서 돈다."""
    keys = body.selected_optional_keys
    if len(set(keys)) != len(keys) or not set(keys) <= SELECTABLE_KEYS:
        raise _invalid("selected_optional_keys")
    chosen = DEFAULT_PROFILE_SECTION_KEYS | set(keys)
    for key, label in body.display_labels.items():
        if key not in chosen or not label.strip():
            raise _invalid("display_labels." + key)
    # Core: 보이는 칸은 표시 이름을 직접 받아야 한다 — 칸 이름(키)으로 대신하지 않는다.
    if missing := sorted(chosen - set(body.display_labels)):
        raise _invalid(*("display_labels." + key for key in missing))
    if "focus" in keys:
        if body.focus_variant not in FOCUS_VARIANTS:
            raise _invalid("focus_variant")
    elif body.focus_variant is not None:
        raise _invalid("focus_variant")


@router.post(
    "/centers/{center_id}/template-profiles",
    response_model=ProfileOut,
    status_code=status.HTTP_201_CREATED,
)
def start_profile(center_id: int, body: StartProfile, session: DbSession, user: CurrentUser):
    """「Reference 기반으로 시작」 → 원 소유 READY v1. 원 기본은 걸지 않는다(C2.6 — 동의할 때 따로).

    요청마다 새 Profile 이다 — 같은 요청을 두 번 보내면 두 개가 생긴다(Idempotency-Key 없음).
    실패하면 commit 하지 않으므로 아무것도 남지 않는다.
    """
    require_own_center(user, center_id)
    _check_start(body)
    try:
        template_ref = TemplateRef(
            body.base_template_ref.template_id, body.base_template_ref.template_version
        )
    except InvalidDomainValueError as error:
        raise _invalid("base_template_ref") from error
    repo = PostgresTemplateProfileRepository(session, center_id=center_id)
    try:
        ref = repo.start_from_reference(
            service.TEMPLATES,
            template_ref,
            selected_optional_keys=tuple(body.selected_optional_keys),
            display_labels=body.display_labels,
            focus_variant=None
            if body.focus_variant is None
            else SemanticVariant(body.focus_variant),
            actor_id=user.id,
        )
    except TemplateProfileError as error:
        if error.code == "TEMPLATE_NOT_APPROVED":
            raise _NOT_APPROVED from error
        if error.code == "NOT_FOUND":
            raise _TEMPLATE_NOT_FOUND from error
        if error.code == "INVALID":  # issue 경로는 내부 이름이라 fields 로 내보내지 않는다
            raise _invalid() from error
        raise
    except InvalidDomainValueError as error:  # Core 가 칸 · Profile 을 만들다 거절했다
        raise _invalid() from error
    profile, created_at = next(
        (profile, created_at)
        for profile, created_at in repo.ready_versions()
        if profile.profile_ref == ref
    )
    detail = _profile_out(profile, created_at)
    session.commit()
    return detail


def _pointer_out(row) -> PointerOut:
    if row is None:
        return PointerOut(profile_ref=None, changed_by=None, changed_at=None)
    return PointerOut(
        profile_ref=ProfileRefOut(profile_id=row.profile_id, profile_version=row.profile_version),
        changed_by=row.changed_by,
        changed_at=row.changed_at,
    )


def _domain_ref(ref: ProfileRefIn | None, field: str) -> TemplateProfileRef | None:
    if ref is None:
        return None
    try:
        return TemplateProfileRef(ref.profile_id, ref.profile_version)
    except InvalidDomainValueError as error:
        raise _invalid(field) from error


def _move(body: PointerIn, assign: Callable, clear: Callable, actor_id: int) -> None:
    """지정은 `profile_ref`, 해제는 `profile_ref: null`. 둘 다 본 값(`expected`)이 맞을 때만
    쓴다."""
    target = _domain_ref(body.profile_ref, "profile_ref")
    expected = _domain_ref(body.expected_profile_ref, "expected_profile_ref")
    try:
        if target is not None:
            assign(target, expected=expected, actor_id=actor_id)
        elif expected is None:  # 「무엇을 지우는지」 모르는 해제는 받지 않는다
            raise _invalid("expected_profile_ref")
        else:
            clear(expected=expected)
    except TemplateProfileError as error:
        if error.code == "CONFLICT":
            raise _STALE from error
        if error.code in {"NOT_FOUND", "NOT_READY", "CLASSROOM_SCOPED"}:
            raise _PROFILE_NOT_FOUND from error
        raise


@router.get("/centers/{center_id}/template-profile-default", response_model=PointerOut)
def get_center_default(center_id: int, session: DbSession, user: CurrentUser):
    """원 기본 포인터 그대로. 이 반에 실제로 무엇이 쓰이는지는 §9-2 해석 API 가 준다."""
    require_own_center(user, center_id)
    return _pointer_out(
        PostgresTemplateProfileRepository(session, center_id=center_id).get_default()
    )


@router.put("/centers/{center_id}/template-profile-default", response_model=PointerOut)
def put_center_default(center_id: int, body: PointerIn, session: DbSession, user: CurrentUser):
    require_own_center(user, center_id)
    repo = PostgresTemplateProfileRepository(session, center_id=center_id)
    _move(body, repo.set_default, repo.clear_default, user.id)
    detail = _pointer_out(repo.get_default())
    session.commit()
    return detail


@router.get("/classes/{class_id}/template-profile-override", response_model=PointerOut)
def get_class_override(class_id: int, session: DbSession, user: CurrentUser):
    """반 override 포인터 그대로. 대상을 못 쓰게 됐어도(R3) 보인다 — 해제하려면 이 값이 필요하다."""
    klass = require_own_class(session, user, class_id)
    repo = PostgresTemplateProfileRepository(session, center_id=user.center_id)
    return _pointer_out(repo.get_override(klass.id))


@router.put("/classes/{class_id}/template-profile-override", response_model=PointerOut)
def put_class_override(class_id: int, body: PointerIn, session: DbSession, user: CurrentUser):
    klass = require_own_class(session, user, class_id)
    repo = PostgresTemplateProfileRepository(session, center_id=user.center_id)
    _move(
        body,
        partial(repo.set_override, klass.id),
        partial(repo.clear_override, klass.id),
        user.id,
    )
    detail = _pointer_out(repo.get_override(klass.id))
    session.commit()
    return detail
