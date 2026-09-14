"""LLM 호출 telemetry.

CLAUDE.md §21이 요구하는 기록 항목:
    요청 종류 · 모델 · 입력 토큰 · 출력 토큰 · latency ·
    성공/실패 · validation 결과 · retry 횟수

금지: API Key, 전체 Prompt, 개인정보를 일반 애플리케이션 로그에 남기지 않는다.
이 레코드에는 프롬프트 본문 필드가 **존재하지 않는다**. 남기는 것은
theme_id·period_key 같은 Reference 식별자와 집계 수치뿐이다.

`retry_count`를 정확히 세기 위해 Adapter는 SDK 자동 재시도를 끄고
(`max_retries=0`) 자체 루프에서 재시도한다. CLAUDE.md §21이 retry 횟수를
명시적으로 요구하므로 SDK에 위임하면 관측이 불가능해진다.
"""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = ["LLMCallRecord"]

_FORBIDDEN_KEYS = ("api_key", "authorization", "prompt", "messages", "input")


@dataclass(frozen=True, slots=True)
class LLMCallRecord:
    """호출 1회의 관측 기록."""

    operation: str
    provider: str
    model: str
    success: bool
    latency_ms: int
    retry_count: int
    item_count: int
    input_tokens: int | None = None
    output_tokens: int | None = None
    validation_result: str = "OK"
    api_style: str | None = None
    reasoning_effort: str | None = None
    request_id: str | None = None
    failure_kind: str | None = None
    theme_ids: tuple[str, ...] = ()
    period_keys: tuple[str, ...] = ()
    extra: dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for key in self.extra:
            if any(bad in key.lower() for bad in _FORBIDDEN_KEYS):
                raise ValueError(
                    f"telemetry.extra에 민감 키를 넣을 수 없다: {key!r}"
                )

    @property
    def total_tokens(self) -> int | None:
        if self.input_tokens is None or self.output_tokens is None:
            return None
        return self.input_tokens + self.output_tokens

    def to_log_dict(self) -> dict[str, object]:
        """구조화 로그용 dict. 프롬프트·Key는 애초에 담지 않는다."""
        payload: dict[str, object] = {
            "operation": self.operation,
            "provider": self.provider,
            "model": self.model,
            "api_style": self.api_style,
            "reasoning_effort": self.reasoning_effort,
            "success": self.success,
            "latency_ms": self.latency_ms,
            "retry_count": self.retry_count,
            "item_count": self.item_count,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "validation_result": self.validation_result,
            "request_id": self.request_id,
        }
        if self.failure_kind:
            payload["failure_kind"] = self.failure_kind
        if self.theme_ids:
            payload["theme_ids"] = list(self.theme_ids)
        if self.period_keys:
            payload["period_keys"] = list(self.period_keys)
        payload.update(self.extra)
        return payload
