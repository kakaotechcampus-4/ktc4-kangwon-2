"""§4. 현재 Production Rule로 Monthly Case 12개 재현 (분석 전용).

Production module을 **import만** 한다. 수정하지 않고 runtime에 연결하지 않는다.
Selection 경로는 Production과 동일하다.

    ActivityCatalog.eligible_candidates()   ← hard filter (Domain)
    select_activity_for_cell()              ← ranking (M2-B Rule)

GenerateMonthlyPlan 전체를 돌리려면 연령별 Confirmed Yearly가 필요한데, 그 경로는
이미 E2E 테스트로 검증되어 있고 Cell 값 결정은 위 두 함수가 전담한다. 따라서
여기서는 두 함수를 직접 호출해 **같은 결과**를 재현한다.

    python analysis/experiments/monthly_vnext/reproduce_current.py
"""

from __future__ import annotations

import collections
import io
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from ssuksak.adapters.json_activity_reference_repository import (  # noqa: E402
    DEFAULT_ACTIVITY_CATALOG_PATH,
    JsonActivityReferenceRepository,
)
from ssuksak.planning.rules.monthly_activity_selection import (  # noqa: E402
    select_activity_for_cell,
)
from ssuksak.planning.rules.monthly_week_periods import (  # noqa: E402
    canonical_week_periods,
)
from ssuksak.planning.domain.identifiers import PeriodKey  # noqa: E402

CATALOG_ID = "ssuksak.outdoor-activity-reference"
CATALOG_VERSION = "activity-reference-v0.2.0"
OUTDOOR = "outdoor_play"

THEMES = json.loads(
    (ROOT / "data" / "themes" / "theme_reference_v0.json").read_text("utf-8")
)
# 월 → (theme_id, label). 한 달에 후보가 여러 개면 Yearly Rule이 고르는데,
# 여기서는 Demo 재현이 목적이므로 실제 Demo가 고른 것과 같은 첫 후보를 쓴다.
THEME_BY_MONTH: dict[int, tuple[str, str]] = {}
for t in THEMES["themes"]:
    for m in t.get("applicable_months", []):
        THEME_BY_MONTH.setdefault(m, (t["theme_id"], t["label"]))

CAT = JsonActivityReferenceRepository(DEFAULT_ACTIVITY_CATALOG_PATH).get_catalog(
    CATALOG_ID, CATALOG_VERSION
)
RAW = json.loads(DEFAULT_ACTIVITY_CATALOG_PATH.read_text("utf-8"))
RAW_BY_ID = {a["activity_id"]: a for a in RAW["activities"]}

SCHOOL_YEAR = 2026


def target_month_for(calendar_month: int) -> str:
    year = SCHOOL_YEAR if calendar_month >= 3 else SCHOOL_YEAR + 1
    return f"{year}-{calendar_month:02d}"


# ------------------------------------------------------------ Review Flag


def flags_for(act, candidate, calendar_month: int, ages) -> list[str]:
    """§4의 Review Flag. 자동 판정이 아니라 Human Review 후보 표시다."""
    out = []
    lab = candidate.label
    n = re.sub(r"[\s.,·…~!?\"'()\[\]]+", "", lab)

    if len(n) <= 3:
        out.append("TOO_SHORT")
    if re.fullmatch(r"[가-힣]{2,3}기", n):
        out.append("CONTEXT_DEPENDENT_LABEL")
    if re.search(r"^(놀이|활동)(를|을)?\s*(해요|합니다|한다)\.?$", lab):
        out.append("CONTEXT_DEPENDENT_LABEL")
    if re.search(r"(을|를|은|는|의|에|와|과|으로|로)$", lab) and not re.search(
        r"(놀이|하기|먹기|보기|찾기|잡기|쌓기|만들기)$", lab
    ):
        out.append("POSSIBLE_FRAGMENT")
    if any(w in lab for w in ("유희실", "강당", "옥상", "텃밭", "산책로", "놀이터",
                              "운동장", "테라스", "마당", "공원", "체육관")):
        out.append("INSTITUTION_SPECIFIC")

    # age evidence
    scopes = [tuple(e.get("age_scope", [])) for e in act.get("evidence", [])]
    for age in sorted(ages):
        if not any(len(s) == 1 and s[0] == age for s in scopes):
            out.append("AGE_EVIDENCE_WEAK")
            break
    # month evidence
    if sum(1 for e in act.get("evidence", []) if e.get("observed_month") == calendar_month) <= 1:
        out.append("MONTH_EVIDENCE_THIN")
    return out


