"""놀이 프로젝트형 연간계획안을 생성하고 응답 형식으로 옮긴다 (api-spec §4)."""

import json
import logging
import random
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from functools import partial
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StrictStr, StringConstraints
from ssuksak import timing
from ssuksak.adapters.elice_openai_monthly import MonthlyLlmConfigurationError
from ssuksak.adapters.in_memory_plan_repository import InMemoryPlanRepository
from ssuksak.adapters.json_curriculum_reference_repository import JsonCurriculumReferenceRepository

# Core 가 공개 창구에 아직 안 내놓아 안쪽에서 가져온다 — router.py 와 같다.
from ssuksak.planning.application.generate_play_project_plan import (
    PLAY_PROJECT_LAYOUT_V0_2,
    GeneratePlayProjectPlan,
    GeneratePlayProjectPlanCommand,
    PlayProjectGenerationError,
)
from ssuksak.planning.domain.play_project_plan import ROW_FIELDS, PlayProjectYearlyPlan
from ssuksak.planning.domain.teacher_memo import TEACHER_MEMO_EVIDENCE
from ssuksak.planning.planner.contracts import ProposalRejectedError, RawLlmResponse
from ssuksak.planning.planner.play_project import (
    PlayProjectRequest,
    overlapping_candidates,
    remaining_memo_notices,
)

from app.features.plans.generation_runs import PromptNoted
from app.features.plans.memo_privacy import MemoMaskFailed, with_masked_memo
from app.features.plans.models import Plan
from app.features.plans.monthly_llm import monthly_llm_provider
from app.features.plans.monthly_schemas import RevisionIn
from app.features.plans.runtime import FixedPlanIdGenerator, SystemClock, UuidGenerator
from app.features.plans.schemas import (
    EvidenceOut,
    GenerationOut,
    PlayAuditEventOut,
    PlayAuditOut,
    PlayCandidateOut,
    PlayCellOut,
    PlayPeriodOut,
    PlayProjectPlanOut,
    SelectionChangeOut,
    ValueChangeOut,
    memo_notices_out,
)
from app.shared.childCode import NameTable
from app.shared.llm import LlmBudgetExceeded, LlmCallCapExceeded, LlmUnavailable, is_mock

_log = logging.getLogger(__name__)
CURRICULUM_CATALOG_ID = "ssuksak.nuri-curriculum-content"
CURRICULUM_CATALOG_VERSION = "nuri-curriculum-content-v0.1.0"
_PERIOD_LABELS = {
    "m03_m05": "3~5월",
    "m06_m08": "6~8월",
    "m09_m11": "9~11월",
    "m12_m02": "12~2월",
}


class MockPlayProjectProvider:
    def generate_play_project(self, request: PlayProjectRequest) -> RawLlmResponse:
        content_ids = sorted(request.allowed_content_ids)
        return RawLlmResponse(
            content=json.dumps(
                {
                    "period_key": request.period_key,
                    "rows": [
                        {
                            "play_name": (
                                f"{_PERIOD_LABELS[request.period_key]} {seed.nuri_content}"
                            ),
                            "materials": seed.material_hint,
                            "support_direction": (
                                "주변의 모양과 움직임을 살펴보는 놀이를 지원하면 유아들이 "
                                "자료를 자유롭게 놓고 이어 보며 놀이를 넓혀 갈 수 있도록 돕는다."
                            ),
                            "learning_content_ids": [
                                seed.nuri_content_id,
                                next(i for i in content_ids if i != seed.nuri_content_id),
                            ],
                        }
                        for seed in request.play_seeds
                    ],
                    # 요청 사항이 있으면 mock 은 첫 후보에 반영했다고 답한다(ADR-060).
                    **(
                        {
                            "memo_applied": list(request.memo_addresses[:1]),
                            "memo_skipped": [],
                            "memo_reflected": [],
                        }
                        if request.memo_addresses is not None
                        else {}
                    ),
                },
                ensure_ascii=False,
            ),
            model="mock",
        )


def curriculum_repository():
    return JsonCurriculumReferenceRepository()


def provider():
    return MockPlayProjectProvider() if is_mock() else monthly_llm_provider()


