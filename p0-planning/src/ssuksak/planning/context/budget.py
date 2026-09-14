"""Context Budget 측정과 결정론적 Trimming (L3).

두 가지를 한다.

1. **Planner-visible payload를 추출한다.** Packet에는 재현·감사용 필드가 함께
   들어 있지만 GPT에게 보낼 것은 그중 일부다. Budget은 **보낼 것만** 센다.
2. **넘치면 결정론적으로 줄인다.** random sampling을 쓰지 않는다. L2 ranking
   순서를 유지한 채 tail부터 자른다.

Token이 아니라 **문자 수**를 1차 지표로 쓴다. 이 프로젝트에는 GPT-4.1 mini의
tokenizer가 없고, `한글 1자 = X token` 같은 환산을 근거 없이 Contract로 만들지
않는다(CLAUDE.md §8). tokenizer를 도입해야 할 이유가 생기면 그때 넣는다.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from .models import (
    MonthlyContextPacket,
    PackedBlock,
)

__all__ = [
    "DEFAULT_CHAR_BUDGET",
    "MIN_ITEMS",
    "TRIM_ORDER",
    "PacketMeasurement",
    "measure",
    "packet_fingerprint",
    "planner_visible_payload",
    "trim_to_budget",
]

DEFAULT_CHAR_BUDGET = 20_000
"""Planner-visible canonical JSON의 문자 수 상한.

실측 5 Case가 11.0k~11.9k이므로 **평상시에는 동작하지 않는다.** 그것이 의도다 —
Trim이 상시 동작하면 근거가 조용히 사라지고, 그 사실을 아무도 눈치채지 못한다.
처음 12,000으로 잡았다가 2026-06 만4세에서 바로 발동하는 것을 보고 올렸다.

이 수치는 canonical JSON 기준이며 **Prompt 문자 수가 아니다.** JSON은 key와
따옴표가 내용의 2배 가까이 되므로, L4가 실제 Prompt 형태를 정하면 그 표현에
맞는 상한을 다시 잡아야 한다.
"""

TRIM_ORDER: tuple[PackedBlock, ...] = (
    PackedBlock.OTHER_OUTDOOR,
    PackedBlock.WEEK_EXPERIENCE,
    PackedBlock.INSTITUTION_EVIDENCE,
    PackedBlock.AGE_CONTRAST,
)
"""줄이는 순서. 앞에 있을수록 먼저 줄인다.

`REFERENCE_ACTIVITIES`는 목록에 없다 — **자르지 않는다.** 승인 Catalog에서 온
canonical 후보이고 후속 Planner가 그대로 선택할 수 있는 유일한 축이다
(2027-02처럼 후보가 4개뿐인 달에서 자르면 남는 것이 없다).

`AGE_CONTRAST`가 마지막인 이유는 희소성이다. 5 Case에서 3~6건뿐이고,
"같은 기관에서 연령만 달랐을 때 무엇이 달라지는가"는 다른 Block이 대체할 수
없는 정보다. 자를 때도 **Group 단위로** 잘라 Pair 관계를 깨지 않는다.
"""

MIN_ITEMS: dict[PackedBlock, int] = {
    PackedBlock.OTHER_OUTDOOR: 0,
    PackedBlock.WEEK_EXPERIENCE: 2,
    PackedBlock.INSTITUTION_EVIDENCE: 4,
    PackedBlock.AGE_CONTRAST: 0,
}
"""Trim이 남겨야 하는 최소 개수.

