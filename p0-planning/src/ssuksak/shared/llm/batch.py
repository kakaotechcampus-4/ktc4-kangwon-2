"""Yearly Theme Batch 표현 Contract.

Rule이 12개월 Theme을 모두 확정한 뒤 **inference 요청 1회**로 12개 표현을
받는다. Elice의 비동기 Batch API가 아니라 일반 요청 하나에 12개를 담는 것이다.

LLM은 다음을 할 수 없다.
- 새 theme_id 생성 / 기존 theme_id 변경
- Month(period) 추가·삭제·중복
- 입력되지 않은 행사나 사실 추가
- Rule 후보 변경

`period_key`와 `theme_id`는 **검증용**이며 LLM의 자유 결정값이 아니다.
최종 Plan의 theme_id와 Evidence는 항상 Rule 결과에서 가져오고,
LLM 결과에서 콘텐츠로 쓰는 값은 `value` 하나뿐이다.

`period_key`를 응답에 포함하는 이유:
Theme 중복 정책(비인접 월의 동일 theme_id 허용)에 따라 두 기간이 같은
theme_id를 가질 수 있다. theme_id만으로 키를 잡으면 어느 기간의 값인지
판별할 수 없고 정당한 중복을 오탐한다. `period_key`는 구조상 유일하다.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Annotated, Mapping

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from .port import ThemePolishConstraints

__all__ = [
    "BatchReconcileError",
    "BatchViolation",
    "PolishedThemeOut",
    "ThemeBatchPolishItem",
    "ThemeBatchPolishRequest",
    "ThemeBatchPolishResponse",
    "reconcile_batch",
]

_PERIOD_KEY_PATTERN = r"^\d{4}-(0[1-9]|1[0-2])$"


def _non_blank(value: str) -> str:
    """공백만 있는 문자열을 거부한다. `min_length`만으로는 `"   "`가 통과한다."""
    if not value.strip():
        raise ValueError("공백 문자열은 허용되지 않는다")
    return value


NonBlankStr = Annotated[str, Field(strict=True), AfterValidator(_non_blank)]


# ------------------------------------------------------------------ 요청


@dataclass(frozen=True, slots=True)
class ThemeBatchPolishItem:
    """한 기간에 대해 Rule이 확정한 Theme 하나.

    후보 배열이 아니다. 이 타입에 후보 목록 필드가 없다는 점이 방어 1이다.
    """

    period_key: str
    theme_id: str
    label: str
    event_labels: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ThemeBatchPolishRequest:
    task: str
    school_year: int
    ages: tuple[int, ...]
    items: tuple[ThemeBatchPolishItem, ...]
    constraints: ThemePolishConstraints = ThemePolishConstraints()

    @property
    def expected(self) -> dict[str, str]:
        """period_key → theme_id (Rule이 확정한 기대값)."""
        return {item.period_key: item.theme_id for item in self.items}


# ------------------------------------------------------------------ 응답


class PolishedThemeOut(BaseModel):
    """Structured Output 항목 하나."""

    model_config = ConfigDict(extra="forbid")

    period_key: Annotated[str, Field(strict=True, pattern=_PERIOD_KEY_PATTERN)]
    theme_id: NonBlankStr
    value: NonBlankStr


class ThemeBatchPolishResponse(BaseModel):
    """Structured Output 전체.

    `extra="forbid"`가 스키마 밖 필드로 정책을 밀어 넣는 것을 막는다.
    """

    model_config = ConfigDict(extra="forbid")

    themes: Annotated[list[PolishedThemeOut], Field(min_length=1, max_length=12)]


# ------------------------------------------------------------- reconcile


class BatchViolation(str, Enum):
    """reconcile 실패 종류. Golden Set 내부 의미 식별자와 같은 성격이며
    공개 HTTP 오류 코드로 자동 승격하지 않는다."""

    MISSING_PERIOD = "llm_batch_must_cover_every_period"
    EXTRA_PERIOD = "llm_batch_must_not_add_periods"
    DUPLICATE_PERIOD = "llm_batch_must_not_duplicate_period"
    THEME_ID_MISMATCH = "llm_must_not_select_or_replace_theme"
    BLANK_VALUE = "theme_is_required_and_non_blank_for_every_period"


class BatchReconcileError(ValueError):
    """Batch 응답이 Rule 결정과 일치하지 않는 경우.

    부분 성공을 허용하지 않는다. 하나라도 어긋나면 전체 실패다
    (`GENERATION_PARTIAL` 미구현).
    """

    def __init__(
        self,
        violation: BatchViolation,
        detail: str = "",
        period_key: str | None = None,
    ) -> None:
        self.violation = violation
        self.detail = detail
        self.period_key = period_key
        where = f" [{period_key}]" if period_key else ""
        super().__init__(f"{violation.value}{where} {detail}".rstrip())


def reconcile_batch(
    response: ThemeBatchPolishResponse,
    expected: Mapping[str, str],
) -> dict[str, str]:
    """응답을 Rule 결정과 대조하고 `period_key → value` map을 만든다.

    Args:
        expected: period_key → theme_id. Rule이 확정한 기대값.

    Returns:
        period_key → 다듬어진 표현. **value만 반환한다** — theme_id는
        호출자가 Rule 결과에서 가져오므로 여기서 넘기지 않는다.

    Raises:
        BatchReconcileError: 누락·추가·중복·불일치·공백 중 하나라도 있을 때.
    """
    seen: dict[str, str] = {}

    for item in response.themes:
        if item.period_key in seen:
            raise BatchReconcileError(
                BatchViolation.DUPLICATE_PERIOD,
                f"period_key가 두 번 반환되었다",
                period_key=item.period_key,
            )

        if item.period_key not in expected:
            raise BatchReconcileError(
                BatchViolation.EXTRA_PERIOD,
                f"요청에 없는 기간이 반환되었다 (기대 {sorted(expected)})",
                period_key=item.period_key,
            )

        if item.theme_id != expected[item.period_key]:
            raise BatchReconcileError(
                BatchViolation.THEME_ID_MISMATCH,
                f"Rule 선택 {expected[item.period_key]} != LLM 반환 {item.theme_id}",
                period_key=item.period_key,
            )

        if not item.value.strip():
            raise BatchReconcileError(
                BatchViolation.BLANK_VALUE,
                "LLM이 공백 표현을 반환했다",
                period_key=item.period_key,
            )

        seen[item.period_key] = item.value

    missing = sorted(set(expected) - set(seen))
    if missing:
        raise BatchReconcileError(
            BatchViolation.MISSING_PERIOD,
            f"반환되지 않은 기간: {missing}",
        )

    return seen
