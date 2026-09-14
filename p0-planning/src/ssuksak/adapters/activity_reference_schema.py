"""Activity Reference JSON의 엄격 검증.

`theme_reference_schema.py`와 같은 원칙이다.

금지:
- 누락 필드를 기본값으로 보정
- 알 수 없는 필드를 조용히 무시
- 잘못된 item을 skip하고 계속 진행
- caller가 승인 상태를 덮어쓰기
- `latest` version 자동 탐색

`activation_status`는 `review.domain_owner_approval`에서만 읽는다. 외부 요청자가
지정할 수 없고 JSON에 `runtime_active` 필드를 두지 않는다. 파일에 그 필드가
있으면 거부한다 — activation을 독립 writable 값으로 만드는 경로를 없앤다.

**승인 우회 입력이 없다.** `activation_override` / `approval_override` /
`force_active` 같은 파라미터를 두지 않는다. 테스트 편의를 위해 Production
Approval Gate를 우회하는 API를 만들지 않는다.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from ..planning.domain.activity_reference import (
    ActivityDisplayQuality,
    DisplayQualityReviewStatus,
    ActivationStatus,
    ActivityCandidate,
    ActivityCatalog,
    ActivityEvidence,
    ActivitySetting,
    ActivityThemeLink,
    CurriculumLink,
)

__all__ = [
    "ActivityReferenceSchemaError",
    "parse_activity_reference_payload",
]

_EXPECTED_SCHEMA_VERSION = "activity-reference.schema.v0"

_FORBIDDEN_TOP_LEVEL_KEYS = {
    "runtime_active": (
        "runtime_active를 파일에 둘 수 없다. activation은 "
        "review.domain_owner_approval에서 파생되는 값이며 독립 writable 필드가 "
        "아니다"
    ),
    "activation_status": (
        "activation_status를 파일에 직접 둘 수 없다. "
        "review.domain_owner_approval에서만 읽는다"
    ),
}

_FORBIDDEN_ACTIVITY_KEYS = {
    "safety_flags": (
        "safety_flags를 Activity에 둘 수 없다. 법정 안전교육과 혼동되는 필드를 "
        "만들지 않는다"
    ),
    "activity_area": (
        "activity_area는 OD-N03에서 아직 OPEN이다. 제어 어휘가 확정되기 전에 "
        "값을 넣을 수 없다"
    ),
    "tags": "tags는 OD-N03에서 아직 OPEN이다",
    "runtime_active": "Activity 항목에 runtime_active를 둘 수 없다",
}


class ActivityReferenceSchemaError(Exception):
    """Activity Reference 원시 데이터가 Contract를 만족하지 않는다."""


class _Review(BaseModel):
    model_config = ConfigDict(extra="allow")

    domain_owner_approval: str

    @field_validator("domain_owner_approval")
    @classmethod
    def _known_approval(cls, v: str) -> str:
        allowed = {s.value for s in ActivationStatus}
        if v not in allowed:
            raise ValueError(
                f"알 수 없는 domain_owner_approval '{v}'. 허용: {sorted(allowed)}"
            )
        return v


class _Coverage(BaseModel):
    model_config = ConfigDict(extra="allow")

    month_coverage: list[int]

    @field_validator("month_coverage")
    @classmethod
    def _valid_months(cls, v: list[int]) -> list[int]:
        for m in v:
            if not 1 <= m <= 12:
                raise ValueError(f"month_coverage는 1~12여야 한다: {v}")
        if len(set(v)) != len(v):
            raise ValueError(f"month_coverage에 중복이 있다: {v}")
        return v


class _Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    origin_id: str
    page: int
    age_scope: list[int]
    observed_month: int
    observed_label: str
    observed_section: str
    observed_source_label: str
    matched_via: str | None = None
    match_note: str | None = None

    @field_validator("matched_via")
    @classmethod
    def _known_matched_via(cls, v: str | None) -> str | None:
        if v is not None and v not in ("DIRECT_EXPRESSION", "RELATED_EXPRESSION"):
            raise ValueError(f"알 수 없는 matched_via '{v}'")
        return v


class _ThemeLink(BaseModel):
    model_config = ConfigDict(extra="forbid")

    theme_id: str
    relation: str
    theme_catalog_version: str


class _CurriculumLink(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str
    domain: str
    source_page: int
    relation: str = "EDUCATIONAL_ALIGNMENT"


class _Activity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    activity_id: str
    label: str
    supported_ages: list[int]
    allow_mixed_age: bool
    mixed_age_requires_all_supported: bool
    applicable_months: list[int]
    placement_slots: list[str]
    setting: str
    source_version: str
    origin_id: str | None = None
    label_derivation_type: str | None = None
    label_derivation: str | None = None
    aliases: list[str] = Field(default_factory=list)
    theme_links: list[_ThemeLink] = Field(default_factory=list)
    curriculum_links: list[_CurriculumLink] = Field(default_factory=list)
    evidence: list[_Evidence] = Field(default_factory=list)
    display_quality: str | None = None
    display_quality_review_status: str | None = None

    @field_validator("display_quality")
    @classmethod
    def _known_display_quality(cls, v: str | None) -> str | None:
        if v is None:
            return None
        allowed = {q.value for q in ActivityDisplayQuality}
        if v not in allowed:
            raise ValueError(
                f"알 수 없는 display_quality '{v}'. 허용: {sorted(allowed)}"
            )
        return v

    @field_validator("display_quality_review_status")
    @classmethod
    def _known_review_status(cls, v: str | None) -> str | None:
        if v is None:
            return None
        allowed = {s.value for s in DisplayQualityReviewStatus}
        if v not in allowed:
            raise ValueError(
                f"알 수 없는 display_quality_review_status '{v}'. 허용: {sorted(allowed)}"
            )
        return v

    @field_validator("setting")
    @classmethod
    def _known_setting(cls, v: str) -> str:
        allowed = {s.value for s in ActivitySetting}
        if v not in allowed:
            raise ValueError(f"알 수 없는 setting '{v}'. 허용: {sorted(allowed)}")
        return v

    @field_validator("label_derivation_type")
    @classmethod
    def _known_derivation(cls, v: str | None) -> str | None:
        if v is not None and v not in ("DIRECT_TRANSCRIPTION", "NORMALIZED"):
            raise ValueError(f"알 수 없는 label_derivation_type '{v}'")
        return v


class _Catalog(BaseModel):
    model_config = ConfigDict(extra="allow")

    schema_version: str
    catalog_id: str
    catalog_version: str
    normative_status: str | None = None
    review: _Review
    coverage: _Coverage
    origins: list[dict[str, Any]]
    activities: list[_Activity]

    @field_validator("schema_version")
    @classmethod
    def _expected_schema(cls, v: str) -> str:
        if v != _EXPECTED_SCHEMA_VERSION:
            raise ValueError(
                f"schema_version이 '{_EXPECTED_SCHEMA_VERSION}'이 아니다: '{v}'"
            )
        return v

    @field_validator("activities")
    @classmethod
    def _non_empty(cls, v: list[_Activity]) -> list[_Activity]:
        if not v:
            raise ValueError("activities가 비어 있다")
        return v


def _reject_forbidden(payload: dict[str, Any]) -> None:
    for key, reason in _FORBIDDEN_TOP_LEVEL_KEYS.items():
        if key in payload:
            raise ActivityReferenceSchemaError(reason)
    for raw in payload.get("activities") or []:
        if not isinstance(raw, dict):
            continue
        for key, reason in _FORBIDDEN_ACTIVITY_KEYS.items():
            if key in raw:
                aid = raw.get("activity_id", "<unknown>")
                raise ActivityReferenceSchemaError(f"{aid}: {reason}")


def _require_declared_origins(model: _Catalog) -> None:
    """evidence와 activity의 origin_id가 origins[]에 선언돼 있어야 한다."""
    declared = set()
    for raw in model.origins:
        oid = raw.get("origin_id")
        if not oid or not isinstance(oid, str):
            raise ActivityReferenceSchemaError("origins[]의 각 항목은 origin_id를 가져야 한다")
        if oid in declared:
            raise ActivityReferenceSchemaError(f"origins[]에 중복된 origin_id: {oid}")
        declared.add(oid)

    for activity in model.activities:
        if activity.origin_id is not None and activity.origin_id not in declared:
            raise ActivityReferenceSchemaError(
                f"{activity.activity_id}: 선언되지 않은 origin_id "
                f"'{activity.origin_id}'"
            )
        for e in activity.evidence:
            if e.origin_id not in declared:
                raise ActivityReferenceSchemaError(
                    f"{activity.activity_id}: evidence가 선언되지 않은 origin_id "
                    f"'{e.origin_id}'를 참조한다"
                )


def parse_activity_reference_payload(payload: object) -> ActivityCatalog:
    """원시 payload를 검증하고 domain ActivityCatalog로 변환한다.

    승인 상태는 **오직** `review.domain_owner_approval`에서 파생된다. 승인을
    우회하는 입력을 받지 않는다. 테스트가 승인 상태 동작을 검증하려면
    HUMAN_APPROVED인 JSON fixture를 별도로 만들거나 Domain 객체를 직접 구성한다.

    Raises:
        ActivityReferenceSchemaError: 형식이나 Contract 위반.
    """
    if not isinstance(payload, dict):
        raise ActivityReferenceSchemaError(
            f"Activity Reference payload는 object여야 한다: {type(payload).__name__}"
        )

    _reject_forbidden(payload)

    try:
        model = _Catalog.model_validate(payload)
    except ValidationError as exc:
        raise ActivityReferenceSchemaError(
            f"Activity Reference 형식 검증 실패: {exc}"
        ) from exc

    _require_declared_origins(model)

    status = ActivationStatus(model.review.domain_owner_approval)

    try:
        activities = tuple(
            ActivityCandidate(
                activity_id=a.activity_id,
                label=a.label,
                supported_ages=tuple(a.supported_ages),
                allow_mixed_age=a.allow_mixed_age,
                mixed_age_requires_all_supported=a.mixed_age_requires_all_supported,
                applicable_months=tuple(a.applicable_months),
                placement_slots=tuple(a.placement_slots),
                setting=ActivitySetting(a.setting),
                source_version=a.source_version,
                origin_id=a.origin_id,
                label_derivation_type=a.label_derivation_type,
                label_derivation=a.label_derivation,
                aliases=tuple(a.aliases),
                display_quality=(
                    None
                    if a.display_quality is None
                    else ActivityDisplayQuality(a.display_quality)
                ),
                display_quality_review_status=(
                    None
                    if a.display_quality_review_status is None
                    else DisplayQualityReviewStatus(a.display_quality_review_status)
                ),
                theme_links=tuple(
                    ActivityThemeLink(
                        theme_id=link.theme_id,
                        relation=link.relation,
                        theme_catalog_version=link.theme_catalog_version,
                    )
                    for link in a.theme_links
                ),
                curriculum_links=tuple(
                    CurriculumLink(
                        source_id=link.source_id,
                        domain=link.domain,
                        source_page=link.source_page,
                        relation=link.relation,
                    )
                    for link in a.curriculum_links
                ),
                evidence=tuple(
                    ActivityEvidence(
                        origin_id=e.origin_id,
                        page=e.page,
                        age_scope=tuple(e.age_scope),
                        observed_month=e.observed_month,
                        observed_label=e.observed_label,
                        observed_section=e.observed_section,
                        observed_source_label=e.observed_source_label,
                        matched_via=e.matched_via,
                        match_note=e.match_note,
                    )
                    for e in a.evidence
                ),
            )
            for a in model.activities
        )
        return ActivityCatalog(
            catalog_id=model.catalog_id,
            catalog_version=model.catalog_version,
            activation_status=status,
            activities=activities,
            normative_status=model.normative_status,
            month_coverage=tuple(model.coverage.month_coverage),
        )
    except ValueError as exc:
        # Domain 불변식 위반도 schema 오류로 올린다. 부분 로드를 허용하지 않는다.
        raise ActivityReferenceSchemaError(f"Activity Reference Contract 위반: {exc}") from exc
