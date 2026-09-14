"""GenerateMonthlyPlan Use Case.

실행 순서가 계약이다. Gate 실패 시 Monthly Plan 저장 0회 / LLM 호출 0회 /
partial Plan 저장 없음이어야 하므로
**Gate → Reference → Duplicate → Optional Context → WeekPeriod → Template →
Cell → Constraint → Validation → 저장** 순서를 지킨다.

Optional Context는 필수 Parent/Reference Gate를 **통과한 뒤에** 조회한다.
필수 Gate 실패인데 외부 Provider부터 호출하지 않는다.

**LLM을 호출하지 않는다.** 값이 있는 Section은 상위 anchor에서 파생되는 theme와
승인 Activity Reference에서 Rule이 고른 `outdoor_play`뿐이고, 나머지는
Reference·source 부재로 빈 Cell이다. 빈 Cell을 GPT로 채우면 Reference 없는
창작이 된다(CLAUDE.md §4). 따라서 LLMPort를 주입받지 않는다.

**M2-C**에서 Activity Reference를 연결했다. Activity Catalog selector는 Optional
이며, 주지 않으면 M1과 동일하게 `outdoor_play`가 `EMPTY_VALID`로 남는다. 선택
logic은 이 파일에 없다. `rules/monthly_activity_selection.py`의 pure rule에
위임한다.
"""

from __future__ import annotations

from ..domain.constraint import (
    CellState,
    ConstraintAssessment,
    ConstraintKind,
    ConstraintVerification,
)
from ..domain.errors import FailureCategory, validation_failed
from ..domain.identifiers import ItemId, PeriodKey, PlanId
from ..domain.monthly_plan import (
    ActivityCatalogLineage,
    MonthlyPlan,
    MonthlyPlanItem,
    MonthlySection,
)
from ..domain.activity_reference import ActivityCatalog
from ..domain.monthly_template import DisplayMode, SectionRole
from ..domain.parent_lineage import ParentYearlyLineage
from ..domain.plan import PlanStatus
from ..domain.provenance import (
    AuditEvent,
    AuditEventType,
    AuditTrail,
    EvidenceSource,
    EvidenceSourceType,
    GenerationMethod,
    GenerationMethodDetail,
    SYSTEM_ACTOR_MARKER,
)
from ..rules import gates, monthly_gates
from ..rules.monthly_activity_selection import (
    RULE_ID as ACTIVITY_RULE_ID,
    RULE_VERSION as ACTIVITY_RULE_VERSION,
    select_activity_for_cell,
)
from ..rules.monthly_template_resolver import (
    RULE_ID as TEMPLATE_RULE_ID,
    RULE_VERSION as TEMPLATE_RULE_VERSION,
    ResolvedSection,
    build_section_skeleton,
    resolve_sections,
)
from ..rules.monthly_theme_derivation import (
    build_theme_evidence,
    derive_theme_value,
    theme_generation_method,
)
from ..rules.monthly_cell_state import OUTDOOR_SECTION_KEY
from ..rules.monthly_llm_validation import PLANNER_RULE_ID, PLANNER_RULE_VERSION
from ...shared.llm.monthly import ProposedActivityOrigin
from .monthly_llm_planning import MonthlyLlmPlanner, MonthlyPlannerOutcome
from ..rules.monthly_week_periods import canonical_week_periods
from .monthly_dto import (
    MonthlyGenerationMode,
    ActivitySelectionTrace,
    GenerateMonthlyPlanCommand,
    MonthlyGenerationRun,
    MonthlyPlanResult,
)
from .monthly_ports import (
    ActivityReferenceRepository,
    MonthlyPlanRepository,
    MonthlyTemplateRepository,
    SafetyLegalRuleRepository,
)
from .ports import (
    Clock,
    IdGenerator,
    OptionalContextBundle,
    OptionalContextProvider,
    PlanRepository,
)
from .validate_monthly_plan import validate_monthly_plan

SAFETY_SECTION_KEY = "safety_education"
FOCUS_SECTION_KEY = "focus"
"""주차별 중심 경험(week experience) Cell. Template A v0.2.0에서 활성화됐다(OD-N18)."""
THEME_SECTION_KEY = "theme"

