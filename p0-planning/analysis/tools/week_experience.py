"""§6/§7 + Q3. Month → Week Experience 구조 추출과 Coverage Matrix.

원문 Label을 보존한 채 (month, age, institution, monthly_theme, W1..W5)를 뽑고,
기관이 달라도 반복되는 Concept Cluster와 순서 지지도를 계산한다.

`normalized_concept_candidate`는 **분석용 후보**다. Canonical Reference로
승격하지 않는다. 원문은 항상 함께 보존한다.

    python analysis/tools/week_experience.py
"""

from __future__ import annotations

import collections
import io
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
TMP = ROOT / "analysis" / "tmp"
TEXT = TMP / "corpus_text"
INV = json.loads((TMP / "inventory2.json").read_text("utf-8"))

# §5 재분석에서 확인된 Template Family. 독립 근거 보정에 쓴다.
TEMPLATE_FAMILY = {"마성어린이집", "우리어린이집", "키즈로스쿨어린이집", "혜솔어린이집"}

WEEK_SUBTHEME_LABELS = (
    "소주제", "주별주제", "주간주제", "주제전개", "놀이흐름", "예상놀이",
    "기대되는 놀이", "예상 놀이", "놀이예상", "주차별 활동", "주별 내용",
    "놀이경험", "확장놀이", "예상되는 놀이", "놀이 흐름", "주별 놀이", "활동주제",
)
THEME_LABELS = ("놀이주제", "생활주제", "놀이 주제", "월주제", "주제명", "주제")

LABEL_HEAD = re.compile(r"^\s{0,14}([가-힣][가-힣 ·/]{1,14}?)\s{2,}")
DATE_CELL = re.compile(r"^\d{1,2}\s*월?\s*\d{0,2}\s*일?\s*[~\-]")

# 분석용 concept 후보 (원문 치환이 아니라 태깅이다)
CONCEPT = [
    ("날씨/계절변화", ("날씨", "바람", "햇볕", "비", "눈", "기온", "계절", "변화")),
    ("자연/동식물", ("꽃", "나무", "잎", "씨앗", "곤충", "동물", "열매", "식물",
                 "자연물", "텃밭", "새싹", "개구리", "나비", "단풍", "낙엽")),
    ("나/몸/마음", ("나의", "내 몸", "몸", "마음", "감정", "소중한 나", "얼굴", "손발")),
    ("가족", ("가족", "엄마", "아빠", "형제", "생일")),
    ("친구/우리반", ("친구", "우리 반", "우리반", "선생님", "약속", "적응")),
    ("동네/기관", ("동네", "이웃", "시장", "마트", "병원", "소방서", "우체국", "직업",
                "공공기관", "표지판")),
    ("전통/명절", ("추석", "설날", "한복", "전통", "송편", "윷", "제기", "명절",
                "태극기", "무궁화")),
    ("물/여름놀이", ("물놀이", "물", "분수", "얼음", "그늘", "수영")),
    ("음식/요리", ("음식", "요리", "간식", "디저트", "아이스크림", "떡")),
    ("환경/자원", ("환경", "분리수거", "재활용", "쓰레기", "지구", "에너지")),
    ("도구/기계/디지털", ("도구", "기계", "로봇", "미디어", "digital", "컴퓨터", "블록")),
    ("이동/교통", ("자동차", "교통", "버스", "기차", "비행기", "탈것")),
    ("성장/전이", ("형님", "졸업", "수료", "성장", "초등학교", "달라진")),
    ("안전", ("안전", "조심", "약속 지키", "지켜야")),
]


def concept_of(text: str) -> list[str]:
    s = text.replace(" ", "")
    out = []
    for name, keys in CONCEPT:
        if any(k.replace(" ", "") in s for k in keys):
            out.append(name)
    return out


def canon_label(lab: str) -> str | None:
    s = lab.replace(" ", "")
    for syn in WEEK_SUBTHEME_LABELS:
        if syn.replace(" ", "") in s:
            return "week_subtheme"
    for syn in THEME_LABELS:
        if syn.replace(" ", "") in s:
            return "theme"
    return None


def cells_of(seg: str) -> list[str]:
    cs = [c.strip(" ·.-") for c in re.split(r"\s{2,}", seg) if c.strip()]
    out = []
    for c in cs:
        if len(c) < 2:
            continue
        if re.fullmatch(r"[\d\s./~\-()월일주]+", c):
            continue
        if DATE_CELL.match(c):
            continue  # 기간 행이 소주제 Label 아래 오는 레이아웃 (혜솔)
        out.append(c)
    return out


def bar(t):
    print()
    print("=" * 78)
    print(" " + t)
    print("=" * 78)


monthly = [
    r for r in INV if r["body2"]["doc_type"] == "MONTHLY_PLAN" and r["readable"]
]

