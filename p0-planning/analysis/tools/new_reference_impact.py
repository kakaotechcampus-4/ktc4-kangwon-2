"""신규 Reference 자료 Impact 재평가 (분석 전용 · 읽기 전용).

`analysis/tmp/inventory_baseline_2026_09_12.json`(175건)과 현재
`analysis/tmp/inventory2.json`(349건)을 대조해 **신규 자료가 실제로 무엇을
늘렸는지**를 계산한다. Production / Reference / Rule을 읽지도 쓰지도 않는다.

핵심 원칙

- 파일 수 증가를 Evidence 증가로 보지 않는다. SHA로 중복을 먼저 제거한다.
- **문서 단위가 아니라 페이지 단위로 연령을 판정한다.** 한 PDF 안에 만3세 면과
  만4세 면이 따로 있는 자료가 실제로 존재하기 때문이다.
- Official / Institution / Public Field Source를 하나의 count로 합치지 않는다.
- 파일명이 아니라 **본문**을 Truth로 본다. 둘이 다르면 둘 다 남긴다.

    python analysis/tools/new_reference_impact.py
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

BASELINE = TMP / "inventory_baseline_2026_09_12.json"
CURRENT = TMP / "inventory2.json"

# --------------------------------------------------------------- 연령 표기

AGE_RANGE = re.compile(r"만?\s*([0-5])\s*[-~∼]\s*([0-5])\s*세")
AGE_LIST = re.compile(r"만?\s*([0-5])\s*[,·.]\s*([0-5])\s*(?:[,·.]\s*([0-5])\s*)?세")
AGE_SINGLE = re.compile(r"만?\s*([0-5])\s*세")
MIXED_WORD = re.compile(r"혼합\s*연?령?")
"""연령 표기 3형태. 범위/열거는 **단일연령 근거가 아니다.**"""


def page_ages(text: str) -> tuple[set[int], bool]:
    """한 페이지의 연령 집합과 '범위/열거 표기가 있었는가'를 돌려준다.

    범위(`만3~5세`)·열거(`만4,5세`)·`혼합` 단어가 하나라도 있으면 그 페이지는
    단일연령 근거가 아니다. 남은 단일 표기만 모아도 마찬가지다 — 같은 면에
    `3세`와 `5세`가 따로 적혀 있으면 그것도 단일연령이 아니다.
    """
    multi = bool(MIXED_WORD.search(text))
    ages: set[int] = set()
    t = text
    for m in AGE_RANGE.finditer(t):
        a, b = int(m.group(1)), int(m.group(2))
        ages |= set(range(min(a, b), max(a, b) + 1))
        multi = True
    t = AGE_RANGE.sub(" ", t)
    for m in AGE_LIST.finditer(t):
        ages |= {int(g) for g in m.groups() if g}
        multi = True
    t = AGE_LIST.sub(" ", t)
    for m in AGE_SINGLE.finditer(t):
        ages.add(int(m.group(1)))
    return ages, multi


def pages_of(rec: dict) -> list[str]:
    p = TEXT / f"{rec['sha12']}.layout.txt"
    if not p.exists():
        return []
    raw = p.read_text("utf-8", errors="replace")
    return [x for x in raw.split("\f") if x.strip()]


# --------------------------------------------------------------- 월 표기

MONTH_TITLE = re.compile(r"(\d{1,2})\s*월")


def page_months(text: str) -> set[int]:
    return {int(m.group(1)) for m in MONTH_TITLE.finditer(text)
            if 1 <= int(m.group(1)) <= 12}


# --------------------------------------------------------------- 분류

def classify(records: list[dict], baseline: list[dict]) -> None:
    old_sha = {r["sha256"] for r in baseline}
    old_path = {r["path"] for r in baseline}
    sha_count = collections.Counter(r["sha256"] for r in records)
    for r in records:
        if r["path"] in old_path and r["sha256"] in old_sha:
            r["_cls"] = "EXISTING_SOURCE"
        elif r["sha256"] in old_sha:
            r["_cls"] = "DUPLICATE"
        elif sha_count[r["sha256"]] > 1:
            r["_cls"] = "POSSIBLE_DUPLICATE"
        else:
            r["_cls"] = "NEW_SOURCE"


def enrich(records: list[dict]) -> None:
    """페이지 단위 연령/월과 단일연령 근거를 계산해 붙인다."""
    for r in records:
        pages = pages_of(r)
        r["_page_count"] = len(pages)
        per_page = []
        for i, txt in enumerate(pages, 1):
            ages, multi = page_ages(txt)
            ages = {a for a in ages if 3 <= a <= 5}  # P0 Target
            per_page.append({
                "page": i,
                "ages": sorted(ages),
                "has_range_or_list": multi,
                "single_age": (sorted(ages)[0] if len(ages) == 1 and not multi
                               else None),
                "months": sorted(page_months(txt)),
            })
        r["_pages"] = per_page
        r["_single_ages"] = sorted({p["single_age"] for p in per_page
                                    if p["single_age"] is not None})
        r["_all_ages"] = sorted({a for p in per_page for a in p["ages"]})


def main() -> int:
    base = json.loads(BASELINE.read_text("utf-8"))
    cur = json.loads(CURRENT.read_text("utf-8"))
    classify(cur, base)
    enrich(cur)

    old = [r for r in cur if r["_cls"] == "EXISTING_SOURCE"]
    new = [r for r in cur if r["_cls"] != "EXISTING_SOURCE"]

    line = "=" * 92
    print(line)
    print(" §1. Repository 상태와 신규 Source 식별")
    print(line)
    print(f"  baseline (2026-09-12 inventory): {len(base)}건")
    print(f"  현재 references/samples        : {len(cur)}건")
    print(f"  분류: {dict(collections.Counter(r['_cls'] for r in cur))}")
    print(f"\n  신규 {len(new)}건 내역")
    print(f"    문서군   : {dict(collections.Counter(r['dir'] for r in new))}")
    print(f"    doc_type : "
          f"{dict(collections.Counter(r['body2']['doc_type'] for r in new))}")
    print(f"    판독     : {dict(collections.Counter(r['readable'] for r in new))}")
    print(f"    설립유형 : "
          f"{dict(collections.Counter(r['filename'].get('establishment') for r in new))}")

    old_inst = {r["filename"].get("institution") for r in old}
    new_inst = collections.Counter(r["filename"].get("institution") for r in new)
    brand = {i: n for i, n in new_inst.items() if i not in old_inst}
    print(f"    기관     : 신규 파일이 속한 기관 {len(new_inst)}곳, "
          f"그중 기존에 없던 기관 {len(brand)}곳")

    # ------------------------------------------------------- §4/§5 Age evidence
    print("\n" + line)
    print(" §4-5. Age Evidence — 페이지 단위 단일연령 근거")
    print(line)

    def age_stats(recs, label):
        out = {}
        for age in (3, 4, 5):
            single_pages = [
                (r, p) for r in recs for p in r["_pages"]
                if p["single_age"] == age
            ]
            single_files = {r["path"] for r, _ in single_pages}
            single_insts = {r["filename"].get("institution") for r, _ in single_pages}
            any_pages = [(r, p) for r in recs for p in r["_pages"] if age in p["ages"]]
            any_insts = {r["filename"].get("institution") for r, _ in any_pages}
            mixed_only_insts = any_insts - single_insts
            out[age] = {
                "single_pages": len(single_pages),
                "single_files": len(single_files),
                "single_institutions": len(single_insts),
                "single_institution_names": sorted(x for x in single_insts if x),
                "any_institutions": len(any_insts),
                "mixed_only_institutions": len(mixed_only_insts),
            }
        print(f"\n  [{label}]  문서 {len(recs)}건")
        print(f"  {'':4}{'단일연령 면':>12}{'단일연령 파일':>14}"
              f"{'단일연령 기관':>14}{'연령 언급 기관':>15}{'혼합만 있는 기관':>17}")
        for age in (3, 4, 5):
            s = out[age]
            print(f"  만{age}세{s['single_pages']:>12}{s['single_files']:>14}"
                  f"{s['single_institutions']:>14}{s['any_institutions']:>15}"
                  f"{s['mixed_only_institutions']:>17}")
        return out

    before = age_stats(old, "BEFORE — 기존 175건")
    after_all = age_stats(cur, "AFTER — 전체 349건")
    after_new = age_stats(new, "신규 174건만")

    print("\n  만4세 단일연령 근거 기관 (전체 corpus)")
    for i in after_all[4]["single_institution_names"]:
        print(f"    - {i}")
    print("\n  만4세 단일연령 근거 기관 (신규분)")
    for i in after_new[4]["single_institution_names"]:
        print(f"    - {i}")

    out = TMP / "new_reference_impact.json"
    out.write_text(json.dumps({
        "counts": {"baseline": len(base), "current": len(cur), "new": len(new)},
        "before": before, "after": after_all, "new_only": after_new,
        "records": [
            {k: r[k] for k in ("path", "dir", "name", "sha12", "_cls",
                               "_page_count", "_pages", "_single_ages",
                               "_all_ages", "readable")} | {
                "doc_type": r["body2"]["doc_type"],
                "institution": r["filename"].get("institution"),
                "establishment": r["filename"].get("establishment"),
                "fn_month": r["filename"].get("month"),
                "body_month": r["body2"]["month"].get("first"),
            }
            for r in cur
        ],
    }, ensure_ascii=False), encoding="utf-8")
    print(f"\n  저장: {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
