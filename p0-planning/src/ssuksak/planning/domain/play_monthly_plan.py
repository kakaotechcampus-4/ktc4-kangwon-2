"""Play-centred monthly plan (PLAY_MONTHLY): a separate aggregate from the v1 ``MonthlyPlan``.

Its parent is a CONFIRMED ``PlayProjectYearlyPlan``. The plan keeps the header layout it was
made with, the parent plays it read, the Reference versions it used, and values that may be
blank: teacher-input cells start empty, and safety candidates are kept apart from the weekly
placement, which starts unplaced. Every list row and candidate is addressed by its ``ItemId``,
never by its position. A row a teacher deletes leaves the document but stays whole in
``removed_activities``; adding, deleting and placing are plan-level ARRANGEMENT_CHANGED events.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import Enum

from .errors import InvalidDomainValueError, InvalidStateTransitionError
from .identifiers import ActorId, ItemId, PlanId
from .lineage import ParentLineage
from .plan import PlanStatus
from .provenance import (
    ArrangementChange,
    AuditEvent,
    AuditEventType,
    AuditHistory,
    EvidenceSource,
    EvidenceSourceType,
    GenerationMethod,
    GenerationMethodDetail,
)
from .safety_placement import SafetyKind
from .week_period import WeekId, WeekPeriod
from .year_month import YearMonth

PLAY_MONTHLY_FORMAT = "PLAY_MONTHLY"
PLAY_SECTIONS = ("together", "free_play")
DRILL_CELL_KEY = "fire_disaster_drill"
DRILL_COPY_RULE_ID = "play_monthly.drill_copy"


def _non_blank(value: object, path: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise InvalidDomainValueError(f"{path} must be a non-blank string")


class LayoutRole(str, Enum):
    TITLE = "TITLE"  # a printed group header with no value
    CALENDAR = "CALENDAR"  # filled from the system calendar (예상 기간)
    GENERATED = "GENERATED"
    TEACHER_INPUT = "TEACHER_INPUT"  # starts blank; never generated


@dataclass(frozen=True, slots=True)
class LayoutSection:
    semantic_key: str
    source_label: str
    role: LayoutRole

    def __post_init__(self) -> None:
        _non_blank(self.semantic_key, "LayoutSection.semantic_key")
        _non_blank(self.source_label, "LayoutSection.source_label")
        if not isinstance(self.role, LayoutRole):
            raise InvalidDomainValueError("LayoutSection.role is invalid")


@dataclass(frozen=True, slots=True)
class PlayMonthlyLayout:
    """Versioned header layout and initial list sizes, captured into each plan."""

    layout_version: str
    sections: tuple[LayoutSection, ...]
    together_count: int
    free_play_count: int
    drill_candidate_count: int

    def __post_init__(self) -> None:
        _non_blank(self.layout_version, "PlayMonthlyLayout.layout_version")
        keys = [section.semantic_key for section in self.sections]
        if not keys or len(keys) != len(set(keys)):
            raise InvalidDomainValueError("PlayMonthlyLayout needs unique sections")
        counts = (self.together_count, self.free_play_count, self.drill_candidate_count)
        if any(type(n) is not int or n < 1 for n in counts):
            raise InvalidDomainValueError("PlayMonthlyLayout list sizes must be positive")

    @property
    def teacher_input_keys(self) -> tuple[str, ...]:
        return tuple(s.semantic_key for s in self.sections if s.role is LayoutRole.TEACHER_INPUT)


@dataclass(frozen=True, slots=True)
class PlayMonthlyCell:
    """An editable value that may be blank.

    No generation means nothing was ever written (a teacher-input cell before its first
    write). A generated value keeps its generation even when a teacher later clears it.
    """

    item_id: ItemId
    semantic_key: str
    value: str = ""
    evidence: tuple[EvidenceSource, ...] = ()
    generation: GenerationMethodDetail | None = None
    audit: AuditHistory = field(default_factory=AuditHistory)

    def __post_init__(self) -> None:
        if not isinstance(self.item_id, ItemId):
            raise InvalidDomainValueError("PlayMonthlyCell.item_id must be ItemId")
        _non_blank(self.semantic_key, "PlayMonthlyCell.semantic_key")
        if not isinstance(self.value, str):
            raise InvalidDomainValueError("PlayMonthlyCell.value must be a string")
        if not isinstance(self.evidence, tuple) or not all(
            isinstance(source, EvidenceSource) for source in self.evidence
        ):
            raise InvalidDomainValueError("PlayMonthlyCell.evidence must be EvidenceSource values")
        if self.generation is None:
            if self.value.strip() or self.evidence:
                raise InvalidDomainValueError(
                    "A PlayMonthlyCell without generation must be blank and cite nothing"
                )
        elif not isinstance(self.generation, GenerationMethodDetail):
            raise InvalidDomainValueError("PlayMonthlyCell.generation is invalid")
        if not isinstance(self.audit, AuditHistory):
            raise InvalidDomainValueError("PlayMonthlyCell.audit must be AuditHistory")

    def cites_only(self, *types: EvidenceSourceType) -> bool:
        return all(source.source_type in types for source in self.evidence)


@dataclass(frozen=True, slots=True)
class PlayActivity:
    """One row of 함께 하는 활동 or 유아 예상 자유놀이: a play name with its links.

    PARENT_PLAN evidence appears only when the row actually builds on one parent play, and
    then the parent item is snapshotted. CURRICULUM evidence lists the content ids linked at
    generation and never changes; ``content_ids`` holds the current links, which a teacher may
    change within the plan's curriculum catalog version (M2-D18, I-1).

    ``description`` explains the play for the teacher on the edit screen (M2-D16). It is its
    own cell, paired to the name by semantic key, and is never printed in the document.
    """

    cell: PlayMonthlyCell
    description: PlayMonthlyCell
    content_ids: tuple[str, ...]
    parent_snapshot: ParentLineage | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.cell, PlayMonthlyCell):
            raise InvalidDomainValueError("PlayActivity.cell must be PlayMonthlyCell")
        if not isinstance(self.content_ids, tuple) or not all(
            isinstance(i, str) and i.strip() for i in self.content_ids
        ):
            raise InvalidDomainValueError("PlayActivity.content_ids must be non-blank strings")
        if len(self.content_ids) != len(set(self.content_ids)):
            raise InvalidDomainValueError("PlayActivity.content_ids must be unique")
        if not isinstance(self.description, PlayMonthlyCell):
            raise InvalidDomainValueError("PlayActivity.description must be PlayMonthlyCell")
        if self.description.semantic_key != f"{self.cell.semantic_key}.description":
            raise InvalidDomainValueError("PlayActivity.description must pair with its name cell")
        if not all(
            c.cites_only(EvidenceSourceType.CURRICULUM, EvidenceSourceType.PARENT_PLAN)
            for c in (self.cell, self.description)
        ):
            raise InvalidDomainValueError("PlayActivity cites CURRICULUM and PARENT_PLAN only")
        cites_parent = any(
            s.source_type is EvidenceSourceType.PARENT_PLAN for s in self.cell.evidence
        )
        if self.parent_snapshot is not None and (
            not isinstance(self.parent_snapshot, ParentLineage)
            or self.parent_snapshot.parent_item_id is None
        ):
            raise InvalidDomainValueError("PlayActivity.parent_snapshot must be item-level")
        if cites_parent != (self.parent_snapshot is not None):
            raise InvalidDomainValueError(
                "PlayActivity cites PARENT_PLAN exactly when it snapshots a parent play"
            )


@dataclass(frozen=True, slots=True)
class RemovedActivity:
    """A row a teacher deleted, kept whole for history (I-3). Never shown, exported or confirmed."""

    section: str
    activity: PlayActivity

    def __post_init__(self) -> None:
        if self.section not in PLAY_SECTIONS or not isinstance(self.activity, PlayActivity):
            raise InvalidDomainValueError("RemovedActivity needs a play section and a PlayActivity")


@dataclass(frozen=True, slots=True)
class SafetyCandidate:
    """A proposed safety education item; placing it in a week is separate (``SafetyWeek``).

    STATUTORY: one of the six legal categories, grounded in that category's official items.
    SUPPLEMENTAL: 생활안전, grounded in approved institution samples of one topic.
    """

    cell: PlayMonthlyCell
    kind: SafetyKind
    category_id: str | None = None
    topic_group: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.cell, PlayMonthlyCell):
            raise InvalidDomainValueError("SafetyCandidate.cell must be PlayMonthlyCell")
        if not isinstance(self.kind, SafetyKind):
            raise InvalidDomainValueError("SafetyCandidate.kind is invalid")
        statutory = self.kind is SafetyKind.STATUTORY
        named = self.category_id if statutory else self.topic_group
        other = self.topic_group if statutory else self.category_id
        _non_blank(named, "SafetyCandidate category_id/topic_group")
        if other is not None:
            raise InvalidDomainValueError(
                "STATUTORY names a category_id only; SUPPLEMENTAL names a topic_group only"
            )
        source = EvidenceSourceType.SAFETY_RULE if statutory else EvidenceSourceType.INSTITUTION_SAMPLE
        if not self.cell.cites_only(source):
            raise InvalidDomainValueError(f"{self.kind.value} safety cites {source.value} only")


@dataclass(frozen=True, slots=True)
class SafetyWeek:
    """Which candidate a teacher placed in one week; ``None`` = not placed yet."""

    week_id: WeekId
    candidate_item_id: ItemId | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.week_id, WeekId):
            raise InvalidDomainValueError("SafetyWeek.week_id must be WeekId")
        if self.candidate_item_id is not None and not isinstance(self.candidate_item_id, ItemId):
            raise InvalidDomainValueError("SafetyWeek.candidate_item_id must be ItemId")


@dataclass(frozen=True, slots=True)
class EntryCell:
    """A cell filled from a daily-life Reference entry; ``entry_id`` is the entry it came from."""

    cell: PlayMonthlyCell
    entry_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.cell, PlayMonthlyCell):
            raise InvalidDomainValueError("EntryCell.cell must be PlayMonthlyCell")
        if self.entry_id is not None:
            _non_blank(self.entry_id, "EntryCell.entry_id")
        if not self.cell.cites_only(EvidenceSourceType.CURRICULUM):
            raise InvalidDomainValueError("EntryCell cites CURRICULUM only")


@dataclass(frozen=True, slots=True)
class DrillCandidate:
    """A 소방대피 · 재난대비 topic candidate. The document's drill cell is a separate
    teacher-input cell that starts blank; a candidate is never placed automatically.

    ``topic_id`` and ``label`` are the Rule's choice. The sentence is checked for its topic id
    and for invented facts, not for matching the topic, so the screen shows ``label`` next to
    it and the teacher reviews the sentence."""

    cell: PlayMonthlyCell
    topic_id: str
    label: str

    def __post_init__(self) -> None:
        if not isinstance(self.cell, PlayMonthlyCell):
            raise InvalidDomainValueError("DrillCandidate.cell must be PlayMonthlyCell")
        _non_blank(self.topic_id, "DrillCandidate.topic_id")
        _non_blank(self.label, "DrillCandidate.label")
        if not self.cell.cites_only(EvidenceSourceType.CURRICULUM):
            raise InvalidDomainValueError("DrillCandidate cites CURRICULUM only")


@dataclass(frozen=True, slots=True)
class HabitWeek:
    week_id: WeekId
    habit: EntryCell

    def __post_init__(self) -> None:
        if not isinstance(self.week_id, WeekId) or not isinstance(self.habit, EntryCell):
            raise InvalidDomainValueError("HabitWeek needs a WeekId and an EntryCell")


@dataclass(frozen=True, slots=True)
class ParentPlay:
    """A selected parent candidate as it was read: its row_key and play_name item."""

    row_key: str
    play_name_item_id: ItemId
    play_name: str
    materials: str
    support_direction: str

    def __post_init__(self) -> None:
        for name in ("row_key", "play_name", "materials", "support_direction"):
            _non_blank(getattr(self, name), f"ParentPlay.{name}")
        if not isinstance(self.play_name_item_id, ItemId):
            raise InvalidDomainValueError("ParentPlay.play_name_item_id must be ItemId")


@dataclass(frozen=True, slots=True)
class ParentPlaySnapshot:
    """Plan-level parent input: the confirmed yearly plan, its period and its selected plays."""

    lineage: ParentLineage
    layout_version: str
    period_key: str
    plays: tuple[ParentPlay, ...]
    emphasized: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.lineage, ParentLineage) or self.lineage.parent_item_id is not None:
            raise InvalidDomainValueError("ParentPlaySnapshot.lineage must be plan-level")
        _non_blank(self.layout_version, "ParentPlaySnapshot.layout_version")
        _non_blank(self.period_key, "ParentPlaySnapshot.period_key")
        keys = [play.row_key for play in self.plays]
        if not keys or len(keys) != len(set(keys)):
            raise InvalidDomainValueError("ParentPlaySnapshot needs unique selected plays")
        if len(self.emphasized) != len(set(self.emphasized)) or not set(self.emphasized) <= set(keys):
            raise InvalidDomainValueError("ParentPlaySnapshot.emphasized must name selected plays")

    def play(self, row_key: str) -> ParentPlay | None:
        return next((p for p in self.plays if p.row_key == row_key), None)


@dataclass(frozen=True, slots=True)
class PlayMonthlyReferences:
    """Exact versions of everything the generation read, for reproduction."""

    curriculum_catalog_id: str
    curriculum_catalog_version: str
    daily_life_catalog_id: str
    daily_life_catalog_version: str
    legal_rule_version: str
    evidence_store_version: str
    evidence_store_sha256: str
    safety_classification_version: str
    safety_quality_version: str
    drill_catalog_id: str
    drill_catalog_version: str
    prompt_version: str
    request_fingerprint: str

    def __post_init__(self) -> None:
        for name in self.__dataclass_fields__:
            _non_blank(getattr(self, name), f"PlayMonthlyReferences.{name}")


@dataclass(frozen=True, slots=True)
class PlayMonthlyPlan:
    plan_id: PlanId
    school_year: int
    classroom_ref: str
    target_month: YearMonth
    target_ages: frozenset[int]
    status: PlanStatus
    layout: PlayMonthlyLayout
    weeks: tuple[WeekPeriod, ...]
    parent: ParentPlaySnapshot
    references: PlayMonthlyReferences
    theme: PlayMonthlyCell
    rationale: PlayMonthlyCell
    together: tuple[PlayActivity, ...]
    free_play: tuple[PlayActivity, ...]
    habits: tuple[HabitWeek, ...]
    safety_candidates: tuple[SafetyCandidate, ...]
    safety_weeks: tuple[SafetyWeek, ...]
    health: EntryCell
    nutrition: EntryCell
    drill_candidates: tuple[DrillCandidate, ...]
    teacher_inputs: tuple[PlayMonthlyCell, ...]
    audit: AuditHistory = field(default_factory=AuditHistory)
    removed_activities: tuple[RemovedActivity, ...] = ()
    format: str = PLAY_MONTHLY_FORMAT

    def __post_init__(self) -> None:
        if self.format != PLAY_MONTHLY_FORMAT:
            raise InvalidDomainValueError("PlayMonthlyPlan.format must be PLAY_MONTHLY")
        if not isinstance(self.plan_id, PlanId):
            raise InvalidDomainValueError("PlayMonthlyPlan.plan_id must be PlanId")
        _non_blank(self.classroom_ref, "PlayMonthlyPlan.classroom_ref")
        if not isinstance(self.status, PlanStatus):
            raise InvalidDomainValueError("PlayMonthlyPlan.status is invalid")
        if not self.target_ages or any(age not in {3, 4, 5} for age in self.target_ages):
            raise InvalidDomainValueError("target_ages must be a non-empty subset of {3, 4, 5}")
        month = self.target_month
        if not isinstance(month, YearMonth) or type(self.school_year) is not int:
            raise InvalidDomainValueError("PlayMonthlyPlan needs a YearMonth and an int school_year")
        if month.calendar_year != (self.school_year if month.calendar_month >= 3 else self.school_year + 1):
            raise InvalidDomainValueError("target_month must belong to the school year")
        week_ids = tuple(week.week_id for week in self.weeks)
        if not week_ids or len(set(week_ids)) != len(week_ids) or any(
            w.target_month != month for w in week_ids
        ):
            raise InvalidDomainValueError("PlayMonthlyPlan.weeks must be unique weeks of target_month")
        if tuple(h.week_id for h in self.habits) != week_ids:
            raise InvalidDomainValueError("PlayMonthlyPlan needs one habit per week, in week order")
        if tuple(s.week_id for s in self.safety_weeks) != week_ids:
            raise InvalidDomainValueError("PlayMonthlyPlan needs one safety placement per week")
        candidate_ids = {c.cell.item_id for c in self.safety_candidates}
        if any(
            s.candidate_item_id is not None and s.candidate_item_id not in candidate_ids
            for s in self.safety_weeks
        ):
            raise InvalidDomainValueError("A safety placement must name a kept candidate")
        topics = [d.topic_id for d in self.drill_candidates]
        if len(topics) != len(set(topics)):
            raise InvalidDomainValueError("Drill candidates must name distinct topics")
        if tuple(t.semantic_key for t in self.teacher_inputs) != self.layout.teacher_input_keys:
            raise InvalidDomainValueError("teacher_inputs must follow the layout's teacher-input keys")
        drill_ids = {d.cell.item_id for d in self.drill_candidates}
        for t in self.teacher_inputs:
            if t.generation is None or t.generation.method is GenerationMethod.MANUAL:
                continue
            # The one exception (M2-D17): the drill cell holds a copied drill candidate.
            copies = [e for e in t.audit if e.event_type is AuditEventType.CANDIDATE_COPIED]
            if (
                t.semantic_key != DRILL_CELL_KEY
                or t.generation != self.drill_copy_generation
                or not copies
                or any(e.copied_from not in drill_ids for e in copies)
            ):
                raise InvalidDomainValueError(
                    "A teacher-input cell is MANUAL, or the drill cell holds a copied drill candidate"
                )
        if not isinstance(self.removed_activities, tuple) or not all(
            isinstance(r, RemovedActivity) for r in self.removed_activities
        ):
            raise InvalidDomainValueError("PlayMonthlyPlan.removed_activities must be RemovedActivity")
        # Archived rows keep their ids, so a removed id is never used again.
        cells = (
            *self.cells(),
            *(c for r in self.removed_activities for c in (r.activity.cell, r.activity.description)),
        )
        for name in ("item_id", "semantic_key"):
            values = [getattr(cell, name) for cell in cells]
            if len(values) != len(set(values)):
                raise InvalidDomainValueError(f"PlayMonthlyPlan {name}s must be unique")

    def cells(self) -> tuple[PlayMonthlyCell, ...]:
        return (
            self.theme,
            self.rationale,
            *(c for a in (*self.together, *self.free_play) for c in (a.cell, a.description)),
            *(h.habit.cell for h in self.habits),
            *(c.cell for c in self.safety_candidates),
            self.health.cell,
            self.nutrition.cell,
            *(d.cell for d in self.drill_candidates),
            *self.teacher_inputs,
        )

    @property
    def drill_copy_generation(self) -> GenerationMethodDetail:
        return GenerationMethodDetail(
            GenerationMethod.RULE_ONLY, rule_id=DRILL_COPY_RULE_ID, rule_version=self.layout.layout_version
        )

    def ensure_mutable(self, operation: str) -> None:
        if not self.status.is_mutable:
            raise InvalidStateTransitionError(
                f"{operation} is not allowed for a CONFIRMED PlayMonthlyPlan"
            )

    def find_cell(self, item_id: ItemId) -> PlayMonthlyCell | None:
        return next((c for c in self.cells() if c.item_id == item_id), None)

    def replace_cell(self, updated: PlayMonthlyCell) -> PlayMonthlyPlan:
        """Swap the cell with the same ``item_id`` and ``semantic_key``; nothing else moves."""
        self.ensure_mutable("replace_cell")
        current = self.find_cell(updated.item_id)
        if current is None or current.semantic_key != updated.semantic_key:
            raise InvalidDomainValueError(f"PlayMonthlyPlan cell not found: {updated.item_id}")

        def swap(cell: PlayMonthlyCell) -> PlayMonthlyCell:
            return updated if cell.item_id == updated.item_id else cell

        def rows(activities: tuple[PlayActivity, ...]) -> tuple[PlayActivity, ...]:
            return tuple(
                replace(a, cell=swap(a.cell), description=swap(a.description)) for a in activities
            )

        return replace(
            self,
            theme=swap(self.theme),
            rationale=swap(self.rationale),
            together=rows(self.together),
            free_play=rows(self.free_play),
            habits=tuple(
                replace(h, habit=replace(h.habit, cell=swap(h.habit.cell))) for h in self.habits
            ),
            safety_candidates=tuple(replace(c, cell=swap(c.cell)) for c in self.safety_candidates),
            health=replace(self.health, cell=swap(self.health.cell)),
            nutrition=replace(self.nutrition, cell=swap(self.nutrition.cell)),
            drill_candidates=tuple(replace(d, cell=swap(d.cell)) for d in self.drill_candidates),
            teacher_inputs=tuple(swap(t) for t in self.teacher_inputs),
        )

    def replace_activity(self, updated: PlayActivity) -> PlayMonthlyPlan:
        """Swap the row whose name cell has the same ``item_id``; its section and place stay."""
        self.ensure_mutable("replace_activity")
        current = self.activity(updated.cell.item_id)
        if current is None or current.description.item_id != updated.description.item_id:
            raise InvalidDomainValueError(f"PlayMonthlyPlan activity not found: {updated.cell.item_id}")

        def swap(activities: tuple[PlayActivity, ...]) -> tuple[PlayActivity, ...]:
            return tuple(updated if a is current else a for a in activities)

        return replace(self, together=swap(self.together), free_play=swap(self.free_play))

    def activity(self, name_item_id: ItemId) -> PlayActivity | None:
        return next(
            (a for a in (*self.together, *self.free_play) if a.cell.item_id == name_item_id), None
        )

    def add_activity(
        self, section: str, activity: PlayActivity, *, actor_id: ActorId, occurred_at: datetime
    ) -> PlayMonthlyPlan:
        """Append a teacher's new row at the end of a section (M2-D03)."""
        self.ensure_mutable("add_activity")
        rows = self._rows(section)
        return self._arranged(
            section, _row_ids(rows), _row_ids((*rows, activity)), actor_id, occurred_at,
            **{section: (*rows, activity)},
        )

    def remove_activity(
        self, name_item_id: ItemId, *, actor_id: ActorId, occurred_at: datetime
    ) -> PlayMonthlyPlan:
        """Drop a row from the document and keep it whole in ``removed_activities`` (I-3)."""
        self.ensure_mutable("remove_activity")
        current = self.activity(name_item_id)
        if current is None:
            raise InvalidDomainValueError(f"PlayMonthlyPlan activity not found: {name_item_id}")
        section = next(s for s in PLAY_SECTIONS if any(a is current for a in getattr(self, s)))
        rows = getattr(self, section)
        kept = tuple(a for a in rows if a is not current)
        return self._arranged(
            section, _row_ids(rows), _row_ids(kept), actor_id, occurred_at,
            **{section: kept},
            removed_activities=(*self.removed_activities, RemovedActivity(section, current)),
        )

    def place_safety(
        self,
        week_id: WeekId,
        candidate_item_id: ItemId | None,
        *,
        actor_id: ActorId,
        occurred_at: datetime,
    ) -> PlayMonthlyPlan:
        """Place a kept safety candidate in one week, or clear it with ``None`` (M2-D08).

        The same candidate may be placed in several weeks."""
        self.ensure_mutable("place_safety")
        current = next((s for s in self.safety_weeks if s.week_id == week_id), None)
        if current is None:
            raise InvalidDomainValueError(f"PlayMonthlyPlan week not found: {week_id}")

        def ids(item_id: ItemId | None) -> tuple[str, ...]:
            return () if item_id is None else (item_id.value,)

        return self._arranged(
            week_id.value, ids(current.candidate_item_id), ids(candidate_item_id), actor_id, occurred_at,
            safety_weeks=tuple(
                SafetyWeek(week_id, candidate_item_id) if s is current else s for s in self.safety_weeks
            ),
        )

    def _rows(self, section: str) -> tuple[PlayActivity, ...]:
        if section not in PLAY_SECTIONS:
            raise InvalidDomainValueError(f"Unknown play section: {section}")
        return getattr(self, section)

    def _arranged(
        self,
        scope: str,
        before: tuple[str, ...],
        after: tuple[str, ...],
        actor_id: ActorId,
        occurred_at: datetime,
        **changes: object,
    ) -> PlayMonthlyPlan:
        event = AuditEvent(
            event_type=AuditEventType.ARRANGEMENT_CHANGED,
            occurred_at=occurred_at,
            plan_id=self.plan_id,
            actor_id=actor_id,
            arrangement_change=ArrangementChange(scope, before, after),
        )
        return replace(self, audit=self.audit.append(event), **changes)

    def confirm(self, *, actor_id: ActorId, occurred_at: datetime) -> PlayMonthlyPlan:
        self.ensure_mutable("confirm")
        event = AuditEvent(
            event_type=AuditEventType.CONFIRMED,
            occurred_at=occurred_at,
            plan_id=self.plan_id,
            actor_id=actor_id,
        )
        return replace(self, status=PlanStatus.CONFIRMED, audit=self.audit.append(event))


def _row_ids(rows: tuple[PlayActivity, ...]) -> tuple[str, ...]:
    return tuple(a.cell.item_id.value for a in rows)
