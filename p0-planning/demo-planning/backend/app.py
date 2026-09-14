"""Planning Integration Demo — Yearly → Monthly.

한 명령으로 Demo API와 정적 Frontend를 함께 띄운다.

    python demo-planning/backend/app.py
    python demo-planning/backend/app.py --port 8800

**버려도 되는 코드다.** Production HTTP Adapter가 아니고 인증·DB·배포 구성도
없다. 표준 라이브러리 `http.server`만 쓰므로 추가 패키지 설치가 필요 없다.

이 파일은 Business Logic을 갖지 않는다. 요청을 받아 **기존 실제 Use Case**를
호출하고 결과를 JSON으로 옮길 뿐이다. Gate·Validation·선택 규칙은 전부
Production Rule이 판정한다. Front가 status를 바꾸거나 Gate를 흉내 내지 않는다.

    POST /api/session/reset      새 InMemory 세션
    GET  /api/state              현재 세션 상태
    POST /api/yearly/generate    GenerateYearlyPlan
    POST /api/yearly/confirm     ConfirmYearlyPlan
    POST /api/yearly/regenerate  RegenerateYearlyPlanItem   (선택)
    POST /api/yearly/edit        EditYearlyPlanItem          (선택)
    POST /api/monthly/generate   GenerateMonthlyPlan
    POST /api/monthly/confirm    ConfirmMonthlyPlan
    POST /api/monthly/regenerate RegenerateMonthlyPlanItem   (선택)
    POST /api/monthly/edit       EditMonthlyPlanItem         (선택)

Persistence는 InMemory이며 프로세스 종료 시 사라진다.

**LLM은 Yearly에서 실제로 호출된다.** `GenerateYearlyPlan(use_llm=True)` 경로가
기존 Elice MLAPI Adapter와 환경변수 설정을 그대로 쓴다. FakeLLM / mock /
fixture / canned fallback이 없다. 호출이 실패하면 가짜 결과로 대체하지 않고
실제 오류를 화면에 그대로 보여 준다. Monthly는 현재 Contract대로 0회다.

API Key와 Prompt 전문은 응답·로그·화면 어디에도 싣지 않는다. telemetry는
provider / model / token 수 / latency / 성공 여부만 담는다.

`--yearly-rule-only`는 **운영자가 직접 지정할 때만** Yearly를 Rule 전용 경로
(`use_llm=False`)로 돌린다. 실패했을 때 자동으로 전환되는 fallback이 아니다.
LLM 호출이 실패하면 언제나 실제 오류가 그대로 표시된다. 이 플래그는 API Key가
만료된 상황에서도 Yearly → Monthly 연결 자체를 확인하기 위한 개발용 스위치이며,
켜져 있으면 화면 상단과 서버 배너에 그대로 표시된다.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
import threading
import traceback
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
FRONTEND = HERE.parent / "frontend"
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from composition import build_demo_wiring  # noqa: E402
from views import error_view, monthly_view, yearly_view  # noqa: E402

from ssuksak.planning.application.dto import (  # noqa: E402
    ClassroomContext,
    ConfirmYearlyPlanCommand,
    DaycareContext,
    EditYearlyPlanItemCommand,
    GenerateYearlyPlanCommand,
    ItemAddress,
    PlanningSetup,
    RegenerateYearlyPlanItemCommand,
)
from ssuksak.planning.application.monthly_dto import (  # noqa: E402
    ConfirmMonthlyPlanCommand,
    EditMonthlyPlanItemCommand,
    GenerateMonthlyPlanCommand,
    MonthlyCellAddress,
    RegenerateMonthlyPlanItemCommand,
)
from ssuksak.planning.domain.errors import PlanningError  # noqa: E402
from ssuksak.planning.domain.identifiers import (  # noqa: E402
    ActorId,
    InvalidIdentifierError,
)
from ssuksak.planning.rules.periods import academic_period_keys  # noqa: E402
from ssuksak.shared.llm.config import LLMConfigError  # noqa: E402
from ssuksak.shared.llm.port import (  # noqa: E402
    LLMConfigurationError,
    LLMUnavailableError,
)

DEMO_ACTOR = ActorId("teacher_demo_001")
"""opaque actor. 담임 표시 이름이 아니다(OD-Y03)."""

MONTH_LABELS = {
    3: "3월", 4: "4월", 5: "5월", 6: "6월", 7: "7월", 8: "8월",
    9: "9월", 10: "10월", 11: "11월", 12: "12월", 1: "1월", 2: "2월",
}


# =========================================================== 세션 (InMemory)


class Session:
    """프로세스 수명 동안만 유지되는 Demo 세션.

    상태 보관만 한다. 판단·검증은 전부 Use Case가 한다.
    """

    def __init__(
        self,
        *,
        yearly_use_llm: bool = True,
        monthly_llm: bool = True,
        llm=None,
    ) -> None:
        """Args:
        llm: Composition에 그대로 넘긴다. 기본값 None이면 환경변수로 만든 실제
            Adapter를 쓴다. 결정론 E2E가 route 전 경로를 실제 호출 없이 돌리기
            위한 seam이며, **실행 중에 자동으로 선택되지 않는다.**
        """
        self.lock = threading.Lock()
        self.yearly_use_llm = yearly_use_llm
        self.monthly_llm = monthly_llm
        self.llm = llm
        self.reset()

    def reset(self) -> None:
        # 설정이 없으면 여기서 실패한다. 가짜 LLM으로 대체하지 않는다.
        self.wiring = None
        self.llm_config_error = None
        try:
            self.wiring = build_demo_wiring(
                use_llm=self.yearly_use_llm,
                monthly_llm=self.monthly_llm,
                llm=self.llm,
            )
        except LLMConfigError as exc:
            self.llm_config_error = str(exc)
        self.yearly_plan = None
        self.yearly_run = None
        self.daycare_ref = "demo_daycare_001"
        self.monthly_plan = None
        self.monthly_run = None
        self.log: list[dict] = []

    # ------------------------------------------------------------ 조회용

    def note(self, action: str, ok: bool, detail: str) -> None:
        self.log.append({"action": action, "ok": ok, "detail": detail})
        del self.log[:-40]

    def state(self) -> dict:
        w = self.wiring
        if w is None:
            return {
                "ok": False,
                "kind": "LLM_CONFIG",
                "llm_config_error": self.llm_config_error,
                "references": None,
                "yearly": None,
                "monthly": None,
                "selectable_months": [],
                "monthly_generate_enabled": False,
                "log": list(self.log),
            }
        school_year = (
            self.yearly_plan.school_year if self.yearly_plan is not None else None
        )
        months = []
        if school_year is not None:
            for key in academic_period_keys(school_year):
                months.append(
                    {
                        "period_key": key.value,
                        "label": MONTH_LABELS.get(
                            key.calendar_month, f"{key.calendar_month}월"
                        ),
                    }
                )
        return {
            "ok": True,
            "references": {
                "theme_catalog_id": w.theme_selector.catalog_id,
                "theme_catalog_version": w.theme_selector.catalog_version,
                "template_id": w.template_ref.template_id,
                "template_version": w.template_ref.template_version,
                "safety_rule_version": w.safety_selector.legal_rule_version,
                "activity_catalog_id": w.activity_selector.catalog_id,
                "activity_catalog_version": w.activity_selector.catalog_version,
                "llm_provider": w.yearly.provider,
                "llm_model": w.yearly.model,
                "llm_api_style": w.yearly.api_style,
                "live_api": w.yearly.live_api,
                "yearly_uses_llm": self.yearly_use_llm,
                "monthly_generation_mode": (
                    "LLM_PLANNER" if self.monthly_llm else "RULE_ONLY"
                ),
            },
            "llm_calls": [
                # API Key도 Prompt도 담지 않는다. 관측값만 담는다.
                {
                    "operation": r.operation,
                    "provider": r.provider,
                    "model": r.model,
                    "success": r.success,
                    "latency_ms": r.latency_ms,
                    "retry_count": r.retry_count,
                    "item_count": r.item_count,
                    "input_tokens": r.input_tokens,
                    "output_tokens": r.output_tokens,
                    "validation_result": r.validation_result,
                    "failure_kind": r.failure_kind,
                }
                for r in w.llm_records
            ],
            "yearly": None
            if self.yearly_plan is None
            else yearly_view(self.yearly_plan, self.yearly_run),
            "monthly": None
            if self.monthly_plan is None
            else monthly_view(self.monthly_plan, self.monthly_run),
            "selectable_months": months,
            "monthly_generate_enabled": (
                self.yearly_plan is not None
                and self.yearly_plan.status.value == "CONFIRMED"
            ),
            "log": list(self.log),
        }


SESSION = Session()


# ============================================================= Use Case 호출


def _actor(body: dict) -> ActorId:
    raw = (body.get("actor_id") or "").strip()
    if not raw:
        return DEMO_ACTOR
    return ActorId(raw)


def _ages(body: dict) -> frozenset[int]:
    raw = body.get("ages") or []
    ages = frozenset(int(a) for a in raw)
    if not ages:
        raise ValueError("ages가 비어 있습니다")
    return ages


def api_reset(body: dict) -> dict:
    SESSION.reset()
    SESSION.note("session.reset", True, "새 InMemory 세션을 만들었습니다")
    return SESSION.state()


def api_state(body: dict) -> dict:
    return SESSION.state()


def _require_wiring():
    if SESSION.wiring is None:
        raise LLMConfigError(SESSION.llm_config_error or "LLM 설정이 없습니다")
    return SESSION.wiring


def api_yearly_generate(body: dict) -> dict:
    w = _require_wiring()
    # YearlyPlan은 daycare_ref를 갖지 않는다(OD-Y03: 소유 단위는 classroom).
    # Monthly 생성에 필요하므로 Demo 세션이 입력값을 기억한다.
    daycare_ref = (body.get("daycare_ref") or "demo_daycare_001").strip()
    result = w.yearly.generate.execute(
        GenerateYearlyPlanCommand(
            school_year=int(body.get("school_year", 2026)),
            daycare=DaycareContext(daycare_ref=daycare_ref),
            classroom=ClassroomContext(
                classroom_ref=(
                    body.get("classroom_ref") or "demo_classroom_001"
                ).strip(),
                ages=_ages(body),
            ),
            planning_setup=PlanningSetup(completed=True, start_mode="CREATE_NEW"),
            catalog=w.theme_selector,
        )
    )
    SESSION.yearly_plan = result.plan
    SESSION.yearly_run = result.run
    SESSION.daycare_ref = daycare_ref
    SESSION.monthly_plan = None
    SESSION.monthly_run = None
    SESSION.note(
        "yearly.generate",
        True,
        f"{result.plan.plan_id.value} · {result.plan.status.value} · "
        f"{len(result.plan.month_periods)}개월 · "
        f"LLM {result.run.llm_call_count}회 / {result.run.llm_item_count}항목",
    )
    return SESSION.state()


def api_yearly_confirm(body: dict) -> dict:
    w = _require_wiring()
    result = w.yearly.confirm.execute(
        ConfirmYearlyPlanCommand(
            plan_id=SESSION.yearly_plan.plan_id.value,
            actor_id=_actor(body),
            catalog=w.theme_selector,
        )
    )
    SESSION.yearly_plan = result.plan
    SESSION.note(
        "yearly.confirm", True, f"DRAFT → {result.plan.status.value}"
    )
    return SESSION.state()


def api_yearly_edit(body: dict) -> dict:
    w = _require_wiring()
    result = w.yearly.edit.execute(
        EditYearlyPlanItemCommand(
            plan_id=SESSION.yearly_plan.plan_id.value,
            address=ItemAddress(item_id=body["item_id"]),
            new_value=body.get("new_value", ""),
            actor_id=_actor(body),
        )
    )
    SESSION.yearly_plan = result.plan
    SESSION.note("yearly.edit", True, body["item_id"])
    return SESSION.state()


def api_yearly_regenerate(body: dict) -> dict:
    w = _require_wiring()
    result = w.yearly.regenerate.execute(
        RegenerateYearlyPlanItemCommand(
            plan_id=SESSION.yearly_plan.plan_id.value,
            address=ItemAddress(item_id=body["item_id"]),
            actor_id=_actor(body),
            catalog=w.theme_selector,
        )
    )
    SESSION.yearly_plan = result.plan
    if result.run is not None:
        SESSION.yearly_run = result.run
    SESSION.note("yearly.regenerate", True, body["item_id"])
    return SESSION.state()


def api_monthly_generate(body: dict) -> dict:
    w = _require_wiring()
    parent = SESSION.yearly_plan
    if parent is None:
        raise ValueError("먼저 연간계획을 생성하세요")
    result = w.monthly_generate.execute(
        GenerateMonthlyPlanCommand(
            parent_yearly_plan_id=parent.plan_id.value,
            school_year=parent.school_year,
            target_month=body["target_month"],
            daycare=DaycareContext(daycare_ref=SESSION.daycare_ref),
            classroom=ClassroomContext(
                classroom_ref=parent.classroom_ref, ages=parent.classroom_ages
            ),
            planning_setup=PlanningSetup(completed=True, start_mode="CREATE_NEW"),
            template_ref=w.template_ref,
            safety_rule=w.safety_selector,
            catalog=w.theme_selector,
            activity_catalog=w.activity_selector,
            # Mode와 Template을 **Composition이** 정한다. Frontend가 보내지 않고
            # Use Case가 환경을 보고 고르지도 않는다.
            generation_mode=w.monthly_generation_mode,
        )
    )
    SESSION.monthly_plan = result.plan
    SESSION.monthly_run = result.run
    SESSION.note(
        "monthly.generate",
        True,
        f"{result.plan.target_month.value} · {result.run.week_period_count}주 · "
        f"{result.run.generation_mode} · LLM {result.run.llm_call_count}회"
        + (
            f" · repair {result.run.planner_validation_repair_count}"
            if result.run.llm_invoked
            else f" · Activity FILLED {result.run.activity_filled_cell_count}"
        ),
    )
    return SESSION.state()


def api_monthly_confirm(body: dict) -> dict:
    result = _require_wiring().monthly_confirm.execute(
        ConfirmMonthlyPlanCommand(
            plan_id=SESSION.monthly_plan.plan_id.value, actor_id=_actor(body)
        )
    )
    SESSION.monthly_plan = result.plan
    SESSION.note("monthly.confirm", True, f"DRAFT → {result.plan.status.value}")
    return SESSION.state()


def _monthly_address(body: dict) -> MonthlyCellAddress:
    return MonthlyCellAddress(
        target_month=SESSION.monthly_plan.target_month.value,
        section_key=body["section_key"],
        week_id=body.get("week_id") or None,
    )


def api_monthly_edit(body: dict) -> dict:
    result = _require_wiring().monthly_edit.execute(
        EditMonthlyPlanItemCommand(
            plan_id=SESSION.monthly_plan.plan_id.value,
            address=_monthly_address(body),
            new_value=body.get("new_value", ""),
            actor_id=_actor(body),
        )
    )
    SESSION.monthly_plan = result.plan
    SESSION.note("monthly.edit", True, f"{body['section_key']} {body.get('week_id')}")
    return SESSION.state()


def api_monthly_regenerate(body: dict) -> dict:
    result = _require_wiring().monthly_regenerate.execute(
        RegenerateMonthlyPlanItemCommand(
            plan_id=SESSION.monthly_plan.plan_id.value,
            address=_monthly_address(body),
            actor_id=_actor(body),
        )
    )
    SESSION.monthly_plan = result.plan
    outcome = result.activity_regeneration
    SESSION.note(
        "monthly.regenerate",
        True,
        f"{body['section_key']} {body.get('week_id')}"
        + (
            f" · {outcome.previous_activity_id} → {outcome.selected_activity_id}"
            f" ({outcome.reason})"
            if outcome
            else ""
        )
        + (
            f" · LLM {result.cell_regeneration.provider_call_count}회"
            f" · repair {result.cell_regeneration.validation_repair_count}"
            if result.cell_regeneration
            else ""
        ),
    )
    state = SESSION.state()
    cell = result.cell_regeneration
    if cell is not None:
        # 교사 화면에 쓰지 않는다. Debug Panel 전용이며 Prompt·Key·Source 전문은
        # 애초에 담기지 않는다.
        state["last_cell_regeneration"] = {
            "section_key": body["section_key"],
            "week_id": body.get("week_id"),
            "value": cell.proposal.value,
            "activity_origin": (
                cell.proposal.activity_origin.value
                if cell.proposal.activity_origin is not None
                else None
            ),
            "reference_activity_id": cell.proposal.reference_activity_id,
            "provider_call_count": cell.provider_call_count,
            "validation_repair_count": cell.validation_repair_count,
            "repaired_violations": list(cell.rejected_violation_codes),
        }
    if outcome is not None:
        state["last_activity_regeneration"] = {
            "previous_activity_id": outcome.previous_activity_id,
            "previous_value": outcome.previous_value,
            "selected_activity_id": outcome.selected_activity_id,
            "selected_value": outcome.selected_value,
            "reason": outcome.reason,
            "catalog_id": outcome.catalog_id,
            "catalog_version": outcome.catalog_version,
            "rule_id": outcome.rule_id,
            "rule_version": outcome.rule_version,
            "candidate_count": outcome.trace.candidate_count,
        }
    return state


ROUTES = {
    "/api/session/reset": api_reset,
    "/api/state": api_state,
    "/api/yearly/generate": api_yearly_generate,
    "/api/yearly/confirm": api_yearly_confirm,
    "/api/yearly/edit": api_yearly_edit,
    "/api/yearly/regenerate": api_yearly_regenerate,
    "/api/monthly/generate": api_monthly_generate,
    "/api/monthly/confirm": api_monthly_confirm,
    "/api/monthly/edit": api_monthly_edit,
    "/api/monthly/regenerate": api_monthly_regenerate,
}


# ==================================================================== HTTP


class Handler(SimpleHTTPRequestHandler):
    """정적 파일은 frontend/, `/api/*`는 Use Case 호출."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(FRONTEND), **kwargs)

    # 요청 로그를 줄인다. Demo 콘솔이 시끄러워지지 않게.
    def log_message(self, fmt, *args):  # noqa: A003
        if self.path.startswith("/api/"):
            sys.stderr.write(f"  {self.command} {self.path}\n")

    def end_headers(self):
        """정적 파일도 캐시하지 않는다.

        Demo는 파일을 자주 고치는 코드다. 브라우저가 `index.html`은 캐시에서
        쓰고 `app.js`만 새로 받으면 **서로 맞지 않는 조합**이 만들어진다. 그때
        나는 오류(없는 element·없는 전역)는 원인을 찾기가 매우 어렵다.
        `SimpleHTTPRequestHandler`의 기본 조건부 캐시가 Demo에는 맞지 않는다.
        """
        if not self.path.startswith("/api/"):
            self.send_header("Cache-Control", "no-store, must-revalidate")
        super().end_headers()

    def _json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802
        if self.path.split("?")[0] == "/api/state":
            with SESSION.lock:
                self._json(200, SESSION.state())
            return
        if self.path.startswith("/api/"):
            self._json(405, {"ok": False, "kind": "METHOD", "message": "POST를 쓰세요"})
            return
        super().do_GET()

    def do_POST(self):  # noqa: N802
        path = self.path.split("?")[0]
        handler = ROUTES.get(path)
        if handler is None:
            self._json(404, {"ok": False, "kind": "NOT_FOUND", "message": path})
            return

        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw.decode("utf-8") or "{}")
        except json.JSONDecodeError as exc:
            self._json(400, {"ok": False, "kind": "BAD_JSON", "message": str(exc)})
            return

        with SESSION.lock:
            try:
                self._json(200, handler(body))
            except PlanningError as exc:
                # Gate / Validation 실패는 정상적인 Demo 결과다. 그대로 보여 준다.
                payload = error_view(exc)
                payload["state"] = SESSION.state()
                SESSION.note(path, False, f"{exc.violated_rule}")
                self._json(409, payload)
            except LLMConfigError as exc:
                # 설정 부재를 가짜 결과로 대체하지 않는다. 그대로 보여 준다.
                SESSION.note(path, False, "LLM 설정 오류")
                self._json(
                    503,
                    {
                        "ok": False,
                        "kind": "LLM_CONFIG",
                        "message": str(exc),
                        "hint": "프로젝트 루트 .env 또는 OS 환경변수에 "
                        "ELICE_MLAPI_BASE_URL / ELICE_MLAPI_API_KEY / LLM_MODEL 이 "
                        "필요합니다. 값은 화면에 표시하지 않습니다.",
                        "state": SESSION.state(),
                    },
                )
            except LLMUnavailableError as exc:
                # 재시도 후에도 실패했다. **Rule-only 결과로 대체하지 않는다.**
                # 기존 Plan은 그대로 남고 사용자는 다시 시도할 수 있다.
                SESSION.note(path, False, f"LLM 호출 실패 ({exc.kind})")
                self._json(
                    503,
                    {
                        "ok": False,
                        "kind": "LLM_UNAVAILABLE",
                        "message": "AI 생성에 실패했습니다. 잠시 후 다시 시도해 주세요.",
                        # 내부 분류는 개발용이다. API Key도 Prompt도 담기지 않는다.
                        "failure_kind": exc.kind,
                        "state": SESSION.state(),
                    },
                )
            except LLMConfigurationError as exc:
                # 인증·권한·모델 오류. 재시도가 무의미하므로 운영자에게 알린다.
                SESSION.note(path, False, f"LLM 설정 오류 ({exc.kind})")
                self._json(
                    503,
                    {
                        "ok": False,
                        "kind": "LLM_CONFIG",
                        "message": "AI 설정에 문제가 있어 생성할 수 없습니다.",
                        "failure_kind": exc.kind,
                        "hint": "ELICE_MLAPI_BASE_URL / ELICE_MLAPI_API_KEY / "
                        "LLM_MODEL 설정을 확인하세요. 값은 화면에 표시하지 않습니다.",
                        "state": SESSION.state(),
                    },
                )
            except (InvalidIdentifierError, KeyError, ValueError) as exc:
                self._json(
                    400,
                    {
                        "ok": False,
                        "kind": "INPUT",
                        "message": f"{type(exc).__name__}: {exc}",
                        "state": SESSION.state(),
                    },
                )
            except Exception as exc:  # noqa: BLE001 - Demo 서버가 죽지 않게
                # LLM 호출 실패도 여기로 온다. 가짜 결과로 대체하지 않는다.
                traceback.print_exc()
                SESSION.note(path, False, type(exc).__name__)
                self._json(
                    500,
                    {
                        "ok": False,
                        "kind": "UNEXPECTED",
                        "message": f"{type(exc).__name__}: {exc}",
                        "state": SESSION.state(),
                    },
                )


