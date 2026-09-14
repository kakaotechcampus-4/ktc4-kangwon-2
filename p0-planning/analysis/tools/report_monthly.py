"""D/E. Monthly 구조 재분석 + Week Sub-theme 분석.

Monthly 문서에서 (1) 행 Label 어휘, (2) 주차 축 존재 여부, (3) 주차별
Sub-theme/경험 행을 결정론적으로 추출한다.

    python analysis/tools/report_monthly.py

원문 Label을 먼저 보존한다. semantic merge를 하지 않는다. Label 그룹핑은
사전에 등록한 동의어 목록으로만 하고, 매칭되지 않으면 원문 그대로 남긴다.
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
NEW_DAY = "2026-09-12"

# ---- Template A의 semantic_key ↔ 원문 Label 후보 (관찰 어휘만)
SECTION_SYNONYMS = [
    # 순서가 중요하다. '소주제'가 '주제'에 먼저 걸리면 안 되므로 앞에 둔다.
    ("week_subtheme", ("소주제", "주별주제", "주간주제", "주제전개", "놀이흐름",
                       "예상놀이", "기대되는 놀이", "예상 놀이", "놀이예상",
                       "주차별 활동", "주별 내용", "놀이경험", "확장놀이",
                       "예상되는 놀이", "놀이 흐름", "주별 놀이", "활동주제")),
    ("interest_area", ("쌓기", "역할", "음률", "미술", "언어", "수·조작", "수조작",
                       "과학", "이야기나누기", "이야기", "신체활동", "대소집단",
                       "자유놀이", "흥미영역")),
    ("theme", ("놀이주제", "생활주제", "놀이 주제", "월주제", "주제명",
               "경험할 수 있는 내용", "주제")),
    ("goals", ("목표", "교사의 기대", "교육목표", "보육목표", "기대", "교사기대")),
    ("habits", ("기본생활습관", "기본생활", "생활습관", "인성", "성품")),
    ("outdoor_play", ("바깥놀이", "실외놀이", "바깥 놀이", "야외놀이", "실외활동",
                      "바깥놀이 및 대소집단")),
    ("indoor_alternative", ("실내대체", "실내 대체", "실내놀이", "대체활동")),
    ("safety_education", ("안전교육", "안전", "법정안전교육")),
    ("emergency_response", ("비상대응", "비상대응훈련")),
    ("drill", ("소방", "대피훈련", "소방대피훈련", "재난대비훈련")),
    ("event_schedule", ("행사", "어린이집 행사", "이달의 행사", "월행사", "행사계획")),
    ("special_program", ("특성화", "특별활동", "특성화 프로그램", "숲", "생태",
                         "텃밭", "원어민", "체육", "원내체험")),
    ("nutrition", ("식단", "간식", "급식", "건강영양")),
    ("parent", ("가정연계", "가정과의", "부모참여", "가정통신")),
    ("observation", ("관찰", "평가", "일지")),
]

WEEK_HEADER = re.compile(r"(\d)\s*주\b|주\s*(\d)\b|W\s*(\d)")
WEEK_ROW = re.compile(r"(\d{1,2})\s*월\s*(\d)\s*주")

# 행 Label 후보: 줄 앞쪽의 짧은 한글 덩어리
LABEL_HEAD = re.compile(r"^\s{0,14}([가-힣][가-힣 ·/]{1,14}?)\s{2,}")


def canon(label: str) -> str | None:
    s = label.replace(" ", "")
    for key, syns in SECTION_SYNONYMS:
        for syn in syns:
            if syn.replace(" ", "") in s:
                return key
    return None


def bar(t):
    print()
    print("=" * 78)
    print(" " + t)
    print("=" * 78)


monthly = [
    r for r in INV if r["body2"]["doc_type"] == "MONTHLY_PLAN" and r["readable"]
]
bar("D-1. Monthly 문서")
print(f"  MONTHLY_PLAN & readable : {len(monthly)}건 "
      f"(신규 {sum(1 for r in monthly if r['mtime_day'] == NEW_DAY)})")
insts = {r["filename"]["institution"] for r in monthly if r["filename"]["institution"]}
print(f"  기관 수                 : {len(insts)}")

# ---------------------------------------------------------- D-2. Section coverage

sec_files = collections.Counter()
sec_inst = collections.defaultdict(set)
sec_month = collections.defaultdict(set)
sec_new = collections.Counter()
raw_labels = collections.Counter()

for r in monthly:
    inst = r["filename"]["institution"] or r["sha12"]
    m = r["body2"]["month"]["first"] or r["filename"]["month"]
    lay = (TEXT / f"{r['sha12']}.layout.txt").read_text("utf-8")
    seen = set()
    for line in lay.splitlines():
        mm = LABEL_HEAD.match(line)
        if not mm:
            continue
        lab = mm.group(1).strip()
        if len(lab) < 2:
            continue
        raw_labels[lab] += 1
        key = canon(lab)
        if key:
            seen.add(key)
    for key in seen:
        sec_files[key] += 1
        sec_inst[key].add(inst)
        if m:
            sec_month[key].add(m)
        if r["mtime_day"] == NEW_DAY:
            sec_new[key] += 1

bar("D-2. Section Coverage (Monthly, 원문 행 Label 기준)")
ACTIVE = {"theme", "outdoor_play", "safety_education"}
ORDER = [k for k, _ in SECTION_SYNONYMS]
print(f"  {'semantic_key':<22}{'파일':>5}{'기관':>5}{'월':>4}{'신규':>5}  Template A")
for key, _ in SECTION_SYNONYMS:
    n = sec_files.get(key, 0)
    if n == 0:
        continue
    state = "ACTIVE" if key in ACTIVE else "inactive/없음"
    print(f"  {key:<22}{n:>5}{len(sec_inst[key]):>5}{len(sec_month[key]):>4}"
          f"{sec_new.get(key,0):>5}  {state}")
print()
print("  Template A ACTIVE인데 관찰이 적은 것 / 관찰이 많은데 inactive인 것을 본다.")

bar("D-3. 원문 행 Label 원본 (상위 40, semantic merge 이전)")
for lab, n in raw_labels.most_common(40):
    key = canon(lab)
    print(f"    {n:>4}  {lab:<18} → {key or '(미매칭)'}")

# ------------------------------------------------- E. Week Sub-theme

bar("E-1. 주차 축 / 주차별 Sub-theme 행 존재 여부")

week_axis = 0
subtheme_docs = []
for r in monthly:
    lay = (TEXT / f"{r['sha12']}.layout.txt").read_text("utf-8")
    has_week = bool(re.search(r"1\s*주", lay) and re.search(r"[34]\s*주", lay))
    if has_week:
        week_axis += 1
    rows = []
    for line in lay.splitlines():
        mm = LABEL_HEAD.match(line)
        if mm and canon(mm.group(1).strip()) == "week_subtheme":
            rows.append((mm.group(1).strip(), line[mm.end():]))
    if rows:
        subtheme_docs.append((r, rows))

print(f"  주차 축(1주/3~4주 동시 등장) 보유 : {week_axis}/{len(monthly)}건 "
      f"({week_axis/len(monthly)*100:.0f}%)")
print(f"  주차별 Sub-theme 행 보유         : {len(subtheme_docs)}건 "
      f"({len(subtheme_docs)/len(monthly)*100:.0f}%)")
st_inst = {
    r["filename"]["institution"] for r, _ in subtheme_docs if r["filename"]["institution"]
}
print(f"  Sub-theme 행을 가진 기관         : {len(st_inst)}곳 / 전체 {len(insts)}곳")
print(f"    {sorted(st_inst)}")

bar("E-2. 주차별 Sub-theme 원문 표본 (월별)")
by_month = collections.defaultdict(list)
for r, rows in subtheme_docs:
    m = r["body2"]["month"]["first"] or r["filename"]["month"]
    inst = r["filename"]["institution"]
    for lab, seg in rows:
        cells = [c.strip() for c in re.split(r"\s{2,}", seg) if c.strip()]
        cells = [c for c in cells if len(c) >= 2 and not re.fullmatch(r"[\d\s./~\-()]+", c)]
        if m and cells:
            by_month[m].append((inst, lab, cells[:6]))

for m in list(range(3, 13)) + [1, 2]:
    if m not in by_month:
        continue
    print(f"\n  ── {m}월 ({len(by_month[m])}행) ──")
    for inst, lab, cells in by_month[m][:5]:
        print(f"    [{inst}] {lab}")
        for i, c in enumerate(cells, 1):
            print(f"        W{i}: {c[:46]}")

# ------------------------------------------------- E-3. 순서 패턴

bar("E-3. 주차 위치별 어휘 빈도 (순서 패턴 탐색)")
VERB_BUCKETS = [
    ("관심/관찰", ("관심", "살펴", "관찰", "알아", "느껴", "탐색")),
    ("탐구/실험", ("탐구", "실험", "비교", "조사", "궁금")),
    ("놀이/표현", ("놀이", "표현", "만들", "그리", "꾸미", "역할")),
    ("확장/공유", ("확장", "발표", "공유", "전시", "초대", "함께")),
    ("정리/마무리", ("정리", "마무리", "회상", "평가", "돌아보")),
]


def bucket(text: str) -> list[str]:
    out = []
    for name, keys in VERB_BUCKETS:
        if any(k in text for k in keys):
            out.append(name)
    return out


pos = collections.defaultdict(lambda: collections.Counter())
for m, rows in by_month.items():
    for inst, lab, cells in rows:
        for i, c in enumerate(cells[:5], 1):
            for b in bucket(c):
                pos[i][b] += 1

print(f"  {'주차':<6}" + "".join(f"{n:<12}" for n, _ in VERB_BUCKETS))
for i in range(1, 6):
    row = f"  W{i}    "
    for name, _ in VERB_BUCKETS:
        row += f"{pos[i].get(name, 0):<12}"
    print(row)
print()
total_cells = sum(sum(c.values()) for c in pos.values())
print(f"  어휘 bucket에 걸린 셀 수 합계: {total_cells}")
print("  ※ 표본이 적으면 순서 패턴을 주장하지 않는다.")
