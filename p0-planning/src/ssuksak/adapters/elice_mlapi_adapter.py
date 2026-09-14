"""Elice MLAPI LLM Adapter.

Elice MLAPI는 **OpenAI-compatible API**를 제공하므로 내부 구현에 `openai`
Python SDK를 쓰고 `base_url`을 MLAPI endpoint로 지정한다.

    endpoint = Elice MLAPI
    API Key  = Elice Serverless API Key
    billing  = Elice MLAPI credit

`openai` SDK를 쓴다고 해서 OpenAI 직접 API를 호출하는 것이 아니다.

**격리 경계**
Domain과 Application은 이 모듈도, `openai`도, Elice도 import하지 않는다.
그쪽은 `shared/llm/port.py`의 `LLMPort` Protocol만 안다. 모델·Provider 교체가
Domain / Rule / Validation / Provenance 코드를 바꾸지 않는 이유가 이것이다.

**모델을 코드에 확정하지 않는다.**
MLAPI는 GPT-5.6 Terra/Sol/Luna, GPT-5.4, GPT-5.2, GPT-5.1, GPT-5 mini,
GPT-4.1 계열, Claude Sonnet 5 등을 제공한다. 어떤 모델도 이 파일에 적지 않고
`LLM_MODEL` 설정으로만 들어온다. 현재 개발·통합 기준값은 `gpt-4.1-mini`이며
데모 단계에서 상위 모델로 Config만 바꿔 비교한다.

**재시도를 직접 센다.**
SDK 자동 재시도는 횟수를 노출하지 않는데 CLAUDE.md §21이 `retry_count`를
요구한다. 그래서 SDK client는 `max_retries=0`으로 만들고 재시도를 이 Adapter의
루프에서 수행한다.
"""

from __future__ import annotations

import logging
import time
from typing import Callable, Sequence, TypeVar

from pydantic import BaseModel

from ..shared.llm.batch import (
    ThemeBatchPolishRequest,
    ThemeBatchPolishResponse,
)
from ..shared.llm.config import LLMApiStyle, LLMConfig
from ..shared.llm.monthly import (
    MonthlyPlanProposal,
    MonthlyPlannerRequest,
    MonthlyProposalError,
    reconcile_monthly_proposal,
)
from ..shared.llm.monthly_cell import (
    MonthlyCellProposalError,
    MonthlyCellRegenerationProposal,
    MonthlyCellRegenerationRequest,
    reconcile_cell_proposal,
)
from ..shared.llm.port import (
    LLMConfigurationError,
    LLMUnavailableError,
    ThemePolishRequest,
    ThemePolishResponse,
)
from ..shared.llm.telemetry import LLMCallRecord

__all__ = ["EliceMLAPIAdapter", "PROVIDER_NAME", "build_openai_client"]

PROVIDER_NAME = "elice-mlapi"

_Schema = TypeVar("_Schema", bound=BaseModel)

MAX_REPAIR_ATTEMPTS = 1
"""Structured Output이 Packet Contract를 어겼을 때의 재요청 횟수.

Transport 재시도(`LLM_MAX_RETRIES`)와 **다른 축**이다. 저쪽은 네트워크·서버
실패를, 이쪽은 모델이 계약을 어긴 경우를 다룬다. 1회로 제한하는 이유는
두 번째까지 같은 실수를 하면 Prompt나 Packet 쪽 문제이지 우연이 아니기
때문이다. 무제한 재시도는 비용만 쓰고 원인을 가린다.
"""

_LOGGER = logging.getLogger("ssuksak.llm")

TelemetrySink = Callable[[LLMCallRecord], None]