SAFETY_SOURCE_KINDS = ("INSTITUTION_ANNUAL_SAFETY_PLAN", "TEACHER_INPUT")
"""OD-M04가 정한 배치 Source 2종.

speculative Enum을 만들지 않고 ConstraintAssessment의 tuple[str] Contract 안에서
stable identifier로 둔다.
"""

SAFETY_UNRESOLVED_DETAIL = (
    "기관 안전교육 연간계획 또는 교사 직접 입력이 없어 안전교육 배치를 검증하지 "
    "못했다. 임의 배치를 생성하지 않았다. 이 상태는 법정 요건 충족 여부에 대한 "
    "판정이 아니라 미검증 표시다."
)


class GenerateMonthlyPlan:
    def __init__(
        self,
        *,
        yearly_plan_repository: PlanRepository,
        monthly_plan_repository: MonthlyPlanRepository,
        template_repository: MonthlyTemplateRepository,
        safety_rule_repository: SafetyLegalRuleRepository,
        clock: Clock,
        id_generator: IdGenerator,
        optional_context: OptionalContextProvider | None = None,
        activity_reference_repository: ActivityReferenceRepository | None = None,
        llm_planner: MonthlyLlmPlanner | None = None,
    ) -> None:
        """Args:
        llm_planner: `generation_mode=LLM_PLANNER`일 때만 쓰인다.
            RULE_ONLY 경로는 이 협력자를 건드리지 않으므로 Evidence Store ·
            Retriever · LLM 없이도 동작한다(§31).
        """
        self._yearly = yearly_plan_repository
        self._monthly = monthly_plan_repository
        self._templates = template_repository
        self._safety_rules = safety_rule_repository
        self._clock = clock
        self._ids = id_generator
        self._optional_context = optional_context
        self._activities = activity_reference_repository
        self._llm_planner = llm_planner

    def execute(self, command: GenerateMonthlyPlanCommand) -> MonthlyPlanResult:
        # ---------------------------------------------- 1. 선행조건 Gate
        gates.require_planning_setup_complete(command.planning_setup)
        gates.require_valid_age_configuration(command.classroom)

        # ------------------------------------------------ 2. Parent Gate
        parent = self._yearly.get(command.parent_yearly_plan_id)
        gates.require_confirmed_parent_yearly(parent)
        assert parent is not None  # Gate가 None을 이미 막았다

        monthly_gates.require_matching_classroom_owner(
            parent, command.classroom.classroom_ref
        )
        monthly_gates.require_target_month_in_parent_academic_year(
            parent, command.target_month
        )
        parent_period = monthly_gates.require_parent_month_period(
            parent, command.target_month
        )
        anchor_evidence = monthly_gates.require_parent_theme_reference_evidence(
            parent_period.theme, command.target_month
        )
        monthly_gates.require_catalog_matches_parent_evidence(
            anchor_evidence,
            command.catalog.catalog_id,
            command.catalog.catalog_version,
            command.target_month,
        )

        # -------------------------------------------- 3. Reference Gate
        template = monthly_gates.require_resolved_template(
            self._templates.get_template(
                command.template_ref.template_id,
                command.template_ref.template_version,
            ),
            command.template_ref,
        )
        monthly_gates.require_active_template_instance(template)

        safety_rule = monthly_gates.require_resolved_safety_rule(
            self._safety_rules.get_legal_rule(command.safety_rule.legal_rule_version),
            command.safety_rule.legal_rule_version,
        )
        monthly_gates.require_active_safety_rule(safety_rule)

        activity_catalog = self._resolve_activity_catalog(command)

        # ------------------------- 4. Duplicate Gate (Optional Context 이전)
        # 실패 시 Optional Provider 호출도 발생하지 않아야 하므로 여기서 막는다.
        monthly_gates.require_unique_monthly_plan(
            self._monthly.find_monthly(
                command.classroom.classroom_ref, command.target_month
            ),
            command.classroom.classroom_ref,
            command.target_month,
        )

        run = MonthlyGenerationRun(
            run_id=self._ids.new_run_id(),
            started_at=self._clock.now(),
            template_id=template.template_ref.template_id,
            template_version=template.template_ref.template_version,
            safety_legal_rule_version=safety_rule.legal_rule_version,
            generation_mode=command.generation_mode.value,
        )

        # ----------------------- 5. Optional Context (Gate 통과 후, 실패 무해)
        bundle = self._fetch_optional_context(command)
        run.optional_context = bundle.results
        run.fallbacks_used = tuple(
            f"{r.name}:{r.status.value}" for r in bundle.failures
        )

        # -------------------------------------------- 6. WeekPeriod Rule
        target_month = PeriodKey(command.target_month)
        week_periods = canonical_week_periods(target_month)
        run.week_period_count = len(week_periods)

        # ------------------------------------------ 7. Template Resolver
        resolved = resolve_sections(template)
        sections = build_section_skeleton(template, resolved)

        # ------------------------------------------------- 8. lineage
        lineage = self._build_lineage(
            parent, parent_period, anchor_evidence, command.catalog.catalog_id
        )

        # ------------------------------- 8.5 LLM Planner (LLM_PLANNER 전용)
        # Cell을 만들기 **전에** Proposal을 확정한다. 검증을 통과하지 못하면
        # 여기서 예외가 나가고 Plan도 저장도 없다(§8 Atomicity).
        self._require_template_supports_mode(command, resolved)
        outcome = self._plan_with_llm(command, lineage, run)

        # -------------------------------------------------- 9. Cell 생성
        plan_id = PlanId(self._ids.new_plan_id())
        now = self._clock.now()
        active_weeks = tuple(w for w in week_periods if w.active)

        by_key = {r.section_key: r for r in resolved}
        activity_traces: list[ActivitySelectionTrace] = []
        for section in sections:
            self._fill_section(
                section=section,
                resolved=by_key[section.section_key],
                active_weeks=active_weeks,
                lineage=lineage,
                plan_id=plan_id,
                now=now,
                target_month=target_month,
                classroom_ages=command.classroom.ages,
                activity_catalog=activity_catalog,
                activity_traces=activity_traces,
                planner_outcome=outcome,
            )

        # -------------------------------------------- 10. Constraint 평가
        assessments = self._assess_constraints(sections, safety_rule)

        plan = MonthlyPlan(
            plan_id=plan_id,
            school_year=command.school_year,
            target_month=target_month,
            daycare_ref=command.daycare.daycare_ref,
            classroom_ref=command.classroom.classroom_ref,
            classroom_ages=command.classroom.ages,
            age_mode=command.classroom.effective_age_mode.value,
            status=PlanStatus.DRAFT,
            parent_lineage=lineage,
            template_ref=template.template_ref,
            activity_catalog=(
                None
                if activity_catalog is None
                else ActivityCatalogLineage(
                    catalog_id=activity_catalog.catalog_id,
                    catalog_version=activity_catalog.catalog_version,
                )
            ),
            week_periods=week_periods,
            sections=sections,
            constraint_assessments=assessments,
            audit=AuditTrail(
                [
                    AuditEvent(
                        event_type=AuditEventType.CREATED,
                        occurred_at=now,
                        plan_id=plan_id.value,
                        system_actor=SYSTEM_ACTOR_MARKER,
                    )
                ]
            ),
        )

        self._record_counts(run, plan, assessments)
        self._record_activity_counts(run, activity_catalog, activity_traces)

        # ----------------------------------------------- 11. Validation
        validate_monthly_plan(
            plan,
            template=template,
            expected_school_year=command.school_year,
            expected_classroom_ref=command.classroom.classroom_ref,
        )

        # ------------------------------------------- 12. 저장 (마지막에만)
        self._monthly.save(plan)
        return MonthlyPlanResult(plan=plan, run=run)

    # ------------------------------------------------------------ 내부

    @staticmethod
    def _require_template_supports_mode(command, resolved) -> None:
        """Mode와 Template이 맞는지 확인한다 (OD-N18 §5).

        **Template을 몰래 바꾸지 않는다.** LLM_PLANNER인데 Template에 `focus`가
        활성화돼 있지 않으면 Proposal의 주차별 경험이 **조용히 버려진다.**
        그것은 silent data loss이므로 여기서 명확히 실패한다.

        Template 선택은 계속 호출자의 `template_ref`가 한다.
        """
        if command.generation_mode is not MonthlyGenerationMode.LLM_PLANNER:
            return
        if any(r.section_key == FOCUS_SECTION_KEY for r in resolved):
            return
        raise validation_failed(
            "llm_planner_mode_requires_a_week_experience_section",
            FailureCategory.PREREQUISITE_GATE,
            f"generation_mode=LLM_PLANNER에는 `{FOCUS_SECTION_KEY}`가 활성화된 "
            f"Template이 필요하다. 현재 Template "
            f"{command.template_ref.template_version}에는 없다. "
            "Template을 자동으로 바꾸지 않는다 — 요청의 template_ref를 고쳐라.",
        )

    def _plan_with_llm(
        self, command, lineage, run
    ) -> MonthlyPlannerOutcome | None:
        """LLM_PLANNER Mode일 때만 Planner를 돌린다.

        **Mode를 여기서 고르지 않는다.** `command.generation_mode`가 곧 결정이며
        환경이나 협력자 유무를 보고 바꾸지 않는다. LLM_PLANNER인데 Planner가
        주입되지 않았으면 **조용히 RULE_ONLY로 내려가지 않고** 실패한다(§32).
        """
        if command.generation_mode is not MonthlyGenerationMode.LLM_PLANNER:
            return None

        if self._llm_planner is None:
            raise validation_failed(
                "llm_planner_mode_requires_a_planner_dependency",
                FailureCategory.PREREQUISITE_GATE,
                "generation_mode=LLM_PLANNER인데 Planner가 주입되지 않았다. "
                "RULE_ONLY로 대체하지 않는다.",
            )

        outcome = self._llm_planner.plan(
            school_year=command.school_year,
            target_month=PeriodKey(command.target_month),
            classroom_ages=tuple(sorted(command.classroom.ages)),
            age_mode=command.classroom.effective_age_mode.value,
            lineage=lineage,
            daycare_ref=command.daycare.daycare_ref,
            classroom_ref=command.classroom.classroom_ref,
        )

        lineage_meta = outcome.packet.source_lineage
        run.llm_invoked = True
        run.llm_call_count = outcome.provider_call_count
        run.llm_item_count = len(outcome.proposal.weeks)
        run.planner_model = outcome.planner_model
        run.prompt_version = outcome.prompt_version
        run.packet_fingerprint = outcome.packet_fingerprint
        run.evidence_store_version = lineage_meta.evidence_store_ingestion_version
        run.evidence_store_sha256 = lineage_meta.evidence_store_content_sha256
        run.retrieval_version = lineage_meta.retrieval_version
        run.context_packet_version = lineage_meta.packet_version
        run.planner_validation_repair_count = outcome.validation_repair_count
        run.planner_repaired_violations = outcome.rejected_violation_codes
        return outcome

    def _fill_focus_from_proposal(
        self,
        *,
        section: MonthlySection,
        active_weeks,
        outcome: MonthlyPlannerOutcome,
        plan_id: PlanId,
        now,
    ) -> None:
        """Proposal의 주차별 `experience`를 `focus` Cell로 옮긴다 (OD-N18).

        **Evidence를 붙이지 않는다.** LLM이 Context 전체를 참고해 구성한 문장이며
        특정 EvidenceRecord를 이 문장의 직접 근거로 주장할 수 없다. 빈 Evidence는
        "근거가 없다"가 아니라 **"특정 record를 인용하지 않았다"**는 뜻이고,
        생성 방식은 2축(`RULE_LLM`)이 표현한다.

        금지한 것 셋.

            Activity의 grounding_refs를 여기로 복사   하지 않는다
            근거 없이 INSTITUTION_SAMPLE 부여          하지 않는다
            week_order_basis = SOURCE_OBSERVED        하지 않는다
                (Corpus에 week_position 보유 0건 — OD-N14)
        """
        by_week = {w.week_id: w for w in outcome.proposal.weeks}
        detail = GenerationMethodDetail(
            method=GenerationMethod.RULE_LLM,
            rule_id=PLANNER_RULE_ID,
            rule_version=PLANNER_RULE_VERSION,
            selection_reason=outcome.proposal.month_flow_rationale,
        )

        for period in active_weeks:
            week = by_week.get(period.week_id.value)
            if week is None:  # pragma: no cover - L5가 이미 막는다
                raise validation_failed(
                    "llm_proposal_must_cover_every_canonical_week",
                    FailureCategory.LLM_OUTPUT_VALIDATION,
                    f"Proposal에 {period.week_id.value}가 없다",
                )

            item_id = ItemId(self._ids.new_item_id())
            section.items.append(
                MonthlyPlanItem(
                    item_id=item_id,
                    semantic_key=section.semantic_key,
                    value=week.experience,
                    generation=detail,
                    cell_state=CellState.FILLED,
                    week_id=period.week_id,
                    source_label=section.source_label,
                    evidence=[],
                    audit=AuditTrail(
                        [
                            AuditEvent(
                                event_type=AuditEventType.CREATED,
                                occurred_at=now,
                                plan_id=plan_id.value,
                                item_id=item_id.value,
                                system_actor=SYSTEM_ACTOR_MARKER,
                                new_method=GenerationMethod.RULE_LLM,
                            )
                        ]
                    ),
                )
            )

    def _fill_outdoor_from_proposal(
        self,
        *,
        section: MonthlySection,
        active_weeks,
        outcome: MonthlyPlannerOutcome,
        activity_catalog: ActivityCatalog | None,
        plan_id: PlanId,
        now,
    ) -> None:
        """검증을 통과한 Proposal을 `outdoor_play` Cell로 옮긴다.

        **Week ID의 Source of Truth는 canonical WeekPeriod다**(§19). Proposal의
        `week_id`는 대조 anchor로만 쓰며, L5가 이미 순서·집합 일치를 확인했다.

        Evidence는 origin에 따라 갈린다.

            REFERENCE        ACTIVITY_REFERENCE + 승인 catalog_version
            LLM_SYNTHESIZED  INSTITUTION_SAMPLE + 실제 Evidence record_id

        `LLM_SYNTHESIZED`를 EvidenceSourceType으로 쓰지 않는다 — 생성 방식은
        2축(GenerationMethod)이 표현한다(CLAUDE.md §13).
        """
        by_week = {w.week_id: w for w in outcome.proposal.weeks}
        detail = GenerationMethodDetail(
            method=GenerationMethod.RULE_LLM,
            rule_id=PLANNER_RULE_ID,
            rule_version=PLANNER_RULE_VERSION,
            selection_reason=outcome.proposal.month_flow_rationale,
        )

        for period in active_weeks:
            week = by_week.get(period.week_id.value)
            if week is None:  # pragma: no cover - L5가 이미 막는다
                raise validation_failed(
                    "llm_proposal_must_cover_every_canonical_week",
                    FailureCategory.LLM_OUTPUT_VALIDATION,
                    f"Proposal에 {period.week_id.value}가 없다",
                )

            activity = week.activity
            if activity.origin is ProposedActivityOrigin.REFERENCE:
                evidence = [
                    EvidenceSource(
                        source_type=EvidenceSourceType.ACTIVITY_REFERENCE,
                        source_id=activity.reference_activity_id or "",
                        source_version=(
                            activity_catalog.catalog_version
                            if activity_catalog is not None
                            else None
                        ),
                        display_name=activity.value,
                    )
                ]
            else:
                draft = next(
                    d for d in outcome.validation.provenance
                    if d.week_id == week.week_id
                )
                evidence = [
                    EvidenceSource(
                        source_type=EvidenceSourceType.INSTITUTION_SAMPLE,
                        source_id=record_id,
                        source_version=outcome.evidence_store_sha256,
                    )
                    for record_id in draft.grounding_source_ids
                ]

            item_id = ItemId(self._ids.new_item_id())
            section.items.append(
                MonthlyPlanItem(
                    item_id=item_id,
                    semantic_key=section.semantic_key,
                    value=activity.value,
                    generation=detail,
                    cell_state=CellState.FILLED,
                    week_id=period.week_id,
                    source_label=section.source_label,
                    evidence=evidence,
                    audit=AuditTrail(
                        [
                            AuditEvent(
                                event_type=AuditEventType.CREATED,
                                occurred_at=now,
                                plan_id=plan_id.value,
                                item_id=item_id.value,
                                system_actor=SYSTEM_ACTOR_MARKER,
                                new_method=GenerationMethod.RULE_LLM,
                            )
                        ]
                    ),
                )
            )

    def _fetch_optional_context(
        self, command: GenerateMonthlyPlanCommand
    ) -> OptionalContextBundle:
        """Optional Context 조회. 실패가 Core 생성을 실패시키지 않는다."""
        if self._optional_context is None or not command.optional_context_requested:
            return OptionalContextBundle(results=())
        try:
            return self._optional_context.fetch(command.optional_context_requested)
        except Exception:  # noqa: BLE001 - Optional 의존성은 Core를 깨뜨릴 수 없다
            from .ports import OptionalContextResult, OptionalContextStatus

            return OptionalContextBundle(
                results=tuple(
                    OptionalContextResult(
                        name=name,
                        status=OptionalContextStatus.ERROR,
                        detail="provider raised",
                    )
                    for name in command.optional_context_requested
                )
            )

    def _build_lineage(
        self, parent, parent_period, anchor: EvidenceSource, catalog_id: str
    ) -> ParentYearlyLineage:
        """확정된 상위 Plan에서 immutable snapshot을 만든다.

        `parent_yearly_theme_id`는 Rule이 검증한 Evidence에서만 읽는다.
        요청자 입력이나 LLM 응답에서 읽는 경로가 없다.
        """
        confirmed = [
            e for e in parent.audit.events if e.event_type is AuditEventType.CONFIRMED
        ]
        if not confirmed:
            raise validation_failed(
                "parent_yearly_confirmation_audit_must_exist",
                FailureCategory.PROVENANCE_VALIDATION,
                "상위 Yearly에 CONFIRMED Audit Event가 없어 lineage를 만들 수 없다",
            )
        event = confirmed[-1]
        if event.actor_id is None:
            raise validation_failed(
                "parent_yearly_confirmation_requires_actor",
                FailureCategory.ACTOR_VALIDATION,
                "상위 Yearly CONFIRMED Event에 actor_id가 없다",
            )
        return ParentYearlyLineage(
            parent_yearly_plan_id=parent.plan_id.value,
            parent_yearly_period_key=parent_period.period_key.value,
            parent_yearly_theme_id=anchor.source_id,
            parent_yearly_value=parent_period.theme.value,
            reference_catalog_id=catalog_id,
            reference_version=anchor.source_version or "",
            confirmed_at=event.occurred_at,
            confirmed_by=event.actor_id.value,
        )

    def _fill_section(
        self,
        *,
        section: MonthlySection,
        resolved: ResolvedSection,
        active_weeks,
        lineage: ParentYearlyLineage,
        plan_id: PlanId,
        now,
        target_month: PeriodKey,
        classroom_ages: frozenset[int],
        activity_catalog: ActivityCatalog | None,
        activity_traces: list[ActivitySelectionTrace],
        planner_outcome: MonthlyPlannerOutcome | None = None,
    ) -> None:
        """Section의 display_mode에 따라 Cell을 만든다.

        AXIS는 Item을 만들지 않는다. 전역 기본값을 쓰지 않으므로
        display_mode가 없는 활성 Section은 Resolver가 이미 막았다.

        `outdoor_play`만 Activity Reference를 참조한다. 선택 logic을 여기서
        다시 구현하지 않고 **M2-B pure rule**(`select_activity_for_cell`)에
        위임한다. `used_activity_ids`와 `used_curriculum_domains`는 같은 월의
        앞 주차에서 누적되며, 반복은 hard exclusion이 아니라 penalty다.
        """
        if resolved.role is SectionRole.AXIS:
            # week_axis가 여기 걸린다. AXIS는 값을 담는 Section이 아니라 축이므로
            # Proposal의 week experience를 넣을 자리가 없다 — L6 보고서 §4 / OD-N18.
            return

        if planner_outcome is not None and section.section_key == FOCUS_SECTION_KEY:
            self._fill_focus_from_proposal(
                section=section,
                active_weeks=active_weeks,
                outcome=planner_outcome,
                plan_id=plan_id,
                now=now,
            )
            return

        if (
            planner_outcome is not None
            and section.section_key == OUTDOOR_SECTION_KEY
        ):
            self._fill_outdoor_from_proposal(
                section=section,
                active_weeks=active_weeks,
                outcome=planner_outcome,
                activity_catalog=activity_catalog,
                plan_id=plan_id,
                now=now,
            )
            return

        method = GenerationMethodDetail(
            method=GenerationMethod.RULE_ONLY,
            rule_id=TEMPLATE_RULE_ID,
            rule_version=TEMPLATE_RULE_VERSION,
        )

        uses_activity = (
            section.section_key == OUTDOOR_SECTION_KEY and activity_catalog is not None
        )
        candidates: tuple = ()
        if uses_activity:
            assert activity_catalog is not None
            candidates = activity_catalog.eligible_candidates(
                section_key=section.section_key,
                calendar_month=int(target_month.value[5:7]),
                ages=classroom_ages,
            )

        used_activity_ids: set[str] = set()
        used_curriculum_domains: dict[str, int] = {}

        def build(week_id) -> MonthlyPlanItem:
            # Rule과 Trace의 week_id Contract는 `str | None`이다. Domain의
            # `WeekId` 값 객체를 그대로 넘기지 않는다.
            week_key = week_id.value if week_id is not None else None
            if not uses_activity:
                return self._make_cell(
                    section=section,
                    week_id=week_id,
                    lineage=lineage,
                    method=method,
                    plan_id=plan_id,
                    now=now,
                )
            selection = select_activity_for_cell(
                candidates=candidates,
                target_month=target_month.value,
                section_key=section.section_key,
                week_id=week_key,
                parent_theme_id=lineage.parent_yearly_theme_id,
                used_activity_ids=frozenset(used_activity_ids),
                used_curriculum_domains=used_curriculum_domains,
            )
            activity_traces.append(selection.trace)
            chosen = selection.candidate
            if chosen is not None:
                used_activity_ids.add(chosen.activity_id)
                for link in chosen.curriculum_links:
                    used_curriculum_domains[link.domain] = (
                        used_curriculum_domains.get(link.domain, 0) + 1
                    )
            assert activity_catalog is not None
            return self._make_cell(
                section=section,
                week_id=week_id,
                lineage=lineage,
                method=method,
                plan_id=plan_id,
                now=now,
                activity=chosen,
                activity_catalog=activity_catalog,
            )

        if resolved.display_mode is DisplayMode.MONTHLY_MERGED_SUMMARY:
            section.items.append(build(None))
            return

        for week in active_weeks:
            section.items.append(build(week.week_id))

    def _make_cell(
        self,
        *,
        section,
        week_id,
        lineage,
        method,
        plan_id,
        now,
        activity=None,
        activity_catalog: ActivityCatalog | None = None,
    ) -> MonthlyPlanItem:
        """M1의 Cell 값 정책.

            theme             parent anchor에서 파생. FILLED
            그 밖의 활성 Section  Reference·source 부재로 빈 Cell

        `safety_education`만 EMPTY_UNRESOLVED다. 나머지 빈 Cell은 EMPTY_VALID다.
        빈 Cell에는 content Evidence를 붙이지 않는다. 값이 없으면 근거도 없기
        때문이며, Template 추적은 2축 rule_id/rule_version이 담당한다.
        """
        if section.section_key == THEME_SECTION_KEY:
            # Regenerate와 같은 Rule을 쓴다. 두 경로가 다른 값을 만들면
            # 재생성이 anchor에서 벗어날 수 있다.
            value = derive_theme_value(lineage)
            state = CellState.FILLED
            evidence = build_theme_evidence(lineage)
            method = theme_generation_method()
        elif activity is not None:
            # Rule이 고른 활동 **하나**만 담는다. 여러 활동을 한 문자열로 이어
            # 붙이지 않는다. Evidence는 기존 3축 구조를 그대로 쓴다.
            assert activity_catalog is not None
            value = activity.label
            state = CellState.FILLED
            evidence = [
                EvidenceSource(
                    source_type=EvidenceSourceType.ACTIVITY_REFERENCE,
                    source_id=activity.activity_id,
                    source_version=activity_catalog.catalog_version,
                    display_name=activity.label,
                )
            ]
            method = GenerationMethodDetail(
                method=GenerationMethod.RULE_ONLY,
                rule_id=ACTIVITY_RULE_ID,
                rule_version=ACTIVITY_RULE_VERSION,
            )
        else:
            value = ""
            state = (
                CellState.EMPTY_UNRESOLVED
                if section.section_key == SAFETY_SECTION_KEY
                else CellState.EMPTY_VALID
            )
            evidence = []

        item_id = ItemId(self._ids.new_item_id())
        return MonthlyPlanItem(
            item_id=item_id,
            semantic_key=section.semantic_key,
            value=value,
            generation=method,
            cell_state=state,
            week_id=week_id,
            source_label=section.source_label,
            evidence=evidence,
            audit=AuditTrail(
                [
                    AuditEvent(
                        event_type=AuditEventType.CREATED,
                        occurred_at=now,
                        plan_id=plan_id.value,
                        item_id=item_id.value,
                        system_actor=SYSTEM_ACTOR_MARKER,
                        new_value=value,
                        new_method=method.method,
                    )
                ]
            ),
        )

    def _resolve_activity_catalog(
        self, command: GenerateMonthlyPlanCommand
    ) -> ActivityCatalog | None:
        """Activity Catalog을 Reference Gate에서 해소한다.

        `command.activity_catalog`가 없으면 Activity Reference를 쓰지 않는
        생성이며 M1과 동일하게 동작한다(outdoor는 `EMPTY_VALID`). Selector가
        있는데 Repository가 없거나 Catalog이 해소되지 않거나 미승인이면
        **Reference 실패**다. 조용히 `EMPTY_VALID`로 fallback하지 않는다.

        Catalog이 정상 해소된 뒤 후보가 0인 것은 실패가 아니라 정상 결과다.
        그 구분이 M2-C의 계약이다.
        """
        selector = command.activity_catalog
        if selector is None:
            return None
        if self._activities is None:
            raise validation_failed(
                "activity_catalog_id_and_version_must_resolve_exactly",
                FailureCategory.REFERENCE_VALIDATION,
                "Activity Catalog을 요청했으나 ActivityReferenceRepository가 "
                "주입되지 않았다",
            )
        catalog = monthly_gates.require_resolved_activity_catalog(
            self._activities.get_catalog(selector.catalog_id, selector.catalog_version),
            selector.catalog_id,
            selector.catalog_version,
        )
        monthly_gates.require_active_activity_catalog(catalog)
        return catalog

    @staticmethod
    def _record_activity_counts(
        run: MonthlyGenerationRun,
        catalog: ActivityCatalog | None,
        traces: list[ActivitySelectionTrace],
    ) -> None:
        """Activity 배정 결과를 Run에 남긴다.

        `activity_unfilled_cell_count`는 후보가 0이라 비워 둔 Cell 수이며
        `unresolved_requirements`가 아니다. 안전교육 미해소와 같은 의미가
        아니다.
        """
        run.activity_selection_traces = tuple(traces)
        if catalog is None:
            return
        run.activity_catalog_id = catalog.catalog_id
        run.activity_catalog_version = catalog.catalog_version
        run.activity_filled_cell_count = sum(1 for t in traces if t.has_selection)
        run.activity_unfilled_cell_count = sum(1 for t in traces if not t.has_selection)

    def _assess_constraints(
        self, sections: list[MonthlySection], safety_rule
    ) -> tuple[ConstraintAssessment, ...]:
        """Safety source 부재를 unresolved requirement로 표현한다.

        생성 실패가 아니고 fallback도 아니다. Plan 생성은 성공한다.
        """
        safety = next(
            (s for s in sections if s.section_key == SAFETY_SECTION_KEY), None
        )
        if safety is None:
            return ()
        return (
            ConstraintAssessment(
                kind=ConstraintKind.STATUTORY_SAFETY_EDUCATION,
                verification=ConstraintVerification.NOT_VERIFIED_SOURCE_REQUIRED,
                rule_version=safety_rule.legal_rule_version,
                required_source_kinds=SAFETY_SOURCE_KINDS,
                affected_section_keys=(SAFETY_SECTION_KEY,),
                detail=SAFETY_UNRESOLVED_DETAIL,
            ),
        )

    @staticmethod
    def _record_counts(
        run: MonthlyGenerationRun,
        plan: MonthlyPlan,
        assessments: tuple[ConstraintAssessment, ...],
    ) -> None:
        items = plan.items
        run.generated_cell_count = len(items)
        run.filled_cell_count = sum(
            1 for i in items if i.cell_state is CellState.FILLED
        )
        run.empty_valid_cell_count = sum(
            1 for i in items if i.cell_state is CellState.EMPTY_VALID
        )
        run.empty_unresolved_cell_count = sum(
            1 for i in items if i.cell_state is CellState.EMPTY_UNRESOLVED
        )
        # Safety source 부재는 fallback이 아니라 unresolved requirement다.
        run.unresolved_requirements = tuple(a for a in assessments if a.is_unresolved)
