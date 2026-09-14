"""RegenerateMonthlyPlanItem Use Case.

**재생성 가능한 Cell은 `theme`와 `outdoor_play` 둘이다.**

    theme              parent anchor에서 Rule로 재파생 (M1)
    outdoor_play       승인 Activity Catalog + M2-B Selection Rule (M2-D)
    focus              inactive이므로 Cell이 없다
    safety_education   배치 source 없음 (OD-M04). 계속 BLOCKED다

두 Section은 **서로 다른 Rule**을 쓴다. theme logic을 outdoor에 재사용하거나
그 반대로 섞지 않는다. 분기는 section_key 하나로만 한다.

Reference·Rule 근거 없이 GPT가 내용을 만드는 우회 경로를 만들지 않는다
(CLAUDE.md §4). 차단할 때 빈 문자열을 성공 결과처럼 반환하지 않고, 선택 Cell을
mutation하지 않으며, Repository save도 발생하지 않는다. **LLM 호출은 0회다.**

theme 재생성은 parent anchor에서 Rule로 재파생한다.
**`parent_yearly_theme_id`를 교체하지 않는다.** 재파생 결과가 기존 값과 같을 수
있으며 **동일 value여도 성공**이다. Yearly와 같은 원칙이다.

outdoor 재생성은 Plan이 생성될 때 기록한 `activity_catalog` lineage를 그대로
다시 해소한다. Production default Catalog로 조용히 대체하지 않는다. 후보가 0이면
기존 Cell을 유지한 채 **차단**한다. Generate의 후보 0(`EMPTY_VALID`)과 다르다 —
Regenerate는 이미 존재하는 Cell을 지울 권한이 없다.
"""

from __future__ import annotations

from ..domain.activity_reference import ActivityCandidate, ActivityCatalog
from ..domain.constraint import CellState
from ..domain.errors import FailureCategory, blocked
from ..domain.monthly_plan import MonthlyPlan, MonthlyPlanItem, MonthlySection
from ..domain.provenance import (
    AuditEvent,
    AuditEventType,
    EvidenceSource,
    EvidenceSourceType,
    GenerationMethod,
    GenerationMethodDetail,
)
from ..rules import monthly_gates
from ..rules.monthly_activity_selection import (
    RULE_ID as ACTIVITY_RULE_ID,
    RULE_VERSION as ACTIVITY_RULE_VERSION,
    select_activity_for_cell,
)
from ..rules.monthly_cell_state import OUTDOOR_SECTION_KEY, THEME_SECTION_KEY
from ..rules.monthly_llm_validation import (
    PLANNER_RULE_ID,
    PLANNER_RULE_VERSION,
)
from ...shared.llm.monthly import ProposedActivityOrigin
from ...shared.llm.monthly_cell import FOCUS_SECTION_KEY
from ..rules.monthly_theme_derivation import (
    build_theme_evidence,
    derive_theme_value,
    theme_generation_method,
)
from .confirm_yearly_plan import require_opaque_actor
from .edit_monthly_plan_item import _CellSnapshot, _require_template, require_monthly_plan
from .monthly_cell_resolution import resolve_cell
from .monthly_dto import (
    ActivityRegenerationOutcome,
    MonthlyGenerationMode,
    MonthlyPlanResult,
    RegenerateMonthlyPlanItemCommand,
)
from ..rules.monthly_llm_cell_validation import SiblingCell
from .monthly_llm_cell_regeneration import (
    MonthlyLlmCellRegenerator,
    build_month_snapshot,
)
from .monthly_ports import (
    ActivityReferenceRepository,
    MonthlyPlanRepository,
    MonthlyTemplateRepository,
)
from .ports import Clock
from .validate_monthly_plan import validate_monthly_plan

__all__ = [
    "LLM_REGENERATABLE_SECTION_KEYS",
    "RegenerateMonthlyPlanItem",
    "REGENERATABLE_SECTION_KEYS",
    "plan_generation_mode",
]

REGENERATABLE_SECTION_KEYS: frozenset[str] = frozenset(
    {THEME_SECTION_KEY, OUTDOOR_SECTION_KEY}
)
"""RULE_ONLY 경로에서 재생성 가능한 Section.

이 집합을 넓히려면 그 Section의 후보 Reference나 배치 source가 먼저 있어야 한다.
`outdoor_play`는 2026-09-12 승인된 Activity Reference v0.2.0으로 열렸다.
"""

