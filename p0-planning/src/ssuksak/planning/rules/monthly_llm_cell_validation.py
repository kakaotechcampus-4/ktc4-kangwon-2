"""Regenerated Cell Deterministic Validator (L7).

L5가 한 달 전체 Proposal에 하던 검사를 **Cell 하나**에 적용한다.

    L5   MonthlyPlanProposal (주차 전부)  → validate_monthly_proposal
    L7   Cell 하나                        → validate_cell_proposal

**Violation 어휘를 새로 만들지 않았다.** `ProposalViolationCode`를 그대로 쓴다 —
같은 위반을 다른 이름으로 부르면 repair 분류와 UI가 두 벌이 된다.

**LLM을 호출하지 않는다.** 의미 유사도·주제 적합성·paired Cell 어울림을 코드가
판단하는 척하지 않는다(L5 §16과 같은 한계).
"""

from __future__ import annotations

from collections.abc import Sequence

from ...shared.llm.monthly import ProposedActivityOrigin
from ...shared.llm.monthly_cell import (
    FOCUS_SECTION_KEY,
    OUTDOOR_SECTION_KEY,
    MonthlyCellProposalError,
    MonthlyCellRegenerationProposal,
    MonthlyCellRegenerationRequest,
    reconcile_cell_proposal,
)
from ..context.budget import packet_fingerprint
from ..context.models import MonthlyContextPacket
from .monthly_llm_text_policy import (
    find_official_claims,
    find_safety_education,
    find_source_identifiers,
    normalize_for_comparison,
)
from .monthly_llm_validation import (
    GENERATION_METHOD,
    PLANNER_RULE_ID,
    PLANNER_RULE_VERSION,
    WEEK_ORDER_BASIS,
    MonthlyProposalValidationResult,
    ProposalViolation,
    ProposalViolationCode,
    WeekProvenanceDraft,
    build_packet_index,
)

__all__ = ["SiblingCell", "validate_cell_proposal"]


class SiblingCell:
    """같은 달의 다른 Cell 하나. 중복 판정에만 쓴다."""

    __slots__ = ("week_id", "section_key", "value", "activity_id")

    def __init__(
        self,
        *,
        week_id: str,
        section_key: str,
        value: str,
        activity_id: str | None = None,
    ) -> None:
        self.week_id = week_id
        self.section_key = section_key
        self.value = value
        self.activity_id = activity_id


