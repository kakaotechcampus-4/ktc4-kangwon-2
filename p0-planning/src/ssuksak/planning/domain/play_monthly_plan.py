"""Play-centred monthly plan (PLAY_MONTHLY): a separate aggregate from the v1 ``MonthlyPlan``.

Its parent is a CONFIRMED ``PlayProjectYearlyPlan``. The plan keeps the header layout it was
made with, the parent plays it read, the Reference versions it used, and values that may be
blank: teacher-input cells start empty, and safety candidates are kept apart from the weekly
placement, which starts unplaced. Every list row and candidate is addressed by its ``ItemId``,
never by its position. A row a teacher deletes leaves the document but stays whole in
``removed_activities``; adding, deleting and placing are plan-level ARRANGEMENT_CHANGED events.

Layout v0.2.0 (2026-10-28 D-1 ~ D-10) adds cells the teacher owns. The play direction is the
theme copied once at generation and then edited on its own (never refilled). The display
strings (title · ages · class · period) only print: editing them never moves the month, the
ages or the weeks. The specialized timetable is five titles over five contents. The
special-activity timetable is one tree per weekday: a split keeps the cell (id, value, history)
as the first part and adds one new cell, a boundary keeps its ``split_id`` until it is removed,
a removed cell stays whole in ``removed_timetable_cells``, and splitting, removing and
resizing are plan-level TIMETABLE_CHANGED events with the numbers before and after.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import Enum
from fractions import Fraction

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
    SplitAxis,
    TimetableChange,
    TimetableOperation,
)
from .safety_placement import SafetyKind
from .week_period import WeekId, WeekPeriod
from .year_month import YearMonth

PLAY_MONTHLY_FORMAT = "PLAY_MONTHLY"
PLAY_SECTIONS = ("together", "free_play")
DRILL_CELL_KEY = "fire_disaster_drill"
DRILL_COPY_RULE_ID = "play_monthly.drill_copy"
DIRECTION_KEY = "expected_play_direction"
DIRECTION_COPY_RULE_ID = "play_monthly.direction_copy"
DISPLAY_RULE_ID = "play_monthly.document_display"
DISPLAY_KEYS = ("document_title", "age_label", "class_name", "expected_period")
SPECIALIZED_KEY = "specialized_timetable"
SPECIALIZED_COLUMNS = 5
SPECIAL_ACTIVITY_KEY = "special_activity_timetable"
DAYS = ("mon", "tue", "wed", "thu", "fri")  # the timetable always keeps Monday to Friday
# Limits (2026-10-28 D-3). Every cell keeps at least 3.5 % of the table width (about 6.3 mm on
# the approved template): narrower cells clip their text, and below about 4 mm Hangul widens the
# whole table past the page margin. The other limits stay as first set.
MAX_SPLIT_DEPTH = 4
SPLIT_RATIO_RANGE = (10, 90)  # a boundary's first part, percent
COLUMN_MIN_PERCENT = 5
CELL_MIN_WIDTH_PERCENT = Fraction(7, 2)  # day width x the left/right ratios above the cell
HEIGHT_MM_RANGE = (16, 80)


def _non_blank(value: object, path: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise InvalidDomainValueError(f"{path} must be a non-blank string")


class LayoutRole(str, Enum):
    TITLE = "TITLE"  # a printed group header with no value
    CALENDAR = "CALENDAR"  # filled from the system calendar (예상 기간)
    GENERATED = "GENERATED"
    TEACHER_INPUT = "TEACHER_INPUT"  # starts blank; never generated
    TEACHER_TABLE = "TEACHER_TABLE"  # teacher-written table, addressed cell by cell


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
class DocumentDisplay:
    """What the document header shows (2026-10-28 D-2). Copied from the plan at generation,
    then edited freely, blanks included; editing never changes the classroom, ages, month or weeks.
    """

    title: PlayMonthlyCell
    age: PlayMonthlyCell
    class_name: PlayMonthlyCell
    period: PlayMonthlyCell

    def cells(self) -> tuple[PlayMonthlyCell, ...]:
        return (self.title, self.age, self.class_name, self.period)

    def __post_init__(self) -> None:
        cells = self.cells()
        if not all(isinstance(c, PlayMonthlyCell) for c in cells):
            raise InvalidDomainValueError("DocumentDisplay values must be PlayMonthlyCell")
        if tuple(c.semantic_key for c in cells) != DISPLAY_KEYS:
            raise InvalidDomainValueError("DocumentDisplay cells must follow DISPLAY_KEYS")
        for c in cells:
            if c.generation is not None and c.generation.method is not GenerationMethod.MANUAL and (
                c.generation.rule_id != DISPLAY_RULE_ID
            ):
                raise InvalidDomainValueError("A display cell is the display copy or MANUAL")
            if not c.cites_only(EvidenceSourceType.CALENDAR, EvidenceSourceType.CLASSROOM_PROFILE):
                raise InvalidDomainValueError("A display cell cites CALENDAR and CLASSROOM_PROFILE only")


class TimetableTooNarrowError(InvalidDomainValueError):
    """A timetable cell would be narrower than ``CELL_MIN_WIDTH_PERCENT`` of the table."""


@dataclass(frozen=True, slots=True)
class TimetableNode:
    """One part of a day in the special-activity timetable: a cell, or a boundary splitting a
    part in two. A boundary has its own ``split_id`` so a resize names it even after other
    parts are removed; ``ratio`` is its first part's percent. One dataclass for both shapes so
    the plan codec reads it back."""

    cell: PlayMonthlyCell | None = None
    split_id: ItemId | None = None
    axis: SplitAxis | None = None
    ratio: int | None = None
    children: tuple[TimetableNode, ...] = ()

    def __post_init__(self) -> None:
        if self.cell is not None:
            if not isinstance(self.cell, PlayMonthlyCell) or (
                self.split_id, self.axis, self.ratio, self.children
            ) != (None, None, None, ()):
                raise InvalidDomainValueError("A timetable cell node holds its cell only")
            return
        low, high = SPLIT_RATIO_RANGE
        if (
            not isinstance(self.split_id, ItemId)
            or not isinstance(self.axis, SplitAxis)
            or type(self.ratio) is not int
            or not low <= self.ratio <= high
            or not isinstance(self.children, tuple)
            or len(self.children) != 2
            or not all(isinstance(c, TimetableNode) for c in self.children)
        ):
            raise InvalidDomainValueError("A timetable boundary needs split_id, axis, ratio and two parts")

    @property
    def depth(self) -> int:
        return 0 if self.cell is not None else 1 + max(c.depth for c in self.children)

    def narrowest(self, width: Fraction) -> Fraction:
        """The narrowest cell's width when this part is ``width`` wide; top/bottom keeps the width."""
        if self.cell is not None:
            return width
        first, second = self.children
        if self.axis is SplitAxis.VERTICAL:
            return min(first.narrowest(width), second.narrowest(width))
        part = width * self.ratio / 100
        return min(first.narrowest(part), second.narrowest(width - part))

    def leaves(self) -> tuple[PlayMonthlyCell, ...]:
        if self.cell is not None:
            return (self.cell,)
        return tuple(leaf for c in self.children for leaf in c.leaves())

    def boundaries(self) -> tuple[TimetableNode, ...]:
        if self.cell is not None:
            return ()
        return (self, *(b for c in self.children for b in c.boundaries()))

    def rebuilt(self, visit: Callable[[TimetableNode], TimetableNode | None]) -> TimetableNode:
        """A copy where ``visit`` may replace any node; ``None`` keeps it and looks inside."""
        found = visit(self)
        if found is not None:
            return found
        if self.cell is not None:
            return self
        return replace(self, children=tuple(c.rebuilt(visit) for c in self.children))


