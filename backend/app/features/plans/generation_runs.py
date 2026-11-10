"""생성 요청 한 번의 기록(Generation Run) — 단계 · 결과 · 숫자 · 이름만 (ADR-096).

**작업 큐가 아니다.** 생성은 지금처럼 요청 스레드가 한 번에 하고, 계획안은 마지막에 한 번만
저장한다. 이 표는 그 요청이 어디까지 갔는지와 어떻게 끝났는지를 적을 뿐, 이어 만들기에 쓰지 않는다.
**기록이 죽어도 생성은 돈다**(CLAUDE.md 「부가 기능」) — 따로 연결 · 짧은 시간 제한 ·
한 번 실패하면 그 요청은 끈다.
트렌드 상태는 여기 두지 않는다 — 서버 로그 한 줄로 갈음한다(CLAUDE.md 「계획안의 트렌드」).
"""

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import UUID4, BaseModel
from sqlalchemy import create_engine, func, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, sessionmaker
from ssuksak import timing

from app.config import settings
from app.db import get_session
from app.features.plans.models import GenerationRun
from app.shared.auth.dependency import CurrentUser
from app.shared.auth.ownership import require_own_class
from app.shared.llm import MODEL

_log = logging.getLogger("app.server")

RUN_HEADER = "X-Generation-Run-Id"
STAGES = {  # kind → 단계 순서. 화면 글자가 이 순서에 1:1 로 붙는다
    "annual_theme": ("generate", "subthemes", "save"),
    "annual_play": ("generate", "check", "save"),
    "monthly_theme": ("prepare", "generate", "check", "save"),
    "monthly_play": ("prepare", "generate", "check", "save"),
    "weekly": ("prepare", "generate", "check", "save"),
}
_PLAN = {
    "prompt": "generate",
    "llm": "generate",
    "validate": "check",
    "repair": "check",
    "assemble": "save",
    "save": "save",
}
OPENS = {  # timing 구간 → 그 구간이 여는 단계. 없는 구간은 단계를 바꾸지 않는다
    "annual_theme": {"subthemes": "subthemes", "save": "save"},
    "annual_play": {"overlap": "check", "save": "save"},
    "monthly_theme": _PLAN,
    "monthly_play": _PLAN,
    "weekly": _PLAN,
}
# 근거: ADR-096 — 서버 쪽 최장 약 6분(놀이 연간) · nginx 최장 510초보다 넉넉히
STALE_AFTER = timedelta(minutes=15)

# 기록 전용 작은 연결 풀. 공용 풀(app.db, pool_timeout 30초)이 차면 생성이 30초 서는 것을 막는다.
# ponytail: 풀 5개 상한(uvicorn 프로세스 하나 — Dockerfile). 기록이 자주 꺼지면 pool_size 를 올린다.
_engine = create_engine(
    settings.database_url,
    pool_size=2,
    max_overflow=3,
    pool_timeout=1,
    pool_pre_ping=True,
    hide_parameters=True,
    connect_args={"connect_timeout": 2},
)
_Sessions = sessionmaker(bind=_engine)

_STOPPED = "GENERATION_STOPPED"


class PromptNoted:
    """provider 를 부르기 직전에 요청의 `prompt_version` 을 timing 에 적는다.

    수리 호출도 같은 문을 지난다. `MaskedMemoProvider.__getattr__` 와 같은 모양이다.
    `with_masked_memo` 에 얹지 않고 그 **안쪽**에 둔다 — 이름표가 없으면 그 함수는 원래 provider 를
    그대로 돌려주고, 가명 치환을 통과하지 못해 부르지 않은 요청의 판은 남기지 않아야 한다.
    """

    def __init__(self, inner) -> None:
        self._inner = inner

    def __getattr__(self, name):
        method = getattr(self._inner, name)
        if not callable(method):
            return method

        def call(request, *args, **kwargs):
            timing.note_prompt(getattr(request, "prompt_version", None))
            return method(request, *args, **kwargs)

        return call


