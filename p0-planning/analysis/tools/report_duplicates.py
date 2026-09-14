"""B. Source Independence / Template Family 분석.

exact duplicate(SHA-256)와 정규화 본문 기반 near-duplicate를 찾는다.
유사하다고 해서 같은 Source로 단정하지 않는다. 등급만 붙인다.

    python analysis/tools/report_duplicates.py
"""

from __future__ import annotations

import collections
import io
import itertools
import json
import pathlib
import re
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = pathlib.Path(__file__).resolve().parents[2]
TMP = ROOT / "analysis" / "tmp"
TEXT = TMP / "corpus_text"
INV = json.loads((TMP / "inventory2.json").read_text("utf-8"))
NEW_DAY = "2026-09-12"

# 문서 고유 정보(연도/기관/반이름/날짜)를 지운 뒤 비교한다.
STRIP = [
    (re.compile(r"20\d{2}\s*년?"), " "),
    (re.compile(r"\d{1,2}\s*[월일]"), " "),
    (re.compile(r"[가-힣A-Za-z0-9]+(?:어린이집|유치원)"), " "),
    (re.compile(r"[가-힣]{1,6}반"), " "),
    (re.compile(r"\d+"), " "),
    (re.compile(r"[^\w가-힣]+"), " "),
    (re.compile(r"\s+"), " "),
]


def norm(text: str) -> str:
    s = text
    for pat, rep in STRIP:
        s = pat.sub(rep, s)
    return s.strip()


def shingles(s: str, k: int = 6) -> set[str]:
    toks = s.split()
    if len(toks) < k:
        return {" ".join(toks)} if toks else set()
    return {" ".join(toks[i : i + k]) for i in range(len(toks) - k + 1)}


def jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def bar(t):
    print()
    print("=" * 78)
    print(" " + t)
    print("=" * 78)


# ------------------------------------------------------------ exact duplicate

bar("B-1. Exact Duplicate (SHA-256)")
by_sha = collections.defaultdict(list)
for r in INV:
    by_sha[r["sha256"]].append(r)
dups = {k: v for k, v in by_sha.items() if len(v) > 1}
print(f"  고유 SHA {len(by_sha)}개 / 파일 {len(INV)}개")
print(f"  exact duplicate 그룹: {len(dups)}개, "
      f"중복 파일 {sum(len(v) - 1 for v in dups.values())}개")
for sha, group in dups.items():
    print(f"\n  [{sha[:12]}] {len(group)}개 — 내용 동일, 파일명만 다름")
    for r in group:
        tag = " *신규" if r["mtime_day"] == NEW_DAY else ""
        print(f"    {r['dir']}/{r['name']}{tag}")

# ------------------------------------------------------- near duplicate

bar("B-2. Normalized Near-Duplicate (본문 정규화 후 Jaccard)")
docs = []
for r in INV:
    if not r["readable"]:
        continue
    p = TEXT / f"{r['sha12']}.raw.txt"
    t = p.read_text("utf-8") if p.exists() else ""
    n = norm(t)
    if len(n.split()) < 20:
        continue
    docs.append((r, shingles(n)))
print(f"  비교 대상 {len(docs)}건 (판독 가능 & 본문 20토큰 이상)")

pairs = []
for (ra, sa), (rb, sb) in itertools.combinations(docs, 2):
    j = jaccard(sa, sb)
    if j >= 0.45:
        pairs.append((j, ra, rb))
pairs.sort(key=lambda x: -x[0])
print(f"  Jaccard ≥ 0.45 쌍: {len(pairs)}개")


def grade(j, ra, rb):
    ia = ra["filename"]["institution"]
    ib = rb["filename"]["institution"]
    if ra["sha256"] == rb["sha256"]:
        return "EXACT_DUPLICATE"
    if ia and ib and ia == ib:
        return "HIGH_SIMILARITY_SAME_INSTITUTION"
    if j >= 0.75:
        return "POSSIBLE_TEMPLATE_FAMILY"
    return "HIGH_SIMILARITY_CROSS_INSTITUTION"


graded = collections.Counter()
cross = []
for j, ra, rb in pairs:
    g = grade(j, ra, rb)
    graded[g] += 1
    if g in ("POSSIBLE_TEMPLATE_FAMILY", "HIGH_SIMILARITY_CROSS_INSTITUTION"):
        cross.append((j, g, ra, rb))
print()
for g, n in graded.most_common():
    print(f"    {g:<38}{n}쌍")

print(f"\n  기관이 다른데 유사한 쌍 {len(cross)}개 (상위 30)")
for j, g, ra, rb in cross[:30]:
    print(f"    {j:.3f} {g}")
    print(f"        {ra['filename']['institution']} | {ra['name'][:52]}")
    print(f"        {rb['filename']['institution']} | {rb['name'][:52]}")

# ------------------------------------------------- template family clustering

bar("B-3. Template Family 후보 (기관 간 연결 성분)")
adj = collections.defaultdict(set)
for j, g, ra, rb in cross:
    ia, ib = ra["filename"]["institution"], rb["filename"]["institution"]
    if ia and ib and ia != ib:
        adj[ia].add(ib)
        adj[ib].add(ia)

seen = set()
families = []
for node in adj:
    if node in seen:
        continue
    stack, comp = [node], set()
    while stack:
        cur = stack.pop()
        if cur in comp:
            continue
        comp.add(cur)
        stack.extend(adj[cur] - comp)
    seen |= comp
    families.append(sorted(comp))

all_inst = {r["filename"]["institution"] for r in INV if r["filename"]["institution"]}
linked = set().union(*families) if families else set()
print(f"  관찰된 기관 수                       : {len(all_inst)}")
print(f"  기관 간 고유사 연결이 있는 기관 수    : {len(linked)}")
print(f"  Template Family 후보 군집 수         : {len(families)}")
for fam in sorted(families, key=lambda f: -len(f)):
    print(f"    - {fam}")
print()
print(f"  possible independent source count (보수적 추정)")
print(f"    = 연결 없는 기관 {len(all_inst - linked)}곳 + 군집 {len(families)}개")
print(f"    = {len(all_inst - linked) + len(families)}")
print(f"  (observed institution count = {len(all_inst)})")
print()
print("  ※ 유사하다고 같은 Source로 확정하지 않는다. 위 값은 evidence strength를")
print("    해석할 때의 상한/하한 참고치이며, 확정은 사람 검토가 필요하다.")
