"""F. Activity 재분석 — 재현율 / Label 품질 / Age Evidence / 신규 후보.

Activity Reference v0.2.0을 **읽기만** 한다. 수정하지 않는다.
자동 merge / rewriting / canonical label 생성을 하지 않는다. 분류만 한다.

    python analysis/tools/report_activity.py
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
TMP = ROOT / "analysis" / "tmp"
TEXT = TMP / "corpus_text"
INV = json.loads((TMP / "inventory2.json").read_text("utf-8"))
CAT = json.loads(
    (ROOT / "data" / "activities" / "activity_reference_v0_2.json").read_text("utf-8")
)
NEW_DAY = "2026-09-12"

ACTS = CAT["activities"]
LABELS = {a["label"] for a in ACTS}
ALIASES = {}
for a in ACTS:
    for al in a.get("aliases", []):
        ALIASES[al] = a["activity_id"]


def nrm(s: str) -> str:
    return re.sub(r"[\s.,·…~!?\"'()\[\]]+", "", s)


NORM_INDEX = {}
for a in ACTS:
    NORM_INDEX[nrm(a["label"])] = a["activity_id"]
    for al in a.get("aliases", []):
        NORM_INDEX.setdefault(nrm(al), a["activity_id"])


def bar(t):
    print()
    print("=" * 78)
    print(" " + t)
    print("=" * 78)


# =============================================== F-1. Catalog 현황 (읽기 전용)

bar("F-1. Activity Reference v0.2.0 현황 (읽기 전용)")
print(f"  catalog_version : {CAT['catalog_version']}")
print(f"  승인 상태       : {CAT['review']['domain_owner_approval']}")
print(f"  항목 수         : {len(ACTS)}")
ev_total = sum(len(a.get("evidence", [])) for a in ACTS)
print(f"  evidence 총계   : {ev_total}")
cov = sorted({m for a in ACTS for m in a.get("applicable_months", [])})
print(f"  월 coverage     : {cov}")

ev_dist = collections.Counter(len(a.get("evidence", [])) for a in ACTS)
print(f"\n  evidence 수 분포")
for k in sorted(ev_dist):
    print(f"    evidence {k:>2}건 : {ev_dist[k]:>3} items")
single = sum(1 for a in ACTS if len(a.get("evidence", [])) == 1)
print(f"  evidence 1건뿐인 항목: {single} ({single/len(ACTS)*100:.0f}%)")

inst_dist = collections.Counter()
for a in ACTS:
    insts = {e["origin_id"].split(".")[2] if e["origin_id"].count(".") >= 2 else e["origin_id"]
             for e in a.get("evidence", [])}
    inst_dist[len(insts)] += 1
print(f"\n  관찰 기관 수 분포")
for k in sorted(inst_dist):
    print(f"    기관 {k}곳 : {inst_dist[k]:>3} items")
one_inst = inst_dist.get(1, 0)
print(f"  단일 기관 관찰 항목: {one_inst} ({one_inst/len(ACTS)*100:.0f}%)")

# =============================================== F-2. Label 품질 분류

bar("F-2. Activity Label 품질 분류 (Human Review 후보)")

SECTION_WORDS = ("놀이", "활동", "교육", "영역", "주제", "계획", "안전", "일과")
INST_WORDS = ("유희실", "강당", "옥상", "텃밭", "숲", "산책로", "놀이터", "운동장",
              "테라스", "마당", "공원", "체육관", "정원")
FRAGMENT_TAIL = ("고", "며", "서", "이", "가", "을", "를", "은", "는", "의", "에",
                 "와", "과", "도", "만", "로", "면")

buckets = collections.defaultdict(list)
for a in ACTS:
    lab = a["label"].strip()
    n = nrm(lab)
    tags = []
    if len(n) <= 3:
        tags.append("TOO_SHORT")
    if not re.search(r"[가-힣]", lab):
        tags.append("NEEDS_HUMAN_REVIEW")
    # 절단 증거가 있을 때만 FRAGMENT로 본다. 짧다는 이유만으로 찍지 않는다
    # (이전 corpus 분석에서 확립: completeness = 절단 증거의 부재).
    if re.search(r"(고|며|면서|지만|는데|어서|아서|하며|하고)$", lab):
        tags.append("POSSIBLE_FRAGMENT")
    # 조사로 끝나는 절단. '이/가'는 한국어 명사 말음과 충돌이 커서 제외하고
    # ('놀이', '무궁화꽃이' 등) 확실한 목적격/관형격만 본다.
    if re.search(r"(을|를|은|는|의|에|와|과|으로|로)$", lab) and not re.search(
        r"(놀이|하기|먹기|보기|찾기|잡기|쌓기|만들기)$", lab
    ):
        tags.append("POSSIBLE_FRAGMENT")
    # 목적어 없이 술어만 남은 아주 짧은 표현만 본다. '사방치기'처럼 그 자체가
    # 완결된 놀이 이름은 자동으로 가려낼 수 없으므로 길이를 3자로 제한한다.
    if re.fullmatch(r"[가-힣]{2,3}기", lab.replace(" ", "")):
        tags.append("CONTEXT_DEPENDENT")
    if re.search(r"^(놀이|활동)(를|을)?\s*(해요|합니다|한다)\.?$", lab):
        tags.append("CONTEXT_DEPENDENT")
    if any(w in lab for w in INST_WORDS):
        tags.append("INSTITUTION_SPECIFIC")
    if n in {nrm(w) for w in SECTION_WORDS} or (
        len(n) <= 4 and any(n.endswith(nrm(w)) for w in ("놀이", "활동", "영역"))
    ):
        tags.append("POSSIBLE_SECTION_LABEL")
    if re.search(r"안전|조심|주의|위험|지키", lab):
        tags.append("SAFETY_ADJACENT")
    # 조사로 끝나 문맥 없이는 뜻이 안 서는 표현
    if re.search(r"(에서|에게|으로|와 함께|과 함께)$", lab):
        tags.append("CONTEXT_DEPENDENT")
    if not tags:
        tags = ["GOOD_STANDALONE_LABEL"]
    for t in set(tags):
        buckets[t].append(a)

order = ["GOOD_STANDALONE_LABEL", "TOO_SHORT", "POSSIBLE_FRAGMENT",
         "CONTEXT_DEPENDENT", "POSSIBLE_SECTION_LABEL", "INSTITUTION_SPECIFIC",
         "SAFETY_ADJACENT", "NEEDS_HUMAN_REVIEW"]
print(f"  {'분류':<26}{'건수':>5}")
for k in order:
    if k in buckets:
        print(f"  {k:<26}{len(buckets[k]):>5}")
flagged = {a["activity_id"] for k, v in buckets.items()
           if k != "GOOD_STANDALONE_LABEL" for a in v}
print(f"\n  최소 1개 flag가 붙은 항목: {len(flagged)} / {len(ACTS)} "
      f"({len(flagged)/len(ACTS)*100:.0f}%)")

for k in order[1:]:
    if k not in buckets:
        continue
    print(f"\n  [{k}] {len(buckets[k])}건 (최대 20개)")
    for a in sorted(buckets[k], key=lambda x: len(x["label"]))[:20]:
        ev = len(a.get("evidence", []))
        print(f"    {a['label']:<28} ev={ev} months={a.get('applicable_months')}")

# =============================================== F-3. Corpus 재현 / 신규 후보

bar("F-3. Current Full Corpus에서의 Activity 재현 / 신규 후보")

OUTDOOR_LABEL = re.compile(r"^\s{0,14}(바깥\s*놀이|실외\s*놀이|바깥놀이|야외놀이)")
monthly = [r for r in INV if r["body2"]["doc_type"] == "MONTHLY_PLAN" and r["readable"]]

observed = collections.Counter()
observed_inst = collections.defaultdict(set)
observed_new = collections.Counter()
for r in monthly:
    inst = r["filename"]["institution"] or r["sha12"]
    lay = (TEXT / f"{r['sha12']}.layout.txt").read_text("utf-8")
    for line in lay.splitlines():
        if not OUTDOOR_LABEL.match(line):
            continue
        seg = OUTDOOR_LABEL.sub("", line, count=1)
        for c in re.split(r"\s{2,}", seg):
            c = c.strip(" ·.-")
            if len(nrm(c)) < 2 or re.fullmatch(r"[\d\s./~\-()]+", c):
                continue
            observed[c] += 1
            observed_inst[c].add(inst)
            if r["mtime_day"] == NEW_DAY:
                observed_new[c] += 1

print(f"  바깥놀이 행에서 추출한 표현: {len(observed)}개 고유 / "
      f"{sum(observed.values())}건 관찰")

repro, alias_cand, new_cand = [], [], []
for expr, n in observed.items():
    key = nrm(expr)
    if key in NORM_INDEX:
        repro.append((expr, n, NORM_INDEX[key]))
    elif any(key in k or k in key for k in NORM_INDEX if len(k) >= 4):
        alias_cand.append((expr, n))
    else:
        new_cand.append((expr, n))

print(f"    EXACT_EXISTING   : {len(repro)}개")
print(f"    POSSIBLE_ALIAS   : {len(alias_cand)}개")
print(f"    NEW_RAW_CANDIDATE: {len(new_cand)}개")
reproduced_ids = {aid for _, _, aid in repro}
print(f"\n  v0.2.0의 198개 중 현재 Corpus 추출로 재현된 항목: {len(reproduced_ids)}")
print(f"  (추출기는 바깥놀이 행만 보므로 재현율 자체가 하한이다)")

print(f"\n  신규 자료에서만 관찰된 표현 (상위 25)")
only_new = [(e, n) for e, n in observed_new.items() if observed[e] == n]
for e, n in sorted(only_new, key=lambda x: -x[1])[:25]:
    key = nrm(e)
    kind = ("EXACT_EXISTING" if key in NORM_INDEX else "NEW_RAW_CANDIDATE")
    print(f"    {n:>3}  [{kind:<17}] {e[:50]}")

# =============================================== F-4. Age Evidence

bar("F-4. Age Evidence 재집계 (v0.2.0 기준, 읽기 전용)")
for age in (3, 4, 5):
    items = [a for a in ACTS if age in a.get("supported_ages", [])]
    single_ev, mixed_only, insts = 0, 0, set()
    for a in items:
        scopes = [tuple(e.get("age_scope", [])) for e in a.get("evidence", [])]
        has_single = any(len(s) == 1 and s[0] == age for s in scopes)
        has_mixed = any(len(s) >= 2 and age in s for s in scopes)
        if has_single:
            single_ev += 1
        elif has_mixed:
            mixed_only += 1
        for e in a.get("evidence", []):
            oid = e["origin_id"]
            insts.add(oid.split(".")[2] if oid.count(".") >= 2 else oid)
    print(f"\n  만 {age}세")
    print(f"    supported item        : {len(items)}")
    print(f"    single-age evidence 有 : {single_ev}")
    print(f"    mixed-only evidence    : {mixed_only}")
    print(f"    관련 기관 수           : {len(insts)}")

# 2세 이하 자료
bar("F-5. Target 밖 연령 (만 0~2세) 자료 존재 여부")
low = [r for r in INV if any(a <= 2 for a in r["body2"]["ages"])]
print(f"  본문에 만0~2세 표기가 있는 파일: {len(low)}건")
for r in low[:12]:
    print(f"    {r['name'][:64]}")
    print(f"      본문 관찰 연령={r['body2']['ages']} per_page={r['per_page_ages'][:6]}")
print("\n  ※ Corpus에는 보존하되 supported age {3,4,5} 자동 확장 금지.")
print("     만2 evidence를 만3 evidence와 합치지 않는다.")

# =============================================== F-6. Curriculum link
bar("F-6. Curriculum Link 명시 여부 (Corpus 전수)")
DOMAINS = ("신체운동", "의사소통", "사회관계", "예술경험", "자연탐구")
hit_files, hit_inst = 0, set()
per_domain = collections.Counter()
for r in INV:
    if not r["readable"]:
        continue
    t = (TEXT / f"{r['sha12']}.raw.txt").read_text("utf-8")
    found = [d for d in DOMAINS if d in t]
    if found:
        hit_files += 1
        if r["filename"]["institution"]:
            hit_inst.add(r["filename"]["institution"])
        for d in found:
            per_domain[d] += 1
print(f"  누리과정 5영역 명칭이 본문에 등장하는 파일: {hit_files} / "
      f"{sum(1 for r in INV if r['readable'])}")
print(f"  해당 기관 수: {len(hit_inst)}  {sorted(hit_inst)}")
for d in DOMAINS:
    print(f"    {d:<10}{per_domain.get(d,0)}건")
print()
if hit_files == 0:
    print("  판정: NOT_EXPLICIT — Corpus에 누리과정 영역 연결이 명시되지 않는다.")
else:
    print("  판정: 일부 EXPLICITLY_OBSERVED. 다만 Activity 단위 연결인지")
    print("        문서 전체 머리말인지는 사람 확인이 필요하다(AMBIGUOUS 가능).")