_BATCH_SYSTEM_PROMPT = (
    "당신은 한국 어린이집 만 3~5세 보육계획안의 표현을 다듬는 편집자입니다.\n"
    "각 항목에는 이미 확정된 월(period_key)과 주제 식별자(theme_id), "
    "그리고 주제 이름(label)이 주어집니다.\n"
    "\n"
    "규칙:\n"
    "1. period_key와 theme_id는 그대로 되돌려 주세요. 절대 바꾸거나 새로 만들지 마세요.\n"
    "2. 항목을 추가하거나 빼지 마세요. 받은 항목 수와 정확히 같아야 합니다.\n"
    "3. value에는 label의 의미를 유지한 자연스러운 한국어 표현을 쓰세요.\n"
    "4. 주어지지 않은 행사·날짜·사실을 만들지 마세요.\n"
    "5. 보육계획안에 어울리는 담백하고 따뜻한 문체를 쓰세요.\n"
)

_SINGLE_SYSTEM_PROMPT = (
    "당신은 한국 어린이집 만 3~5세 보육계획안의 표현을 다듬는 편집자입니다.\n"
    "주어진 theme_id는 그대로 되돌려 주고, value에는 label의 의미를 유지한 "
    "자연스러운 한국어 표현을 쓰세요.\n"
    "주어지지 않은 행사·날짜·사실을 만들지 마세요.\n"
)


def build_openai_client(config: LLMConfig):
    """Elice MLAPI를 가리키는 OpenAI-compatible client를 만든다.

    `max_retries=0`은 의도적이다. 재시도는 Adapter가 세면서 수행한다.
    """
    try:
        from openai import OpenAI
    except ImportError as exc:  # pragma: no cover - 의존성 미설치 환경
        raise LLMConfigurationError(
            "openai SDK가 설치되지 않았다. Elice MLAPI Adapter는 "
            "OpenAI-compatible SDK를 사용한다."
        ) from exc

    return OpenAI(
        api_key=config.api_key,
        base_url=config.base_url,
        timeout=config.timeout_seconds,
        max_retries=0,
    )


