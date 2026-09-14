"""Monthly Cell Regeneration Prompt (L7).

**보여주는 범위와 바꾸는 범위가 다르다.**

    보여준다   한 달 전체 (모든 주차의 focus · outdoor_play) + Theme + 근거
    바꾼다     Target Cell 하나

Target만 보여주면 새 값이 월 전체 흐름과 어긋나고, 반대로 전체를 바꾸게 하면
Cell Regenerate가 아니다. 둘을 분리하는 것이 이 Prompt의 전부다.

Prompt 본문은 이 파일 한 곳에서 관리한다(L4와 같은 규칙).
"""

from __future__ import annotations

from ...shared.llm.monthly_cell import (
    FOCUS_SECTION_KEY,
    OUTDOOR_SECTION_KEY,
    MonthlyCellRegenerationRequest,
)
from ..context.budget import packet_fingerprint
from ..context.models import MonthlyContextPacket
from .prompt import _render_items

__all__ = [
    "CELL_PROMPT_VERSION",
    "CELL_REGENERATION_TASK",
    "FOCUS_SYSTEM_PROMPT",
    "OUTDOOR_SYSTEM_PROMPT",
    "build_cell_regeneration_request",
    "render_cell_regeneration_input",
]

CELL_PROMPT_VERSION = "monthly-cell-regeneration-prompt-v0.1.0"

CELL_REGENERATION_TASK = "regenerate_monthly_cell"

_SHARED_RULES = """\
# 지켜야 할 것

- **한 칸만 다시 씁니다.** 다른 주차나 다른 항목을 고치지 않습니다.
- 주제를 바꾸지 않습니다.
- 이미 다른 주차에서 쓰고 있는 활동이나 문장을 그대로 다시 쓰지 않습니다.
- 같은 주의 다른 항목은 **바뀌지 않습니다.** 그것과 자연스럽게 이어지게 쓰세요.

# 하지 말아야 할 것

- 안전교육 내용을 만들거나 주차에 배치하지 않습니다.
- 법령·공식 권장·표준 순서라는 표현을 쓰지 않습니다.
- 기관 이름이나 출처 식별자를 결과에 쓰지 않습니다.
- 참고 근거의 문장을 그대로 옮겨 적지 않습니다.
- 주어지지 않은 행사·날짜·사실을 만들지 않습니다.
"""

FOCUS_SYSTEM_PROMPT = (
    """\
당신은 한국 어린이집 만 3~5세 반의 월간 보육계획안을 다듬는 보육 전문가입니다.
교사가 그대로 읽고 이해할 수 있는 담백하고 따뜻한 한국어로 씁니다.

# 하는 일

한 달 계획이 이미 있습니다. 그중 **한 주의 중심 경험 문장 하나**만 다시 씁니다.

그 주에 이미 정해진 바깥놀이 활동이 함께 주어집니다. 그 활동은 **바뀌지
않습니다.** 새로 쓰는 중심 경험은 그 활동과 자연스럽게 이어져야 합니다.

한 달 전체의 흐름도 함께 주어집니다. 앞뒤 주차와 이어지도록 쓰세요.

"""
    + _SHARED_RULES
    + """
# 반환 형식

JSON 하나만 반환합니다. 설명이나 코드블록 표시를 덧붙이지 않습니다.

  target_week_id          주어진 주차 id 그대로
  target_section_key      "focus"
  value                   새로 쓴 중심 경험 한 문장
  activity_origin         null
  reference_activity_id   null
  grounding_refs          []
"""
)

