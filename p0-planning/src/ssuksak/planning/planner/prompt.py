"""Monthly Planner Production Prompt (L4).

**Prompt 본문은 이 파일 한 곳에서 관리한다.** Adapter에 큰 문자열을 박아 넣지
않는다(§20). Adapter는 여기서 만든 `MonthlyPlannerRequest`를 전송할 뿐이다.

Context Rendering 원칙 셋.

1. **Audit-only 정보를 넣지 않는다.** `source_sha256` · `source_path` ·
   `rank_score` · `retrieval_tier` · `institution_id`는 Prompt에 들어가지
   않는다. L3의 planner-visible payload만 쓴다.
2. **JSON을 그대로 붓지 않는다.** L3 canonical JSON은 내용 924자에 10,282자다
   — key와 따옴표가 열 배다. 사람이 읽는 형태로 다시 렌더링하면 같은 내용이
   훨씬 짧아진다.
3. **의미·reuse policy·ref는 사라지지 않는다.** 짧게 만들려고 `CONTEXT_ONLY`
   표시나 `E01` 참조를 빼면 Contract가 Prompt에서 사라진다.
"""

from __future__ import annotations

from ...shared.llm.monthly import MonthlyPlannerRequest
from ..context.budget import packet_fingerprint
from ..context.models import MonthlyContextPacket

__all__ = [
    "MONTHLY_PLANNER_TASK",
    "PROMPT_VERSION",
    "SYSTEM_PROMPT",
    "build_monthly_planner_request",
    "render_planning_input",
]

PROMPT_VERSION = "monthly-planner-prompt-v0.1.1"
"""v0.1.0 → v0.1.1 (2026-09-13).

첫 Live Smoke에서 2027-02 만5세가 `CONTEXT_ONLY` 근거 문장(`내 키만큼 멀리 뛰기`)을
글자 그대로 `LLM_SYNTHESIZED` value로 반환했다. 금지 문구가 「하지 말아야 할 것」
목록에만 있고 **판단하는 지점**에는 없었다. LLM_SYNTHESIZED 설명 안으로 옮겼다.

한 번의 재실행으로 고쳐졌다고 단정하지 않는다. L5의 exact-copy 검출은 여전히
필요하다 — Prompt는 확률을 낮출 뿐 보장하지 않는다.
"""

MONTHLY_PLANNER_TASK = "plan_monthly"

SYSTEM_PROMPT = """\
당신은 한국 어린이집 만 3~5세 반의 월간 보육계획안 초안을 구성하는 보육 전문가입니다.
교사가 그대로 읽고 이해할 수 있는 담백하고 따뜻한 한국어로 씁니다.

# 하는 일

한 달 전체의 바깥놀이 흐름을 구성합니다. 주차마다 그 주의 중심 경험(experience)과
활동(activity)을 하나씩 정합니다.

**주차를 하나씩 따로 뽑지 마세요.** 먼저 한 달 전체의 흐름을 생각한 다음, 그 흐름에
맞춰 각 주차를 배치하세요. 예를 들어 관심을 갖는 단계에서 직접 탐색하고, 경험을
넓히고, 표현하거나 응용하는 쪽으로 이어지는 전개를 생각해 볼 수 있습니다.
이것은 하나의 사고 방향일 뿐 정해진 규칙이 아닙니다. 주제와 주어진 근거에 맞는
흐름을 직접 판단하세요.

# 하지 않는 일

- 주제를 고르거나 바꾸지 않습니다. 주어진 theme_id를 그대로 돌려줍니다.
- 주차 수나 날짜를 계산하지 않습니다. 주어진 week_id를 그대로, 순서대로 씁니다.
- 안전교육 내용을 만들지 않고, 주차에 배치하지 않고, 충족 여부를 판단하지 않습니다.
- 법적 기준이나 공식 권장을 말하지 않습니다.
- 기관 이름이나 출처 식별자를 결과에 쓰지 않습니다.

# 활동을 정하는 방법

활동은 두 가지 중 하나입니다.

**REFERENCE** — 주어진 「승인 활동 후보」에서 고릅니다.
  - `origin`: "REFERENCE"
  - `reference_activity_id`: 후보의 id
  - `value`: 후보의 이름을 **글자 그대로** 씁니다. 다듬거나 바꾸지 않습니다.
  - `grounding_refs`: 빈 배열이어도 됩니다.

**LLM_SYNTHESIZED** — 근거를 참고해 새로 구성합니다.
  - `origin`: "LLM_SYNTHESIZED"
  - `reference_activity_id`: null
  - `value`: 새로 쓴 활동 이름.
    **참고한 근거의 문장을 그대로 옮겨 적으면 안 됩니다.** 근거의 활동명과
    글자가 같으면 그것은 새로 구성한 것이 아닙니다. 근거에서 아이디어만 가져와
    다른 표현으로 쓰세요.
  - `grounding_refs`: 참고한 근거의 `E01` 형태 참조를 **최소 1개** 넣습니다.
    주어진 근거에 실제로 있는 참조만 씁니다. 없는 참조를 만들지 마세요.

승인 활동 후보만으로 주제에 맞고 자연스러운 한 달을 만들 수 있다면 그쪽을 먼저
쓰세요. 후보가 부족하거나 한 달 흐름을 만들기 어려울 때 근거를 바탕으로 새 활동을
구성하세요. 굳이 새로 만들 이유가 없으면 만들지 않아도 됩니다.

# 관찰 근거를 다루는 방법

「기관 관찰 근거」·「주차 경험 관찰」·「그 밖의 바깥놀이 근거」는 실제 어린이집
계획안에서 관찰된 자료이며 **맥락과 아이디어를 이해하기 위한 참고자료**입니다.
재사용 정책이 참고 전용이므로 **문장을 그대로 옮겨 적지 마세요.** 의미를 참고해
새로 구성하세요. 다만 "산책하기"·"모래놀이"처럼 누구나 쓰는 일반적인 표현까지
피할 필요는 없습니다.

# 연령을 다루는 방법

「연령 근거」의 등급과 **Packet 안의 실제 단일연령 근거 수**를 함께 보세요.
등급이 높아도 실제 단일연령 근거가 적으면 연령에 따른 차이를 크게 말하지 마세요.
「연령 대조 근거」가 있으면 일반적인 발달 이론으로 차이를 지어내기 전에 그것을
먼저 참고하세요. 다만 대조 사례를 그대로 옮겨 적지는 마세요.
"""


