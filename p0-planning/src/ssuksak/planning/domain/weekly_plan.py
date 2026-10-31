"""Immutable structural model for a Weekly Plan (docs/weekly-plan-contract.md §5).

One classroom x one WeekId. A NONE Section holds one Cell; a DAY Section holds
one Cell per operating day (``WeeklyCell.day``), in Template order. The week address and its
Monday-Friday span come from the monthly WeekPeriod unchanged; Saturday is
carried only by ``operating_days`` (contract §3).
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import Enum

from .errors import InvalidDomainValueError, InvalidStateTransitionError
from .identifiers import ActorId, ItemId, PlanId
from .lineage import ParentLineage
from .monthly_constraint import CellState, ConstraintAssessment
from .monthly_plan import ActivityCatalogRef, MonthlyGenerationMode
from .monthly_template import (
    MonthlyTemplate,
    RepeatBy,
    SectionRole,
    TemplateRef,
    TemplateSection,
)
from .monthly_verification import VerificationReport
from .plan import PlanStatus
from .provenance import (
    AuditEvent,
    AuditEventType,
    AuditHistory,
    EvidenceSource,
    GenerationMethod,
    GenerationMethodDetail,
)
from .safety_placement import SafetyPlacement
from .week_period import WeekId, WeekPeriod

# Teacher-input Sections are never generated (contract §6-2). Their Cell starts
# empty with no generation and becomes MANUAL on the first teacher write (§10-2).
WEEKLY_INSTITUTION_INPUT_SECTION_KEYS = frozenset(
    {"family_link", "event_schedule", "special_program"}
)


class OperatingDay(str, Enum):
    MON = "MON"
    TUE = "TUE"
    WED = "WED"
    THU = "THU"
    FRI = "FRI"
    SAT = "SAT"


WEEKDAYS = (
    OperatingDay.MON,
    OperatingDay.TUE,
    OperatingDay.WED,
    OperatingDay.THU,
    OperatingDay.FRI,
)
WEEKDAYS_WITH_SATURDAY = (*WEEKDAYS, OperatingDay.SAT)
# ADR-030 WQ-01: Monday-Friday by default, Saturday by center setting, no Sunday.
SUPPORTED_OPERATING_DAYS = (WEEKDAYS, WEEKDAYS_WITH_SATURDAY)


def _non_blank(value: object, path: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise InvalidDomainValueError(f"{path} must be a non-blank string")


@dataclass(frozen=True, slots=True)
class WeeklyTemplateSnapshot:
    """Template structure captured at generation. Weekly has no TemplateProfile (§5-2)."""

    base_template_ref: TemplateRef
    institution_ref: str
    sections: tuple[TemplateSection, ...]
    classroom_ref: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.base_template_ref, TemplateRef):
            raise InvalidDomainValueError(
                "WeeklyTemplateSnapshot.base_template_ref must be TemplateRef"
            )
        _non_blank(self.institution_ref, "WeeklyTemplateSnapshot.institution_ref")
        if self.classroom_ref is not None:
            _non_blank(self.classroom_ref, "WeeklyTemplateSnapshot.classroom_ref")
        if not isinstance(self.sections, tuple) or not self.sections:
            raise InvalidDomainValueError(
                "WeeklyTemplateSnapshot.sections must be a non-empty tuple"
            )
        if not all(isinstance(section, TemplateSection) for section in self.sections):
            raise InvalidDomainValueError(
                "WeeklyTemplateSnapshot.sections must contain TemplateSection values"
            )
        keys = tuple(section.section_key for section in self.sections)
        if "habits" in keys:
            raise InvalidDomainValueError(
                "WeeklyTemplateSnapshot cannot store the legacy habits alias"
            )
        if len(set(keys)) != len(keys):
            raise InvalidDomainValueError(
                "WeeklyTemplateSnapshot contains duplicate section keys"
            )
        if "theme" not in keys:
            raise InvalidDomainValueError("WeeklyTemplateSnapshot requires theme")
        for section in self.sections:
            if not section.activated:
                raise InvalidDomainValueError(
                    "WeeklyTemplateSnapshot may contain active Sections only"
                )
            if section.role is not SectionRole.CONTENT or section.repeat_by not in (
                RepeatBy.NONE,
                RepeatBy.DAY,
            ):
                raise InvalidDomainValueError(
                    "Weekly Sections must be CONTENT with repeat_by NONE or DAY"
                )
            if section.parent_section_key is not None and section.parent_section_key not in keys:
                raise InvalidDomainValueError(
                    "TemplateSection parent_section_key must resolve in its Snapshot"
                )
        orders = tuple(section.order for section in self.sections)
        if len(set(orders)) != len(orders) or orders != tuple(sorted(orders)):
            raise InvalidDomainValueError(
                "WeeklyTemplateSnapshot.sections must have unique ascending order"
            )

    @classmethod
    def from_template(
        cls,
        template: MonthlyTemplate,
        *,
        institution_ref: str,
        classroom_ref: str | None = None,
    ) -> WeeklyTemplateSnapshot:
        # ponytail: the monthly Template value type is structure-only and reused for
        # the weekly JSON; split a WeeklyTemplate type if their rules ever diverge.
        if not isinstance(template, MonthlyTemplate):
            raise InvalidDomainValueError("from_template requires a parsed Template")
        return cls(
            base_template_ref=template.template_ref,
            institution_ref=institution_ref,
            classroom_ref=classroom_ref,
            sections=template.activated_sections,
        )


@dataclass(frozen=True, slots=True)
class WeeklyCell:
    """One Section value. ``parent_snapshots`` records which parent monthly Cells
    (and their values at the time) this value used (§5-3)."""

    item_id: ItemId
    section_key: str
    value: str
    cell_state: CellState
    generation: GenerationMethodDetail | None = None
    evidence: tuple[EvidenceSource, ...] = ()
    audit: AuditHistory = field(default_factory=AuditHistory)
    parent_snapshots: tuple[ParentLineage, ...] = ()
    source_label: str | None = None
    safety: SafetyPlacement | None = None
    # Set only on a repeat_by DAY Section; (section_key, day) is the semantic address.
    day: OperatingDay | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.item_id, ItemId):
            raise InvalidDomainValueError("WeeklyCell.item_id must be ItemId")
        _non_blank(self.section_key, "WeeklyCell.section_key")
        if self.day is not None and not isinstance(self.day, OperatingDay):
            raise InvalidDomainValueError("WeeklyCell.day must be OperatingDay")
        if not isinstance(self.value, str):
            raise InvalidDomainValueError("WeeklyCell.value must be a string")
        if not isinstance(self.cell_state, CellState):
            raise InvalidDomainValueError("WeeklyCell.cell_state is invalid")
        if bool(self.value.strip()) != (self.cell_state is CellState.FILLED):
            raise InvalidDomainValueError(
                "WeeklyCell FILLED state must match whether value is non-blank"
            )
        teacher_input = self.section_key in WEEKLY_INSTITUTION_INPUT_SECTION_KEYS
        if self.generation is None:
            if self.value.strip() or not teacher_input:
                raise InvalidDomainValueError(
                    "Only an empty teacher-input WeeklyCell may have no generation"
                )
        elif not isinstance(self.generation, GenerationMethodDetail):
            raise InvalidDomainValueError("WeeklyCell.generation is invalid")
        elif teacher_input and self.generation.method is not GenerationMethod.MANUAL:
            raise InvalidDomainValueError(
                "A teacher-input WeeklyCell is never generated; it can only be MANUAL"
            )
        elif not teacher_input and self.generation.method is GenerationMethod.MANUAL:
            # A teacher's edit keeps the generated method (TEACHER_EDITED is audit only).
            raise InvalidDomainValueError(
                "A generated WeeklyCell keeps its generation method; MANUAL is for teacher-input cells only"
            )
        if not isinstance(self.evidence, tuple) or not all(
            isinstance(source, EvidenceSource) for source in self.evidence
        ):
            raise InvalidDomainValueError(
                "WeeklyCell.evidence must contain EvidenceSource values"
            )
        if not isinstance(self.audit, AuditHistory):
            raise InvalidDomainValueError("WeeklyCell.audit must be AuditHistory")
        if not isinstance(self.parent_snapshots, tuple) or not all(
            isinstance(item, ParentLineage) and item.parent_item_id is not None
            for item in self.parent_snapshots
        ):
            raise InvalidDomainValueError(
                "WeeklyCell.parent_snapshots must be item-level ParentLineage values"
            )
        if self.source_label is not None:
            _non_blank(self.source_label, "WeeklyCell.source_label")
        if self.safety is not None and (
            not isinstance(self.safety, SafetyPlacement)
            or self.section_key != "safety_education"
        ):
            raise InvalidDomainValueError(
                "WeeklyCell.safety belongs to the safety_education Cell only"
            )


@dataclass(frozen=True, slots=True)
class WeeklyPlan:
    plan_id: PlanId
    school_year: int
    week_id: WeekId
    week_period: WeekPeriod
    operating_days: tuple[OperatingDay, ...]
    daycare_ref: str
    classroom_ref: str
    target_ages: frozenset[int]
    status: PlanStatus
    parent_lineage: ParentLineage
    template_snapshot: WeeklyTemplateSnapshot
    cells: tuple[WeeklyCell, ...]
    constraint_assessments: tuple[ConstraintAssessment, ...] = ()
    audit: AuditHistory = field(default_factory=AuditHistory)
    activity_catalog_ref: ActivityCatalogRef | None = None
    verification_report: VerificationReport | None = None
    # Same reason as MonthlyPlan: the run record and the response say which path ran.
    generation_mode: MonthlyGenerationMode = MonthlyGenerationMode.RULE_ONLY

    def __post_init__(self) -> None:
        if not isinstance(self.plan_id, PlanId):
            raise InvalidDomainValueError("WeeklyPlan.plan_id must be PlanId")
        if type(self.school_year) is not int or not 1 <= self.school_year <= 9998:
            raise InvalidDomainValueError("WeeklyPlan.school_year must be 1 through 9998")
        if not isinstance(self.week_id, WeekId):
            raise InvalidDomainValueError("WeeklyPlan.week_id must be WeekId")
        month = self.week_id.target_month
        expected_year = self.school_year if month.calendar_month >= 3 else self.school_year + 1
        if month.calendar_year != expected_year:
            raise InvalidDomainValueError("WeeklyPlan.week_id must belong to its school year")
        if not isinstance(self.week_period, WeekPeriod) or self.week_period.week_id != self.week_id:
            raise InvalidDomainValueError("WeeklyPlan.week_period must be the WeekPeriod of week_id")
        if not self.week_period.active:
            raise InvalidDomainValueError("WeeklyPlan.week_period must be an active week")
        if self.operating_days not in SUPPORTED_OPERATING_DAYS:
            raise InvalidDomainValueError(
                "WeeklyPlan.operating_days must be MON-FRI or MON-SAT"
            )
        _non_blank(self.daycare_ref, "WeeklyPlan.daycare_ref")
        _non_blank(self.classroom_ref, "WeeklyPlan.classroom_ref")
        if not isinstance(self.target_ages, frozenset) or not self.target_ages:
            raise InvalidDomainValueError("WeeklyPlan.target_ages must be a non-empty frozenset")
        if any(type(age) is not int or age not in {3, 4, 5} for age in self.target_ages):
            raise InvalidDomainValueError("WeeklyPlan.target_ages supports P0 ages 3, 4, and 5 only")
        if not isinstance(self.status, PlanStatus):
            raise InvalidDomainValueError("WeeklyPlan.status is invalid")
        if not isinstance(self.parent_lineage, ParentLineage) or self.parent_lineage.parent_item_id is not None:
            raise InvalidDomainValueError(
                "WeeklyPlan.parent_lineage must be plan-level ParentLineage of the monthly Plan"
            )
        if not isinstance(self.template_snapshot, WeeklyTemplateSnapshot):
            raise InvalidDomainValueError(
                "WeeklyPlan.template_snapshot must be WeeklyTemplateSnapshot"
            )
        if self.template_snapshot.institution_ref != self.daycare_ref:
            raise InvalidDomainValueError("WeeklyPlan daycare_ref must match its Snapshot scope")
        if self.template_snapshot.classroom_ref not in (None, self.classroom_ref):
            raise InvalidDomainValueError("WeeklyPlan classroom_ref must match its Snapshot scope")
        if not isinstance(self.cells, tuple) or not all(
            isinstance(cell, WeeklyCell) for cell in self.cells
        ):
            raise InvalidDomainValueError("WeeklyPlan.cells must contain WeeklyCell values")
        expected = tuple(
            (section.section_key, day)
            for section in self.template_snapshot.sections
            for day in (
                self.operating_days if section.repeat_by is RepeatBy.DAY else (None,)
            )
        )
        if tuple((cell.section_key, cell.day) for cell in self.cells) != expected:
            raise InvalidDomainValueError(
                "WeeklyPlan needs one Cell per Snapshot Section (per operating day for DAY), "
                "in Section order"
            )
        if len({cell.item_id for cell in self.cells}) != len(self.cells):
            raise InvalidDomainValueError("WeeklyPlan cells must have unique ItemId values")
        if self.cell("theme").cell_state is not CellState.FILLED:
            raise InvalidDomainValueError("WeeklyPlan theme cannot be empty")
        if not isinstance(self.constraint_assessments, tuple) or not all(
            isinstance(item, ConstraintAssessment) for item in self.constraint_assessments
        ):
            raise InvalidDomainValueError("WeeklyPlan.constraint_assessments are invalid")
        codes = tuple(item.constraint.code for item in self.constraint_assessments)
        if len(set(codes)) != len(codes):
            raise InvalidDomainValueError("WeeklyPlan cannot duplicate a constraint assessment")
        if not isinstance(self.audit, AuditHistory):
            raise InvalidDomainValueError("WeeklyPlan.audit must be AuditHistory")
        if self.activity_catalog_ref is not None and not isinstance(
            self.activity_catalog_ref, ActivityCatalogRef
        ):
            raise InvalidDomainValueError(
                "WeeklyPlan.activity_catalog_ref must be ActivityCatalogRef"
            )
        if self.verification_report is not None and (
            not isinstance(self.verification_report, VerificationReport)
            or self.verification_report.target_plan_id != self.plan_id
        ):
            raise InvalidDomainValueError(
                "WeeklyPlan.verification_report must be a VerificationReport for this Plan"
            )
        if not isinstance(self.generation_mode, MonthlyGenerationMode):
            raise InvalidDomainValueError("WeeklyPlan.generation_mode is invalid")

    def cell(self, section_key: str, day: OperatingDay | None = None) -> WeeklyCell:
        found = next(
            (
                cell
                for cell in self.cells
                if cell.section_key == section_key and cell.day is day
            ),
            None,
        )
        if found is None:
            raise InvalidDomainValueError(f"Weekly Section not found: {section_key} {day}")
        return found

    def find_cell(self, item_id: ItemId) -> WeeklyCell | None:
        if not isinstance(item_id, ItemId):
            raise InvalidDomainValueError("WeeklyPlan.find_cell requires ItemId")
        return next((cell for cell in self.cells if cell.item_id == item_id), None)

    def replace_cell(self, item_id: ItemId, replacement: WeeklyCell) -> WeeklyPlan:
        self.ensure_mutable("replace_cell")
        current = self.find_cell(item_id)
        if current is None:
            raise InvalidDomainValueError(f"Weekly cell not found: {item_id}")
        if not isinstance(replacement, WeeklyCell):
            raise InvalidDomainValueError("replacement must be WeeklyCell")
        if (replacement.item_id, replacement.section_key, replacement.day) != (
            current.item_id,
            current.section_key,
            current.day,
        ):
            raise InvalidDomainValueError(
                "Weekly replacement must preserve ItemId, section_key and day"
            )
        return replace(self, cells=tuple(replacement if cell is current else cell for cell in self.cells))

    def ensure_mutable(self, operation: str) -> None:
        _non_blank(operation, "operation")
        if not self.status.is_mutable:
            raise InvalidStateTransitionError(
                f"{operation} is not allowed for a CONFIRMED Weekly Plan"
            )

    def confirm(self, *, actor_id: ActorId, occurred_at: datetime) -> WeeklyPlan:
        self.ensure_mutable("confirm")
        event = AuditEvent(
            event_type=AuditEventType.CONFIRMED,
            occurred_at=occurred_at,
            plan_id=self.plan_id,
            actor_id=actor_id,
        )
        return replace(self, status=PlanStatus.CONFIRMED, audit=self.audit.append(event))
