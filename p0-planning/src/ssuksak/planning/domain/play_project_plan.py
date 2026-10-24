"""Play-project yearly plan (ADR-042 PLAY_PROJECT): periods of several months, fixed play rows.

A separate aggregate from ``YearlyPlan`` — it has no monthly theme and no monthly child yet.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .errors import InvalidDomainValueError
from .identifiers import PlanId
from .plan import PlanItem, PlanStatus
from .provenance import AuditHistory, EvidenceSourceType

PLAY_PROJECT_FORMAT = "PLAY_PROJECT"
ROW_FIELDS = ("play_name", "materials", "support_direction", "learning")


@dataclass(frozen=True, slots=True)
class PlayPeriod:
    """A versioned layout period, e.g. ``m03_m05`` = March–May."""

    key: str
    months: tuple[int, ...]
    label: str

    def __post_init__(self) -> None:
        if not self.key.strip() or not self.label.strip():
            raise InvalidDomainValueError("PlayPeriod key and label must be non-blank")
        if not self.months or any(type(m) is not int or not 1 <= m <= 12 for m in self.months):
            raise InvalidDomainValueError("PlayPeriod.months must be calendar months")


@dataclass(frozen=True, slots=True)
class PlayProjectLayout:
    layout_version: str
    periods: tuple[PlayPeriod, ...]
    rows_per_period: int

    def __post_init__(self) -> None:
        keys = [period.key for period in self.periods]
        if not keys or len(keys) != len(set(keys)):
            raise InvalidDomainValueError("PlayProjectLayout needs unique periods")
        if type(self.rows_per_period) is not int or self.rows_per_period < 1:
            raise InvalidDomainValueError("PlayProjectLayout.rows_per_period must be positive")

    def period(self, key: str) -> PlayPeriod | None:
        return next((p for p in self.periods if p.key == key), None)


@dataclass(frozen=True, slots=True)
class PlayRow:
    row_key: str  # stable address part: "row1".."rowN"; display order may change, this does not
    play_name: PlanItem
    materials: PlanItem
    support_direction: PlanItem
    learning: PlanItem

    def __post_init__(self) -> None:
        if not self.learning.evidence or any(
            source.source_type is not EvidenceSourceType.CURRICULUM
            for source in self.learning.evidence
        ):
            raise InvalidDomainValueError("PlayRow.learning cites CURRICULUM evidence only")

    def semantic_key(self, period_key: str, field_name: str) -> str:
        return f"play_project.{period_key}.{self.row_key}.{field_name}"


@dataclass(frozen=True, slots=True)
class PlayPeriodRows:
    period: PlayPeriod
    rows: tuple[PlayRow, ...]

    def __post_init__(self) -> None:
        keys = [row.row_key for row in self.rows]
        if not keys or len(keys) != len(set(keys)):
            raise InvalidDomainValueError("PlayPeriodRows needs unique rows")


@dataclass(frozen=True, slots=True)
class PlayProjectYearlyPlan:
    plan_id: PlanId
    school_year: int
    classroom_ref: str
    target_ages: frozenset[int]
    status: PlanStatus
    layout_version: str
    periods: tuple[PlayPeriodRows, ...]
    audit: AuditHistory = field(default_factory=AuditHistory)
    format: str = PLAY_PROJECT_FORMAT

    def __post_init__(self) -> None:
        if self.format != PLAY_PROJECT_FORMAT:
            raise InvalidDomainValueError("PlayProjectYearlyPlan.format must be PLAY_PROJECT")
        if not self.classroom_ref.strip() or not self.layout_version.strip():
            raise InvalidDomainValueError("classroom_ref and layout_version must be non-blank")
        if not self.target_ages or any(age not in {3, 4, 5} for age in self.target_ages):
            raise InvalidDomainValueError("target_ages must be a non-empty subset of {3, 4, 5}")
        keys = [p.period.key for p in self.periods]
        if not keys or len(keys) != len(set(keys)):
            raise InvalidDomainValueError("PlayProjectYearlyPlan needs unique periods")
        item_ids = [
            getattr(row, name).item_id
            for p in self.periods
            for row in p.rows
            for name in ROW_FIELDS
        ]
        if len(item_ids) != len(set(item_ids)):
            raise InvalidDomainValueError("PlayProjectYearlyPlan item ids must be unique")
