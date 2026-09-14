"""Monthly LLM Proposal Deterministic Validator (L5).

저장 전 마지막 Guardrail이다.

    MonthlyContextPacket + MonthlyPlanProposal
        → validate_monthly_proposal()
        → VALID  또는  결정론적 violation 목록

**LLM을 호출하지 않는다.** LLM-as-a-judge · semantic grading · embedding ·
GPT 재검토를 쓰지 않는다. 코드로 확인 가능한 사실만 판정한다. 모델에게 자기
출력을 다시 평가시키면 같은 착각을 두 번 하게 된다.

**L4 reconcile을 다시 구현하지 않는다.** Theme lock · Week lock ·
REFERENCE id/value · SYNTHESIZED grounding 유무는
`shared.llm.monthly.reconcile_monthly_proposal()`이 이미 본다. L5는 그것을
호출해 재사용하고, 그 위의 Product-safe 검증을 담당한다.

L5가 존재하는 이유는 실측이다. L4 Live Smoke에서 `LLM_SYNTHESIZED` 활동 2건이
모두 `CONTEXT_ONLY` 근거 문장의 글자 그대로 복사였고, Prompt 강화로는
사라지지 않았다(`docs/analysis/monthly-llm-planner-l4-gpt-planner.md` §14.3).
Prompt는 확률을 낮출 뿐 보장하지 않는다.
"""

from __future__ import annotations

import collections
from dataclasses import dataclass, field
from enum import Enum

from ...shared.llm.monthly import (
    MonthlyPlannerRequest,
    MonthlyPlanProposal,
    MonthlyProposalError,
    ProposedActivityOrigin,
    ProposedWeek,
    reconcile_monthly_proposal,
)
from ..context.budget import packet_fingerprint
from ..context.models import MonthlyContextPacket
from .monthly_llm_text_policy import (
    find_official_claims,
    find_safety_education,
    find_source_identifiers,
    normalize_for_comparison,
)

__all__ = [
    "GENERATION_METHOD",
    "PLANNER_RULE_ID",
    "PLANNER_RULE_VERSION",
    "WEEK_ORDER_BASIS",
    "GroundedText",
    "MonthlyProposalValidationResult",
    "PacketIndex",
    "ProposalViolation",
    "ProposalViolationCode",
    "WeekProvenanceDraft",
    "build_packet_index",
    "build_provenance_drafts",
    "validate_monthly_proposal",
]

PLANNER_RULE_ID = "monthly.llm.evidence_grounded_planner"
PLANNER_RULE_VERSION = "v1"
GENERATION_METHOD = "RULE_LLM"
WEEK_ORDER_BASIS = "PLANNER_COMPOSED"
"""OD-N14 확정값.

Corpus에 주차 순서 근거가 없으므로(`week_position` 보유 0건) LLM Planner 결과는
언제나 `PLANNER_COMPOSED`다. `SOURCE_OBSERVED`로 표기하지 않는다.
"""


# ------------------------------------------------------------------ 결과


class ProposalViolationCode(str, Enum):
    """L5 위반 종류.

    L4 `MonthlyProposalViolation`과 **겹치지 않는다.** L4 계약 위반은
    `BASIC_CONTRACT_VIOLATION` 하나로 감싸 전달하고 세부는 detail에 남긴다.

    Golden Set `failure_category`와 같은 성격의 테스트 의미 식별자이며
    공개 HTTP 오류 코드로 자동 승격하지 않는다(CLAUDE.md §20).
    """

    BASIC_CONTRACT_VIOLATION = "basic_proposal_contract_violation"

    SYNTHESIZED_EXACT_SOURCE_COPY = "synthesized_activity_copies_source_text_exactly"
    DUPLICATE_ACTIVITY = "activity_must_not_repeat_within_a_month"
    DUPLICATE_EXPERIENCE = "week_experience_must_not_repeat_within_a_month"

    FORBIDDEN_OFFICIAL_CLAIM = "must_not_claim_legal_or_official_authority"
    SAFETY_CONTENT_LEAKAGE = "must_not_generate_statutory_safety_education"
    SOURCE_IDENTIFIER_LEAKAGE = "must_not_expose_grounding_identifiers"

    ORIGIN_NOT_ALLOWED = "activity_origin_not_allowed_by_packet"
    REFERENCE_NOT_IN_PACKET = "reference_activity_must_come_from_this_packet"
    REFERENCE_AGE_UNSUPPORTED = "reference_activity_must_support_requested_ages"

    INVALID_GROUNDING_REF = "grounding_ref_must_exist_in_this_packet"
    INELIGIBLE_GROUNDING = "grounding_record_must_be_grounding_eligible"
    GROUNDING_AGE_MISMATCH = "grounding_must_not_be_only_other_single_ages"

    PACKET_FINGERPRINT_MISMATCH = "proposal_must_belong_to_this_packet"
    PROVENANCE_INCOMPLETE = "provenance_fields_must_be_resolvable"


