"""Monthly LLM Planner vNext — Prompt / Structured Output / Validator (분석 전용).

Production을 수정하지 않는다. Domain Contract(`MonthlyPlan` · `EvidenceSource` ·
`GenerationMethodDetail`)는 **읽기만** 한다.

    python analysis/experiments/monthly_llm_vnext/planner_contract.py
"""

from __future__ import annotations

import io
import json
import pathlib
import re
import sys

from pydantic import BaseModel, Field, ValidationError

ROOT = pathlib.Path(__file__).resolve().parents[3]
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

PROMPT_VERSION = "monthly-planner-prompt-v0.1.0-draft"

# ============================================================ Structured Output


class PlannedActivity(BaseModel):
    model_config = {"extra": "forbid"}

    value: str = Field(min_length=2, max_length=60)
    origin: str = Field(pattern=r"^(REFERENCE|CORPUS_EVIDENCE|LLM_SYNTHESIZED)$")
    reference_activity_id: str | None = None
    grounding_source_ids: list[str] = Field(default_factory=list)


class PlannedWeek(BaseModel):
    model_config = {"extra": "forbid"}

    week_id: str = Field(min_length=1)
    experience: str = Field(min_length=2, max_length=80)
    activity: PlannedActivity


class MonthlyPlanProposal(BaseModel):
    """LLM이 돌려주는 것. **Domain 객체가 아니다.**

    `theme_id`는 검증용이며 Plan Item에는 Rule이 고른 값이 들어간다
    (`shared/llm/port.py`의 4중 방어와 같은 원칙).
    """

    model_config = {"extra": "forbid"}

    theme_id: str = Field(min_length=1)
    month_flow_rationale: str = Field(min_length=2, max_length=300)
    weeks: list[PlannedWeek] = Field(min_length=1, max_length=6)


def parse_proposal(raw: object) -> MonthlyPlanProposal:
    try:
        if isinstance(raw, MonthlyPlanProposal):
            return raw
        if isinstance(raw, dict):
            return MonthlyPlanProposal.model_validate(raw)
        return MonthlyPlanProposal.model_validate_json(str(raw))
    except ValidationError as exc:
        raise ValueError(f"Planner Structured Output 스키마 위반: {exc}") from exc


# ============================================================ Prompt

SYSTEM_PROMPT = """\
당신은 한국 어린이집(만 3~5세) 담임교사의 월간 보육계획안 **초안**을 구성한다.

역할 경계
- 당신은 Planner다. 무엇이 법적으로 필요한지, 어떤 주제가 국가 필수인지 판정하지 않는다.
- 제공된 EVIDENCE PACKET 안의 근거만 사용한다. 패킷 밖의 사실을 만들어내지 않는다.
- 최종 확정은 교사가 한다. 당신의 출력은 DRAFT다.

반드시 지킬 것
- 한 달 전체를 **함께** 설계한다. 주차를 따로 뽑아 나열하지 않는다.
- 주차 사이에 자연스러운 전개가 있어야 한다. 다만 그 순서를 공식 규칙처럼 주장하지 않는다.
- 주어진 Theme에서 벗어나지 않는다.
- 같은 놀이·같은 경험을 반복하지 않는다.
- 각 주차는 `experience`(그 주에 아이들이 만나는 경험)와 `activity`(바깥놀이 한 가지)를 갖는다.
- `activity.origin`을 정확히 구분한다.
    REFERENCE        REFERENCE ACTIVITIES 목록에서 그대로 고른 경우. reference_activity_id 필수.
    CORPUS_EVIDENCE  패킷의 기관 관찰 근거에서 가져온 경우. grounding_source_ids 필수.
    LLM_SYNTHESIZED  위 둘로 채울 수 없어 근거를 조합해 새로 구성한 경우.
                     grounding_source_ids에 실제로 참고한 record_id를 모두 적는다.

절대 하지 말 것
- "공식적으로 권장된다" / "누리과정에서 반드시 한다" / "법적으로 이 주에 해야 한다" 같은 주장
- 안전교육 배치. 안전교육은 이 작업의 대상이 아니다.
- 패킷에 없는 기관명·시설명·행사명 사용
- 패킷의 문장을 그대로 옮겨 적기(참고는 하되 이 반을 위한 표현으로 새로 쓴다)

출력은 지정된 JSON 스키마만 반환한다.
"""


def render_packet(blocks, q) -> str:
    """Context Packet을 Prompt 텍스트로 만든다. Raw PDF 텍스트를 넣지 않는다."""
    out: list[str] = []
    out.append("PLANNING REQUEST")
    out.append(f"  target_month : {q.target_month}")
    out.append(f"  ages         : 만 {', '.join(map(str, q.ages))}세")
    out.append(f"  week_ids     : {', '.join(q.week_ids)}  (총 {len(q.week_ids)}주)")
    out.append("")
    out.append("CONFIRMED YEARLY THEME")
    out.append(f"  theme_id    : {q.theme_id}")
    out.append(f"  theme_label : {q.theme_label}")
    out.append("  (상위 연간계획에서 교사가 확정한 값이다. 바꾸지 않는다.)")
    out.append("")

    for b in blocks:
        out.append(f"{b.name}   [{'required' if b.required else 'optional'}]")
        if not b.items:
            out.append("  (해당 근거 없음)")
            out.append("")
            continue
        for it in b.items:
            if "activity_id" in it:
                flag = " ※표시품질 확인필요" if it["display_quality_issue"] else ""
                out.append(f"  - id={it['activity_id']} | {it['label']}"
                           f" | 근거 {it['evidence_strength']}건{flag}")
            else:
                txt = it.get("activity_text") or it.get("experience_text")
                age = "".join(map(str, it["age_scope"])) or "미상"
                out.append(f"  - id={it['record_id']} | 만{age}세 | "
                           f"{it['institution_id']} | [{it['source_label']}] {txt}")
        out.append("")
    return "\n".join(out)


