"""Monthly Cell Regeneration Contract (L7).

한 달 전체를 다시 만들지 않는다. **Cell 하나만** 재생성한다.

    plan_monthly              한 달 전체를 구성한다 (L4)
    regenerate_monthly_cell   Cell 하나만 다시 쓴다 (L7)

둘을 하나로 합치지 않은 이유는 `plan_monthly`로 한 달을 다시 만든 뒤 Target만
꺼내 쓰면 ① 필요 없는 token을 쓰고 ② 쓰지도 않을 나머지 Cell을 생성하며
③ 그 나머지가 기존 Plan과 어긋났을 때 무엇을 검증해야 하는지가 흐려지기
때문이다. Output이 Target 하나면 Contract도 Target 하나여야 한다.

**Adapter는 Domain을 모른다.** Request는 이미 렌더링된 문자열과 검증 anchor만
담는다(L4와 같은 경계).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from .monthly import ProposedActivityOrigin

__all__ = [
    "FOCUS_SECTION_KEY",
    "OUTDOOR_SECTION_KEY",
    "REGENERATABLE_LLM_SECTION_KEYS",
    "MonthlyCellRegenerationProposal",
    "MonthlyCellRegenerationRequest",
    "MonthlyCellViolation",
    "MonthlyCellProposalError",
    "reconcile_cell_proposal",
]

FOCUS_SECTION_KEY = "focus"
OUTDOOR_SECTION_KEY = "outdoor_play"

REGENERATABLE_LLM_SECTION_KEYS = frozenset({FOCUS_SECTION_KEY, OUTDOOR_SECTION_KEY})
"""LLM이 재생성할 수 있는 Section (2026-09-13 Product Decision B).