_REPAIRABLE: frozenset[ProposalViolationCode] = frozenset(
    {
        ProposalViolationCode.BASIC_CONTRACT_VIOLATION,
        ProposalViolationCode.SYNTHESIZED_EXACT_SOURCE_COPY,
        ProposalViolationCode.DUPLICATE_ACTIVITY,
        ProposalViolationCode.DUPLICATE_EXPERIENCE,
        ProposalViolationCode.FORBIDDEN_OFFICIAL_CLAIM,
        ProposalViolationCode.SAFETY_CONTENT_LEAKAGE,
        ProposalViolationCode.SOURCE_IDENTIFIER_LEAKAGE,
        ProposalViolationCode.ORIGIN_NOT_ALLOWED,
        ProposalViolationCode.REFERENCE_NOT_IN_PACKET,
        ProposalViolationCode.REFERENCE_AGE_UNSUPPORTED,
        ProposalViolationCode.INVALID_GROUNDING_REF,
        ProposalViolationCode.GROUNDING_AGE_MISMATCH,
    }
)
"""모델이 다시 써서 고칠 수 있는 위반.

여기 없는 것은 **Context·Packet·설정 쪽 문제**이므로 모델에게 되돌려 보내면
안 된다. 같은 Packet으로 다시 물어봐야 같은 답이 나온다.

    PACKET_FINGERPRINT_MISMATCH   다른 Packet의 Proposal이다
    INELIGIBLE_GROUNDING          Packet이 부적격 Evidence를 담고 있다
    PROVENANCE_INCOMPLETE         호출자가 model/prompt metadata를 안 줬다
"""

_REPAIR_HINTS: dict[ProposalViolationCode, str] = {
    ProposalViolationCode.SYNTHESIZED_EXACT_SOURCE_COPY: (
        "합성 활동의 이름이 참고 근거 문장과 글자 그대로 같습니다. "
        "같은 놀이 아이디어를 유지하되 표현을 새로 쓰세요."
    ),
    ProposalViolationCode.DUPLICATE_ACTIVITY: (
        "한 달 안에서 같은 활동이 두 번 쓰였습니다. 주차마다 다른 활동을 쓰세요."
    ),
    ProposalViolationCode.DUPLICATE_EXPERIENCE: (
        "두 주차의 중심 경험 문장이 같습니다. 주차마다 다른 경험을 쓰세요."
    ),
    ProposalViolationCode.FORBIDDEN_OFFICIAL_CLAIM: (
        "법적 근거나 공식 권장이라고 주장하는 표현이 있습니다. 그런 표현을 빼세요."
    ),
    ProposalViolationCode.SAFETY_CONTENT_LEAKAGE: (
        "법정 안전교육을 만들거나 배치하는 표현이 있습니다. 안전교육은 다루지 않습니다."
    ),
    ProposalViolationCode.SOURCE_IDENTIFIER_LEAKAGE: (
        "교사에게 보이는 문장에 근거 참조나 출처 이름이 들어 있습니다. 빼세요."
    ),
    ProposalViolationCode.ORIGIN_NOT_ALLOWED: (
        "허용되지 않은 활동 출처를 썼습니다. 허용된 값만 쓰세요."
    ),
    ProposalViolationCode.REFERENCE_NOT_IN_PACKET: (
        "제공되지 않은 승인 활동을 골랐습니다. 목록에 있는 후보에서만 고르세요."
    ),
    ProposalViolationCode.REFERENCE_AGE_UNSUPPORTED: (
        "요청 연령을 지원하지 않는 승인 활동을 골랐습니다. 다른 후보를 고르세요."
    ),
    ProposalViolationCode.INVALID_GROUNDING_REF: (
        "제공되지 않은 근거 참조를 썼습니다. 주어진 참조만 쓰세요."
    ),
    ProposalViolationCode.GROUNDING_AGE_MISMATCH: (
        "요청 연령과 무관한 다른 연령 근거만 참조했습니다. "
        "요청 연령의 근거나 혼합연령 근거를 함께 쓰세요."
    ),
}


