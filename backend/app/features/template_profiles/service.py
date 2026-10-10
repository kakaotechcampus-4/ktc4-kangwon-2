"""다른 feature 가 TemplateProfile 을 쓰는 창구.

모델 · 저장소를 직접 엮지 않게 한다(structure.md).
"""

from sqlalchemy.orm import Session
from ssuksak.adapters.monthly_reference_repositories import JsonMonthlyTemplateRepository
from ssuksak.planning import TemplateProfileRef

from app.features.template_profiles.repository import (
    PostgresTemplateProfileRepository,
    TemplateProfileError,
    approved_template,
)

# 승인 상태는 데이터 파일이 말한다. 테스트만 OD-N11 (A) 객체로 바꿔 낀다.
TEMPLATES = JsonMonthlyTemplateRepository()


def ready_profile_for_generation(session: Session, center_id: int, ref: TemplateProfileRef):
    """생성에 쓸 정확한 READY 버전 (Contract 2 R5). 최신 버전을 대신 고르지 않는다.

    - 없다 · READY 가 아니다 · 남의 원 것이다 → `NOT_FOUND` (셋을 가르지 않는다)
    - 기반 Template 이 사람 승인 전이다 → `TEMPLATE_NOT_APPROVED` (결정 문서 12.8).
      READY 는 만들 때 이미 검사했지만 생성 직전에 한 번 더 본다 — 승인 우회 경로를 두지 않는다.
    """
    profile = PostgresTemplateProfileRepository(session, center_id=center_id).get_profile(
        ref.profile_id, ref.profile_version
    )
    if profile is None:
        raise TemplateProfileError("NOT_FOUND", f"{ref} 가 없다")
    try:
        approved_template(TEMPLATES, profile.base_template_ref)
    except TemplateProfileError as error:
        raise TemplateProfileError("TEMPLATE_NOT_APPROVED", str(error)) from error
    return profile
