"""L2 Retrieval 품질 감사 (분석 전용 · Production 무변경).

실제 Production Retriever를 호출한다. 결과를 보기 좋게 고치지 않는다.

    python analysis/experiments/monthly_llm_vnext/audit_l2_retrieval.py
"""

from __future__ import annotations

import collections
import io
import json
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from ssuksak.adapters.json_activity_reference_repository import (  # noqa: E402
    production_activity_reference_repository,
)
from ssuksak.planning.retrieval import (  # noqa: E402
    BlockName,
    JsonInstitutionEvidenceRepository,
    MonthlyEvidenceRetriever,
    RetrievalRequest,
)

CATALOG_ID = "ssuksak.outdoor-activity-reference"
CATALOG_VERSION = "activity-reference-v0.2.1"

THEMES = json.loads(
    (ROOT / "data" / "themes" / "theme_reference_v0.json").read_text("utf-8")
)
THEME_BY_MONTH: dict[int, tuple[str, str]] = {}
for t in THEMES["themes"]:
    for m in t.get("applicable_months", []):
        THEME_BY_MONTH.setdefault(m, (t["theme_id"], t["label"]))

CASES = [
    ("2026-03", 3, (3,), 4),
    ("2026-06", 6, (4,), 4),
    ("2026-07", 7, (4,), 5),
    ("2026-08", 8, (4,), 4),
    ("2027-02", 2, (5,), 4),
]

LINE = "=" * 96


def make_request(tm: str, month: int, ages: tuple[int, ...], weeks: int):
    tid, label = THEME_BY_MONTH[month]
    return RetrievalRequest(
        target_month=tm, calendar_month=month, ages=ages, age_mode="SINGLE",
        confirmed_theme_id=tid, confirmed_theme_value=label, week_count=weeks,
    )


def show_block(block, limit: int = 8) -> None:
    print(f"\n  [{block.name.value}]  top_k={block.top_k}  "
          f"반환 {block.size}  eligible pool {block.eligible_pool_size}  "
          f"기관 {block.distinct_institutions}")
    print(f"    reason: {block.retrieval_reason}")
    if block.note:
        print(f"    note  : {block.note}")
    if block.reference_items:
        for it in block.reference_items[:limit]:
            flag = " ※표시품질" if it.has_display_quality_issue else ""
            print(f"      {it.rank:>2}. {it.label}  (근거 {it.evidence_strength}){flag}")
        return
    if not block.items:
        print("      (없음)")
        return
    for it in block.items[:limit]:
        r, t = it.record, it.trace
        age = "".join(map(str, r.age_scope)) or "미상"
        print(f"      · [{t.retrieval_tier.value[:16]:<16}] 만{age}세 "
              f"| {r.institution_id} | {r.text}")