Institution 4는 주차 수의 하한(4주)에서 왔다. 주차마다 최소 하나의 실제 관찰
근거는 남겨야 Grounding이라 부를 수 있다.
"""


def planner_visible_payload(packet: MonthlyContextPacket) -> dict:
    """GPT에게 실제로 보낼 내용만 남긴 canonical dict.

    `audit` 하위 model과 내부 참조 ID를 제거한다. Prompt 문자열이 아니다 —
    Rendering은 L4다.
    """
    raw = packet.model_dump(mode="json")

    request = dict(raw["planning_request"])
    request.pop("daycare_ref", None)
    request.pop("classroom_ref", None)

    theme = dict(raw["parent_theme"])
    for key in (
        "parent_yearly_plan_id",
        "parent_yearly_period_key",
        "reference_catalog_id",
        "reference_version",
        "confirmed_at",
    ):
        theme.pop(key, None)

    return {
        "packet_version": raw["packet_version"],
        "planning_request": request,
        "parent_theme": theme,
        "week_slots": raw["week_slots"],
        "age_context": _strip(raw["age_context"], ("criteria_id",)),
        "institution_evidence": [_evidence(i) for i in raw["institution_evidence"]],
        "age_contrast_evidence": [
            _contrast(g) for g in raw["age_contrast_evidence"]
        ],
        "week_experience_candidates": [
            _evidence(c) for c in raw["week_experience_candidates"]
        ],
        "reference_activities": raw["reference_activities"],
        "other_outdoor_evidence": [
            _evidence(i) for i in raw["other_outdoor_evidence"]
        ],
        "official_play_context": raw["official_play_context"],
        "official_topic_context": raw["official_topic_context"],
        "safety_context": raw["safety_context"],
        "constraints": raw["constraints"],
    }


def _strip(d: dict, keys: tuple[str, ...]) -> dict:
    out = dict(d)
    for k in keys:
        out.pop(k, None)
    return out


_ITEM_DROP = ("audit", "evidence_id", "month", "source_section")
"""Planner payload에서 빼는 항목별 필드.

    audit           Retrieval 내부 점수·좌표. GPT가 쓸 수 없다
    evidence_id     35자 hex. 대신 짧은 `ref`를 준다
    month           Packet 전체가 한 달이다. `planning_request`에 이미 있다
    source_section  Block 이름이 곧 section이다

