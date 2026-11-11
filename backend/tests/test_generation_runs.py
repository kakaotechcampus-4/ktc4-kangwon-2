"""생성 기록(ADR-096) — 헤더 검사 · 진짜 쓰기 · 조회 · 권한.

`db_session` 은 바깥 transaction 안에서 도는데 기록은 따로 연결해 쓴다. 그래서 거기서는
기록기를 끄고(conftest `_Unrecorded`) 단계 규칙은 받아 적는 기록기(`Captured`)로 본다.
진짜 쓰기는 이 파일이 진짜 commit 한 원 · 반 위에서 새 연결로 읽어 본다.
다섯 종류의 단계는 세계마다 나눈 `test_generation_runs_{annual,monthly,weekly}.py` 가 본다.
"""

import logging
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from time import monotonic
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select, text
from sqlalchemy.orm import Session
from ssuksak import timing
from ssuksak.planning.planner.contracts import RawLlmResponse

from app import main
from app.db import engine
from app.features.auth.models import User
from app.features.centers.models import Center, Class, ClassAccessRequest
from app.features.plans import generation_runs
from app.features.plans.annual_content import ANNUAL_SUBTHEMES_PROMPT_VERSION
from app.features.plans.generation_runs import (
    RUN_HEADER,
    PromptNoted,
    RunRecorder,
    generation_run,
)
from app.features.plans.memo_privacy import MemoMaskFailed, with_masked_memo
from app.features.plans.models import GenerationRun, Plan
from app.main import app
from app.shared.childCode import NameTable

client = TestClient(app)


class Captured(RunRecorder):
    """`_save` 만 바꿔 쓰지 않고 `(first, values)` 를 적는다. 나머지는 진짜다."""

    def __init__(self, run_id=None):
        super().__init__(run_id)
        self.writes = []

    def _save(self, values, *, first=False):
        self.writes.append((first, values))

    @property
    def stages(self):
        return [values["stage"] for _, values in self.writes if "stage" in values]

    @property
    def final(self):
        """끝 줄 — 상태가 RUNNING 이 아닌 쓰기. 없으면 None."""
        done = [values for _, values in self.writes if values.get("status", "RUNNING") != "RUNNING"]
        return done[-1] if done else None


class Broken(RunRecorder):
    """쓰기가 늘 예외를 낸다. 예외 문장에 값이 들어 있어도 로그에 나가면 안 된다."""

    SECRET = "SECRET-DETAIL-7"

    def _save(self, values, *, first=False):
        raise RuntimeError(self.SECRET)


@pytest.fixture
def captured_run(db_session):
    """요청마다 받아 적는 기록기를 하나씩 만든다. 목록은 요청 순서다."""
    runs = []

    def make():
        runs.append(Captured())
        return runs[-1]

    app.dependency_overrides[generation_run] = make
    return runs


@pytest.fixture
def broken_run(db_session):
    app.dependency_overrides[generation_run] = Broken
    return Broken


@pytest.fixture
def warnings(monkeypatch):
    """`app.server` 로거는 conftest 의 alembic fileConfig 로 꺼져 있다 — 켜고 줄을 모은다."""
    monkeypatch.setattr(main.logger, "disabled", False)
    lines = []
    handler = logging.Handler()
    handler.emit = lambda record: lines.append(record.getMessage())
    main.logger.addHandler(handler)
    try:
        yield lines
    finally:
        main.logger.removeHandler(handler)


def run_lines(lines):
    return [line for line in lines if line.startswith("generation_run")]


def assert_forward(kind, seen):
    """받은 단계가 그 종류의 단계 순서에서 앞으로만 가고 첫 단계에서 save 로 끝난다."""
    order = generation_runs.STAGES[kind]
    assert seen[0] == order[0] and seen[-1] == "save", seen
    assert [order.index(stage) for stage in seen] == sorted({order.index(s) for s in seen}), seen


_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_PERIOD_KEY = re.compile(r"m\d\d_m\d\d")
_ATTEMPT_FIELDS = {"kind", "phase", "period", "attempt", "result"}


def assert_attempts_shape(attempts):
    """`attempts` 의 각 줄은 정해진 칸만 갖고 값은 식별자 · 구간 키 · 정수다. 메시지가 못 든다.

    영문 식별자만 받으므로 한글 오류 문장 · 반 이름 · 요청 사항이 섞이면 여기서 걸린다.
    """
    for line in attempts:
        assert {"kind", "phase", "result"} <= set(line) <= _ATTEMPT_FIELDS, line
        assert line["kind"] in ("period", "transport", "repair"), line
        assert all(_NAME.fullmatch(line[key]) for key in ("kind", "phase", "result")), line
        assert ("period" in line) == ("attempt" in line) == (line["kind"] == "period"), line
        if "period" in line:
            assert _PERIOD_KEY.fullmatch(line["period"]), line
            assert type(line["attempt"]) is int and line["attempt"] in (1, 2), line


