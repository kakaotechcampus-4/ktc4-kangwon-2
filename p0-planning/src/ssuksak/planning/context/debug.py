"""사람이 Packet 내용을 눈으로 확인하기 위한 deterministic rendering (L3).

**이것은 Production Prompt가 아니다.** 이름에 `debug`가 들어간 이유가 그것이다.
L4의 Prompt Renderer는 별도로 만들며, 이 함수를 Prompt로 승격하지 않는다.

여기서 만드는 문자열은 Token Budget 계산에도 쓰지 않는다 — Budget은
`budget.planner_visible_payload()`의 canonical JSON으로 잰다.
"""

from __future__ import annotations

from .budget import measure, packet_fingerprint
from .models import MonthlyContextPacket

__all__ = ["render_debug_packet"]


def render_debug_packet(packet: MonthlyContextPacket, *, audit: bool = False) -> str:
    """같은 Packet이면 항상 같은 문자열."""
    req = packet.planning_request
    out: list[str] = []
    add = out.append

    add(f"# MONTHLY CONTEXT PACKET  ({packet.packet_version})")
    add(
        f"  {req.target_month} · 만{'/'.join(str(a) for a in req.classroom_ages)}세"
        f" · {req.age_mode} · {req.school_year}학년도"
    )
    add(f"  Theme  {packet.parent_theme.theme_value}  [{packet.parent_theme.theme_id}]")
    add(
        "  Weeks  "
        + " | ".join(
            f"{w.week_id}({w.display_label}) {w.start_date}~{w.end_date}"
            for w in packet.week_slots
        )
    )

    age = packet.age_context
    add("")
    add(f"## AGE CONTEXT  overall={age.overall_strength.value}  [{age.criteria_id}]")
    for s in age.per_age:
        add(
            f"  만{s.age}세 {s.strength.value:<10}"
            f" 단{s.single_age_institution_count}"
            f"/전{s.age_mentioning_institution_count}"
            f"/바{s.single_age_outdoor_page_count}"
        )
    add(
        f"  age contrast {age.age_contrast_count}건 / 문서 "
        f"{age.age_contrast_document_count}건"
        f"  |  Packet 내 요청연령 단일연령 근거 {age.single_age_grounding_count}건"
    )

    add("")
    add(f"## INSTITUTION EVIDENCE  ({len(packet.institution_evidence)})")
    for i in packet.institution_evidence:
        add(f"  [{i.source_group}] {i.age_match_kind.value:<22} {i.text}")
        if audit:
            add(f"      {i.audit.record_id}  p{i.audit.page}  {i.audit.institution_id}")

    add("")
    add(f"## AGE CONTRAST  ({len(packet.age_contrast_evidence)} groups)")
    for g in packet.age_contrast_evidence:
        add(f"  {g.group_id} [{g.source_group}] theme={g.monthly_theme}")
        for obs in g.observations:
            for item in obs.items:
                add(f"      만{obs.age}세 | {item.text}")

    add("")
    add(f"## WEEK EXPERIENCE CANDIDATES  ({len(packet.week_experience_candidates)})")
    add("  (주차 번호 없음 — 그 달에 관찰된 경험 후보다)")
    for c in packet.week_experience_candidates:
        add(f"  [{c.source_group}] {c.text}")

    add("")
    add(f"## REFERENCE ACTIVITIES  ({len(packet.reference_activities)})")
    for a in packet.reference_activities:
        flag = " !display" if a.has_display_quality_issue else ""
        add(
            f"  {a.rank:>2}. {a.label}  "
            f"(만{'/'.join(str(x) for x in a.supported_ages)}세, "
            f"evidence {a.evidence_strength}){flag}"
        )

    add("")
    add(f"## OTHER OUTDOOR EVIDENCE  ({len(packet.other_outdoor_evidence)})")
    for i in packet.other_outdoor_evidence:
        add(f"  [{i.source_group}] {i.text}")

    add("")
    add(f"## OFFICIAL CONTEXT  play={len(packet.official_play_context)} "
        f"topic={len(packet.official_topic_context)}")
    if not packet.official_play_context and not packet.official_topic_context:
        add("  (비어 있음 — Official Adapter 미구현. 가짜 근거로 채우지 않는다)")

    safety = packet.safety_context
    add("")
    add("## SAFETY")
    add(
        f"  generation_allowed={safety.safety_generation_allowed}"
        f"  {safety.verification} / {safety.cell_state}"
    )
    add(f"  required_source_kinds={', '.join(safety.required_source_kinds)}")

    c = packet.constraints
    add("")
    add("## CONSTRAINTS")
    add(f"  theme_locked={c.theme_locked}")
    add(f"  duplicate_activity_allowed={c.duplicate_activity_allowed}")
    add(f"  official_claim_allowed={c.official_claim_allowed}")
    add(f"  source_text_copy_allowed={c.source_text_copy_allowed}")
    add(f"  corpus_direct_output_enabled={c.corpus_direct_output_enabled}")
    add(
        "  allowed_activity_origins="
        + ", ".join(o.value for o in c.allowed_activity_origins)
    )
    add(
        "  activity_origin_priority="
        + " > ".join(o.value for o in c.activity_origin_priority)
    )

    m = measure(packet)
    add("")
    add("## SIZE")
    add(f"  planner-visible {m.planner_visible_chars}자 / full {m.full_packet_chars}자")
    for block, chars in sorted(m.block_chars.items(), key=lambda kv: -kv[1]):
        add(f"  {block.value:<28} {chars:>6}자  {m.block_items[block]:>3}건")
    add(f"  trimmed_blocks={list(packet.trimmed_blocks)}")
    add(f"  fingerprint={packet_fingerprint(packet)}")

    return "\n".join(out)