def render_planning_input(packet: MonthlyContextPacket) -> str:
    """Packet을 사람이 읽는 결정론적 텍스트로 렌더링한다.

    같은 Packet이면 항상 같은 문자열이다. `render_debug_packet()`과 다르다 —
    저쪽은 사람이 점검하려고 audit 수치까지 보여주고, 이쪽은 **모델에게 보내는
    본문**이라 audit을 담지 않는다.
    """
    req = packet.planning_request
    out: list[str] = []
    add = out.append

    add("# 계획 입력")
    ages = "·".join(f"만{a}세" for a in req.classroom_ages)
    add(f"- 학년도: {req.school_year}학년도")
    add(f"- 대상 월: {req.target_month}")
    add(f"- 연령: {ages} ({req.age_mode})")
    add(f"- 확정 주제: {packet.parent_theme.theme_value}")
    add(f"- theme_id: {packet.parent_theme.theme_id}   ← 그대로 돌려주세요")
    add(f"- 주차 {len(packet.week_slots)}개 (이 순서 그대로, 추가·누락 금지)")
    for slot in packet.week_slots:
        add(
            f"  - {slot.week_id}  {slot.display_label}"
            f"  {slot.start_date}~{slot.end_date}"
        )

    age = packet.age_context
    add("")
    add("# 연령 근거")
    for summary in age.per_age:
        add(
            f"- 만{summary.age}세: {summary.strength.value}"
            f" (단일연령 면을 가진 독립기관 {summary.single_age_institution_count}곳,"
            f" 연령을 언급한 기관 {summary.age_mentioning_institution_count}곳,"
            f" 단일연령 바깥놀이 면 {summary.single_age_outdoor_page_count}건)"
        )
    add(f"- 이 자료에 담긴 요청 연령의 단일연령 근거: {age.single_age_grounding_count}건")
    if age.single_age_grounding_count <= 2:
        add("  → 실제 단일연령 근거가 적습니다. 연령에 따른 차이를 크게 말하지 마세요.")

    add("")
    add("# 연령 대조 근거")
    add("같은 기관의 같은 달 계획안에서 연령만 다른 면을 비교한 것입니다.")
    if not packet.age_contrast_evidence:
        add("- (없음)")
    for index, group in enumerate(packet.age_contrast_evidence, start=1):
        theme = f'  원문 주제 "{group.monthly_theme}"' if group.monthly_theme else ""
        add(f"- 대조 {index} (출처 {group.source_group}){theme}")
        for obs in group.observations:
            for item in obs.items:
                add(f"    만{obs.age}세: {item.text}  [{item.ref}]")

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
    add("# 승인 활동 후보   (REFERENCE로 고를 수 있는 유일한 목록)")
    add("value는 아래 이름을 글자 그대로 씁니다.")
    if not packet.reference_activities:
        add("- (없음)")
    for activity in packet.reference_activities:
        supported = "/".join(str(a) for a in activity.supported_ages)
        note = "  ※ 표시 품질 검토 대상" if activity.has_display_quality_issue else ""
        add(f"- {activity.activity_id}")
        add(f"    이름: {activity.label}")
        add(f"    지원 연령: 만{supported}세{note}")

    add("")
    add("# 그 밖의 바깥놀이 근거   (참고 전용 · 그대로 옮겨 적지 마세요)")
    _render_items(add, packet.other_outdoor_evidence)

    if packet.official_play_context or packet.official_topic_context:
        add("")
        add("# 공식 자료 사례")
        for case in packet.official_play_context + packet.official_topic_context:
            add(f"- {case.title}")

    constraints = packet.constraints
    add("")
    add("# 지켜야 할 것")
    add(f"- theme_id는 {packet.parent_theme.theme_id} 그대로 반환합니다.")
    add(f"- 주차는 정확히 {constraints.expected_week_count}개, 위 순서 그대로입니다.")
    add(f"  {', '.join(constraints.expected_week_ids)}")
    add("- 같은 활동을 두 주차에 쓰지 않습니다.")
    add(
        "- origin은 "
        + " 또는 ".join(o.value for o in constraints.allowed_activity_origins)
        + " 만 씁니다."
    )
    add("- 승인 활동 후보를 먼저 고려하고, 필요할 때 새 활동을 구성합니다.")

    add("")
    add("# 하지 말아야 할 것")
    add("- 안전교육 내용을 만들거나 주차에 배치하지 않습니다.")
    add("- 법령·공식 권장·표준 순서라는 표현을 쓰지 않습니다.")
    add("- 기관 이름이나 출처 식별자를 결과에 쓰지 않습니다.")
    add("- 참고 근거의 문장을 그대로 옮겨 적지 않습니다.")
    add("- 위 목록에 없는 활동 id나 근거 참조를 만들지 않습니다.")
    add("- 주어지지 않은 행사·날짜·사실을 만들지 않습니다.")

    add("")
    add("# 반환 형식")
    add("JSON 하나만 반환합니다. 설명이나 코드블록 표시를 덧붙이지 않습니다.")
    add("")
    add("  theme_id               : 위 theme_id 그대로")
    add("  month_flow_rationale   : 한 달 흐름을 어떻게 구성했는지 2~3문장")
    add("  weeks[]                : 위 주차 순서 그대로")
    add("    week_id              : 주차 id")
    add("    experience           : 그 주의 중심 경험·놀이 방향 한 문장")
    add("    activity.value       : 활동 이름")
    add("    activity.origin      : REFERENCE 또는 LLM_SYNTHESIZED")
    add("    activity.reference_activity_id : REFERENCE면 후보 id, 아니면 null")
    add("    activity.grounding_refs        : LLM_SYNTHESIZED면 1개 이상의 E.. 참조")

    return "\n".join(out)


