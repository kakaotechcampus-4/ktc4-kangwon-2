"""생성 기록 — 연간 주제형 · 놀이 연간(ADR-096). 단계 순서 · 끝 줄 · 실패 · 기록이 깨져도 같은 생성.

`db_session` 위에서 받아 적는 기록기(`Captured`)로 본다. 진짜 쓰기는 `test_generation_runs.py`.
"""

# ruff: noqa: F811 — 다른 테스트 파일의 픽스처를 가져와 쓰면 인자 이름이 import 와 겹친다

import io
import json

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select
from test_generation_runs import (  # noqa: F401
    Broken,
    Captured,
    assert_forward,
    broken_run,
    captured_run,
    run_lines,
    spy_masked_memo,
    warnings,
)
from test_plans_api import mine  # noqa: F401
from test_play_project_llm_cap import Scripted, server  # noqa: F401 — server 는 autouse

from app.config import settings
from app.features.centers.models import Child
from app.features.plans import generation_runs, play_project
from app.features.plans import router as plans_router
from app.features.plans.annual_content import (
    ANNUAL_SUBTHEMES_PROMPT_VERSION,
    ANNUAL_SUBTHEMES_REPAIR_PROMPT_VERSION,
)
from app.features.plans.generation_runs import PromptNoted, generation_run
from app.features.plans.llm import ANNUAL_THEME_PROMPT_VERSION
from app.features.plans.models import Plan
from app.main import app
from app.shared.llm import MODEL
from app.shared.llm import client as llm

client = TestClient(app)
THEME = "MONTHLY_THEME"
PLAY = "PLAY_PROJECT"


def _post(klass, format=THEME, **body):
    return client.post("/api/plans/annual", json={"format": format, "class_id": klass.id, **body})


class Recording:
    """목업 그대로 답하고 받은 요청의 판을 적는다."""

    def __init__(self):
        self.versions = []

    def generate_play_project(self, request):
        self.versions.append(request.prompt_version)
        return play_project.MockPlayProjectProvider().generate_play_project(request)


# ── 단계 · 끝 줄 ──────────────────────────────────────────────────────────


def test_연간_주제형은_주제_소주제_저장_순서로_가고_끝_줄에_숫자와_이름만_남는다(
    mine, captured_run
):
    response = _post(mine)

    assert response.status_code == 201, response.text
    run = captured_run[-1]
    # 소주제 전에 save 가 오면 링이 소주제 LLM 을 기다리는 내내 「저장」에 머문다(router.py).
    assert run.stages == ["generate", "subthemes", "save"]
    first = run.writes[0]
    assert first[0] is True
    assert first[1] == {
        "kind": "annual_theme",
        "center_id": mine.center_id,
        "class_id": mine.id,
        "status": "RUNNING",
        "stage": "generate",
        "mode": "mock",
    }
    final = run.final
    assert (final["status"], final["error_code"], final["plan_id"]) == (
        "SUCCEEDED",
        None,
        response.json()["id"],
    )
    assert (final["model"], final["llm_calls"]) == (None, 0)
    assert {"db_read", "subthemes", "save"} <= set(final["phase_ms"])
    assert all(isinstance(ms, int) for ms in final["phase_ms"].values())
    assert final["prompt_versions"] == [
        ANNUAL_SUBTHEMES_PROMPT_VERSION
    ]  # 결정적 주제 생성기는 요청이 없다
    assert "햇살반" not in str(run.writes)


def test_놀이_연간은_놀이_떠올리기_겹침_살펴보기_저장_순서로_간다(mine, captured_run, monkeypatch):
    recording = Recording()
    monkeypatch.setattr(play_project, "provider", lambda: recording)

    response = _post(mine, PLAY)

    assert response.status_code == 201, response.text
    run = captured_run[-1]
    assert run.stages == ["generate", "check", "save"]
    assert run.writes[0][1]["kind"] == "annual_play"  # 분기 전에 set_kind 를 마쳤다
    final = run.final
    assert (final["status"], final["plan_id"]) == ("SUCCEEDED", response.json()["id"])
    assert "overlap" in final["phase_ms"]
    assert recording.versions and set(final["prompt_versions"]) == set(recording.versions)
    assert final["llm_calls"] == 0  # mock 은 전송을 지나지 않는다


@pytest.mark.parametrize("format", [THEME, PLAY])
def test_단계는_종류별_순서에서_앞으로만_간다(mine, captured_run, format):
    assert _post(mine, format).status_code == 201

    kind = "annual_theme" if format == THEME else "annual_play"
    assert_forward(kind, captured_run[-1].stages)


