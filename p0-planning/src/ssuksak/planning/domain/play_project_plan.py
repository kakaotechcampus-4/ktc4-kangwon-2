"""Play-project yearly plan (ADR-042 PLAY_PROJECT): periods of several months, play candidates.

Each period holds the AI candidates; the teacher picks ``selected_per_period`` of them
(2026-10-24 decision — the selection step comes with edit / confirm).

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
    candidates_per_period: int
    selected_per_period: int

    def __post_init__(self) -> None:
        keys = [period.key for period in self.periods]
        if not keys or len(keys) != len(set(keys)):
            raise InvalidDomainValueError("PlayProjectLayout needs unique periods")
        counts = (self.selected_per_period, self.candidates_per_period)
        if any(type(n) is not int for n in counts) or not 1 <= counts[0] <= counts[1]:
            raise InvalidDomainValueError(
                "PlayProjectLayout needs 1 <= selected_per_period <= candidates_per_period"
            )

    def period(self, key: str) -> PlayPeriod | None:
        return next((p for p in self.periods if p.key == key), None)


@dataclass(frozen=True, slots=True)
class PlayRow:
    row_key: str  # stable address part: "cand1".."candN"; selection order may change, this does not
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
    candidates: tuple[PlayRow, ...]

    def __post_init__(self) -> None:
        keys = [row.row_key for row in self.candidates]
        if not keys or len(keys) != len(set(keys)):
            raise InvalidDomainValueError("PlayPeriodRows needs unique candidates")


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
            for row in p.candidates
            for name in ROW_FIELDS
        ]
        if len(item_ids) != len(set(item_ids)):
            raise InvalidDomainValueError("PlayProjectYearlyPlan item ids must be unique")
