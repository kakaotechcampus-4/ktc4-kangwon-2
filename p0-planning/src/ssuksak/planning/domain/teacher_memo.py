"""교사가 생성 전에 적은 「요청 사항」의 domain 값(ADR-057).

메모를 반영한 칸은 Evidence 하나를 더 갖는다. 칸마다 받는 Evidence 종류를 정해 둔 domain 검사는
이 Evidence 하나만 예외로 받는다 — 근거 종류를 넓히는 것이 아니라 「교사가 요청했다」는 표시다.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .errors import InvalidDomainValueError
from .provenance import EvidenceSource, EvidenceSourceType

MEMO_NOTICE_MAX_LENGTH = 80

# 「반에 대한 교사 입력」이라 12종 중 CLASSROOM_PROFILE 이 가장 가깝다.
TEACHER_MEMO_EVIDENCE = EvidenceSource(
    EvidenceSourceType.CLASSROOM_PROFILE, "teacher_memo", display_name="요청 사항"
)


def without_memo_evidence(evidence: tuple[EvidenceSource, ...]) -> tuple[EvidenceSource, ...]:
    """칸별 근거 종류 검사가 볼 Evidence: 요청 사항 표시는 뺀다."""
    return tuple(source for source in evidence if source != TEACHER_MEMO_EVIDENCE)


class MemoNoticeReason(str, Enum):
    OUT_OF_RANGE = "OUT_OF_RANGE"  # 승인 후보 · 근거 밖을 요구했다
    RULE_CONFLICT = "RULE_CONFLICT"  # 안전교육 · 법정 기준 · 칸 구조와 부딪힌다
    FIXED_CELL = "FIXED_CELL"  # Rule 이 복사하는 칸(상위 계획 주제 · 주간 안전교육 등)


@dataclass(frozen=True, slots=True)
class MemoNotice:
    """반영하지 못한 요청 하나: 짧은 요약과 까닭. 생성을 막지 않는다."""

    summary: str
    reason: MemoNoticeReason

    def __post_init__(self) -> None:
        if not isinstance(self.summary, str) or not self.summary.strip():
            raise InvalidDomainValueError("MemoNotice.summary must be non-blank")
        if len(self.summary) > MEMO_NOTICE_MAX_LENGTH:
            raise InvalidDomainValueError("MemoNotice.summary is too long")
        if not isinstance(self.reason, MemoNoticeReason):
            raise InvalidDomainValueError("MemoNotice.reason is invalid")


def require_memo_fields(owner: str, memo: object, notices: object) -> None:
    """계획안 다섯 종류가 함께 쓰는 검사: 메모 원문과 반영 못한 요청."""
    if not isinstance(memo, str):
        raise InvalidDomainValueError(f"{owner}.teacher_memo must be a string")
    if not isinstance(notices, tuple) or not all(isinstance(n, MemoNotice) for n in notices):
        raise InvalidDomainValueError(f"{owner}.memo_notices must be MemoNotice values")
    if notices and not memo:
        raise InvalidDomainValueError(f"{owner}.memo_notices need a teacher_memo")


@dataclass(frozen=True, slots=True)
class SafetyRequest:
    """메모에서 LLM 이 뽑은 법정 안전교육 요청 하나(ADR-057 2층). 배치는 Rule 이 한다.

    ``weeks`` = 교사가 짚은 주(week_id 문자열), ``min_weeks`` = 바라는 최소 주 수(0 = 개수 요청 없음).
    """

    slot: str
    weeks: tuple[str, ...]
    min_weeks: int

    def __post_init__(self) -> None:
        if not isinstance(self.slot, str) or not self.slot.strip():
            raise InvalidDomainValueError("SafetyRequest.slot must be non-blank")
        if not isinstance(self.weeks, tuple) or not all(isinstance(w, str) for w in self.weeks):
            raise InvalidDomainValueError("SafetyRequest.weeks must be week id strings")
        if type(self.min_weeks) is not int or self.min_weeks < 0:
            raise InvalidDomainValueError("SafetyRequest.min_weeks must be a non-negative int")

    @property
    def count(self) -> int:
        return max(self.min_weeks, len(self.weeks))
