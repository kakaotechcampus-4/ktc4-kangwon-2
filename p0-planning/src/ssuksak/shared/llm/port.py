"""LLM Port와 Structured Output Contract.

CLAUDE.md §15·§16:
- LLM 공급자와 모델을 도메인 코드에 직접 박지 않는다.
- LLM 출력은 자유 텍스트가 아니라 구조화된 스키마로 받는다.
- LLM 출력 형식을 DB 모델과 직접 결합하지 말고 Application Contract를 사이에 둔다.
- LLM은 Rule에서 선택된 theme_id를 입력으로 받아 의미를 유지한 표현만 생성한다.

theme_id 교체를 막는 방어는 4중이다.
1. 후보 목록을 LLM에 전달하지 않는다 — 선택할 대상이 애초에 없다.
2. 반환 theme_id가 Rule의 선택과 다르면 거부한다.
3. Plan Item의 theme_id와 Evidence는 Rule 결과에서 세팅하고 LLM 응답에서 읽지 않는다.
4. 최종 Validation이 모든 theme_id를 활성 Catalog에서 다시 resolve한다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from pydantic import BaseModel, Field, ValidationError

__all__ = [
    "LLMConfigurationError",
    "LLMPort",
    "LLMUnavailableError",
    "ThemePolishConstraints",
    "ThemePolishRequest",
    "ThemePolishResponse",
    "parse_theme_polish_response",
]


class LLMUnavailableError(RuntimeError):
    """재시도 후에도 LLM 호출이 실패한 경우.

    docs/open-decisions.md OD-N04: 재시도 후 실패를 잘못된 Plan 성공으로
    처리하지 않는다. 따라서 조용한 degrade가 아니라 예외로 전파한다.

    Optional Context(Trend/Weather) 실패와 **다른 경로**다. Optional 실패는
    결과 객체로 표현되어 Core가 성공하지만, 필수 LLM 실패는 여기서 예외가 되어
    Plan이 저장되지 않는다.
    """

    def __init__(self, message: str, *, kind: str = "UNAVAILABLE") -> None:
        self.kind = kind
        super().__init__(message)


class LLMConfigurationError(RuntimeError):
    """인증 실패·권한 오류·잘못된 요청처럼 재시도가 무의미한 설정 오류.

    운영자가 고쳐야 하는 문제이므로 재시도하지 않고 즉시 전파한다.
    Application은 이를 `LLM_CONFIG_ERROR`로 분류한다.
    """

    def __init__(self, message: str, *, kind: str = "CONFIG") -> None:
        self.kind = kind
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class ThemePolishConstraints:
    """표현 다듬기 제약.

    `max_chars`는 현재 Source of Truth에서 확정되지 않았으므로 기본값을 두지 않고
    None으로 격리한다. 설정으로 주입할 수 있으나 어디에서도 하드코딩하지 않는다.
    """

    must_preserve_meaning_of_label: bool = True
    must_not_introduce_facts_or_events: bool = True
    max_chars: int | None = None


@dataclass(frozen=True, slots=True)
class ThemePolishRequest:
    """LLM에 전달하는 입력.

    후보 배열이 아니라 **Rule이 이미 선택한 단 하나의 Theme**만 담는다.
    """

    task: str
    selected_theme_id: str
    selected_theme_label: str
    period_key: str
    ages: tuple[int, ...]
    event_labels: tuple[str, ...] = ()
    constraints: ThemePolishConstraints = ThemePolishConstraints()


class ThemePolishResponse(BaseModel):
    """LLM Structured Output 스키마.

    `theme_id`를 함께 받지만 이것은 **검증용**이다. Plan Item에 반영되는
    theme_id와 Evidence는 Rule 결과에서 세팅한다.
    """

    model_config = {"extra": "forbid"}

    theme_id: str = Field(min_length=1)
    value: str = Field(min_length=1)


def parse_theme_polish_response(raw: object) -> ThemePolishResponse:
    """LLM 원시 출력을 스키마로 검증한다.

    CLAUDE.md §14: LLM 출력은 신뢰하지 않고 Application 경계에서 검증한다.
    """
    try:
        if isinstance(raw, ThemePolishResponse):
            return raw
        if isinstance(raw, dict):
            return ThemePolishResponse.model_validate(raw)
        return ThemePolishResponse.model_validate_json(str(raw))
    except ValidationError as exc:
        raise ValueError(f"LLM Structured Output 스키마 위반: {exc}") from exc


class LLMPort(Protocol):
    """공급자 중립 인터페이스.

    구현체는 timeout / retry / token 측정 / logging을 자신의 경계 안에서 처리한다
    (CLAUDE.md §16). 도메인은 이 Protocol만 안다.

    Provider·모델·SDK는 이 Protocol 뒤에 완전히 격리된다. Domain과 Application은
    `openai`·`anthropic`·Elice 중 무엇도 import하지 않으며, 같은 Contract로
    여러 모델을 교체·비교할 수 있다.
    """

    def polish_theme(self, request: ThemePolishRequest) -> ThemePolishResponse:
        """선택된 Theme 하나의 표현을 다듬어 반환한다.

        RegenerateYearlyPlanItem이 사용하는 단건 경로다.

        Raises:
            LLMUnavailableError: 재시도 후에도 실패한 경우.
            LLMConfigurationError: 인증·권한·요청 형식 오류.
            ValueError: 출력이 스키마를 위반한 경우.
        """
        ...

    def polish_themes(self, request):
        """여러 Theme 표현을 **요청 1회**로 받는다.

        GenerateYearlyPlan이 12개월을 한 번에 처리하는 경로다.
        `request`는 `batch.ThemeBatchPolishRequest`,
        반환은 `batch.ThemeBatchPolishResponse`다.
        (순환 import를 피하려 여기서는 타입을 명시하지 않는다.)

        Raises:
            LLMUnavailableError: 재시도 후에도 실패한 경우.
            LLMConfigurationError: 인증·권한·요청 형식 오류.
            ValueError: 출력이 스키마를 위반한 경우.
        """
        ...

    def plan_monthly(self, request):
        """한 달 전체 바깥놀이 흐름을 **요청 1회**로 구성한다 (L4).

        `polish_*`와 역할이 다르다. 저쪽은 Rule이 고른 값의 표현만 바꾸지만,
        이쪽은 주차 배치와 활동 선택을 LLM이 구성한다. 그래도 경계는 같다 —
        `theme_id`와 `week_id`는 입력이며 LLM이 만들지 않는다.

        `request`는 `monthly.MonthlyPlannerRequest`,
        반환은 `monthly.MonthlyPlanProposal`이다.
        (순환 import를 피하려 여기서는 타입을 명시하지 않는다.)

        구현체는 반환 전에 `monthly.reconcile_monthly_proposal()`로 Theme /
        Week / Origin 계약을 대조한다. 완전한 Deterministic Validator는 L5다.

        **실패 시 빈 Proposal이나 Rule-only 결과를 대신 돌려주지 않는다**
        (OD-N15 silent fallback 금지). 호출자에게 예외로 전파한다.

        Raises:
            LLMUnavailableError: 재시도 후에도 실패한 경우.
            LLMConfigurationError: 인증·권한·요청 형식 오류.
            ValueError: 출력이 스키마나 Packet Contract를 위반한 경우.
        """
        ...

    def regenerate_monthly_cell(self, request):
        """Monthly Cell **하나**만 다시 쓴다 (L7).

        `plan_monthly`와 역할이 다르다. 저쪽은 한 달 전체를 구성하고, 이쪽은
        이미 있는 계획에서 Target Cell 하나만 바꾼다. 한 달을 다시 만든 뒤
        Target만 꺼내 쓰지 않는다 — 쓰지 않을 값을 만드는 비용과 그 값이 기존
        Plan과 어긋났을 때의 검증 복잡성을 피한다.

        `request`는 `monthly_cell.MonthlyCellRegenerationRequest`,
        반환은 `monthly_cell.MonthlyCellRegenerationProposal`이다.

        구현체는 반환 전에 `monthly_cell.reconcile_cell_proposal()`로 Target
        주차·Section과 Activity 계약을 대조한다.

        **실패 시 기존 Cell 값을 그대로 돌려주거나 Rule 결과로 대체하지 않는다.**

        Raises:
            LLMUnavailableError: 재시도 후에도 실패한 경우.
            LLMConfigurationError: 인증·권한·요청 형식 오류.
            ValueError: 출력이 스키마나 Cell Contract를 위반한 경우.
        """
        ...
