"""Inventory 집계 (A. Corpus Inventory / B. Source Independence).

    python analysis/tools/report_inventory.py

analysis/tmp/inventory.json만 읽는다. Production을 건드리지 않는다.
"""

from __future__ import annotations

import collections
import io
import json
import pathlib
import re
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = pathlib.Path(__file__).resolve().parents[2]
INV = json.loads((ROOT / "analysis" / "tmp" / "inventory.json").read_text("utf-8"))
TEXT = ROOT / "analysis" / "tmp" / "corpus_text"

NEW_DAY = "2026-09-12"


def is_new(r) -> bool:
    return r["mtime_day"] == NEW_DAY


def bar(title):
    print()
    print("=" * 78)
    print(" " + title)
    print("=" * 78)


def counts(rows, key):
    c = collections.Counter()
    for r in rows:
        c[key(r)] += 1
    return c


def delta_table(label, key, fmt=str):
    old = counts([r for r in INV if not is_new(r)], key)
    new = counts([r for r in INV if is_new(r)], key)
    allc = counts(INV, key)
    keys = sorted(allc, key=lambda k: (k is None, k))
    print(f"  {label:<24}{'기존':>7}{'신규':>7}{'전체':>7}")
    for k in keys:
        print(f"    {fmt(k):<22}{old.get(k,0):>7}{new.get(k,0):>7}{allc.get(k,0):>7}")
    print(f"    {'합계':<22}{sum(old.values()):>7}{sum(new.values()):>7}{sum(allc.values()):>7}")


# ============================================================ A. Inventory

bar("A. Corpus Inventory  (기존 / 신규(2026-09-12) / 전체)")

print(f"  전체 파일          : {len(INV)}")
print(f"  기존               : {sum(1 for r in INV if not is_new(r))}")
print(f"  신규(대구 증분)    : {sum(1 for r in INV if is_new(r))}")
print()

delta_table("디렉터리", lambda r: r["dir"])
print()
delta_table("본문 기준 문서유형", lambda r: r["body"]["doc_type"])
print()
delta_table("판독 가능", lambda r: "readable" if r["readable"] else "IMAGE_ONLY/OCR필요")
print()
delta_table("연도(파일명)", lambda r: r["filename"]["year"])
print()
delta_table("설립유형(파일명)", lambda r: r["filename"]["establishment"])

# ---- 기관
bar("A-2. 기관")
inst_all = {r["filename"]["institution"] for r in INV if r["filename"]["institution"]}
inst_old = {
    r["filename"]["institution"]
    for r in INV
    if not is_new(r) and r["filename"]["institution"]
}
inst_new = {
    r["filename"]["institution"] for r in INV if is_new(r) and r["filename"]["institution"]
}
print(f"  기관 수  기존 {len(inst_old)} / 신규 {len(inst_new)} / 전체 {len(inst_all)}")
print(f"  신규로 처음 등장한 기관 {len(inst_new - inst_old)}곳:")
for name in sorted(inst_new - inst_old):
    n = sum(1 for r in INV if r["filename"]["institution"] == name)
    print(f"    {name} ({n}건)")
print(f"  기존에도 있던 기관인데 신규 파일이 추가된 곳:")
for name in sorted(inst_new & inst_old):
    print(f"    {name}")
print(f"  파일명에서 기관을 못 뽑은 파일: "
      f"{sum(1 for r in INV if not r['filename']['institution'])}")

# ---- 연령
bar("A-3. 연령 (본문 Truth)")
age_rows = collections.Counter()
for r in INV:
    for a in r["body"]["ages"]:
        age_rows[a] += 1
print("  본문에서 관찰된 연령 표기가 있는 파일 수 (연령별, 중복 포함)")
for a in sorted(age_rows):
    new_n = sum(1 for r in INV if is_new(r) and a in r["body"]["ages"])
    print(f"    만 {a}세 : 전체 {age_rows[a]:>3}  (신규 {new_n})")
print()
print(f"  본문에 '혼합' 명시 파일 : "
      f"{sum(1 for r in INV if r['body']['explicit_mixed'])} "
      f"(신규 {sum(1 for r in INV if is_new(r) and r['body']['explicit_mixed'])})")
print(f"  본문 연령 표기 없음     : {sum(1 for r in INV if not r['body']['ages'])}")

# ---- 페이지별 연령 (multi-age PDF)
bar("A-4. Multi-page / Multi-age PDF")
multi = []
for r in INV:
    per = [set(p) for p in r["per_page_ages"] if p]
    if len(per) >= 2:
        distinct = {frozenset(p) for p in per}
        if len(distinct) >= 2:
            multi.append((r, [sorted(p) for p in per]))
print(f"  페이지마다 연령 표기가 다른 PDF: {len(multi)}건")
for r, per in multi[:20]:
    print(f"    {r['name'][:60]}")
    print(f"      pages={r['page_count']} 연령표기={per[:8]}")