@dataclass(frozen=True, slots=True)
class TimetableSize:
    column_widths: tuple[int, ...]  # Monday to Friday, percent of the table width
    height_mm: int

    def __post_init__(self) -> None:
        widths = self.column_widths
        if (
            not isinstance(widths, tuple)
            or len(widths) != len(DAYS)
            or not all(type(w) is int and w >= COLUMN_MIN_PERCENT for w in widths)
            or sum(widths) != 100
        ):
            raise InvalidDomainValueError(
                f"TimetableSize needs {len(DAYS)} int percents of at least {COLUMN_MIN_PERCENT}, summing to 100"
            )
        low, high = HEIGHT_MM_RANGE
        if type(self.height_mm) is not int or not low <= self.height_mm <= high:
            raise InvalidDomainValueError(f"TimetableSize.height_mm must be {low}~{high}")


def specialized_keys() -> tuple[str, ...]:
    """Five title cells, then the five content cells under them."""
    return tuple(
        f"{SPECIALIZED_KEY}.{part}.{i}" for part in ("header", "content") for i in range(SPECIALIZED_COLUMNS)
    )


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
    # 2026-10-28 (layout v0.2.0): the centre play direction and the header strings are copied
    # once at generation and then edited on their own; the timetables are written cell by cell.
    direction: PlayMonthlyCell
    display: DocumentDisplay
    specialized_timetable: tuple[PlayMonthlyCell, ...]
    special_activity: tuple[TimetableNode, ...]  # Monday to Friday
    special_activity_size: TimetableSize
    audit: AuditHistory = field(default_factory=AuditHistory)
    removed_activities: tuple[RemovedActivity, ...] = ()
    # A timetable cell a teacher removed, kept whole for history (D-7). Never printed.
    removed_timetable_cells: tuple[PlayMonthlyCell, ...] = ()
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
        self._check_document_cells()
        # Archived rows and cells keep their ids, so a removed id is never used again.
        cells = (
            *self.cells(),
            *(c for r in self.removed_activities for c in (r.activity.cell, r.activity.description)),
            *self.removed_timetable_cells,
        )
        for name in ("item_id", "semantic_key"):
            values = [getattr(cell, name) for cell in cells]
            if name == "item_id":
                values += [b.split_id for day in self.special_activity for b in day.boundaries()]
            if len(values) != len(set(values)):
                raise InvalidDomainValueError(f"PlayMonthlyPlan {name}s must be unique")

    def _check_document_cells(self) -> None:
        if not isinstance(self.direction, PlayMonthlyCell) or self.direction.semantic_key != DIRECTION_KEY:
            raise InvalidDomainValueError(f"PlayMonthlyPlan.direction must be the {DIRECTION_KEY} cell")
        if self.direction.generation is not None and self.direction.generation.method is not (
            GenerationMethod.MANUAL
        ) and self.direction.generation.rule_id != DIRECTION_COPY_RULE_ID:
            raise InvalidDomainValueError("The direction cell is the theme copy or MANUAL")
        if not self.direction.cites_only(EvidenceSourceType.PARENT_PLAN):
            raise InvalidDomainValueError("The direction cell cites PARENT_PLAN only, like the theme")
        if not isinstance(self.display, DocumentDisplay):
            raise InvalidDomainValueError("PlayMonthlyPlan.display must be DocumentDisplay")
        specialized = self.specialized_timetable
        if not isinstance(specialized, tuple) or not all(isinstance(c, PlayMonthlyCell) for c in specialized):
            raise InvalidDomainValueError("specialized_timetable must be PlayMonthlyCell values")
        if tuple(c.semantic_key for c in specialized) != specialized_keys():
            raise InvalidDomainValueError("specialized_timetable must follow its ten cell keys")
        days = self.special_activity
        if not isinstance(days, tuple) or len(days) != len(DAYS) or not all(
            isinstance(d, TimetableNode) for d in days
        ):
            raise InvalidDomainValueError("special_activity needs one part tree per weekday")
        if any(d.depth > MAX_SPLIT_DEPTH for d in days):
            raise InvalidDomainValueError(f"A timetable day splits at most {MAX_SPLIT_DEPTH} deep")
        for day, tree in zip(DAYS, days, strict=True):
            if not all(c.semantic_key.startswith(f"{SPECIAL_ACTIVITY_KEY}.{day}.") for c in tree.leaves()):
                raise InvalidDomainValueError(f"A {day} timetable cell must use its day's key")
        if not isinstance(self.special_activity_size, TimetableSize):
            raise InvalidDomainValueError("special_activity_size must be TimetableSize")
        widths = self.special_activity_size.column_widths
        if any(tree.narrowest(Fraction(w)) < CELL_MIN_WIDTH_PERCENT for tree, w in zip(days, widths, strict=True)):
            raise TimetableTooNarrowError(
                f"A timetable cell keeps at least {float(CELL_MIN_WIDTH_PERCENT)}% of the table width"
            )
        if not isinstance(self.removed_timetable_cells, tuple) or not all(
            isinstance(c, PlayMonthlyCell) and c.semantic_key.startswith(f"{SPECIAL_ACTIVITY_KEY}.")
            for c in self.removed_timetable_cells
        ):
            raise InvalidDomainValueError("removed_timetable_cells must be timetable cells")
        written = (*specialized, *(c for d in days for c in d.leaves()), *self.removed_timetable_cells)
        if any(c.generation is not None and c.generation.method is not GenerationMethod.MANUAL for c in written):
            raise InvalidDomainValueError("Timetable cells are written by a teacher only")

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
            self.direction,
            *self.display.cells(),
            *self.specialized_timetable,
            *(c for day in self.special_activity for c in day.leaves()),
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
            direction=swap(self.direction),
            display=DocumentDisplay(*(swap(c) for c in self.display.cells())),
            specialized_timetable=tuple(swap(c) for c in self.specialized_timetable),
            special_activity=tuple(
                day.rebuilt(lambda n: TimetableNode(cell=updated) if n.cell is current else None)
                for day in self.special_activity
            ),
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

    def timetable_day(self, item_id: ItemId) -> int | None:
        """The weekday index holding this timetable cell, or ``None``."""
        return next(
            (i for i, day in enumerate(self.special_activity) if any(c.item_id == item_id for c in day.leaves())),
            None,
        )

    def timetable_depth(self, item_id: ItemId) -> int:
        """How many boundaries sit above this timetable cell."""

        def walk(node: TimetableNode, depth: int) -> int | None:
            if node.cell is not None:
                return depth if node.cell.item_id == item_id else None
            return next((d for c in node.children if (d := walk(c, depth + 1)) is not None), None)

        day = self.timetable_day(item_id)
        if day is None:
            raise InvalidDomainValueError(f"PlayMonthlyPlan timetable cell not found: {item_id}")
        return walk(self.special_activity[day], 0)

    def next_timetable_key(self, day: int) -> str:
        """A key never used on that day: removed cells keep theirs, so numbers only grow."""
        prefix = f"{SPECIAL_ACTIVITY_KEY}.{DAYS[day]}."
        used = [
            int(c.semantic_key.removeprefix(prefix))
            for c in (*self.special_activity[day].leaves(), *self.removed_timetable_cells)
            if c.semantic_key.startswith(prefix)
        ]
        return f"{prefix}{max(used, default=0) + 1}"

    def split_timetable_cell(
        self,
        item_id: ItemId,
        axis: SplitAxis,
        *,
        split_id: ItemId,
        new_cell: PlayMonthlyCell,
        actor_id: ActorId,
        occurred_at: datetime,
    ) -> PlayMonthlyPlan:
        """The cell keeps its id, value and history as the first part; ``new_cell`` is the second."""
        self.ensure_mutable("split_timetable_cell")
        day = self.timetable_day(item_id)
        if day is None:
            raise InvalidDomainValueError(f"PlayMonthlyPlan timetable cell not found: {item_id}")

        def split(node: TimetableNode) -> TimetableNode | None:
            if node.cell is None or node.cell.item_id != item_id:
                return None
            return TimetableNode(
                split_id=split_id, axis=axis, ratio=50, children=(node, TimetableNode(cell=new_cell))
            )

        change = TimetableChange(
            TimetableOperation.SPLIT, split_id=split_id, axis=axis, cell_id=item_id, new_cell_id=new_cell.item_id
        )
        return self._timetable_changed(change, actor_id, occurred_at, special_activity=self._days(day, split))

    def remove_timetable_cell(
        self, item_id: ItemId, *, actor_id: ActorId, occurred_at: datetime
    ) -> PlayMonthlyPlan:
        """Drop a cell from the document and keep it whole; its sibling takes the place.

        A weekday's last cell cannot be removed, only cleared."""
        self.ensure_mutable("remove_timetable_cell")
        day = self.timetable_day(item_id)
        if day is None:
            raise InvalidDomainValueError(f"PlayMonthlyPlan timetable cell not found: {item_id}")
        parent = next(
            (
                b for b in self.special_activity[day].boundaries()
                if any(c.cell is not None and c.cell.item_id == item_id for c in b.children)
            ),
            None,
        )
        if parent is None:
            raise InvalidDomainValueError("A weekday keeps at least one timetable cell")
        removed = next(c.cell for c in parent.children if c.cell is not None and c.cell.item_id == item_id)
        sibling = next(c for c in parent.children if c.cell is not removed)
        change = TimetableChange(
            TimetableOperation.REMOVE, split_id=parent.split_id, axis=parent.axis, cell_id=item_id
        )
        return self._timetable_changed(
            change, actor_id, occurred_at,
            special_activity=self._days(day, lambda n: sibling if n is parent else None),
            removed_timetable_cells=(*self.removed_timetable_cells, removed),
        )

    def resize_timetable_split(
        self, split_id: ItemId, ratio: int, *, actor_id: ActorId, occurred_at: datetime
    ) -> PlayMonthlyPlan:
        self.ensure_mutable("resize_timetable")
        day, boundary = next(
            ((i, b) for i, d in enumerate(self.special_activity) for b in d.boundaries() if b.split_id == split_id),
            (None, None),
        )
        if boundary is None:
            raise InvalidDomainValueError(f"PlayMonthlyPlan timetable boundary not found: {split_id}")
        change = TimetableChange(
            TimetableOperation.RESIZE_SPLIT, split_id=split_id, before=(boundary.ratio,), after=(ratio,)
        )
        return self._timetable_changed(
            change, actor_id, occurred_at,
            special_activity=self._days(day, lambda n: replace(n, ratio=ratio) if n is boundary else None),
        )

    def resize_timetable(self, size: TimetableSize, *, actor_id: ActorId, occurred_at: datetime) -> PlayMonthlyPlan:
        """Change the day-column widths or the height; one event per changed measure."""
        self.ensure_mutable("resize_timetable")
        current = self.special_activity_size
        plan = self
        for operation, before, after in (
            (TimetableOperation.RESIZE_COLUMNS, current.column_widths, size.column_widths),
            (TimetableOperation.RESIZE_HEIGHT, (current.height_mm,), (size.height_mm,)),
        ):
            if before != after:
                plan = plan._timetable_changed(
                    TimetableChange(operation, before=before, after=after), actor_id, occurred_at
                )
        return replace(plan, special_activity_size=size)

    def _days(
        self, day: int, visit: Callable[[TimetableNode], TimetableNode | None]
    ) -> tuple[TimetableNode, ...]:
        return tuple(tree.rebuilt(visit) if i == day else tree for i, tree in enumerate(self.special_activity))

    def _timetable_changed(
        self, change: TimetableChange, actor_id: ActorId, occurred_at: datetime, **changes: object
    ) -> PlayMonthlyPlan:
        event = AuditEvent(
            event_type=AuditEventType.TIMETABLE_CHANGED,
            occurred_at=occurred_at,
            plan_id=self.plan_id,
            actor_id=actor_id,
            timetable_change=change,
        )
        return replace(self, audit=self.audit.append(event), **changes)

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
