"""Monthly LLM Planner vNext — Prototype 실행 (분석 전용 · Production 무변경).

5 Case에 대해 Context Packet을 조립하고, Token Budget을 측정하고,
Deterministic Validator를 **실제로** 돌린다.

LLM 호출은 기본적으로 하지 않는다. 사람이 만든 예시 Output으로 Validator가
작동하는지 확인하며, 그 결과는 전부 `DESIGN_SIMULATION`으로 표기한다.
`--live`를 주면 환경변수에 설정된 실제 Adapter로 1회 호출을 시도한다
(실패해도 Blocker가 아니다).

    python analysis/experiments/monthly_llm_vnext/run_prototype.py [--live]
"""

from __future__ import annotations

import io
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from planner_contract import (  # noqa: E402
    CONSTRAINTS,
    PROMPT_VERSION,
    SYSTEM_PROMPT,
    MonthlyPlanProposal,
    parse_proposal,
    render_packet,
    validate_proposal,
)
from retriever import MonthlyRetriever, RetrievalQuery, build_packet  # noqa: E402

from ssuksak.planning.domain.identifiers import PeriodKey  # noqa: E402
from ssuksak.planning.rules.monthly_week_periods import (  # noqa: E402
    canonical_week_periods,
)

THEMES = json.loads((ROOT / "data" / "themes" / "theme_reference_v0.json")
                    .read_text("utf-8"))
THEME_BY_MONTH: dict[int, tuple[str, str]] = {}
for t in THEMES["themes"]:
    for m in t.get("applicable_months", []):
        THEME_BY_MONTH.setdefault(m, (t["theme_id"], t["label"]))

CASES = [
    ("2026-03", 3, (3,)),
    ("2026-06", 6, (4,)),
    ("2026-07", 7, (4,)),
    ("2026-08", 8, (4,)),
    ("2027-02", 2, (5,)),
]


def approx_tokens(text: str) -> int:
    """한국어는 대략 글자당 0.7~1.0 token이다. 보수적으로 1.0으로 센다.

    정확한 tokenizer를 붙이지 않는다 — Budget **상한** 추정이 목적이다.
    """
    return len(text)


def make_query(target_month: str, cal: int, ages: tuple[int, ...]) -> RetrievalQuery:
    weeks = tuple(w.week_id.value for w in canonical_week_periods(PeriodKey(target_month))
                  if w.active)
    tid, tlabel = THEME_BY_MONTH.get(cal, ("yr_theme_unknown", "(없음)"))
    return RetrievalQuery(target_month, cal, ages, tid, tlabel, weeks)


def simulated_output(q: RetrievalQuery, blocks) -> dict:
    """**DESIGN_SIMULATION.** 사람이 규칙적으로 만든 예시다. GPT 결과가 아니다.

    Validator가 실제로 동작하는지 보기 위한 입력이며, 품질 판단 대상이 아니다.
    """
    ref = next(b for b in blocks if b.name == "REFERENCE ACTIVITIES")
    corp = next(b for b in blocks if b.name == "OTHER RETRIEVED ACTIVITY EVIDENCE")
    exp = next(b for b in blocks if b.name == "WEEK EXPERIENCE CANDIDATES")
    weeks = []
    for i, wid in enumerate(q.week_ids):
        if i < len(ref.items):
            it = ref.items[i]
            act = {"value": it["label"], "origin": "REFERENCE",
                   "reference_activity_id": it["activity_id"],
                   "grounding_source_ids": []}
        elif i - len(ref.items) < len(corp.items):
            it = corp.items[i - len(ref.items)]
            act = {"value": (it.get("activity_text") or "")[:60],
                   "origin": "CORPUS_EVIDENCE", "reference_activity_id": None,
                   "grounding_source_ids": [it["record_id"]]}
        else:
            src = [x["record_id"] for x in exp.items[:2]]
            act = {"value": f"{q.theme_label} 이야기 나누며 산책하기",
                   "origin": "LLM_SYNTHESIZED", "reference_activity_id": None,
                   "grounding_source_ids": src}
        e = exp.items[i % len(exp.items)] if exp.items else None
        experience = ((e.get("experience_text") or f"{q.theme_label} 경험 {i+1}")[:80]
                      if e else f"{q.theme_label} 경험 {i+1}")
        weeks.append({"week_id": wid, "experience": f"{experience} ({i+1})",
                      "activity": act})
    return {"theme_id": q.theme_id,
            "month_flow_rationale": "DESIGN_SIMULATION 예시 — 실제 모델 출력이 아니다.",
            "weeks": weeks}


