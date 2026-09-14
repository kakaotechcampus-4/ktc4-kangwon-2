"""Constraint 검증 상태와 Cell 충족 상태.

docs/open-decisions.md OD-M04 (`RESOLVED_FOR_P0`) / 2026-09-11 승인:

안전교육 Section이 활성인데 기관 안전교육 연간계획·교사 입력 source가 없으면
임의 배치도, LLM 생성도, 법적 충족 주장도 하지 않는다. 구조는 존재하되 값이
비어 있을 수 있고 `법정 요건 미검증 / source required` 상태를 표현해야 한다.

**이것은 다음 어느 것도 아니다.**

    Optional Context 실패      OptionalContextStatus — 외부 의존성 조회 결과
    fallback                   대체재를 썼다는 뜻. 여기서는 대체재를 쓰지 않는 것이 결정
    generation failure         OD-M04가 구조 존재를 요구하므로 실패가 아님
    PlanStatus                 DRAFT/CONFIRMED는 작성 단계이며 이 축과 직교
    Human approval status      데이터 파일의 승인 상태. Plan 인스턴스 상태가 아님

별도의 **unresolved requirement**다.

`CellState`를 이 모듈에 둔 이유: `EMPTY_UNRESOLVED`는 단순히 "비었다"가 아니라
"Constraint가 해결되지 않아 비었다"를 뜻하므로 Constraint 개념과 한 묶음이다.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ConstraintKind(str, Enum):
    """검증 대상 Constraint 종류.

    M1 편의를 위한 speculative value를 추가하지 않는다.
    """

    STATUTORY_SAFETY_EDUCATION = "STATUTORY_SAFETY_EDUCATION"


class ConstraintVerification(str, Enum):
    """Constraint 검증 결과.

    `NOT_VERIFIED_SOURCE_REQUIRED`는 실패가 아니라 **미검증**이다. Plan은 이
    상태로도 생성·저장·확정될 수 있다(OD-M01: 값이 없다는 사실만으로 생성·저장·
    확정을 차단하지 않는다).
    """

    VERIFIED = "VERIFIED"
    NOT_VERIFIED_SOURCE_REQUIRED = "NOT_VERIFIED_SOURCE_REQUIRED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class CellState(str, Enum):
    """Cell 값의 충족 상태.

    FILLED            값이 있다
    EMPTY_VALID       채울 근거가 없는 것이 정상이다. 알릴 것이 없다
    EMPTY_UNRESOLVED  채워야 하는데 source가 없다. 해결 방법을 안내해야 한다
    """

    FILLED = "FILLED"
    EMPTY_VALID = "EMPTY_VALID"
    EMPTY_UNRESOLVED = "EMPTY_UNRESOLVED"

    @property
    def is_empty(self) -> bool:
        return self is not CellState.FILLED


@dataclass(frozen=True, slots=True)
class ConstraintAssessment:
    """Plan 수준의 Constraint 검증 결과. 사용자에게 보여줄 정본이다.

    Confirm 이후에도 **보존된다**. Confirm은 법적 충족을 주장하지 않으며
    이 값을 VERIFIED로 바꾸지 않는다(2026-09-11 Product Contract).

        CONFIRMED  = 교사가 Monthly Plan 작성 상태를 확정함
        CONFIRMED != 법정 안전교육 요건 충족 확인
    """

    kind: ConstraintKind
    verification: ConstraintVerification
    rule_version: str
    """근거 Rule 데이터의 version. 예: legal_rule_version."""
    required_source_kinds: tuple[str, ...] = ()
    """이 Constraint를 해결하려면 필요한 source 종류."""
    affected_section_keys: tuple[str, ...] = ()
    detail: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.rule_version, str) or not self.rule_version.strip():
            raise ValueError("ConstraintAssessment.rule_version은 비어 있을 수 없다")
        if (
            self.verification is ConstraintVerification.NOT_VERIFIED_SOURCE_REQUIRED
            and not self.required_source_kinds
        ):
            raise ValueError(
                "NOT_VERIFIED_SOURCE_REQUIRED는 required_source_kinds를 명시해야 한다. "
                "사용자에게 해결 방법을 안내할 수 없는 미검증 상태를 만들지 않는다."
            )

    @property
    def is_unresolved(self) -> bool:
        return self.verification is ConstraintVerification.NOT_VERIFIED_SOURCE_REQUIRED
