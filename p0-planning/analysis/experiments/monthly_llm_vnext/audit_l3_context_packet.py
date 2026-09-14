"""L3 Monthly Context Packet 감사 (§32 / §37 / §38).

Production Builder를 그대로 쓴다. 별도 Prototype 경로를 만들지 않는다.

    PYTHONPATH=src python -m analysis.experiments.monthly_llm_vnext.audit_l3_context_packet
"""

from __future__ import annotations

import datetime
import json
import pathlib
import time

from ssuksak.adapters.json_activity_reference_repository import (
    production_activity_reference_repository,
)
from ssuksak.planning.context import (
    MonthlyContextPacketBuilder,
    MonthlyContextRequest,
    PackedBlock,
    measure,
    packet_fingerprint,
    render_debug_packet,
    validate_packet,
)
from ssuksak.planning.domain.identifiers import PeriodKey
from ssuksak.planning.domain.parent_lineage import ParentYearlyLineage
from ssuksak.planning.retrieval import (
    JsonInstitutionEvidenceRepository,
    MonthlyEvidenceRetriever,
)

ROOT = pathlib.Path(__file__).resolve().parents[3]
OUT = ROOT / "analysis" / "tmp" / "l3_audit.txt"

CATALOG_ID = "ssuksak.outdoor-activity-reference"
CATALOG_VERSION = "activity-reference-v0.2.1"

CASES = [
    ("2026-03", (3,)),
    ("2026-06", (4,)),
    ("2026-07", (4,)),
    ("2026-08", (4,)),
    ("2027-02", (5,)),
]

_THEMES = json.loads(
    (ROOT / "data" / "themes" / "theme_reference_v0.json").read_text("utf-8")
)
THEME_BY_MONTH: dict[int, tuple[str, str]] = {}
for _t in _THEMES["themes"]:
    for _m in _t.get("applicable_months", []):
        THEME_BY_MONTH.setdefault(_m, (_t["theme_id"], _t["label"]))


def request(target_month: str, ages: tuple[int, ...]) -> MonthlyContextRequest:
    key = PeriodKey(target_month)
    theme_id, label = THEME_BY_MONTH[key.calendar_month]
    lineage = ParentYearlyLineage(
        parent_yearly_plan_id="yp_audit_001",
        parent_yearly_period_key=target_month,
        parent_yearly_theme_id=theme_id,
        parent_yearly_value=label,
        reference_catalog_id=_THEMES["catalog_id"],
        reference_version=_THEMES["catalog_version"],
        confirmed_at=datetime.datetime(2026, 2, 20, 9, 0, tzinfo=datetime.UTC),
        confirmed_by="actor_audit_001",
    )
    return MonthlyContextRequest(
        school_year="2026",
        target_month=key,
        classroom_ages=ages,
        age_mode="SINGLE" if len(ages) == 1 else "MIXED",
        parent_lineage=lineage,
        daycare_ref="dc_audit",
        classroom_ref="cr_audit",
    )