def spy_masked_memo(monkeypatch, module):
    """`module` 이 `with_masked_memo` 에 넘긴 provider 를 모은다. 동작은 진짜 그대로다.

    첫 인자가 `PromptNoted` 여야 판 기록이 가명 처리 **안쪽**이다 — 바깥이면 가명 치환에 막혀
    부르지 않은 요청의 판도 남는다.
    """
    seen = []

    def spy(provider, *args, **kwargs):
        seen.append(provider)
        return with_masked_memo(provider, *args, **kwargs)

    monkeypatch.setattr(module, "with_masked_memo", spy)
    return seen


# ── 헤더 422 ──────────────────────────────────────────────────────────────

ROUTES = {
    "annual": ("/api/plans/annual", {"format": "MONTHLY_THEME", "class_id": 1}),
    "monthly": (
        "/api/plans/monthly",
        {"class_id": 1, "month": 9, "profile_ref": {"profile_id": "p", "profile_version": "v"}},
    ),
    "monthly_play": ("/api/plans/monthly/play", {"class_id": 1, "month": 9}),
    "weekly": ("/api/plans/weekly", {"class_id": 1, "week_id": "2026-09-W2"}),
}


@pytest.mark.parametrize("route", ROUTES)
@pytest.mark.parametrize("value", ["abc", str(uuid.uuid1()), ""])
def test_헤더가_uuid_v4_가_아니면_생성_없이_422(teacher, route, value):
    """`db_session` · 받아 적는 기록기를 쓰지 않는다 — override 가 걸리면 헤더 검사가 사라진다."""
    path, body = ROUTES[route]

    response = client.post(path, json=body, headers={RUN_HEADER: value})

    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "VALIDATION_FAILED"
    assert response.json()["error"]["fields"] == [RUN_HEADER]


def test_v1_uuid_로_거절한_요청은_기록도_생성도_없다(_schema, teacher):
    rid = uuid.uuid1()
    path, body = ROUTES["annual"]

    assert client.post(path, json=body, headers={RUN_HEADER: str(rid)}).status_code == 422

    with Session(engine) as session:
        assert session.scalar(select(func.count()).where(GenerationRun.id == rid)) == 0


# ── PromptNoted ───────────────────────────────────────────────────────────


@dataclass(frozen=True)
class _Request:
    user_content: str
    prompt_version: str | None = None
    system_prompt: str = ""


def test_provider_를_지날_때마다_요청의_프롬프트_판을_적고_수리_판도_남는다():
    class Provider:
        label = "그대로"

        def generate_weekly(self, request):
            return request.prompt_version

    @timing.timed("weekly", lambda line: None)
    def handler():
        provider = PromptNoted(Provider())
        answers = [
            provider.generate_weekly(_Request("{}", "weekly-v1")),
            provider.generate_weekly(_Request("{}", "weekly-repair-v1")),
            provider.generate_weekly(_Request("{}", "weekly-v1")),
            provider.generate_weekly(_Request("{}")),  # 판이 없는 요청은 적지 않는다
        ]
        assert provider.label == "그대로"
        return answers, timing.current().prompts

    answers, prompts = handler()
    assert answers == ["weekly-v1", "weekly-repair-v1", "weekly-v1", None]  # 답은 그대로 돌아온다
    assert prompts == ["weekly-v1", "weekly-repair-v1"]


def test_수리_구간에서_부른_호출만_수리_시도로_적고_답과_예외는_그대로다():
    class Boom(Exception):
        pass

    boom = Boom("메시지는 적지 않는다")

    class Provider:
        def __init__(self, error=None):
            self.error = error

        def generate_weekly(self, request):
            if self.error:
                raise self.error
            return "답"

    assert PromptNoted(Provider()).generate_weekly(_Request("{}")) == "답"  # 실행 밖은 그냥 부른다

    @timing.timed("weekly", lambda line: None)
    def handler():
        provider = PromptNoted(Provider())
        timing.phase("prompt")
        first = provider.generate_weekly(_Request("{}", "weekly-v1"))  # 첫 호출은 수리가 아니다
        timing.phase("repair")
        repaired = provider.generate_weekly(_Request("{}", "weekly-repair-v1"))
        with pytest.raises(Boom) as raised:
            PromptNoted(Provider(boom)).generate_weekly(_Request("{}", "weekly-repair-v1"))
        assert raised.value is boom
        return (first, repaired), timing.current().attempts

    answers, attempts = handler()
    assert answers == ("답", "답")
    assert attempts == [
        {"kind": "repair", "phase": "repair", "result": "ok"},
        {"kind": "repair", "phase": "repair", "result": "Boom"},
    ]
    assert_attempts_shape(attempts)


