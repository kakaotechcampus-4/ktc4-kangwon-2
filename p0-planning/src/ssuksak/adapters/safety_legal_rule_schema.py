"""법정 안전교육 Rule 외부 JSON의 Input Schema.

fail-fast 원칙 (OD-M04):
- `normative_status`는 `STATUTORY`여야 한다.
- 법정 구분은 **정확히 6개**여야 한다(별표6 2022. 6. 21. 개정).
- 실시 간격·연간 최소 시간·적용 대상이 없으면 실패다.
- **category에 월 배정 필드가 생기면 정책 위반으로 차단**한다.
- **`placement_policy_version`이 P0에서 값을 가지면 정책 위반으로 차단**한다.
- 승인 상태에서 파생한 활성 여부와 파일의 `runtime_active`가 다르면 데이터 오류다.

비법정 기관 label을 official category로 추가하거나 매핑하지 않는다.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, ValidationError

from ..planning.domain.safety_legal_rule import (
    LEGAL_CATEGORY_COUNT,
    SafetyCategory,
    SafetyLegalRule,
)

__all__ = [
    "SafetyLegalRuleSchemaError",
    "parse_safety_legal_rule_payload",
]

HUMAN_APPROVED = "HUMAN_APPROVED"

NON_LEGAL_LABELS = ("생활안전", "심폐소생술", "장애인식 개선", "소방안전", "비상대응")
"""별표6 6구분이 아닌 기관 label. category로 들어오면 차단한다."""

FORBIDDEN_CATEGORY_KEYS = (
    "month",
    "months",
    "month_assignment",
    "assigned_month",
    "placement",
    "week",
)
"""법령 데이터에 있어서는 안 되는 배치성 필드. `interval_months`는 예외다."""


def _non_blank(value: str) -> str:
    if not value.strip():
        raise ValueError("공백 문자열은 허용되지 않는다")
    return value


StrictBool = Annotated[bool, Field(strict=True)]
NonEmptyStr = Annotated[str, Field(strict=True), AfterValidator(_non_blank)]
PositiveInt = Annotated[int, Field(ge=1, strict=True)]


class SafetyLegalRuleSchemaError(ValueError):
    """법정 Safety Rule JSON이 Input Schema를 위반한 경우."""


_STRICT = ConfigDict(extra="ignore", strict=False)


class _ReviewIn(BaseModel):
    model_config = _STRICT

    domain_owner_approval: NonEmptyStr
    runtime_active: StrictBool


class _ScopeIn(BaseModel):
    model_config = _STRICT

    age_tier_label_verbatim: NonEmptyStr


class _MonthPolicyIn(BaseModel):
    model_config = _STRICT

    has_month_assignment: Literal[False]
    """True가 되면 스키마 위반이다. 법령에 월 지정이 0건이다."""


class _CategoryIn(BaseModel):
    model_config = _STRICT

    category_id: NonEmptyStr
    official_label: NonEmptyStr
    interval_months: PositiveInt
    annual_hours_min: PositiveInt
    interval_verbatim: NonEmptyStr
    annual_hours_min_verbatim: NonEmptyStr

    def to_domain(self) -> SafetyCategory:
        return SafetyCategory(
            category_id=self.category_id,
            official_label=self.official_label,
            interval_months=self.interval_months,
            annual_hours_min=self.annual_hours_min,
        )


class _RuleIn(BaseModel):
    model_config = _STRICT

    legal_rule_version: NonEmptyStr
    normative_status: Literal["STATUTORY"]
    review: _ReviewIn
    applicable_scope: _ScopeIn
    month_assignment_policy: _MonthPolicyIn
    categories: list[_CategoryIn]
    placement_policy_version: None = None
    """P0에서는 제품 기본 배치 정책을 발행하지 않으므로 반드시 null이다."""


def _reject_placement_fields(payload: object) -> None:
    """category에 배치성 필드가 생기면 차단한다."""
    if not isinstance(payload, dict):
        return
    for raw in payload.get("categories") or []:
        if not isinstance(raw, dict):
            continue
        for key in raw:
            lowered = key.lower()
            if lowered == "interval_months":
                continue
            if any(bad in lowered for bad in FORBIDDEN_CATEGORY_KEYS):
                raise SafetyLegalRuleSchemaError(
                    f"법정 category에 배치성 필드가 있다: "
                    f"{raw.get('category_id')}.{key}. "
                    "법령에는 월 지정이 없으며 배치는 placement policy가 담당한다."
                )


def parse_safety_legal_rule_payload(
    payload: object, *, approval_override: str | None = None
) -> SafetyLegalRule:
    """원시 JSON을 검증하고 Domain `SafetyLegalRule`로 변환한다."""
    _reject_placement_fields(payload)

    try:
        parsed = _RuleIn.model_validate(payload)
    except ValidationError as exc:
        raise SafetyLegalRuleSchemaError(
            f"법정 Safety Rule JSON이 Input Schema를 위반한다: {exc}"
        ) from exc

    if len(parsed.categories) != LEGAL_CATEGORY_COUNT:
        raise SafetyLegalRuleSchemaError(
            f"별표6 법정 구분은 {LEGAL_CATEGORY_COUNT}개여야 한다: "
            f"{len(parsed.categories)}개"
        )

    for category in parsed.categories:
        for label in NON_LEGAL_LABELS:
            if label in category.official_label:
                raise SafetyLegalRuleSchemaError(
                    f"비법정 기관 label이 official category에 있다: "
                    f"{category.official_label}. 법정 6구분으로 매핑하지 않는다."
                )

    approval = approval_override or parsed.review.domain_owner_approval
    derived_active = approval == HUMAN_APPROVED

    if approval_override is None and parsed.review.runtime_active != derived_active:
        raise SafetyLegalRuleSchemaError(
            "runtime_active가 승인 상태에서 파생된 값과 다르다. "
            f"domain_owner_approval={approval!r} -> 기대 {derived_active}, "
            f"파일 값 {parsed.review.runtime_active}."
        )

    try:
        return SafetyLegalRule(
            legal_rule_version=parsed.legal_rule_version,
            normative_status=parsed.normative_status,
            categories=tuple(c.to_domain() for c in parsed.categories),
            age_tier_label=parsed.applicable_scope.age_tier_label_verbatim,
            placement_policy_version=parsed.placement_policy_version,
            runtime_active=derived_active,
        )
    except ValueError as exc:
        raise SafetyLegalRuleSchemaError(
            f"법정 Safety Rule이 Domain 불변식을 위반한다: {exc}"
        ) from exc