`theme`은 Rule이 parent anchor에서 재파생하고, `week_axis`는 축이며,
`safety_education`은 배치 source가 없다(OD-M04). 셋 다 대상이 아니다.
"""


def _non_blank(value: str) -> str:
    if not value.strip():
        raise ValueError("공백 문자열은 허용되지 않는다")
    return value


NonBlankStr = Annotated[str, Field(strict=True), AfterValidator(_non_blank)]


# ------------------------------------------------------------------ 요청


@dataclass(frozen=True, slots=True)
class MonthlyCellRegenerationRequest:
    """Adapter에 전달하는 입력.

    `user_content`에는 **한 달 전체 snapshot**이 들어간다. Target Cell만 보여
    주면 새 값이 월 전체 흐름과 어긋나기 때문이다. 반대로 **Output은 Target
    하나**다 — 보여주는 범위와 바꾸는 범위를 분리한다.
    """

    task: str
    prompt_version: str
    system_prompt: str
    user_content: str

    target_week_id: str
    target_section_key: str

    expected_theme_id: str
    reference_labels: Mapping[str, str] = field(default_factory=dict)
    valid_grounding_refs: frozenset[str] = frozenset()

    packet_fingerprint: str = ""
    plan_snapshot_fingerprint: str = ""
    """어떤 Plan 상태를 보고 만든 요청인지. 재현·감사용이며 Prompt에 넣지 않는다."""

    def __post_init__(self) -> None:
        if self.target_section_key not in REGENERATABLE_LLM_SECTION_KEYS:
            raise ValueError(
                f"LLM이 재생성할 수 있는 Section이 아니다: {self.target_section_key}"
            )
        if not self.target_week_id.strip():
            raise ValueError("target_week_id는 비어 있을 수 없다")
        if not self.expected_theme_id.strip():
            raise ValueError("expected_theme_id는 비어 있을 수 없다")
        if not self.system_prompt.strip() or not self.user_content.strip():
            raise ValueError("system_prompt와 user_content는 비어 있을 수 없다")

    @property
    def is_outdoor(self) -> bool:
        return self.target_section_key == OUTDOOR_SECTION_KEY


# ------------------------------------------------------------------ 응답


class MonthlyCellRegenerationProposal(BaseModel):
    """Target Cell 하나에 대한 제안.

    `focus`는 `value` 하나면 되고 나머지는 `null` / `[]`이다. Structured Output
    strict mode가 optional 필드를 다루는 방식이 Provider마다 다르므로 **모두
    필수 필드로 두고** 비어 있음을 명시하게 한다(L4와 같은 이유).

    다른 주차·다른 Section을 담을 자리가 **없다.** 자리를 만들면 모델이 채운다.
    """

    model_config = ConfigDict(extra="forbid")

    target_week_id: NonBlankStr
    target_section_key: NonBlankStr
    value: NonBlankStr

    activity_origin: ProposedActivityOrigin | None
    reference_activity_id: str | None
    grounding_refs: list[str]


# ------------------------------------------------------------- reconcile


class MonthlyCellViolation(str, Enum):
    """reconcile 실패 종류. 공개 HTTP 오류 코드로 자동 승격하지 않는다."""

    WRONG_WEEK = "regenerated_cell_must_target_the_requested_week"
    WRONG_SECTION = "regenerated_cell_must_target_the_requested_section"
    FOCUS_MUST_NOT_CARRY_ACTIVITY_FIELDS = (
        "focus_cell_must_not_carry_activity_origin_or_reference"
    )
    OUTDOOR_REQUIRES_ORIGIN = "outdoor_cell_requires_an_activity_origin"
    REFERENCE_REQUIRES_ID = "reference_activity_requires_reference_activity_id"
    UNKNOWN_REFERENCE_ID = "reference_activity_id_must_exist_in_packet"
    REFERENCE_VALUE_MISMATCH = "reference_activity_value_must_match_catalog_label"
    SYNTHESIZED_MUST_NOT_CLAIM_REFERENCE = (
        "synthesized_activity_must_not_set_reference_activity_id"
    )
    SYNTHESIZED_REQUIRES_GROUNDING = "synthesized_activity_requires_grounding_refs"
    UNKNOWN_GROUNDING_REF = "grounding_ref_must_exist_in_packet"


class MonthlyCellProposalError(ValueError):
    """Cell 제안이 요청 Contract와 어긋난다."""

    def __init__(self, violation: MonthlyCellViolation, detail: str = "") -> None:
        self.violation = violation
        self.detail = detail
        super().__init__(f"{violation.value} {detail}".rstrip())

    @property
    def summary(self) -> str:
        return f"{self.violation.value}: {self.detail}".strip()


def _normalized(value: str) -> str:
    return " ".join(value.split())


def reconcile_cell_proposal(
    proposal: MonthlyCellRegenerationProposal,
    *,
    target_week_id: str,
    target_section_key: str,
    reference_labels: Mapping[str, str],
    valid_grounding_refs: frozenset[str],
) -> MonthlyCellRegenerationProposal:
    """요청한 Cell에 대한 답이 맞는지, Activity 계약을 지켰는지 본다.

    의미 중복 · 원문 복사 · 금지 표현 검출은 **L5 계열 Validator**가 한다.
    여기는 계약 형태만 본다(L4와 같은 분담).
    """
    if proposal.target_week_id != target_week_id:
        raise MonthlyCellProposalError(
            MonthlyCellViolation.WRONG_WEEK,
            f"요청 {target_week_id} != 반환 {proposal.target_week_id}",
        )
    if proposal.target_section_key != target_section_key:
        raise MonthlyCellProposalError(
            MonthlyCellViolation.WRONG_SECTION,
            f"요청 {target_section_key} != 반환 {proposal.target_section_key}",
        )

    unknown = [r for r in proposal.grounding_refs if r not in valid_grounding_refs]
    if unknown:
        raise MonthlyCellProposalError(
            MonthlyCellViolation.UNKNOWN_GROUNDING_REF,
            f"Packet에 없는 근거 참조다: {unknown}",
        )

    if target_section_key == FOCUS_SECTION_KEY:
        if proposal.activity_origin is not None or proposal.reference_activity_id:
            raise MonthlyCellProposalError(
                MonthlyCellViolation.FOCUS_MUST_NOT_CARRY_ACTIVITY_FIELDS,
                "focus는 활동이 아니다. origin과 reference_activity_id는 null이어야 한다",
            )
        return proposal

    if proposal.activity_origin is None:
        raise MonthlyCellProposalError(
            MonthlyCellViolation.OUTDOOR_REQUIRES_ORIGIN,
            "outdoor_play는 REFERENCE 또는 LLM_SYNTHESIZED를 명시해야 한다",
        )

    if proposal.activity_origin is ProposedActivityOrigin.REFERENCE:
        if not proposal.reference_activity_id:
            raise MonthlyCellProposalError(
                MonthlyCellViolation.REFERENCE_REQUIRES_ID,
                "origin=REFERENCE인데 reference_activity_id가 없다",
            )
        label = reference_labels.get(proposal.reference_activity_id)
        if label is None:
            raise MonthlyCellProposalError(
                MonthlyCellViolation.UNKNOWN_REFERENCE_ID,
                f"후보에 없는 activity_id다: {proposal.reference_activity_id}",
            )
        if _normalized(proposal.value) != _normalized(label):
            raise MonthlyCellProposalError(
                MonthlyCellViolation.REFERENCE_VALUE_MISMATCH,
                f"승인 label {label!r} != 반환 value {proposal.value!r}",
            )
        return proposal

    if proposal.reference_activity_id:
        raise MonthlyCellProposalError(
            MonthlyCellViolation.SYNTHESIZED_MUST_NOT_CLAIM_REFERENCE,
            f"origin={proposal.activity_origin.value}인데 "
            f"reference_activity_id={proposal.reference_activity_id!r}가 있다",
        )
    if not proposal.grounding_refs:
        raise MonthlyCellProposalError(
            MonthlyCellViolation.SYNTHESIZED_REQUIRES_GROUNDING,
            "합성 Activity는 최소 1개의 grounding_ref가 필요하다",
        )
    return proposal
