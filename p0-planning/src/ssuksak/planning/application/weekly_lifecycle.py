"""Teacher edit, one-cell regeneration and confirmation of a DRAFT Weekly Plan
(docs/weekly-plan-contract.md §10-2 · §10-3 · §10-4).

Same flow as the monthly use cases. Verification re-runs on every change: its
findings never block a teacher value or a confirmation (§11-2, ADR-037); a verifier
that cannot run stops the save. A regenerated value is AI output, so a safety
grounding error in it blocks the save, as at generation (§8).
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from ..domain.errors import InvalidDomainValueError
from ..domain.identifiers import ActorId, ItemId, PlanId
from ..domain.monthly_plan import MonthlyGenerationMode, MonthlyPlan
from ..domain.plan import PlanStatus
from ..domain.provenance import (
    AuditEvent,
    AuditEventType,
    EvidenceSourceType,
    GenerationMethod,
    GenerationMethodChange,
    GenerationMethodDetail,
    ValueChange,
)
from ..domain.weekly_plan import WEEKLY_INSTITUTION_INPUT_SECTION_KEYS, WeeklyPlan
from ..evidence.ports import InstitutionEvidenceRepository, WeeklyEvidenceClassificationRepository
from ..planner.weekly import OUTDOOR_KEY, SAFETY_KEY, THEME_KEY, WeeklyPlanner, cell_request
from ..rules.errors import MonthlyRuleError
from ..rules.monthly_cell_state import resolve_cell_state
from ..rules.weekly_verification import verify_weekly_plan
from .generate_weekly_plan import (
    LLM_RULE_ID,
    OUTDOOR_RULE_ID,
    WEEKLY_RULE_VERSION,
    WeeklyApplicationError,
    _only_cell,
    _outdoor_ranking,
    llm_cell_sources,
    llm_context,
    require_safe_grounding,
    rule_outdoor_sources,
)
from .monthly_support import MonthlyContextPipeline, load_plan_activity_catalog, require_actor, require_item_id
from .ports import ActivityReferenceRepository, Clock, PlanRepository

STATUTORY_SAFETY = "STATUTORY_SAFETY_EDUCATION"


@dataclass(frozen=True, slots=True)
class EditWeeklyPlanCellCommand:
    plan_id: PlanId
    item_id: ItemId
    new_value: str
    actor_id: ActorId


@dataclass(frozen=True, slots=True)
class RegenerateWeeklyPlanCellCommand:
    plan_id: PlanId
    item_id: ItemId
    actor_id: ActorId


@dataclass(frozen=True, slots=True)
class ConfirmWeeklyPlanCommand:
    plan_id: PlanId
    actor_id: ActorId


class _WeeklyLifecycle:
    def __init__(
        self,
        *,
        plan_repository: PlanRepository[WeeklyPlan],
        parent_plan_repository: PlanRepository[MonthlyPlan],
        clock: Clock,
        activity_repository: ActivityReferenceRepository | None = None,
    ) -> None:
        self._plans = plan_repository
        self._parents = parent_plan_repository
        self._clock = clock
        self._activities = activity_repository

    def _plan(self, plan_id: object) -> WeeklyPlan:
        if not isinstance(plan_id, PlanId):
            raise WeeklyApplicationError("invalid_plan_id", "Weekly use cases require PlanId")
        plan = self._plans.get(plan_id)
        if plan is None:
            raise WeeklyApplicationError("weekly_plan_not_found", f"Weekly Plan not found: {plan_id}")
        if not isinstance(plan, WeeklyPlan):
            raise WeeklyApplicationError(
                "repository_contract_violation", "PlanRepository returned a non-WeeklyPlan value"
            )
        return plan

    def _parent(self, plan: WeeklyPlan) -> MonthlyPlan:
        parent = self._parents.get(plan.parent_lineage.parent_plan_id)
        if not isinstance(parent, MonthlyPlan):
            raise WeeklyApplicationError(
                "parent_monthly_plan_not_found",
                f"Parent Monthly Plan not found: {plan.parent_lineage.parent_plan_id}",
            )
        return parent

    def _verified(self, plan: WeeklyPlan) -> WeeklyPlan:
        """Fresh report against the confirmed parent; findings are guidance only (§11-2)."""
        parent = self._parent(plan)
        try:
            catalog = load_plan_activity_catalog(self._activities, plan)
            report = verify_weekly_plan(plan, catalog, parent)
        except Exception as exc:  # a verifier that cannot run is not a finding
            raise WeeklyApplicationError(
                "weekly_verification_failed", "Weekly rule verification failed before the Plan was saved"
            ) from exc
        return replace(plan, verification_report=report)


class EditWeeklyPlanCell(_WeeklyLifecycle):
    def execute(self, command: EditWeeklyPlanCellCommand) -> WeeklyPlan:
        plan = self._plan(command.plan_id)
        plan.ensure_mutable("edit")
        item_id = require_item_id(command.item_id)
        actor_id = require_actor(command.actor_id)
        if not isinstance(command.new_value, str):
            raise WeeklyApplicationError("invalid_weekly_cell_value", "Weekly Cell value must be a string")
        cell = plan.find_cell(item_id)
        if cell is None:
            raise WeeklyApplicationError("weekly_cell_not_found", f"Weekly Cell not found: {item_id}")
        if cell.value == command.new_value:
            raise WeeklyApplicationError(
                "weekly_cell_value_unchanged", "Teacher edit must change the Cell value"
            )
        assessment = next(
            (a for a in plan.constraint_assessments if a.constraint.code == STATUTORY_SAFETY), None
        )
        try:  # empty theme and blank -> blank are the teacher's input, so an invalid value
            value_change = ValueChange(cell.value, command.new_value)
            cell_state = resolve_cell_state(
                section_key=cell.section_key, value=command.new_value, assessment=assessment
            )
        except (InvalidDomainValueError, MonthlyRuleError) as error:
            raise WeeklyApplicationError(
                "invalid_weekly_cell_value", "Teacher edit value is not allowed for this Cell"
            ) from error
        generation = cell.generation
        # §10-2: a teacher-input Cell becomes MANUAL on its first write and stays MANUAL.
        # Decision 2026-10-21: recorded on the Cell only; TEACHER_EDITED keeps the value change.
        if generation is None and cell.section_key in WEEKLY_INSTITUTION_INPUT_SECTION_KEYS:
            generation = GenerationMethodDetail(GenerationMethod.MANUAL)
        event = AuditEvent(
            AuditEventType.TEACHER_EDITED,
            self._clock.now(),
            plan.plan_id,
            item_id=cell.item_id,
            actor_id=actor_id,
            value_change=value_change,
        )
        updated = plan.replace_cell(item_id, replace(
            cell,
            value=command.new_value,
            cell_state=cell_state,
            generation=generation,
            audit=cell.audit.append(event),
        ))
        updated = self._verified(updated)
        self._plans.save(updated.plan_id, updated)
        return updated


class RegenerateWeeklyPlanCell(_WeeklyLifecycle):
    """One generated Cell, rewritten inside the range the Rule fixed at generation (§10-3).

    Every other Cell, and this Cell's item_id and section_key, stay as they were. A
    failed LLM answer saves nothing and is never replaced by rule output (§10-1).
    """

    def __init__(
        self,
        *,
        plan_repository: PlanRepository[WeeklyPlan],
        parent_plan_repository: PlanRepository[MonthlyPlan],
        clock: Clock,
        activity_repository: ActivityReferenceRepository | None = None,
        context_pipeline: MonthlyContextPipeline | None = None,
        planner: WeeklyPlanner | None = None,
        evidence_repository: InstitutionEvidenceRepository | None = None,
        weekly_classification_repository: WeeklyEvidenceClassificationRepository | None = None,
    ) -> None:
        super().__init__(
            plan_repository=plan_repository,
            parent_plan_repository=parent_plan_repository,
            clock=clock,
            activity_repository=activity_repository,
        )
        self._context = context_pipeline
        self._planner = planner
        self._evidence = evidence_repository
        self._weekly_classification = weekly_classification_repository

    def execute(self, command: RegenerateWeeklyPlanCellCommand) -> WeeklyPlan:
        plan = self._plan(command.plan_id)
        plan.ensure_mutable("regenerate")
        item_id = require_item_id(command.item_id)
        actor_id = require_actor(command.actor_id)
        cell = plan.find_cell(item_id)
        if cell is None:
            raise WeeklyApplicationError("weekly_cell_not_found", f"Weekly Cell not found: {item_id}")
        if cell.section_key in WEEKLY_INSTITUTION_INPUT_SECTION_KEYS:
            raise WeeklyApplicationError(
                "weekly_cell_not_regeneratable", "A teacher-input Cell is written by the teacher only"
            )
        parent = self._parent(plan)
        catalog = load_plan_activity_catalog(self._activities, plan)
        current_activity = next(
            (s.source_id for s in cell.evidence if s.source_type is EvidenceSourceType.ACTIVITY_REFERENCE), None
        )
        outdoor = _outdoor_ranking(parent, plan.week_id, catalog, _only_cell(parent, THEME_KEY), current_activity)
        if plan.generation_mode is MonthlyGenerationMode.RULE_ONLY:
            value, evidence, snapshots, generation = self._rule_only(plan, cell, parent, catalog, outdoor)
        else:
            value, evidence, snapshots, generation = self._llm(plan, cell, parent, catalog, outdoor)
        event = AuditEvent(
            AuditEventType.REGENERATED,
            self._clock.now(),
            plan.plan_id,
            item_id=cell.item_id,
            actor_id=actor_id,
            value_change=ValueChange(cell.value, value),
            generation_change=GenerationMethodChange(cell.generation, generation),
        )
        assessment = next(
            (a for a in plan.constraint_assessments if a.constraint.code == STATUTORY_SAFETY), None
        )
        updated = plan.replace_cell(item_id, replace(
            cell,
            value=value,
            cell_state=resolve_cell_state(section_key=cell.section_key, value=value, assessment=assessment),
            generation=generation,
            evidence=evidence,
            parent_snapshots=snapshots,
            audit=cell.audit.append(event),
        ))
        updated = self._verified(updated)
        require_safe_grounding(updated)
        self._plans.save(updated.plan_id, updated)
        return updated

    def _rule_only(self, plan, cell, parent, catalog, outdoor):
        # RULE_ONLY writes no text, so only the outdoor activity has a next candidate.
        if cell.section_key != OUTDOOR_KEY:
            raise WeeklyApplicationError(
                "rule_only_regeneration_unsupported",
                f"RULE_ONLY weekly regeneration covers outdoor_play only: {cell.section_key}",
            )
        if catalog is None:
            raise WeeklyApplicationError(
                "activity_catalog_required", "RULE_ONLY outdoor regeneration requires its exact Activity Catalog"
            )
        candidate = outdoor.selection.candidate
        if candidate is None:
            raise WeeklyApplicationError(
                "no_activity_candidate", "No eligible Activity candidate is available for regeneration"
            )
        evidence, snapshots = rule_outdoor_sources(
            candidate, parent=parent, lineage=plan.parent_lineage, outdoor=outdoor, catalog=catalog
        )
        generation = GenerationMethodDetail(GenerationMethod.RULE_ONLY, OUTDOOR_RULE_ID, WEEKLY_RULE_VERSION)
        return candidate.label, evidence, snapshots, generation

    def _llm(self, plan, cell, parent, catalog, outdoor):
        if self._context is None or self._planner is None:
            raise WeeklyApplicationError(
                "weekly_llm_dependencies_required",
                "LLM_PLANNER regeneration requires a Context Pipeline and a Weekly Planner",
            )
        key = cell.section_key
        context = llm_context(
            self._context, self._evidence, self._weekly_classification,
            parent=parent, period=plan.week_period, operating_days=plan.operating_days,
            snapshot=plan.template_snapshot, catalog=catalog,
            constraint_assessments=plan.constraint_assessments, outdoor=outdoor,
        )
        if context.request.target(key) is None:
            # The same Rule as generation decides; this request is refused, not the Plan.
            if key == SAFETY_KEY:  # only the parent teacher-text row is written (§8)
                raise WeeklyApplicationError(
                    "weekly_cell_not_regeneratable", "This safety_education Cell has no parent teacher sentence"
                )
            raise WeeklyApplicationError(
                "weekly_cell_evidence_missing", f"No Rule-approved basis to regenerate Section: {key}"
            )
        request = cell_request(
            context.request,
            key,
            current_values=tuple(
                (c.section_key, c.value) for c in plan.cells if c.item_id != cell.item_id and c.value.strip()
            ),
            teacher_facts=tuple(
                c.value for c in plan.cells
                if c.section_key in WEEKLY_INSTITUTION_INPUT_SECTION_KEYS and c.value.strip()
            ),
        )
        try:
            outcome = self._planner.plan(request)
        except Exception as exc:  # never answered by the rule path instead (§10-1)
            raise WeeklyApplicationError(
                "weekly_llm_cell_planning_failed", "Weekly Cell planning failed before the Plan was saved"
            ) from exc
        proposed = outcome.value(key)
        if proposed is None or proposed.unresolved:  # the teacher asked for a new value
            raise WeeklyApplicationError(
                "weekly_llm_cell_planning_failed", "Weekly Cell planning returned no value"
            )
        evidence, snapshots = llm_cell_sources(
            proposed, context, parent=parent, lineage=plan.parent_lineage, outdoor=outdoor, catalog=catalog
        )
        generation = GenerationMethodDetail(GenerationMethod.RULE_LLM, LLM_RULE_ID, outcome.prompt_version_for(key))
        return proposed.value, evidence, snapshots, generation


class ConfirmWeeklyPlan(_WeeklyLifecycle):
    """Idempotent: an already CONFIRMED Plan comes back unchanged, no event, no re-check.
    Confirm never submits or sends anything."""

    def execute(self, command: ConfirmWeeklyPlanCommand) -> WeeklyPlan:
        plan = self._plan(command.plan_id)
        actor_id = require_actor(command.actor_id)
        if plan.status is PlanStatus.CONFIRMED:
            return plan
        confirmed = self._verified(plan).confirm(actor_id=actor_id, occurred_at=self._clock.now())
        self._plans.save(confirmed.plan_id, confirmed)
        return confirmed
