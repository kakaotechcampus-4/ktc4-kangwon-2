"""Immutable requests and proposals for Monthly LLM planning.

These values deliberately stop before ``MonthlyPlan`` persistence. PR5 owns a
proposal boundary; a later application slice decides how a validated proposal
becomes domain cells and audit history.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import re

from ..domain.errors import DomainError, InvalidDomainValueError

MONTHLY_PROMPT_VERSION = "monthly-planner-v1"
MONTHLY_CELL_PROMPT_VERSION = "monthly-cell-planner-v1"
MONTHLY_MODEL = "openai/gpt-4.1-mini"

FOCUS_SECTION_KEY = "focus"
OUTDOOR_SECTION_KEY = "outdoor_play"
LLM_CELL_SECTION_KEYS = frozenset({FOCUS_SECTION_KEY, OUTDOOR_SECTION_KEY})


def _require_text(name: str, value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise InvalidDomainValueError(f"{name} must be a non-blank string")


def _require_sha256(name: str, value: str) -> None:
    if re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise InvalidDomainValueError(f"{name} must be a lowercase SHA-256")


def _require_reference_labels(
    name: str, values: tuple[tuple[str, str], ...]
) -> None:
    if not isinstance(values, tuple) or any(
        not isinstance(item, tuple)
        or len(item) != 2
        or not all(isinstance(value, str) and value.strip() for value in item)
        for item in values
    ):
        raise InvalidDomainValueError(
            f"{name} must contain non-blank (id, label) pairs"
        )
    if len({key for key, _ in values}) != len(values):
        raise InvalidDomainValueError(f"{name} ids must be unique")


def _require_grounding_refs(name: str, values: frozenset[str]) -> None:
    if not isinstance(values, frozenset) or any(
        not isinstance(value, str) or not value.strip() for value in values
    ):
        raise InvalidDomainValueError(
            f"{name} must be a frozenset of non-blank strings"
        )


class ProposedActivityOrigin(str, Enum):
    REFERENCE = "REFERENCE"
    LLM_SYNTHESIZED = "LLM_SYNTHESIZED"


@dataclass(frozen=True, slots=True)
class MonthlyPlanningRequest:
    task: str
    prompt_version: str
    system_prompt: str
    user_content: str
    target_month: str
    expected_theme_id: str
    expected_week_ids: tuple[str, ...]
    reference_labels: tuple[tuple[str, str], ...] = ()
    valid_grounding_refs: frozenset[str] = frozenset()
    packet_fingerprint: str = ""

    def __post_init__(self) -> None:
        for name in (
            "task",
            "prompt_version",
            "system_prompt",
            "user_content",
            "target_month",
            "expected_theme_id",
        ):
            _require_text(f"MonthlyPlanningRequest.{name}", getattr(self, name))
        if not isinstance(self.expected_week_ids, tuple) or not self.expected_week_ids or any(
            not isinstance(value, str) or not value.strip()
            for value in self.expected_week_ids
        ):
            raise InvalidDomainValueError("MonthlyPlanningRequest requires week ids")
        if len(set(self.expected_week_ids)) != len(self.expected_week_ids):
            raise InvalidDomainValueError("MonthlyPlanningRequest week ids must be unique")
        _require_reference_labels(
            "MonthlyPlanningRequest.reference_labels", self.reference_labels
        )
        _require_grounding_refs(
            "MonthlyPlanningRequest.valid_grounding_refs",
            self.valid_grounding_refs,
        )
        _require_sha256("MonthlyPlanningRequest.packet_fingerprint", self.packet_fingerprint)

    @property
    def reference_label_map(self) -> dict[str, str]:
        return dict(self.reference_labels)


@dataclass(frozen=True, slots=True)
class MonthlyCellSnapshot:
    week_id: str
    focus: str
    outdoor_play: str

    def __post_init__(self) -> None:
        _require_text("MonthlyCellSnapshot.week_id", self.week_id)
        if not isinstance(self.focus, str) or not isinstance(self.outdoor_play, str):
            raise InvalidDomainValueError("MonthlyCellSnapshot values must be strings")


@dataclass(frozen=True, slots=True)
class MonthlyCellPlanningRequest:
    task: str
    prompt_version: str
    system_prompt: str
    user_content: str
    target_month: str
    target_week_id: str
    target_section_key: str
    expected_theme_id: str
    reference_labels: tuple[tuple[str, str], ...] = ()
    valid_grounding_refs: frozenset[str] = frozenset()
    packet_fingerprint: str = ""
    plan_snapshot_fingerprint: str = ""

    def __post_init__(self) -> None:
        for name in (
            "task",
            "prompt_version",
            "system_prompt",
            "user_content",
            "target_month",
            "target_week_id",
            "target_section_key",
            "expected_theme_id",
        ):
            _require_text(f"MonthlyCellPlanningRequest.{name}", getattr(self, name))
        if self.target_section_key not in LLM_CELL_SECTION_KEYS:
            raise InvalidDomainValueError(
                f"LLM cannot plan section {self.target_section_key!r}"
            )
        _require_reference_labels(
            "MonthlyCellPlanningRequest.reference_labels", self.reference_labels
        )
        _require_grounding_refs(
            "MonthlyCellPlanningRequest.valid_grounding_refs",
            self.valid_grounding_refs,
        )
        _require_sha256("MonthlyCellPlanningRequest.packet_fingerprint", self.packet_fingerprint)
        _require_sha256(
            "MonthlyCellPlanningRequest.plan_snapshot_fingerprint",
            self.plan_snapshot_fingerprint,
        )

    @property
    def reference_label_map(self) -> dict[str, str]:
        return dict(self.reference_labels)


@dataclass(frozen=True, slots=True)
class RawLlmResponse:
    content: str
    model: str
    request_id: str | None = None

    def __post_init__(self) -> None:
        _require_text("RawLlmResponse.content", self.content)
        _require_text("RawLlmResponse.model", self.model)
        if self.request_id is not None:
            _require_text("RawLlmResponse.request_id", self.request_id)


@dataclass(frozen=True, slots=True)
class ProposedActivity:
    value: str
    origin: ProposedActivityOrigin
    reference_activity_id: str | None
    grounding_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_text("ProposedActivity.value", self.value)
        if not isinstance(self.origin, ProposedActivityOrigin):
            raise InvalidDomainValueError("ProposedActivity.origin is invalid")
        if self.reference_activity_id is not None:
            _require_text(
                "ProposedActivity.reference_activity_id",
                self.reference_activity_id,
            )
        if not isinstance(self.grounding_refs, tuple) or any(
            not isinstance(value, str) or not value.strip()
            for value in self.grounding_refs
        ):
            raise InvalidDomainValueError(
                "ProposedActivity.grounding_refs must contain non-blank strings"
            )
        if len(set(self.grounding_refs)) != len(self.grounding_refs):
            raise InvalidDomainValueError(
                "ProposedActivity.grounding_refs must be unique"
            )


@dataclass(frozen=True, slots=True)
class ProposedWeek:
    week_id: str
    experience: str
    activity: ProposedActivity

    def __post_init__(self) -> None:
        _require_text("ProposedWeek.week_id", self.week_id)
        _require_text("ProposedWeek.experience", self.experience)
        if not isinstance(self.activity, ProposedActivity):
            raise InvalidDomainValueError("ProposedWeek.activity is invalid")


@dataclass(frozen=True, slots=True)
class MonthlyPlanProposal:
    target_month: str
    theme_id: str
    month_flow_rationale: str
    weeks: tuple[ProposedWeek, ...]

    def __post_init__(self) -> None:
        for name in ("target_month", "theme_id", "month_flow_rationale"):
            _require_text(f"MonthlyPlanProposal.{name}", getattr(self, name))
        if not self.weeks or not all(
            isinstance(value, ProposedWeek) for value in self.weeks
        ):
            raise InvalidDomainValueError("MonthlyPlanProposal requires ProposedWeek values")


@dataclass(frozen=True, slots=True)
class MonthlyCellProposal:
    target_month: str
    target_week_id: str
    target_section_key: str
    value: str
    activity_origin: ProposedActivityOrigin | None
    reference_activity_id: str | None
    grounding_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        for name in ("target_month", "target_week_id", "target_section_key", "value"):
            _require_text(f"MonthlyCellProposal.{name}", getattr(self, name))
        if self.activity_origin is not None and not isinstance(
            self.activity_origin, ProposedActivityOrigin
        ):
            raise InvalidDomainValueError("MonthlyCellProposal.activity_origin is invalid")
        if self.reference_activity_id is not None:
            _require_text(
                "MonthlyCellProposal.reference_activity_id",
                self.reference_activity_id,
            )
        if not isinstance(self.grounding_refs, tuple) or any(
            not isinstance(value, str) or not value.strip()
            for value in self.grounding_refs
        ):
            raise InvalidDomainValueError(
                "MonthlyCellProposal.grounding_refs must contain non-blank strings"
            )
        if len(set(self.grounding_refs)) != len(self.grounding_refs):
            raise InvalidDomainValueError(
                "MonthlyCellProposal.grounding_refs must be unique"
            )


class ProposalParseError(DomainError, ValueError):
    """A provider response cannot be decoded as the strict proposal contract."""


class ProposalRejectedError(DomainError):
    """A parsed proposal failed deterministic validation."""

    def __init__(self, violation_codes: tuple[str, ...]) -> None:
        self.violation_codes = violation_codes
        super().__init__("Monthly proposal rejected: " + ", ".join(violation_codes))


@dataclass(frozen=True, slots=True)
class MonthlyPlanningOutcome:
    proposal: MonthlyPlanProposal
    model: str
    prompt_version: str
    packet_fingerprint: str
    request_id: str | None = None


@dataclass(frozen=True, slots=True)
class MonthlyCellPlanningOutcome:
    proposal: MonthlyCellProposal
    model: str
    prompt_version: str
    packet_fingerprint: str
    plan_snapshot_fingerprint: str
    request_id: str | None = None
