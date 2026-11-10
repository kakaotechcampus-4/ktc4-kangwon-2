"""생성 기록 — 월간 주제형(ADR-096). 단계 순서 · 끝 줄 · 실패 · 기록이 깨져도 같은 생성.

`db_session` 위에서 받아 적는 기록기(`Captured`)로 본다. 진짜 쓰기는 `test_generation_runs.py`.
"""

# ruff: noqa: F811 — 다른 테스트 파일의 픽스처를 가져와 쓰면 인자 이름이 import 와 겹친다

import json
from dataclasses import replace

from fastapi.testclient import TestClient
from ssuksak.adapters.request_aware_monthly_llm import RequestAwareMonthlyLlm
from ssuksak.planning.planner.contracts import MONTHLY_MODEL, RawLlmResponse
from test_generation_runs import (  # noqa: F401
    Broken,
    assert_attempts_shape,
    assert_forward,
    broken_run,
    captured_run,
    run_lines,
    spy_masked_memo,
    warnings,
)
from test_monthly_plans_api import (  # noqa: F401 — _approved 는 autouse
    _annual,
    _approved,
    _create,
    world,
)

from app.config import settings
from app.features.plans import monthly_router
from app.features.plans.generation_runs import PromptNoted
from app.main import app
from app.shared.llm import MODEL, LlmFailed
from app.shared.llm import client as llm

client = TestClient(app)


class Recording(RequestAwareMonthlyLlm):
    """mock 그대로 답하고 받은 요청의 판을 적는다. 수리 호출도 같은 문을 지난다."""

    def __init__(self):
        self.versions = []

    def generate_monthly(self, request):
        self.versions.append(request.prompt_version)
        return super().generate_monthly(request)


def _provider(monkeypatch, provider):
    monkeypatch.setattr(monthly_router, "monthly_llm_provider", lambda: provider)
    return provider


def test_월간_주제형은_이어받기_나누기_다듬기_저장_순서로_가고_끝_줄을_남긴다(
    world, captured_run, monkeypatch
):
    recording = _provider(monkeypatch, Recording())
    _annual(world["class_a"])

    response = _create(world)

    assert response.status_code == 201, response.text
    run = captured_run[-1]
    assert run.stages == ["prepare", "generate", "check", "save"]
    assert run.writes[0][1]["kind"] == "monthly_theme"
    final = run.final
    assert (final["status"], final["plan_id"]) == ("SUCCEEDED", response.json()["id"])
    assert (final["model"], final["llm_calls"]) == (None, 0)  # mock 은 전송을 지나지 않는다
    assert final["attempts"] is None  # 다시 한 일이 없다
    assert {"db_read", "select", "prompt", "validate", "assemble", "save"} <= set(final["phase_ms"])
    assert recording.versions and final["prompt_versions"] == list(
        dict.fromkeys(recording.versions)
    )
    assert_forward("monthly_theme", run.stages)


def test_real_모드_월간은_전송을_지난_호출_수와_모델과_모드를_남긴다(
    world, captured_run, monkeypatch
):
    """부모 연간은 real 로 바꾸기 전에 mock 으로 만든다. 작은 가짜가 `post_stream` 을 지난다."""
    _annual(world["class_a"])

    class Small(Recording):
        def generate_monthly(self, request):
            llm.post_stream(
                "https://x/v1/chat/completions",
                headers={},
                payload={"model": MODEL},
                timeout=1,
                fold=list,
                deadline=1,
            )
            return super().generate_monthly(request)

    small = _provider(monkeypatch, Small())
    monkeypatch.setattr(llm, "_post_stream", lambda *args, **kwargs: {})
    monkeypatch.setattr(settings, "llm_mode", "real")
    monkeypatch.setattr(settings, "is_server", True)

    response = _create(world)

    assert response.status_code == 201, response.text
    run = captured_run[-1]
    assert run.stages == ["prepare", "generate", "check", "save"]
    assert run.writes[0][1]["mode"] == "real"
    final = run.final
    assert (final["status"], final["model"]) == ("SUCCEEDED", MODEL)
    assert final["llm_calls"] == len(small.versions) >= 1
    assert "llm" in final["phase_ms"]


