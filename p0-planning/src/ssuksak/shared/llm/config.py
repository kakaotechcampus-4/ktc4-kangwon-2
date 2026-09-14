"""LLM Provider 설정 경계.

CLAUDE.md §16 / OD-N04: Provider와 모델을 도메인 코드에 직접 박지 않는다.
환경변수를 읽는 곳은 이 모듈뿐이다.

**API Key는 이 객체의 `__repr__`/로그에 나타나지 않는다.**
`ELICE_MLAPI_API_KEY`는 Adapter가 SDK client를 만들 때만 사용하고,
telemetry·예외 메시지·테스트 Fixture에 남기지 않는다.

**모델은 코드 기본값을 두지 않는다.**
`LLM_MODEL`은 필수 환경변수다. MLAPI는 GPT-5.6 Terra/Sol/Luna, GPT-5.4,
GPT-5.2, GPT-5.1, GPT-5 mini, GPT-4.1 계열, Claude Sonnet 5 등을 제공하며
P0 최종 모델은 Adapter 완성 후 동일 입력 비교로 결정한다. 따라서 어떤
모델 문자열도 코드에 확정하지 않는다.

**`.env` 로딩 범위**
`from_env()`를 인자 없이 부르는 실제 환경 경로에서만 프로젝트 루트의 `.env`를
로드한다. `from_env(env=<dict>)`처럼 명시적으로 env를 넘기면 `.env`를 읽지
않는다 — 테스트 결과가 개발자 로컬 `.env`에 영향받으면 안 되기 때문이다.
`.env`는 이미 설정된 OS 환경변수를 덮어쓰지 않는다(`override=False`).
기존 이름(`PROXY_TOKEN`, `CHAT_PROXY_URL`, `OPENAI_MODEL`)에 대한 alias는
두지 않는다. 쓱싹요정은 아래 이름 하나로 통일한다.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

__all__ = [
    "DOTENV_PATH",
    "PROJECT_ROOT",
    "LLMApiStyle",
    "LLMConfig",
    "LLMConfigError",
    "REASONING_EFFORT_VALUES",
    "load_project_dotenv",
]

PROJECT_ROOT = Path(__file__).resolve().parents[4]
"""저장소 루트. `src/ssuksak/shared/llm/config.py` 기준 4단계 위."""

DOTENV_PATH = PROJECT_ROOT / ".env"
"""로컬 개발용 `.env` 경로. 커밋하지 않는다."""


def load_project_dotenv() -> bool:
    """프로젝트 루트의 `.env`를 Process 환경으로 로드한다.

    **`override=False`**: 이미 설정된 OS 환경변수를 `.env`가 덮어쓰지 않는다.
    CI나 배포에서 명시적으로 주입한 값이 로컬 파일에 밀리면 안 되기 때문이다.

    Returns:
        `.env` 파일이 실제로 존재해 로드를 시도했는지.
    """
    if not DOTENV_PATH.is_file():
        return False
    try:
        from dotenv import load_dotenv
    except ImportError:  # pragma: no cover - 의존성 미설치 환경
        return False
    load_dotenv(DOTENV_PATH, override=False)
    return True


class LLMConfigError(RuntimeError):
    """필수 LLM 설정이 없거나 형식이 잘못된 경우."""


class LLMApiStyle(str, Enum):
    """Elice MLAPI가 제공하는 OpenAI-compatible 요청 방식.

    두 방식을 모두 지원하는 이유는 문서와 실제 endpoint 동작이 다를 때
    코드 수정 없이 확인·비교할 수 있어야 하기 때문이다(모델 A/B 목적과 동일).
    추측으로 우회하는 것이 아니라 명시적 설정으로 전환한다.
    """

    RESPONSES = "responses"
    CHAT_COMPLETIONS = "chat_completions"


REASONING_EFFORT_VALUES = ("minimal", "low", "medium", "high")
"""reasoning effort 허용값.

