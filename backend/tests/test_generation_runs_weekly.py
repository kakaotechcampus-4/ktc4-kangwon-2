"""생성 기록 — 주간 · 놀이 중심 월간(ADR-096). 단계 순서 · 끝 줄 · 실패 · 기록이 깨져도 같은 생성.

`db_session` 위에서 받아 적는 기록기(`Captured`)로 본다. 진짜 쓰기는 `test_generation_runs.py`.
"""

# ruff: noqa: F811 — 다른 테스트 파일의 픽스처를 가져와 쓰면 인자 이름이 import 와 겹친다

import json
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete
from sqlalchemy.orm import Session
from ssuksak.adapters.request_aware_weekly_llm import RequestAwareWeeklyLlm
from ssuksak.planning.domain.monthly_template import SemanticVariant
from ssuksak.planning.planner.weekly import WEEKLY_CONTEXT_PROMPT_VERSION
from ssuksak.planning.venue_policy import VENUE_POLICY_TAG
from test_generation_runs import (  # noqa: F401
    Broken,
    _rows,
    assert_forward,
    broken_run,
    captured_run,
    committed,
    run_lines,
    spy_masked_memo,
    warnings,
)
from test_play_monthly_create_api import _annual as _play_annual
from test_weekly_plans_api import (  # noqa: F401
    FOCUS,
    LABELS,
    WEEK,
    ApprovedTemplates,
    _answer,
    _approved,
    _create,
    _error,
    _monthly,
    world,
)

from app.config import settings
from app.db import engine
from app.features.plans import monthly_llm, play_monthly_router, weekly_router
from app.features.plans.generation_runs import RUN_HEADER, PromptNoted
from app.features.template_profiles.models import (
    TemplateProfileDefault,
    TemplateProfileOverride,
    TemplateProfileVersion,
)
from app.features.template_profiles.repository import PostgresTemplateProfileRepository
from app.main import app
from app.shared.llm import MODEL, LlmFailed
from app.shared.llm import client as llm

client = TestClient(app)
PLAY_URL = "/api/plans/monthly/play"


def _versions(provider: RequestAwareWeeklyLlm) -> list[str]:
    """mock 이 받은 요청의 판 — 처음 쓴 순서, 중복 없이."""
    return list(dict.fromkeys(request.prompt_version for request in provider.requests))


def _post_play(world, **body):
    return client.post(PLAY_URL, json={"class_id": world["mine"]["class"], "month": 10, **body})


class _Response:
    def __init__(self, body):
        self._body = json.dumps(body).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return self._body


# ── 주간 ──────────────────────────────────────────────────────────────────


def test_주간은_단계를_앞으로만_가고_저장으로_끝나며_끝_줄을_남긴다(
    world, captured_run, monkeypatch
):
    provider = RequestAwareWeeklyLlm()
    monkeypatch.setattr(weekly_router, "_weekly_provider", lambda: provider)

    response = _create(world)

    assert response.status_code == 201, response.text
    run = captured_run[-1]
    # mock 은 llm 구간이 없어 「요일별 활동 나누기」를 건너뛴다(앞으로 건너뛰기는 괜찮다).
    assert_forward("weekly", run.stages)
    assert run.writes[0][1]["kind"] == "weekly"
    final = run.final
    assert (final["status"], final["plan_id"]) == ("SUCCEEDED", response.json()["id"])
    assert (final["model"], final["llm_calls"]) == (None, 0)
    assert {"db_read", "select", "validate", "assemble", "save"} <= set(final["phase_ms"])
    assert _versions(provider) and final["prompt_versions"] == _versions(provider)


