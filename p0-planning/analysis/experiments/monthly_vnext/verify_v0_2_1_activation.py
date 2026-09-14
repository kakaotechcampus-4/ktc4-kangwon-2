"""v0.2.1 Activation 검증 (§8~§13). 실제 Monthly Use Case를 그대로 실행한다.

Fake Catalog도 Mock도 쓰지 않는다. Production Composition
(`build_monthly_wiring`)이 조립한 Use Case를 호출하고, Reference는 승인된
실제 파일만 읽는다. LLM 호출은 0회다(Monthly는 Rule 전용, 상위 Yearly fixture는
`use_llm=False` 경로).

    python analysis/experiments/monthly_vnext/verify_v0_2_1_activation.py
"""

from __future__ import annotations

import io
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from ssuksak.adapters.json_activity_reference_repository import (  # noqa: E402
    DEFAULT_ACTIVITY_CATALOG_PATH,
    SUPERSEDED_ACTIVITY_CATALOG_PATHS,
    production_activity_reference_repository,
)
from ssuksak.dev.monthly_wiring import DEV_ACTOR, build_monthly_wiring  # noqa: E402
from ssuksak.planning.application.dto import CatalogSelector  # noqa: E402
from ssuksak.planning.application.monthly_dto import (  # noqa: E402
    ConfirmMonthlyPlanCommand,
    EditMonthlyPlanItemCommand,
    GenerateMonthlyPlanCommand,
    MonthlyCellAddress,
    RegenerateMonthlyPlanItemCommand,
)
from ssuksak.planning.domain.errors import PlanningError  # noqa: E402
from ssuksak.planning.domain.provenance import EvidenceSourceType  # noqa: E402

CATALOG_ID = "ssuksak.outdoor-activity-reference"
V0 = "activity-reference-v0.2.0"
V1 = "activity-reference-v0.2.1"
OUTDOOR = "outdoor_play"
ACTOR = DEV_ACTOR

FRAGMENTS = ("건너기", "장화 신고 물웅덩이", "우리집에 왜 왔니?", "놀이를 해요.")
RESTORED = ("장화 신고 물웅덩이 건너기", "우리집에 왜 왔니? 놀이를 해요.")

failures: list[str] = []


def check(ok: bool, label: str) -> None:
    print(f"    {'PASS' if ok else 'FAIL'}  {label}")
    if not ok:
        failures.append(label)


def wiring(month: str, ages: frozenset[int], year: int = 2026):
    return build_monthly_wiring(target_month=month, school_year=year, ages=ages)


def generate(w, **over):
    base = dict(
        parent_yearly_plan_id=w.parent_yearly.plan_id.value,
        school_year=w.school_year,
        target_month=w.target_month,
        daycare=w.daycare,
        classroom=w.classroom,
        planning_setup=w.planning_setup,
        template_ref=w.template_ref,
        safety_rule=w.safety_rule,
        catalog=w.catalog,
        activity_catalog=w.activity_catalog,
    )
    base.update(over)
    return w.generate.execute(GenerateMonthlyPlanCommand(**base))


def outdoor(plan):
    section = plan.section(OUTDOOR)
    return section.items if section else []


def activity_id_of(item):
    for e in item.evidence:
        if e.source_type is EvidenceSourceType.ACTIVITY_REFERENCE:
            return e.source_id
    return None


def theme_value(plan):
    section = plan.section("theme")
    return section.items[0].value if section and section.items else None


def show(plan, title: str) -> list[str]:
    print(f"\n  {title}")
    print(f"    Theme: {theme_value(plan)}")
    labels = []
    for item in outdoor(plan):
        wid = item.week_id.value if item.week_id else "-"
        labels.append(item.value or "")
        print(f"    {wid}  {item.cell_state.value:<16} {item.value}")
    return labels


# ============================================================ §8 Production Generate