class GenerationStopped(Exception):
    """교사가 「생성 멈추기」로 요청을 끊었다 — 다음 단계를 부르지 않고 저장하지 않는다."""


# 다시 불러도 풀리지 않는 실패 — 한도 · 키 · 호출 상한(ADR-081) · 설정 · 참조 미승인 · 메모 가명
# (ADR-077 · ADR-076).
_FINAL = (
    LlmBudgetExceeded,
    LlmCallCapExceeded,
    LlmUnavailable,
    MonthlyLlmConfigurationError,
    MemoMaskFailed,
    PlayProjectGenerationError,
)


def _final(error: BaseException, kinds: tuple[type, ...] = _FINAL) -> bool:
    seen = set()
    while error is not None and id(error) not in seen:
        if isinstance(error, kinds):
            return True
        seen.add(id(error))
        error = error.__cause__ or error.__context__  # type: ignore[assignment]
    return False


def _each(pool, jobs: dict):
    """jobs 를 동시에 부르고 {key: 결과 또는 예외} — 하나가 실패해도 나머지를 기다린다."""
    futures = {key: pool.submit(timing.in_thread(job)) for key, job in jobs.items()}
    done = {}
    for key, future in futures.items():
        try:
            done[key] = future.result()
        except Exception as error:
            done[key] = error
    return done


def _noted(done: dict, keys, attempt: int) -> None:
    """구간 생성 한 번(호출 + 검사)의 결과를 생성 기록에 적는다 — 요청 스레드에서만(ADR-096)."""
    for key in keys:
        value = done[key]
        result = type(value).__name__ if isinstance(value, Exception) else "ok"
        timing.note_attempt("period", result, period=key, attempt=attempt)


def _memo_applied(candidate) -> bool:
    return TEACHER_MEMO_EVIDENCE in candidate.play_name.evidence