@dataclass(frozen=True, slots=True)
class ProposalViolation:
    """위반 하나.

    `detail`에 **원문 Evidence · 기관명 · 비밀정보를 넣지 않는다**(§24).
    무엇이 왜 걸렸는지는 code와 범주·참조 id로 충분히 전달된다.
    """

    code: ProposalViolationCode
    field: str
    detail: str = ""
    week_id: str | None = None

    @property
    def is_repairable(self) -> bool:
        return self.code in _REPAIRABLE

    @property
    def repair_hint(self) -> str:
        """모델에게 되돌려 보낼 범주 수준 요약. 원문을 다시 넣지 않는다(§28)."""
        return _REPAIR_HINTS.get(self.code, "")

    def __str__(self) -> str:
        where = f" [{self.week_id}]" if self.week_id else ""
        return f"{self.code.value}{where} ({self.field}) {self.detail}".rstrip()


@dataclass(frozen=True, slots=True)
class WeekProvenanceDraft:
    """Proposal → Provenance 변환에 필요한 값이 실제로 있는지 보기 위한 초안.

    **여기서 Domain에 저장하지 않는다.** L6이 이 값으로 Plan Item Evidence와
    Generation Method를 채운다.
    """

    week_id: str
    activity_origin: str
    reference_activity_id: str | None
    grounding_source_ids: tuple[str, ...]
    """`grounding_refs`를 Packet audit으로 되짚은 실제 `record_id`."""

    @property
    def is_complete(self) -> bool:
        if self.activity_origin == ProposedActivityOrigin.REFERENCE.value:
            return bool(self.reference_activity_id)
        return bool(self.grounding_source_ids)


@dataclass(frozen=True, slots=True)
class MonthlyProposalValidationResult:
    """판정 결과. boolean 하나로 돌려주지 않는다."""

    is_valid: bool
    violations: tuple[ProposalViolation, ...] = ()
    provenance: tuple[WeekProvenanceDraft, ...] = ()

    planner_model: str = ""
    prompt_version: str = ""
    packet_fingerprint: str = ""
    generation_method: str = GENERATION_METHOD
    rule_id: str = PLANNER_RULE_ID
    rule_version: str = PLANNER_RULE_VERSION
    week_order_basis: str = WEEK_ORDER_BASIS

    @property
    def codes(self) -> tuple[ProposalViolationCode, ...]:
        return tuple(v.code for v in self.violations)

    @property
    def repairable_violations(self) -> tuple[ProposalViolation, ...]:
        return tuple(v for v in self.violations if v.is_repairable)

    @property
    def is_repairable(self) -> bool:
        """**모든** 위반이 고칠 수 있는 것일 때만 재요청 대상이다.

        하나라도 Context·설정 문제가 섞여 있으면 다시 물어봐야 소용이 없다.
        """
        return bool(self.violations) and all(v.is_repairable for v in self.violations)

    @property
    def repair_summary(self) -> tuple[str, ...]:
        """모델에게 되돌려 보낼 범주 수준 문장들. 중복을 없앤다."""
        hints = [v.repair_hint for v in self.violations if v.repair_hint]
        return tuple(dict.fromkeys(hints))


# ------------------------------------------------------------------ Packet


@dataclass(frozen=True, slots=True)
class GroundedText:
    """Packet이 Planner에게 준 근거 하나."""

    ref: str
    record_id: str
    text: str
    normalized: str
    age_scope: tuple[int, ...]
    reuse_policy: str
    extraction_quality: str
    machine_readability: str
    block: str

    @property
    def is_eligible(self) -> bool:
        return self.extraction_quality == "VALID" and (
            self.machine_readability == "TEXT_LAYER"
        )

    @property
    def single_age(self) -> int | None:
        return self.age_scope[0] if len(self.age_scope) == 1 else None