def main() -> None:
    lines: list[str] = []

    def emit(text: str = "") -> None:
        print(text)
        lines.append(text)

    t0 = time.perf_counter()
    store = JsonInstitutionEvidenceRepository().get_store()
    catalog = production_activity_reference_repository().get_catalog(
        CATALOG_ID, CATALOG_VERSION
    )
    load = time.perf_counter() - t0

    retriever = MonthlyEvidenceRetriever(store, activity_catalog=catalog)
    builder = MonthlyContextPacketBuilder(
        retriever, store, activity_catalog=catalog
    )

    emit("=" * 78)
    emit("§32  FIVE-CASE INSPECTION")
    emit("=" * 78)
    emit(
        f"{'Case':<18}{'theme':<14}{'wk':>3}{'age':>10}"
        f"{'inst':>6}{'ctr':>5}{'wkex':>6}{'ref':>5}{'oth':>5}"
        f"{'출처':>5}{'json':>8}{'내용':>7}"
    )

    packets = {}
    for target_month, ages in CASES:
        req = request(target_month, ages)
        packet = builder.build(req)
        validate_packet(packet, catalog=catalog)
        packets[(target_month, ages)] = packet

        m = measure(packet)
        sizes = packet.block_sizes()
        groups = {
            i.source_group
            for i in packet.institution_evidence + packet.other_outdoor_evidence
        } | {c.source_group for c in packet.week_experience_candidates}
        emit(
            f"{target_month + ' 만' + '/'.join(map(str, ages)) + '세':<18}"
            f"{packet.parent_theme.theme_value:<14}"
            f"{len(packet.week_slots):>3}"
            f"{packet.age_context.overall_strength.value:>10}"
            f"{sizes[PackedBlock.INSTITUTION_EVIDENCE]:>6}"
            f"{sizes[PackedBlock.AGE_CONTRAST]:>5}"
            f"{sizes[PackedBlock.WEEK_EXPERIENCE]:>6}"
            f"{sizes[PackedBlock.REFERENCE_ACTIVITIES]:>5}"
            f"{sizes[PackedBlock.OTHER_OUTDOOR]:>5}"
            f"{len(groups):>5}"
            f"{m.planner_visible_chars:>8}"
            f"{m.content_chars:>7}"
        )

    emit()
    emit("빈 Optional Block")
    for (target_month, ages), packet in packets.items():
        empty = [
            name
            for name, value in (
                ("age_contrast", packet.age_contrast_evidence),
                ("official_play", packet.official_play_context),
                ("official_topic", packet.official_topic_context),
                ("week_experience", packet.week_experience_candidates),
            )
            if not value
        ]
        emit(f"  {target_month} 만{ages}: {empty or '없음'}  trimmed={list(packet.trimmed_blocks)}")

    emit()
    emit("=" * 78)
    emit("§22  BLOCK별 Context 점유")
    emit("=" * 78)
    total_json = 0
    total_content = 0
    agg: dict[PackedBlock, int] = {b: 0 for b in PackedBlock}
    for packet in packets.values():
        m = measure(packet)
        total_json += m.planner_visible_chars
        total_content += m.content_chars
        for b, c in m.block_chars.items():
            agg[b] += c
    n = len(packets)
    total_render = sum(
        len(render_debug_packet(p).split("## SIZE")[0]) for p in packets.values()
    )
    emit(f"  평균 planner-visible JSON  {total_json / n:,.0f}자   (Budget 판정 기준)")
    emit(f"  평균 debug render          {total_render / n:,.0f}자   (Prototype 5,407자와 비교 가능한 쪽)")
    emit(f"  평균 내용 문자            {total_content / n:,.0f}자   (활동명·주제 등 자연어만)")
    emit(f"  JSON / 내용 배율           {total_json / total_content:.2f}x")
    emit(f"  render / 내용 배율         {total_render / total_content:.2f}x")
    emit()
    for b, c in sorted(agg.items(), key=lambda kv: -kv[1]):
        emit(f"  {b.value:<28}{c / n:>8,.0f}자  ({c / total_json * 100:>4.1f}%)")

    emit()
    emit("=" * 78)
    emit("§37  AGE DIFFERENTIATION  (2026-07 만3 / 만4 / 만5)")
    emit("=" * 78)
    by_age = {}
    for age in (3, 4, 5):
        packet = builder.build(request("2026-07", (age,)))
        validate_packet(packet, catalog=catalog)
        by_age[age] = packet
        s = packet.block_sizes()
        emit(
            f"  만{age}세 strength={packet.age_context.overall_strength.value:<10}"
            f" 단{packet.age_context.per_age[0].single_age_institution_count}"
            f"/전{packet.age_context.per_age[0].age_mentioning_institution_count}"
            f"/바{packet.age_context.per_age[0].single_age_outdoor_page_count}"
            f"  inst={s[PackedBlock.INSTITUTION_EVIDENCE]}"
            f" ctr={s[PackedBlock.AGE_CONTRAST]}"
            f" ref={s[PackedBlock.REFERENCE_ACTIVITIES]}"
            f" oth={s[PackedBlock.OTHER_OUTDOOR]}"
        )

    def ids(packet, attr):
        return {i.evidence_id for i in getattr(packet, attr)}

    emit()
    for attr in (
        "institution_evidence",
        "week_experience_candidates",
        "other_outdoor_evidence",
    ):
        a3, a4, a5 = (ids(by_age[a], attr) for a in (3, 4, 5))
        emit(
            f"  {attr:<28} 3∩4={len(a3 & a4):>3} 4∩5={len(a4 & a5):>3} "
            f"3∩5={len(a3 & a5):>3} 3연령공통={len(a3 & a4 & a5):>3}"
        )
    r3, r4, r5 = (
        {a.activity_id for a in by_age[a].reference_activities} for a in (3, 4, 5)
    )
    emit(
        f"  {'reference_activities':<28} 3∩4={len(r3 & r4):>3} 4∩5={len(r4 & r5):>3} "
        f"3∩5={len(r3 & r5):>3} 3연령공통={len(r3 & r4 & r5):>3}"
    )
    emit()
    emit(
        f"  fingerprint 만3={packet_fingerprint(by_age[3])[:16]} "
        f"만4={packet_fingerprint(by_age[4])[:16]} "
        f"만5={packet_fingerprint(by_age[5])[:16]}"
    )

    emit()
    emit("=" * 78)
    emit("§38  PERFORMANCE")
    emit("=" * 78)
    emit(f"  store + catalog load    {load:.3f}s")

    req = request("2026-07", (4,))
    t = time.perf_counter()
    for _ in range(20):
        builder.build(req)
    emit(f"  packet build (1건)      {(time.perf_counter() - t) / 20 * 1000:.2f}ms")

    t = time.perf_counter()
    for _ in range(20):
        for target_month, ages in CASES:
            builder.build(request(target_month, ages))
    emit(f"  5-case batch            {(time.perf_counter() - t) / 20 * 1000:.2f}ms")

    packet = packets[("2026-07", (4,))]
    t = time.perf_counter()
    for _ in range(200):
        measure(packet)
    emit(f"  serialization(measure)  {(time.perf_counter() - t) / 200 * 1000:.2f}ms")

    emit()
    emit("=" * 78)
    emit("§40  DETERMINISM")
    emit("=" * 78)
    fresh_store = JsonInstitutionEvidenceRepository().get_store()
    fresh = MonthlyContextPacketBuilder(
        MonthlyEvidenceRetriever(fresh_store, activity_catalog=catalog),
        fresh_store,
        activity_catalog=catalog,
    )
    for target_month, ages in CASES:
        req = request(target_month, ages)
        a = packet_fingerprint(builder.build(req))
        b = packet_fingerprint(builder.build(req))
        c = packet_fingerprint(fresh.build(req))
        emit(f"  {target_month} 만{ages}  동일={a == b == c}  {a[:24]}")

    emit()
    emit("=" * 78)
    emit("§33~§36  CASE 본문")
    emit("=" * 78)
    for target_month in ("2026-06", "2026-07", "2026-08", "2027-02"):
        ages = dict(CASES)[target_month]
        emit()
        emit(render_debug_packet(packets[(target_month, ages)]))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n-> {OUT}")


if __name__ == "__main__":
    main()