def institutions_of(act) -> set[str]:
    out = set()
    for e in act.get("evidence", []):
        oid = e["origin_id"]
        out.add(oid.split(".")[2] if oid.count(".") >= 2 else oid)
    return out


def run_case(calendar_month: int, ages: frozenset[int]) -> dict:
    tm = target_month_for(calendar_month)
    weeks = [w for w in canonical_week_periods(PeriodKey(tm)) if w.active]
    theme_id, theme_label = THEME_BY_MONTH.get(calendar_month, (None, "(없음)"))

    cands = CAT.eligible_candidates(
        section_key=OUTDOOR, calendar_month=calendar_month, ages=ages
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
            rows.append({"week": w.week_id.value, "empty": True, "reason": tr.reason})
            continue
        used.add(c.activity_id)
        for link in c.curriculum_links:
            domains[link.domain] = domains.get(link.domain, 0) + 1
        raw = RAW_BY_ID[c.activity_id]
        rows.append({
            "week": w.week_id.value,
            "empty": False,
            "activity_id": c.activity_id,
            "label": c.label,
            "reason": tr.reason,
            "theme_matched": tr.theme_matched,
            "month_evidence": tr.evidence_strength,
            "total_evidence": len(raw.get("evidence", [])),
            "institutions": sorted(institutions_of(raw)),
            "flags": flags_for(raw, c, calendar_month, ages),
        })
    return {
        "month": calendar_month,
        "target_month": tm,
        "ages": sorted(ages),
        "theme_id": theme_id,
        "theme_label": theme_label,
        "candidate_count": len(cands),
        "weeks": len(weeks),
        "rows": rows,
    }


CASES = [
    (3, {3}), (5, {3}), (7, {3}), (11, {3}),
    (3, {4}), (5, {4}), (9, {4}), (1, {4}),
    (7, {5}), (9, {5}), (11, {5}), (2, {5}),
]


def main() -> int:
    print("=" * 78)
    print(" §4. 현재 Production Rule 재현 — Monthly 12 Case")
    print("=" * 78)
    print(f" Catalog  : {CAT.catalog_id} @ {CAT.catalog_version} (활성 {CAT.is_active})")
    print(f" 경로     : eligible_candidates() → select_activity_for_cell()")
    print(f" Rule     : monthly.activity.reference_candidate_selection v1")
    print()

    results = []
    flag_tally = collections.Counter()
    for m, ages in CASES:
        r = run_case(m, frozenset(ages))
        results.append(r)
        print("-" * 78)
        print(f" {r['target_month']}  만{r['ages']}세  Theme: {r['theme_label']}")
        print(f"   후보 {r['candidate_count']}개 · 주차 {r['weeks']}개")
        for row in r["rows"]:
            if row["empty"]:
                print(f"   {row['week'][-2:]}  (EMPTY_VALID) {row['reason']}")
                continue
            fl = ",".join(row["flags"]) or "GOOD"
            print(f"   {row['week'][-2:]}  {row['label'][:34]:<34} "
                  f"ev月{row['month_evidence']}/총{row['total_evidence']} "
                  f"기관{len(row['institutions'])} theme={str(row['theme_matched'])[0]} [{fl}]")
            for f in row["flags"]:
                flag_tally[f] += 1
        # type diversity 근사: label 말미 어휘
        labs = [r2["label"] for r2 in r["rows"] if not r2["empty"]]
        walk = sum(1 for l in labs if re.search(r"산책|나들이|가보기|찾아가|탐험", l))
        if labs and walk >= max(2, len(labs) // 2):
            print(f"   ! REPETITIVE_ACTIVITY_TYPE — 산책/나들이류 {walk}/{len(labs)}")
            flag_tally["REPETITIVE_ACTIVITY_TYPE"] += 1

    print()
    print("=" * 78)
    print(" Flag 집계 (Human Review 후보)")
    print("=" * 78)
    total_cells = sum(len([x for x in r["rows"] if not x["empty"]]) for r in results)
    print(f"  생성된 Cell 총계: {total_cells}")
    for k, n in flag_tally.most_common():
        print(f"    {k:<28}{n}")

    out = ROOT / "analysis" / "tmp" / "monthly_cases_current.json"
    out.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n  저장: {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
