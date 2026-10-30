"""Generate a DRAFT play-centred monthly plan (PLAY_MONTHLY) from a CONFIRMED play-project yearly plan.

First Core unit: generation only, fake provider, InMemory storage. Edit, weekly safety
placement and confirm are later units; this result already carries what they need — stable
item ids, blank teacher-input cells, and safety candidates kept apart from the (unplaced)
weekly placement. Every gate runs before the provider is called; a failure stores nothing.

The parent Domain has no institution field. This use case compares ``classroom_ref`` only;
institution isolation belongs to the parent repository's scope and the backend permission check.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from typing import Protocol

from ..domain.curriculum_reference import CurriculumCatalog
from ..domain.daily_life_reference import DailyLifeCatalog, DailyLifeEntry, DailyLifeKind
from ..domain.drill_topic_reference import DrillTopic, DrillTopicCatalog
from ..domain.errors import DomainError, InvalidDomainValueError
from ..domain.identifiers import PlanId
from ..domain.lineage import ParentLineage
from ..domain.plan import PlanStatus
from ..domain.play_monthly_plan import (
    DAYS,
    DIRECTION_COPY_RULE_ID,
    DIRECTION_KEY,
    DISPLAY_KEYS,
    DISPLAY_RULE_ID,
    DRILL_CELL_KEY,
    SPECIAL_ACTIVITY_KEY,
    DocumentDisplay,
    DrillCandidate,
    EntryCell,
    HabitWeek,
    LayoutRole,
    LayoutSection,
    ParentPlay,
    ParentPlaySnapshot,
    PlayActivity,
    PlayMonthlyCell,
    PlayMonthlyLayout,
    PlayMonthlyPlan,
    PlayMonthlyReferences,
    SafetyCandidate,
    SafetyWeek,
    TimetableNode,
    TimetableSize,
    specialized_keys,
)
from ..domain.play_project_plan import PlayProjectYearlyPlan
from ..domain.provenance import (
    AuditEvent,
    AuditEventType,
    AuditHistory,
    EvidenceSource,
    EvidenceSourceType,
    GenerationMethod,
    GenerationMethodDetail,
    SplitAxis,
)
from ..domain.safety_placement import SafetyKind
from ..domain.safety_rule import SafetyLegalRule
from ..domain.year_month import YearMonth
from ..evidence.models import SourceSection
from ..evidence.ports import InstitutionEvidenceRepository
from ..evidence.safety_classification import SafetyEvidenceClassification, SafetyReferenceKind
from ..evidence.safety_quality import SafetyReferenceQuality
from ..planner.contracts import ProposalRejectedError
from ..planner.play_monthly import (
    PLAY_MONTHLY_PROMPT_VERSION,
    PLAY_MONTHLY_REPAIR_PROMPT_VERSION,
    PlayMonthlyIssue,
    PlayMonthlyProvider,
    SafetySlot,
    build_play_monthly_request,
    build_repair_request,
    changed_locations,
    parent_ref,
    parse_play_monthly_proposal,
    repair_scope_issues,
    section_of,
    validate_play_monthly,
)
from ..rules.monthly_week_periods import canonical_week_periods
from ..rules.safety_placement import (
    STATUTORY_SHORT_LABELS,
    official_ref,
    select_supplemental_primaries,
)
from .generate_play_project_plan import CurriculumReferenceRepository
from .play_project_lifecycle import PLAY_PROJECT_LAYOUTS
from .ports import Clock, IdGenerator, PlanRepository, SafetyLegalRuleRepository

SYSTEM_ACTOR = "play_monthly_application"
RULE_ID = "play_monthly.generate"
LIFE_SAFETY_LABEL = "life_safety"
LIFE_SAFETY_SLOTS = ("life_safety_1", "life_safety_2")

# Header layout measured from the reference monthly plan, not a national standard. Specialized-
# program sub-headers are that institution's own programs and are not reproduced.
# v0.2.0 (2026-10-28): the centre play direction holds a value (a copy of the theme), and both
# timetables are written cell by cell (TEACHER_TABLE) instead of as one text each.
PLAY_MONTHLY_LAYOUT_V0_2 = PlayMonthlyLayout(
    layout_version="play-monthly-layout-v0.2.0",
    sections=tuple(
        LayoutSection(key, label, role)
        for key, label, role in (
            ("theme", "놀이 주제", LayoutRole.GENERATED),
            ("expected_period", "예상 기간", LayoutRole.CALENDAR),
            ("rationale", "주제선정이유", LayoutRole.GENERATED),
            ("expected_play_direction", "예상되는 놀이 방향", LayoutRole.GENERATED),
            ("together", "함께 하는 활동", LayoutRole.GENERATED),
            ("free_play", "유아 예상 자유놀이", LayoutRole.GENERATED),
            ("basic_habits", "기본생활습관", LayoutRole.GENERATED),
            ("safety_education", "안전교육", LayoutRole.GENERATED),
            ("fire_disaster_drill", "소방대피/재난대비", LayoutRole.TEACHER_INPUT),
            ("health_nutrition", "건강‧영양교육", LayoutRole.GENERATED),
            ("specialized_timetable", "특성화 시간표", LayoutRole.TEACHER_TABLE),
            ("special_activity_timetable", "특별활동 시간표", LayoutRole.TEACHER_TABLE),
            ("class_notice", "우리반 안내사항", LayoutRole.TEACHER_INPUT),
            ("class_birthdays", "우리반 생일", LayoutRole.TEACHER_INPUT),
            ("home_connection", "가정연계", LayoutRole.TEACHER_INPUT),
        )
    ),
    together_count=5,
    free_play_count=5,
    drill_candidate_count=5,  # M2-D15: candidates, not a drill frequency
)

# The special-activity parts as the approved template draws them (전달본 rows 20~21): None is a
# cell, (axis, first-part percent, first, second) a boundary. Percents are the template's widths
# and heights, rounded; columns are equal and the two rows are 24 mm together.
_ROW = (SplitAxis.HORIZONTAL, 36, None, None)
SPECIAL_ACTIVITY_START = (
    (SplitAxis.VERTICAL, 48, _ROW, _ROW),
    _ROW,
    (SplitAxis.VERTICAL, 48, _ROW, _ROW),
    None,
    (SplitAxis.HORIZONTAL, 33, None, None),
)
SPECIAL_ACTIVITY_START_SIZE = TimetableSize((20, 20, 20, 20, 20), 24)


class PlayMonthlyGenerationError(DomainError):
    """Internal gate failure; ``code`` is not a public API error code."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class DailyLifeReferenceRepository(Protocol):
    def get_catalog(self, catalog_id: str, catalog_version: str) -> DailyLifeCatalog | None: ...