class EliceMLAPIAdapter:
    """`LLMPort` 구현. Elice MLAPI를 OpenAI-compatible로 호출한다."""

    def __init__(
        self,
        config: LLMConfig,
        *,
        client: object | None = None,
        telemetry_sink: TelemetrySink | None = None,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        """Args:
        client: 주입하면 그대로 사용한다. 테스트가 네트워크 없이 전 경로를
            검증할 수 있게 하는 지점이다. None이면 실제 client를 만든다.
        telemetry_sink: `LLMCallRecord` 수신자. None이면 구조화 로그로 남긴다.
        """
        self._config = config
        self._client = client if client is not None else build_openai_client(config)
        self._sink = telemetry_sink or _log_record
        self._sleep = sleep
        self._monotonic = monotonic

    # ------------------------------------------------------------ Batch

    def polish_themes(
        self, request: ThemeBatchPolishRequest
    ) -> ThemeBatchPolishResponse:
        """요청 1회로 여러 Theme 표현을 받는다."""
        payload = _render_batch_payload(request)
        item_count = len(request.items)

        return self._invoke(
            operation="polish_themes",
            system_prompt=_BATCH_SYSTEM_PROMPT,
            user_content=payload,
            schema=ThemeBatchPolishResponse,
            item_count=item_count,
            theme_ids=tuple(i.theme_id for i in request.items),
            period_keys=tuple(i.period_key for i in request.items),
        )

    # ------------------------------------------------------------ 단건

    def polish_theme(self, request: ThemePolishRequest) -> ThemePolishResponse:
        """Regenerate가 쓰는 단건 경로. Batch와 별개로 유지한다."""
        payload = _render_single_payload(request)

        batch_like = self._invoke(
            operation="polish_theme",
            system_prompt=_SINGLE_SYSTEM_PROMPT,
            user_content=payload,
            schema=ThemeBatchPolishResponse,
            item_count=1,
            theme_ids=(request.selected_theme_id,),
            period_keys=(request.period_key,),
        )

        if len(batch_like.themes) != 1:
            raise ValueError(
                f"단건 요청에 {len(batch_like.themes)}개가 반환되었다"
            )
        item = batch_like.themes[0]
        return ThemePolishResponse(theme_id=item.theme_id, value=item.value)

    # ------------------------------------------------------ Monthly Planner

    def plan_monthly(self, request: MonthlyPlannerRequest) -> MonthlyPlanProposal:
        """한 달 전체 계획을 요청 1회로 받는다 (L4).

        Prompt 본문은 `request`가 들고 온다. 이 Adapter는 전송·파싱·대조만
        한다(§20 — Adapter에 Prompt를 박지 않는다).

        Structured Output이 Packet Contract를 어기면 **최대 1회** repair를
        보낸다. Transport 재시도와 다른 축이며, repair에도 실패하면
        `MonthlyProposalError`를 그대로 올린다. **빈 Proposal이나 Rule-only
        결과로 대신하지 않는다.**
        """
        content = request.user_content
        last_error: MonthlyProposalError | None = None

        for repair in range(MAX_REPAIR_ATTEMPTS + 1):
            proposal = self._invoke(
                operation="plan_monthly",
                system_prompt=request.system_prompt,
                user_content=content,
                schema=MonthlyPlanProposal,
                item_count=len(request.expected_week_ids),
                period_keys=request.expected_week_ids,
                theme_ids=(request.expected_theme_id,),
                extra={
                    # `prompt_version`이라 부르지 않는다 — telemetry가 키에
                    # "prompt"가 들어간 항목을 거부한다. 그 가드는 Prompt 본문이
                    # 로그에 새는 것을 막는 장치이므로 이름 편의로 완화하지 않는다.
                    "template_version": request.prompt_version,
                    "packet_fingerprint": request.packet_fingerprint,
                    "repair_count": repair,
                },
            )
            try:
                return reconcile_monthly_proposal(
                    proposal,
                    expected_theme_id=request.expected_theme_id,
                    expected_week_ids=request.expected_week_ids,
                    reference_labels=request.reference_labels,
                    valid_grounding_refs=request.valid_grounding_refs,
                )
            except MonthlyProposalError as exc:
                last_error = exc
                if repair >= MAX_REPAIR_ATTEMPTS:
                    break
                content = _with_repair_note(request.user_content, exc)

        assert last_error is not None  # noqa: S101 - 루프 구조상 항상 설정된다
        raise last_error

    # ------------------------------------------------- Cell Regeneration

    def regenerate_monthly_cell(
        self, request: MonthlyCellRegenerationRequest
    ) -> MonthlyCellRegenerationProposal:
        """Cell 하나만 다시 쓴다 (L7).

        `plan_monthly`와 같은 repair 정책을 쓴다 — 새 정책을 만들지 않는다.
        """
        content = request.user_content
        last_error: MonthlyCellProposalError | None = None

        for repair in range(MAX_REPAIR_ATTEMPTS + 1):
            proposal = self._invoke(
                operation="regenerate_monthly_cell",
                system_prompt=request.system_prompt,
                user_content=content,
                schema=MonthlyCellRegenerationProposal,
                item_count=1,
                period_keys=(request.target_week_id,),
                theme_ids=(request.expected_theme_id,),
                extra={
                    "template_version": request.prompt_version,
                    "packet_fingerprint": request.packet_fingerprint,
                    "target_section_key": request.target_section_key,
                    "plan_snapshot_fingerprint": request.plan_snapshot_fingerprint,
                    "repair_count": repair,
                },
            )
            try:
                return reconcile_cell_proposal(
                    proposal,
                    target_week_id=request.target_week_id,
                    target_section_key=request.target_section_key,
                    reference_labels=request.reference_labels,
                    valid_grounding_refs=request.valid_grounding_refs,
                )
            except MonthlyCellProposalError as exc:
                last_error = exc
                if repair >= MAX_REPAIR_ATTEMPTS:
                    break
                content = _with_cell_repair_note(request.user_content, exc)

        assert last_error is not None  # noqa: S101 - 루프 구조상 항상 설정된다
        raise last_error

    # ------------------------------------------------------------ 내부

    def _invoke(
        self,
        *,
        operation: str,
        system_prompt: str,
        user_content: str,
        schema: type[_Schema],
        item_count: int,
        theme_ids: Sequence[str] = (),
        period_keys: Sequence[str] = (),
        extra: dict[str, object] | None = None,
    ) -> _Schema:
        started = self._monotonic()
        retry_count = 0
        last_error: Exception | None = None

        while retry_count <= self._config.max_retries:
            try:
                parsed, request_id, usage = self._call_once(
                    system_prompt, user_content, schema
                )
            except _RetryableProviderError as exc:
                last_error = exc
                if retry_count >= self._config.max_retries:
                    break
                delay = exc.retry_after if exc.retry_after is not None else _backoff(
                    retry_count
                )
                retry_count += 1
                self._sleep(delay)
                continue
            except LLMConfigurationError as exc:
                # 인증·권한·요청 오류는 재시도하지 않는다.
                self._emit(
                    operation,
                    success=False,
                    started=started,
                    retry_count=retry_count,
                    item_count=item_count,
                    theme_ids=theme_ids,
                    period_keys=period_keys,
                    validation_result="CONFIG_ERROR",
                    failure_kind=getattr(exc, "kind", "CONFIG"),
                    extra=extra,
                )
                raise
            except ValueError as exc:
                self._emit(
                    operation,
                    success=False,
                    started=started,
                    retry_count=retry_count,
                    item_count=item_count,
                    theme_ids=theme_ids,
                    period_keys=period_keys,
                    validation_result=f"SCHEMA_VIOLATION: {exc}"[:200],
                    failure_kind="SCHEMA",
                    extra=extra,
                )
                raise

            self._emit(
                operation,
                success=True,
                started=started,
                retry_count=retry_count,
                item_count=item_count,
                theme_ids=theme_ids,
                period_keys=period_keys,
                validation_result="OK",
                request_id=request_id,
                usage=usage,
                extra=extra,
            )
            return parsed

        self._emit(
            operation,
            success=False,
            started=started,
            retry_count=retry_count,
            item_count=item_count,
            theme_ids=theme_ids,
            period_keys=period_keys,
            validation_result="PROVIDER_FAILURE",
            failure_kind=getattr(last_error, "kind", "UNAVAILABLE"),
            extra=extra,
        )
        raise LLMUnavailableError(
            f"Elice MLAPI 호출이 재시도 {retry_count}회 후에도 실패했다: {last_error}",
            kind=getattr(last_error, "kind", "UNAVAILABLE"),
        )

    def _call_once(
        self,
        system_prompt: str,
        user_content: str,
        schema: type[_Schema],
    ) -> tuple[_Schema, str | None, tuple[int | None, int | None]]:
        """API 1회 호출. 예외를 우리 분류로 변환한다."""
        try:
            if self._config.api_style is LLMApiStyle.RESPONSES:
                return self._call_responses(system_prompt, user_content, schema)
            return self._call_chat_completions(system_prompt, user_content, schema)
        except Exception as exc:  # noqa: BLE001 - 아래에서 분류해 재전파
            classified = _classify_provider_error(exc)
            if classified is not None:
                raise classified from exc
            raise

    def _call_responses(self, system_prompt, user_content, schema):
        kwargs: dict[str, object] = {
            "model": self._config.model,
            "instructions": system_prompt,
            "input": user_content,
            "text_format": schema,
        }
        if self._config.reasoning_effort:
            kwargs["reasoning"] = {"effort": self._config.reasoning_effort}
        if self._config.max_output_tokens:
            kwargs["max_output_tokens"] = self._config.max_output_tokens

        response = self._client.responses.parse(**kwargs)
        parsed = response.output_parsed
        if parsed is None:
            raise ValueError("Responses API가 parsed 출력을 돌려주지 않았다")

        usage = getattr(response, "usage", None)
        tokens = (
            getattr(usage, "input_tokens", None),
            getattr(usage, "output_tokens", None),
        )
        return parsed, getattr(response, "id", None), tokens

    def _call_chat_completions(self, system_prompt, user_content, schema):
        kwargs: dict[str, object] = {
            "model": self._config.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            "response_format": schema,
        }
        if self._config.reasoning_effort:
            kwargs["reasoning_effort"] = self._config.reasoning_effort
        if self._config.max_output_tokens:
            kwargs["max_completion_tokens"] = self._config.max_output_tokens

        response = self._client.chat.completions.parse(**kwargs)
        choices = getattr(response, "choices", None) or []
        if not choices:
            raise ValueError("Chat Completions가 choices를 돌려주지 않았다")

        message = choices[0].message
        refusal = getattr(message, "refusal", None)
        if refusal:
            raise ValueError(f"모델이 요청을 거부했다: {refusal}")

        parsed = getattr(message, "parsed", None)
        if parsed is None:
            raise ValueError("Chat Completions가 parsed 출력을 돌려주지 않았다")

        usage = getattr(response, "usage", None)
        tokens = (
            getattr(usage, "prompt_tokens", None),
            getattr(usage, "completion_tokens", None),
        )
        return parsed, getattr(response, "id", None), tokens

    def _emit(
        self,
        operation: str,
        *,
        success: bool,
        started: float,
        retry_count: int,
        item_count: int,
        theme_ids: Sequence[str],
        period_keys: Sequence[str],
        validation_result: str,
        request_id: str | None = None,
        usage: tuple[int | None, int | None] = (None, None),
        failure_kind: str | None = None,
        extra: dict[str, object] | None = None,
    ) -> None:
        record = LLMCallRecord(
            operation=operation,
            provider=PROVIDER_NAME,
            model=self._config.model,
            success=success,
            latency_ms=int((self._monotonic() - started) * 1000),
            retry_count=retry_count,
            item_count=item_count,
            input_tokens=usage[0],
            output_tokens=usage[1],
            validation_result=validation_result,
            api_style=self._config.api_style.value,
            reasoning_effort=self._config.reasoning_effort,
            request_id=request_id,
            failure_kind=failure_kind,
            theme_ids=tuple(theme_ids),
            period_keys=tuple(period_keys),
            extra=dict(extra or {}),
        )
        self._sink(record)


# ------------------------------------------------------------- 오류 분류


class _RetryableProviderError(RuntimeError):
    def __init__(self, message: str, *, kind: str, retry_after: float | None = None):
        self.kind = kind
        self.retry_after = retry_after
        super().__init__(message)


def _retry_after_of(exc: Exception) -> float | None:
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None)
    if not headers:
        return None
    raw = headers.get("retry-after")
    if not raw:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _classify_provider_error(exc: Exception) -> Exception | None:
    """SDK 예외를 재시도 가능/설정 오류로 분류한다.

    `openai`가 없는 환경에서도 동작하도록 클래스 이름으로 판별한다.
    """
    name = type(exc).__name__

    if name in ("APITimeoutError",):
        return _RetryableProviderError(f"timeout: {exc}", kind="TIMEOUT")
    if name in ("RateLimitError",):
        return _RetryableProviderError(
            f"rate limit: {exc}", kind="RATE_LIMIT", retry_after=_retry_after_of(exc)
        )
    if name in ("APIConnectionError", "InternalServerError"):
        return _RetryableProviderError(f"connection/server: {exc}", kind="CONNECTION")

    if name in ("AuthenticationError",):
        return LLMConfigurationError(
            f"Elice MLAPI 인증 실패. ELICE_MLAPI_API_KEY를 확인하라: {exc}",
            kind="AUTH",
        )
    if name in ("PermissionDeniedError",):
        return LLMConfigurationError(f"권한 거부: {exc}", kind="PERMISSION")
    if name in ("NotFoundError",):
        return LLMConfigurationError(
            f"모델 또는 endpoint를 찾을 수 없다. LLM_MODEL과 "
            f"ELICE_MLAPI_BASE_URL을 확인하라: {exc}",
            kind="NOT_FOUND",
        )
    if name in ("BadRequestError", "UnprocessableEntityError"):
        return LLMConfigurationError(
            f"요청이 거부되었다. reasoning effort 미지원 모델이면 "
            f"LLM_REASONING_EFFORT=none으로 두라: {exc}",
            kind="BAD_REQUEST",
        )

    status = getattr(exc, "status_code", None)
    if isinstance(status, int):
        if status >= 500:
            return _RetryableProviderError(f"server {status}: {exc}", kind="SERVER")
        if status in (408, 409, 429):
            return _RetryableProviderError(f"transient {status}: {exc}", kind="TRANSIENT")
        return LLMConfigurationError(f"client {status}: {exc}", kind="CLIENT_ERROR")

    if name == "ValidationError":
        return ValueError(f"Structured Output 스키마 위반: {exc}")

    return None


