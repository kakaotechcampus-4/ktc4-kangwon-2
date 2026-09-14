"""Dev 전용 Composition Root.

기존 Adapter만 재사용해 Use Case를 조립한다. Harness를 위한 새 Persistence나
HTTP Adapter를 만들지 않는다.

    JsonThemeReferenceRepository   실제 승인 상태를 그대로 읽는다 (override 없음)
    InMemoryPlanRepository         세션 1개 인스턴스, 종료 시 소멸
    EliceMLAPIAdapter              LLMConfig.from_env()로 구성
    FixedClock                     현재 시각 시드 + 1초 증가
    DeterministicIdGenerator       prefix="dev"
    OptionalContextProvider        None (P0 입력 없음)

`catalog_id`/`catalog_version`은 코드에 하드코딩하지 않고 Reference 파일에서
읽는다. 새 카탈로그 버전이 발행되어도 이 모듈을 고치지 않아도 된다.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from ..adapters.deterministic import DeterministicIdGenerator, FixedClock
from ..adapters.elice_mlapi_adapter import PROVIDER_NAME, EliceMLAPIAdapter
from ..adapters.in_memory_plan_repository import InMemoryPlanRepository
from ..adapters.json_theme_reference_repository import (
    DEFAULT_CATALOG_PATH,
    JsonThemeReferenceRepository,
)
from ..planning.application.confirm_yearly_plan import ConfirmYearlyPlan
from ..planning.application.dto import (
    CatalogSelector,
    GenerationRun,
    ThemeSelectionTrace,
)
from ..planning.application.edit_yearly_plan_item import EditYearlyPlanItem
from ..planning.application.generate_yearly_plan import GenerateYearlyPlan
from ..planning.application.regenerate_yearly_plan_item import (
    RegenerateYearlyPlanItem,
)
from ..planning.domain.plan import YearlyPlan
from ..planning.domain.theme_reference import ThemeCatalog
from ..shared.llm.config import LLMConfig, LLMConfigError
from ..shared.llm.fake import FakeLLM
from ..shared.llm.telemetry import LLMCallRecord

__all__ = [
    "DEV_CLASSROOM_REF",
    "DEV_DAYCARE_REF",
    "HarnessSession",
    "HarnessWiring",
    "build_wiring",
    "read_catalog_selector",
]

DEV_DAYCARE_REF = "dev_daycare_001"
DEV_CLASSROOM_REF = "dev_classroom_001"

_KST = timezone(timedelta(hours=9))


def read_catalog_selector(path=DEFAULT_CATALOG_PATH) -> CatalogSelector:
    """Reference 파일에서 catalog_id / catalog_version을 읽는다.

    CLAUDE.md §8: Domain 코드에 특정 catalog version을 장기 하드코딩하지 않는다.
    """
    payload = json.loads(path.read_text(encoding="utf-8"))
    return CatalogSelector(payload["catalog_id"], payload["catalog_version"])


@dataclass(slots=True)
class HarnessSession:
    """세션 상태 보관만 한다. 판단·검증·값 대입은 Use Case가 한다."""

    selector: CatalogSelector
    plan: YearlyPlan | None = None
    traces: dict[str, ThemeSelectionTrace] = field(default_factory=dict)
    llm_records: list[LLMCallRecord] = field(default_factory=list)

    @property
    def plan_id(self) -> str | None:
        return self.plan.plan_id.value if self.plan is not None else None

    @property
    def has_plan(self) -> bool:
        return self.plan is not None

    def adopt(self, plan: YearlyPlan) -> None:
        """Use Case가 반환한 Plan을 현재 Plan으로 채택한다."""
        self.plan = plan

    def absorb_run(self, run: GenerationRun | None) -> None:
        """Use Case가 반환한 trace를 period_key 기준으로 보관·갱신한다.

        Harness가 reason을 계산하지 않는다. 받은 값을 그대로 넣는다.
        """
        if run is None:
            return
        for trace in run.selection_traces:
            self.traces[trace.period_key] = trace


@dataclass(slots=True)
class HarnessWiring:
    """조립된 Use Case 묶음."""

    catalog: ThemeCatalog
    selector: CatalogSelector
    generate: GenerateYearlyPlan
    edit: EditYearlyPlanItem
    regenerate: RegenerateYearlyPlanItem
    confirm: ConfirmYearlyPlan
    plans: InMemoryPlanRepository
    llm_records: list[LLMCallRecord]
    provider: str
    model: str
    api_style: str | None
    live_api: bool


def build_wiring(
    *,
    use_llm: bool = True,
    llm=None,
    catalog_path=DEFAULT_CATALOG_PATH,
) -> HarnessWiring:
    """Use Case를 조립한다.

    Args:
        use_llm: False면 `GenerateYearlyPlan(use_llm=False)` 경로를 쓴다.
            실제 MLAPI를 호출하지 않으므로 비용이 없다.
        llm: 주입하면 그대로 쓴다(테스트에서 FakeLLM). None이면 use_llm에 따라
            EliceMLAPIAdapter를 만들거나 LLM을 쓰지 않는다.

    Raises:
        LLMConfigError: 실제 LLM이 필요한데 설정이 없을 때.
    """
    themes = JsonThemeReferenceRepository(catalog_path)  # override 없음
    selector = read_catalog_selector(catalog_path)
    catalog = themes.get_catalog(selector.catalog_id, selector.catalog_version)
    if catalog is None:  # pragma: no cover - 파일과 selector가 같은 출처다
        raise LLMConfigError(
            f"Reference Catalog를 찾을 수 없습니다: "
            f"{selector.catalog_id} / {selector.catalog_version}"
        )

    records: list[LLMCallRecord] = []
    provider, model, api_style = "-", "-", None

    if llm is not None:
        provider, model = "injected", type(llm).__name__
    elif use_llm:
        config = LLMConfig.from_env()
        llm = EliceMLAPIAdapter(config, telemetry_sink=records.append)
        provider, model = PROVIDER_NAME, config.model
        api_style = config.api_style.value
    else:
        # LLM을 쓰지 않는 경로. Port는 필요하므로 호출되지 않는 Fake를 넣는다.
        llm = FakeLLM()
        provider, model = "(사용 안 함)", "(사용 안 함)"

    plans = InMemoryPlanRepository()
    clock = FixedClock(datetime.now(_KST).replace(microsecond=0), advance_seconds=1)
    ids = DeterministicIdGenerator(prefix="dev")

    shared = {
        "theme_repository": themes,
        "plan_repository": plans,
        "llm": llm,
        "clock": clock,
        "id_generator": ids,
    }

    return HarnessWiring(
        catalog=catalog,
        selector=selector,
        generate=GenerateYearlyPlan(
            optional_context=None,  # P0 입력 없음
            use_llm=use_llm,
            **shared,
        ),
        edit=EditYearlyPlanItem(plan_repository=plans, clock=clock),
        regenerate=RegenerateYearlyPlanItem(use_llm=use_llm, **shared),
        confirm=ConfirmYearlyPlan(
            plan_repository=plans, clock=clock, theme_repository=themes
        ),
        plans=plans,
        llm_records=records,
        provider=provider,
        model=model,
        api_style=api_style,
        live_api=use_llm and llm is not None and provider == PROVIDER_NAME,
    )