def test_가명_치환을_못_지난_요청의_판은_남지_않는다():
    """`PromptNoted` 는 `with_masked_memo` 안쪽이라 실제로 부른 요청만 적는다."""
    table = NameTable({"이가명": "도담"})
    memo = "가명이가 좋아하는 하나씩 쌓기"
    payload = '{"teacher_memo": {"text": "' + memo + '"}}'

    class Inner:
        def generate_weekly(self, request):
            return RawLlmResponse(content="{}", model="m")

    @timing.timed("weekly", lambda line: None)
    def handler():
        provider = with_masked_memo(PromptNoted(Inner()), memo, table)
        provider.generate_weekly(_Request(payload, "sent-v1"))
        with pytest.raises(MemoMaskFailed):
            provider.generate_weekly(_Request(payload + " 이가명", "masked-v1"))
        return timing.current().prompts

    assert handler() == ["sent-v1"]


# ── 진짜 쓰기 — 진짜 commit 한 원 · 반 위에서 새 연결로 읽는다 ─────────────────


def _user(session, center_id, email):
    user = User(
        email=email, name="선생", password_hash=b"x" * 64, password_salt=b"y" * 16,
        center_id=center_id,
    )  # fmt: skip
    session.add(user)
    session.flush()
    return user


@pytest.fixture
def committed(_schema, teacher):
    """진짜 commit 한 원 둘 · 계정 셋 · 반 하나(담임 owner). `teacher` 가 그 계정으로 바뀐다.

    `owner` 가 담임, `colleague` 는 같은 원 다른 교사, `outsider` 는 다른 원 교사다.
    """
    with Session(engine) as session:
        center = Center(
            name="생성 기록 시험원", director_name="김원장", region_sido="강원특별자치도",
            region_sigungu="춘천시",
        )  # fmt: skip
        other = Center(
            name="생성 기록 옆원", director_name="김원장", region_sido="강원특별자치도",
            region_sigungu="춘천시",
        )  # fmt: skip
        session.add_all([center, other])
        session.flush()
        owner = _user(session, center.id, "gen-runs-owner@example.com")
        colleague = _user(session, center.id, "gen-runs-colleague@example.com")
        outsider = _user(session, other.id, "gen-runs-outsider@example.com")
        klass = Class(
            center_id=center.id, name="기록반", school_year=2026, age_min=3, age_max=3,
            teacher_name="선생", teacher_id=owner.id,
        )  # fmt: skip
        session.add(klass)
        session.commit()
        world = SimpleNamespace(
            center=center.id,
            other=other.id,
            klass=klass.id,
            owner=(owner.id, center.id),
            colleague=(colleague.id, center.id),
            outsider=(outsider.id, other.id),
        )

    def act_as(who):
        teacher.id, teacher.center_id = who

    world.act_as = act_as
    act_as(world.owner)
    try:
        yield world
    finally:
        centers = [world.center, world.other]
        with Session(engine) as session:
            session.execute(delete(GenerationRun).where(GenerationRun.center_id.in_(centers)))
            session.execute(delete(Plan).where(Plan.center_id.in_(centers)))
            session.execute(
                delete(ClassAccessRequest).where(ClassAccessRequest.class_id == world.klass)
            )
            session.execute(delete(Class).where(Class.center_id.in_(centers)))
            session.execute(delete(User).where(User.center_id.in_(centers)))
            session.execute(delete(Center).where(Center.id.in_(centers)))
            session.commit()


def _post_annual(world, rid=None):
    headers = {RUN_HEADER: str(rid)} if rid else {}
    return client.post(
        "/api/plans/annual",
        json={"format": "MONTHLY_THEME", "class_id": world.klass},
        headers=headers,
    )


def _rows(**where):
    with Session(engine) as session:
        query = select(GenerationRun)
        for name, value in where.items():
            query = query.where(getattr(GenerationRun, name) == value)
        return list(session.scalars(query))


