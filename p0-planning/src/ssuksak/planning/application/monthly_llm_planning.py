"""Monthly LLM Planner 오케스트레이션 (L6).

`GenerateMonthlyPlan`이 이 하나만 호출하면 L2~L5가 순서대로 돈다.

    Retrieval → Context Packet → Packet 검증 → Planner Request
      → LLM plan_monthly → L5 Deterministic Validation
      → (repairable이면 1회 repair) → 검증된 Proposal

Use Case 안에 이 흐름을 펼쳐 놓지 않은 이유: Generate가 이미 12단계이고,
여기에 6단계를 더 끼우면 Gate와 Planner 실패가 한 함수에서 섞인다.

**조용한 Rule-only fallback을 만들지 않는다.** 어느 단계에서 실패하든 예외가
호출자에게 그대로 간다(OD-N15). 실패했는데 Plan이 만들어지는 경로는 없다.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ...shared.llm.monthly import MonthlyPlanProposal
from ..context.budget import packet_fingerprint
from ..context.builder import MonthlyContextPacketBuilder, MonthlyContextRequest
from ..context.models import MonthlyContextPacket
from ..context.validation import validate_packet
from ..domain.activity_reference import ActivityCatalog
from ..domain.errors import FailureCategory, validation_failed
from ..domain.identifiers import PeriodKey
from ..domain.parent_lineage import ParentYearlyLineage
from ..planner.prompt import PROMPT_VERSION, build_monthly_planner_request
from ..rules.monthly_llm_validation import (
    MonthlyProposalValidationResult,
    validate_monthly_proposal,
)

__all__ = [
    "MAX_VALIDATION_REPAIR_ATTEMPTS",
    "MonthlyLlmPlanner",
    "MonthlyPlannerOutcome",
]

MAX_VALIDATION_REPAIR_ATTEMPTS = 1
"""L5 Product-safety 위반에 대한 재요청 횟수.

L4 Adapter 안의 **구조 repair**(`MAX_REPAIR_ATTEMPTS`)와 다른 층이다.

    L4 contract repair   Theme/Week/origin 계약이 깨졌을 때. Adapter 내부
    L5 validation repair 원문 복사·중복·금지 표현 등 제품 안전. 여기

