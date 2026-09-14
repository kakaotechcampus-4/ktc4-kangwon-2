"""Monthly Template 외부 JSON의 Input Schema.

Domain Model과 분리된 경계다. Domain은 Pydantic을 알지 못한다.

fail-fast 원칙 (OD-M01):
- 누락 필드를 조용한 기본값으로 보정하지 않는다.
- **`display_mode`를 추정하지 않는다.** 활성 CONTENT Section에 값이 없으면 실패다.
- PENDING Section을 임의로 활성화하지 않는다.
- unknown `display_mode` 문자열을 조용히 수용하지 않는다.
- approval을 우회하지 않는다.

**`runtime_active`를 독립적인 수동 switch로 신뢰하지 않는다.**
활성 여부는 `review.domain_owner_approval == HUMAN_APPROVED`에서 파생하며,
JSON의 `runtime_active` 값과 파생값이 다르면 **데이터 오류**로 처리한다.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, ValidationError

from ..planning.domain.monthly_template import (
    DisplayMode,
    EmptyValuePolicy,
    MonthlyTemplate,
    SectionRole,
    TemplateRef,
    TemplateSection,
)

__all__ = [
    "MonthlyTemplateSchemaError",
    "parse_monthly_template_payload",
]

HUMAN_APPROVED = "HUMAN_APPROVED"


def _non_blank(value: str) -> str:
    if not value.strip():
        raise ValueError("공백 문자열은 허용되지 않는다")
    return value


StrictBool = Annotated[bool, Field(strict=True)]
NonEmptyStr = Annotated[str, Field(strict=True), AfterValidator(_non_blank)]
Depth = Annotated[int, Field(ge=1, le=2, strict=True)]


class MonthlyTemplateSchemaError(ValueError):
    """Monthly Template JSON이 Input Schema를 위반한 경우."""


_STRICT = ConfigDict(extra="ignore", strict=False)


class _ReviewIn(BaseModel):
    model_config = _STRICT

    domain_owner_approval: NonEmptyStr
    runtime_active: StrictBool


class _StructureRulesIn(BaseModel):
    model_config = _STRICT

    hierarchy_max_depth: Annotated[int, Field(ge=1, le=2, strict=True)]
    default_empty_value_policy: Literal["RENDER_EMPTY_CELL"]
    global_display_mode_default: None = None
    """전역 기본값은 반드시 null이어야 한다(OD-M01). 값이 있으면 스키마 위반이다."""


class _SectionIn(BaseModel):
    model_config = _STRICT

    semantic_key: NonEmptyStr
    role: Literal["CONTENT", "AXIS"]
    activated: StrictBool
    depth: Depth
    display_mode: Literal["WEEKLY_CELLS", "MONTHLY_MERGED_SUMMARY"] | None = None
    empty_value_policy: Literal["RENDER_EMPTY_CELL"] | None = None
    parent_section: str | None = None
    source_label: str | None = None

    def to_domain(self) -> TemplateSection:
        return TemplateSection(
            section_key=self.semantic_key,
            role=SectionRole(self.role),
            activated=self.activated,
            display_mode=(
                DisplayMode(self.display_mode) if self.display_mode else None
            ),
            empty_value_policy=(
                EmptyValuePolicy(self.empty_value_policy)
                if self.empty_value_policy
                else None
            ),
            parent_section_key=self.parent_section,
            source_label=self.source_label,
            depth=self.depth,
        )


class _TemplateIn(BaseModel):
    model_config = _STRICT

    template_id: NonEmptyStr
    template_version: NonEmptyStr
    normative_status: NonEmptyStr
    review: _ReviewIn
    structure_rules: _StructureRulesIn
    sections: list[_SectionIn] = Field(min_length=1)


def parse_monthly_template_payload(
    payload: object, *, approval_override: str | None = None
) -> MonthlyTemplate:
    """원시 JSON을 검증하고 Domain `MonthlyTemplate`으로 변환한다.

    `approval_override`는 테스트가 승인 상태를 주입하기 위한 경로이며
    실제 파일을 수정하지 않는다. 운영 경로에서는 쓰지 않는다.
    """
    try:
        parsed = _TemplateIn.model_validate(payload)
    except ValidationError as exc:
        raise MonthlyTemplateSchemaError(
            f"Monthly Template JSON이 Input Schema를 위반한다: {exc}"
        ) from exc

    approval = approval_override or parsed.review.domain_owner_approval
    derived_active = approval == HUMAN_APPROVED

    if approval_override is None and parsed.review.runtime_active != derived_active:
        raise MonthlyTemplateSchemaError(
            "runtime_active가 승인 상태에서 파생된 값과 다르다. "
            f"domain_owner_approval={approval!r} -> 기대 {derived_active}, "
            f"파일 값 {parsed.review.runtime_active}. "
            "runtime_active는 독립 스위치가 아니며 수동 activation 우회를 허용하지 않는다."
        )

    for section in parsed.sections:
        if (
            section.activated
            and section.role == "CONTENT"
            and section.display_mode is None
        ):
            raise MonthlyTemplateSchemaError(
                f"활성 CONTENT Section에 display_mode가 없다: {section.semantic_key}. "
                "전역 기본값으로 추정하지 않는다."
            )

    try:
        return MonthlyTemplate(
            template_ref=TemplateRef(parsed.template_id, parsed.template_version),
            normative_status=parsed.normative_status,
            sections=tuple(s.to_domain() for s in parsed.sections),
            hierarchy_max_depth=parsed.structure_rules.hierarchy_max_depth,
            default_empty_value_policy=EmptyValuePolicy(
                parsed.structure_rules.default_empty_value_policy
            ),
            runtime_active=derived_active,
        )
    except ValueError as exc:
        raise MonthlyTemplateSchemaError(
            f"Monthly Template이 Domain 불변식을 위반한다: {exc}"
        ) from exc