LLM_REGENERATABLE_SECTION_KEYS: frozenset[str] = frozenset(
    {FOCUS_SECTION_KEY, OUTDOOR_SECTION_KEY}
)
"""LLM_PLANNER 경로에서 재생성 가능한 Section (2026-09-13 Product Decision B).

`theme`은 LLM이 만들지 않는다 — parent anchor에서 Rule로 재파생한다.
`week_axis`는 축이고 `safety_education`은 배치 source가 없다(OD-M04).
"""


def plan_generation_mode(plan: MonthlyPlan) -> MonthlyGenerationMode:
    """Plan이 어느 경로로 만들어졌는지 **Item Provenance에서 파생한다.**

    `MonthlyGenerationRun`은 Repository가 저장하지 않으므로(Plan만 저장된다)
    Run의 `generation_mode`를 나중에 읽을 수 없다. 대신 LLM Planner가 남긴
    `RULE_LLM` + planner rule_id가 Plan 안에 그대로 있으므로 그것을 본다.

    L6 보고서 §12는 이 값을 Run에 기록했다고 적었는데, Run이 영속되지 않는다는
    점은 그때 확인하지 못했다. L7 보고서 §3에 기록했다.
    """
    for section in plan.sections:
        for item in section.items:
            if (
                item.generation.method is GenerationMethod.RULE_LLM
                and item.generation.rule_id == PLANNER_RULE_ID
            ):
                return MonthlyGenerationMode.LLM_PLANNER
    return MonthlyGenerationMode.RULE_ONLY

_BLOCK_REASONS: dict[str, str] = {
    "safety_education": (
        "안전교육 배치 source가 없다. 기관 안전교육 연간계획 또는 교사 직접 "
        "입력이 선행되어야 한다. 임의 배치와 LLM 생성을 하지 않는다."
    ),
}


