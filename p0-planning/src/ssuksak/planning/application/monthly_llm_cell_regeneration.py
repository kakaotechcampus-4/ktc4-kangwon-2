"""Monthly Cell Regenerate 오케스트레이션 (L7).

    현재 Plan snapshot + Retrieval Packet
      → Cell Regeneration Request (한 달 전체를 보여주고 Target 하나를 지정)
      → llm.regenerate_monthly_cell()
      → L7 Cell Validator
      → (repairable이면 1회 repair) → 검증된 Cell 제안

L6 `MonthlyLlmPlanner`와 같은 구조·같은 repair 정책을 쓴다. 새 정책을 만들지
않았다(§22).

**조용한 fallback이 없다.** 실패하면 예외가 호출자에게 가고 Cell은 그대로다.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ...shared.llm.monthly_cell import (
    FOCUS_SECTION_KEY,
    OUTDOOR_SECTION_KEY,
    MonthlyCellRegenerationProposal,
)
from ..context.budget import packet_fingerprint
from ..context.builder import MonthlyContextPacketBuilder, MonthlyContextRequest
from ..context.models import MonthlyContextPacket
from ..context.validation import ContextPacketError, validate_packet
from ..domain.errors import FailureCategory, validation_failed
from ..domain.identifiers import PeriodKey
from ..domain.parent_lineage import ParentYearlyLineage
from ..planner.cell_prompt import (
    CELL_PROMPT_VERSION,
    build_cell_regeneration_request,
)
from ..rules.monthly_llm_cell_validation import SiblingCell, validate_cell_proposal
from ..rules.monthly_llm_validation import MonthlyProposalValidationResult

__all__ = [
    "MAX_CELL_VALIDATION_REPAIR_ATTEMPTS",
    "MonthlyCellRegenerationOutcome",
    "MonthlyLlmCellRegenerator",
    "build_month_snapshot",
    "month_snapshot_fingerprint",
]

MAX_CELL_VALIDATION_REPAIR_ATTEMPTS = 1
"""L6 `MAX_VALIDATION_REPAIR_ATTEMPTS`와 같은 값·같은 의미다.