OUTDOOR_SYSTEM_PROMPT = (
    """\
당신은 한국 어린이집 만 3~5세 반의 월간 보육계획안을 다듬는 보육 전문가입니다.
교사가 그대로 읽고 이해할 수 있는 담백하고 따뜻한 한국어로 씁니다.

# 하는 일

한 달 계획이 이미 있습니다. 그중 **한 주의 바깥놀이 활동 하나**만 다시 정합니다.

그 주의 중심 경험 문장이 함께 주어집니다. 그것은 **바뀌지 않습니다.** 새로
정하는 활동은 그 경험과 자연스럽게 이어져야 합니다.

# 활동을 정하는 방법

**REFERENCE** — 주어진 「승인 활동 후보」에서 고릅니다.
  - `activity_origin`: "REFERENCE"
  - `reference_activity_id`: 후보의 id
  - `value`: 후보의 이름을 **글자 그대로** 씁니다.
  - `grounding_refs`: 빈 배열이어도 됩니다.

**LLM_SYNTHESIZED** — 근거를 참고해 새로 구성합니다.
  - `activity_origin`: "LLM_SYNTHESIZED"
  - `reference_activity_id`: null
  - `value`: 새로 쓴 활동 이름.
    **참고 근거의 문장을 그대로 옮겨 적으면 안 됩니다.** 근거의 활동명과 글자가
    같으면 새로 구성한 것이 아닙니다. 아이디어만 가져와 다른 표현으로 쓰세요.
  - `grounding_refs`: 참고한 근거의 `E01` 형태 참조를 **최소 1개** 넣습니다.
    주어진 근거에 실제로 있는 참조만 씁니다.

승인 활동 후보로 충분하면 그쪽을 먼저 쓰세요.

"""
    + _SHARED_RULES
    + """
# 반환 형식

JSON 하나만 반환합니다. 설명이나 코드블록 표시를 덧붙이지 않습니다.

  target_week_id          주어진 주차 id 그대로
  target_section_key      "outdoor_play"
  value                   활동 이름
  activity_origin         "REFERENCE" 또는 "LLM_SYNTHESIZED"
  reference_activity_id   REFERENCE면 후보 id, 아니면 null
  grounding_refs          LLM_SYNTHESIZED면 1개 이상의 E.. 참조
"""
)