def generate(
    school_year: int,
    classroom_ref: str,
    target_ages: frozenset[int],
    memo: str = "",
    names: NameTable | None = None,
    stopped: Callable[[], bool] = lambda: False,
    rng: random.Random | None = None,
):
    """네 구간을 동시에 만들고, 실패한 구간만 한 번 · 겹친 후보만 한 번 다시 만든다(ADR-077).

    `stopped()` 는 요청 스레드에서만 부른다(router `_disconnected` 가 anyio 작업 스레드 전용이다).
    """
    plan_id = UuidGenerator().new_plan_id()
    use_case = GeneratePlayProjectPlan(
        curriculum_repository=curriculum_repository(),
        plan_repository=InMemoryPlanRepository(),
        provider=with_masked_memo(PromptNoted(provider()), memo, names),
        clock=SystemClock(),
        id_generator=FixedPlanIdGenerator(plan_id),
    )
    keys = [period.key for period in PLAY_PROJECT_LAYOUT_V0_2.periods]
    seeds = use_case.draw_seeds(
        CURRICULUM_CATALOG_ID, CURRICULUM_CATALOG_VERSION, rng or random.Random()
    )

    def period(key, play_seeds, avoid_play_names=(), teacher_memo=memo):
        return use_case.generate_period(
            GeneratePlayProjectPlanCommand(
                school_year=school_year,
                classroom_ref=classroom_ref,
                target_ages=target_ages,
                period_key=key,
                curriculum_catalog_id=CURRICULUM_CATALOG_ID,
                curriculum_catalog_version=CURRICULUM_CATALOG_VERSION,
                avoid_play_names=avoid_play_names,
                teacher_memo=teacher_memo,
                play_seeds=play_seeds,
            )
        )

    # 끊어도 이미 동시에 부른 비용은 남는다 — 저장만 하지 않는다(ADR-077, 하민 결정 2026-11-06).
    if stopped():
        raise GenerationStopped("parallel")
    timing.phase("llm")
    with ThreadPoolExecutor(len(keys)) as pool:
        done = _each(pool, {key: partial(period, key, seeds[key]) for key in keys})
        _noted(done, keys, 1)
        failed = [key for key in keys if isinstance(done[key], Exception)]
        for key in failed:
            if _final(done[key]):
                raise done[key]
        if failed:
            if stopped():
                raise GenerationStopped("recall")
            done |= _each(pool, {key: partial(period, key, seeds[key]) for key in failed})
            _noted(done, failed, 2)
            for key in failed:
                if isinstance(done[key], Exception):
                    raise done[key]
        rows = {key: list(done[key][0].periods[0].candidates) for key in keys}

        # 겹침 찾기 · 겹친 후보 다시 — 생성 기록의 「겹치는 놀이 살펴보기」 단계(ADR-096)
        timing.phase("overlap")
        targets = overlapping_candidates(
            [
                [(c.play_name.value, c.materials.value, _memo_applied(c)) for c in rows[k]]
                for k in keys
            ]
        )
        by_period: dict[str, list[int]] = {}
        for j, i in targets:
            by_period.setdefault(keys[j], []).append(i)
        if by_period:
            if stopped():
                raise GenerationStopped("replace")
            redo = {}
            for key, index in by_period.items():
                avoid = tuple(
                    c.play_name.value
                    for k in keys
                    for n, c in enumerate(rows[k])
                    if not (k == key and n in index)
                )
                # 요청 사항은 넣지 않는다 — 요청을 반영한 후보는 바꾸지 않아 알림이 그대로다.
                redo[key] = partial(period, key, tuple(seeds[key][i] for i in index), avoid, "")
            for key, result in _each(pool, redo).items():
                if isinstance(result, Exception):
                    if _final(result, (LlmCallCapExceeded,)):
                        raise result  # 상한이 샌 반복문 신호다 — 원래 후보로 덮고 이어 가지 않는다
                    _log.warning(
                        "annual play-project replace failed period=%s type=%s",
                        key,
                        type(result).__name__,
                    )
                    continue
                for i, new in zip(by_period[key], result[0].periods[0].candidates, strict=True):
                    rows[key][i] = replace(new, row_key=rows[key][i].row_key)
    timing.phase("assemble")
    names_ = [" ".join(c.play_name.value.split()) for k in keys for c in rows[k]]
    left = overlapping_candidates(
        [[(c.play_name.value, c.materials.value, False) for c in rows[k]] for k in keys]
    )
    _log.info(
        "annual play-project parallel recalled=%d replaced=%d overlaps_left=%d",
        len(failed),
        sum(len(index) for index in by_period.values()),
        len(left),
    )
    # 비슷한 겹침은 원래 후보를 둔다(품질 문제). 같은 이름은 순차에서도 저장된 적 없다.
    if len(set(names_)) != len(names_):
        raise ProposalRejectedError(("DUPLICATE_PLAY_NAME",))
    if stopped():  # 끝난 뒤 끊겼어도 저장하지 않는다 — 다시 만들 때 409 가 나지 않는다.
        raise GenerationStopped("save")
    first = done[keys[0]][0]
    return replace(
        first,
        periods=tuple(
            replace(done[key][0].periods[0], candidates=tuple(rows[key])) for key in keys
        ),
        # 같은 요청을 여러 구간이 못 했다고 답하면 한 번만, 다른 구간이 반영했으면 뺀다.
        memo_notices=remaining_memo_notices(
            memo, tuple((done[key][0].memo_notices, done[key][1]) for key in keys)
        ),
    )


def format_of(row: Plan) -> str:
    """양식은 본문에 있다. 없으면 월별 주제형이다(ADR-043 §1 · 마이그레이션 없음)."""
    return row.body.get("format", "MONTHLY_THEME")


def _cell(item) -> PlayCellOut:
    return PlayCellOut(
        item_id=item.item_id.value,
        value=item.value,
        evidence=[
            EvidenceOut(
                source_type=source.source_type.value,
                source_id=source.source_id,
                source_version=source.source_version,
                effective_date=None,
                display_name=source.display_name,
            )
            for source in item.evidence
        ],
        generation=GenerationOut(
            method=item.generation.method.value,
            rule_id=item.generation.rule_id,
            rule_version=item.generation.rule_version,
        ),
    )