def test_real_모드_월간의_전송_재시도는_프롬프트_구간의_시도로_남고_생성은_같다(
    world, captured_run, monkeypatch
):
    """`phase` 는 `_llm_call` 의 `llm` 구간이 아니라 그것을 부른 쪽(월간은 `prompt`)이다."""
    _annual(world["class_a"])
    sent = []

    class Small(Recording):
        def generate_monthly(self, request):
            llm.post_stream(
                "https://x/v1/chat/completions",
                headers={},
                payload={"model": MODEL},
                timeout=1,
                fold=list,
                deadline=1,
            )
            return super().generate_monthly(request)

    def network(*args, **kwargs):
        sent.append(1)
        if len(sent) == 1:
            raise llm._NotDelivered("엘리스에 닿지 못했다")
        return {}

    _provider(monkeypatch, Small())
    monkeypatch.setattr(llm, "_post_stream", network)
    monkeypatch.setattr(llm, "RETRY_DELAY_SECONDS", 0)
    monkeypatch.setattr(settings, "llm_mode", "real")
    monkeypatch.setattr(settings, "is_server", True)

    response = _create(world)

    assert response.status_code == 201, response.text
    final = captured_run[-1].final
    assert final["llm_calls"] == len(sent) == 2  # 시도 기록은 상한 셈을 바꾸지 않는다
    assert final["attempts"] == [{"kind": "transport", "phase": "prompt", "result": "ok"}]
    assert_attempts_shape(final["attempts"])


def test_LLM_이_실패하면_실패한_단계와_보낸_판이_남는다(world, captured_run, monkeypatch):
    class Failing:
        versions = []

        def generate_monthly(self, request):
            self.versions.append(request.prompt_version)
            raise LlmFailed("timeout")

    failing = _provider(monkeypatch, Failing())
    _annual(world["class_a"])

    response = _create(world)

    assert response.status_code == 500
    run = captured_run[-1]
    final = run.final
    assert (final["status"], final["error_code"], final["plan_id"]) == (
        "FAILED",
        "GENERATION_FAILED",
        None,
    )
    assert run.stages == ["prepare", "generate"]  # 실패한 단계에서 멈춘다
    assert failing.versions and final["prompt_versions"] == list(dict.fromkeys(failing.versions))


class LegalClaimFirst(Recording):
    """첫 답에 법적 표현을 넣어 수리 대상으로 만든다. 수리 호출에는 빈 답을 낸다."""

    def generate_monthly(self, request):
        if self.versions:  # 두 번째 호출 = 수리
            self.versions.append(request.prompt_version)
            return RawLlmResponse(content="{}", model=MONTHLY_MODEL)
        response = super().generate_monthly(request)
        body = json.loads(response.content)
        focus = next(s for s in body["weeks"][0]["sections"] if s["section_key"] == "focus")
        focus["value"] = "법적 기준에 맞게 바람을 살펴본다."
        return replace(response, content=json.dumps(body, ensure_ascii=False))


def test_수리_대상이_되면_수리_호출_하나가_남고_수리_뒤에_틀리면_check_에서_실패로_끝난다(
    world, captured_run, monkeypatch
):
    """수리 결과는 호출 결과(답을 받았나)다. 고친 답이 검사를 통과했는지는 실행의 끝이 말한다."""
    recording = _provider(monkeypatch, LegalClaimFirst())
    _annual(world["class_a"])

    response = _create(world)

    assert response.status_code == 500
    assert len(recording.versions) == 2  # 첫 호출 + 수리 1회
    run = captured_run[-1]
    assert (run.final["status"], run.stages[-1]) == ("FAILED", "check")
    assert run.final["attempts"] == [{"kind": "repair", "phase": "repair", "result": "ok"}]
    assert_attempts_shape(run.final["attempts"])


def test_월간은_판_기록을_가명_처리_안쪽에_둔다(world, monkeypatch):
    _provider(monkeypatch, Recording())
    _annual(world["class_a"])
    seen = spy_masked_memo(monkeypatch, monthly_router)

    assert _create(world).status_code == 201

    assert len(seen) == 1 and isinstance(seen[0], PromptNoted)


def test_기록이_깨져도_월간_생성은_같다(world, broken_run, warnings):
    _annual(world["class_a"])
    warnings.clear()  # 부모 연간 요청의 경고는 뺀다

    created = _create(world)

    assert created.status_code == 201, created.text
    assert client.get(f"/api/plans/monthly/{created.json()['id']}").json() == created.json()
    failures = run_lines(warnings)
    assert len(failures) == 1 and " step=begin type=RuntimeError" in failures[0]
    assert Broken.SECRET not in "".join(warnings)

    again = _create(world)  # 실패하는 생성에 기록 실패가 겹쳐도 원래 봉투가 그대로다

    assert (again.status_code, again.json()["error"]["code"]) == (409, "ALREADY_EXISTS")
