"""Demo Composition Root — 기존 실제 Use Case를 조립하기만 한다.

**Business Logic을 새로 구현하지 않는다.** Production의 Domain / Rule /
Validation / Adapter를 그대로 호출한다. 여기에 있는 것은 "무엇을 어떤 순서로
부를지"뿐이다.

Yearly 절반은 Production dev Composition(`ssuksak.dev.wiring.build_wiring`)을
그대로 쓰고, Monthly 절반은 그 **같은 Yearly Plan Repository**에 붙여 조립한다.
`build_monthly_wiring()`은 자기 Yearly Repository를 따로 만들고 Parent Plan까지
스스로 생성하므로, 사용자가 화면에서 직접 만든 Yearly를 Parent로 쓰려면 여기서
Monthly Use Case를 조립해야 한다. Production 모듈은 읽기만 하고 고치지 않는다.

    Yearly   build_wiring(use_llm=True)           ← Production dev Composition (실제 LLM)
    Monthly  Production Adapter + Use Case 조립   ← 같은 InMemoryPlanRepository 공유

버전 값은 코드에 하드코딩하지 않고 Production의 selector reader로 승인 파일에서
읽는다. 새 Catalog가 발행되어도 이 파일을 고치지 않아도 된다.

Persistence는 InMemory다. 프로세스가 죽으면 사라진다.

**LLM**

    Yearly   실제 호출한다. `build_wiring(use_llm=True)` → EliceMLAPIAdapter.
             설정은 `LLMConfig.from_env()`가 읽는 기존 환경변수를 그대로 쓴다.
             FakeLLM / mock / fixture / canned fallback을 쓰지 않는다.
    Monthly  2026-09-14 L8부터 **LLM_PLANNER가 Demo 기본 경로**다.
             Generate와 Cell Regenerate가 같은 Elice Adapter를 쓴다.

**Demo Composition Decision이지 Production global default 변경이 아니다.**
`GenerateMonthlyPlanCommand.generation_mode`의 기본값은 여전히 `RULE_ONLY`이고
여기서 명시적으로 `LLM_PLANNER`를 고른다. Use Case가 환경을 보고 mode를
자동 선택하지 않는다.

**Template도 Composition이 정한다.** Frontend가 `monthly-template-a-v0.2.0`
문자열을 보내지 않는다.

    RULE_ONLY     v0.1.0   focus Section 없음
    LLM_PLANNER   v0.2.0   focus 활성 — 주차별 중심 경험

API Key는 이 모듈이 읽지도 기록하지도 않는다. Adapter가 env에서만 읽는다.
설정이 없으면 가짜 결과로 대체하지 않고 `LLMConfigError`를 그대로 올린다.
"""

from __future__ import annotations

import pathlib
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from ssuksak.adapters.deterministic import (  # noqa: E402
    DeterministicIdGenerator,
    FixedClock,
)
from ssuksak.adapters.json_activity_reference_repository import (  # noqa: E402
    DEFAULT_ACTIVITY_CATALOG_PATH,
    production_activity_reference_repository,
)
from ssuksak.adapters.elice_mlapi_adapter import EliceMLAPIAdapter  # noqa: E402
from ssuksak.adapters.monthly_repositories import (  # noqa: E402
    DEFAULT_SAFETY_RULE_PATH,
    DEFAULT_TEMPLATE_PATH,
    WEEK_EXPERIENCE_TEMPLATE_PATH,
    InMemoryMonthlyPlanRepository,
    JsonSafetyLegalRuleRepository,
    production_monthly_template_repository,
)
from ssuksak.planning.application.monthly_dto import (  # noqa: E402
    MonthlyGenerationMode,
)
from ssuksak.planning.application.monthly_llm_cell_regeneration import (  # noqa: E402
    MonthlyLlmCellRegenerator,
)
from ssuksak.planning.application.monthly_llm_planning import (  # noqa: E402
    MonthlyLlmPlanner,
)
from ssuksak.planning.context import MonthlyContextPacketBuilder  # noqa: E402
from ssuksak.planning.retrieval import (  # noqa: E402
    JsonInstitutionEvidenceRepository,
    MonthlyEvidenceRetriever,
)
from ssuksak.shared.llm.config import LLMConfig  # noqa: E402
from ssuksak.dev.monthly_wiring import (  # noqa: E402
    read_activity_catalog_selector,
    read_safety_selector,
    read_template_ref,
)
from ssuksak.dev.wiring import build_wiring  # noqa: E402
from ssuksak.planning.application.confirm_monthly_plan import (  # noqa: E402
    ConfirmMonthlyPlan,
)
from ssuksak.planning.application.edit_monthly_plan_item import (  # noqa: E402
    EditMonthlyPlanItem,
)
from ssuksak.planning.application.generate_monthly_plan import (  # noqa: E402
    GenerateMonthlyPlan,
)
from ssuksak.planning.application.regenerate_monthly_plan_item import (  # noqa: E402
    RegenerateMonthlyPlanItem,
)

_KST = timezone(timedelta(hours=9))

__all__ = ["DemoWiring", "build_demo_wiring"]