def test_real_모드_놀이_연간은_호출_수와_모델과_판을_남긴다(mine, captured_run, monkeypatch):
    """`Scripted` 가 답마다 실제 `post_stream` 을 한 번 지나게 해 span · 호출 수를 진짜로 남긴다."""
    monkeypatch.setattr(settings, "llm_mode", "real")
    scripted = Scripted(monkeypatch, overlap=True)  # 겹친 후보를 다시 만든다

    response = _post(mine, PLAY)

    assert response.status_code == 201, response.text
    run = captured_run[-1]
    assert run.stages == ["generate", "check", "save"]
    assert run.writes[0][1]["mode"] == "real"
    final = run.final
    assert final["status"] == "SUCCEEDED"
    assert final["llm_calls"] == len(scripted.attempts) >= 4
    assert final["model"] == MODEL
    versions = {request.prompt_version for request in scripted.requests}
    assert set(final["prompt_versions"]) == versions
    assert all(v.startswith("play-project") for v in versions)


def test_real_모드_연간_주제형은_주제_소주제_수리_판을_보낸_순서로_남긴다(
    mine, captured_run, monkeypatch
):
    """`urlopen` 만 가짜다 — 세 요청이 진짜 전송을 지난다. 첫 소주제 답은 개수가 틀려 수리한다."""
    sent = []

    def urlopen(request, timeout):
        body = json.loads(json.loads(request.data)["messages"][1]["content"])
        version = body["prompt_version"]
        sent.append(version)
        if version == ANNUAL_THEME_PROMPT_VERSION:
            answer = {
                "themes": [
                    {"theme_id": m["theme_id"], "value": m["reference_label"]}
                    for m in body["months"]
                ]
            }
        else:
            count = 1 if version == ANNUAL_SUBTHEMES_PROMPT_VERSION else None
            answer = {
                "months": [
                    {
                        "month": m["month"],
                        "sub_themes": [
                            f"{m['theme']} 소주제 {i}"
                            for i in range(1, (count or m["week_count"]) + 1)
                        ],
                    }
                    for m in body["months"]
                ]
            }
        content = json.dumps(answer, ensure_ascii=False)
        return io.BytesIO(json.dumps({"choices": [{"message": {"content": content}}]}).encode())

    monkeypatch.setattr(llm.urllib_request, "urlopen", urlopen)
    monkeypatch.setattr(settings, "llm_mode", "real")
    monkeypatch.setattr(settings, "elice_mlapi_base_url", "https://llm.invalid/v1")
    monkeypatch.setattr(settings, "elice_mlapi_api_key", "test-only-not-a-key")

    response = _post(mine)

    assert response.status_code == 201, response.text
    run = captured_run[-1]
    assert run.stages == ["generate", "subthemes", "save"]
    versions = [
        ANNUAL_THEME_PROMPT_VERSION,
        ANNUAL_SUBTHEMES_PROMPT_VERSION,
        ANNUAL_SUBTHEMES_REPAIR_PROMPT_VERSION,
    ]
    assert sent == versions
    final = run.final
    assert final["prompt_versions"] == versions
    assert (final["status"], final["llm_calls"], final["model"]) == ("SUCCEEDED", 3, MODEL)


def test_놀이_연간은_판_기록을_가명_처리_안쪽에_둔다(mine, monkeypatch):
    monkeypatch.setattr(play_project, "provider", Recording)
    seen = spy_masked_memo(monkeypatch, play_project)

    assert _post(mine, PLAY).status_code == 201

    assert len(seen) == 1 and isinstance(seen[0], PromptNoted)


# ── 실패 · 멈춤 ───────────────────────────────────────────────────────────


def test_같은_반_연간을_두_번_만들면_둘째는_ALREADY_EXISTS_로_기록된다(mine, captured_run):
    assert _post(mine).status_code == 201

    second = _post(mine)

    assert second.status_code == 409
    final = captured_run[-1].final  # 반 확인을 지났으니 기록된다
    assert (final["status"], final["error_code"], final["plan_id"]) == (
        "FAILED",
        "ALREADY_EXISTS",
        None,
    )
    assert captured_run[-1].stages == ["generate"]  # 실패한 단계가 그대로 남는다


def test_메모의_아이_이름을_못_가리면_실제_오류_코드로_기록된다(mine, db_session, captured_run):
    db_session.add_all(
        [
            Child(class_id=mine.id, name="김하나", code="도아"),
            Child(class_id=mine.id, name="박하나", code="새미"),
        ]
    )
    db_session.flush()

    response = _post(mine, memo="하나가 좋아하는 공 놀이")

    assert response.status_code == 422
    final = captured_run[-1].final
    assert (final["status"], final["error_code"]) == ("FAILED", "VALUE_INVALID")
    assert "하나" not in str(captured_run[-1].writes)


