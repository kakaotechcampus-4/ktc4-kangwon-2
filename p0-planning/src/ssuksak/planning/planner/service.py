"""Context Packet -> provider -> parsed and validated Monthly proposal."""

from __future__ import annotations

from ... import timing
import logging

from ..context.models import MonthlyContextPacket
from ..domain.monthly_template_snapshot import TemplateSnapshot
from ..venue_policy import venue_name_only_repair
from .contracts import (
    is_compatible_monthly_model,
    MonthlyPlanningOutcome,
    MonthlyPlanningRequest,
    ProposalRejectedError,
)
from .parser import parse_monthly_proposal, parse_repair_patches
from .ports import MonthlyPlanningProvider
from .teacher_memo import split_memo_applied, split_safety_requests
from .prompt import build_monthly_planning_request, build_monthly_repair_request
from .validation import (
    MonthlyProposalValidationResult,
    canonicalize_reference_labels,
    changed_reference_ids,
    hydrate_reference_values,
    merge_repair_patches,
    repair_targets,
    sanitize_activity_details,
    validate_monthly_proposal,
)

_log = logging.getLogger(__name__)

# OD-N04: content findings a single repair generation may fix. Anything else
# (model, parse, structure, placement, AXIS, theme, unknown refs) fails closed.
# SAFETY_GROUNDING_MISMATCH is a ref choice inside a fixed slot, like
# WRONG_SOURCE_GROUNDING; SAFETY_PLACEMENT_MISMATCH changes the slot and fails closed.
# Safety focus/quality findings are re-selection or rewriting inside the same slot.
# REFERENCE_VALUE_MISMATCH is repaired deterministically, never by the LLM: same
# reference_id, value := its canonical label; if that label is unknown it fails closed.
# An LLM repair that changes or drops that reference_id is rejected.
REPAIRABLE_CODES = frozenset(
    {
        "SOURCE_TEXT_COPY", "TEXT_POLICY", "WRONG_SOURCE_GROUNDING", "SAFETY_GROUNDING_MISMATCH",
        "SAFETY_FOCUS_MISMATCH", "SAFETY_MULTIPLE_SENTENCES", "SAFETY_DUPLICATE_CONTENT", "SAFETY_DUPLICATE_REFERENCE",
        "REFERENCE_VALUE_MISMATCH",
        "INDOOR_ALTERNATIVE_REQUIRED",
    }
)


def finding_summary(issues) -> str:
    """Code, location and stable reason per finding; no generated or evidence text."""
    return "; ".join(
        f"{issue.code.value}@{issue.week_id or 'month'}/{issue.field}"
        + (f" reason={issue.reason}" if issue.reason else "")
        + (f" expected={issue.expected}" if issue.expected else "")
        + (f" actual={issue.actual}" if issue.actual else "")
        for issue in issues
    )


class MonthlyPlanner:
    def __init__(self, provider: MonthlyPlanningProvider) -> None:
        self._provider = provider

    def plan(
        self, packet: MonthlyContextPacket, snapshot: TemplateSnapshot
    ) -> MonthlyPlanningOutcome:
        timing.phase("prompt")
        request = build_monthly_planning_request(packet, snapshot)
        initial_prompt_version, repaired_cells = request.prompt_version, frozenset()
        response = self._generate(request)
        timing.phase("validate")
        content, memo_applied, memo_skipped = split_memo_applied(response.content, request.memo_addresses)
        content, safety_requests = split_safety_requests(
            content, request.safety_request_slots, tuple(w.value for w in request.expected_week_ids)
        )
        # The schema pairs each reference id with its label; hydration re-asserts that pair.
        content, _ = hydrate_reference_values(content, request)
        proposal = parse_monthly_proposal(content)
        validation = validate_monthly_proposal(proposal, packet, request)
        found = validation.issues
        if not validation.is_valid and set(validation.codes) <= REPAIRABLE_CODES:
            # Deterministic step first; it is no provider call.
            content, fixed = canonicalize_reference_labels(content, validation.issues, request)
            if fixed:
                _log.info("Monthly deterministic repair applied: %s", finding_summary(fixed))
                proposal = parse_monthly_proposal(content)
                validation = validate_monthly_proposal(proposal, packet, request)
        if (
            not validation.is_valid
            and set(validation.codes) <= REPAIRABLE_CODES
            and "REFERENCE_VALUE_MISMATCH" not in validation.codes  # label unknown: fail closed
            and repair_targets(validation.issues)
        ):
            # At most one LLM repair call: 2 provider calls in total, never 3.
            _log.info("Monthly LLM repair attempted: %s", finding_summary(validation.issues))
            timing.phase("repair")
            request = build_monthly_repair_request(request, content, validation.issues)
            rejected = proposal
            try:
                response = self._generate(request)
                patches = parse_repair_patches(response.content)  # a malformed repair still fails closed
            except Exception:
                _log.warning("Monthly LLM repair failed before validation")
                raise
            # The repair returns patches for its targets only; each patch is applied whole
            # or rejected whole by the merge.
            content, applied, ignored = merge_repair_patches(content, patches, request.repair_targets)
            repaired_cells = frozenset(applied)
            if ignored:
                _log.info(
                    "Monthly LLM repair rejected unauthorized patches: %s",
                    "; ".join(
                        f"REPAIR_PATCH_REJECTED@{week or 'month'}/{section} fields={','.join(fields)}"
                        for week, section, fields in ignored
                    ),
                )
            content, _ = hydrate_reference_values(content, request)
            proposal = parse_monthly_proposal(content)
            validation = MonthlyProposalValidationResult(
                validate_monthly_proposal(proposal, packet, request).issues
                + changed_reference_ids(rejected, proposal, found)
            )
            if any(issue.detail == "UNREQUESTED_VENUE" for issue in found) and venue_name_only_repair(rejected, proposal):
                raise ProposalRejectedError(("VENUE_NAME_ONLY_REMOVAL",))
            if validation.is_valid:
                _log.info("Monthly LLM repair succeeded")
            else:
                _log.warning("Monthly LLM repair failed: %s", finding_summary(validation.issues))
        if not validation.is_valid:
            if not request.repair_targets:
                _log.warning("Monthly LLM proposal rejected: %s", finding_summary(validation.issues))
            raise ProposalRejectedError(validation.codes, validation.issues)
        return MonthlyPlanningOutcome(
            proposal=sanitize_activity_details(proposal, packet, request),
            model=response.model,
            prompt_version=request.prompt_version,
            packet_fingerprint=request.packet_fingerprint,
            request_id=response.request_id,
            initial_prompt_version=initial_prompt_version,
            repaired_cells=repaired_cells,
            memo_applied=memo_applied,
            memo_skipped=memo_skipped,
            safety_requests=safety_requests,
        )

    def _generate(self, request: MonthlyPlanningRequest):
        response = self._provider.generate_monthly(request)
        if not is_compatible_monthly_model(response.model):
            raise ProposalRejectedError(("UNEXPECTED_MODEL",))
        return response