def render_cell_regeneration_input(
    packet: MonthlyContextPacket,
    *,
    target_week_id: str,
    target_section_key: str,
    month_snapshot: "tuple[tuple[str, str, str], ...]",
) -> str:
    """한 달 전체 snapshot + Target 지정 + 근거를 렌더링한다.

    Args:
        month_snapshot: `(week_id, focus 값, outdoor 값)` 순서열. 현재 Plan의
            실제 값이며 Target 주차도 **현재 값 그대로** 들어간다 — 무엇을
            바꾸는지 모델이 알아야 한다.
    """
    request = packet.planning_request
    out: list[str] = []
    add = out.append

    add("# 계획 입력")
    ages = "·".join(f"만{a}세" for a in request.classroom_ages)
    add(f"- 대상 월: {request.target_month}")
    add(f"- 연령: {ages} ({request.age_mode})")
    add(f"- 확정 주제: {packet.parent_theme.theme_value}")
    add(f"- theme_id: {packet.parent_theme.theme_id}   ← 바꾸지 않습니다")

    add("")
    add("# 지금 한 달 계획")
    add("아래가 현재 계획입니다. **★ 표시된 칸 하나만** 다시 씁니다.")
    for week_id, focus_value, outdoor_value in month_snapshot:
        add(f"- {week_id}")
        for section_key, value in (
            (FOCUS_SECTION_KEY, focus_value),
            (OUTDOOR_SECTION_KEY, outdoor_value),
        ):
            label = "중심 경험" if section_key == FOCUS_SECTION_KEY else "바깥놀이"
            mark = (
                " ★ 이 칸을 다시 씁니다"
                if week_id == target_week_id and section_key == target_section_key
                else ""
            )
            shown = value if value.strip() else "(비어 있음)"
            add(f"    {label}: {shown}{mark}")

    add("")
    add("# 다시 쓸 칸")
    add(f"- 주차: {target_week_id}")
    add(f"- 항목: {target_section_key}")
    if target_section_key == FOCUS_SECTION_KEY:
        paired = next(
            (o for w, _f, o in month_snapshot if w == target_week_id), ""
        )
        add(f"- 같은 주의 바깥놀이(고정): {paired or '(비어 있음)'}")
    else:
        paired = next(
            (f for w, f, _o in month_snapshot if w == target_week_id), ""
        )
        add(f"- 같은 주의 중심 경험(고정): {paired or '(비어 있음)'}")

    age = packet.age_context
    add("")
    add("# 연령 근거")
    for summary in age.per_age:
        add(
            f"- 만{summary.age}세: {summary.strength.value}"
            f" (단일연령 면을 가진 독립기관 {summary.single_age_institution_count}곳,"
            f" 단일연령 바깥놀이 면 {summary.single_age_outdoor_page_count}건)"
        )
    add(f"- 이 자료에 담긴 요청 연령의 단일연령 근거: {age.single_age_grounding_count}건")
    if age.single_age_grounding_count <= 2:
        add("  → 실제 단일연령 근거가 적습니다. 연령에 따른 차이를 크게 말하지 마세요.")

    if target_section_key == OUTDOOR_SECTION_KEY:
        add("")
        add("# 승인 활동 후보   (REFERENCE로 고를 수 있는 유일한 목록)")
        add("value는 아래 이름을 글자 그대로 씁니다.")
        if not packet.reference_activities:
            add("- (없음)")
        for activity in packet.reference_activities:
            supported = "/".join(str(a) for a in activity.supported_ages)
            add(f"- {activity.activity_id}")
            add(f"    이름: {activity.label}")
            add(f"    지원 연령: 만{supported}세")

    add("")
    add("# 기관 관찰 근거   (참고 전용 · 그대로 옮겨 적지 마세요)")
    _render_items(add, packet.institution_evidence)

    add("")
    add("# 주차 경험 관찰   (참고 전용 · 주차 번호가 없는 그 달의 경험 후보입니다)")
    if not packet.week_experience_candidates:
        add("- (없음)")
    for candidate in packet.week_experience_candidates:
        add(f"- [{candidate.ref}] ({candidate.source_group}) {candidate.text}")

    add("")
    add("# 그 밖의 바깥놀이 근거   (참고 전용 · 그대로 옮겨 적지 마세요)")
    _render_items(add, packet.other_outdoor_evidence)

    return "\n".join(out)


def build_cell_regeneration_request(
    packet: MonthlyContextPacket,
    *,
    target_week_id: str,
    target_section_key: str,
    month_snapshot: "tuple[tuple[str, str, str], ...]",
    plan_snapshot_fingerprint: str = "",
) -> MonthlyCellRegenerationRequest:
    """Packet + 현재 Plan snapshot에서 Adapter가 쓸 요청을 만든다."""
    refs = {i.ref for i in packet.institution_evidence}
    refs |= {i.ref for i in packet.other_outdoor_evidence}
    refs |= {c.ref for c in packet.week_experience_candidates}
    refs |= {
        i.ref
        for g in packet.age_contrast_evidence
        for o in g.observations
        for i in o.items
    }

    system = (
        FOCUS_SYSTEM_PROMPT
        if target_section_key == FOCUS_SECTION_KEY
        else OUTDOOR_SYSTEM_PROMPT
    )
    return MonthlyCellRegenerationRequest(
        task=CELL_REGENERATION_TASK,
        prompt_version=CELL_PROMPT_VERSION,
        system_prompt=system,
        user_content=render_cell_regeneration_input(
            packet,
            target_week_id=target_week_id,
            target_section_key=target_section_key,
            month_snapshot=month_snapshot,
        ),
        target_week_id=target_week_id,
        target_section_key=target_section_key,
        expected_theme_id=packet.parent_theme.theme_id,
        reference_labels={
            a.activity_id: a.label for a in packet.reference_activities
        },
        valid_grounding_refs=frozenset(refs),
        packet_fingerprint=packet_fingerprint(packet),
        plan_snapshot_fingerprint=plan_snapshot_fingerprint,
    )