class RegenerateMonthlyPlanItem:
    def __init__(
        self,
        *,
        monthly_plan_repository: MonthlyPlanRepository,
        template_repository: MonthlyTemplateRepository,
        clock: Clock,
        activity_reference_repository: ActivityReferenceRepository | None = None,
        llm_cell_regenerator: MonthlyLlmCellRegenerator | None = None,
    ) -> None:
        """Args:
        llm_cell_regenerator: LLM Plan의 Cell을 재생성할 때만 쓰인다.
            RULE_ONLY 경로는 이 협력자를 건드리지 않는다.
        """
        self._plans = monthly_plan_repository
        self._templates = template_repository
        self._clock = clock
        self._activities = activity_reference_repository
        self._llm_cells = llm_cell_regenerator

    def execute(
        self, command: RegenerateMonthlyPlanItemCommand
    ) -> MonthlyPlanResult:
        # ---- 실패 가능한 검사는 전부 Mutation 이전에 수행한다 ----
        plan = require_monthly_plan(self._plans, command.plan_id)
        plan.ensure_mutable("RegenerateMonthlyPlanItem")
        actor = require_opaque_actor(
            command.actor_id, rule="regenerate_requires_opaque_actor_id"
        )

        section, item = resolve_cell(plan, command.address)

        # Mode는 Plan의 Provenance에서 파생한다. 환경이나 LLM 가용성을 보고
        # 바꾸지 않는다(§26). 요청이 Mode를 명시했다면 일치해야 한다.
        mode = plan_generation_mode(plan)
        _require_matching_mode(command, mode)
        _require_regeneratable(section, mode)

        template = _require_template(self._templates, plan)

        llm_outcome = None
        # Section마다 다른 Rule을 쓴다. 세 경로는 섞이지 않는다.
        if mode is MonthlyGenerationMode.LLM_PLANNER and section.section_key in (
            LLM_REGENERATABLE_SECTION_KEYS
        ):
            (
                new_value,
                new_evidence,
                new_method,
                llm_outcome,
            ) = self._resolve_with_llm(
                plan=plan, section=section, item=item
            )
            outcome = None
        elif section.section_key == OUTDOOR_SECTION_KEY:
            new_value, new_evidence, new_method, outcome = self._resolve_outdoor(
                plan=plan, section=section, item=item, command=command
            )
        else:
            # parent anchor에서 재파생한다. LLM을 호출하지 않는다.
            lineage = plan.parent_lineage
            new_value = derive_theme_value(lineage)
            new_evidence = build_theme_evidence(lineage)
            new_method = theme_generation_method()
            outcome = None

        event = AuditEvent(
            event_type=AuditEventType.REGENERATED,
            occurred_at=self._clock.now(),
            plan_id=plan.plan_id.value,
            item_id=item.item_id.value,
            actor_id=actor,
            previous_value=item.value,
            new_value=new_value,
            previous_method=item.generation.method,
            new_method=new_method.method,
        )

        # ---------------------- 여기서부터 Mutation ----------------------
        snapshot = _CellSnapshot.of(item)
        previous_evidence = list(item.evidence)
        previous_generation = item.generation

        item.value = new_value
        item.generation = new_method
        item.evidence = new_evidence
        if section.section_key in (OUTDOOR_SECTION_KEY, FOCUS_SECTION_KEY):
            item.cell_state = CellState.FILLED
        item.audit.append(event)

        try:
            validate_monthly_plan(
                plan,
                template=template,
                expected_school_year=plan.school_year,
                expected_classroom_ref=plan.classroom_ref,
            )
        except Exception:
            snapshot.restore()
            item.evidence = previous_evidence
            item.generation = previous_generation
            raise

        self._plans.save(plan)
        return MonthlyPlanResult(
            plan=plan,
            activity_regeneration=outcome,
            cell_regeneration=llm_outcome,
        )

    # -------------------------------------------------------- LLM Cell 전용

    def _resolve_with_llm(self, *, plan, section, item):
        """Target Cell 하나를 LLM으로 다시 쓴다.

        **Mutation을 하지 않는다.** 실패 가능한 판정을 전부 끝내고 값만 돌려준다.
        Target 외 Cell은 읽기만 하며 `month_snapshot`으로 Context에 들어간다.
        """
        if self._llm_cells is None:
            raise blocked(
                "llm_cell_regenerate_requires_a_regenerator_dependency",
                FailureCategory.PREREQUISITE_GATE,
                "LLM으로 생성된 Plan의 Cell을 재생성하려면 Cell Regenerator가 "
                "필요하다. Rule 재생성으로 대체하지 않는다.",
            )
        if item.week_id is None:  # pragma: no cover - WEEKLY_CELLS만 대상이다
            raise blocked(
                "llm_cell_regenerate_requires_a_week_cell",
                FailureCategory.PREREQUISITE_GATE,
                f"{section.section_key}는 주차 Cell이 아니다",
            )

        siblings = tuple(
            SiblingCell(
                week_id=other.week_id.value,
                section_key=other_section.section_key,
                value=other.value,
                activity_id=_activity_id_of(other),
            )
            for other_section in plan.sections
            for other in other_section.items
            if other is not item and other.week_id is not None
        )

        outcome = self._llm_cells.regenerate(
            school_year=plan.school_year,
            target_month=plan.target_month,
            classroom_ages=tuple(sorted(plan.classroom_ages)),
            age_mode=plan.age_mode,
            lineage=plan.parent_lineage,
            target_week_id=item.week_id.value,
            target_section_key=section.section_key,
            month_snapshot=build_month_snapshot(plan),
            siblings=siblings,
            daycare_ref=plan.daycare_ref,
            classroom_ref=plan.classroom_ref,
        )

        proposal = outcome.proposal
        method = GenerationMethodDetail(
            method=GenerationMethod.RULE_LLM,
            rule_id=PLANNER_RULE_ID,
            rule_version=PLANNER_RULE_VERSION,
        )

        if section.section_key == FOCUS_SECTION_KEY:
            # 특정 EvidenceRecord를 이 문장의 직접 근거로 주장하지 않는다(OD-N18).
            return proposal.value, [], method, outcome

        if proposal.activity_origin is ProposedActivityOrigin.REFERENCE:
            catalog = self._load_pinned_catalog(plan)
            evidence = [
                EvidenceSource(
                    source_type=EvidenceSourceType.ACTIVITY_REFERENCE,
                    source_id=proposal.reference_activity_id or "",
                    source_version=catalog.catalog_version,
                    display_name=proposal.value,
                )
            ]
        else:
            evidence = [
                EvidenceSource(
                    source_type=EvidenceSourceType.INSTITUTION_SAMPLE,
                    source_id=record_id,
                    source_version=outcome.evidence_store_sha256,
                )
                for record_id in outcome.grounding_source_ids
            ]
        return proposal.value, evidence, method, outcome

    # ------------------------------------------------------------ outdoor 전용

    def _resolve_outdoor(
        self,
        *,
        plan: MonthlyPlan,
        section: MonthlySection,
        item: MonthlyPlanItem,
        command: RegenerateMonthlyPlanItemCommand,
    ) -> tuple[str, list[EvidenceSource], GenerationMethodDetail, ActivityRegenerationOutcome]:
        """대상 outdoor Cell 하나에 쓸 Activity를 결정한다.

        **Mutation을 하지 않는다.** 실패 가능한 판정은 전부 여기서 끝내고 값만
        돌려준다. 호출자는 이 함수가 성공한 뒤에야 Cell을 건드린다.
        """
        catalog = self._load_pinned_catalog(plan)

        candidates = catalog.eligible_candidates(
            section_key=section.section_key,
            calendar_month=plan.target_month.calendar_month,
            ages=plan.classroom_ages,
        )
        if not candidates:
            # Generate와 다르다. 기존 Cell을 EMPTY_VALID로 지우지 않는다.
            raise blocked(
                "regenerate_requires_at_least_one_eligible_candidate",
                FailureCategory.PREREQUISITE_GATE,
                f"{catalog.catalog_id}@{catalog.catalog_version}에 "
                f"{plan.target_month.value} / 만 {sorted(plan.classroom_ages)}세 "
                "조건을 만족하는 후보가 없다. 기존 Cell을 그대로 둔다",
            )

        current_activity_id = _activity_id_of(item)
        used_activity_ids, used_domains = _sibling_context(section, item, catalog)

        selection = select_activity_for_cell(
            candidates=candidates,
            target_month=plan.target_month.value,
            section_key=section.section_key,
            week_id=item.week_id.value if item.week_id else None,
            parent_theme_id=plan.parent_lineage.parent_yearly_theme_id,
            used_activity_ids=frozenset(used_activity_ids),
            used_curriculum_domains=used_domains,
            current_activity_id=current_activity_id,
        )
        chosen = selection.candidate
        assert chosen is not None  # 후보가 비어 있지 않으면 Rule은 반드시 고른다

        evidence = [
            EvidenceSource(
                source_type=EvidenceSourceType.ACTIVITY_REFERENCE,
                source_id=chosen.activity_id,
                source_version=catalog.catalog_version,
                display_name=chosen.label,
            )
        ]
        method = GenerationMethodDetail(
            method=GenerationMethod.RULE_ONLY,
            rule_id=ACTIVITY_RULE_ID,
            rule_version=ACTIVITY_RULE_VERSION,
        )
        outcome = ActivityRegenerationOutcome(
            address=command.address,
            catalog_id=catalog.catalog_id,
            catalog_version=catalog.catalog_version,
            previous_value=item.value,
            previous_activity_id=current_activity_id,
            selected_value=chosen.label,
            selected_activity_id=chosen.activity_id,
            trace=selection.trace,
        )
        return chosen.label, evidence, method, outcome

    def _load_pinned_catalog(self, plan: MonthlyPlan) -> ActivityCatalog:
        """Plan이 생성 시 기록한 **정확히 그 Catalog**를 해소한다.

        Production default를 쓰지 않는다. v0.3가 default가 되어도 v0.2로 생성된
        Plan은 v0.2를 다시 찾는다. 찾지 못하면 실패이며 default로 fallback하지
        않는다.
        """
        lineage = plan.activity_catalog
        if lineage is None:
            # M1 Plan의 차단 의미를 그대로 유지한다. violated_rule을 바꾸면 기존
            # Golden/M1-D contract가 달라지므로 식별자는 보존하고 detail만 좁힌다.
            raise blocked(
                "regenerate_requires_resolved_candidate_source",
                FailureCategory.PREREQUISITE_GATE,
                "이 Plan은 Activity Reference 없이 생성되어 outdoor Cell을 "
                "재생성할 수 없다. 현재 default Activity Catalog를 임의로 붙여 "
                "과거 Plan을 업그레이드하지 않는다",
            )
        if self._activities is None:
            raise blocked(
                "regenerate_requires_activity_reference_repository",
                FailureCategory.PREREQUISITE_GATE,
                "ActivityReferenceRepository가 주입되지 않아 "
                f"{lineage.catalog_id}@{lineage.catalog_version}를 해소할 수 없다",
            )
        catalog = monthly_gates.require_resolved_activity_catalog(
            self._activities.get_catalog(lineage.catalog_id, lineage.catalog_version),
            lineage.catalog_id,
            lineage.catalog_version,
        )
        monthly_gates.require_active_activity_catalog(catalog)
        return catalog