def test_헤더를_붙인_생성은_새_연결로_읽어도_한_줄이고_조회가_끝난_모양을_준다(committed):
    rid = uuid.uuid4()

    created = _post_annual(committed, rid)

    assert created.status_code == 201, created.text
    rows = _rows(id=rid)
    assert len(rows) == 1  # 기록을 삼켜 0건인데 초록이 되는 것을 막는다
    row = rows[0]
    assert (row.status, row.stage, row.plan_id) == ("SUCCEEDED", "save", created.json()["id"])
    assert (row.kind, row.mode, row.model, row.llm_calls) == ("annual_theme", "mock", None, 0)
    assert (row.center_id, row.class_id) == (committed.center, committed.klass)
    assert row.prompt_versions == [ANNUAL_SUBTHEMES_PROMPT_VERSION]  # mock 은 소주제 판 하나
    assert row.attempts is None  # 다시 한 일이 없으면 비어 있다
    assert {"db_read", "save"} <= set(row.phase_ms)
    assert row.finished_at > row.started_at

    got = client.get(f"/api/generation-runs/{rid}")

    assert got.status_code == 200, got.text
    body = got.json()
    assert (body["id"], body["status"], body["stage"]) == (str(rid), "SUCCEEDED", "save")
    assert (body["plan_id"], body["class_id"], body["error_code"]) == (
        created.json()["id"],
        committed.klass,
        None,
    )
    assert "center_id" not in body
    assert body["attempts"] is None
    # 기록에 반 이름 · 요청 사항 · 아이 이름이 들어갈 길이 없다 — 숫자와 이름만이다.
    assert "기록반" not in got.text


def test_헤더_없이_만들어도_줄이_하나_는다(committed):
    first = _post_annual(committed)
    second = _post_annual(committed)  # 반 하나에 연간 하나 — 둘째는 409 지만 반 확인을 지났다

    assert (first.status_code, second.status_code) == (201, 409)
    rows = sorted(_rows(class_id=committed.klass), key=lambda row: row.started_at)
    assert [(row.status, row.error_code) for row in rows] == [
        ("SUCCEEDED", None),
        ("FAILED", "ALREADY_EXISTS"),
    ]
    assert rows[1].plan_id is None and rows[1].stage == "generate"


def test_판이_없는_끝난_줄의_prompt_versions_는_jsonb_null_이_아니라_SQL_NULL_이다(committed):
    _post_annual(committed)
    rid = uuid.uuid4()
    assert _post_annual(committed, rid).status_code == 409  # LLM 을 부르기 전에 끝난다

    # ORM 은 둘 다 None 으로 읽어 못 잡는다 — 날 SQL 로 본다.
    with Session(engine) as session:
        is_null, kind = session.execute(
            text(
                "SELECT prompt_versions IS NULL, jsonb_typeof(prompt_versions) "
                "FROM generation_runs WHERE id = :id"
            ),
            {"id": rid},
        ).one()
    assert (is_null, kind) == (True, None)


def test_시도가_없는_끝난_줄의_attempts_는_jsonb_null_이_아니라_SQL_NULL_이다(committed):
    rid = uuid.uuid4()
    _post_annual(committed)
    assert _post_annual(committed, rid).status_code == 409  # LLM 을 부르기 전에 끝나 시도가 없다

    # 위 테스트와 같은 이유 — ORM 은 둘 다 None 으로 읽는다.
    with Session(engine) as session:
        is_null, kind = session.execute(
            text(
                "SELECT attempts IS NULL, jsonb_typeof(attempts) "
                "FROM generation_runs WHERE id = :id"
            ),
            {"id": rid},
        ).one()
    assert (is_null, kind) == (True, None)


def test_계획안을_지워도_기록은_남고_plan_id_만_비는다(committed):
    rid = uuid.uuid4()
    plan_id = _post_annual(committed, rid).json()["id"]
    assert _rows(id=rid)[0].plan_id == plan_id

    assert client.delete(f"/api/plans/annual/{plan_id}").status_code == 204

    row = _rows(id=rid)[0]
    assert (row.status, row.plan_id) == ("SUCCEEDED", None)
    assert client.get(f"/api/generation-runs/{rid}").json()["plan_id"] is None


def test_같은_uuid_가_다시_오면_덮지_않고_그_요청은_기록하지_않는다(committed, warnings):
    rid = uuid.uuid4()
    plan_id = _post_annual(committed, rid).json()["id"]
    client.delete(f"/api/plans/annual/{plan_id}")
    before = _rows(id=rid)[0]

    again = _post_annual(committed, rid)

    assert again.status_code == 201, again.text  # 생성은 지금처럼 돈다
    after = _rows(id=rid)
    assert len(after) == 1  # upsert 가 없다
    assert (after[0].plan_id, after[0].finished_at, after[0].started_at) == (
        None,
        before.finished_at,
        before.started_at,
    )
    assert run_lines(warnings) == [f"generation_run duplicate run={rid}"]


