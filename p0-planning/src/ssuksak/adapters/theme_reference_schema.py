"""Theme Reference 외부 JSON의 Input Schema.

**Domain Model과 분리된 경계다.** 이 모듈은 파일에서 들어오는 원시 JSON을
엄격하게 검증하고, 통과한 것만 domain의 `ThemeCandidate` / `ThemeCatalog`로
변환한다. Domain은 Pydantic을 알지 못한다.

fail-fast 원칙 (CLAUDE.md §7·§8):
- 최소 필수 필드가 없으면 조용히 기본값으로 보정하지 않고 즉시 실패한다.
- 특히 `themes[].source_version`이 없을 때 `catalog_version`을 자동 대입하지 않는다.
  Evidence의 `source_version`은 Provenance 재현성의 근거이므로 추측하면 안 된다.
- `evidence`도 필수로 둔다. 선택 Rule이 `observed_month` 기반 강도를 쓰기 때문에
  누락되면 모든 후보의 강도가 0이 되어 선택 근거가 조용히 사라진다.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, ValidationError

from ..planning.domain.theme_reference import (
    ActivationStatus,
    CurriculumLink,
    ThemeCandidate,
    ThemeCatalog,
    ThemeEvidence,
)

__all__ = [
    "ThemeReferenceSchemaError",
    "parse_theme_reference_payload",
]


def _non_blank(value: str) -> str:
    """공백만 있는 문자열을 거부한다. 값 자체는 변형하지 않는다.

    `min_length=1`만으로는 `"   "`가 통과하므로 별도 검사가 필요하다.
    strip한 값을 대신 넣지 않는 이유는 조용한 보정을 피하기 위함이다.
    """
    if not value.strip():
        raise ValueError("공백 문자열은 허용되지 않는다")
    return value


# `strict=True`는 `"9"` → `9` 같은 조용한 타입 강제 변환을 막는다.
CalendarMonth = Annotated[int, Field(ge=1, le=12, strict=True)]
AgeYear = Annotated[int, Field(ge=0, le=7, strict=True)]
NonNegativeInt = Annotated[int, Field(ge=0, strict=True)]
StrictStr = Annotated[str, Field(strict=True)]
NonEmptyStr = Annotated[str, Field(strict=True), AfterValidator(_non_blank)]
StrictBool = Annotated[bool, Field(strict=True)]


class ThemeReferenceSchemaError(ValueError):
    """Theme Reference JSON이 Input Schema를 위반한 경우."""


_STRICT = ConfigDict(extra="ignore", strict=False)


class _AgeConditionsIn(BaseModel):
    model_config = _STRICT

    supported_ages: list[AgeYear] = Field(min_length=1)
    allow_mixed_age: StrictBool
    mixed_age_requires_all_supported: StrictBool


class _CurriculumLinkIn(BaseModel):
    model_config = _STRICT

    source_id: NonEmptyStr
    domain: NonEmptyStr
    source_page: NonNegativeInt
    relation: NonEmptyStr


class _EvidenceIn(BaseModel):
    model_config = _STRICT

    origin_id: NonEmptyStr
    page: NonNegativeInt
    age_scope: list[AgeYear]
    observed_month: CalendarMonth
    observed_label: StrictStr


class _ThemeIn(BaseModel):
    """Theme 후보 하나의 필수 필드.

    기본값을 두지 않는다. 누락은 곧 실패다.
    """

    model_config = _STRICT

    theme_id: NonEmptyStr
    label: NonEmptyStr
    applicable_months: list[CalendarMonth] = Field(min_length=1)
    age_conditions: _AgeConditionsIn
    curriculum_links: list[_CurriculumLinkIn]
    origin_id: NonEmptyStr
    source_version: NonEmptyStr
    evidence: list[_EvidenceIn] = Field(min_length=1)


class _ReviewIn(BaseModel):
    model_config = _STRICT

    domain_owner_approval: NonEmptyStr
    approved_by: StrictStr | None = None
    approved_at: StrictStr | None = None


class _CatalogIn(BaseModel):
    model_config = _STRICT

    catalog_id: NonEmptyStr
    catalog_version: NonEmptyStr
    review: _ReviewIn
    themes: list[_ThemeIn] = Field(min_length=1)
    normative_status: StrictStr | None = None


def _activation_from(review: _ReviewIn) -> ActivationStatus:
    """알 수 없는 승인 문자열을 활성으로 해석하지 않는다."""
    raw = review.domain_owner_approval.strip().upper()
    if raw == ActivationStatus.HUMAN_APPROVED.value:
        return ActivationStatus.HUMAN_APPROVED
    return ActivationStatus.PENDING_HUMAN_REVIEW


def parse_theme_reference_payload(
    payload: object, *, activation_override: ActivationStatus | None = None
) -> ThemeCatalog:
    """원시 JSON payload를 검증하고 domain ThemeCatalog로 변환한다.

    Raises:
        ThemeReferenceSchemaError: 필수 필드 누락 또는 타입 위반.
    """
    try:
        parsed = _CatalogIn.model_validate(payload)
    except ValidationError as exc:
        raise ThemeReferenceSchemaError(
            f"Theme Reference Input Schema 위반: {exc}"
        ) from exc

    themes: list[ThemeCandidate] = []
    for theme in parsed.themes:
        # source_version은 자동 대입하지 않는다. 위 Schema가 필수로 강제했다.
        themes.append(
            ThemeCandidate(
                theme_id=theme.theme_id,
                label=theme.label,
                applicable_months=tuple(theme.applicable_months),
                supported_ages=tuple(theme.age_conditions.supported_ages),
                allow_mixed_age=theme.age_conditions.allow_mixed_age,
                mixed_age_requires_all_supported=(
                    theme.age_conditions.mixed_age_requires_all_supported
                ),
                source_version=theme.source_version,
                origin_id=theme.origin_id,
                curriculum_links=tuple(
                    CurriculumLink(
                        source_id=link.source_id,
                        domain=link.domain,
                        source_page=link.source_page,
                        relation=link.relation,
                    )
                    for link in theme.curriculum_links
                ),
                evidence=tuple(
                    ThemeEvidence(
                        origin_id=ev.origin_id,
                        page=ev.page,
                        age_scope=tuple(ev.age_scope),
                        observed_month=ev.observed_month,
                        observed_label=ev.observed_label,
                    )
                    for ev in theme.evidence
                ),
            )
        )

    activation = activation_override or _activation_from(parsed.review)

    try:
        return ThemeCatalog(
            catalog_id=parsed.catalog_id,
            catalog_version=parsed.catalog_version,
            activation_status=activation,
            themes=tuple(themes),
            normative_status=parsed.normative_status,
        )
    except ValueError as exc:
        # 중복 theme_id 등 domain 불변식 위반
        raise ThemeReferenceSchemaError(str(exc)) from exc
