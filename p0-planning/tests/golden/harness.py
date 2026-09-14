"""Golden Set 실행 harness.

tests/golden/yearly_cases.json이 진실이다. 이 harness는 파일을 읽어 case를
구성하며 case 목록을 하드코딩하지 않는다. 파일에 case가 추가되면
handler 부재로 **실패**하도록 만들어 조용히 건너뛰는 일이 없게 한다.

assertion_policy:
    exact_sentence_match      = false
    exact_theme_label_match   = false
따라서 문장·label을 exact match하지 않고 구조·Rule·Reference·Gate·Validation·
Provenance만 검증한다.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ssuksak.adapters.deterministic import DeterministicIdGenerator, FixedClock
from ssuksak.adapters.in_memory_plan_repository import InMemoryPlanRepository
from ssuksak.adapters.json_theme_reference_repository import (
    DEFAULT_CATALOG_PATH,
    InMemoryThemeReferenceRepository,
    load_catalog_from_dict,
)
from ssuksak.adapters.stub_optional_context_provider import StubOptionalContextProvider
from ssuksak.planning.application.confirm_yearly_plan import (
    ConfirmYearlyPlan,
    MonthlyGenerationGate,
)
from ssuksak.planning.application.dto import (
    CatalogSelector,
    ClassroomContext,
    DaycareContext,
    EventInput,
    GenerateYearlyPlanCommand,
    PlanningSetup,
)
from ssuksak.planning.application.edit_yearly_plan_item import EditYearlyPlanItem
from ssuksak.planning.application.generate_yearly_plan import GenerateYearlyPlan
from ssuksak.planning.application.regenerate_yearly_plan_item import (
    RegenerateYearlyPlanItem,
)
from ssuksak.planning.domain.identifiers import ActorId
from ssuksak.planning.domain.provenance import EvidenceSourceType
from ssuksak.planning.domain.theme_reference import ActivationStatus, ThemeCatalog
from ssuksak.shared.llm.fake import FakeLLM, FakeLLMMode

SUITE_PATH = Path(__file__).resolve().parent / "yearly_cases.json"


def load_suite() -> dict[str, Any]:
    return json.loads(SUITE_PATH.read_text(encoding="utf-8"))


def load_catalog_payload() -> dict[str, Any]:
    return json.loads(DEFAULT_CATALOG_PATH.read_text(encoding="utf-8"))


def build_catalog(
    *,
    activation: ActivationStatus = ActivationStatus.HUMAN_APPROVED,
    drop_themes: set[str] | None = None,
) -> ThemeCatalog:
    """실제 Catalog 파일에서 Catalog를 만든다.

    파일을 수정하지 않는다. 승인 상태는 override로 주입하고,
    case 9의 `catalog_mutation`은 `drop_themes`로 표현한다.
    """
    payload = load_catalog_payload()
    if drop_themes:
        payload["themes"] = [
            t for t in payload["themes"] if t["theme_id"] not in drop_themes
        ]
    return load_catalog_from_dict(payload, activation_override=activation)


def resolve_fixture(fixtures: dict[str, Any], ref: str) -> Any:
    """`classrooms.age3` 같은 점 경로를 해석한다."""
    node: Any = fixtures
    for part in ref.split("."):
        node = node[part]
    return node


@dataclass
class Harness:
    """Use Case와 관찰 지점을 함께 들고 있는 실행 환경."""

    catalog: ThemeCatalog
    themes: InMemoryThemeReferenceRepository
    plans: InMemoryPlanRepository
    llm: FakeLLM
    clock: FixedClock
    ids: DeterministicIdGenerator
    optional_context: StubOptionalContextProvider

    @property
    def selector(self) -> CatalogSelector:
        return CatalogSelector(self.catalog.catalog_id, self.catalog.catalog_version)

    def generate(self, **kwargs) -> GenerateYearlyPlan:
        return GenerateYearlyPlan(
            theme_repository=self.themes,
            plan_repository=self.plans,
            llm=self.llm,
            clock=self.clock,
            id_generator=self.ids,
            optional_context=self.optional_context,
            **kwargs,
        )

    def edit(self) -> EditYearlyPlanItem:
        return EditYearlyPlanItem(plan_repository=self.plans, clock=self.clock)

    def regenerate(self, **kwargs) -> RegenerateYearlyPlanItem:
        return RegenerateYearlyPlanItem(
            theme_repository=self.themes,
            plan_repository=self.plans,
            llm=self.llm,
            clock=self.clock,
            id_generator=self.ids,
            **kwargs,
        )

    def confirm(self) -> ConfirmYearlyPlan:
        return ConfirmYearlyPlan(
            plan_repository=self.plans,
            clock=self.clock,
            theme_repository=self.themes,
        )

    def monthly_gate(self) -> MonthlyGenerationGate:
        return MonthlyGenerationGate(plan_repository=self.plans)


def make_harness(
    *,
    activation: ActivationStatus = ActivationStatus.HUMAN_APPROVED,
    drop_themes: set[str] | None = None,
    llm_mode: FakeLLMMode = FakeLLMMode.POLISH,
    optional_outcomes: dict[str, object] | None = None,
) -> Harness:
    catalog = build_catalog(activation=activation, drop_themes=drop_themes)
    return Harness(
        catalog=catalog,
        themes=InMemoryThemeReferenceRepository([catalog]),
        plans=InMemoryPlanRepository(),
        llm=FakeLLM(llm_mode),
        clock=FixedClock(),
        ids=DeterministicIdGenerator(),
        optional_context=StubOptionalContextProvider(optional_outcomes),
    )


# ------------------------------------------------------------ Command 조립


def build_generate_command(
    suite: dict[str, Any],
    case: dict[str, Any],
    *,
    catalog: CatalogSelector,
) -> GenerateYearlyPlanCommand:
    fixtures = suite["fixtures"]
    refs = case.get("fixture_refs") or []
    payload = case.get("input") or {}

    daycare_raw = None
    classroom_raw = None
    setup_raw = None
    events: list[EventInput] = []
    optional_requested: dict[str, object] = {}

    for ref in refs:
        value = resolve_fixture(fixtures, ref)
        if ref.startswith("classrooms."):
            classroom_raw = value
        elif ref == "daycare_valid":
            daycare_raw = value
        elif ref == "planning_setup_complete":
            setup_raw = value
        elif ref.startswith("event_"):
            events.append(
                EventInput(
                    event_id=value["event_id"],
                    label=value["label"],
                    starts_on=value["starts_on"],
                    status=value.get("status", "CONFIRMED"),
                )
            )
        elif ref == "optional_context_none":
            optional_requested = {}

    # input.classroom이 있으면 fixture를 덮어쓴다(case 13).
    if "classroom" in payload:
        classroom_raw = payload["classroom"]
    if "planning_setup" in payload:
        setup_raw = payload["planning_setup"]

    oc = payload.get("optional_context") or {}
    for name in ("trend", "weather", "climate_profile"):
        if oc.get(name) is not None:
            optional_requested[name] = oc[name]
    if oc.get("trend_provider"):
        optional_requested["trend"] = oc["trend_provider"]
    for event_ref in oc.get("events", []) or []:
        value = resolve_fixture(fixtures, event_ref)
        events.append(
            EventInput(
                event_id=value["event_id"],
                label=value["label"],
                starts_on=value["starts_on"],
                status=value.get("status", "CONFIRMED"),
            )
        )

    assert classroom_raw is not None, "case에 classroom fixture 또는 input이 없다"
    daycare_raw = daycare_raw or fixtures["daycare_valid"]
    setup_raw = setup_raw or {"completed": True, "start_mode": "CREATE_NEW"}

    age_mode = None
    if classroom_raw.get("age_mode"):
        from ssuksak.planning.application.dto import AgeMode

        age_mode = AgeMode(classroom_raw["age_mode"])

    return GenerateYearlyPlanCommand(
        school_year=payload.get("school_year", suite["academic_calendar"]["school_year"]),
        daycare=DaycareContext(
            daycare_ref=daycare_raw["daycare_ref"],
            name=daycare_raw.get("name"),
            director_name=daycare_raw.get("director_name"),
            region_ref=(daycare_raw.get("region") or {}).get("region_ref"),
        ),
        classroom=ClassroomContext(
            classroom_ref=classroom_raw["classroom_ref"],
            ages=frozenset(classroom_raw["ages"]),
            name=classroom_raw.get("name"),
            teacher_name=classroom_raw.get("teacher_name"),
            age_mode=age_mode,
        ),
        planning_setup=PlanningSetup(
            completed=bool(setup_raw.get("completed")),
            start_mode=setup_raw.get("start_mode"),
        ),
        catalog=catalog,
        events=tuple(events),
        optional_context_requested=optional_requested,
    )


def input_event_ids(suite: dict[str, Any], case: dict[str, Any]) -> set[str]:
    ids: set[str] = set()
    fixtures = suite["fixtures"]
    for ref in case.get("fixture_refs") or []:
        if ref.startswith("event_"):
            ids.add(resolve_fixture(fixtures, ref)["event_id"])
    oc = (case.get("input") or {}).get("optional_context") or {}
    for ref in oc.get("events", []) or []:
        ids.add(resolve_fixture(fixtures, ref)["event_id"])
    return ids


def theme_ids_of(plan) -> dict[str, str]:
    """period_key → THEME_REFERENCE Evidence의 source_id."""
    out: dict[str, str] = {}
    for mp in plan.month_periods:
        refs = mp.theme.evidence_of_type(EvidenceSourceType.THEME_REFERENCE)
        if refs:
            out[mp.period_key.value] = refs[0].source_id
    return out


ACTOR = ActorId("user_fixture_teacher_001")