class RunRecorder:
    """한 요청의 기록기. `begin` 뒤로 timing 이 구간이 바뀔 때(`phase`)와 끝날 때(`end`) 부른다."""

    def __init__(self, run_id: uuid.UUID | None = None) -> None:
        self.id = run_id or uuid.uuid4()
        self._kind = self._stage = None
        self._live = False  # 첫 줄을 썼고 아직 실패하지 않았다

    def begin(self, klass) -> None:
        """반 확인 직후 한 번. ORM 객체는 들지 않고 번호만 읽는다."""
        try:
            run = timing.current()
            if run is None or self._kind is not None:
                return
            self._kind, self._stage = run.kind, STAGES[run.kind][0]
            self._live = True
            self._save(
                {
                    "kind": self._kind,
                    "center_id": klass.center_id,
                    "class_id": klass.id,
                    "status": "RUNNING",
                    "stage": self._stage,
                    "mode": settings.llm_mode,
                },
                first=True,
            )
            if self._live:
                timing.observe(self)
        except Exception as error:
            self._off("begin", error)

    def phase(self, name: str) -> None:
        if not self._live:
            return
        try:
            order = STAGES[self._kind]
            stage = OPENS[self._kind].get(name)
            if stage is not None and order.index(stage) > order.index(self._stage):
                self._save({"stage": stage})
                self._stage = stage
        except Exception as error:
            self._off("phase", error)

    def end(self, run, result, error) -> None:
        """timing.timed 의 finally — 핸들러가 commit 한 뒤라 `plan_id` 를 쓸 수 있다."""
        if not self._live:
            return
        try:
            plan_id = code = None
            if error is None:
                outcome, plan_id = "SUCCEEDED", getattr(result, "id", None)
            else:
                detail = error.detail if isinstance(error, HTTPException) else None
                code = detail.get("code") if isinstance(detail, dict) else None
                code = code if isinstance(code, str) else "INTERNAL_ERROR"
                outcome = "STOPPED" if code == _STOPPED else "FAILED"
            self._save(
                {
                    "status": outcome,
                    "error_code": code,
                    "plan_id": plan_id,
                    "finished_at": func.now(),
                    "llm_calls": run.llm_calls,
                    "phase_ms": {name: round(ms) for name, ms in run.ms.items()},
                    "model": MODEL if run.llm_calls else None,
                    "prompt_versions": list(run.prompts) or None,
                }
            )
        except Exception as failure:
            self._off("end", failure)

    def _off(self, step: str, error: Exception) -> None:
        # str(error) 는 찍지 않는다 — Postgres DETAIL 에 값이 든다(db.py · ADR-004).
        self._live = False
        _log.warning(
            "generation_run failed run=%s step=%s type=%s", self.id, step, type(error).__name__
        )

    def _save(self, values: dict, *, first: bool = False) -> None:
        """유일한 DB 쓰기. 테스트는 이 메서드만 바꿔 끼운다. 요청 세션은 건드리지 않는다."""
        with _Sessions() as session:
            session.execute(
                text(
                    "SELECT set_config('lock_timeout', '2s', true), "
                    "set_config('statement_timeout', '2s', true)"
                )
            )
            if first:
                inserted = session.scalar(
                    insert(GenerationRun)
                    .values(id=self.id, **values)
                    .on_conflict_do_nothing(index_elements=["id"])
                    .returning(GenerationRun.id)
                )
                if inserted is None:
                    # 먼저 있던 줄은 다른 반 · 다른 원 것일 수도 있다 — 덮지 않고 기록을 끈다.
                    _log.warning("generation_run duplicate run=%s", self.id)
                    self._live = False
            else:
                session.execute(
                    update(GenerationRun).where(GenerationRun.id == self.id).values(**values)
                )
            session.commit()


def generation_run(
    run_id: Annotated[UUID4 | None, Header(alias=RUN_HEADER)] = None,
) -> RunRecorder:
    return RunRecorder(run_id)


RunRecord = Annotated[RunRecorder, Depends(generation_run)]

router = APIRouter(prefix="/generation-runs", tags=["plans"])
DbSession = Annotated[Session, Depends(get_session)]


class GenerationRunOut(BaseModel):
    id: uuid.UUID
    kind: str
    class_id: int
    status: Literal["RUNNING", "UNKNOWN", "SUCCEEDED", "FAILED", "STOPPED"]
    stage: str
    plan_id: int | None
    error_code: str | None
    mode: str
    model: str | None
    prompt_versions: list[str] | None
    llm_calls: int | None
    phase_ms: dict[str, int] | None
    started_at: datetime
    finished_at: datetime | None


class GenerationRunListOut(BaseModel):
    items: list[GenerationRunOut]


def _out(row: GenerationRun) -> GenerationRunOut:
    out = GenerationRunOut.model_validate(row, from_attributes=True)
    if row.status == "RUNNING" and row.started_at < datetime.now(UTC) - STALE_AFTER:
        out.status = "UNKNOWN"  # 저장하지 않고 읽을 때 만든다 — 끝 줄을 못 쓴 채 끝난 요청
    return out


@router.get("/{run_id}", response_model=GenerationRunOut)
def get_generation_run(run_id: uuid.UUID, session: DbSession, user: CurrentUser):
    """생성 한 번의 지금 단계. 첫 줄을 쓰기 전 · 남의 원 · 기록이 꺼진 요청은 모두 같은 404 다."""
    row = session.scalar(
        select(GenerationRun).where(
            GenerationRun.id == run_id, GenerationRun.center_id == user.center_id
        )
    )
    if row is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail={
                "code": "NOT_FOUND",
                "message": "생성 기록을 찾을 수 없습니다.",
                "fields": ["run_id"],
            },
        )
    require_own_class(session, user, row.class_id, read_only=True)
    return _out(row)


@router.get("", response_model=GenerationRunListOut)
def list_generation_runs(class_id: int, session: DbSession, user: CurrentUser):
    """이 반의 최근 생성 기록 50개, 최근 것부터(5c 「실행 이력 조회」)."""
    require_own_class(session, user, class_id, read_only=True)
    rows = session.scalars(
        select(GenerationRun)
        .where(GenerationRun.class_id == class_id)
        .order_by(GenerationRun.started_at.desc())
        .limit(50)
    )
    return GenerationRunListOut(items=[_out(row) for row in rows])