@dataclass(slots=True)
class DemoWiring:
    """조립된 실제 Use Case 묶음. Demo는 이것을 호출만 한다."""

    # Yearly (Production dev Composition 그대로)
    yearly: object
    theme_selector: object
    # Monthly
    template_ref: object
    safety_selector: object
    activity_selector: object
    monthly_generate: GenerateMonthlyPlan
    monthly_edit: EditMonthlyPlanItem
    monthly_regenerate: RegenerateMonthlyPlanItem
    monthly_confirm: ConfirmMonthlyPlan
    monthly_plans: InMemoryMonthlyPlanRepository
    monthly_generation_mode: MonthlyGenerationMode
    monthly_model: str | None = None
    llm_call_records: list | None = None
    """Monthly LLM 호출 telemetry. API Key도 Prompt 본문도 담기지 않는다."""

    @property
    def yearly_plans(self):
        return self.yearly.plans

    @property
    def llm_records(self):
        """실제 LLM 호출 telemetry. API Key도 Prompt도 담기지 않는다."""
        return self.yearly.llm_records


def build_demo_wiring(
    *, use_llm: bool = True, monthly_llm: bool = True, llm=None
) -> DemoWiring:
    """실제 Adapter / Use Case를 조립한다. Demo 전용 Rule은 없다.

    Args:
        use_llm: 기본 True. Yearly가 실제 Elice MLAPI를 호출한다. 설정이 없으면
            `LLMConfigError`가 그대로 올라온다 — 가짜 결과로 대체하지 않는다.
        monthly_llm: 기본 True. Monthly를 LLM Planner로 생성한다.
            **False면 기존 Rule-only 경로가 그대로 돈다** — 삭제하지 않고
            개발 옵션으로 보존한다.
        llm: 주입하면 Yearly·Monthly가 그대로 쓴다. `build_wiring(llm=...)`과
            같은 규약이며 **Composition Root에서만** 바꿀 수 있다는 점도 같다.
            결정론 E2E가 실제 호출 없이 route 전 경로를 돌리기 위한 seam이고,
            **실행 중 자동으로 선택되지 않는다** — 기본값은 여전히 None이며
            그때는 환경변수로 만든 실제 Adapter를 쓴다.

    Raises:
        LLMConfigError: 실제 LLM 설정(환경변수)이 없을 때.
    """
    # ---- Yearly: Production dev Composition을 그대로 쓴다
    yearly = build_wiring(use_llm=use_llm, llm=llm)

    # ---- Monthly: 같은 Yearly Repository에 붙인다
    # 두 Template version을 함께 서빙한다. fallback이 아니라 exact resolve다.
    templates = production_monthly_template_repository()
    safety_rules = JsonSafetyLegalRuleRepository()  # 승인 상태 override 없음
    # Production과 **같은 승인 Artifact**를 읽는다. Demo 전용 Fake Catalog는 없다.
    activities = production_activity_reference_repository()
    activity_selector = read_activity_catalog_selector(DEFAULT_ACTIVITY_CATALOG_PATH)
    monthly_plans = InMemoryMonthlyPlanRepository()

    clock = FixedClock(datetime.now(_KST).replace(microsecond=0), advance_seconds=1)
    ids = DeterministicIdGenerator(prefix="demom")

    # ---- Monthly LLM Planner (Demo 기본 경로)
    llm_planner = None
    cell_regenerator = None
    monthly_model = None
    llm_records: list = []
    template_path = DEFAULT_TEMPLATE_PATH
    mode = MonthlyGenerationMode.RULE_ONLY

    if monthly_llm:
        if llm is not None:
            adapter = llm
            model_name = f"injected/{type(llm).__name__}"
        else:
            # 설정이 없으면 여기서 실패한다. 가짜 결과로 대체하지 않는다.
            config = LLMConfig.from_env()
            adapter = EliceMLAPIAdapter(config, telemetry_sink=llm_records.append)
            model_name = config.model
        store = JsonInstitutionEvidenceRepository().get_store()
        catalog = activities.get_catalog(
            activity_selector.catalog_id, activity_selector.catalog_version
        )
        builder = MonthlyContextPacketBuilder(
            MonthlyEvidenceRetriever(store, activity_catalog=catalog),
            store,
            activity_catalog=catalog,
        )
        llm_planner = MonthlyLlmPlanner(
            context_builder=builder,
            llm=adapter,
            planner_model=model_name,
            activity_catalog=catalog,
        )
        cell_regenerator = MonthlyLlmCellRegenerator(
            context_builder=builder, llm=adapter, planner_model=model_name
        )
        monthly_model = model_name
        template_path = WEEK_EXPERIENCE_TEMPLATE_PATH
        mode = MonthlyGenerationMode.LLM_PLANNER

    shared = {
        "monthly_plan_repository": monthly_plans,
        "template_repository": templates,
        "clock": clock,
    }

    return DemoWiring(
        yearly=yearly,
        theme_selector=yearly.selector,
        template_ref=read_template_ref(template_path),
        safety_selector=read_safety_selector(DEFAULT_SAFETY_RULE_PATH),
        activity_selector=activity_selector,
        monthly_generate=GenerateMonthlyPlan(
            yearly_plan_repository=yearly.plans,  # ← 화면에서 만든 Yearly가 Parent다
            monthly_plan_repository=monthly_plans,
            template_repository=templates,
            safety_rule_repository=safety_rules,
            clock=clock,
            id_generator=ids,
            optional_context=None,
            activity_reference_repository=activities,
            llm_planner=llm_planner,
        ),
        monthly_edit=EditMonthlyPlanItem(**shared),
        monthly_regenerate=RegenerateMonthlyPlanItem(
            activity_reference_repository=activities,
            llm_cell_regenerator=cell_regenerator,
            **shared,
        ),
        monthly_confirm=ConfirmMonthlyPlan(
            safety_rule_repository=safety_rules, **shared
        ),
        monthly_plans=monthly_plans,
        monthly_generation_mode=mode,
        monthly_model=monthly_model,
        llm_call_records=llm_records,
    )