CONSTRAINTS = """\
PRODUCT CONSTRAINTS
  - 주차 수와 week_id는 위 목록과 정확히 일치해야 한다. 추가·삭제·변경 금지.
  - theme_id는 위 값을 그대로 반환한다.
  - activity.value는 60자 이내, experience는 80자 이내.
  - 같은 activity.value를 두 번 쓰지 않는다.
  - REFERENCE를 쓸 때 reference_activity_id는 REFERENCE ACTIVITIES 목록의 id여야 한다.
  - CORPUS_EVIDENCE / LLM_SYNTHESIZED는 grounding_source_ids가 비어 있으면 안 되며,
    그 id는 위 패킷에 실제로 등장한 id여야 한다.

SAFETY STATE
  - 안전교육 칸은 이 요청의 대상이 아니다. 별도 Rule이 처리하며 현재 미해결 상태다.
  - 안전교육을 주차에 배치하거나 언급하지 않는다.
"""


# ============================================================ Validator


class ValidationIssue(BaseModel):
    model_config = {"extra": "forbid"}
    rule: str
    detail: str


def validate_proposal(
    proposal: MonthlyPlanProposal, *, q, blocks
) -> list[ValidationIssue]:
    """Deterministic Validator. LLM에게 검증을 맡기지 않는다."""
    issues: list[ValidationIssue] = []

    def bad(rule: str, detail: str) -> None:
        issues.append(ValidationIssue(rule=rule, detail=detail))

    # --- week 구조
    got = [w.week_id for w in proposal.weeks]
    if len(got) != len(q.week_ids):
        bad("monthly_llm.week_count", f"{len(q.week_ids)}주 요청, {len(got)}주 반환")
    if got != list(q.week_ids):
        bad("monthly_llm.week_ids_exact", f"기대 {list(q.week_ids)} / 실제 {got}")

    # --- theme 보존
    if proposal.theme_id != q.theme_id:
        bad("monthly_llm.theme_preserved",
            f"theme_id가 바뀌었다: {q.theme_id} → {proposal.theme_id}")

    # --- 중복
    acts = [w.activity.value.strip() for w in proposal.weeks]
    exps = [w.experience.strip() for w in proposal.weeks]
    if len(set(acts)) != len(acts):
        bad("monthly_llm.duplicate_activity", f"중복 activity: {acts}")
    if len(set(exps)) != len(exps):
        bad("monthly_llm.duplicate_experience", f"중복 experience: {exps}")

    # --- id 존재
    ref_ids = {it["activity_id"] for b in blocks for it in b.items
               if "activity_id" in it}
    src_ids = {it["record_id"] for b in blocks for it in b.items
               if "record_id" in it}
    for w in proposal.weeks:
        a = w.activity
        if a.origin == "REFERENCE":
            if not a.reference_activity_id:
                bad("monthly_llm.reference_id_required", w.week_id)
            elif a.reference_activity_id not in ref_ids:
                bad("monthly_llm.reference_id_exists",
                    f"{w.week_id}: 패킷에 없는 id {a.reference_activity_id}")
        else:
            if not a.grounding_source_ids:
                bad("monthly_llm.grounding_required",
                    f"{w.week_id}: origin={a.origin}인데 grounding_source_ids가 비었다")
            for sid in a.grounding_source_ids:
                if sid not in src_ids and sid not in ref_ids:
                    bad("monthly_llm.grounding_source_exists",
                        f"{w.week_id}: 패킷에 없는 source id {sid}")
        if a.origin == "REFERENCE" and a.grounding_source_ids:
            bad("monthly_llm.reference_needs_no_grounding",
                f"{w.week_id}: REFERENCE는 reference_activity_id로 충분하다")

    # --- 금지 Claim
    BANNED = ("누리과정에서 반드시", "법적으로", "공식적으로 권장", "의무적으로",
              "평가제", "국가가 정한")
    for w in proposal.weeks:
        for field, text in (("experience", w.experience),
                            ("activity", w.activity.value)):
            for b in BANNED:
                if b in text:
                    bad("monthly_llm.no_official_claim",
                        f"{w.week_id}.{field}: 금지 표현 '{b}'")
    for b in BANNED:
        if b in proposal.month_flow_rationale:
            bad("monthly_llm.no_official_claim", f"rationale: 금지 표현 '{b}'")

    # --- 안전교육 침범
    if any("안전교육" in w.activity.value or "안전교육" in w.experience
           for w in proposal.weeks):
        bad("monthly_llm.safety_untouched", "안전교육을 주차 칸에 배치했다")

    return issues


def main() -> int:
    print("=" * 92)
    print(" Planner Contract — Structured Output Schema")
    print("=" * 92)
    print(json.dumps(MonthlyPlanProposal.model_json_schema(),
                     ensure_ascii=False, indent=1)[:1800])
    print("\n  prompt_version:", PROMPT_VERSION)
    print("  SYSTEM PROMPT 문자 수:", len(SYSTEM_PROMPT))
    print("  CONSTRAINTS 문자 수 :", len(CONSTRAINTS))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