class DrillTopicReferenceRepository(Protocol):
    def get_catalog(self, catalog_id: str, catalog_version: str) -> DrillTopicCatalog | None: ...


class SafetyClassificationRepository(Protocol):
    def get_classification(self) -> SafetyEvidenceClassification: ...


class SafetyQualityRepository(Protocol):
    def get_quality(self) -> SafetyReferenceQuality: ...


@dataclass(frozen=True, slots=True)
class GeneratePlayMonthlyPlanCommand:
    parent_plan_id: PlanId
    classroom_ref: str  # checked by the caller's server, never taken from the parent
    school_year: int
    target_month: YearMonth
    curriculum_catalog_id: str
    curriculum_catalog_version: str
    daily_life_catalog_id: str
    daily_life_catalog_version: str
    legal_rule_version: str
    safety_classification_version: str
    safety_quality_version: str
    drill_catalog_id: str
    drill_catalog_version: str
    emphasized_row_keys: tuple[str, ...] = ()  # optional teacher emphasis among the selected plays
    # The class name the document header starts with (D-10), from the caller's classroom.
    # Blank leaves that header cell for the teacher; it never names or checks the classroom.
    class_name: str = ""


def _fail(code: str) -> PlayMonthlyGenerationError:
    return PlayMonthlyGenerationError(code)