def _backoff(attempt: int) -> float:
    """지수 백오프. 결정론적이라 테스트에서 예측 가능하다."""
    return min(0.5 * (2**attempt), 8.0)


def _log_record(record: LLMCallRecord) -> None:
    """기본 telemetry 싱크. API Key·전체 Prompt를 담지 않는다."""
    _LOGGER.info("llm_call", extra={"llm": record.to_log_dict()})


# ------------------------------------------------------------- 프롬프트


def _with_repair_note(user_content: str, error: MonthlyProposalError) -> str:
    """Repair 요청 본문. **원래 Context 전체 + 위반 요약**이다.

    위반만 보내면 모델이 무엇을 고쳐야 하는지 알아도 근거가 없어 다시 쓸 수
    없다. 요약에는 Prompt 본문도 Key도 담기지 않는다 — 위반 식별자와 값뿐이다.
    """
    return (
        f"{user_content}\n\n"
        "# 직전 응답이 계약을 위반했습니다\n"
        f"- {error.summary}\n"
        "위 내용을 고쳐 같은 형식으로 다시 반환하세요."
    )


def _with_cell_repair_note(user_content: str, error: MonthlyCellProposalError) -> str:
    """Cell repair 본문. 원래 Context 전체 + 위반 요약이다."""
    return (
        f"{user_content}\n\n"
        "# 직전 응답이 계약을 위반했습니다\n"
        f"- {error.summary}\n"
        "위 내용을 고쳐 같은 형식으로 다시 반환하세요."
    )


