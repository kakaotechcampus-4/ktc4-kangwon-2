from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime

import pytest

from ssuksak.adapters.deterministic import (
    DeterministicIdGenerator,
    FixedClock,
)
from ssuksak.adapters.deterministic_theme_text_generator import (
    DeterministicThemeTextGenerator,
)
from ssuksak.adapters.in_memory_plan_repository import InMemoryPlanRepository
from ssuksak.adapters.json_theme_reference_repository import (
    JsonThemeReferenceRepository,
)
from ssuksak.adapters.stub_optional_context_provider import (
    StubOptionalContextProvider,
)
from ssuksak.planning.application.confirm_yearly_plan import ConfirmYearlyPlan
from ssuksak.planning.application.edit_yearly_plan_item import EditYearlyPlanItem
from ssuksak.planning.application.generate_yearly_plan import GenerateYearlyPlan
from ssuksak.planning.application.ports import (
    OptionalContextResult,
    OptionalContextStatus,
)
from ssuksak.planning.application.regenerate_yearly_plan_item import (
    RegenerateYearlyPlanItem,
)
from ssuksak.planning.application.yearly_dto import (
    CatalogSelector,
    ConfirmYearlyPlanCommand,
    EditYearlyPlanItemCommand,
    GenerateYearlyPlanCommand,
    RegenerateYearlyPlanItemCommand,
)
from ssuksak.planning.application.yearly_errors import YearlyApplicationError
from ssuksak.planning.application.yearly_ports import (
    ThemeTextRequest,
    ThemeTextResult,
)
from ssuksak.planning.domain.errors import (
    InvalidDomainValueError,
    InvalidStateTransitionError,
)
from ssuksak.planning.domain.identifiers import ActorId, ItemId
from ssuksak.planning.domain.plan import PlanStatus
from ssuksak.planning.domain.provenance import (
    AuditEventType,
    EvidenceSourceType,
    GenerationMethod,
)
from ssuksak.planning.domain.theme_reference import ActivationStatus
from ssuksak.planning.rules.errors import YearlyRuleError

NOW = datetime(2026, 9, 19, 10, 0, tzinfo=UTC)
ACTOR = ActorId("teacher_001")
SELECTOR = CatalogSelector(
    catalog_id="ssuksak.yearly-theme-reference",
    catalog_version="theme-reference-v0.1.2",
)


class Harness:
    def __init__(self) -> None:
        self.themes = JsonThemeReferenceRepository()
        self.plans = InMemoryPlanRepository()
        self.text = DeterministicThemeTextGenerator()
        self.clock = FixedClock(NOW)
        self.ids = DeterministicIdGenerator("yearly")
        self.optional = StubOptionalContextProvider()

    def generate_use_case(self) -> GenerateYearlyPlan:
        return GenerateYearlyPlan(
            theme_repository=self.themes,
            plan_repository=self.plans,
            text_generator=self.text,
            clock=self.clock,
            id_generator=self.ids,
            optional_context=self.optional,
        )

    def generate(self, **overrides):
        values = {
            "school_year": 2026,
            "classroom_ref": "classroom_001",
            "target_ages": frozenset({3}),
            "catalog": SELECTOR,
        }
        values.update(overrides)
        return self.generate_use_case().execute(GenerateYearlyPlanCommand(**values))

    def edit(self) -> EditYearlyPlanItem:
        return EditYearlyPlanItem(
            plan_repository=self.plans,
            clock=self.clock,
        )

    def regenerate(
        self, text_generator: DeterministicThemeTextGenerator | None = None
    ) -> RegenerateYearlyPlanItem:
        return RegenerateYearlyPlanItem(
            theme_repository=self.themes,
            plan_repository=self.plans,
            text_generator=text_generator or self.text,
            clock=self.clock,
        )

    def confirm(self) -> ConfirmYearlyPlan:
        return ConfirmYearlyPlan(
            plan_repository=self.plans,
            clock=self.clock,
        )