새 repair 정책을 만들지 않았다(§22). OD-N04는 계속 OPEN이다.
"""


@dataclass(slots=True)
class MonthlyCellRegenerationOutcome:
    """검증을 통과한 Cell 제안과 재현에 필요한 metadata."""

    proposal: MonthlyCellRegenerationProposal
    packet: MonthlyContextPacket
    validation: MonthlyProposalValidationResult

    planner_model: str
    prompt_version: str
    packet_fingerprint: str

    provider_call_count: int = 0
    validation_repair_count: int = 0
    rejected_violation_codes: tuple[str, ...] = field(default_factory=tuple)
    plan_snapshot_fingerprint: str = ""

    @property
    def evidence_store_sha256(self) -> str:
        return self.packet.source_lineage.evidence_store_content_sha256

    @property
    def grounding_source_ids(self) -> tuple[str, ...]:
        return self.validation.provenance[0].grounding_source_ids


class MonthlyLlmCellRegenerator:
    """Retrieval → Packet → LLM → Cell Validator를 한 번에 수행한다."""

    def __init__(
        self,
        *,
        context_builder: MonthlyContextPacketBuilder,
        llm,
        planner_model: str,
    ) -> None:
        self._builder = context_builder
        self._llm = llm
        self._model = planner_model

    def regenerate(
        self,
        *,
        school_year: int,
        target_month: PeriodKey,
        classroom_ages: tuple[int, ...],
        age_mode: str,
        lineage: ParentYearlyLineage,
        target_week_id: str,
        target_section_key: str,
        month_snapshot: tuple[tuple[str, str, str], ...],
        siblings: tuple[SiblingCell, ...],
        daycare_ref: str | None = None,
        classroom_ref: str | None = None,
        plan_snapshot_fingerprint: str = "",
    ) -> MonthlyCellRegenerationOutcome:
        """검증을 통과한 Cell 제안을 돌려준다. 실패하면 예외를 올린다.

        Retrieval은 **현재 Plan의 월·연령·확정 Theme** 기준으로만 수행한다.
        다른 월이나 다른 Theme으로 벗어나지 않는다(§21).
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
        try:
            validate_packet(packet)
        except ContextPacketError as exc:
            raise validation_failed(
                "monthly_llm_context_packet_invalid",
                FailureCategory.STRUCTURE_VALIDATION,
                f"Monthly Context Packet이 스스로 모순된다: {exc}",
            ) from exc

        request = build_cell_regeneration_request(
            packet,
            target_week_id=target_week_id,
            target_section_key=target_section_key,
            month_snapshot=month_snapshot,
            plan_snapshot_fingerprint=(
                plan_snapshot_fingerprint
                or month_snapshot_fingerprint(month_snapshot)
            ),
        )

        calls = 0
        repairs = 0
        first_codes: tuple[str, ...] = ()

        proposal = self._llm.regenerate_monthly_cell(request)
        calls += 1
        validation = self._validate(proposal, packet, request, siblings)

        if not validation.is_valid:
            first_codes = tuple(c.value for c in validation.codes)

            if not validation.is_repairable:
                # Context·Packet·설정 문제다. 다시 물어봐야 같은 답이 온다.
                raise self._rejected(validation, repaired=False)

            for _ in range(MAX_CELL_VALIDATION_REPAIR_ATTEMPTS):
                repairs += 1
                proposal = self._llm.regenerate_monthly_cell(
                    self._repair_request(request, validation)
                )
                calls += 1
                validation = self._validate(proposal, packet, request, siblings)
                if validation.is_valid:
                    break

            if not validation.is_valid:
                raise self._rejected(validation, repaired=True)

        return MonthlyCellRegenerationOutcome(
            proposal=proposal,
            packet=packet,
            validation=validation,
            planner_model=self._model,
            prompt_version=CELL_PROMPT_VERSION,
            packet_fingerprint=packet_fingerprint(packet),
            provider_call_count=calls,
            validation_repair_count=repairs,
            rejected_violation_codes=first_codes,
            plan_snapshot_fingerprint=request.plan_snapshot_fingerprint,
        )

    # ------------------------------------------------------------ 내부

    def _validate(self, proposal, packet, request, siblings):
        return validate_cell_proposal(
            proposal,
            packet,
            request,
            siblings=siblings,
            planner_model=self._model,
        )

    @staticmethod
    def _repair_request(request, validation):
        """같은 Packet·같은 snapshot으로 다시 묻는다. Retrieval을 되풀이하지 않는다."""
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
    def _rejected(validation, *, repaired: bool):
        codes = ", ".join(c.value for c in validation.codes)
        where = "repair 후에도" if repaired else "초기 응답에서"
        return validation_failed(
            "monthly_llm_cell_proposal_must_pass_deterministic_validation",
            FailureCategory.LLM_OUTPUT_VALIDATION,
            f"재생성된 Cell이 {where} 검증을 통과하지 못했다: {codes}",
        )


def month_snapshot_fingerprint(
    snapshot: tuple[tuple[str, str, str], ...]
) -> str:
    """요청이 **어떤 Plan 상태**를 보고 만들어졌는지 나타내는 값.

    새 동시성 제어 장치를 만들지 않았다(§33). Domain에 revision도
    `updated_at`도 없고 L7에서 그것을 도입하는 것은 과한 범위다.

    다만 LLM 호출 중에 다른 Teacher Edit가 들어오면 오래된 Context로 만든 값이
    저장될 수 있다. 그 위험을 **관측 가능하게** 두려고 요청에 이 값을 실어
    telemetry에 남긴다. 막지는 못하고 나중에 알아볼 수는 있다.
    """
    import hashlib
    import json

    blob = json.dumps(snapshot, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def build_month_snapshot(
    plan, *, focus_key: str = FOCUS_SECTION_KEY, outdoor_key: str = OUTDOOR_SECTION_KEY
) -> tuple[tuple[str, str, str], ...]:
    """`(week_id, focus 값, outdoor 값)` 순서열.

    canonical WeekPeriod 순서를 따른다. Cell이 없으면 빈 문자열이다.
    """
    by_section: dict[str, dict[str, str]] = {}
    for section in plan.sections:
        if section.section_key not in (focus_key, outdoor_key):
            continue
        by_section[section.section_key] = {
            item.week_id.value: item.value
            for item in section.items
            if item.week_id is not None
        }
    return tuple(
        (
            period.week_id.value,
            by_section.get(focus_key, {}).get(period.week_id.value, ""),
            by_section.get(outdoor_key, {}).get(period.week_id.value, ""),
        )
        for period in plan.week_periods
        if period.active
    )