def main(argv: list[str] | None = None) -> int:
    # Windows 콘솔이 cp949여도 배너가 깨지거나 죽지 않게 한다.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001 - 재구성 불가여도 서버는 떠야 한다
            pass
    parser = argparse.ArgumentParser(
        prog="python demo-planning/backend/app.py",
        description="쓱싹요정 Planning Integration Demo (제품 서버가 아님)",
    )
    parser.add_argument("--port", type=int, default=8800)
    parser.add_argument(
        "--yearly-rule-only",
        action="store_true",
        help="Yearly를 Rule 전용 경로(use_llm=False)로 실행한다. 실패 시 자동 "
        "전환되는 fallback이 아니라 운영자가 직접 켜는 스위치다.",
    )
    parser.add_argument(
        "--monthly-rule-only",
        action="store_true",
        help="Monthly를 기존 Rule 전용 경로로 실행한다(Template v0.1.0). "
        "L8 기본 시연 경로는 LLM_PLANNER이며 이것은 개발 옵션이다.",
    )
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args(argv)

    if args.yearly_rule_only or args.monthly_rule_only:
        SESSION.yearly_use_llm = not args.yearly_rule_only
        SESSION.monthly_llm = not args.monthly_rule_only
        SESSION.reset()

    full = SESSION.state()
    print("=" * 64)
    print(" 쓱싹요정 Planning Integration Demo  (Yearly → Monthly)")
    print("=" * 64)
    if full.get("references") is None:
        print("  ! LLM 설정을 찾지 못했습니다.")
        print(f"    {full.get('llm_config_error')}")
        print("    .env 또는 OS 환경변수에 ELICE_MLAPI_BASE_URL /")
        print("    ELICE_MLAPI_API_KEY / LLM_MODEL 이 필요합니다.")
        print("    Demo는 뜨지만 연간계획 생성 시 실제 오류를 표시합니다.")
    else:
        ref = full["references"]
        print(f"  Theme Reference   : {ref['theme_catalog_version']}")
        print(f"  Monthly Template  : {ref['template_version']}")
        print(f"  Safety Legal Rule : {ref['safety_rule_version']}")
        print(f"  Activity Reference: {ref['activity_catalog_version']}")
        print(
            f"  Yearly LLM        : {ref['llm_provider']} / {ref['llm_model']}"
            f" ({ref['llm_api_style']}) - 실제 호출"
        )
        print("  Monthly LLM       : 호출 0회 (현재 Contract)")
    if args.yearly_rule_only:
        print("-" * 64)
        print("  ! --yearly-rule-only 가 켜져 있습니다.")
        print("    Yearly가 LLM을 호출하지 않고 Rule 전용 경로로 실행됩니다.")
        print("    실제 LLM 결과를 보려면 이 플래그 없이 다시 실행하세요.")
    print("  Persistence       : InMemory (프로세스 종료 시 소멸)")
    print("-" * 64)
    print(f"  브라우저에서 열기 : http://{args.host}:{args.port}/")
    print("  종료              : Ctrl+C")
    print("=" * 64)

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n종료합니다. InMemory 데이터는 소멸합니다.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
