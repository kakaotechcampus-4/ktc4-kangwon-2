"""Provenance 3축.

CLAUDE.md §13 / docs/screen-spec.md §6 / docs/demo-source-of-truth.md §22:

    1. Evidence Source    — 내용의 근거
    2. Generation Method  — 생성 방식
    3. Audit History      — 생성 이후의 변경

세 축을 하나의 Enum으로 합치지 않는다.
`AI`와 `TEACHER_EDIT`은 Evidence Source가 아니다. 이 모듈에는 두 리터럴이
EvidenceSourceType으로 존재하지 않으므로 screen-spec §20-3·§20-4 위반을
값으로 만들어 낼 수 없다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from .identifiers import ActorId

# ---------------------------------------------------------------- 1축: Evidence


class EvidenceSourceType(str, Enum):
    """docs/screen-spec.md §6.1의 Evidence Source 목록.

    의도적으로 `AI`와 `TEACHER_EDIT`을 포함하지 않는다.
    LLM 사용 여부는 GenerationMethod, 교사 수정은 AuditEvent로 표현한다.
    """

    CURRICULUM = "CURRICULUM"
    THEME_REFERENCE = "THEME_REFERENCE"
    PARENT_PLAN = "PARENT_PLAN"
    DAYCARE_PROFILE = "DAYCARE_PROFILE"
    CLASSROOM_PROFILE = "CLASSROOM_PROFILE"
    EVENT = "EVENT"
    SAFETY_RULE = "SAFETY_RULE"
    ACTIVITY_REFERENCE = "ACTIVITY_REFERENCE"
    INSTITUTION_SAMPLE = "INSTITUTION_SAMPLE"
    """실제 기관 계획안 Corpus에서 관찰된 Source (OD-N13, 2026-09-13 승인).

    `ACTIVITY_REFERENCE`를 대체하지 않는다. 승인 Catalog에서 고른 값은 계속
    `ACTIVITY_REFERENCE`다. LLM이 근거를 참고해 새로 구성한 Activity가
    실제로 어떤 Corpus record를 Grounding했는지 기록할 때 쓴다.

    **`LLM_SYNTHESIZED`는 Evidence Source Type이 아니다.** 생성 방식은
    `GenerationMethod.RULE_LLM`이, Activity 출처 구분은 activity_origin이
    표현한다 — 세 축은 독립이다(CLAUDE.md §13).
    """

    CALENDAR = "CALENDAR"
    TREND = "TREND"
    EXTERNAL_CONTEXT = "EXTERNAL_CONTEXT"


@dataclass(frozen=True, slots=True)
class EvidenceSource:
    """Item이 실제로 참조한 근거 하나.

    `source_id`는 Item이 참조한 Evidence record의 canonical 식별자다.
    Theme Reference Item이면 `source_id = theme_id`이고
    `source_version = 활성 catalog_version`이다(CLAUDE.md §8).

    `origin_id`는 여기 넣지 않는다. upstream lineage는 Theme Reference record가
    보존하며 Evidence의 canonical source_id를 대신하지 않는다.
    """

    source_type: EvidenceSourceType
    source_id: str
    source_version: str | None = None
    effective_date: str | None = None
    display_name: str | None = None

    def __post_init__(self) -> None:
        if not self.source_id or not self.source_id.strip():
            raise ValueError("EvidenceSource.source_id는 필수다")


# ------------------------------------------------------- 2축: Generation Method


class GenerationMethod(str, Enum):
    """Item의 **현재 값**이 만들어진 방식(docs/screen-spec.md §6.1)."""

    RULE_ONLY = "RULE_ONLY"
    RULE_LLM = "RULE_LLM"
    IMPORTED = "IMPORTED"
    MANUAL = "MANUAL"


@dataclass(frozen=True, slots=True)
class GenerationMethodDetail:
    """Generation Method와 그 상세 metadata.

    적용된 Rule의 rule_id / rule_version은 여기 기록하며
    Evidence Source에 넣지 않는다(CLAUDE.md §13.2).
    """

    method: GenerationMethod
    rule_id: str | None = None
    rule_version: str | None = None
    selection_reason: str | None = None

    def __post_init__(self) -> None:
        if self.method in (GenerationMethod.RULE_ONLY, GenerationMethod.RULE_LLM):
            if not self.rule_id or not self.rule_version:
                raise ValueError(
                    "RULE_ONLY / RULE_LLM은 rule_id와 rule_version을 상세로 가져야 한다"
                )


# --------------------------------------------------------- 3축: Audit History


class AuditEventType(str, Enum):
    CREATED = "CREATED"
    REGENERATED = "REGENERATED"
    TEACHER_EDITED = "TEACHER_EDITED"
    CONFIRMED = "CONFIRMED"


SYSTEM_ACTOR_MARKER = "SYSTEM"


@dataclass(frozen=True, slots=True)
class AuditEvent:
    """생성 이후의 변경 하나.

    docs/screen-spec.md §9: 최소 event_type, occurred_at, plan_id, 선택적 item_id,
    그리고 사람의 opaque actor_id 또는 시스템 행위자 Marker를 가진다.
    """

    event_type: AuditEventType
    occurred_at: datetime
    plan_id: str
    item_id: str | None = None
    actor_id: ActorId | None = None
    system_actor: str | None = None
    previous_value: str | None = None
    new_value: str | None = None
    previous_method: GenerationMethod | None = None
    new_method: GenerationMethod | None = None

    def __post_init__(self) -> None:
        if self.actor_id is None and self.system_actor is None:
            raise ValueError("AuditEvent는 opaque actor_id 또는 system_actor를 가져야 한다")
        # 표시 이름 문자열이 actor로 기록되는 것을 런타임에서도 막는다.
        # 타입 힌트만으로는 강제되지 않으므로 여기서 확인한다(OD-Y03).
        if self.actor_id is not None and not isinstance(self.actor_id, ActorId):
            raise TypeError(
                "AuditEvent.actor_id는 ActorId여야 한다. "
                f"담임 표시 이름 등 원시 문자열은 사용할 수 없다: {self.actor_id!r}"
            )

    @property
    def actor_display(self) -> str:
        return str(self.actor_id) if self.actor_id else (self.system_actor or SYSTEM_ACTOR_MARKER)


@dataclass(slots=True)
class AuditTrail:
    """발생 순서를 보존하는 ordered AuditEvent[]."""

    events: list[AuditEvent] = field(default_factory=list)

    def append(self, event: AuditEvent) -> None:
        self.events.append(event)

    def types(self) -> list[AuditEventType]:
        return [e.event_type for e in self.events]

    def contains(self, event_type: AuditEventType) -> bool:
        return any(e.event_type is event_type for e in self.events)

    def __iter__(self):
        return iter(self.events)

    def __len__(self) -> int:
        return len(self.events)
