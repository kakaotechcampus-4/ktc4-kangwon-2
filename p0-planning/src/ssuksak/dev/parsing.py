"""Harness 입력 파싱. 모두 순수 함수이며 I/O를 하지 않는다.

검증 규칙을 새로 만들지 않는다. 지원 연령은 Rule 계층의 `SUPPORTED_AGES`를,
학년도 기간은 `expected_period_key_values`를, 의미 주소는
`SemanticKey.yearly_month_theme`을 그대로 쓴다.
"""

from __future__ import annotations

import re

from ..planning.application.dto import AgeMode
from ..planning.domain.identifiers import SemanticKey
from ..planning.rules.gates import SUPPORTED_AGES
from ..planning.rules.periods import expected_period_key_values

__all__ = [
    "HarnessInputError",
    "parse_age_mode",
    "parse_ages",
    "parse_menu_choice",
    "parse_period_key",
    "parse_school_year",
    "semantic_key_for_period",
]

_PERIOD_RE = re.compile(r"^(\d{4})-(\d{1,2})$")


class HarnessInputError(ValueError):
    """사용자 입력이 잘못된 경우. 재입력을 요청하는 데 쓴다."""


def parse_school_year(raw: str, *, default: int | None = None) -> int:
    """학년도를 읽는다. 빈 입력은 default가 있을 때만 허용한다."""
    text = (raw or "").strip()
    if not text:
        if default is not None:
            return default
        raise HarnessInputError("학년도를 입력하세요.")
    if not text.isdigit():
        raise HarnessInputError(f"학년도는 숫자여야 합니다: {text!r}")
    year = int(text)
    if not 2000 <= year <= 2100:
        raise HarnessInputError(f"학년도가 범위를 벗어났습니다: {year}")
    return year


def parse_ages(raw: str) -> frozenset[int]:
    """`3` · `3,4` · `3, 4, 5` 형태를 연령 집합으로 읽는다.

    지원 연령은 Rule 계층의 SUPPORTED_AGES를 그대로 따른다.
    """
    text = (raw or "").strip()
    if not text:
        raise HarnessInputError("연령을 입력하세요. 예: 3 또는 3,4")

    tokens = [t.strip() for t in text.replace(" ", ",").split(",") if t.strip()]
    if not tokens:
        raise HarnessInputError("연령을 입력하세요. 예: 3 또는 3,4")

    ages: set[int] = set()
    for token in tokens:
        if not token.isdigit():
            raise HarnessInputError(f"연령은 숫자여야 합니다: {token!r}")
        ages.add(int(token))

    unsupported = sorted(ages - SUPPORTED_AGES)
    if unsupported:
        raise HarnessInputError(
            f"P0 지원 연령은 {sorted(SUPPORTED_AGES)}입니다. "
            f"지원하지 않는 값: {unsupported}"
        )
    return frozenset(ages)


def parse_age_mode(raw: str, ages: frozenset[int]) -> AgeMode | None:
    """`SINGLE` / `MIXED`를 읽는다. 빈 입력은 None(연령 개수에서 파생)이다.

    모드와 연령 개수가 모순이면 여기서 막는다. 같은 규칙을 Rule 계층도
    검증하지만, 사용자가 재입력할 수 있게 미리 알려 주는 편이 낫다.
    """
    text = (raw or "").strip().upper()
    if not text:
        return None
    if text not in (AgeMode.SINGLE.value, AgeMode.MIXED.value):
        raise HarnessInputError(
            f"모드는 SINGLE 또는 MIXED여야 합니다: {raw.strip()!r}"
        )

    mode = AgeMode(text)
    if mode is AgeMode.MIXED and len(ages) < 2:
        raise HarnessInputError(
            f"MIXED는 서로 다른 연령 2개 이상이 필요합니다. 현재: {sorted(ages)}"
        )
    if mode is AgeMode.SINGLE and len(ages) != 1:
        raise HarnessInputError(
            f"SINGLE은 연령이 정확히 1개여야 합니다. 현재: {sorted(ages)}"
        )
    return mode


def parse_period_key(raw: str, school_year: int) -> str:
    """`4` · `04` · `2026-04` 를 학년도의 period_key로 정규화한다.

    학년도 12기간은 Rule 계층에서 가져오므로 1·2월의 연도 처리를 중복 구현하지
    않는다.
    """
    text = (raw or "").strip()
    if not text:
        raise HarnessInputError("월을 입력하세요. 예: 4 또는 2026-04")

    valid = expected_period_key_values(school_year)

    matched = _PERIOD_RE.match(text)
    if matched:
        year, month = int(matched.group(1)), int(matched.group(2))
        candidate = f"{year:04d}-{month:02d}"
        if candidate not in valid:
            raise HarnessInputError(
                f"{candidate}는 {school_year} 학년도에 속하지 않습니다. "
                f"({valid[0]} ~ {valid[-1]})"
            )
        return candidate

    if not text.isdigit():
        raise HarnessInputError(f"월을 숫자로 입력하세요: {text!r}")

    month = int(text)
    if not 1 <= month <= 12:
        raise HarnessInputError(f"월은 1~12여야 합니다: {month}")

    for key in valid:
        if int(key[5:7]) == month:
            return key
    raise HarnessInputError(f"{month}월을 찾을 수 없습니다.")


def semantic_key_for_period(period_key: str) -> str:
    """period_key에 대응하는 theme Item의 의미 주소."""
    return SemanticKey.yearly_month_theme(int(period_key[5:7])).value


def parse_menu_choice(raw: str, allowed: tuple[str, ...]) -> str:
    """메뉴 번호를 읽는다."""
    text = (raw or "").strip()
    if not text:
        raise HarnessInputError("메뉴 번호를 입력하세요.")
    if text not in allowed:
        raise HarnessInputError(
            f"없는 메뉴입니다: {text!r} (가능: {', '.join(allowed)})"
        )
    return text