def test_generate_creates_one_draft_with_twelve_academic_periods():
    harness = Harness()

    result = harness.generate()

    assert result.plan.status is PlanStatus.DRAFT
    assert result.plan.plan_id.value == "yearly_plan_001"
    assert [period.period.value for period in result.plan.periods] == [
        "2026-03",
        "2026-04",
        "2026-05",
        "2026-06",
        "2026-07",
        "2026-08",
        "2026-09",
        "2026-10",
        "2026-11",
        "2026-12",
        "2027-01",
        "2027-02",
    ]
    assert len(result.plan.items) == 12
    assert len(harness.plans) == 1
    assert harness.plans.save_count == 1


def test_generate_reuses_pr1_selection_and_batches_text_once():
    harness = Harness()

    result = harness.generate()

    assert harness.text.call_count == 1
    assert len(harness.text.batches[0]) == 12
    assert len(result.selection_traces) == 12
    assert [trace.period for trace in result.selection_traces] == [
        period.period for period in result.plan.periods
    ]
    assert all(
        trace.rule_id == "yearly.theme.sample_derived_candidate_selection"
        and trace.rule_version == "v2"
        for trace in result.selection_traces
    )


def test_generated_items_have_independent_provenance_and_created_audit():
    plan = Harness().generate().plan

    for period in plan.periods:
        item = period.theme
        assert item.generation.method is GenerationMethod.RULE_LLM
        assert item.generation.rule_id == (
            "yearly.theme.sample_derived_candidate_selection"
        )
        assert item.generation.rule_version == "v2"
        assert len(item.evidence) == 1
        assert item.evidence[0].source_type is EvidenceSourceType.THEME_REFERENCE
        assert item.evidence[0].source_id == period.theme_id
        assert item.evidence[0].source_version == "theme-reference-v0.1.2"
        assert [event.event_type for event in item.audit] == [
            AuditEventType.CREATED
        ]
    assert [event.event_type for event in plan.audit] == [AuditEventType.CREATED]


@pytest.mark.parametrize(
    "ages",
    [frozenset({3}), frozenset({4}), frozenset({5}), frozenset({3, 4, 5})],
)
def test_generate_supports_each_p0_age_configuration(ages):
    result = Harness().generate(target_ages=ages)

    assert result.plan.target_ages == ages
    assert len(result.plan.periods) == 12


def test_invalid_age_fails_before_text_generation_and_persistence():
    harness = Harness()

    with pytest.raises(YearlyRuleError):
        harness.generate(target_ages=frozenset({2}))

    assert harness.text.call_count == 0
    assert harness.plans.save_count == 0


def test_unapproved_catalog_fails_before_text_generation_and_persistence():
    harness = Harness()
    approved = harness.themes.get_catalog(
        SELECTOR.catalog_id, SELECTOR.catalog_version
    )
    assert approved is not None
    pending = replace(
        approved,
        activation_status=ActivationStatus.PENDING_HUMAN_REVIEW,
    )

    class PendingRepository:
        def get_catalog(self, catalog_id: str, catalog_version: str):
            return pending

    harness.themes = PendingRepository()

    with pytest.raises(YearlyRuleError):
        harness.generate()

    assert harness.text.call_count == 0
    assert harness.plans.save_count == 0


def test_invalid_text_generator_result_is_not_partially_saved():
    harness = Harness()

    class WrongThemeGenerator:
        def generate(self, requests: tuple[ThemeTextRequest, ...]):
            return tuple(
                ThemeTextResult(
                    period=request.period,
                    theme_id="invented-theme",
                    value=request.reference_label,
                )
                for request in requests
            )

    use_case = GenerateYearlyPlan(
        theme_repository=harness.themes,
        plan_repository=harness.plans,
        text_generator=WrongThemeGenerator(),
        clock=harness.clock,
        id_generator=harness.ids,
    )

    with pytest.raises(YearlyApplicationError) as exc:
        use_case.execute(
            GenerateYearlyPlanCommand(
                school_year=2026,
                classroom_ref="classroom_001",
                target_ages=frozenset({3}),
                catalog=SELECTOR,
            )
        )

    assert exc.value.code == "invalid_theme_text_result"
    assert harness.plans.save_count == 0