def main(argv: list[str]) -> int:
    live = "--live" in argv
    retr = MonthlyRetriever()
    line = "=" * 96
    rows = []

    for target_month, cal, ages in CASES:
        q = make_query(target_month, cal, ages)
        blocks = build_packet(q, retr)
        packet = render_packet(blocks, q)
        prompt = SYSTEM_PROMPT + "\n" + packet + "\n" + CONSTRAINTS

        print(line)
        print(f" {q.target_month}  만{'·'.join(map(str,q.ages))}세   "
              f"Theme={q.theme_label}   주차 {len(q.week_ids)}")
        print(line)
        budget = {
            "SYSTEM+CONSTRAINTS": approx_tokens(SYSTEM_PROMPT + CONSTRAINTS),
        }
        for b in blocks:
            seg = render_packet([b], q)
            budget[b.name] = approx_tokens(seg) - approx_tokens(render_packet([], q))
        total = approx_tokens(prompt)
        print(f"  Block 반환 수: " + " · ".join(
            f"{b.name.split()[0]}={len(b.items)}" for b in blocks))
        print(f"  Prompt 총 문자 수(≈token 상한): {total}")
        for k, v in budget.items():
            print(f"    {k:<34}{v:>7}  ({v/total:>4.0%})")

        proposal = parse_proposal(simulated_output(q, blocks))
        issues = validate_proposal(proposal, q=q, blocks=blocks)
        print(f"\n  [DESIGN_SIMULATION] Validator: "
              f"{'PASS' if not issues else f'{len(issues)} issue'}")
        for it in issues:
            print(f"    - {it.rule}: {it.detail}")
        origins = [w.activity.origin for w in proposal.weeks]
        print(f"  origin 분포: {origins}")
        rows.append({
            "case": f"{q.target_month} 만{q.ages}", "tokens": total,
            "blocks": {b.name: len(b.items) for b in blocks},
            "validator_issues": len(issues), "origins": origins,
        })

        # 위반 주입 테스트 — Validator가 실제로 잡는지 확인
        broken = json.loads(proposal.model_dump_json())
        broken["theme_id"] = "yr_theme_hacked"
        broken["weeks"][0]["activity"]["origin"] = "LLM_SYNTHESIZED"
        broken["weeks"][0]["activity"]["reference_activity_id"] = None
        broken["weeks"][0]["activity"]["grounding_source_ids"] = ["ev_없는id"]
        broken["weeks"][0]["experience"] = "누리과정에서 반드시 하는 활동"
        if len(broken["weeks"]) > 1:
            broken["weeks"][1]["activity"]["value"] = \
                broken["weeks"][0]["activity"]["value"]
        bad_issues = validate_proposal(parse_proposal(broken), q=q, blocks=blocks)
        print(f"  [위반 주입] Validator가 잡은 위반: {len(bad_issues)}")
        for it in bad_issues[:6]:
            print(f"    - {it.rule}")
        print()

    print(line)
    print(" 요약")
    print(line)
    print(f"  {'Case':<20}{'≈Prompt 문자':>14}{'Validator':>12}  origin")
    for r in rows:
        print(f"  {r['case']:<20}{r['tokens']:>14}{r['validator_issues']:>12}  "
              f"{r['origins']}")
    avg = sum(r["tokens"] for r in rows) / len(rows)
    print(f"\n  평균 Prompt ≈ {avg:.0f}자.  196개 Activity 전체를 넣었을 때와 비교하면:")
    cat = json.loads((ROOT / "data" / "activities" /
                      "activity_reference_v0_2_1.json").read_text("utf-8"))
    all_labels = sum(len(a["label"]) + 24 for a in cat["activities"])
    print(f"    Reference 196개 전체 나열 ≈ {all_labels}자 (id+label만 계산)")
    print(f"    Top-K(12)만 넣으면 ≈ {all_labels * 12 // 196}자 → "
          f"{12/196:.0%} 규모")

    (ROOT / "analysis" / "tmp" / "monthly_llm_prototype.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\n  저장: analysis/tmp/monthly_llm_prototype.json")
    print(f"  prompt_version: {PROMPT_VERSION}")

    if live:
        print("\n" + line)
        print(" LIVE 호출 시도 (실패해도 Blocker 아님)")
        print(line)
        try:
            from ssuksak.shared.llm.config import load_llm_config
            cfg = load_llm_config()
            print(f"  model={cfg.model}  api_style={cfg.api_style.value}  "
                  "(API Key는 출력하지 않는다)")
            print("  ※ Prototype은 Production Adapter의 polish_theme 계약만 알고 있고")
            print("    Monthly Planner용 호출 경로는 아직 Production에 없다.")
            print("    따라서 이번 단계에서는 호출하지 않는다 — 설계 단계에서 Adapter를")
            print("    추가하는 것은 §46 Production Freeze 위반이다.")
        except Exception as exc:  # noqa: BLE001
            print(f"  설정 확인 실패: {type(exc).__name__}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
