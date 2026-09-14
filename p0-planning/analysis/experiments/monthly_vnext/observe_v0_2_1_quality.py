"""Monthly v1 + Activity v0.2.1 실제 생성 결과 관찰 (분석 전용 · 읽기 전용).

Production Composition이 조립한 실제 Use Case를 그대로 실행하고, 결과를
**보기 좋게 고치지 않고** 있는 그대로 출력한다. Rule·Reference·Code를 건드리지
않는다.

    python analysis/experiments/monthly_vnext/observe_v0_2_1_quality.py

12 Case:
    만3세  3월 / 7월 / 9월 / 11월
    만4세  4월 / 6월 / 8월 / 12월
    만5세  5월 / 9월 / 1월 / 2월
"""

from __future__ import annotations

import collections
import io
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from ssuksak.adapters.json_activity_reference_repository import (  # noqa: E402
    production_activity_reference_repository,
)
from ssuksak.dev.monthly_wiring import build_monthly_wiring  # noqa: E402
from ssuksak.planning.application.monthly_dto import (  # noqa: E402
    GenerateMonthlyPlanCommand,
)
from ssuksak.planning.domain.provenance import EvidenceSourceType  # noqa: E402

CATALOG_ID = "ssuksak.outdoor-activity-reference"
VERSION = "activity-reference-v0.2.1"
OUTDOOR = "outdoor_play"

CASES = [
    (3, [3, 7, 9, 11]),
    (4, [4, 6, 8, 12]),
    (5, [5, 9, 1, 2]),
]

CATALOG = production_activity_reference_repository().get_catalog(CATALOG_ID, VERSION)
BY_ID = {a.activity_id: a for a in CATALOG.activities}
RAW = json.loads(
    (ROOT / "data" / "activities" / "activity_reference_v0_2_1.json").read_text("utf-8")
)
RAW_BY_ID = {a["activity_id"]: a for a in RAW["activities"]}
ORIGINS = {o["origin_id"]: o for o in RAW["origins"]}

FRAGMENTS = ("건너기", "장화 신고 물웅덩이", "우리집에 왜 왔니?", "놀이를 해요.")


def target_month(month: int) -> str:
    return f"{2026 if month >= 3 else 2027}-{month:02d}"


def run_case(age: int, month: int):
    tm = target_month(month)
    w = build_monthly_wiring(target_month=tm, school_year=2026, ages=frozenset({age}))
    result = w.generate.execute(
        GenerateMonthlyPlanCommand(
            parent_yearly_plan_id=w.parent_yearly.plan_id.value,
            school_year=w.school_year,
            target_month=w.target_month,
            daycare=w.daycare,
            classroom=w.classroom,
            planning_setup=w.planning_setup,
            template_ref=w.template_ref,
            safety_rule=w.safety_rule,
            catalog=w.catalog,
            activity_catalog=w.activity_catalog,
        )
    )
    return result.plan, result.run


def theme_of(plan):
    section = plan.section("theme")
    if not section or not section.items:
        return None, None
    item = section.items[0]
    theme_id = next(
        (e.source_id for e in item.evidence
         if e.source_type is EvidenceSourceType.THEME_REFERENCE),
        None,
    )
    return item.value, theme_id


def activity_id_of(item):
    for e in item.evidence:
        if e.source_type is EvidenceSourceType.ACTIVITY_REFERENCE:
            return e.source_id
    return None