`reuse_policy`는 **절대 빼지 않는다.** 원문 재사용 정책이 Planner에 도달하지
않으면 CONTEXT_ONLY Contract가 Packet에서 사라진다(§27).
"""


def _evidence(item: dict) -> dict:
    return _strip(item, _ITEM_DROP)


def _contrast(group: dict) -> dict:
    out = _strip(group, ("source_sha256", "source_path"))
    out["observations"] = [
        {"age": o["age"], "items": [_evidence(i) for i in o["items"]]}
        for o in group["observations"]
    ]
    return out


def _canonical_json(payload: dict) -> str:
    """같은 내용이면 항상 같은 문자열. 사람이 읽을 목적이 아니다."""
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True, slots=True)
class PacketMeasurement:
    """무엇이 Context를 얼마나 차지하는가.

    두 수치를 따로 둔다. 하나로 합치면 비교가 틀린다.

        planner_visible_chars   canonical JSON 문자 수. Budget 판정 기준이다.
                                key·따옴표·구분자를 포함하므로 표현에 의존한다.
        content_chars           Planner가 실제로 읽는 **내용 문자열**의 합.
                                표현 방식과 무관하므로 Prototype 수치나 L4의
                                Prompt 수치와 비교할 수 있는 쪽은 이것이다.
    """

    planner_visible_chars: int
    content_chars: int
    full_packet_chars: int
    block_chars: dict[PackedBlock, int]
    block_items: dict[PackedBlock, int]

    @property
    def largest_block(self) -> PackedBlock:
        return max(self.block_chars, key=lambda b: (self.block_chars[b], b.value))

    @property
    def serialization_overhead_ratio(self) -> float:
        """JSON 표현이 내용의 몇 배인가. 1.0에 가까울수록 군더더기가 없다."""
        return (
            self.planner_visible_chars / self.content_chars
            if self.content_chars
            else 0.0
        )


def measure(packet: MonthlyContextPacket) -> PacketMeasurement:
    payload = planner_visible_payload(packet)
    block_chars = {
        block: len(_canonical_json({block.value: payload[block.value]}))
        for block in PackedBlock
    }
    return PacketMeasurement(
        planner_visible_chars=len(_canonical_json(payload)),
        content_chars=_content_chars(packet),
        full_packet_chars=len(_canonical_json(packet.model_dump(mode="json"))),
        block_chars=block_chars,
        block_items=packet.block_sizes(),
    )


def _content_chars(packet: MonthlyContextPacket) -> int:
    """Planner가 읽는 자연어 내용만 센다. 식별자·enum·좌표는 제외한다."""
    total = len(packet.parent_theme.theme_value)
    for item in packet.institution_evidence + packet.other_outdoor_evidence:
        total += len(item.text) + len(item.monthly_theme or "")
    for group in packet.age_contrast_evidence:
        total += len(group.monthly_theme or "")
        for obs in group.observations:
            total += sum(len(i.text) for i in obs.items)
    for cand in packet.week_experience_candidates:
        total += len(cand.text) + len(cand.monthly_theme or "")
    total += sum(len(a.label) for a in packet.reference_activities)
    return total


def packet_fingerprint(packet: MonthlyContextPacket) -> str:
    """같은 입력이면 같은 값.

    **Planner-visible 내용 + Source Lineage**로만 계산한다. `generated_at` 같은
    volatile metadata는 애초에 Packet에 없다. Lineage를 포함하는 이유: 같은
    문장이라도 다른 Evidence Store version에서 나왔다면 다른 Context다.
    """
    payload = {
        "content": planner_visible_payload(packet),
        "lineage": packet.source_lineage.model_dump(mode="json"),
    }
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def trim_to_budget(
    packet: MonthlyContextPacket, *, char_budget: int = DEFAULT_CHAR_BUDGET
) -> MonthlyContextPacket:
    """Budget을 넘으면 결정론적으로 줄인 새 Packet을 돌려준다.

    `random`을 쓰지 않는다. L2 ranking 순서를 유지한 채 **tail부터** 한 건씩
    지우며, `TRIM_ORDER` 앞쪽 Block을 먼저 소진한다. 같은 입력이면 같은 결과다.

    절대 건드리지 않는 것: Planning Request · Theme · Week Slots ·
    Age Context · Safety · Constraints · Lineage · Reference Activities.
    """
    if _planner_chars(packet) <= char_budget:
        return packet

    current = packet
    trimmed: list[str] = []
    for block in TRIM_ORDER:
        while _planner_chars(current) > char_budget:
            shorter = _drop_tail(current, block)
            if shorter is None:
                break
            current = shorter
            if block.value not in trimmed:
                trimmed.append(block.value)
        if _planner_chars(current) <= char_budget:
            break

    return current.model_copy(update={"trimmed_blocks": tuple(trimmed)})


def _planner_chars(packet: MonthlyContextPacket) -> int:
    """Trim loop 전용 경량 측정. `measure()`의 전체 dump를 반복하지 않는다."""
    return len(_canonical_json(planner_visible_payload(packet)))


def _drop_tail(
    packet: MonthlyContextPacket, block: PackedBlock
) -> MonthlyContextPacket | None:
    """Block의 마지막 항목 하나를 지운 Packet. 더 지울 수 없으면 None."""
    floor = MIN_ITEMS.get(block, 0)

    if block is PackedBlock.AGE_CONTRAST:
        groups = packet.age_contrast_evidence
        # Group 단위로 지운다. 낱개로 지우면 대조 Pair가 깨진다.
        if not groups or sum(g.size for g in groups) - groups[-1].size < floor:
            return None
        return packet.model_copy(update={"age_contrast_evidence": groups[:-1]})

    field = {
        PackedBlock.OTHER_OUTDOOR: "other_outdoor_evidence",
        PackedBlock.WEEK_EXPERIENCE: "week_experience_candidates",
        PackedBlock.INSTITUTION_EVIDENCE: "institution_evidence",
    }[block]
    items = getattr(packet, field)
    if len(items) <= floor:
        return None
    return packet.model_copy(update={field: items[:-1]})