def test_optional_context_is_fetched_by_name_and_passed_to_text_requests():
    harness = Harness()
    harness.optional = StubOptionalContextProvider(
        {
            "trend": OptionalContextResult(
                name="trend",
                status=OptionalContextStatus.AVAILABLE,
                value={"keyword": "숲"},
            ),
            "weather": OptionalContextResult(
                name="weather",
                status=OptionalContextStatus.TIMEOUT,
                detail="timed out",
            ),
        }
    )

    result = harness.generate(optional_context_names=("trend", "weather"))

    assert [context.status for context in result.optional_context] == [
        OptionalContextStatus.AVAILABLE,
        OptionalContextStatus.TIMEOUT,
    ]
    assert harness.text.batches[0][0].optional_context == result.optional_context


def test_optional_context_provider_exception_does_not_fail_generation():
    harness = Harness()

    class ExplodingProvider:
        def fetch(self, name: str):
            raise RuntimeError(name)

    harness.optional = ExplodingProvider()

    result = harness.generate(optional_context_names=("trend",))

    assert result.optional_context[0].status is OptionalContextStatus.ERROR
    assert len(result.plan.periods) == 12


def test_teacher_edit_returns_a_new_plan_and_preserves_evidence():
    harness = Harness()
    original = harness.generate().plan
    item = original.periods[2].theme
    evidence_before = item.evidence

    updated = harness.edit().execute(
        EditYearlyPlanItemCommand(
            plan_id=original.plan_id,
            item_id=item.item_id,
            new_value="소중한 나와 가족",
            actor_id=ACTOR,
        )
    )
    edited = updated.find_item(item.item_id)
    assert edited is not None
    edited_item = edited[1].theme

    assert updated is not original
    assert original.find_item(item.item_id)[1].theme.value == item.value
    assert edited_item.value == "소중한 나와 가족"
    assert edited_item.evidence == evidence_before
    # The edit keeps the Generation Method and is recorded in the Audit only.
    assert edited_item.generation == item.generation
    assert edited_item.generation.method is GenerationMethod.RULE_LLM
    assert edited_item.generation.rule_id and edited_item.generation.rule_version
    event = edited_item.audit.events[-1]
    assert event.event_type is AuditEventType.TEACHER_EDITED and event.generation_change is None
    assert (event.value_change.before, event.value_change.after) == (item.value, "소중한 나와 가족")


def test_teacher_edit_changes_only_the_target_period():
    harness = Harness()
    original = harness.generate().plan
    target = original.periods[4].theme

    updated = harness.edit().execute(
        EditYearlyPlanItemCommand(
            plan_id=original.plan_id,
            item_id=target.item_id,
            new_value="여름을 만나요",
            actor_id=ACTOR,
        )
    )

    for before, after in zip(original.periods, updated.periods, strict=True):
        if before.theme.item_id == target.item_id:
            assert after is not before
        else:
            assert after is before


def test_blank_teacher_edit_is_rejected_without_saving():
    harness = Harness()
    plan = harness.generate().plan
    saves_before = harness.plans.save_count

    with pytest.raises(InvalidDomainValueError):
        harness.edit().execute(
            EditYearlyPlanItemCommand(
                plan_id=plan.plan_id,
                item_id=plan.periods[0].theme.item_id,
                new_value=" ",
                actor_id=ACTOR,
            )
        )

    assert harness.plans.save_count == saves_before
    assert harness.plans.get(plan.plan_id) is plan


def test_regenerate_replaces_one_item_and_preserves_stable_identity():
    harness = Harness()
    original = harness.generate().plan
    target = original.periods[2]
    generator = DeterministicThemeTextGenerator(suffix=" · 다시 생성")

    result = harness.regenerate(generator).execute(
        RegenerateYearlyPlanItemCommand(
            plan_id=original.plan_id,
            item_id=target.theme.item_id,
            actor_id=ACTOR,
            catalog=SELECTOR,
        )
    )
    regenerated = result.plan.find_item(target.theme.item_id)
    assert regenerated is not None
    regenerated_item = regenerated[1].theme

    assert generator.call_count == 1
    assert len(generator.batches[0]) == 1
    assert regenerated_item.item_id == target.theme.item_id
    assert regenerated_item.value.endswith(" · 다시 생성")
    assert regenerated_item.audit.events[-1].event_type is AuditEventType.REGENERATED
    assert regenerated_item.audit.events[-1].generation_change is not None
    assert result.selection_trace.period == target.period
    for before, after in zip(original.periods, result.plan.periods, strict=True):
        if before.theme.item_id == target.theme.item_id:
            assert after is not before
        else:
            assert after is before