P0 초기값은 `low`이며 provisional이다. Domain Rule로 하드코딩하지 않는다.
모델에 따라 reasoning을 지원하지 않을 수 있으므로 None도 허용한다.
"""

_PROVISIONAL_REASONING_EFFORT = "low"


@dataclass(frozen=True, slots=True)
class LLMConfig:
    """Elice MLAPI 호출에 필요한 설정.

    `api_key`는 `repr`에 노출되지 않도록 별도 취급한다.
    """

    base_url: str
    model: str
    timeout_seconds: float
    max_retries: int
    api_key: str = field(repr=False, default="")
    reasoning_effort: str | None = _PROVISIONAL_REASONING_EFFORT
    api_style: LLMApiStyle = LLMApiStyle.RESPONSES
    max_output_tokens: int | None = None

    def __post_init__(self) -> None:
        if not self.base_url.strip():
            raise LLMConfigError("ELICE_MLAPI_BASE_URL이 비어 있다")
        if not self.model.strip():
            raise LLMConfigError("LLM_MODEL이 비어 있다")
        if not self.api_key.strip():
            raise LLMConfigError("ELICE_MLAPI_API_KEY가 비어 있다")
        if self.timeout_seconds <= 0:
            raise LLMConfigError(
                f"LLM_TIMEOUT_SECONDS는 양수여야 한다: {self.timeout_seconds}"
            )
        if self.max_retries < 0:
            raise LLMConfigError(f"LLM_MAX_RETRIES는 0 이상이어야 한다: {self.max_retries}")
        if (
            self.reasoning_effort is not None
            and self.reasoning_effort not in REASONING_EFFORT_VALUES
        ):
            raise LLMConfigError(
                f"LLM_REASONING_EFFORT는 {REASONING_EFFORT_VALUES} 중 하나여야 한다: "
                f"{self.reasoning_effort!r}"
            )

    # ------------------------------------------------------------ 노출 안전

    @property
    def safe_summary(self) -> dict[str, object]:
        """telemetry·로그에 남겨도 되는 요약. API Key를 포함하지 않는다."""
        return {
            "base_url": self.base_url,
            "model": self.model,
            "api_style": self.api_style.value,
            "timeout_seconds": self.timeout_seconds,
            "max_retries": self.max_retries,
            "reasoning_effort": self.reasoning_effort,
        }

    def __str__(self) -> str:
        return f"LLMConfig({self.safe_summary})"

    # ------------------------------------------------------------ env 로딩

    @staticmethod
    def from_env(env: dict[str, str] | None = None) -> "LLMConfig":
        """환경변수에서 설정을 읽는다. 누락은 조용히 보정하지 않고 실패한다.

        timeout/retry 수치는 아직 제품 결정이 없으므로 **코드 기본값을 두지 않는다**.
        미설정이면 명확한 메시지로 실패해 배포 설정에서 값이 정해지도록 한다.

        Args:
            env: 명시하면 그 dict만 읽고 **`.env`를 로드하지 않는다**. 테스트
                결과가 개발자 로컬 `.env`에 영향받지 않게 하는 지점이다.
                None이면 실제 환경 경로로 보고 프로젝트 `.env`를 먼저 로드한 뒤
                `os.environ`을 읽는다.
        """
        if env is not None:
            source = dict(env)
        else:
            load_project_dotenv()
            source = dict(os.environ)

        base_url = _require(source, "ELICE_MLAPI_BASE_URL")
        api_key = _require(source, "ELICE_MLAPI_API_KEY")
        model = _require(source, "LLM_MODEL")

        timeout_raw = _require(source, "LLM_TIMEOUT_SECONDS")
        try:
            timeout_seconds = float(timeout_raw)
        except ValueError as exc:
            raise LLMConfigError(
                f"LLM_TIMEOUT_SECONDS를 숫자로 읽을 수 없다: {timeout_raw!r}"
            ) from exc

        retries_raw = _require(source, "LLM_MAX_RETRIES")
        try:
            max_retries = int(retries_raw)
        except ValueError as exc:
            raise LLMConfigError(
                f"LLM_MAX_RETRIES를 정수로 읽을 수 없다: {retries_raw!r}"
            ) from exc

        effort = source.get("LLM_REASONING_EFFORT", _PROVISIONAL_REASONING_EFFORT)
        effort_value: str | None = None if effort.strip().lower() == "none" else effort

        style_raw = source.get("LLM_API_STYLE", LLMApiStyle.RESPONSES.value)
        try:
            api_style = LLMApiStyle(style_raw)
        except ValueError as exc:
            raise LLMConfigError(
                f"LLM_API_STYLE은 {[s.value for s in LLMApiStyle]} 중 하나여야 한다: "
                f"{style_raw!r}"
            ) from exc

        max_output_raw = source.get("LLM_MAX_OUTPUT_TOKENS")
        max_output_tokens: int | None = None
        if max_output_raw:
            try:
                max_output_tokens = int(max_output_raw)
            except ValueError as exc:
                raise LLMConfigError(
                    f"LLM_MAX_OUTPUT_TOKENS를 정수로 읽을 수 없다: {max_output_raw!r}"
                ) from exc

        return LLMConfig(
            base_url=base_url,
            model=model,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
            api_key=api_key,
            reasoning_effort=effort_value,
            api_style=api_style,
            max_output_tokens=max_output_tokens,
        )


def _require(source: dict[str, str], key: str) -> str:
    value = source.get(key, "")
    if not value.strip():
        raise LLMConfigError(
            f"필수 환경변수 {key}가 설정되지 않았다. "
            f"LLM Adapter는 설정 누락을 기본값으로 보정하지 않는다."
        )
    return value