def test_real_모드_주간은_전송을_지나_요일별_활동_나누기_단계가_열린다(
    world, captured_run, monkeypatch
):
    """진짜 어댑터를 지난다 — `urlopen` 만 가짜다. 후보가 없는 기본 생성은 `post_json` 을 지난다."""
    sent = []

    def urlopen(request, timeout):
        payload = json.loads(request.data)
        sent.append(payload)
        return _Response(_answer(payload))

    monkeypatch.setattr(llm.urllib_request, "urlopen", urlopen)
    monkeypatch.setattr(settings, "llm_mode", "real")
    monkeypatch.setattr(settings, "weekly_llm_enabled", True)
    monkeypatch.setattr(settings, "is_server", True)
    monkeypatch.setattr(settings, "elice_mlapi_base_url", "https://llm.invalid/v1")
    monkeypatch.setattr(settings, "elice_mlapi_api_key", "test-only-not-a-key")

    response = _create(world)

    assert response.status_code == 201, response.text
    run = captured_run[-1]
    assert run.stages == ["prepare", "generate", "check", "save"]  # llm span 이 generate 를 연다
    assert run.writes[0][1]["mode"] == "real"
    final = run.final
    assert (final["status"], final["model"]) == ("SUCCEEDED", MODEL)
    assert final["llm_calls"] == len(sent) >= 1
    # 어댑터가 보내는 payload 에는 판이 없다 — 판은 요청에 실려 provider 를 지날 때 적힌다.
    assert [v.split("+")[0] for v in final["prompt_versions"]] == [WEEKLY_CONTEXT_PROMPT_VERSION]
    assert "llm" in final["phase_ms"]


def test_주간_LLM_이_실패하면_저장까지_가지_않고_보낸_판이_남는다(world, captured_run, monkeypatch):
    class Failing:
        versions = []

        def generate_weekly(self, request):
            self.versions.append(request.prompt_version)
            raise LlmFailed("timeout")

    failing = Failing()
    monkeypatch.setattr(weekly_router, "_weekly_provider", lambda: failing)

    response = _create(world)

    assert _error(response) == (500, "GENERATION_FAILED", [])
    run = captured_run[-1]
    final = run.final
    assert (final["status"], final["error_code"], final["plan_id"]) == (
        "FAILED",
        "GENERATION_FAILED",
        None,
    )
    assert "save" not in run.stages  # 실패한 단계에서 멈춘다
    assert failing.versions and final["prompt_versions"] == list(dict.fromkeys(failing.versions))


def test_주간은_판_기록을_가명_처리_안쪽에_둔다(world, monkeypatch):
    seen = spy_masked_memo(monkeypatch, weekly_router)

    assert _create(world).status_code == 201

    assert len(seen) == 1 and isinstance(seen[0], PromptNoted)


@pytest.fixture
def committed_weekly(committed):
    """`committed` 위에 승인된 양식 프로필과 확정된 연간 · 월간을 진짜 commit 한다 — 주간의 전제.

    `world`(db_session 안)와 달리 롤백이 없어서 만든 것을 직접 지운다. `committed` 의 정리가
    계획안 · 반 · 계정 · 원을 지우므로 여기서는 그보다 먼저 양식 프로필만 지운다.
    """
    with Session(engine) as session:
        ref = PostgresTemplateProfileRepository(
            session, center_id=committed.center
        ).start_from_reference(
            ApprovedTemplates(),
            FOCUS,
            selected_optional_keys=("focus",),
            display_labels=LABELS,
            focus_variant=SemanticVariant.SUBTHEME,
            actor_id=committed.owner[0],
        )
        session.commit()
    profile = {"profile_id": ref.profile_id, "profile_version": ref.profile_version}
    try:
        _monthly({"class": committed.klass, "profile": profile})
        yield committed
    finally:
        with Session(engine) as session:
            session.execute(
                delete(TemplateProfileOverride).where(
                    TemplateProfileOverride.class_id == committed.klass
                )
            )
            session.execute(
                delete(TemplateProfileDefault).where(
                    TemplateProfileDefault.center_id == committed.center
                )
            )
            session.execute(
                delete(TemplateProfileVersion).where(
                    TemplateProfileVersion.center_id == committed.center
                )
            )
            session.commit()


