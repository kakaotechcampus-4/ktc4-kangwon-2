"""§19/§21. Before/After 비교 + 12개월 × 연령 Candidate Coverage Regression.

BEFORE : v0.2.0 (승인본) + Ranking v2
AFTER  : v0.2.1 Draft + Ranking v2

v0.2.1은 `PENDING_HUMAN_REVIEW`라 그대로는 후보가 0이다. 시뮬레이션을 위해
**분석 tmp에만** 승인 상태 사본을 만들어 쓴다. `data/`는 건드리지 않는다.

    python analysis/experiments/monthly_vnext/before_after_patch1.py
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
    JsonActivityReferenceRepository,
)
from ssuksak.planning.domain.identifiers import PeriodKey  # noqa: E402
from ssuksak.planning.rules.monthly_activity_selection import (  # noqa: E402
    RULE_VERSION,
    select_activity_for_cell,
)
from ssuksak.planning.rules.monthly_week_periods import (  # noqa: E402
    canonical_week_periods,
)

CATALOG_ID = "ssuksak.outdoor-activity-reference"
V0 = "activity-reference-v0.2.0"
V1 = "activity-reference-v0.2.1"
OUTDOOR = "outdoor_play"
TMP = ROOT / "analysis" / "tmp"

THEMES = json.loads(
    (ROOT / "data" / "themes" / "theme_reference_v0.json").read_text("utf-8")
)
THEME_BY_MONTH: dict[int, tuple[str, str]] = {}
for t in THEMES["themes"]:
    for m in t.get("applicable_months", []):
        THEME_BY_MONTH.setdefault(m, (t["theme_id"], t["label"]))


def approved_copy(src: pathlib.Path) -> pathlib.Path:
    """시뮬레이션 전용 승인 사본. data/에 쓰지 않는다."""
    payload = json.loads(src.read_text("utf-8"))
    payload["review"] = dict(payload["review"])
    payload["review"]["domain_owner_approval"] = "HUMAN_APPROVED"
    payload["review"]["approved_by"] = "simulation_only_not_an_approval"
    payload["review"]["approved_at"] = "2026-09-13T00:00:00+09:00"
    out = TMP / "v0_2_1_simulation_approved.json"
    out.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return out


BEFORE = JsonActivityReferenceRepository(
    ROOT / "data" / "activities" / "activity_reference_v0_2.json"
).get_catalog(CATALOG_ID, V0)
AFTER = JsonActivityReferenceRepository(
    approved_copy(ROOT / "data" / "activities" / "activity_reference_v0_2_1_draft.json")
).get_catalog(CATALOG_ID, V1)


def target_month(m: int) -> str:
    return f"{2026 if m >= 3 else 2027}-{m:02d}"


def run(catalog, month: int, ages: frozenset[int]):
    tm = target_month(month)
    weeks = [w for w in canonical_week_periods(PeriodKey(tm)) if w.active]
    theme_id, theme_label = THEME_BY_MONTH.get(month, (None, "(없음)"))
    cands = catalog.eligible_candidates(
        section_key=OUTDOOR, calendar_month=month, ages=ages
    )
    used: set[str] = set()
    domains: dict[str, int] = {}
    rows = []
    for w in weeks:
        sel = select_activity_for_cell(
            candidates=cands,
            target_month=tm,
            section_key=OUTDOOR,
            week_id=w.week_id.value,
            parent_theme_id=theme_id,
            used_activity_ids=frozenset(used),
            used_curriculum_domains=domains,
        )
        c, tr = sel.candidate, sel.trace
        if c is None:
            rows.append({"week": w.week_id.value, "id": None, "label": "(EMPTY_VALID)",
                         "reason": tr.reason, "qp": 0, "ev": 0, "theme": False})
            continue
        used.add(c.activity_id)
        for link in c.curriculum_links:
            domains[link.domain] = domains.get(link.domain, 0) + 1
        rows.append({
            "week": w.week_id.value, "id": c.activity_id, "label": c.label,
            "reason": tr.reason, "qp": tr.display_quality_penalty,
            "ev": tr.evidence_strength, "theme": tr.theme_matched,
        })
    return {"theme": theme_label, "n_cand": len(cands), "rows": rows}


def bar(t):
    print()
    print("=" * 78)
    print(" " + t)
    print("=" * 78)


CASES = [
    (7, {3}), (5, {3}), (3, {4}), (9, {4}), (9, {5}), (2, {5}),
]

bar(f"§19. Before / After  (Ranking {RULE_VERSION})")
print(f"  BEFORE : {BEFORE.catalog_version}  항목 {len(BEFORE.activities)}")
print(f"  AFTER  : {AFTER.catalog_version}  항목 {len(AFTER.activities)} "
      f"(시뮬레이션 전용 승인 사본)")

changed_total = 0
for month, ages in CASES:
    b = run(BEFORE, month, frozenset(ages))
    a = run(AFTER, month, frozenset(ages))
    print()
    print("-" * 78)
    print(f" {target_month(month)}  만{sorted(ages)}세   Theme: {b['theme']}")
    print(f"   후보 수  BEFORE {b['n_cand']} → AFTER {a['n_cand']}")
    print()
    print("   BEFORE")
    for r in b["rows"]:
        print(f"     {r['week'][-2:]}  {r['label']}")
    print("   AFTER")
    for r in a["rows"]:
        print(f"     {r['week'][-2:]}  {r['label']}")
    diffs = [(x, y) for x, y in zip(b["rows"], a["rows"]) if x["label"] != y["label"]]
    if not diffs:
        print("   변경 없음")
        continue
    print()
    for x, y in diffs:
        changed_total += 1
        print(f"   [변경] {x['week']}")
        print(f"     previous activity_id : {x['id']}")
        print(f"     new activity_id      : {y['id']}")
        print(f"     previous value       : {x['label']}")
        print(f"     new value            : {y['label']}")
        print(f"     change reason        : {y['reason']}")
        print(f"     quality penalty      : before {x['qp']} → after {y['qp']}")
        print(f"     evidence count(월)   : before {x['ev']} → after {y['ev']}")
        print(f"     theme match          : before {x['theme']} → after {y['theme']}")
print()
print(f"  변경된 Cell 총계: {changed_total}")

bar("§20. 반드시 확인할 항목")
b_labels = {x.label for x in BEFORE.activities}
a_labels = {x.label for x in AFTER.activities}
for lab, want in [
    ("건너기", False),
    ("장화 신고 물웅덩이", False),
    ("장화 신고 물웅덩이 건너기", True),
    ("놀이를 해요.", False),
    ("우리집에 왜 왔니?", False),
    ("우리집에 왜 왔니? 놀이를 해요.", True),
    ("자연물로 여름 디저트 만들기", True),
    ("전통놀이", True),
]:
    got = lab in a_labels
    mark = "OK " if got == want else "!! "
    print(f"  {mark} v0.2.1에 {lab!r} 존재={got} (기대={want}) / v0.2.0 존재={lab in b_labels}")
trad = next(a for a in AFTER.activities if a.label == "전통놀이")
print(f"\n  전통놀이 display_quality={trad.display_quality} "
      f"status={trad.display_quality_review_status} "
      f"penalty대상={trad.has_confirmed_display_issue}")

bar("§21. Candidate Coverage Regression (12개월 × 연령조합)")
AGE_SETS = [frozenset(s) for s in ({3}, {4}, {5}, {3, 4}, {3, 5}, {4, 5})]
hdr = "  월  " + "".join(f"{'/'.join(map(str, sorted(s))):>10}" for s in AGE_SETS)
print(hdr)
zero_new = []
for m in list(range(3, 13)) + [1, 2]:
    row = f"  {m:>2}월"
    for s in AGE_SETS:
        nb = len(BEFORE.eligible_candidates(section_key=OUTDOOR, calendar_month=m, ages=s))
        na = len(AFTER.eligible_candidates(section_key=OUTDOOR, calendar_month=m, ages=s))
        flag = "" if na == nb else ("↓" if na < nb else "↑")
        row += f"{nb:>4}→{na:<4}{flag:<2}"
        if na == 0 and nb > 0:
            zero_new.append((m, sorted(s)))
    print(row)
print()
if zero_new:
    print(f"  !! 새로 후보 0이 된 조합: {zero_new}")
else:
    print("  새로 후보 0이 된 (월, 연령) 조합 없음")
print(f"  후보 0인 조합 (BEFORE부터 0): "
      f"{[(m, sorted(s)) for m in range(1, 13) for s in AGE_SETS if len(BEFORE.eligible_candidates(section_key=OUTDOOR, calendar_month=m, ages=s)) == 0]}")
