"""C. Yearly 재분석 — Month → Broad Theme 재집계.

Yearly 문서에서 (월, 주제 문자열) 쌍을 결정론적으로 뽑고, 현재 Theme Reference
v0.1.2의 12개월 Theme와 대조한다.

    python analysis/tools/report_yearly.py

Theme Reference JSON은 **읽기만** 한다. 수정하지 않는다.
semantic merge를 하지 않는다. broad theme 매칭은 사전에 등록된 keyword로만
판정하고, 매칭되지 않으면 UNMATCHED로 남긴다.
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
THEMES = json.loads(
    (ROOT / "data" / "themes" / "theme_reference_v0.json").read_text("utf-8")
)
NEW_DAY = "2026-09-12"

# ---- Theme Reference v0.1.2 의 월별 theme (읽기 전용)
REF = {}
for t in THEMES["themes"]:
    for m in t.get("applicable_months", []):
        REF.setdefault(m, []).append((t["theme_id"], t["label"]))

# ---- broad theme 판정 keyword (관찰 어휘 기반, 확장하지 않음)
BROAD = [
    ("새학기/우리반", ("우리 반", "우리반", "새 친구", "새친구", "어린이집과 친구",
                  "새로운 환경", "적응", "만나서 반가", "입학", "새학기", "우리 원",
                  "원과 친구", "어린이집과", "친구와 나", "우리들")),
    ("봄", ("봄",)),
    ("나와 가족", ("나와 가족", "가족", "나의 몸", "소중한 나", "나를 알아", "가족과 나")),
    ("우리 동네", ("우리 동네", "동네", "이웃", "지역사회")),
    ("여름", ("여름",)),
    ("교통기관", ("교통기관", "교통", "탈것", "자동차")),
    ("우리나라/세계", ("우리나라", "대한민국", "세계", "지구촌", "전통")),
    ("가을", ("가을", "추석")),
    ("환경과 생활", ("환경", "자연과 더불어", "재활용", "지구를 지")),
    ("겨울", ("겨울", "눈", "크리스마스")),
    ("생활도구", ("생활도구", "도구", "기계")),
    ("성장/전이", ("형님", "성장", "졸업", "수료", "새로운 시작", "초등학교",
                "소중했던", "달라진 나", "된 우리")),
]

MONTH_ROW = re.compile(r"^\s*(\d{1,2})\s*월")
MONTH_TOKEN = re.compile(r"(?<![\d/.~-])(\d{1,2})\s*월(?![\d/.~일-])")

SAFETY_ROW = re.compile(
    r"연간\s*\d+\s*시간|시간\s*이상|예방\s*교육|비상대응|소방|대피훈련|"
    r"실종|유괴|약물|성폭력|아동학대|감염병|교통안전\s*교육"
)
"""안전교육 계획 행. 기관의 배치 Sample이며 Yearly broad theme가 아니다."""


def broad_of(label: str) -> str:
    s = label.replace(" ", "")
    for name, keys in BROAD:
        for k in keys:
            if k.replace(" ", "") in s:
                return name
    return "UNMATCHED"


def extract_month_themes(layout: str) -> list[tuple[int, str]]:
    """'N월 <주제...>' 형태의 행에서 (월, 원문 주제 표현)을 뽑는다.

    셀 경계를 모르므로 월 토큰 뒤 첫 의미 덩어리만 취한다. 완전 추출이 아니라
    **관찰 표본**이며, 뽑히지 않은 것을 추정으로 채우지 않는다.
    """
    out = []
    for line in layout.splitlines():
        if SAFETY_ROW.search(line):
            # 안전교육 배치 행은 Yearly broad theme가 아니다(§15).
            continue
        hits = list(MONTH_TOKEN.finditer(line))
        if not hits:
            continue
        # 반쪽표 좌우 병렬 레이아웃: 한 줄에 월 토큰이 2개 이상 나온다.
        # 각 월 토큰 뒤 ~ 다음 월 토큰 앞까지를 그 월의 구간으로 본다.
        for i, m in enumerate(hits):
            month = int(m.group(1))
            if not 1 <= month <= 12:
                continue
            end = hits[i + 1].start() if i + 1 < len(hits) else len(line)
            seg = line[m.end() : end]
            cells = [c.strip() for c in re.split(r"\s{2,}", seg) if c.strip()]
            cells = [c for c in cells if not re.fullmatch(r"[\d\s./~\-()]+", c)]
            cells = [c for c in cells if len(c) >= 2]
            # 행사/훈련 일자 셀은 주제가 아니다
            cells = [
                c for c in cells
                if not re.match(r"^\d{1,2}\s*일", c) and "불시" not in c
            ]
            if cells:
                out.append((month, cells[0][:40]))
    return out


def bar(t):
    print()
    print("=" * 78)
    print(" " + t)
    print("=" * 78)


yearly = [r for r in INV if r["body2"]["doc_type"] == "YEARLY_PLAN"]
yearly_readable = [r for r in yearly if r["readable"]]

bar("C-1. Yearly 문서")
print(f"  YEARLY_PLAN 판정 : {len(yearly)}건 "
      f"(신규 {sum(1 for r in yearly if r['mtime_day'] == NEW_DAY)})")
print(f"  판독 가능        : {len(yearly_readable)}건")
print(f"  기관 수          : "
      f"{len({r['filename']['institution'] for r in yearly_readable if r['filename']['institution']})}")

# ---- 월 × broad theme 집계
obs = collections.defaultdict(lambda: collections.Counter())  # month -> broad -> n
obs_inst = collections.defaultdict(lambda: collections.defaultdict(set))
samples = collections.defaultdict(lambda: collections.defaultdict(list))
new_obs = collections.defaultdict(lambda: collections.Counter())
unmatched = collections.Counter()

for r in yearly_readable:
    inst = r["filename"]["institution"] or r["sha12"]
    lay = (TEXT / f"{r['sha12']}.layout.txt").read_text("utf-8")
    for month, label in extract_month_themes(lay):
        b = broad_of(label)
        obs[month][b] += 1
        obs_inst[month][b].add(inst)
        if len(samples[month][b]) < 6:
            samples[month][b].append(f"{label} ({inst})")
        if r["mtime_day"] == NEW_DAY:
            new_obs[month][b] += 1
        if b == "UNMATCHED":
            unmatched[label] += 1

bar("C-2. Month → Broad Theme 재집계 (Current Full Corpus)")
MONTH_ORDER = list(range(3, 13)) + [1, 2]
for m in MONTH_ORDER:
    ref = REF.get(m, [])
    ref_labels = ", ".join(f"{lab}" for _, lab in ref) or "(없음)"
    print(f"\n  ── {m}월 ──  Theme Reference v0.1.2: {ref_labels}")
    c = obs[m]
    if not c:
        print("     관찰 0건")
        continue
    total = sum(c.values())
    for b, n in c.most_common(6):
        insts = len(obs_inst[m][b])
        nn = new_obs[m].get(b, 0)
        print(f"     {b:<14} obs {n:>3} ({n/total*100:4.1f}%)  기관 {insts:>2}  신규 {nn:>2}")
    ex = samples[m][c.most_common(1)[0][0]][:3]
    print(f"     대표 원문: {ex}")

bar("C-3. Theme Reference v0.1.2 Delta 판정")
print(f"  {'월':>4} {'Reference Theme':<24}{'최다 관찰':<14}{'기관':>5}{'일치':>6}  판정")
verdicts = {}
for m in MONTH_ORDER:
    ref = REF.get(m, [])
    ref_label = " / ".join(lab for _, lab in ref) if ref else "(없음)"
    # 한 달에 Reference 후보가 여러 개일 수 있다. 집합으로 평가한다.
    ref_broads = {broad_of(lab) for _, lab in ref} - {"UNMATCHED"}
    c = obs[m]
    if not c:
        verdicts[m] = "INSUFFICIENT"
        print(f"  {m:>3}월 {ref_label[:24]:<24}{'-':<14}{0:>5}{'-':>6}  INSUFFICIENT")
        continue
    top, topn = c.most_common(1)[0]
    total = sum(c.values())
    ref_n = sum(c.get(b, 0) for b in ref_broads)
    ref_inst = len(set().union(*[obs_inst[m][b] for b in ref_broads])) if ref_broads else 0
    share = ref_n / total if total else 0
    if not ref_broads:
        v = "INSUFFICIENT"
    elif ref_n == 0:
        v = "CONFLICTING"
    elif top in ref_broads and ref_inst >= 8 and share >= 0.4:
        v = "SUPPORTED_STRONGLY"
    elif top in ref_broads:
        v = "SUPPORTED"
    elif ref_n >= 3 and ref_inst >= 3:
        v = "SUPPORTED"
    else:
        v = "CONFLICTING"
    verdicts[m] = v
    print(f"  {m:>3}월 {ref_label[:24]:<24}{top:<14}{ref_inst:>5}{share*100:>5.0f}%  {v}")

print()
vc = collections.Counter(verdicts.values())
for k, n in vc.most_common():
    print(f"    {k:<22}{n}개월")

bar("C-4. UNMATCHED 원문 표현 (신규 broad theme 후보 검토용)")
print(f"  UNMATCHED 관찰 {sum(unmatched.values())}건 / 고유 표현 {len(unmatched)}개")
for label, n in unmatched.most_common(30):
    print(f"    {n:>3}  {label}")
