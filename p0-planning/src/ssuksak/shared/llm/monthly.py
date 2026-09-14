"""Monthly Planner Structured Output Contract (L4).

Yearly Theme 다듬기와 **역할이 다르다.**

    polish_themes   Rule이 이미 고른 값의 표현만 바꾼다
    plan_monthly    한 달 전체 흐름을 LLM이 구성한다

그래도 경계 원칙은 같다. LLM은 `theme_id`를 고르지 않고, 주차를 만들지 않고,
안전교육을 배치하지 않는다(CLAUDE.md §5). 여기의 reconcile이 그것을 강제한다.

**Adapter는 Domain을 모른다.** `MonthlyPlannerRequest`는 이미 렌더링된 문자열과
검증 anchor만 담는다. Adapter가 `MonthlyContextPacket` · Evidence Store ·
Activity Repository를 직접 조회하지 않는다(CLAUDE.md §16 격리 경계).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

__all__ = [
    "MonthlyPlanProposal",
    "MonthlyPlannerRequest",
    "MonthlyProposalError",
    "MonthlyProposalViolation",
    "ProposedActivity",
    "ProposedActivityOrigin",
    "ProposedWeek",
    "reconcile_monthly_proposal",
]


def _non_blank(value: str) -> str:
    if not value.strip():
        raise ValueError("공백 문자열은 허용되지 않는다")
    return value


NonBlankStr = Annotated[str, Field(strict=True), AfterValidator(_non_blank)]


class ProposedActivityOrigin(str, Enum):
    """Proposal이 쓸 수 있는 Activity origin.

    `planning.context.ActivityOrigin`의 **부분집합**이다. P0 Corpus record가
    전부 `CONTEXT_ONLY`이므로 `CORPUS_EVIDENCE`는 여기 없다. 두 enum의 값이
    어긋나지 않도록 테스트로 고정한다.

    shared가 planning을 import하지 않기 위해 값을 복제했다 — 반대 방향으로
    import하면 LLM 계층이 Domain에 묶인다.
    """

    REFERENCE = "REFERENCE"
    LLM_SYNTHESIZED = "LLM_SYNTHESIZED"


# ------------------------------------------------------------------ 요청


@dataclass(frozen=True, slots=True)
class MonthlyPlannerRequest:
    """Adapter에 전달하는 입력.

    `system_prompt`와 `user_content`는 **이미 렌더링된 문자열**이다. Prompt
    본문을 Adapter에 두지 않기 위해서다(§20). Adapter는 이것을 전송하고
    응답을 schema로 파싱한 뒤 아래 anchor로 대조한다.
    """

    task: str
    prompt_version: str
    system_prompt: str
    user_content: str

    expected_theme_id: str
    expected_week_ids: tuple[str, ...]

    reference_labels: Mapping[str, str] = field(default_factory=dict)
    """`activity_id → label`. REFERENCE 선택 시 value가 label과 같아야 한다."""

    valid_grounding_refs: frozenset[str] = frozenset()
    """Packet에 실제로 존재하는 `E01` 형태의 참조. 없는 ref를 만들지 못하게 한다."""

    packet_fingerprint: str = ""
    """어느 Context에서 나온 요청인지. 재현·감사용이며 Prompt에 넣지 않는다."""

    def __post_init__(self) -> None:
        if not self.expected_theme_id.strip():
            raise ValueError("expected_theme_id는 비어 있을 수 없다")
        if not self.expected_week_ids:
            raise ValueError("expected_week_ids가 비어 있다")
        if len(set(self.expected_week_ids)) != len(self.expected_week_ids):
            raise ValueError(f"expected_week_ids에 중복이 있다: {self.expected_week_ids}")
        if not self.system_prompt.strip() or not self.user_content.strip():
            raise ValueError("system_prompt와 user_content는 비어 있을 수 없다")


# ------------------------------------------------------------------ 응답


class ProposedActivity(BaseModel):
    """한 주의 활동 하나.

    `reference_activity_id`와 `grounding_refs`를 **둘 다 필수 필드**로 둔다.
    Structured Output strict mode가 optional 필드를 다루는 방식이 Provider마다
    다르므로, 비어 있음을 `null`과 `[]`로 명시하게 하는 편이 안전하다.
    """

    model_config = ConfigDict(extra="forbid")

    value: NonBlankStr
    origin: ProposedActivityOrigin
    reference_activity_id: str | None
    grounding_refs: list[str]


class ProposedWeek(BaseModel):
    model_config = ConfigDict(extra="forbid")

    week_id: NonBlankStr
    experience: NonBlankStr
    activity: ProposedActivity


class MonthlyPlanProposal(BaseModel):
    """LLM이 돌려주는 한 달 제안.

    Safety field가 **없다.** 안전교육은 Planner의 영역이 아니므로 담을 자리를
    만들지 않는다(§17). 자리를 만들면 모델이 채운다.
    """

    model_config = ConfigDict(extra="forbid")

    theme_id: NonBlankStr
    month_flow_rationale: NonBlankStr
    weeks: Annotated[list[ProposedWeek], Field(min_length=1, max_length=6)]


# ------------------------------------------------------------- reconcile


class MonthlyProposalViolation(str, Enum):
    """reconcile 실패 종류.

    Golden Set의 `failure_category`와 같은 성격의 **테스트 의미 식별자**이며
    공개 HTTP 오류 코드로 자동 승격하지 않는다(CLAUDE.md §20).
    """

    THEME_ID_MISMATCH = "llm_must_not_select_or_replace_theme"
    MISSING_WEEK = "llm_must_cover_every_week"
    EXTRA_WEEK = "llm_must_not_add_weeks"
    DUPLICATE_WEEK = "llm_must_not_duplicate_week"
    WEEK_ORDER_MISMATCH = "llm_must_keep_packet_week_order"
    REFERENCE_REQUIRES_ID = "reference_activity_requires_reference_activity_id"
    UNKNOWN_REFERENCE_ID = "reference_activity_id_must_exist_in_packet"
    REFERENCE_VALUE_MISMATCH = "reference_activity_value_must_match_catalog_label"
    SYNTHESIZED_MUST_NOT_CLAIM_REFERENCE = (
        "synthesized_activity_must_not_set_reference_activity_id"
    )
    SYNTHESIZED_REQUIRES_GROUNDING = "synthesized_activity_requires_grounding_refs"
    UNKNOWN_GROUNDING_REF = "grounding_ref_must_exist_in_packet"


class MonthlyProposalError(ValueError):
    """Proposal이 Packet Contract와 어긋난다.

    부분 수용을 허용하지 않는다. 하나라도 어긋나면 전체 실패다 — 절반만 맞는
    계획안을 성공으로 저장하지 않는다(CLAUDE.md §14).
    """

    def __init__(
        self,
        violation: MonthlyProposalViolation,
        detail: str = "",
        week_id: str | None = None,
    ) -> None:
        self.violation = violation
        self.detail = detail
        self.week_id = week_id
        where = f" [{week_id}]" if week_id else ""
        super().__init__(f"{violation.value}{where} {detail}".rstrip())

    @property
    def summary(self) -> str:
        """Repair 호출에 넣을 한 줄 요약. Prompt 본문이나 Key를 담지 않는다."""
        where = f" ({self.week_id})" if self.week_id else ""
        return f"{self.violation.value}{where}: {self.detail}".strip()


def _normalized(value: str) -> str:
    return " ".join(value.split())


def reconcile_monthly_proposal(
    proposal: MonthlyPlanProposal,
    *,
    expected_theme_id: str,
    expected_week_ids: Sequence[str],
    reference_labels: Mapping[str, str],
    valid_grounding_refs: frozenset[str],
) -> MonthlyPlanProposal:
    """Proposal을 Packet Contract와 대조한다.

    여기서 보는 것은 **계약 형태**다. 의미 중복 판정 · 원문 복사 탐지 ·
    금지 표현 탐지 같은 Deterministic Validator는 L5 범위다(§35).

    Raises:
        MonthlyProposalError: Theme / Week / Origin 계약 위반.
    """
    if proposal.theme_id != expected_theme_id:
        raise MonthlyProposalError(
            MonthlyProposalViolation.THEME_ID_MISMATCH,
            f"입력 {expected_theme_id} != 반환 {proposal.theme_id}",
        )

    seen: list[str] = []
    expected = list(expected_week_ids)
    for week in proposal.weeks:
        if week.week_id in seen:
            raise MonthlyProposalError(
                MonthlyProposalViolation.DUPLICATE_WEEK,
                "같은 주차가 두 번 반환되었다",
                week_id=week.week_id,
            )
        if week.week_id not in expected:
            raise MonthlyProposalError(
                MonthlyProposalViolation.EXTRA_WEEK,
                f"Packet에 없는 주차다 (기대 {expected})",
                week_id=week.week_id,
            )
        seen.append(week.week_id)
        _check_activity(week, reference_labels, valid_grounding_refs)

    missing = [w for w in expected if w not in seen]
    if missing:
        raise MonthlyProposalError(
            MonthlyProposalViolation.MISSING_WEEK,
            f"반환되지 않은 주차: {missing}",
        )
    if seen != expected:
        raise MonthlyProposalError(
            MonthlyProposalViolation.WEEK_ORDER_MISMATCH,
            f"Packet 순서 {expected} != 반환 순서 {seen}",
        )
    return proposal


def _check_activity(
    week: ProposedWeek,
    reference_labels: Mapping[str, str],
    valid_grounding_refs: frozenset[str],
) -> None:
    activity = week.activity

    unknown = [r for r in activity.grounding_refs if r not in valid_grounding_refs]
    if unknown:
        raise MonthlyProposalError(
            MonthlyProposalViolation.UNKNOWN_GROUNDING_REF,
            f"Packet에 없는 근거 참조다: {unknown}",
            week_id=week.week_id,
        )

    if activity.origin is ProposedActivityOrigin.REFERENCE:
        if not activity.reference_activity_id:
            raise MonthlyProposalError(
                MonthlyProposalViolation.REFERENCE_REQUIRES_ID,
                "origin=REFERENCE인데 reference_activity_id가 없다",
                week_id=week.week_id,
            )
        label = reference_labels.get(activity.reference_activity_id)
        if label is None:
            raise MonthlyProposalError(
                MonthlyProposalViolation.UNKNOWN_REFERENCE_ID,
                f"Packet 후보에 없는 activity_id다: {activity.reference_activity_id}",
                week_id=week.week_id,
            )
        if _normalized(activity.value) != _normalized(label):
            # id만 맞추고 문구를 바꾸는 것을 막는다. 승인 Catalog 값은 그대로 쓴다.
            raise MonthlyProposalError(
                MonthlyProposalViolation.REFERENCE_VALUE_MISMATCH,
                f"승인 label {label!r} != 반환 value {activity.value!r}",
                week_id=week.week_id,
            )
        return

    if activity.reference_activity_id:
        raise MonthlyProposalError(
            MonthlyProposalViolation.SYNTHESIZED_MUST_NOT_CLAIM_REFERENCE,
            f"origin={activity.origin.value}인데 "
            f"reference_activity_id={activity.reference_activity_id!r}가 있다",
            week_id=week.week_id,
        )
    if not activity.grounding_refs:
        raise MonthlyProposalError(
            MonthlyProposalViolation.SYNTHESIZED_REQUIRES_GROUNDING,
            "합성 Activity는 최소 1개의 grounding_ref가 필요하다",
            week_id=week.week_id,
        )