def validate_cell_proposal(
    proposal: MonthlyCellRegenerationProposal,
    packet: MonthlyContextPacket,
    request: MonthlyCellRegenerationRequest,
    *,
    siblings: Sequence[SiblingCell],
    planner_model: str = "",
) -> MonthlyProposalValidationResult:
    """재생성된 Cell 하나를 검증한다.

    `siblings`는 **Target을 제외한** 같은 달의 Cell들이다. Target 자신의 기존
    값과 같은 값이 다시 나오는 것은 여기서 막지 않는다 — 기존 Rule Regenerate가
    동일 값을 성공으로 다루므로 그 의미를 바꾸지 않는다(§10).
    """
    fingerprint = packet_fingerprint(packet)
    violations: list[ProposalViolation] = []
    week_id = request.target_week_id
    section_key = request.target_section_key

    def fail(code, field_name, detail="") -> None:
        violations.append(
            ProposalViolation(
                code=code, field=field_name, detail=detail, week_id=week_id
            )
        )

    def result(provenance=()) -> MonthlyProposalValidationResult:
        return MonthlyProposalValidationResult(
            is_valid=not violations,
            violations=tuple(violations),
            provenance=tuple(provenance),
            planner_model=planner_model,
            prompt_version=request.prompt_version,
            packet_fingerprint=fingerprint,
            generation_method=GENERATION_METHOD,
            rule_id=PLANNER_RULE_ID,
            rule_version=PLANNER_RULE_VERSION,
            week_order_basis=WEEK_ORDER_BASIS,
        )

    # 1) 다른 Packet의 제안인가. 어긋나면 나머지 검사가 무의미하다.
    if request.packet_fingerprint != fingerprint:
        fail(
            ProposalViolationCode.PACKET_FINGERPRINT_MISMATCH,
            "packet_fingerprint",
            "요청의 fingerprint가 검증 대상 Packet과 다르다",
        )
        return result()

    # 2) 계약 형태는 reconcile이 본다. 다시 구현하지 않는다.
    try:
        reconcile_cell_proposal(
            proposal,
            target_week_id=week_id,
            target_section_key=section_key,
            reference_labels=request.reference_labels,
            valid_grounding_refs=frozenset(build_packet_index(packet).by_ref),
        )
    except MonthlyCellProposalError as exc:
        fail(
            ProposalViolationCode.BASIC_CONTRACT_VIOLATION,
            "proposal",
            exc.violation.value,
        )
        return result()

    index = build_packet_index(packet)
    requested_ages = set(packet.planning_request.classroom_ages)

    # 3) 교사에게 보이는 문자열 검사 — L5와 같은 정책을 쓴다.
    claims = find_official_claims(proposal.value)
    if claims:
        fail(
            ProposalViolationCode.FORBIDDEN_OFFICIAL_CLAIM,
            "value",
            f"범주: {', '.join(claims)}",
        )
    safety = find_safety_education(proposal.value)
    if safety:
        fail(
            ProposalViolationCode.SAFETY_CONTENT_LEAKAGE,
            "value",
            f"범주: {', '.join(safety)}",
        )
    leaked = find_source_identifiers(
        proposal.value, institution_names=index.institution_names
    )
    if leaked:
        fail(
            ProposalViolationCode.SOURCE_IDENTIFIER_LEAKAGE,
            "value",
            f"종류: {', '.join(leaked)}",
        )

    # 4) 같은 달의 다른 Cell과 중복인가.
    normalized = normalize_for_comparison(proposal.value)
    for sibling in siblings:
        if sibling.section_key != section_key:
            continue
        if normalize_for_comparison(sibling.value) == normalized:
            code = (
                ProposalViolationCode.DUPLICATE_EXPERIENCE
                if section_key == FOCUS_SECTION_KEY
                else ProposalViolationCode.DUPLICATE_ACTIVITY
            )
            fail(code, "value", f"{sibling.week_id}와 같은 값이다")
            break

    if section_key == OUTDOOR_SECTION_KEY and proposal.reference_activity_id:
        for sibling in siblings:
            if sibling.section_key != OUTDOOR_SECTION_KEY:
                continue
            if sibling.activity_id == proposal.reference_activity_id:
                fail(
                    ProposalViolationCode.DUPLICATE_ACTIVITY,
                    "reference_activity_id",
                    f"{sibling.week_id}에서 이미 쓴 승인 활동이다",
                )
                break

    # 5) Activity 전용 검사.
    if section_key == OUTDOOR_SECTION_KEY:
        _check_outdoor(proposal, index, requested_ages, fail)

    provenance = (
        WeekProvenanceDraft(
            week_id=week_id,
            activity_origin=(
                proposal.activity_origin.value
                if proposal.activity_origin is not None
                else ""
            ),
            reference_activity_id=proposal.reference_activity_id,
            grounding_source_ids=tuple(
                index.by_ref[ref].record_id
                for ref in proposal.grounding_refs
                if ref in index.by_ref
            ),
        ),
    )

    if not planner_model.strip() or not request.prompt_version.strip():
        fail(
            ProposalViolationCode.PROVENANCE_INCOMPLETE,
            "provenance",
            "planner_model 또는 prompt_version이 비어 있다",
        )
    elif section_key == OUTDOOR_SECTION_KEY and not provenance[0].is_complete:
        fail(
            ProposalViolationCode.PROVENANCE_INCOMPLETE,
            "provenance",
            f"origin={provenance[0].activity_origin}에 필요한 근거 식별자가 없다",
        )

    return result(provenance)


def _check_outdoor(proposal, index, requested_ages, fail) -> None:
    """L5 `_check_synthesized` / `_check_reference`와 같은 규칙을 Cell에 적용한다."""
    if proposal.activity_origin is ProposedActivityOrigin.REFERENCE:
        activity_id = proposal.reference_activity_id
        supported = index.reference_ages.get(activity_id)
        if supported is None:
            fail(
                ProposalViolationCode.REFERENCE_NOT_IN_PACKET,
                "reference_activity_id",
                "이번 Packet의 후보 목록에 없다",
            )
            return
        missing = sorted(requested_ages - set(supported))
        if missing:
            fail(
                ProposalViolationCode.REFERENCE_AGE_UNSUPPORTED,
                "reference_activity_id",
                f"지원하지 않는 요청 연령: {missing}",
            )
        return

    # 핵심 Gate — CONTEXT_ONLY 원문 복사. grounding_refs에 적은 것뿐 아니라
    # Packet이 준 **모든** CONTEXT_ONLY 텍스트와 비교한다(L5 §7과 동일).
    matched = index.context_only_normalized.get(
        normalize_for_comparison(proposal.value)
    )
    if matched:
        fail(
            ProposalViolationCode.SYNTHESIZED_EXACT_SOURCE_COPY,
            "value",
            f"일치한 근거 참조: {', '.join(matched)}",
        )

    grounded = []
    for ref in proposal.grounding_refs:
        item = index.by_ref.get(ref)
        if item is None:
            fail(
                ProposalViolationCode.INVALID_GROUNDING_REF,
                "grounding_refs",
                f"{ref}는 이번 Packet에 없다",
            )
            continue
        if not item.is_eligible:
            fail(
                ProposalViolationCode.INELIGIBLE_GROUNDING,
                "grounding_refs",
                f"{ref}의 추출 품질이 Grounding 조건을 만족하지 않는다",
            )
            continue
        grounded.append(item)

    if grounded and all(
        item.single_age is not None and item.single_age not in requested_ages
        for item in grounded
    ):
        others = "·".join(f"만{a}세" for a in sorted({i.single_age for i in grounded}))
        fail(
            ProposalViolationCode.GROUNDING_AGE_MISMATCH,
            "grounding_refs",
            f"참조가 전부 {others} 단일연령 근거다",
        )