def section_8():
    print("\n" + "=" * 78)
    print(" §8. Production Generate — 만3 / 만4 / 만5")
    print("=" * 78)
    print(f"  default catalog file : {DEFAULT_ACTIVITY_CATALOG_PATH.name}")
    print(f"  superseded resolvable: "
          f"{[p.name for p in SUPERSEDED_ACTIVITY_CATALOG_PATHS]}")
    for age in (3, 4, 5):
        w = wiring("2026-09", frozenset({age}))
        result = generate(w)
        plan = result.plan
        run = result.run
        print(f"\n  -- 만{age}세 2026-09")
        print(f"    activity_catalog.version : {plan.activity_catalog.catalog_version}")
        rules = {
            (i.generation.rule_id, i.generation.rule_version)
            for i in outdoor(plan)
            if i.generation.rule_id
        }
        print(f"    selection_rule           : {sorted(rules)}")
        print(f"    llm_invoked              : {run.llm_invoked}")
        check(plan.activity_catalog.catalog_version == V1,
              f"만{age}세 activity_catalog.version == {V1}")
        check(rules == {("monthly.activity.reference_candidate_selection", "v2")},
              f"만{age}세 selection_rule == v2")
        check(run.llm_invoked is False, f"만{age}세 Monthly LLM calls == 0")


# ============================================================ §9 2026-07 만3세


def section_9():
    print("\n" + "=" * 78)
    print(" §9. 2026-07 만3세 Regression")
    print("=" * 78)
    w = wiring("2026-07", frozenset({3}))
    plan = generate(w).plan
    labels = show(plan, "AFTER (v0.2.1 default)")
    check(plan.activity_catalog.catalog_version == V1, "2026-07 만3세 pin == v0.2.1")
    for frag in FRAGMENTS:
        check(frag not in labels, f"조각 Activity 없음: {frag!r}")

    catalog = production_activity_reference_repository().get_catalog(CATALOG_ID, V1)
    pool = catalog.eligible_candidates(
        section_key=OUTDOOR, calendar_month=7, ages=frozenset({3})
    )
    pool_labels = {c.label for c in pool}
    print(f"\n    7월 만3세 후보 {len(pool)}개")
    for frag in FRAGMENTS:
        check(frag not in pool_labels, f"후보 pool에 조각 없음: {frag!r}")
    for restored in RESTORED:
        present = restored in {a.label for a in catalog.activities}
        print(f"    복원 Activity {restored!r}: catalog={present}, "
              f"7월만3세후보={restored in pool_labels}")
    return labels


# ============================================================ §10 전통놀이


def section_10():
    print("\n" + "=" * 78)
    print(" §10. 전통놀이 Regression (2026-09 만5세)")
    print("=" * 78)
    catalog = production_activity_reference_repository().get_catalog(CATALOG_ID, V1)
    trad = next(a for a in catalog.activities if a.label == "전통놀이")
    print(f"    display_quality               : {trad.display_quality}")
    print(f"    display_quality_review_status : {trad.display_quality_review_status}")
    check(trad.display_quality.value == "TOO_GENERIC", "전통놀이 TOO_GENERIC")
    check(trad.display_quality_review_status.value == "HUMAN_CONFIRMED",
          "전통놀이 HUMAN_CONFIRMED")
    check(trad.has_confirmed_display_issue, "전통놀이 soft penalty 대상")

    pool = catalog.eligible_candidates(
        section_key=OUTDOOR, calendar_month=9, ages=frozenset({5})
    )
    check(any(c.activity_id == trad.activity_id for c in pool),
          "전통놀이 Hard Exclusion 아님 (9월 만5세 후보에 남아 있음)")

    w = wiring("2026-09", frozenset({5}))
    plan = generate(w).plan
    labels = show(plan, "2026-09 만5세 (v0.2.1 default)")
    print(f"\n    W2 = {labels[1]!r}")
    check("전통놀이" not in labels, "선택 결과에 전통놀이 없음 (soft penalty 작동)")
    return labels


# ============================================================ §11 Pinning