def test_주간을_진짜_commit_하면_새_연결로_읽어도_한_줄이다(committed_weekly):
    rid = uuid.uuid4()

    created = client.post(
        "/api/plans/weekly",
        json={"class_id": committed_weekly.klass, "week_id": WEEK},
        headers={RUN_HEADER: str(rid)},
    )

    assert created.status_code == 201, created.text
    rows = _rows(id=rid)
    assert len(rows) == 1  # 기록을 삼켜 0건인데 초록이 되는 것을 막는다
    row = rows[0]
    assert (row.kind, row.status, row.stage) == ("weekly", "SUCCEEDED", "save")
    assert row.plan_id == created.json()["id"]
    assert (row.center_id, row.class_id, row.mode) == (
        committed_weekly.center,
        committed_weekly.klass,
        "mock",
    )
    assert row.prompt_versions == [
        WEEKLY_CONTEXT_PROMPT_VERSION + VENUE_POLICY_TAG
    ]  # mock 도 판이 남는다
    assert row.llm_calls == 0 and {"db_read", "save"} <= set(row.phase_ms)
    assert row.finished_at > row.started_at


def test_기록이_깨져도_주간_생성은_같다(world, broken_run, warnings):
    warnings.clear()  # 세계를 만들 때 부른 요청의 경고는 뺀다

    created = _create(world)

    assert created.status_code == 201, created.text
    assert client.get(f"/api/plans/weekly/{created.json()['id']}").json() == created.json()
    failures = run_lines(warnings)
    assert len(failures) == 1 and " step=begin type=RuntimeError" in failures[0]
    assert Broken.SECRET not in "".join(warnings)

    again = _create(world)  # 실패하는 생성에 기록 실패가 겹쳐도 원래 봉투가 그대로다

    assert _error(again)[:2] == (409, "ALREADY_EXISTS")


# ── 놀이 중심 월간 ─────────────────────────────────────────────────────────


class PlayRecording:
    def __init__(self):
        self.versions = []

    def generate_play_monthly(self, request):
        self.versions.append(request.prompt_version)
        return monthly_llm.MockPlayMonthlyProvider().generate_play_monthly(request)


def test_놀이_월간도_단계를_앞으로만_가고_끝_줄에_판이_남는다(world, captured_run, monkeypatch):
    recording = PlayRecording()
    monkeypatch.setattr(monthly_llm, "play_monthly_provider", lambda: recording)
    _play_annual(world)

    response = _post_play(world)

    assert response.status_code == 201, response.text
    run = captured_run[-1]
    assert run.writes[0][1]["kind"] == "monthly_play"
    assert run.stages == ["prepare", "generate", "check", "save"]
    final = run.final
    assert (final["status"], final["plan_id"]) == ("SUCCEEDED", response.json()["id"])
    assert recording.versions
    assert final["prompt_versions"] == list(dict.fromkeys(recording.versions))


def test_놀이_월간은_판_기록을_가명_처리_안쪽에_둔다(world, monkeypatch):
    monkeypatch.setattr(monthly_llm, "play_monthly_provider", PlayRecording)
    _play_annual(world)
    seen = spy_masked_memo(monkeypatch, play_monthly_router)

    assert _post_play(world).status_code == 201

    assert len(seen) == 1 and isinstance(seen[0], PromptNoted)


def test_기록이_깨져도_놀이_월간_생성은_같다(world, broken_run, warnings, monkeypatch):
    _play_annual(world)
    warnings.clear()

    created = _post_play(world)

    assert created.status_code == 201, created.text
    assert client.get(f"{PLAY_URL}/{created.json()['id']}").json() == created.json()
    failures = run_lines(warnings)
    assert len(failures) == 1 and " step=begin type=RuntimeError" in failures[0]


@pytest.mark.parametrize("route", ["weekly", "play"])
def test_다른_원_반이면_기록_전에_404_이고_줄을_만들지_않는다(world, captured_run, route):
    """기록은 반 확인을 지난 요청만 남긴다."""
    other = world["other"]["class"]
    before = len(captured_run)
    if route == "weekly":
        response = client.post("/api/plans/weekly", json={"class_id": other, "week_id": WEEK})
    else:
        response = client.post(PLAY_URL, json={"class_id": other, "month": 10})

    assert response.status_code == 404
    assert len(captured_run) == before + 1 and captured_run[-1].writes == []
