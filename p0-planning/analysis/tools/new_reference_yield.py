"""신규 Reference의 실제 Evidence 수확량 측정 (분석 전용 · 읽기 전용).

`new_reference_impact.py`가 만든 페이지 단위 연령 판정을 받아,

    - 월 × 연령 Coverage Matrix
    - 바깥놀이 행 보유 여부 (Activity Evidence 가능성)
    - Week Experience / Sub-theme 구조 보유 여부
    - 기존 v0.2.1 Catalog에 없는 Activity 후보 관찰 수

를 계산한다. **Catalog에 반영하지 않는다.** 관찰만 한다.

    python analysis/tools/new_reference_yield.py
"""

from __future__ import annotations

import collections
import io
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
TMP = ROOT / "analysis" / "tmp"
TEXT = TMP / "corpus_text"
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

IMPACT = TMP / "new_reference_impact.json"
CATALOG = ROOT / "data" / "activities" / "activity_reference_v0_2_1.json"

# --------------------------------------------------------- 원문 label 어휘

OUTDOOR_ROW = re.compile(r"(바깥\s*놀?이?|실외\s*놀?이?|바 깥|실 외|산책|나들이|텃밭)")
"""바깥놀이 행 표지. **원문 label 그대로** 본다."""

WEEK_LABELS = (
    "소주제", "주별 주제", "주간 주제", "예상 놀이", "예상놀이", "기대되는 놀이",
    "놀이 흐름", "놀이흐름", "주간 경험", "관심", "흥미", "기대 놀이", "기대놀이",
    "주제 선정 배경", "기대되는 모습", "놀이 이야기", "함께 하는 놀이",
)
"""Week Experience / Sub-theme 후보 원문 label. Canonical화하지 않고 그대로 센다."""

WEEK_NUM = re.compile(r"([1-5])\s*주")


def pages_of(sha12: str) -> list[str]:
    p = TEXT / f"{sha12}.layout.txt"
    if not p.exists():
        return []
    return [x for x in p.read_text("utf-8", errors="replace").split("\f") if x.strip()]


def grade(single_inst: int, any_inst: int, has_outdoor: int) -> str:
    """월 × 연령 Cell 등급.

    판정 기준 (보고서에 명시한다):
        STRONG     단일연령 독립기관 >= 3
        MODERATE   단일연령 독립기관 2, 또는 1이면서 바깥놀이 행 보유
        WEAK       단일연령 독립기관 1 (바깥놀이 행 없음), 또는 혼합만 >= 3
        VERY_WEAK  그 외 (혼합 근거만 2 이하 또는 근거 없음)
    """
    if single_inst >= 3:
        return "STRONG"
    if single_inst == 2 or (single_inst == 1 and has_outdoor):
        return "MODERATE"
    if single_inst == 1 or any_inst >= 3:
        return "WEAK"
    return "VERY_WEAK"