def to_out(row: Plan, plan: PlayProjectYearlyPlan) -> PlayProjectPlanOut:
    return PlayProjectPlanOut(
        id=row.id,
        memo=plan.teacher_memo,
        memo_notices=memo_notices_out(plan),
        revision=row.revision,
        class_id=int(plan.classroom_ref),
        school_year=plan.school_year,
        status=plan.status.value,
        format=plan.format,
        format_version=plan.layout_version,
        periods=[
            PlayPeriodOut(
                period_key=p.period.key,
                label=p.period.label,
                months=list(p.period.months),
                candidates=[
                    PlayCandidateOut(
                        row_key=c.row_key,
                        # 표시용(Human Decision 2026-11-05): 선택 · 배치에 쓰지 않는다.
                        memo_applied=bool(plan.teacher_memo)
                        and TEACHER_MEMO_EVIDENCE in c.play_name.evidence,
                        **{name: _cell(getattr(c, name)) for name in ROW_FIELDS},
                    )
                    for c in p.candidates
                ],
                selected=list(p.selected),
            )
            for p in plan.periods
        ],
    )


def audit_out(plan: PlayProjectYearlyPlan) -> PlayAuditOut:
    """계획안 · 모든 후보 칸의 저장된 이벤트를 발생 시각순으로. type 은 걸러내지 않는다."""
    events = list(plan.audit.events)
    for period in plan.periods:
        for candidate in period.candidates:
            for name in ROW_FIELDS:
                events += getattr(candidate, name).audit.events
    events.sort(key=lambda event: event.occurred_at)  # 안정 정렬 — 같은 시각이면 원래 순서
    return PlayAuditOut(
        items=[
            PlayAuditEventOut(
                type=e.event_type.value,
                occurred_at=e.occurred_at,
                actor=e.actor_id.value if e.actor_id is not None else None,
                system_actor=e.system_actor,
                value_change=(
                    ValueChangeOut(before=e.value_change.before, after=e.value_change.after)
                    if e.value_change is not None
                    else None
                ),
                item_id=e.item_id.value if e.item_id is not None else None,
                selection_change=(
                    SelectionChangeOut(
                        period_key=e.selection_change.period_key,
                        before=list(e.selection_change.before),
                        after=list(e.selection_change.after),
                    )
                    if e.selection_change is not None
                    else None
                ),
            )
            for e in events
        ]
    )


def _no_duplicates(keys: list[str]) -> list[str]:
    if len(keys) != len(set(keys)):
        raise ValueError("같은 후보를 두 번 고를 수 없습니다")
    return keys


# row_key 는 Core 가 "cand1".."candN" 으로 만든다(domain/play_project_plan.py:67). 형식 · 길이
# 규칙은 Core 에 없어 모양은 걸지 않고, 없는 후보는 Core 의 invalid_selection 이 막는다.
# 5개는 layout.selected_per_period(application/play_project_lifecycle.py:84)와 같은 값이다.
_Selected = Annotated[list[StrictStr], Field(max_length=5), AfterValidator(_no_duplicates)]


class PlaySelections(BaseModel):
    """네 구간을 모두 받는다(api-spec §6-1). 구간 키는 _PERIOD_LABELS 와 같다."""

    model_config = ConfigDict(extra="forbid")

    m03_m05: _Selected
    m06_m08: _Selected
    m09_m11: _Selected
    m12_m02: _Selected


class SaveSelectionIn(RevisionIn):
    selections: PlaySelections


class EditItemIn(RevisionIn):
    # 본문이 JSONB 라 맞출 컬럼이 없다. Core 생성 검사의 가장 긴 칸(지원 방향 600자,
    # planner/text_policy.py:8 MAX_RATIONALE_CHARS)에 맞춘다.
    value: Annotated[
        str, StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=600)
    ]


class ConfirmIn(RevisionIn):
    # 월별 주제형은 본문을 안 읽으므로 `{}` 도 받아야 한다.
    # 놀이형의 「없음」은 라우터가 422 로 막고, 타입이 틀린 값은 여기서 먼저 422 다.
    expected_revision: Annotated[int, Field(ge=1, strict=True)] | None = None  # type: ignore[assignment]
