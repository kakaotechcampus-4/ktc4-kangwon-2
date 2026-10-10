"""월간 생성 Luna-6 bench (결정 문서 12.2 「PR-3 전 Luna-6 bench 1회」).

실제 월간 스키마로 엘리스를 불러 400 여부 · 호출별 응답 시간 · 수리 호출 · 구조 검증 결과 ·
토큰을 잰다. **돈이 드는 호출이라 `--live` 없이는 부르지 않는다.** 한 번 생성은 호출 1~2회다
(수리 최대 1회).

DB 를 쓰지 않는다. 부모 연간 · Profile · 저장소는 메모리에만 있다. 기반 Template v0.2.1 은
사람 승인 대기라 OD-N11 (A) — 이 프로세스 안에서만 `replace(template, runtime_active=True)` —
로 Profile 을 만든다. 데이터 파일과 운영 경로는 그대로다.

    ELICE_MLAPI_BASE_URL=<Luna-6 주소> ELICE_MLAPI_API_KEY=... \\
        python scripts/bench_monthly_luna.py --live [--runs 1]

키는 출력하지 않는다. 결과는 JSON 한 덩이로 stdout 에 쓴다.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import replace
from datetime import UTC, datetime
from urllib import error as urllib_error
from urllib import request as urllib_request

from ssuksak.adapters.deterministic import DeterministicIdGenerator, FixedClock
from ssuksak.adapters.deterministic_theme_text_generator import DeterministicThemeTextGenerator
from ssuksak.adapters.elice_openai_monthly import EliceOpenAiMonthlyAdapter, MonthlyLlmConfig
from ssuksak.adapters.evidence_classification_repository import (
    JsonEvidenceClassificationRepository,
)
from ssuksak.adapters.in_memory_plan_repository import InMemoryPlanRepository
from ssuksak.adapters.in_memory_template_profile_repository import (
    InMemoryTemplateProfileRepository,
)
from ssuksak.adapters.institution_evidence_repository import JsonInstitutionEvidenceRepository
from ssuksak.adapters.json_activity_reference_repository import JsonActivityReferenceRepository
from ssuksak.adapters.json_theme_reference_repository import JsonThemeReferenceRepository
from ssuksak.adapters.monthly_reference_repositories import (
    JsonMonthlyTemplateRepository,
    JsonSafetyLegalRuleRepository,
    JsonSafetyPlacementPolicyRepository,
)
from ssuksak.adapters.safety_evidence_classification_repository import (
    JsonSafetyEvidenceClassificationRepository,
)
from ssuksak.adapters.safety_reference_quality_repository import (
    JsonSafetyReferenceQualityRepository,
)
from ssuksak.planning import (
    ActivityCatalogSelector,
    CatalogSelector,
    ConfirmYearlyPlan,
    ConfirmYearlyPlanCommand,
    GenerateMonthlyPlan,
    GenerateMonthlyPlanCommand,
    GenerateYearlyPlan,
    GenerateYearlyPlanCommand,
    MonthlyApplicationError,
    MonthlyGenerationMode,
    SafetyRuleSelector,
    TemplateProfileRef,
)
from ssuksak.planning.application.monthly_support import MonthlyContextPipeline
from ssuksak.planning.context.builder import ContextPacketBuilder
from ssuksak.planning.domain.identifiers import ActorId
from ssuksak.planning.domain.monthly_template import SemanticVariant, TemplateRef
from ssuksak.planning.domain.monthly_template_profile import TemplateProfile
from ssuksak.planning.domain.year_month import YearMonth
from ssuksak.planning.planner.service import MonthlyPlanner

NOW = datetime(2026, 9, 20, 10, 0, tzinfo=UTC)
TEMPLATE = TemplateRef("ssuksak.monthly-template-a", "monthly-template-a-v0.2.1")
PROFILE = TemplateProfileRef("bench-profile", "v1")
LABELS = {
    "theme": "주제",
    "week_axis": "주",
    "outdoor_play": "바깥놀이",
    "safety_education": "안전교육",
    "focus": "소주제",
}
MAX_RUNS = 3


class TimedTransport:
    """호출마다 시간 · HTTP 상태 · 토큰을 남긴다. 응답 본문과 키는 남기지 않는다."""

    def __init__(self, post=urllib_request.urlopen):
        self._open = post
        self.calls: list[dict] = []

    def post_json(self, url, *, headers, payload, timeout):
        record = {"schema": payload["response_format"]["json_schema"]["name"]}
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib_request.Request(url, data=body, headers=dict(headers), method="POST")
        started = time.perf_counter()
        try:
            with self._open(request, timeout=timeout) as response:
                result = json.loads(response.read().decode("utf-8"))
                record["status"] = response.status
        except urllib_error.HTTPError as exc:
            record["status"] = exc.code
            # 오류 본문의 앞부분만 — 400 이면 스키마 거부 사유가 여기 있다.
            record["error_body"] = exc.read()[:500].decode("utf-8", "replace")
            raise
        except Exception as exc:
            record["error"] = type(exc).__name__
            raise
        finally:
            record["seconds"] = round(time.perf_counter() - started, 2)
            self.calls.append(record)
        record["usage"] = result.get("usage")
        record["model"] = result.get("model")
        return result


class _ApprovedTemplates:
    """OD-N11 (A): Core 최종 승인 검사(ADR-027)도 이 프로세스 안에서만 승인 상태로 본다."""

    def get_template(self, template_id, template_version):
        template = JsonMonthlyTemplateRepository().get_template(template_id, template_version)
        return None if template is None else replace(template, runtime_active=True)


def _profile() -> TemplateProfile:
    """OD-N11 (A): 이 프로세스 안에서만 승인 상태로 본다."""
    template = JsonMonthlyTemplateRepository().get_template(
        TEMPLATE.template_id, TEMPLATE.template_version
    )
    template = replace(template, runtime_active=True)
    return TemplateProfile(
        profile_ref=PROFILE,
        institution_ref="bench-daycare",
        base_template_ref=template.template_ref,
        selected_optional_keys=("focus",),
        sections=tuple(
            replace(
                section,
                display_label=LABELS[section.section_key],
                semantic_variant=SemanticVariant.SUBTHEME
                if section.section_key == "focus"
                else None,
            )
            for section in template.activated_sections
        ),
    )


def run_once(transport, *, month: YearMonth, ages: frozenset[int]) -> dict:
    yearly = InMemoryPlanRepository()
    clock = FixedClock(NOW)
    parent = (
        GenerateYearlyPlan(
            theme_repository=JsonThemeReferenceRepository(),
            plan_repository=yearly,
            text_generator=DeterministicThemeTextGenerator(),
            clock=clock,
            id_generator=DeterministicIdGenerator("bench-yearly"),
        )
        .execute(
            GenerateYearlyPlanCommand(
                school_year=2026,
                classroom_ref="bench-classroom",
                target_ages=ages,
                catalog=CatalogSelector("ssuksak.yearly-theme-reference", "theme-reference-v0.1.2"),
            )
        )
        .plan
    )
    ConfirmYearlyPlan(plan_repository=yearly, clock=clock).execute(
        ConfirmYearlyPlanCommand(parent.plan_id, ActorId("bench_teacher"))
    )
    adapter = EliceOpenAiMonthlyAdapter(MonthlyLlmConfig.from_env(), transport=transport)
    use_case = GenerateMonthlyPlan(
        parent_plan_repository=yearly,
        plan_repository=InMemoryPlanRepository(),
        profile_repository=InMemoryTemplateProfileRepository((_profile(),)),
        template_repository=_ApprovedTemplates(),
        safety_repository=JsonSafetyLegalRuleRepository(),
        activity_repository=JsonActivityReferenceRepository(),
        clock=clock,
        id_generator=DeterministicIdGenerator("bench-monthly"),
        context_pipeline=MonthlyContextPipeline(
            evidence_repository=JsonInstitutionEvidenceRepository(),
            classification_repository=JsonEvidenceClassificationRepository(),
            context_builder=ContextPacketBuilder(),
            safety_classification_repository=JsonSafetyEvidenceClassificationRepository(),
            safety_quality_repository=JsonSafetyReferenceQualityRepository(),
        ),
        planner=MonthlyPlanner(adapter),
        safety_placement_repository=JsonSafetyPlacementPolicyRepository(),
    )
    first_call = len(transport.calls)
    started = time.perf_counter()
    outcome: dict = {"month": month.value, "ages": sorted(ages)}
    try:
        plan = use_case.execute(
            GenerateMonthlyPlanCommand(
                parent_yearly_plan_id=parent.plan_id,
                target_month=month,
                daycare_ref="bench-daycare",
                profile_ref=PROFILE,
                safety_rule=SafetyRuleSelector("child-welfare-act-decree-annex6-2022-06-21"),
                generation_mode=MonthlyGenerationMode.LLM_PLANNER,
                activity_catalog=ActivityCatalogSelector(
                    "ssuksak.outdoor-activity-reference", "activity-reference-v0.2.1"
                ),
                # D-M4-03: 배치 정책을 넘기지 않는다 — 안전교육은 근거 필요(미해결) 경로다.
            )
        ).plan
        outcome.update(
            result="SAVED",
            cells=len(plan.cells),
            cell_states=_count(c.cell_state.value for c in plan.cells),
            methods=_count(c.generation.method.value for c in plan.cells if c.generation),
            findings=[f.code for f in plan.verification_report.findings],
        )
    except MonthlyApplicationError as error:
        cause = error.__cause__
        outcome.update(
            result="FAILED",
            code=error.code,
            cause=None if cause is None else f"{type(cause).__name__}: {str(cause)[:300]}",
        )
    outcome["total_seconds"] = round(time.perf_counter() - started, 2)
    outcome["calls"] = transport.calls[first_call:]
    outcome["repair_called"] = len(outcome["calls"]) > 1
    return outcome


def _count(values) -> dict:
    counted: dict = {}
    for value in values:
        counted[value] = counted.get(value, 0) + 1
    return counted


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--live", action="store_true", help="실제 엘리스 호출에 동의한다")
    parser.add_argument("--runs", type=int, default=1)
    args = parser.parse_args(argv)
    if not args.live:
        print("--live 없이는 부르지 않는다 (호출마다 비용이 든다).", file=sys.stderr)
        return 2
    if not 1 <= args.runs <= MAX_RUNS:
        print(f"--runs 는 1~{MAX_RUNS} 이다.", file=sys.stderr)
        return 2
    transport = TimedTransport()
    cases = [(YearMonth(2026, 9), frozenset({4})), (YearMonth(2026, 10), frozenset({3, 4}))]
    results = [
        run_once(transport, month=month, ages=ages)
        for month, ages in (cases * MAX_RUNS)[: args.runs]
    ]
    print(
        json.dumps(
            {"model_expected": MonthlyLlmConfig.from_env().model, "runs": results},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