records = []
for r in monthly:
    inst = r["filename"]["institution"] or r["sha12"]
    month = r["body2"]["month"]["first"] or r["filename"]["month"]
    ages = r["body2"]["ages"] or r["filename"]["ages"]
    ages = [a for a in ages if 3 <= a <= 5]
    lay = (TEXT / f"{r['sha12']}.layout.txt").read_text("utf-8")

    theme_val = None
    weeks: list[tuple[str, str]] = []  # (source_label, raw_value)
    for line in lay.splitlines():
        mm = LABEL_HEAD.match(line)
        if not mm:
            continue
        lab = mm.group(1).strip()
        kind = canon_label(lab)
        if kind == "theme" and theme_val is None:
            cs = cells_of(line[mm.end():])
            if cs:
                theme_val = cs[0][:40]
        elif kind == "week_subtheme":
            for c in cells_of(line[mm.end():])[:5]:
                weeks.append((lab, c[:48]))
    if weeks:
        records.append({
            "file": r["name"],
            "institution": inst,
            "month": month,
            "ages": ages,
            "monthly_theme": theme_val,
            "template_family": inst in TEMPLATE_FAMILY,
            "weeks": [
                {
                    "position": i + 1,
                    "source_label": lab,
                    "raw_value": val,
                    "normalized_concept_candidate": concept_of(val),
                }
                for i, (lab, val) in enumerate(weeks[:5])
            ],
        })

(TMP / "week_experience.json").write_text(
    json.dumps(records, ensure_ascii=False, indent=1), encoding="utf-8"
)

bar("§6. Month → Week Experience 추출 결과")
print(f"  Week Experience 행을 가진 Monthly 문서 : {len(records)}건")
print(f"  기관                                   : "
      f"{len({r['institution'] for r in records})}곳")
print(f"  Template Family 소속 문서              : "
      f"{sum(1 for r in records if r['template_family'])}건")
print(f"  원문 Label 어휘                        : "
      f"{sorted({w['source_label'] for r in records for w in r['weeks']})}")
print(f"  저장                                   : analysis/tmp/week_experience.json")

bar("§7. 월별 Concept Cluster (기관 달라도 반복되는가)")
by_month = collections.defaultdict(lambda: collections.Counter())
by_month_inst = collections.defaultdict(lambda: collections.defaultdict(set))
by_month_indep = collections.defaultdict(lambda: collections.defaultdict(set))
for r in records:
    m = r["month"]
    if not m:
        continue
    # Template Family는 하나의 독립 source로 축약한다
    indep = "FAMILY#1" if r["template_family"] else r["institution"]
    for w in r["weeks"]:
        for c in w["normalized_concept_candidate"]:
            by_month[m][c] += 1
            by_month_inst[m][c].add(r["institution"])
            by_month_indep[m][c].add(indep)

for m in list(range(3, 13)) + [1, 2]:
    if m not in by_month:
        continue
    print(f"\n  ── {m}월 ──")
    for c, n in by_month[m].most_common(5):
        print(f"     {c:<18} obs {n:>2}  기관 {len(by_month_inst[m][c])}  "
              f"독립source {len(by_month_indep[m][c])}")

bar("§7.3 순서 지지도 (position별 concept 분포)")
pos_concept = collections.defaultdict(lambda: collections.Counter())
for r in records:
    for w in r["weeks"]:
        for c in w["normalized_concept_candidate"]:
            pos_concept[w["position"]][c] += 1
for p in range(1, 6):
    if p not in pos_concept:
        continue
    top = ", ".join(f"{c}({n})" for c, n in pos_concept[p].most_common(4))
    print(f"  W{p}: {top}")
print()
print("  ※ 같은 concept가 여러 position에 고르게 나타나면 순서 근거가 아니다.")

bar("Q3. Month × Age Coverage Matrix (Week Experience)")
grid = collections.defaultdict(lambda: collections.defaultdict(lambda: {"docs": 0, "inst": set(), "indep": set()}))
for r in records:
    m = r["month"]
    if not m:
        continue
    ages = r["ages"] or []
    if not ages:
        ages = ["?"]
    indep = "FAMILY#1" if r["template_family"] else r["institution"]
    for a in ages:
        g = grid[m][a]
        g["docs"] += 1
        g["inst"].add(r["institution"])
        g["indep"].add(indep)


def conf(cell) -> str:
    if cell["docs"] == 0:
        return "NONE"
    i = len(cell["indep"])
    if i >= 3 and cell["docs"] >= 4:
        return "MODERATE"
    if i >= 2:
        return "WEAK"
    return "VERY_WEAK"


print(f"  {'월':>4}{'만3세':>18}{'만4세':>18}{'만5세':>18}{'종합':>12}")
for m in list(range(3, 13)) + [1, 2]:
    row = f"  {m:>3}월"
    overall_docs, overall_indep = 0, set()
    for a in (3, 4, 5):
        cell = grid[m].get(a, {"docs": 0, "inst": set(), "indep": set()})
        overall_docs += cell["docs"]
        overall_indep |= cell["indep"]
        row += f"{cell['docs']:>4}건/{len(cell['indep'])}src{'':>6}"
    o = {"docs": overall_docs, "indep": overall_indep}
    row += f"{conf(o):>12}"
    print(row)
print()
print("  판정 기준: MODERATE = 독립source 3+ & 문서 4+ / WEAK = 독립source 2 /")
print("            VERY_WEAK = 독립source 1 / NONE = 관찰 0")