class GeneratePlayMonthlyPlan:
    def __init__(
        self,
        *,
        parent_repository: PlanRepository[PlayProjectYearlyPlan],
        plan_repository: PlanRepository[PlayMonthlyPlan],
        curriculum_repository: CurriculumReferenceRepository,
        daily_life_repository: DailyLifeReferenceRepository,
        drill_repository: DrillTopicReferenceRepository,
        safety_rule_repository: SafetyLegalRuleRepository,
        evidence_repository: InstitutionEvidenceRepository,
        safety_classification_repository: SafetyClassificationRepository,
        safety_quality_repository: SafetyQualityRepository,
        provider: PlayMonthlyProvider,
        clock: Clock,
        id_generator: IdGenerator,
    ) -> None:
        self._parents = parent_repository
        self._plans = plan_repository
        self._curriculum = curriculum_repository
        self._daily_life = daily_life_repository
        self._drills = drill_repository
        self._safety_rules = safety_rule_repository
        self._evidence = evidence_repository
        self._classification = safety_classification_repository
        self._quality = safety_quality_repository
        self._provider = provider
        self._clock = clock
        self._ids = id_generator

    def execute(self, command: GeneratePlayMonthlyPlanCommand) -> PlayMonthlyPlan:
        parent, snapshot = self._parent(command)
        catalog, daily = self._daily_life_references(command)
        drills, drill_topics = self._drill_topics(command, catalog)
        rule, store, life_slots, records = self._safety_references(command)
        month = command.target_month
        weeks = canonical_week_periods(month)
        period = next(p for p in parent.periods if p.period.key == snapshot.period_key)
        statutory_slots = tuple(
            SafetySlot(
                slot=category.category_id,
                kind=SafetyKind.STATUTORY,
                label=STATUTORY_SHORT_LABELS.get(category.category_id, category.official_label),
                allowed=tuple(
                    (official_ref(category.category_id, i), item)
                    for i, item in enumerate(category.content_items, 1)
                ),
                category_id=category.category_id,
            )
            for category in rule.categories
        )
        layout = PLAY_MONTHLY_LAYOUT_V0_2
        counts = {"together": layout.together_count, "free_play": layout.free_play_count}
        request = build_play_monthly_request(
            target_month=month.value,
            month_label=f"{month.calendar_month}월",
            ages=parent.target_ages,
            weeks=tuple((w.week_id.value, w.display_label) for w in weeks),
            counts=counts,
            period_label=period.period.label,
            parent_plays=tuple(
                (
                    parent_ref(snapshot.period_key, p.row_key),
                    p.play_name,
                    p.materials,
                    p.support_direction,
                    p.row_key in snapshot.emphasized,
                )
                for p in snapshot.plays
            ),
            catalog=catalog,
            safety_slots=statutory_slots + life_slots,
            habit_entries=daily.of_kind(DailyLifeKind.HABIT),
            health_entries=daily.of_kind(DailyLifeKind.HEALTH),
            nutrition_entries=daily.of_kind(DailyLifeKind.NUTRITION),
            drill_topics=tuple((t.topic_id, t.label, t.situation) for t in drill_topics),
            reference_versions=(
                PLAY_MONTHLY_LAYOUT_V0_2.layout_version,
                catalog.catalog_version,
                daily.catalog_version,
                drills.catalog_version,
                rule.legal_rule_version,
                store.ingestion_version,
                store.content_sha256,
                command.safety_classification_version,
                command.safety_quality_version,
            ),
        )

        response = self._provider.generate_play_monthly(request)
        proposal = parse_play_monthly_proposal(response.content)
        issues = validate_play_monthly(proposal, request)
        changed: frozenset[str] = frozenset()
        if issues:
            repair = build_repair_request(request, response.content, issues)
            repaired = parse_play_monthly_proposal(self._provider.generate_play_monthly(repair).content)
            changed = changed_locations(proposal, repaired)
            remaining = validate_play_monthly(repaired, request) + repair_scope_issues(changed, issues)
            if remaining:
                raise _rejected(remaining)
            proposal = repaired

        plan_id = self._ids.new_plan_id()
        now = self._clock.now()

        def created(item_id=None) -> AuditHistory:
            return AuditHistory(
                (
                    AuditEvent(
                        event_type=AuditEventType.CREATED,
                        occurred_at=now,
                        plan_id=plan_id,
                        item_id=item_id,
                        system_actor=SYSTEM_ACTOR,
                    ),
                )
            )

        def cell(
            location: str, semantic_key: str | None, value: str, evidence: tuple[EvidenceSource, ...]
        ) -> PlayMonthlyCell:
            """``semantic_key=None``: a list row, addressed by its own item id, never its position."""
            repaired_here = location in changed or section_of(location) in changed
            item_id = self._ids.new_item_id()
            return PlayMonthlyCell(
                item_id=item_id,
                semantic_key=semantic_key or f"{section_of(location)}.{item_id.value}",
                value=value,
                evidence=evidence,
                generation=GenerationMethodDetail(
                    method=GenerationMethod.RULE_LLM,
                    rule_id=RULE_ID,
                    rule_version=(
                        PLAY_MONTHLY_REPAIR_PROMPT_VERSION if repaired_here else PLAY_MONTHLY_PROMPT_VERSION
                    ),
                ),
                audit=created(item_id),
            )

        parent_period = EvidenceSource(
            EvidenceSourceType.PARENT_PLAN,
            parent.plan_id.value,
            snapshot.period_key,
            display_name=period.period.label,
        )

        def blank(semantic_key: str) -> PlayMonthlyCell:
            item_id = self._ids.new_item_id()
            return PlayMonthlyCell(item_id=item_id, semantic_key=semantic_key, audit=created(item_id))

        def copy(
            semantic_key: str, rule_id: str, value: str, evidence: tuple[EvidenceSource, ...]
        ) -> PlayMonthlyCell:
            """A value the Rule copies once; a blank one is left for the teacher (no generation)."""
            if not value.strip():
                return blank(semantic_key)
            item_id = self._ids.new_item_id()
            return PlayMonthlyCell(
                item_id=item_id,
                semantic_key=semantic_key,
                value=value,
                evidence=evidence,
                generation=GenerationMethodDetail(GenerationMethod.RULE_ONLY, rule_id, layout.layout_version),
                audit=created(item_id),
            )

        def timetable(day: str, shape, numbers) -> TimetableNode:
            if shape is None:
                return TimetableNode(cell=blank(f"{SPECIAL_ACTIVITY_KEY}.{day}.{next(numbers)}"))
            axis, ratio, first, second = shape
            split_id = self._ids.new_item_id()
            parts = (timetable(day, first, numbers), timetable(day, second, numbers))
            return TimetableNode(split_id=split_id, axis=axis, ratio=ratio, children=parts)

        last_day = calendar.monthrange(month.calendar_year, month.calendar_month)[1]
        calendar_source = EvidenceSource(EvidenceSourceType.CALENDAR, month.value)
        classroom_source = EvidenceSource(EvidenceSourceType.CLASSROOM_PROFILE, command.classroom_ref)

        def curriculum(content_id: str) -> EvidenceSource:
            return EvidenceSource(EvidenceSourceType.CURRICULUM, content_id, catalog.catalog_version)

        def activities(section: str) -> tuple[PlayActivity, ...]:
            rows = []
            for index, row in enumerate(getattr(proposal, section)):
                evidence = tuple(curriculum(c) for c in row.content_ids)
                lineage = None
                if row.parent_ref is not None:
                    play = snapshot.play(row.parent_ref.split(".", 1)[1])
                    evidence += (
                        EvidenceSource(
                            EvidenceSourceType.PARENT_PLAN,
                            parent.plan_id.value,
                            snapshot.period_key,
                            display_name=play.play_name,
                        ),
                    )
                    lineage = ParentLineage(
                        parent_plan_id=parent.plan_id,
                        confirmed_at=snapshot.lineage.confirmed_at,
                        confirmed_by=snapshot.lineage.confirmed_by,
                        parent_item_id=play.play_name_item_id,
                        snapshot_value=play.play_name,
                    )
                name = cell(f"{section}[{index}]", None, row.name, evidence)
                description = cell(
                    f"{section}[{index}].description", f"{name.semantic_key}.description", row.description, evidence
                )
                rows.append(PlayActivity(name, description, row.content_ids, lineage))
            return tuple(rows)

        def entry_cell(location: str, semantic_key: str, entry: DailyLifeEntry) -> EntryCell:
            return EntryCell(cell(location, semantic_key, entry.text, (curriculum(entry.content_id),)), entry.entry_id)

        def safety(item) -> SafetyCandidate:
            slot = next(s for s in request.safety_slots if s.slot == item.slot)
            texts = dict(slot.allowed)
            if slot.kind is SafetyKind.STATUTORY:
                evidence = tuple(
                    EvidenceSource(EvidenceSourceType.SAFETY_RULE, ref, rule.legal_rule_version, display_name=texts[ref])
                    for ref in item.refs
                )
            else:
                evidence = tuple(
                    EvidenceSource(
                        EvidenceSourceType.INSTITUTION_SAMPLE,
                        ref,
                        store.ingestion_version,
                        display_name=records[ref].source_label,
                    )
                    for ref in item.refs
                )
            return SafetyCandidate(
                cell(f"safety:{slot.slot}", f"safety_education.{slot.slot}", item.text, evidence),
                slot.kind,
                category_id=slot.category_id,
                topic_group=slot.topic_group,
            )

        drill_texts = dict(proposal.drills)
        by_slot = {item.slot: item for item in proposal.safety}
        habits = dict(proposal.habits)
        plan = PlayMonthlyPlan(
            plan_id=plan_id,
            school_year=command.school_year,
            classroom_ref=command.classroom_ref,
            target_month=month,
            target_ages=parent.target_ages,
            status=PlanStatus.DRAFT,
            layout=layout,
            weeks=weeks,
            parent=snapshot,
            references=PlayMonthlyReferences(
                curriculum_catalog_id=catalog.catalog_id,
                curriculum_catalog_version=catalog.catalog_version,
                daily_life_catalog_id=daily.catalog_id,
                daily_life_catalog_version=daily.catalog_version,
                legal_rule_version=rule.legal_rule_version,
                evidence_store_version=store.ingestion_version,
                evidence_store_sha256=store.content_sha256,
                safety_classification_version=command.safety_classification_version,
                safety_quality_version=command.safety_quality_version,
                drill_catalog_id=drills.catalog_id,
                drill_catalog_version=drills.catalog_version,
                prompt_version=PLAY_MONTHLY_PROMPT_VERSION,
                request_fingerprint=request.fingerprint,
            ),
            # Theme and rationale are written from the parent period's selected plays.
            theme=cell("theme", "theme", proposal.theme, (parent_period,)),
            rationale=cell("rationale", "rationale", proposal.rationale, (parent_period,)),
            together=activities("together"),
            free_play=activities("free_play"),
            habits=tuple(
                HabitWeek(
                    w.week_id,
                    entry_cell(
                        f"habits:{w.week_id.value}",
                        f"basic_habits.{w.week_id.value}",
                        daily.get(habits[w.week_id.value]),
                    ),
                )
                for w in weeks
            ),
            safety_candidates=tuple(safety(by_slot[s.slot]) for s in request.safety_slots),
            safety_weeks=tuple(SafetyWeek(w.week_id) for w in weeks),
            health=entry_cell("health", "health_nutrition.health", daily.get(proposal.health_entry_id)),
            nutrition=entry_cell("nutrition", "health_nutrition.nutrition", daily.get(proposal.nutrition_entry_id)),
            drill_candidates=tuple(
                DrillCandidate(
                    cell(
                        f"drills:{topic.topic_id}",
                        f"{DRILL_CELL_KEY}.candidate.{topic.topic_id}",
                        drill_texts[topic.topic_id],
                        (curriculum(topic.content_id),),
                    ),
                    topic.topic_id,
                    topic.label,
                )
                for topic in drill_topics
            ),
            teacher_inputs=tuple(blank(key) for key in layout.teacher_input_keys),
            direction=copy(DIRECTION_KEY, DIRECTION_COPY_RULE_ID, proposal.theme, (parent_period,)),
            display=DocumentDisplay(
                *(
                    copy(key, DISPLAY_RULE_ID, value, (source,))
                    for key, value, source in zip(
                        DISPLAY_KEYS,
                        (
                            f"{month.calendar_month}월 놀이계획안",
                            "만 " + "·".join(str(age) for age in sorted(parent.target_ages)) + "세",
                            " ".join(command.class_name.split()),
                            f"{month.calendar_year}.{month.calendar_month:02d}.01 ~ "
                            f"{month.calendar_year}.{month.calendar_month:02d}.{last_day:02d}",
                        ),
                        (calendar_source, classroom_source, classroom_source, calendar_source),
                        strict=True,
                    )
                )
            ),
            specialized_timetable=tuple(blank(key) for key in specialized_keys()),
            special_activity=tuple(
                timetable(day, start, iter(range(1, 9))) for day, start in zip(DAYS, SPECIAL_ACTIVITY_START, strict=True)
            ),
            special_activity_size=SPECIAL_ACTIVITY_START_SIZE,
            audit=created(),
        )
        self._plans.save(plan.plan_id, plan)
        return plan

    def _parent(self, command: GeneratePlayMonthlyPlanCommand) -> tuple[PlayProjectYearlyPlan, ParentPlaySnapshot]:
        month = command.target_month
        if not isinstance(month, YearMonth):
            raise _fail("TARGET_MONTH_INVALID")
        if month.calendar_year - (1 if month.calendar_month < 3 else 0) != command.school_year:
            raise _fail("TARGET_MONTH_OUTSIDE_SCHOOL_YEAR")
        parent = self._parents.get(command.parent_plan_id)
        if parent is None:
            raise _fail("PARENT_NOT_FOUND")
        if not isinstance(parent, PlayProjectYearlyPlan):
            raise _fail("PARENT_NOT_PLAY_PROJECT")
        if parent.status is not PlanStatus.CONFIRMED:
            raise _fail("PARENT_NOT_CONFIRMED")
        if parent.classroom_ref != command.classroom_ref:
            raise _fail("PARENT_CLASSROOM_MISMATCH")
        if parent.school_year != command.school_year:
            raise _fail("PARENT_SCHOOL_YEAR_MISMATCH")
        layout = PLAY_PROJECT_LAYOUTS.get(parent.layout_version)
        if layout is None:
            raise _fail("PARENT_LAYOUT_UNKNOWN")
        # 12월 · 1월 · 2월 share one season, so the period is found by month, not by order.
        period = next((p for p in parent.periods if month.calendar_month in p.period.months), None)
        if period is None:
            raise _fail("PARENT_PERIOD_MISSING")
        if len(period.selected) != layout.selected_per_period:
            raise _fail("PARENT_SELECTION_INCOMPLETE")
        confirmation = next(
            (e for e in reversed(parent.audit.events) if e.event_type is AuditEventType.CONFIRMED),
            None,
        )
        if confirmation is None or confirmation.actor_id is None:
            raise _fail("PARENT_CONFIRMATION_MISSING")
        emphasized = command.emphasized_row_keys
        if len(set(emphasized)) != len(emphasized) or not set(emphasized) <= set(period.selected):
            raise _fail("EMPHASIS_NOT_SELECTED")
        rows = {row.row_key: row for row in period.candidates}
        return parent, ParentPlaySnapshot(
            lineage=ParentLineage(parent.plan_id, confirmation.occurred_at, confirmation.actor_id),
            layout_version=parent.layout_version,
            period_key=period.period.key,
            plays=tuple(
                ParentPlay(
                    row_key=key,
                    play_name_item_id=rows[key].play_name.item_id,
                    play_name=rows[key].play_name.value,
                    materials=rows[key].materials.value,
                    support_direction=rows[key].support_direction.value,
                )
                for key in period.selected
            ),
            emphasized=emphasized,
        )

    def _daily_life_references(
        self, command: GeneratePlayMonthlyPlanCommand
    ) -> tuple[CurriculumCatalog, DailyLifeCatalog]:
        catalog = self._curriculum.get_catalog(command.curriculum_catalog_id, command.curriculum_catalog_version)
        if catalog is None:
            raise _fail("CURRICULUM_REFERENCE_NOT_FOUND")
        if not catalog.is_active:
            raise _fail("CURRICULUM_REFERENCE_NOT_ACTIVE")
        daily = self._daily_life.get_catalog(command.daily_life_catalog_id, command.daily_life_catalog_version)
        if daily is None:
            raise _fail("DAILY_LIFE_REFERENCE_NOT_FOUND")
        if not daily.is_active:
            raise _fail("DAILY_LIFE_REFERENCE_NOT_ACTIVE")
        if (daily.curriculum_catalog_id, daily.curriculum_catalog_version) != (
            catalog.catalog_id,
            catalog.catalog_version,
        ):
            raise _fail("DAILY_LIFE_CURRICULUM_MISMATCH")
        if any(catalog.get(entry.content_id) is None for entry in daily.entries):
            raise _fail("DAILY_LIFE_UNKNOWN_CONTENT_ID")
        if any(not daily.of_kind(kind) for kind in DailyLifeKind):
            raise _fail("DAILY_LIFE_REFERENCE_INCOMPLETE")
        return catalog, daily

    def _drill_topics(
        self, command: GeneratePlayMonthlyPlanCommand, catalog: CurriculumCatalog
    ) -> tuple[DrillTopicCatalog, tuple[DrillTopic, ...]]:
        drills = self._drills.get_catalog(command.drill_catalog_id, command.drill_catalog_version)
        if drills is None:
            raise _fail("DRILL_REFERENCE_NOT_FOUND")
        if not drills.is_active:
            raise _fail("DRILL_REFERENCE_NOT_ACTIVE")
        if (drills.curriculum_catalog_id, drills.curriculum_catalog_version) != (
            catalog.catalog_id,
            catalog.catalog_version,
        ):
            raise _fail("DRILL_CURRICULUM_MISMATCH")
        if any(catalog.get(topic.content_id) is None for topic in drills.topics):
            raise _fail("DRILL_UNKNOWN_CONTENT_ID")
        count = PLAY_MONTHLY_LAYOUT_V0_2.drill_candidate_count
        eligible = drills.for_month(command.target_month.calendar_month)
        # Month-limited topics (e.g. 폭설 in winter) first, then catalog order.
        # ponytail: fixed order, so a month without a seasonal topic always gets the same five;
        # add rotation only if teachers ask for variety.
        topics = sorted(eligible, key=lambda t: len(t.applicable_months) == 12)[:count]
        if len(topics) < count:
            raise _fail("DRILL_TOPICS_INSUFFICIENT")
        return drills, tuple(topics)

    def _safety_references(self, command: GeneratePlayMonthlyPlanCommand):
        rule: SafetyLegalRule | None = self._safety_rules.get_legal_rule(command.legal_rule_version)
        if rule is None:
            raise _fail("SAFETY_RULE_NOT_FOUND")
        if not rule.is_active:
            raise _fail("SAFETY_RULE_NOT_ACTIVE")
        if any(not category.content_items for category in rule.categories):
            raise _fail("SAFETY_RULE_INCOMPLETE")
        store = self._evidence.get_store()
        classification = self._classification.get_classification()
        quality = self._quality.get_quality()
        if not (classification.runtime_active and quality.runtime_active):
            raise _fail("SAFETY_EVIDENCE_NOT_ACTIVE")
        if (classification.classification_version, quality.quality_version) != (
            command.safety_classification_version,
            command.safety_quality_version,
        ):
            raise _fail("SAFETY_EVIDENCE_VERSION_MISMATCH")
        try:
            classification.require_bound_to(store.content_sha256)
            classification.require_legal_rule(rule)
            quality.require_bound_to(store.content_sha256, classification.classification_version)
        except InvalidDomainValueError:
            raise _fail("SAFETY_EVIDENCE_STORE_MISMATCH") from None

        month = command.target_month.calendar_month
        records = {}
        candidates = []
        # Target month first (tier 0), then other months' approved MONTH_INDEPENDENT contents.
        for record in sorted(store.records, key=lambda r: (r.month != month, r.record_id)):
            if not (
                record.general_grounding_eligible
                and record.source_section is SourceSection.SAFETY_EDUCATION
                and record.text is not None
            ):
                continue
            reference = classification.runtime_reference(record)
            if (
                reference is None
                or reference.kind is not SafetyReferenceKind.SUPPLEMENTAL_REFERENCE
                or reference.supplemental_label != LIFE_SAFETY_LABEL
            ):
                continue
            tier = 0 if record.month == month else 1
            group = (
                quality.usable_topic_group(record) if tier == 0 else quality.month_independent_topic_group(record)
            )
            if group is not None:
                records[record.record_id] = record
                candidates.append((record.record_id, LIFE_SAFETY_LABEL, group, tier))
        try:
            picks = select_supplemental_primaries(len(LIFE_SAFETY_SLOTS), tuple(candidates))
        except ValueError:
            # Never shrink the eight-candidate contract to six.
            raise _fail("LIFE_SAFETY_GROUNDING_INSUFFICIENT") from None
        groups = {ref: group for ref, _, group, _ in candidates}
        slots = tuple(
            SafetySlot(
                slot=slot,
                kind=SafetyKind.SUPPLEMENTAL,
                label="생활안전",
                allowed=tuple((ref, records[ref].text) for ref in (primary, *support)),
                topic_group=groups[primary],
            )
            for slot, (primary, support) in zip(LIFE_SAFETY_SLOTS, picks)
        )
        return rule, store, slots, records


def _rejected(issues: tuple[PlayMonthlyIssue, ...]) -> ProposalRejectedError:
    return ProposalRejectedError(tuple(dict.fromkeys(i.code for i in issues)), issues)