def section_11():
    print("\n" + "=" * 78)
    print(" §11. Exact Catalog Pinning")
    print("=" * 78)
    for name, version in (("A — Legacy v0.2.0", V0), ("B — New v0.2.1", V1)):
        w = wiring("2026-09", frozenset({4}))
        plan = generate(w, activity_catalog=CatalogSelector(CATALOG_ID, version)).plan
        before = [i.value for i in outdoor(plan)]
        outcome = w.regenerate.execute(
            RegenerateMonthlyPlanItemCommand(
                plan_id=plan.plan_id.value,
                address=MonthlyCellAddress(
                    target_month="2026-09", section_key=OUTDOOR, week_id="2026-09-W2"
                ),
                actor_id=ACTOR,
            )
        ).activity_regeneration
        after = [i.value for i in outdoor(w.monthly_plans.get(plan.plan_id.value))]
        print(f"\n  Scenario {name}")
        print(f"    generate pin      : {plan.activity_catalog.catalog_version}")
        print(f"    regenerate loaded : {outcome.catalog_version}")
        print(f"    W2 {before[1]!r} → {after[1]!r}")
        check(plan.activity_catalog.catalog_version == version,
              f"Scenario {name}: generate pin == {version}")
        check(outcome.catalog_version == version,
              f"Scenario {name}: regenerate exact load == {version}")
        check([before[0], *before[2:]] == [after[0], *after[2:]],
              f"Scenario {name}: 비대상 Cell 보존")


# ============================================================ §12 Coverage


def section_12():
    print("\n" + "=" * 78)
    print(" §12. Candidate Coverage — 12개월 × 6 age combinations")
    print("=" * 78)
    repo = production_activity_reference_repository()
    new = repo.get_catalog(CATALOG_ID, V1)
    old = repo.get_catalog(CATALOG_ID, V0)
    combos = [frozenset(c) for c in ([3], [4], [5], [3, 4], [3, 5], [4, 5])]
    header = "  월  " + "".join(f"{'만' + '+'.join(map(str, sorted(c))) + '세':>12}"
                                for c in combos)
    print(header)
    newly_zero = []
    for m in range(1, 13):
        row = f"  {m:>2}월"
        for c in combos:
            nb = len(old.eligible_candidates(
                section_key=OUTDOOR, calendar_month=m, ages=c))
            na = len(new.eligible_candidates(
                section_key=OUTDOOR, calendar_month=m, ages=c))
            row += f"{nb:>6}→{na:<5}"
            if na == 0 and nb > 0:
                newly_zero.append((m, sorted(c), nb, na))
        print(row)
    print(f"\n    newly introduced 0-candidate combos: {len(newly_zero)}")
    for m, c, nb, na in newly_zero:
        print(f"      {m}월 만{c}세  {nb} → {na}")
    check(not newly_zero, "새로운 0 Candidate 조합 없음")


# ============================================================ §13 Contract


