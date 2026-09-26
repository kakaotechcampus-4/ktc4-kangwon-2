"""Immutable requests and proposals for Monthly LLM planning.

These values form the single provider-neutral proposal boundary consumed by
Monthly planning and cell-regeneration application flows.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import re

from ..domain.errors import DomainError, InvalidDomainValueError
from ..domain.monthly_template import DisplayMode, SectionRole, TemplateSection
from ..domain.monthly_template_profile import (
    INSTITUTION_INPUT_SECTION_KEYS,
    TEMPLATE_SPECIFIC_PROFILE_SECTION_KEYS,
)
from ..domain.monthly_template_snapshot import TemplateSnapshot
from ..domain.week_period import WeekId
from ..domain.year_month import YearMonth

MONTHLY_PROMPT_VERSION = "monthly-planner-v11"
MONTHLY_CELL_PROMPT_VERSION = "monthly-cell-planner-v9"
# Embeds prompt.SYSTEM_PROMPT; bump it whenever that prompt changes.
MONTHLY_REPAIR_PROMPT_VERSION = "monthly-planner-repair-v7"
# Used instead of the two above when the Context Packet carries safety placement.
MONTHLY_SAFETY_PROMPT_VERSION = "monthly-planner-safety-v7"
MONTHLY_SAFETY_REPAIR_PROMPT_VERSION = "monthly-planner-safety-repair-v8"
MONTHLY_MODEL = "openai/gpt-4.1-mini"
# Providers may report the requested family without the vendor prefix, or the
# dated snapshot they resolved it to (e.g. "gpt-4.1-mini-2025-04-14").
_MONTHLY_MODEL_SNAPSHOT = re.compile(
    re.escape(MONTHLY_MODEL.rsplit("/", 1)[-1]) + r"(?:-(\d{4}-\d{2}-\d{2}))?"
)


def is_compatible_monthly_model(observed: object) -> bool:
    """True when a provider-reported model id is MONTHLY_MODEL or its dated snapshot."""
    if not isinstance(observed, str):
        return False
    if observed == MONTHLY_MODEL:
        return True
    match = _MONTHLY_MODEL_SNAPSHOT.fullmatch(observed)
    if match is None:
        return False
    if match.group(1) is None:
        return True
    try:
        date.fromisoformat(match.group(1))
    except ValueError:
        return False
    return True



def generation_target_sections(snapshot: TemplateSnapshot) -> tuple[TemplateSection, ...]:
    """Snapshot Sections the LLM writes values for.

    AXIS Sections (week_axis) only shape the weeks, institution-input Sections are
    never invented, and Template-specific Sections have no approved generation
    policy. They all stay in the Snapshot; they are just not generation targets.
    """
    excluded = INSTITUTION_INPUT_SECTION_KEYS | TEMPLATE_SPECIFIC_PROFILE_SECTION_KEYS
    return tuple(
        section
        for section in snapshot.sections
        if section.role is SectionRole.CONTENT and section.section_key not in excluded
    )


FOCUS_SECTION_KEY = "focus"
OUTDOOR_SECTION_KEY = "outdoor_play"
BASIC_HABIT_SECTION_KEY = "basic_habit"
GOALS_SECTION_KEY = "goals"
# Sections whose reference_id may name a supplied Reference item; every other
# section's reference_id is structurally null. theme: the locked parent theme_id
# (Theme Reference). outdoor_play: reference_activities (Activity Catalog; every
# catalog item's placement_slots is outdoor_play).
REFERENCE_CAPABLE_SECTION_KEYS = frozenset({"theme", OUTDOOR_SECTION_KEY})
LLM_CELL_SECTION_KEYS = frozenset(
    {FOCUS_SECTION_KEY, OUTDOOR_SECTION_KEY, BASIC_HABIT_SECTION_KEY, GOALS_SECTION_KEY}
)


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


def _require_allowed_refs(
    name: str,
    values: tuple[tuple[str, tuple[str, ...]], ...],
    valid: frozenset[str],
) -> None:
    if not isinstance(values, tuple) or any(
        not isinstance(item, tuple)
        or len(item) != 2
        or not isinstance(item[0], str)
        or not item[0].strip()
        or not isinstance(item[1], tuple)
        or not set(item[1]) <= valid
        for item in values
    ):
        raise InvalidDomainValueError(
            f"{name} must pair section keys with supplied grounding refs"
        )


def _require_grounding_refs(name: str, values: frozenset[str]) -> None:
    if not isinstance(values, frozenset) or any(
        not isinstance(value, str) or not value.strip() for value in values
    ):
        raise InvalidDomainValueError(
            f"{name} must be a frozenset of non-blank strings"
        )


@dataclass(frozen=True, slots=True)
class ProposedSectionValue:
    """Generated content for one canonical Template section address."""

    section_key: str
    value: str
    unresolved: bool
    grounding_refs: tuple[str, ...] = ()
    reference_id: str | None = None

    def __post_init__(self) -> None:
        _require_text("ProposedSectionValue.section_key", self.section_key)
        if self.section_key == "habits":
            raise InvalidDomainValueError(
                "ProposedSectionValue requires canonical section keys"
            )
        if not isinstance(self.value, str):
            raise InvalidDomainValueError(
                "ProposedSectionValue.value must be a string"
            )
        if type(self.unresolved) is not bool:
            raise InvalidDomainValueError(
                "ProposedSectionValue.unresolved must be a boolean"
            )
        if not isinstance(self.grounding_refs, tuple) or any(
            not isinstance(value, str) or not value.strip()
            for value in self.grounding_refs
        ):
            raise InvalidDomainValueError(
                "ProposedSectionValue.grounding_refs must contain non-blank strings"
            )
        if len(set(self.grounding_refs)) != len(self.grounding_refs):
            raise InvalidDomainValueError(
                "ProposedSectionValue.grounding_refs must be unique"
            )
        if self.reference_id is not None:
            _require_text("ProposedSectionValue.reference_id", self.reference_id)
        if self.unresolved:
            if self.value or self.grounding_refs or self.reference_id is not None:
                raise InvalidDomainValueError(
                    "An unresolved ProposedSectionValue must be empty and ungrounded"
                )
        elif not self.value.strip():
            raise InvalidDomainValueError(
                "A resolved ProposedSectionValue requires a non-blank value"
            )


@dataclass(frozen=True, slots=True)
class ProposedWeek:
    week_id: WeekId
    sections: tuple[ProposedSectionValue, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.week_id, WeekId):
            raise InvalidDomainValueError(
                "ProposedWeek.week_id must be WeekId"
            )
        if not isinstance(self.sections, tuple) or not all(
            isinstance(value, ProposedSectionValue) for value in self.sections
        ):
            raise InvalidDomainValueError(
                "ProposedWeek.sections must contain ProposedSectionValue values"
            )

    def section(self, section_key: str) -> ProposedSectionValue | None:
        return next(
            (value for value in self.sections if value.section_key == section_key),
            None,
        )


@dataclass(frozen=True, slots=True)
class MonthlyPlanProposal:
    target_month: YearMonth
    month_sections: tuple[ProposedSectionValue, ...]
    weeks: tuple[ProposedWeek, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.target_month, YearMonth):
            raise InvalidDomainValueError(
                "MonthlyPlanProposal.target_month must be YearMonth"
            )
        if not isinstance(self.month_sections, tuple) or not all(
            isinstance(value, ProposedSectionValue)
            for value in self.month_sections
        ):
            raise InvalidDomainValueError(
                "MonthlyPlanProposal.month_sections must contain "
                "ProposedSectionValue values"
            )
        if not isinstance(self.weeks, tuple) or not self.weeks or not all(
            isinstance(value, ProposedWeek) for value in self.weeks
        ):
            raise InvalidDomainValueError(
                "MonthlyPlanProposal requires ProposedWeek values"
            )

    def value_for(
        self, section_key: str, week_id: WeekId | None
    ) -> ProposedSectionValue | None:
        if week_id is None:
            return next(
                (
                    value
                    for value in self.month_sections
                    if value.section_key == section_key
                ),
                None,
            )
        week = next((value for value in self.weeks if value.week_id == week_id), None)
        return None if week is None else week.section(section_key)


@dataclass(frozen=True, slots=True)
class MonthlyPlanningRequest:
    task: str
    prompt_version: str
    system_prompt: str
    user_content: str
    target_month: YearMonth
    expected_theme_id: str
    expected_theme_value: str
    expected_week_ids: tuple[WeekId, ...]
    template_snapshot: TemplateSnapshot
    reference_labels: tuple[tuple[str, str], ...] = ()
    valid_grounding_refs: frozenset[str] = frozenset()
    packet_fingerprint: str = ""
    # One entry per LLM generation target of this request, with the supplied refs
    # it may cite (see prompt.generation_targets).
    allowed_grounding_refs_by_section: tuple[tuple[str, tuple[str, ...]], ...] = ()

    def __post_init__(self) -> None:
        for name in (
            "task",
            "prompt_version",
            "system_prompt",
            "user_content",
            "expected_theme_id",
            "expected_theme_value",
        ):
            _require_text(
                f"MonthlyPlanningRequest.{name}", getattr(self, name)
            )
        if not isinstance(self.target_month, YearMonth):
            raise InvalidDomainValueError(
                "MonthlyPlanningRequest.target_month must be YearMonth"
            )
        if (
            not isinstance(self.expected_week_ids, tuple)
            or not self.expected_week_ids
            or not all(isinstance(value, WeekId) for value in self.expected_week_ids)
        ):
            raise InvalidDomainValueError(
                "MonthlyPlanningRequest requires WeekId values"
            )
        if len(set(self.expected_week_ids)) != len(self.expected_week_ids):
            raise InvalidDomainValueError(
                "MonthlyPlanningRequest week ids must be unique"
            )
        if not isinstance(self.template_snapshot, TemplateSnapshot):
            raise InvalidDomainValueError(
                "MonthlyPlanningRequest.template_snapshot must be TemplateSnapshot"
            )
        _require_reference_labels(
            "MonthlyPlanningRequest.reference_labels", self.reference_labels
        )
        _require_grounding_refs(
            "MonthlyPlanningRequest.valid_grounding_refs",
            self.valid_grounding_refs,
        )
        _require_allowed_refs(
            "MonthlyPlanningRequest.allowed_grounding_refs_by_section",
            self.allowed_grounding_refs_by_section,
            self.valid_grounding_refs,
        )
        _require_sha256(
            "MonthlyPlanningRequest.packet_fingerprint",
            self.packet_fingerprint,
        )

    @property
    def reference_label_map(self) -> dict[str, str]:
        return dict(self.reference_labels)

    @property
    def reference_section_keys(self) -> frozenset[str]:
        """REFERENCE_CAPABLE_SECTION_KEYS whose catalog this request actually supplies."""
        return REFERENCE_CAPABLE_SECTION_KEYS - (frozenset() if self.reference_labels else {OUTDOOR_SECTION_KEY})


@dataclass(frozen=True, slots=True)
class MonthlyCellSnapshot:
    week_id: WeekId
    section_values: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        if not isinstance(self.week_id, WeekId):
            raise InvalidDomainValueError(
                "MonthlyCellSnapshot.week_id must be WeekId"
            )
        if not isinstance(self.section_values, tuple) or any(
            not isinstance(item, tuple)
            or len(item) != 2
            or not isinstance(item[0], str)
            or not item[0].strip()
            or not isinstance(item[1], str)
            for item in self.section_values
        ):
            raise InvalidDomainValueError(
                "MonthlyCellSnapshot.section_values must contain "
                "(key, value) pairs"
            )
        keys = tuple(key for key, _ in self.section_values)
        if len(set(keys)) != len(keys):
            raise InvalidDomainValueError(
                "MonthlyCellSnapshot section keys must be unique"
            )


@dataclass(frozen=True, slots=True)
class MonthlyCellPlanningRequest:
    task: str
    prompt_version: str
    system_prompt: str
    user_content: str
    target_month: YearMonth
    target_week_id: WeekId | None
    target_section_key: str
    expected_theme_id: str
    template_snapshot: TemplateSnapshot
    reference_labels: tuple[tuple[str, str], ...] = ()
    valid_grounding_refs: frozenset[str] = frozenset()
    packet_fingerprint: str = ""
    plan_snapshot_fingerprint: str = ""
    allowed_grounding_refs_by_section: tuple[tuple[str, tuple[str, ...]], ...] = ()

    def __post_init__(self) -> None:
        for name in (
            "task",
            "prompt_version",
            "system_prompt",
            "user_content",
            "target_section_key",
            "expected_theme_id",
        ):
            _require_text(
                f"MonthlyCellPlanningRequest.{name}", getattr(self, name)
            )
        if not isinstance(self.target_month, YearMonth):
            raise InvalidDomainValueError(
                "MonthlyCellPlanningRequest.target_month must be YearMonth"
            )
        if self.target_section_key not in LLM_CELL_SECTION_KEYS:
            raise InvalidDomainValueError(
                f"LLM cannot plan section {self.target_section_key!r}"
            )
        if not isinstance(self.template_snapshot, TemplateSnapshot):
            raise InvalidDomainValueError(
                "MonthlyCellPlanningRequest.template_snapshot must be "
                "TemplateSnapshot"
            )
        # The Snapshot placement decides the target address: one cell per week,
        # or the single month-level cell whose week_id is None.
        target_section = self.template_snapshot.section(self.target_section_key)
        placement = None if target_section is None else target_section.display_mode
        if not (
            (
                placement is DisplayMode.WEEKLY_CELLS
                and isinstance(self.target_week_id, WeekId)
            )
            or (
                placement is DisplayMode.MONTHLY_MERGED_SUMMARY
                and self.target_week_id is None
            )
        ):
            raise InvalidDomainValueError(
                "MonthlyCellPlanningRequest.target_week_id must be a WeekId for "
                "a WEEKLY_CELLS target and None for a MONTHLY_MERGED_SUMMARY target"
            )
        _require_reference_labels(
            "MonthlyCellPlanningRequest.reference_labels",
            self.reference_labels,
        )
        _require_grounding_refs(
            "MonthlyCellPlanningRequest.valid_grounding_refs",
            self.valid_grounding_refs,
        )
        _require_allowed_refs(
            "MonthlyCellPlanningRequest.allowed_grounding_refs_by_section",
            self.allowed_grounding_refs_by_section,
            self.valid_grounding_refs,
        )
        _require_sha256(
            "MonthlyCellPlanningRequest.packet_fingerprint",
            self.packet_fingerprint,
        )
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
class MonthlyCellProposal:
    target_month: YearMonth
    target_week_id: WeekId | None
    section: ProposedSectionValue

    def __post_init__(self) -> None:
        if not isinstance(self.target_month, YearMonth):
            raise InvalidDomainValueError(
                "MonthlyCellProposal.target_month must be YearMonth"
            )
        if self.target_week_id is not None and not isinstance(
            self.target_week_id, WeekId
        ):
            raise InvalidDomainValueError(
                "MonthlyCellProposal.target_week_id must be WeekId or None"
            )
        if not isinstance(self.section, ProposedSectionValue):
            raise InvalidDomainValueError(
                "MonthlyCellProposal.section must be ProposedSectionValue"
            )


class ProposalParseError(DomainError, ValueError):
    """A provider response cannot be decoded as the strict proposal contract."""


class ProposalRejectedError(DomainError):
    """A parsed proposal failed structural or grounding validation."""

    def __init__(self, validation_codes: tuple[str, ...], issues: tuple = ()) -> None:
        self.validation_codes = validation_codes
        # ProposalValidationIssue values; content-free locators for diagnostics.
        self.issues = issues
        super().__init__("Monthly proposal rejected: " + ", ".join(validation_codes))


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