def report_case(age: int, month: int) -> dict:
    plan, run = run_case(age, month)
    tm = target_month(month)
    theme_label, theme_id = theme_of(plan)
    traces = {t.week_id: t for t in run.activity_selection_traces}
    items = plan.section(OUTDOOR).items

    print("\n" + "=" * 92)
    print(f" {tm}  만{age}세   Theme: {theme_label}   (theme_id={theme_id})")
    print(f" catalog={run.activity_catalog_version}  "
          f"weeks={run.week_period_count}  "
          f"filled={run.activity_filled_cell_count}  "
          f"unfilled={run.activity_unfilled_cell_count}  "
          f"llm_invoked={run.llm_invoked}")
    print("=" * 92)

    rows = []
    for item in items:
        wid = item.week_id.value if item.week_id else "-"
        aid = activity_id_of(item)
        t = traces.get(wid)
        cand = BY_ID.get(aid)
        raw = RAW_BY_ID.get(aid, {})
        insts = raw.get("observed_institutions", [])
        row = {
            "week": wid,
            "label": item.value,
            "activity_id": aid,
            "evidence_strength": t.evidence_strength if t else None,
            "theme_matched": t.theme_matched if t else None,
            "display_quality": raw.get("display_quality"),
            "display_review": raw.get("display_quality_review_status"),
            "reason": t.reason if t else None,
            "candidate_count": t.candidate_count if t else None,
            "repeat_penalty": t.repeat_penalty if t else None,
            "display_penalty": t.display_quality_penalty if t else None,
            "curriculum_penalty": t.curriculum_repeat_penalty if t else None,
            "domains": list(t.selected_curriculum_domains) if t else [],
            "all_penalized": t.all_candidates_penalized if t else None,
            "inst_count": raw.get("observed_institution_count"),
            "institutions": insts,
            "evidence_count": raw.get("evidence_count"),
            "theme_links": [tl["theme_id"] for tl in raw.get("theme_links", [])],
        }
        rows.append(row)

        print(f"\n  {wid}  {item.value}")
        print(f"       activity_id       : {aid}")
        print(f"       evidence_strength : {row['evidence_strength']}"
              f"   (전체 evidence {row['evidence_count']},"
              f" 관찰 기관 {row['inst_count']})")
        print(f"       theme_matched     : {row['theme_matched']}"
              f"   theme_links={row['theme_links']}")
        print(f"       display_quality   : {row['display_quality']}"
              f" / {row['display_review']}")
        print(f"       curriculum        : {row['domains']}")
        print(f"       trace             : reason={row['reason']}"
              f" candidates={row['candidate_count']}"
              f" penalties(repeat={row['repeat_penalty']},"
              f" display={row['display_penalty']},"
              f" curriculum={row['curriculum_penalty']})"
              f" all_penalized={row['all_penalized']}")

    # ---------- 관찰 지표 (판정이 아니라 측정값이다)
    labels = [r["label"] for r in rows]
    theme_hit = sum(1 for r in rows if r["theme_matched"])
    linked = sum(1 for r in rows if theme_id and theme_id in r["theme_links"])
    dup = len(labels) - len(set(labels))
    strengths = [r["evidence_strength"] for r in rows]
    monotone = all(a >= b for a, b in zip(strengths, strengths[1:]))
    all_domains = [d for r in rows for d in r["domains"]]
    single_inst = [r["label"] for r in rows if (r["inst_count"] or 0) <= 1]
    frag_hit = [x for x in labels if x in FRAGMENTS]
    pool = CATALOG.eligible_candidates(
        section_key=OUTDOOR, calendar_month=month, ages=frozenset({age})
    )

    print(f"\n  ── 측정값")
    print(f"     후보 pool          : {len(pool)}개  (주차 {len(rows)}개 사용)")
    print(f"     theme_matched      : {theme_hit}/{len(rows)}"
          f"   (theme_links에 anchor 포함: {linked}/{len(rows)})")
    print(f"     중복 label         : {dup}")
    print(f"     evidence_strength  : {strengths}  내림차순={monotone}")
    print(f"     누리과정 영역 분포 : {dict(collections.Counter(all_domains))}")
    print(f"     단일기관 근거 Activity : {len(single_inst)}건 {single_inst}")
    print(f"     Fragment 재발      : {frag_hit if frag_hit else '없음'}")

    return {
        "target_month": tm,
        "age": age,
        "theme": theme_label,
        "theme_id": theme_id,
        "pool": len(pool),
        "rows": rows,
        "theme_hit": theme_hit,
        "theme_linked": linked,
        "dup": dup,
        "strengths": strengths,
        "strength_monotone": monotone,
        "domains": dict(collections.Counter(all_domains)),
        "single_inst": single_inst,
        "fragments": frag_hit,
    }


def main() -> int:
    results = []
    for age, months in CASES:
        for m in months:
            results.append(report_case(age, m))

    print("\n" + "=" * 92)
    print(" 요약")
    print("=" * 92)
    print(f"  {'월':<9}{'연령':<6}{'주차':<5}{'pool':<6}{'theme_hit':<11}"
          f"{'anchor링크':<11}{'중복':<5}{'강도내림차순':<14}{'단일기관':<9}{'Fragment'}")
    for r in results:
        print(f"  {r['target_month']:<9}만{r['age']}세  {len(r['rows']):<5}{r['pool']:<6}"
              f"{r['theme_hit']}/{len(r['rows']):<9}"
              f"{r['theme_linked']}/{len(r['rows']):<9}"
              f"{r['dup']:<5}{str(r['strength_monotone']):<14}"
              f"{len(r['single_inst']):<9}{len(r['fragments'])}")

    # 연령 비교: 같은 월을 다른 연령으로 돌렸을 때 결과가 달라지는가
    print("\n  ── 연령 차이 관찰 (9월을 만3/4/5세로)")
    for age in (3, 4, 5):
        plan, _ = run_case(age, 9)
        labels = [i.value for i in plan.section(OUTDOOR).items]
        pool = CATALOG.eligible_candidates(
            section_key=OUTDOOR, calendar_month=9, ages=frozenset({age})
        )
        print(f"     만{age}세 (후보 {len(pool)}): {labels}")

    out = ROOT / "analysis" / "tmp" / "monthly_v0_2_1_quality.json"
    out.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n  저장: {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