@dataclass(frozen=True, slots=True)
class PacketIndex:
    """Packet을 검증에 쓰기 좋은 형태로 펼친 것.

    Packet을 훑는 일이 검사마다 반복되므로 한 번만 만든다.
    """

    by_ref: dict[str, GroundedText] = field(default_factory=dict)
    context_only_normalized: dict[str, tuple[str, ...]] = field(default_factory=dict)
    """정규화 텍스트 → 그 텍스트를 가진 ref들.

    같은 문장이 여러 record로 중복 수록돼 있어도(L4 §14.4의 E25/E26)
    **Violation은 하나만** 나오게 하는 지점이다.
    """

    reference_ages: dict[str, tuple[int, ...]] = field(default_factory=dict)
    institution_names: frozenset[str] = frozenset()


def build_packet_index(packet: MonthlyContextPacket) -> PacketIndex:
    """Packet의 planner-visible 근거를 ref로 색인한다."""
    by_ref: dict[str, GroundedText] = {}
    institutions: set[str] = set()

    def add(item, block: str, text: str) -> None:
        if item.audit.institution_id:
            institutions.add(item.audit.institution_id)
        by_ref[item.ref] = GroundedText(
            ref=item.ref,
            record_id=item.audit.record_id,
            text=text,
            normalized=normalize_for_comparison(text),
            age_scope=tuple(item.age_scope),
            reuse_policy=item.reuse_policy.value,
            extraction_quality=item.audit.extraction_quality,
            machine_readability=item.audit.machine_readability,
            block=block,
        )

    for item in packet.institution_evidence:
        add(item, "institution_evidence", item.text)
    for item in packet.other_outdoor_evidence:
        add(item, "other_outdoor_evidence", item.text)
    for candidate in packet.week_experience_candidates:
        add(candidate, "week_experience_candidates", candidate.text)
    for group in packet.age_contrast_evidence:
        for obs in group.observations:
            for item in obs.items:
                add(item, "age_contrast_evidence", item.text)

    context_only: dict[str, list[str]] = collections.defaultdict(list)
    for grounded in by_ref.values():
        if grounded.reuse_policy == "CONTEXT_ONLY" and grounded.normalized:
            context_only[grounded.normalized].append(grounded.ref)

    return PacketIndex(
        by_ref=by_ref,
        context_only_normalized={
            text: tuple(sorted(refs)) for text, refs in context_only.items()
        },
        reference_ages={
            a.activity_id: tuple(a.supported_ages)
            for a in packet.reference_activities
        },
        institution_names=frozenset(institutions),
    )


# ------------------------------------------------------------------ 검증


def validate_monthly_proposal(
    proposal: MonthlyPlanProposal,
    packet: MonthlyContextPacket,
    planner_request: MonthlyPlannerRequest,
    *,
    planner_model: str = "",
) -> MonthlyProposalValidationResult:
    """저장 전 마지막 Guardrail.

    하나라도 걸리면 **Proposal 전체를 거부한다.** 일부 Week만 저장하지 않는다 —
    Monthly는 Planner 호출 하나의 결과이고, 절반만 맞는 계획안은 절반만
    틀린 계획안이다(§26).

    Args:
        planner_model: 실제 호출한 모델 문자열. Provenance에 필요하다.
    """
    fingerprint = packet_fingerprint(packet)
    violations: list[ProposalViolation] = []

    def fail(code, field_name, detail="", week_id=None) -> None:
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
            prompt_version=planner_request.prompt_version,
            packet_fingerprint=fingerprint,
        )

    # 1) 다른 Packet의 Proposal인가. 이것이 어긋나면 나머지 검사가 무의미하다.
    if planner_request.packet_fingerprint != fingerprint:
        fail(
            ProposalViolationCode.PACKET_FINGERPRINT_MISMATCH,
            "packet_fingerprint",
            "요청의 fingerprint가 검증 대상 Packet과 다르다",
        )
        return result()

    # 2) L4 기본 계약을 재사용한다. 다시 구현하지 않는다(§4).
    try:
        reconcile_monthly_proposal(
            proposal,
            expected_theme_id=packet.parent_theme.theme_id,
            expected_week_ids=tuple(w.week_id for w in packet.week_slots),
            reference_labels={
                a.activity_id: a.label for a in packet.reference_activities
            },
            valid_grounding_refs=frozenset(
                build_packet_index(packet).by_ref
            ),
        )
    except MonthlyProposalError as exc:
        # 구조가 깨졌으면 주차별 검사는 잡음만 만든다. 여기서 멈춘다.
        fail(
            ProposalViolationCode.BASIC_CONTRACT_VIOLATION,
            "proposal",
            exc.violation.value,
            week_id=exc.week_id,
        )
        return result()

    index = build_packet_index(packet)
    allowed = {o.value for o in packet.constraints.allowed_activity_origins}
    requested_ages = set(packet.planning_request.classroom_ages)

    _check_visible_text(
        proposal.month_flow_rationale, "month_flow_rationale", None, index, fail
    )

    for week in proposal.weeks:
        _check_week(
            week,
            index=index,
            allowed_origins=allowed,
            requested_ages=requested_ages,
            fail=fail,
        )

    _check_duplicates(proposal, fail)

    provenance = build_provenance_drafts(proposal, index)
    if not planner_model.strip() or not planner_request.prompt_version.strip():
        fail(
            ProposalViolationCode.PROVENANCE_INCOMPLETE,
            "provenance",
            "planner_model 또는 prompt_version이 비어 있다",
        )
    for draft in provenance:
        if not draft.is_complete:
            fail(
                ProposalViolationCode.PROVENANCE_INCOMPLETE,
                "provenance",
                f"origin={draft.activity_origin}에 필요한 근거 식별자가 없다",
                week_id=draft.week_id,
            )

    return result(provenance)