두 번째 cycle을 자동으로 시작하지 않는다. 같은 Packet으로 두 번 고치지 못하면
Prompt나 Packet 쪽 문제이지 우연이 아니다. OD-N04는 계속 OPEN이다.
"""


@dataclass(slots=True)
class MonthlyPlannerOutcome:
    """검증을 통과한 Proposal과 재현에 필요한 metadata."""

    proposal: MonthlyPlanProposal
    packet: MonthlyContextPacket
    validation: MonthlyProposalValidationResult

    planner_model: str
    prompt_version: str
    packet_fingerprint: str

    provider_call_count: int = 0
    validation_repair_count: int = 0
    rejected_violation_codes: tuple[str, ...] = field(default_factory=tuple)
    """repair 전에 걸렸던 위반 code. 성공해도 무엇을 고쳐 왔는지 남긴다."""

    @property
    def evidence_store_sha256(self) -> str:
        return self.packet.source_lineage.evidence_store_content_sha256


class MonthlyLlmPlanner:
    """Retrieval → Packet → LLM → Validator를 한 번에 수행한다."""

    def __init__(
        self,
        *,
        context_builder: MonthlyContextPacketBuilder,
        llm,
        planner_model: str,
        activity_catalog: ActivityCatalog | None = None,
    ) -> None:
        """Args:
        llm: `LLMPort` 구현. `plan_monthly`를 호출한다.
        planner_model: Provenance에 기록할 실제 모델 문자열. 비어 있으면
            L5가 `PROVENANCE_INCOMPLETE`로 막는다 — 조용히 통과시키지 않는다.
        """
        self._builder = context_builder
        self._llm = llm
        self._model = planner_model
        self._catalog = activity_catalog

    def plan(
        self,
        *,
        school_year: int,
        target_month: PeriodKey,
        classroom_ages: tuple[int, ...],
        age_mode: str,
        lineage: ParentYearlyLineage,
        daycare_ref: str | None = None,
        classroom_ref: str | None = None,
    ) -> MonthlyPlannerOutcome:
        """검증을 통과한 Proposal을 돌려준다. 실패하면 예외를 올린다.

        Raises:
            PlanningError: Packet이 스스로 모순이거나 Proposal이 검증을
                통과하지 못한 경우.
            LLMUnavailableError / LLMConfigurationError: Adapter가 올린다.
        """
        packet = self._builder.build(
            MonthlyContextRequest(
                school_year=str(school_year),
                target_month=target_month,
                classroom_ages=tuple(classroom_ages),
                age_mode=age_mode,
                parent_lineage=lineage,
                daycare_ref=daycare_ref,
                classroom_ref=classroom_ref,
            )
        )
        self._require_sound_packet(packet)

        request = build_monthly_planner_request(packet)
        fingerprint = packet_fingerprint(packet)

        calls = 0
        repairs = 0
        first_codes: tuple[str, ...] = ()

        proposal = self._llm.plan_monthly(request)
        calls += 1
        validation = self._validate(proposal, packet, request)

        if not validation.is_valid:
            first_codes = tuple(c.value for c in validation.codes)

            if not validation.is_repairable:
                # Context·Packet·설정 문제다. 같은 Packet으로 다시 물어봐야
                # 같은 답이 온다. 호출을 낭비하지 않는다.
                raise self._rejected(validation, repaired=False)

            for _ in range(MAX_VALIDATION_REPAIR_ATTEMPTS):
                repairs += 1
                proposal = self._llm.plan_monthly(
                    self._repair_request(request, validation)
                )
                calls += 1
                validation = self._validate(proposal, packet, request)
                if validation.is_valid:
                    break

            if not validation.is_valid:
                raise self._rejected(validation, repaired=True)

        return MonthlyPlannerOutcome(
            proposal=proposal,
            packet=packet,
            validation=validation,
            planner_model=self._model,
            prompt_version=PROMPT_VERSION,
            packet_fingerprint=fingerprint,
            provider_call_count=calls,
            validation_repair_count=repairs,
            rejected_violation_codes=first_codes,
        )

    # ------------------------------------------------------------ 내부

    def _validate(self, proposal, packet, request):
        return validate_monthly_proposal(
            proposal, packet, request, planner_model=self._model
        )

    @staticmethod
    def _repair_request(request, validation):
        """같은 Packet으로 다시 묻는다. **Retrieval을 되풀이하지 않는다.**

        Context가 바뀌면 무엇 때문에 고쳐졌는지 알 수 없고, Retrieval 비용도
        두 번 든다. 원래 본문에 **범주 수준 수정 요청**만 덧붙인다 —
        위반한 Source 문장을 다시 노출하지 않는다(L5 §28).
        """
        import dataclasses

        notes = "\n".join(f"- {hint}" for hint in validation.repair_summary)
        return dataclasses.replace(
            request,
            user_content=(
                f"{request.user_content}\n\n"
                "# 직전 응답이 보육계획안 규칙을 위반했습니다\n"
                f"{notes}\n"
                "위 내용을 고쳐 같은 형식으로 다시 반환하세요."
            ),
        )

    @staticmethod
    def _require_sound_packet(packet: MonthlyContextPacket) -> None:
        from ..context.validation import ContextPacketError

        try:
            validate_packet(packet)
        except ContextPacketError as exc:
            raise validation_failed(
                "monthly_llm_context_packet_invalid",
                FailureCategory.STRUCTURE_VALIDATION,
                f"Monthly Context Packet이 스스로 모순된다: {exc}",
            ) from exc

    @staticmethod
    def _rejected(validation, *, repaired: bool):
        """Validator 거부를 Application 오류로 바꾼다.

        내부 Violation code를 공개 오류 코드로 승격하지 않는다. 사용자에게
        나가는 것은 Application 실패 하나이며, 어떤 위반이었는지는 detail에
        식별자로만 남는다(CLAUDE.md §20).
        """
        codes = ", ".join(c.value for c in validation.codes)
        where = "repair 후에도" if repaired else "초기 응답에서"
        return validation_failed(
            "monthly_llm_proposal_must_pass_deterministic_validation",
            FailureCategory.LLM_OUTPUT_VALIDATION,
            f"LLM Monthly Proposal이 {where} 검증을 통과하지 못했다: {codes}",
        )