def test_regenerate_may_keep_the_same_theme_and_value():
    harness = Harness()
    original = harness.generate().plan
    target = original.periods[2]

    result = harness.regenerate().execute(
        RegenerateYearlyPlanItemCommand(
            plan_id=original.plan_id,
            item_id=target.theme.item_id,
            actor_id=ACTOR,
            catalog=SELECTOR,
        )
    )
    found = result.plan.find_item(target.theme.item_id)
    assert found is not None
    regenerated_period = found[1]
    item = regenerated_period.theme

    assert item.item_id == target.theme.item_id
    assert regenerated_period.theme_id == target.theme_id
    assert item.value == target.theme.value
    assert item.audit.events[-1].event_type is AuditEventType.REGENERATED


def test_unknown_item_is_rejected_without_generator_call_or_save():
    harness = Harness()
    plan = harness.generate().plan
    generator = DeterministicThemeTextGenerator()
    saves_before = harness.plans.save_count

    with pytest.raises(YearlyApplicationError) as exc:
        harness.regenerate(generator).execute(
            RegenerateYearlyPlanItemCommand(
                plan_id=plan.plan_id,
                item_id=ItemId("missing"),
                actor_id=ACTOR,
                catalog=SELECTOR,
            )
        )

    assert exc.value.code == "yearly_item_not_found"
    assert generator.call_count == 0
    assert harness.plans.save_count == saves_before


def test_confirm_is_explicit_and_records_teacher_actor():
    harness = Harness()
    draft = harness.generate().plan

    confirmed = harness.confirm().execute(
        ConfirmYearlyPlanCommand(plan_id=draft.plan_id, actor_id=ACTOR)
    )

    assert draft.status is PlanStatus.DRAFT
    assert confirmed.status is PlanStatus.CONFIRMED
    assert confirmed.audit.events[-1].event_type is AuditEventType.CONFIRMED
    assert confirmed.audit.events[-1].actor_id == ACTOR
    assert harness.plans.get(draft.plan_id) is confirmed


def test_confirmed_plan_rejects_edit_regenerate_and_second_confirm():
    harness = Harness()
    draft = harness.generate().plan
    confirmed = harness.confirm().execute(
        ConfirmYearlyPlanCommand(plan_id=draft.plan_id, actor_id=ACTOR)
    )
    item = confirmed.periods[0].theme
    saves_before = harness.plans.save_count
    text_calls_before = harness.text.call_count

    with pytest.raises(InvalidStateTransitionError):
        harness.edit().execute(
            EditYearlyPlanItemCommand(
                plan_id=confirmed.plan_id,
                item_id=item.item_id,
                new_value="수정 금지",
                actor_id=ACTOR,
            )
        )
    with pytest.raises(InvalidStateTransitionError):
        harness.regenerate().execute(
            RegenerateYearlyPlanItemCommand(
                plan_id=confirmed.plan_id,
                item_id=item.item_id,
                actor_id=ACTOR,
                catalog=SELECTOR,
            )
        )
    with pytest.raises(InvalidStateTransitionError):
        harness.confirm().execute(
            ConfirmYearlyPlanCommand(plan_id=confirmed.plan_id, actor_id=ACTOR)
        )

    assert harness.plans.save_count == saves_before
    assert harness.text.call_count == text_calls_before


def test_yearly_aggregate_is_frozen():
    plan = Harness().generate().plan

    with pytest.raises(FrozenInstanceError):
        plan.status = PlanStatus.CONFIRMED  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        plan.periods[0].theme.value = "mutated"  # type: ignore[misc]


def test_yearly_aggregate_rejects_missing_period():
    plan = Harness().generate().plan

    with pytest.raises(InvalidDomainValueError, match="March"):
        replace(plan, periods=plan.periods[:-1])


def test_no_submit_or_send_capability_exists():
    harness = Harness()
    confirm = harness.confirm()

    for forbidden in ("submit", "send", "dispatch", "notify"):
        assert not hasattr(confirm, forbidden)
        assert not hasattr(harness.plans, forbidden)