def _check_week(
    week: ProposedWeek,
    *,
    index: PacketIndex,
    allowed_origins: set[str],
    requested_ages: set[int],
    fail,
) -> None:
    activity = week.activity

    _check_visible_text(week.experience, "experience", week.week_id, index, fail)
    _check_visible_text(activity.value, "activity.value", week.week_id, index, fail)

    if activity.origin.value not in allowed_origins:
        fail(
            ProposalViolationCode.ORIGIN_NOT_ALLOWED,
            "activity.origin",
            f"{activity.origin.value}는 이 Packet이 허용하지 않는다",
            week_id=week.week_id,
        )

    if activity.origin is ProposedActivityOrigin.REFERENCE:
        _check_reference(week, index, requested_ages, fail)
    else:
        _check_synthesized(week, index, requested_ages, fail)


def _check_visible_text(text: str, field_name: str, week_id, index, fail) -> None:
    """교사에게 보이는 문자열에 대한 검사.

    `grounding_refs` 같은 metadata는 대상이 아니다 — 거기 `E06`이 있는 것은
    정상이다(§17).
    """
    claims = find_official_claims(text)
    if claims:
        fail(
            ProposalViolationCode.FORBIDDEN_OFFICIAL_CLAIM,
            field_name,
            f"범주: {', '.join(claims)}",
            week_id=week_id,
        )

    safety = find_safety_education(text)
    if safety:
        fail(
            ProposalViolationCode.SAFETY_CONTENT_LEAKAGE,
            field_name,
            f"범주: {', '.join(safety)}",
            week_id=week_id,
        )

    leaked = find_source_identifiers(
        text, institution_names=index.institution_names
    )
    if leaked:
        fail(
            ProposalViolationCode.SOURCE_IDENTIFIER_LEAKAGE,
            field_name,
            f"종류: {', '.join(leaked)}",
            week_id=week_id,
        )


def _check_reference(week, index: PacketIndex, requested_ages, fail) -> None:
    """승인 Activity는 **이번 Packet이 준 후보**에서만 고를 수 있다.

    Catalog에는 있지만 Packet에 넣지 않은 Activity를 모델이 알고 쓰는 것을
    막는다. Exact-copy 검사는 하지 않는다 — 승인 label을 글자 그대로 쓰는 것이
    정상이다(§8).
    """
    activity_id = week.activity.reference_activity_id
    if activity_id not in index.reference_ages:
        fail(
            ProposalViolationCode.REFERENCE_NOT_IN_PACKET,
            "activity.reference_activity_id",
            "이번 Packet의 후보 목록에 없다",
            week_id=week.week_id,
        )
        return

    supported = set(index.reference_ages[activity_id])
    missing = sorted(requested_ages - supported)
    if missing:
        fail(
            ProposalViolationCode.REFERENCE_AGE_UNSUPPORTED,
            "activity.reference_activity_id",
            f"지원하지 않는 요청 연령: {missing}",
            week_id=week.week_id,
        )