def _activity_id_of(item: MonthlyPlanItem) -> str | None:
    """Cell의 현재 activity_id를 **Evidence에서만** 읽는다.

    label 역검색이나 유사도 매칭을 하지 않는다. 교사가 직접 쓴 Cell처럼
    ACTIVITY_REFERENCE Evidence가 없으면 None이며, 그때는 현재 Activity penalty가
    적용되지 않는다.
    """
    for source in item.evidence:
        if source.source_type is EvidenceSourceType.ACTIVITY_REFERENCE:
            return source.source_id
    return None


def _sibling_context(
    section: MonthlySection, target: MonthlyPlanItem, catalog: ActivityCatalog
) -> tuple[set[str], dict[str, int]]:
    """대상 Cell을 **제외한** 같은 Section의 배정 현황.

    대상 Cell 자신의 activity_id는 `used_activity_ids`가 아니라
    `current_activity_id`로 넘긴다. 두 축을 섞으면 자기 자신이 두 번 penalty를
    받아 M2-B의 합산 의미가 달라진다.
    """
    used: set[str] = set()
    domains: dict[str, int] = {}
    for item in section.items:
        if item is target:
            continue
        activity_id = _activity_id_of(item)
        if activity_id is None:
            continue
        used.add(activity_id)
        candidate: ActivityCandidate | None = catalog.get(activity_id)
        if candidate is None:
            continue
        for link in candidate.curriculum_links:
            domains[link.domain] = domains.get(link.domain, 0) + 1
    return used, domains


