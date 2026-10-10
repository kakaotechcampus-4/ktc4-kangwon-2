"""월간 양식 설정(TemplateProfile) 조회 API. 계약은 docs/api-spec.md §9-2 다.

**조회 둘뿐이다**(D-M4-02). 만들기 · 편집 · READY 전환 · 보관 · 포인터 변경은 별도 후속 작업이다.
"""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db import get_session
from app.features.template_profiles.repository import PostgresTemplateProfileRepository
from app.shared.auth.dependency import CurrentUser
from app.shared.auth.ownership import require_own_center, require_own_class

router = APIRouter(tags=["template-profiles"])

DbSession = Annotated[Session, Depends(get_session)]


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


def _ref_out(ref) -> ProfileRefOut | None:
    if ref is None:
        return None
    return ProfileRefOut(profile_id=ref.profile_id, profile_version=ref.profile_version)


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
    return ProfileListOut(
        items=[
            ProfileOut(
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
            for profile, created_at in versions
        ]
    )