def _render_batch_payload(request: ThemeBatchPolishRequest) -> str:
    """요청 본문. **후보 목록을 담지 않는다.**"""
    import json

    items = [
        {
            "period_key": item.period_key,
            "theme_id": item.theme_id,
            "label": item.label,
            **({"events": list(item.event_labels)} if item.event_labels else {}),
        }
        for item in request.items
    ]
    body: dict[str, object] = {
        "school_year": request.school_year,
        "ages": list(request.ages),
        "item_count": len(items),
        "items": items,
    }
    if request.constraints.max_chars is not None:
        body["max_chars_per_value"] = request.constraints.max_chars
    return json.dumps(body, ensure_ascii=False, indent=2)


def _render_single_payload(request: ThemePolishRequest) -> str:
    import json

    body: dict[str, object] = {
        "school_year": None,
        "ages": list(request.ages),
        "item_count": 1,
        "items": [
            {
                "period_key": request.period_key,
                "theme_id": request.selected_theme_id,
                "label": request.selected_theme_label,
                **(
                    {"events": list(request.event_labels)}
                    if request.event_labels
                    else {}
                ),
            }
        ],
    }
    if request.constraints.max_chars is not None:
        body["max_chars_per_value"] = request.constraints.max_chars
    return json.dumps(body, ensure_ascii=False, indent=2)