def main() -> int:
    t0 = time.perf_counter()
    store = JsonInstitutionEvidenceRepository().get_store()
    load_s = time.perf_counter() - t0
    catalog = production_activity_reference_repository().get_catalog(
        CATALOG_ID, CATALOG_VERSION
    )
    retriever = MonthlyEvidenceRetriever(store, activity_catalog=catalog)

    print(LINE)
    print(" §17 Performance")
    print(LINE)
    print(f"  store load            {load_s:.3f}s   records {len(store)}")
    print(f"  evidence_store sha    {store.content_sha256}")

    t1 = time.perf_counter()
    results = {tm: retriever.retrieve(make_request(tm, m, a, w))
               for tm, m, a, w in CASES}
    batch = time.perf_counter() - t1
    single = min(
        (lambda: (time.perf_counter(), retriever.retrieve(
            make_request(*CASES[2])), time.perf_counter()))()[2] -
        (lambda: time.perf_counter())()
        for _ in range(1)
    )
    t2 = time.perf_counter()
    retriever.retrieve(make_request(*CASES[2]))
    one = time.perf_counter() - t2
    print(f"  single retrieval      {one*1000:.1f}ms")
    print(f"  5-case batch          {batch*1000:.1f}ms  (case당 {batch/5*1000:.1f}ms)")

    # ---------------------------------------------------------- §14 Quality
    print("\n" + LINE)
    print(" §14 Quality Cases")
    print(LINE)
    for tm, m, ages, weeks in CASES:
        res = results[tm]
        tid, label = THEME_BY_MONTH[m]
        print(f"\n{LINE}\n {tm}  만{'·'.join(map(str,ages))}세  Theme={label}\n{LINE}")
        for name in BlockName:
            show_block(res.blocks[name])

    # ---------------------------------------------------------- §15 연령 차별화
    print("\n" + LINE)
    print(" §15 Age Differentiation Audit — 2026-07 age3 / age4 / age5")
    print(LINE)
    per_age = {}
    for age in (3, 4, 5):
        req = RetrievalRequest(
            target_month="2026-07", calendar_month=7, ages=(age,),
            age_mode="SINGLE", confirmed_theme_id=THEME_BY_MONTH[7][0],
            confirmed_theme_value=THEME_BY_MONTH[7][1], week_count=5,
        )
        per_age[age] = retriever.retrieve(req)

    def ids(res, name):
        b = res.blocks[name]
        if b.reference_items:
            return {i.activity_id for i in b.reference_items}
        return {i.record_id for i in b.items}

    for name in BlockName:
        s3, s4, s5 = (ids(per_age[a], name) for a in (3, 4, 5))
        common = s3 & s4 & s5
        print(f"\n  [{name.value}]")
        print(f"    크기        만3 {len(s3)} · 만4 {len(s4)} · 만5 {len(s5)}")
        print(f"    3개 연령 공통 {len(common)}")
        print(f"    만3∩만4 {len(s3&s4)} · 만4∩만5 {len(s4&s5)} · 만3∩만5 {len(s3&s5)}")
    print("\n  만4세 institution block 실제 내용")
    for it in per_age[4].blocks[BlockName.INSTITUTION_MONTHLY_EVIDENCE].items[:6]:
        print(f"    · 만{''.join(map(str,it.record.age_scope))}세 "
              f"| {it.record.institution_id} | {it.text}")
    print("  만3세 institution block 실제 내용")
    for it in per_age[3].blocks[BlockName.INSTITUTION_MONTHLY_EVIDENCE].items[:6]:
        print(f"    · 만{''.join(map(str,it.record.age_scope))}세 "
              f"| {it.record.institution_id} | {it.text}")

    # ---------------------------------------------------------- §16 편중
    print("\n" + LINE)
    print(" §16 Source Concentration Audit — 기관 상한 ON / OFF")
    print(LINE)
    no_cap = MonthlyEvidenceRetriever(
        store, activity_catalog=catalog, institution_cap=10_000
    )
    print(f"  {'Case':<20}{'Block':<34}{'cap OFF 최다기관 비중':>22}{'cap ON':>10}")
    for tm, m, ages, weeks in CASES:
        req = make_request(tm, m, ages, weeks)
        off, on = no_cap.retrieve(req), results[tm]
        for name in (BlockName.INSTITUTION_MONTHLY_EVIDENCE,
                     BlockName.OTHER_OUTDOOR_EVIDENCE):
            def share(res):
                items = res.blocks[name].items
                if not items:
                    return 0.0, 0
                c = collections.Counter(
                    i.trace.source_diversity_group for i in items
                )
                return c.most_common(1)[0][1] / len(items), len(c)
            so, io_ = share(off)
            sn, in_ = share(on)
            print(f"  {tm} 만{ages[0]}세{'':<6}{name.value:<34}"
                  f"{so:>18.0%} ({io_}기관){sn:>8.0%} ({in_}기관)")

    # ---------------------------------------------------------- §Q6 누출
    print("\n" + LINE)
    print(" Invalid / NEEDS_REVIEW / INDOOR_ALTERNATIVE 누출 검사")
    print(LINE)
    bad = 0
    for tm in results:
        for name in BlockName:
            for it in results[tm].blocks[name].items:
                r = it.record
                if r.extraction_quality.value != "VALID":
                    bad += 1
                    print(f"    누출 {r.extraction_quality.value}: {r.record_id}")
                if r.machine_readability.value != "TEXT_LAYER":
                    bad += 1
                if (name in (BlockName.INSTITUTION_MONTHLY_EVIDENCE,
                             BlockName.OTHER_OUTDOOR_EVIDENCE,
                             BlockName.AGE_CONTRAST_EVIDENCE)
                        and r.setting.value == "INDOOR_ALTERNATIVE"):
                    bad += 1
                    print(f"    누출 INDOOR_ALTERNATIVE: {r.record_id}")
    print(f"  누출 총 {bad}건")

    # ---------------------------------------------------------- §Q7 결정론
    print("\n" + LINE)
    print(" Determinism")
    print(LINE)
    again = {tm: retriever.retrieve(make_request(tm, m, a, w))
             for tm, m, a, w in CASES}
    fresh = MonthlyEvidenceRetriever(
        JsonInstitutionEvidenceRepository().get_store(), activity_catalog=catalog
    )
    third = {tm: fresh.retrieve(make_request(tm, m, a, w)) for tm, m, a, w in CASES}

    def fingerprint(res):
        out = []
        for name in BlockName:
            b = res.blocks[name]
            out.append(
                (name.value,
                 tuple(i.record_id for i in b.items),
                 tuple(i.activity_id for i in b.reference_items))
            )
        return tuple(out)

    same = all(fingerprint(results[k]) == fingerprint(again[k]) == fingerprint(third[k])
               for k in results)
    print(f"  같은 입력 3회(캐시 재사용 2 + 새 Store 1) 결과 동일: {same}")

    # ---------------------------------------------------------- §26~28 명시 검증
    print("\n" + LINE)
    print(" §26~§28 지정 문자열 검증")
    print(LINE)
    checks = {
        "2026-06": ["우리동네를 둘러보아요", "모래로 동네 공원만들기",
                    "깨끗한 우리 동네 만들기"],
        "2026-07": ["물놀이 공원 만들기", "물총놀이", "여름 과일 신체 놀이하기"],
        "2026-08": ["움직이는 교통기관 관찰해요", "우리동네 버스 정류장을 살펴봐요"],
    }
    for tm, wanted in checks.items():
        res = results[tm]
        got = {
            i.text
            for name in (BlockName.INSTITUTION_MONTHLY_EVIDENCE,
                         BlockName.OTHER_OUTDOOR_EVIDENCE,
                         BlockName.AGE_CONTRAST_EVIDENCE)
            for i in res.blocks[name].items
        }
        in_store = {
            r.text for r in store.records
            if r.text in wanted and r.outdoor_activity_eligible
        }
        print(f"\n  {tm}")
        for w in wanted:
            mark = "검색됨" if w in got else ("Store에만 있음" if w in in_store
                                              else "Store에 없음")
            print(f"    {mark:<14} {w}")

    print("\n  2026-06 Reference Block (Rule-only가 최종 선택에서 놓쳤던 후보 확인)")
    for it in results["2026-06"].blocks[BlockName.REFERENCE_ACTIVITIES].reference_items:
        print(f"    {it.rank:>2}. {it.label}")

    print("\n  2027-02 만5세 scarcity 보완")
    res = results["2027-02"]
    print(f"    Reference candidate  {res.blocks[BlockName.REFERENCE_ACTIVITIES].size}"
          f" (pool {res.blocks[BlockName.REFERENCE_ACTIVITIES].eligible_pool_size})")
    print(f"    Other Outdoor        {res.blocks[BlockName.OTHER_OUTDOOR_EVIDENCE].size}")
    print(f"    Week Experience      "
          f"{res.blocks[BlockName.WEEK_EXPERIENCE_CANDIDATES].size}")
    for it in res.blocks[BlockName.OTHER_OUTDOOR_EVIDENCE].items[:6]:
        print(f"      · [{it.record.institution_id}] {it.text}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