def _render_items(add, items) -> None:
    if not items:
        add("- (없음)")
        return
    for item in items:
        theme = f"  · 원문 주제: {item.monthly_theme}" if item.monthly_theme else ""
        ages = (
            "  · 만" + "/".join(str(a) for a in item.age_scope) + "세 면"
            if item.age_scope
            else "  · 연령 표기 없는 면"
        )
        add(f"- [{item.ref}] ({item.source_group}) {item.text}{ages}{theme}")


def build_monthly_planner_request(
    packet: MonthlyContextPacket,
) -> MonthlyPlannerRequest:
    """Packet에서 Adapter가 쓸 요청을 만든다.

    Adapter가 Packet을 직접 알지 않도록 여기서 **문자열과 anchor로 평탄화**한다.
    """
    refs = {i.ref for i in packet.institution_evidence}
    refs |= {i.ref for i in packet.other_outdoor_evidence}
    refs |= {c.ref for c in packet.week_experience_candidates}
    refs |= {
        i.ref
        for g in packet.age_contrast_evidence
        for o in g.observations
        for i in o.items
    }

    return MonthlyPlannerRequest(
        task=MONTHLY_PLANNER_TASK,
        prompt_version=PROMPT_VERSION,
        system_prompt=SYSTEM_PROMPT,
        user_content=render_planning_input(packet),
        expected_theme_id=packet.parent_theme.theme_id,
        expected_week_ids=tuple(w.week_id for w in packet.week_slots),
        reference_labels={
            a.activity_id: a.label for a in packet.reference_activities
        },
        valid_grounding_refs=frozenset(refs),
        packet_fingerprint=packet_fingerprint(packet),
    )