def main() -> int:
    D = json.loads(IMPACT.read_text("utf-8"))
    recs = D["records"]
    cat = json.loads(CATALOG.read_text("utf-8"))
    cat_labels = {a["label"] for a in cat["activities"]}
    cat_aliases = {x for a in cat["activities"] for x in a.get("aliases", [])}
    known = cat_labels | cat_aliases
    ingested = {o["path"] for o in cat["origins"]}

    # ---------------- 페이지 단위 관찰 레코드
    obs = []
    for r in recs:
        if r["dir"] not in ("monthly", "weekly", "yearly"):
            continue
        pages = pages_of(r["sha12"])
        for info in r["_pages"]:
            i = info["page"] - 1
            if i >= len(pages):
                continue
            txt = pages[i]
            outdoor_lines = [ln.strip() for ln in txt.splitlines()
                             if OUTDOOR_ROW.search(ln)]
            week_hits = [w for w in WEEK_LABELS if w in txt]
            obs.append({
                "path": r["path"], "dir": r["dir"], "cls": r["_cls"],
                "institution": r["institution"], "doc_type": r["doc_type"],
                "page": info["page"], "ages": info["ages"],
                "single_age": info["single_age"],
                "fn_month": r["fn_month"],
                "page_months": info["months"],
                "outdoor_lines": len(outdoor_lines),
                "outdoor_sample": outdoor_lines[:3],
                "week_labels": week_hits,
                "week_numbers": sorted({int(m.group(1))
                                        for m in WEEK_NUM.finditer(txt)}),
                "ingested": r["path"] in ingested,
            })

    line = "=" * 96
    print(line)
    print(" §6. 월 × 연령 Coverage Matrix (Monthly 문서 기준)")
    print(line)
    print("  판정 기준: STRONG 단일연령 독립기관>=3 / MODERATE 2 또는 1+바깥놀이행 /")
    print("             WEAK 1 또는 혼합기관>=3 / VERY_WEAK 그 외")

    def month_of(o):
        if o["dir"] != "monthly":
            return None
        if o["fn_month"]:
            return o["fn_month"]
        return o["page_months"][0] if o["page_months"] else None

    def matrix(subset, title):
        cells = {}
        for m in range(1, 13):
            for age in (3, 4, 5):
                rows = [o for o in subset
                        if month_of(o) == m and age in o["ages"]]
                single = {o["institution"] for o in rows if o["single_age"] == age}
                anyi = {o["institution"] for o in rows}
                outdoor = sum(1 for o in rows
                              if o["single_age"] == age and o["outdoor_lines"])
                cells[(m, age)] = {
                    "single_inst": len(single), "any_inst": len(anyi),
                    "outdoor": outdoor,
                    "grade": grade(len(single), len(anyi), outdoor),
                    "institutions": sorted(x for x in single if x),
                }
        print(f"\n  [{title}]")
        print(f"  {'월':<5}{'만3세':<34}{'만4세':<34}{'만5세'}")
        for m in range(1, 13):
            row = f"  {m:>2}월 "
            for age in (3, 4, 5):
                c = cells[(m, age)]
                row += (f"{c['grade']:<11}(단{c['single_inst']}/전{c['any_inst']}"
                        f"/바{c['outdoor']})".ljust(34))
            print(row)
        return cells

    monthly = [o for o in obs if o["dir"] == "monthly"]
    before = matrix([o for o in monthly if o["cls"] == "EXISTING_SOURCE"],
                    "BEFORE — 기존 자료만")
    after = matrix(monthly, "AFTER — 신규 포함 전체")

    print("\n  등급 분포 변화")
    gb = collections.Counter(c["grade"] for c in before.values())
    ga = collections.Counter(c["grade"] for c in after.values())
    for g in ("STRONG", "MODERATE", "WEAK", "VERY_WEAK"):
        print(f"    {g:<11} {gb.get(g,0):>3} → {ga.get(g,0):>3}")

    print("\n  취약 월 상세 (6·7·8·1월)")
    for m in (6, 7, 8, 1):
        for age in (3, 4, 5):
            b, a = before[(m, age)], after[(m, age)]
            if b["grade"] != a["grade"] or b["single_inst"] != a["single_inst"]:
                print(f"    {m:>2}월 만{age}세  {b['grade']}(단{b['single_inst']}) → "
                      f"{a['grade']}(단{a['single_inst']})   기관={a['institutions']}")

    # ---------------- §7 Week Experience
    print("\n" + line)
    print(" §7. Week Experience / Sub-theme 구조")
    print(line)
    for title, subset in (("BEFORE", [o for o in monthly if o["cls"] == "EXISTING_SOURCE"]),
                          ("신규분", [o for o in monthly if o["cls"] != "EXISTING_SOURCE"])):
        has = [o for o in subset if o["week_labels"]]
        insts = {o["institution"] for o in has}
        wk = [o for o in subset if o["week_numbers"]]
        print(f"\n  [{title}] monthly 면 {len(subset)}개")
        print(f"    Week label 보유 면 : {len(has)}  (기관 {len(insts)}곳)")
        print(f"    주차 번호 보유 면  : {len(wk)}")
        c = collections.Counter(w for o in has for w in o["week_labels"])
        print(f"    원문 label 빈도    : {dict(c.most_common(10))}")
        s4 = [o for o in has if o["single_age"] == 4]
        print(f"    만4세 단일연령 Week Evidence 면: {len(s4)}  "
              f"기관 {sorted({o['institution'] for o in s4})}")

    # ---------------- §8 Activity 후보 수확 가능성
    print("\n" + line)
    print(" §8. 바깥놀이 행 보유 (Activity Evidence 가능성)")
    print(line)
    for title, subset in (("BEFORE 기존", [o for o in monthly if o["cls"] == "EXISTING_SOURCE"]),
                          ("신규", [o for o in monthly if o["cls"] != "EXISTING_SOURCE"])):
        od = [o for o in subset if o["outdoor_lines"]]
        print(f"\n  [{title}] monthly 면 {len(subset)}, 바깥놀이 행 보유 면 {len(od)} "
              f"(기관 {len({o['institution'] for o in od})}곳)")
        for age in (3, 4, 5):
            s = [o for o in od if o["single_age"] == age]
            print(f"    만{age}세 단일연령 + 바깥놀이 행: 면 {len(s):>3}  "
                  f"기관 {len({o['institution'] for o in s})}")
    print(f"\n  v0.2.1이 실제로 ingest한 monthly 면: "
          f"{len([o for o in monthly if o['ingested']])}")
    print(f"  미ingest monthly 면 중 바깥놀이 행 보유: "
          f"{len([o for o in monthly if not o['ingested'] and o['outdoor_lines']])}")

    (TMP / "new_reference_yield.json").write_text(
        json.dumps({"observations": obs,
                    "before_matrix": {f"{m}-{a}": v for (m, a), v in before.items()},
                    "after_matrix": {f"{m}-{a}": v for (m, a), v in after.items()}},
                   ensure_ascii=False),
        encoding="utf-8")
    print(f"\n  저장: analysis/tmp/new_reference_yield.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