if len(multi) > 20:
    print(f"    … 외 {len(multi)-20}건")

# ---- filename / body mismatch
bar("A-5. Filename ↔ Body Mismatch  (본문이 Truth)")
mm_age, mm_month, mm_type = [], [], []
for r in INV:
    if not r["readable"]:
        continue
    fa, ba = set(r["filename"]["ages"]), set(r["body"]["ages"])
    if fa and ba and not fa.issubset(ba):
        mm_age.append((r, sorted(fa), sorted(ba)))
    fm = r["filename"]["month"]
    bmv = r["body"]["month"]["first_title_month"]
    if fm and bmv and fm != bmv:
        mm_month.append((r, fm, bmv))
    dirkind = {"yearly": "YEARLY_PLAN", "monthly": "MONTHLY_PLAN", "weekly": "WEEKLY_PLAN"}[
        r["dir"]
    ]
    if r["body"]["doc_type"] != dirkind:
        mm_type.append((r, dirkind, r["body"]["doc_type"]))

print(f"  연령 불일치 (파일명 ⊄ 본문) : {len(mm_age)}건")
for r, fa, ba in mm_age[:15]:
    print(f"    {r['name'][:58]}")
    print(f"      filename={fa}  body={ba}")
if len(mm_age) > 15:
    print(f"    … 외 {len(mm_age)-15}건")

print(f"\n  월 불일치 (파일명 ≠ 본문 제목) : {len(mm_month)}건")
for r, fm, bm in mm_month[:15]:
    print(f"    {r['name'][:58]}  filename={fm}월  body={bm}월")
if len(mm_month) > 15:
    print(f"    … 외 {len(mm_month)-15}건")

print(f"\n  문서유형 불일치 (폴더 ≠ 본문) : {len(mm_type)}건")
for r, d, b in mm_type[:20]:
    print(f"    {r['name'][:58]}  폴더={d}  본문={b}")
if len(mm_type) > 20:
    print(f"    … 외 {len(mm_type)-20}건")

# ---- 부록
bar("A-6. 부록 / 별첨 포함 문서")
app = [r for r in INV if r["body"]["appendix_markers"]]
print(f"  부록 marker가 있는 파일: {len(app)}건 (신규 {sum(1 for r in app if is_new(r))})")
mk = collections.Counter()
for r in app:
    for m in r["body"]["appendix_markers"]:
        mk[m] += 1
for m, n in mk.most_common():
    print(f"    {m:<16}{n}건")

# ---- 월 coverage
bar("A-7. 월 Coverage (Monthly, 본문 제목 기준)")
monthly = [r for r in INV if r["body"]["doc_type"] == "MONTHLY_PLAN"]
cov = collections.Counter()
cov_new = collections.Counter()
for r in monthly:
    m = r["body"]["month"]["first_title_month"] or r["filename"]["month"]
    if m:
        cov[m] += 1
        if is_new(r):
            cov_new[m] += 1
print(f"  Monthly 문서 {len(monthly)}건")
print(f"  {'월':>4}{'전체':>7}{'신규':>7}")
for m in list(range(3, 13)) + [1, 2]:
    print(f"  {m:>3}월{cov.get(m,0):>7}{cov_new.get(m,0):>7}")
print(f"  월 미상: {sum(1 for r in monthly if not (r['body']['month']['first_title_month'] or r['filename']['month']))}")
print(f"  12개월 coverage: {len([m for m in range(1,13) if cov.get(m,0)>0])}/12")

# ---- 기관 x 월
bar("A-8. 기관 × 월 Coverage (Monthly)")
grid = collections.defaultdict(set)
for r in monthly:
    inst = r["filename"]["institution"]
    m = r["body"]["month"]["first_title_month"] or r["filename"]["month"]
    if inst and m:
        grid[inst].add(m)
print(f"  {'기관':<18}{'월 수':>6}  월 목록")
for inst in sorted(grid, key=lambda k: (-len(grid[k]), k)):
    ms = sorted(grid[inst])
    mark = " *신규" if any(
        is_new(r) for r in monthly if r["filename"]["institution"] == inst
    ) else ""
    print(f"  {inst:<18}{len(ms):>6}  {ms}{mark}")
print(f"  12개월 전부를 가진 기관: "
      f"{sum(1 for i in grid if len(grid[i]) == 12)}곳")

# ---- 기관 x 연령
bar("A-9. 기관 × 연령 Coverage (본문 Truth)")
agrid = collections.defaultdict(set)
for r in INV:
    inst = r["filename"]["institution"]
    if inst:
        agrid[inst].update(a for a in r["body"]["ages"] if 0 <= a <= 5)
print(f"  {'기관':<18} 본문 관찰 연령")
for inst in sorted(agrid):
    print(f"  {inst:<18} {sorted(agrid[inst])}")