def _check_synthesized(week, index: PacketIndex, requested_ages, fail) -> None:
    activity = week.activity

    # 핵심 Gate — CONTEXT_ONLY 원문 복사.
    # grounding_refs에 적은 것뿐 아니라 **Packet이 준 모든 CONTEXT_ONLY 텍스트**와
    # 비교한다. 모델이 ref를 잘못 달아도 복사를 놓치지 않기 위해서다(§7).
    normalized = normalize_for_comparison(activity.value)
    matched = index.context_only_normalized.get(normalized)
    if matched:
        fail(
            ProposalViolationCode.SYNTHESIZED_EXACT_SOURCE_COPY,
            "activity.value",
            f"일치한 근거 참조: {', '.join(matched)}",
            week_id=week.week_id,
        )

    grounded = []
    for ref in activity.grounding_refs:
        item = index.by_ref.get(ref)
        if item is None:
            fail(
                ProposalViolationCode.INVALID_GROUNDING_REF,
                "activity.grounding_refs",
                f"{ref}는 이번 Packet에 없다",
                week_id=week.week_id,
            )
            continue
        if not item.is_eligible:
            fail(
                ProposalViolationCode.INELIGIBLE_GROUNDING,
                "activity.grounding_refs",
                f"{ref}의 추출 품질이 Grounding 조건을 만족하지 않는다",
                week_id=week.week_id,
            )
            continue
        grounded.append(item)

    # 요청 연령과 무관한 다른 연령의 단일연령 근거만 참조한 경우.
    # 혼합연령·연령 미상 근거가 하나라도 있으면 판단하지 않는다(§21).
    if grounded and all(
        item.single_age is not None and item.single_age not in requested_ages
        for item in grounded
    ):
        others = "·".join(f"만{a}세" for a in sorted({i.single_age for i in grounded}))
        fail(
            ProposalViolationCode.GROUNDING_AGE_MISMATCH,
            "activity.grounding_refs",
            f"참조가 전부 {others} 단일연령 근거다",
            week_id=week.week_id,
        )


def _check_duplicates(proposal: MonthlyPlanProposal, fail) -> None:
    """한 달 안의 중복. **정규화 완전 일치만** 본다.

    `여름 자연을 탐색해요`와 `여름의 자연을 살펴봐요`를 같다고 추론하지 않는다.
    의미 중복은 후속 Quality Evaluation 영역이다(§14).
    """
    seen_reference: dict[str, str] = {}
    seen_value: dict[str, str] = {}
    seen_experience: dict[str, str] = {}

    for week in proposal.weeks:
        activity = week.activity

        activity_id = activity.reference_activity_id
        if activity_id:
            first = seen_reference.get(activity_id)
            if first is not None:
                fail(
                    ProposalViolationCode.DUPLICATE_ACTIVITY,
                    "activity.reference_activity_id",
                    f"{first}에서 이미 쓴 승인 활동이다",
                    week_id=week.week_id,
                )
            else:
                seen_reference[activity_id] = week.week_id

        value = normalize_for_comparison(activity.value)
        first_value = seen_value.get(value)
        if first_value is not None and first_value != week.week_id:
            # origin이 달라도 같은 문구면 교사에게는 같은 활동이다.
            fail(
                ProposalViolationCode.DUPLICATE_ACTIVITY,
                "activity.value",
                f"{first_value}와 같은 활동 문구다",
                week_id=week.week_id,
            )
        else:
            seen_value.setdefault(value, week.week_id)

        experience = normalize_for_comparison(week.experience)
        first_experience = seen_experience.get(experience)
        if first_experience is not None:
            fail(
                ProposalViolationCode.DUPLICATE_EXPERIENCE,
                "experience",
                f"{first_experience}와 같은 경험 문장이다",
                week_id=week.week_id,
            )
        else:
            seen_experience[experience] = week.week_id


def build_provenance_drafts(
    proposal: MonthlyPlanProposal, index: PacketIndex
) -> tuple[WeekProvenanceDraft, ...]:
    """`grounding_refs`를 실제 `record_id`로 되짚는다.

    L6이 Plan Item Evidence를 채울 때 필요한 값이 모두 존재하는지 여기서
    확인한다. **저장은 하지 않는다.**
    """
    drafts: list[WeekProvenanceDraft] = []
    for week in proposal.weeks:
        activity = week.activity
        source_ids = tuple(
            index.by_ref[ref].record_id
            for ref in activity.grounding_refs
            if ref in index.by_ref
        )
        drafts.append(
            WeekProvenanceDraft(
                week_id=week.week_id,
                activity_origin=activity.origin.value,
                reference_activity_id=activity.reference_activity_id,
                grounding_source_ids=source_ids,
            )
        )
    return tuple(drafts)
