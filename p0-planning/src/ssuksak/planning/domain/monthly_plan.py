"""Immutable structural model for a Monthly Plan."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import Enum

from .errors import InvalidDomainValueError, InvalidStateTransitionError
from .identifiers import ActorId, ItemId, PlanId
from .lineage import ParentLineage
from .monthly_constraint import CellState, ConstraintAssessment
from .monthly_template import (
    DisplayMode,
    EmptyValuePolicy,
    SectionRole,
    TemplateRef,
)
from .monthly_template_snapshot import TemplateSnapshot
from .monthly_verification import VerificationReport
from .plan import PlanStatus
from .safety_placement import SafetyPlacement
from .provenance import (
    AuditEvent,
    AuditEventType,
    AuditHistory,
    EvidenceSource,
    GenerationMethodDetail,
)
from .week_period import WeekId, WeekPeriod
from .year_month import YearMonth


class LabelVariant(str, Enum):
    SUBTHEME_LABELED = "SUBTHEME_LABELED"
    EXPECTED_PLAY_LABELED = "EXPECTED_PLAY_LABELED"
    UNLABELED = "UNLABELED"


class MappingConfidence(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class MonthlyGenerationMode(str, Enum):
    RULE_ONLY = "RULE_ONLY"
    LLM_PLANNER = "LLM_PLANNER"


@dataclass(frozen=True, slots=True)
class ActivityCatalogRef:
    catalog_id: str
    catalog_version: str

    def __post_init__(self) -> None:
        for name in ("catalog_id", "catalog_version"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise InvalidDomainValueError(
                    f"ActivityCatalogRef.{name} must be non-blank"
                )


@dataclass(frozen=True, slots=True)
class MonthlyCell:
    item_id: ItemId
    section_key: str
    week_id: WeekId | None
    value: str
    cell_state: CellState
    generation: GenerationMethodDetail | None = None
    evidence: tuple[EvidenceSource, ...] = ()
    audit: AuditHistory = field(default_factory=AuditHistory)
    source_label: str | None = None
    label_variant: LabelVariant | None = None
    mapping_confidence: MappingConfidence | None = None
    safety: SafetyPlacement | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.item_id, ItemId):
            raise InvalidDomainValueError("MonthlyCell.item_id must be ItemId")
        if not isinstance(self.section_key, str) or not self.section_key.strip():
            raise InvalidDomainValueError(
                "MonthlyCell.section_key must be non-blank"
            )
        if self.week_id is not None and not isinstance(self.week_id, WeekId):
            raise InvalidDomainValueError("MonthlyCell.week_id must be WeekId")
        if not isinstance(self.value, str):
            raise InvalidDomainValueError("MonthlyCell.value must be a string")
        if not isinstance(self.cell_state, CellState):
            raise InvalidDomainValueError("MonthlyCell.cell_state is invalid")
        if bool(self.value.strip()) != (self.cell_state is CellState.FILLED):
            raise InvalidDomainValueError(
                "MonthlyCell FILLED state must match whether value is non-blank"
            )
        if self.value.strip() and not isinstance(
            self.generation, GenerationMethodDetail
        ):
            raise InvalidDomainValueError(
                "A filled MonthlyCell requires GenerationMethodDetail"
            )
        if self.generation is not None and not isinstance(
            self.generation, GenerationMethodDetail
        ):
            raise InvalidDomainValueError("MonthlyCell.generation is invalid")
        if not isinstance(self.evidence, tuple) or not all(
            isinstance(source, EvidenceSource) for source in self.evidence
        ):
            raise InvalidDomainValueError(
                "MonthlyCell.evidence must contain EvidenceSource values"
            )
        if not isinstance(self.audit, AuditHistory):
            raise InvalidDomainValueError("MonthlyCell.audit must be AuditHistory")
        if self.source_label is not None and (
            not isinstance(self.source_label, str) or not self.source_label.strip()
        ):
            raise InvalidDomainValueError(
                "MonthlyCell.source_label must be non-blank when set"
            )
        if self.label_variant is not None and not isinstance(
            self.label_variant, LabelVariant
        ):
            raise InvalidDomainValueError("MonthlyCell.label_variant is invalid")
        if self.mapping_confidence is not None and not isinstance(
            self.mapping_confidence, MappingConfidence
        ):
            raise InvalidDomainValueError(
                "MonthlyCell.mapping_confidence is invalid"
            )
        if self.safety is not None and (
            not isinstance(self.safety, SafetyPlacement)
            or self.section_key != "safety_education"
        ):
            raise InvalidDomainValueError(
                "MonthlyCell.safety belongs to safety_education Cells only"
            )

    @property
    def is_merged_cell(self) -> bool:
        return self.week_id is None


@dataclass(frozen=True, slots=True)
class MonthlySection:
    section_key: str
    role: SectionRole
    display_mode: DisplayMode | None
    empty_value_policy: EmptyValuePolicy
    activated: bool = True
    parent_section_key: str | None = None
    source_label: str | None = None
    cells: tuple[MonthlyCell, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.section_key, str) or not self.section_key.strip():
            raise InvalidDomainValueError(
                "MonthlySection.section_key must be non-blank"
            )
        if not isinstance(self.role, SectionRole):
            raise InvalidDomainValueError("MonthlySection.role is invalid")
        if self.display_mode is not None and not isinstance(
            self.display_mode, DisplayMode
        ):
            raise InvalidDomainValueError("MonthlySection.display_mode is invalid")
        if not isinstance(self.empty_value_policy, EmptyValuePolicy):
            raise InvalidDomainValueError(
                "MonthlySection.empty_value_policy is invalid"
            )
        if type(self.activated) is not bool:
            raise InvalidDomainValueError(
                "MonthlySection.activated must be a boolean"
            )
        if not isinstance(self.cells, tuple) or not all(
            isinstance(cell, MonthlyCell) for cell in self.cells
        ):
            raise InvalidDomainValueError(
                "MonthlySection.cells must contain MonthlyCell values"
            )
        if any(cell.section_key != self.section_key for cell in self.cells):
            raise InvalidDomainValueError(
                "MonthlySection cells must reference their containing section"
            )
        if self.role is SectionRole.AXIS and self.cells:
            raise InvalidDomainValueError("An AXIS MonthlySection cannot own cells")
        if len({cell.week_id for cell in self.cells}) != len(self.cells):
            raise InvalidDomainValueError(
                "MonthlySection cannot contain duplicate week addresses"
            )

    def cell_for_week(self, week_id: WeekId | None) -> MonthlyCell | None:
        return next((cell for cell in self.cells if cell.week_id == week_id), None)


@dataclass(frozen=True, slots=True)
class MonthlyPlan:
    plan_id: PlanId
    school_year: int
    target_month: YearMonth
    daycare_ref: str
    classroom_ref: str
    target_ages: frozenset[int]
    status: PlanStatus
    parent_lineage: ParentLineage
    template_snapshot: TemplateSnapshot
    week_periods: tuple[WeekPeriod, ...]
    sections: tuple[MonthlySection, ...]
    constraint_assessments: tuple[ConstraintAssessment, ...] = ()
    audit: AuditHistory = field(default_factory=AuditHistory)
    activity_catalog_ref: ActivityCatalogRef | None = None
    generation_mode: MonthlyGenerationMode = MonthlyGenerationMode.RULE_ONLY
    verification_report: VerificationReport | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.plan_id, PlanId):
            raise InvalidDomainValueError("MonthlyPlan.plan_id must be PlanId")
        if type(self.school_year) is not int or not 1 <= self.school_year <= 9998:
            raise InvalidDomainValueError(
                "MonthlyPlan.school_year must be 1 through 9998"
            )
        if not isinstance(self.target_month, YearMonth):
            raise InvalidDomainValueError(
                "MonthlyPlan.target_month must be YearMonth"
            )
        if self.target_month.value not in _academic_months(self.school_year):
            raise InvalidDomainValueError(
                "MonthlyPlan.target_month must belong to its school year"
            )
        for name in ("daycare_ref", "classroom_ref"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise InvalidDomainValueError(f"MonthlyPlan.{name} must be non-blank")
        if not isinstance(self.target_ages, frozenset) or not self.target_ages:
            raise InvalidDomainValueError(
                "MonthlyPlan.target_ages must be a non-empty frozenset"
            )
        if any(type(age) is not int or age not in {3, 4, 5} for age in self.target_ages):
            raise InvalidDomainValueError(
                "MonthlyPlan.target_ages supports P0 ages 3, 4, and 5 only"
            )
        if not isinstance(self.status, PlanStatus):
            raise InvalidDomainValueError("MonthlyPlan.status is invalid")
        if not isinstance(self.parent_lineage, ParentLineage):
            raise InvalidDomainValueError(
                "MonthlyPlan.parent_lineage must use ParentLineage"
            )
        if self.parent_lineage.parent_item_id is None:
            raise InvalidDomainValueError(
                "MonthlyPlan requires item-level parent lineage"
            )
        if not isinstance(self.template_snapshot, TemplateSnapshot):
            raise InvalidDomainValueError(
                "MonthlyPlan.template_snapshot must be TemplateSnapshot"
            )
        if self.template_snapshot.institution_ref != self.daycare_ref:
            raise InvalidDomainValueError(
                "MonthlyPlan daycare_ref must match its TemplateSnapshot scope"
            )
        if (
            self.template_snapshot.classroom_ref is not None
            and self.template_snapshot.classroom_ref != self.classroom_ref
        ):
            raise InvalidDomainValueError(
                "MonthlyPlan classroom_ref must match its TemplateSnapshot scope"
            )
        if not isinstance(self.week_periods, tuple) or not self.week_periods:
            raise InvalidDomainValueError(
                "MonthlyPlan.week_periods must be a non-empty tuple"
            )
        if not all(isinstance(period, WeekPeriod) for period in self.week_periods):
            raise InvalidDomainValueError(
                "MonthlyPlan.week_periods must contain WeekPeriod values"
            )
        if any(
            period.week_id.target_month != self.target_month
            for period in self.week_periods
        ):
            raise InvalidDomainValueError(
                "MonthlyPlan WeekPeriod values must match target_month"
            )
        ordinals = tuple(period.week_id.ordinal for period in self.week_periods)
        if ordinals != tuple(range(1, len(self.week_periods) + 1)):
            raise InvalidDomainValueError(
                "MonthlyPlan WeekPeriod ordinals must be consecutive"
            )
        if not isinstance(self.sections, tuple) or not self.sections:
            raise InvalidDomainValueError(
                "MonthlyPlan.sections must be a non-empty tuple"
            )
        if not all(isinstance(section, MonthlySection) for section in self.sections):
            raise InvalidDomainValueError(
                "MonthlyPlan.sections must contain MonthlySection values"
            )
        section_keys = tuple(section.section_key for section in self.sections)
        if len(set(section_keys)) != len(section_keys):
            raise InvalidDomainValueError(
                "MonthlyPlan cannot contain duplicate section keys"
            )
        snapshot_section_keys = tuple(
            section.section_key for section in self.template_snapshot.sections
        )
        if section_keys != snapshot_section_keys:
            raise InvalidDomainValueError(
                "MonthlyPlan sections must match its ordered TemplateSnapshot Sections"
            )
        item_ids = tuple(cell.item_id for cell in self.cells)
        if len(set(item_ids)) != len(item_ids):
            raise InvalidDomainValueError(
                "MonthlyPlan cells must have unique ItemId values"
            )
        active_week_ids = {period.week_id for period in self.active_week_periods}
        for cell in self.cells:
            if cell.week_id is not None and cell.week_id not in active_week_ids:
                raise InvalidDomainValueError(
                    "MonthlyCell week_id must reference an active WeekPeriod"
                )
        if not isinstance(self.constraint_assessments, tuple) or not all(
            isinstance(item, ConstraintAssessment)
            for item in self.constraint_assessments
        ):
            raise InvalidDomainValueError(
                "MonthlyPlan.constraint_assessments are invalid"
            )
        codes = tuple(
            assessment.constraint.code for assessment in self.constraint_assessments
        )
        if len(set(codes)) != len(codes):
            raise InvalidDomainValueError(
                "MonthlyPlan cannot duplicate a constraint assessment"
            )
        if not isinstance(self.audit, AuditHistory):
            raise InvalidDomainValueError("MonthlyPlan.audit must be AuditHistory")
        if self.activity_catalog_ref is not None and not isinstance(
            self.activity_catalog_ref, ActivityCatalogRef
        ):
            raise InvalidDomainValueError(
                "MonthlyPlan.activity_catalog_ref must be ActivityCatalogRef"
            )
        if not isinstance(self.generation_mode, MonthlyGenerationMode):
            raise InvalidDomainValueError(
                "MonthlyPlan.generation_mode must be MonthlyGenerationMode"
            )
        if self.verification_report is not None:
            if not isinstance(self.verification_report, VerificationReport):
                raise InvalidDomainValueError(
                    "MonthlyPlan.verification_report must be VerificationReport"
                )
            if self.verification_report.target_plan_id != self.plan_id:
                raise InvalidDomainValueError(
                    "MonthlyPlan.verification_report must target this Plan"
                )

    @property
    def cells(self) -> tuple[MonthlyCell, ...]:
        return tuple(cell for section in self.sections for cell in section.cells)

    @property
    def template_ref(self) -> TemplateRef:
        """Backward-compatible view derived from the single Snapshot source."""

        return self.template_snapshot.base_template_ref

    @property
    def active_week_periods(self) -> tuple[WeekPeriod, ...]:
        return tuple(period for period in self.week_periods if period.active)

    def section(self, section_key: str) -> MonthlySection | None:
        return next(
            (section for section in self.sections if section.section_key == section_key),
            None,
        )

    def find_cell(
        self, item_id: ItemId
    ) -> tuple[int, int, MonthlySection, MonthlyCell] | None:
        if not isinstance(item_id, ItemId):
            raise InvalidDomainValueError("MonthlyPlan.find_cell requires ItemId")
        for section_index, section in enumerate(self.sections):
            for cell_index, cell in enumerate(section.cells):
                if cell.item_id == item_id:
                    return section_index, cell_index, section, cell
        return None

    def ensure_mutable(self, operation: str) -> None:
        if not isinstance(operation, str) or not operation.strip():
            raise InvalidDomainValueError("operation must be non-blank")
        if not self.status.is_mutable:
            raise InvalidStateTransitionError(
                f"{operation} is not allowed for a CONFIRMED Monthly Plan"
            )

    def replace_cell(self, item_id: ItemId, replacement: MonthlyCell) -> MonthlyPlan:
        self.ensure_mutable("replace_cell")
        found = self.find_cell(item_id)
        if found is None:
            raise InvalidDomainValueError(f"Monthly cell not found: {item_id}")
        if not isinstance(replacement, MonthlyCell):
            raise InvalidDomainValueError("replacement must be MonthlyCell")
        section_index, cell_index, section, current = found
        if replacement.item_id != current.item_id:
            raise InvalidDomainValueError("Monthly replacement must preserve ItemId")
        if (
            replacement.section_key,
            replacement.week_id,
        ) != (
            current.section_key,
            current.week_id,
        ):
            raise InvalidDomainValueError(
                "Monthly replacement must preserve its structural address"
            )
        cells = list(section.cells)
        cells[cell_index] = replacement
        sections = list(self.sections)
        sections[section_index] = replace(section, cells=tuple(cells))
        return replace(
            self,
            sections=tuple(sections),
            verification_report=None,
        )

    def confirm(self, *, actor_id: ActorId, occurred_at: datetime) -> MonthlyPlan:
        self.ensure_mutable("confirm")
        event = AuditEvent(
            event_type=AuditEventType.CONFIRMED,
            occurred_at=occurred_at,
            plan_id=self.plan_id,
            actor_id=actor_id,
        )
        return replace(
            self,
            status=PlanStatus.CONFIRMED,
            audit=self.audit.append(event),
        )

    def constraint(self, code: str) -> ConstraintAssessment | None:
        return next(
            (
                assessment
                for assessment in self.constraint_assessments
                if assessment.constraint.code == code
            ),
            None,
        )

    @property
    def unresolved_constraints(self) -> tuple[ConstraintAssessment, ...]:
        return tuple(
            assessment
            for assessment in self.constraint_assessments
            if assessment.is_unresolved
        )


def _academic_months(school_year: int) -> tuple[str, ...]:
    months = (3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 1, 2)
    return tuple(
        YearMonth(school_year if month >= 3 else school_year + 1, month).value
        for month in months
    )