def section_13():
    print("\n" + "=" * 78)
    print(" §13. 기존 Monthly Contract Regression")
    print("=" * 78)

    # Generate candidate 0 → EMPTY_VALID (2026-11 만3세는 후보가 0인 조합을 쓴다)
    repo = production_activity_reference_repository()
    cat = repo.get_catalog(CATALOG_ID, V1)
    zero = None
    for m in range(1, 13):
        for c in ([3], [4], [5], [3, 4], [3, 5], [4, 5]):
            if not cat.eligible_candidates(
                section_key=OUTDOOR, calendar_month=m, ages=frozenset(c)
            ):
                zero = (m, frozenset(c))
                break
        if zero:
            break
    if zero is None:
        print("    승인본 v0.2.1에는 후보 0 조합이 없다(§12 coverage 참조).")
        print("    따라서 candidate 0 Semantics는 실제 Catalog로 재현할 수 없고")
        print("    In-Memory Catalog를 쓰는 기존 Test가 계속 고정한다:")
        print("      tests/dev/test_monthly_e2e.py"
              "::test_generate_with_zero_candidates_yields_empty_valid")
        print("      tests/dev/test_monthly_e2e.py"
              "::test_regenerate_with_zero_candidates_is_blocked_and_preserves_the_cell")
    else:
        m, ages = zero
        tm = f"{2026 if m >= 3 else 2027}-{m:02d}"
        w = wiring(tm, ages, year=2026)
        result = generate(w)
        states = {i.cell_state.value for i in outdoor(result.plan)}
        print(f"\n  Generate candidate 0 ({tm} 만{sorted(ages)}세)")
        print(f"    outdoor cell states : {states}")
        print(f"    saved               : {result.plan.plan_id.value is not None}")
        check(states == {"EMPTY_VALID"}, "Generate candidate 0 → EMPTY_VALID")

        plan = result.plan
        before = [(i.value, i.cell_state) for i in outdoor(plan)]
        saves_before = len(w.monthly_plans.saved_versions(plan.plan_id.value)) \
            if hasattr(w.monthly_plans, "saved_versions") else None
        blocked = False
        try:
            w.regenerate.execute(
                RegenerateMonthlyPlanItemCommand(
                    plan_id=plan.plan_id.value,
                    address=MonthlyCellAddress(
                        target_month=tm, section_key=OUTDOOR,
                        week_id=outdoor(plan)[1].week_id.value,
                    ),
                    actor_id=ACTOR,
                )
            )
        except PlanningError as exc:
            blocked = True
            print(f"\n  Regenerate candidate 0 → BLOCKED  ({exc.violated_rule})")
        after = [(i.value, i.cell_state)
                 for i in outdoor(w.monthly_plans.get(plan.plan_id.value))]
        check(blocked, "Regenerate candidate 0 → BLOCKED")
        check(before == after, "Regenerate candidate 0 → 기존 값 보존")
        if saves_before is not None:
            print(f"    save 횟수 변화 없음 확인 대상: {saves_before}")

    # CONFIRMED read-only + safety unresolved + LLM 0
    w = wiring("2026-09", frozenset({4}))
    result = generate(w)
    plan = result.plan
    safety = plan.section("safety_education")
    states = {i.cell_state.value for i in safety.items}
    print(f"\n  safety_education cell states : {states}")
    check(states == {"EMPTY_UNRESOLVED"}, "Safety unresolved Semantics 유지")
    check(result.run.llm_invoked is False, "Monthly LLM 0 calls")

    confirmed = w.confirm.execute(
        ConfirmMonthlyPlanCommand(plan_id=plan.plan_id.value, actor_id=ACTOR)
    ).plan
    print(f"  confirmed status : {confirmed.status}")
    edit_blocked = regen_blocked = False
    try:
        w.edit.execute(
            EditMonthlyPlanItemCommand(
                plan_id=plan.plan_id.value,
                address=MonthlyCellAddress(
                    target_month="2026-09", section_key=OUTDOOR,
                    week_id="2026-09-W2",
                ),
                new_value="교사 수정",
                actor_id=ACTOR,
            )
        )
    except PlanningError:
        edit_blocked = True
    try:
        w.regenerate.execute(
            RegenerateMonthlyPlanItemCommand(
                plan_id=plan.plan_id.value,
                address=MonthlyCellAddress(
                    target_month="2026-09", section_key=OUTDOOR, week_id="2026-09-W2"
                ),
                actor_id=ACTOR,
            )
        )
    except PlanningError:
        regen_blocked = True
    check(edit_blocked, "CONFIRMED → edit blocked")
    check(regen_blocked, "CONFIRMED → regenerate blocked")


def main() -> int:
    section_8()
    section_9()
    section_10()
    section_11()
    section_12()
    section_13()
    print("\n" + "=" * 78)
    if failures:
        print(f" ACTIVATION VERIFY FAIL — {len(failures)}건")
        for f in failures:
            print(f"   - {f}")
        return 1
    print(" ACTIVATION VERIFY PASS — 전 항목 통과")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