@pytest.mark.parametrize(
    ("error", "status_code"),
    [
        (HTTPException(418, detail="문자열 detail"), 418),  # 코드가 없다 → INTERNAL_ERROR
        (RuntimeError("예상 밖"), 500),
    ],
)
def test_코드가_없는_오류는_INTERNAL_ERROR_로_기록된다(
    mine, captured_run, monkeypatch, error, status_code
):
    def raises():
        raise error

    monkeypatch.setattr(plans_router, "theme_text_generator", raises)

    response = _post(mine)

    assert response.status_code == status_code
    final = captured_run[-1].final
    assert (final["status"], final["error_code"]) == ("FAILED", "INTERNAL_ERROR")


def test_놀이_연간을_멈추면_STOPPED_로_기록된다(mine, db_session, captured_run, monkeypatch):
    monkeypatch.setattr(plans_router, "_disconnected", lambda request: lambda: True)

    response = _post(mine, PLAY)

    assert response.status_code == 499
    final = captured_run[-1].final
    assert (final["status"], final["error_code"], final["plan_id"]) == (
        "STOPPED",
        "GENERATION_STOPPED",
        None,
    )
    # 이 테스트의 반 것만 본다 — 공유 DB 에 다른 연간이 있어도 된다
    stored = select(Plan.id).where(Plan.kind == "annual", Plan.classroom_ref == str(mine.id))
    assert db_session.scalar(stored) is None


# ── 기록이 깨져도 생성은 같다 ──────────────────────────────────────────────


@pytest.mark.parametrize("format", [THEME, PLAY])
def test_기록이_깨져도_생성_응답은_같고_경고는_한_번_문장은_안_찍는다(
    mine, broken_run, warnings, format
):
    created = _post(mine, format)

    assert created.status_code == 201, created.text
    assert client.get(f"/api/plans/annual/{created.json()['id']}").json() == created.json()
    failures = run_lines(warnings)
    assert len(failures) == 1  # 한 요청에서 실패는 한 번만 난다
    assert " step=begin type=RuntimeError" in failures[0]
    assert Broken.SECRET not in "".join(warnings)  # str(exc) 를 찍지 않는다


def test_실패하는_생성에_기록_실패가_겹쳐도_원래_409_봉투가_그대로다(mine, broken_run):
    assert _post(mine).status_code == 201

    second = _post(mine)

    assert second.status_code == 409
    assert second.json()["error"] == {
        "code": "ALREADY_EXISTS",
        "message": "이 반의 연간계획안이 이미 있습니다.",
        "fields": ["class_id"],
    }


def test_단계_표에_없는_종류여도_생성은_201_이다(mine, captured_run, warnings, monkeypatch):
    monkeypatch.delitem(generation_runs.STAGES, "annual_theme")

    response = _post(mine)

    assert response.status_code == 201, response.text
    assert captured_run[-1].writes == []  # 기록 없이 만들었다
    assert " step=begin type=KeyError" in run_lines(warnings)[0]


def test_첫_줄_뒤의_쓰기가_깨져도_생성은_201_이고_경고는_한_번이다(mine, warnings, db_session):
    class FailsAfterBegin(Captured):
        def _save(self, values, *, first=False):
            if not first:
                raise RuntimeError(Broken.SECRET)
            super()._save(values, first=first)

    runs = []

    def make():
        runs.append(FailsAfterBegin())
        return runs[-1]

    app.dependency_overrides[generation_run] = make

    response = _post(mine)

    assert response.status_code == 201, response.text
    assert len(runs[-1].writes) == 1  # 단계 전진에서 처음 실패하고 그 뒤로는 쓰지 않는다 (끝 줄도)
    failures = run_lines(warnings)
    assert len(failures) == 1 and " step=phase " in failures[0]
    assert Broken.SECRET not in "".join(warnings)
    assert db_session.scalar(select(Plan.id).where(Plan.classroom_ref == str(mine.id))) is not None


def test_끝_줄_쓰기만_깨져도_생성은_201_이고_경고는_end_한_번이다(mine, warnings):
    """끝 줄은 commit 뒤에 쓴다. 여기서 던지면 저장된 계획안에 500 이 나가 교사가 다시 누른다."""

    class FailsAtEnd(Captured):
        def _save(self, values, *, first=False):
            if values.get("status", "RUNNING") != "RUNNING":
                raise RuntimeError(Broken.SECRET)
            super()._save(values, first=first)

    app.dependency_overrides[generation_run] = FailsAtEnd

    created = _post(mine)

    assert created.status_code == 201, created.text
    assert client.get(f"/api/plans/annual/{created.json()['id']}").json() == created.json()
    failures = run_lines(warnings)
    assert len(failures) == 1 and " step=end type=RuntimeError" in failures[0]
    assert Broken.SECRET not in "".join(warnings)