def _require_matching_mode(command, plan_mode) -> None:
    """요청이 Mode를 명시했다면 Plan의 실제 경로와 같아야 한다 (§26).

    **silent switching을 만들지 않는다.** RULE_ONLY Plan을 LLM으로 재생성하거나
    LLM Plan을 Rule로 되돌리는 것은 조합 오류이므로 실패한다.
    """
    requested = getattr(command, "generation_mode", None)
    if requested is None or requested is plan_mode:
        return
    raise blocked(
        "regenerate_mode_must_match_the_plan_generation_path",
        FailureCategory.PREREQUISITE_GATE,
        f"요청 mode {requested.value} != Plan 생성 경로 {plan_mode.value}. "
        "Mode를 자동으로 바꾸지 않는다.",
    )


def _require_regeneratable(section: MonthlySection, mode) -> None:
    """재생성 대상 Section인지 확인한다.

    차단 사유를 구체적으로 알려 사용자가 무엇이 필요한지 알 수 있게 한다.
    """
    allowed = (
        REGENERATABLE_SECTION_KEYS | LLM_REGENERATABLE_SECTION_KEYS
        if mode is MonthlyGenerationMode.LLM_PLANNER
        else REGENERATABLE_SECTION_KEYS
    )
    if section.section_key in allowed:
        return
    reason = _BLOCK_REASONS.get(
        section.section_key,
        "M1에서 재생성 가능한 Cell이 아니다.",
    )
    raise blocked(
        "regenerate_requires_resolved_candidate_source",
        FailureCategory.PREREQUISITE_GATE,
        f"{section.section_key}는 M1에서 재생성할 수 없다. {reason}",
    )