def test_권한은_원_반_승인_순서로_본다(committed):
    rid = uuid.uuid4()
    _post_annual(committed, rid)
    one, many = f"/api/generation-runs/{rid}", f"/api/generation-runs?class_id={committed.klass}"

    committed.act_as(committed.outsider)  # 다른 원 — 있는지도 알리지 않는다
    gone = client.get(one)
    assert gone.status_code == 404
    assert gone.json()["error"] == {
        "code": "NOT_FOUND",
        "message": "생성 기록을 찾을 수 없습니다.",
        "fields": ["run_id"],
    }
    listed = client.get(many)
    assert (listed.status_code, listed.json()["error"]["fields"]) == (404, ["class_id"])
    assert client.get(f"/api/generation-runs/{uuid.uuid4()}").status_code == 404  # 없는 id 도 같다

    committed.act_as(committed.colleague)  # 같은 원 남의 반 — 승인이 있어야 본다
    for url in (one, many):
        denied = client.get(url)
        assert (denied.status_code, denied.json()["error"]["code"]) == (
            403,
            "CLASS_ACCESS_REQUIRED",
        )

    with Session(engine) as session:
        session.add(
            ClassAccessRequest(
                class_id=committed.klass, requester_id=committed.colleague[0], status="APPROVED"
            )
        )
        session.commit()
    assert client.get(one).status_code == 200
    assert [item["id"] for item in client.get(many).json()["items"]] == [str(rid)]

    committed.act_as(committed.owner)
    missing = client.get("/api/generation-runs")
    assert (missing.status_code, missing.json()["error"]["fields"]) == (422, ["class_id"])
    bad = client.get("/api/generation-runs/abc")
    assert (bad.status_code, bad.json()["error"]["fields"]) == (422, ["run_id"])


def test_목록은_최근_것부터_최대_50개다(committed):
    now = datetime.now(UTC)
    with Session(engine) as session:
        session.add_all(
            GenerationRun(
                id=uuid.uuid4(),
                kind="weekly",
                center_id=committed.center,
                class_id=committed.klass,
                status="FAILED",
                stage="prepare",
                error_code="GENERATION_FAILED",
                mode="mock",
                started_at=now - timedelta(minutes=n),
                finished_at=now - timedelta(minutes=n),
            )  # fmt: skip
            for n in range(55)
        )
        session.commit()

    items = client.get(f"/api/generation-runs?class_id={committed.klass}").json()["items"]

    assert len(items) == 50
    assert [item["started_at"] for item in items] == sorted(
        (item["started_at"] for item in items), reverse=True
    )


def test_RUNNING_이_15분을_넘으면_읽을_때_UNKNOWN_이다(committed):
    now = datetime.now(UTC)
    old, fresh = uuid.uuid4(), uuid.uuid4()
    with Session(engine) as session:
        session.add_all(
            GenerationRun(
                id=rid,
                kind="weekly",
                center_id=committed.center,
                class_id=committed.klass,
                status="RUNNING",
                stage="prepare",
                mode="mock",
                started_at=now - ago,
            )  # fmt: skip
            for rid, ago in ((old, timedelta(minutes=16)), (fresh, timedelta(minutes=14)))
        )
        session.commit()

    assert client.get(f"/api/generation-runs/{old}").json()["status"] == "UNKNOWN"
    assert client.get(f"/api/generation-runs/{fresh}").json()["status"] == "RUNNING"
    assert _rows(id=old)[0].status == "RUNNING"  # 저장하지는 않는다


def test_기록_표가_잠겨_있어도_생성은_수_초_안에_끝나고_줄만_없다(committed, warnings):
    rid = uuid.uuid4()
    with engine.connect() as locker:
        locker.execute(text("LOCK TABLE generation_runs IN ACCESS EXCLUSIVE MODE"))
        try:
            started = monotonic()
            created = _post_annual(committed, rid)
            elapsed = monotonic() - started
        finally:
            locker.rollback()

    assert created.status_code == 201, created.text
    assert elapsed < 10
    assert _rows(id=rid) == []
    failures = run_lines(warnings)
    assert len(failures) == 1  # 한 요청에서 실패는 한 번만 난다
    assert failures[0].startswith(f"generation_run failed run={rid} step=begin type=")
