"""Demo 전체 흐름 점검 (선택적 도구).

떠 있는 Demo 서버에 HTTP로 붙어 화면과 **같은 경로**를 순서대로 호출한다.
브라우저 없이 Yearly → Confirm → Gate → Monthly → Confirm 이 실제로 동작하는지
확인할 때 쓴다. 프로젝트 테스트(tests/)와 무관하며 pytest가 수집하지 않는다.

    python demo-planning/backend/app.py --port 8802        # 다른 창에서 먼저 실행
    python demo-planning/tools/smoke_flow.py --port 8802

`--port`만 받는다. 서버가 어떤 모드(실제 LLM / --yearly-rule-only)로 떠 있든
그 서버의 응답을 그대로 보고한다. 이 스크립트는 결과를 만들어 내지 않는다.
"""

from __future__ import annotations

import argparse
import io
import json
import sys
import urllib.error
import urllib.request

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


def call(base: str, path: str, body: dict | None = None):
    url = base + path
    if body is None:
        req = urllib.request.Request(url)
    else:
        req = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
    try:
        with urllib.request.urlopen(req, timeout=180) as res:
            return res.status, json.loads(res.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


def show_error(data: dict) -> None:
    print(f"    kind           : {data.get('kind')}")
    if data.get("kind") == "PLANNING_ERROR":
        print(f"    outcome        : {data.get('outcome')}")
        print(f"    category       : {data.get('failure_category')}")
        print(f"    violated_rule  : {data.get('violated_rule')}")
        for v in data.get("violations", []):
            if v.get("detail"):
                print(f"    detail         : {v['detail']}")
    else:
        print(f"    message        : {data.get('message')}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8800)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--month", default="2026-09")
    ap.add_argument("--school-year", type=int, default=2026)
    ap.add_argument("--ages", default="4")
    args = ap.parse_args(argv)
    base = f"http://{args.host}:{args.port}"
    ages = [int(a) for a in args.ages.split(",") if a.strip()]
    failures = 0

    print("=" * 70)
    print(f" Demo 흐름 점검  {base}")
    print("=" * 70)

    # ---------------------------------------------------------- 0. 참조
    status, s = call(base, "/api/state")
    ref = s.get("references")
    if ref is None:
        print("  LLM 설정 오류:", s.get("llm_config_error"))
        return 1
    print("[0] 사용 중인 Reference")
    print(f"    Theme            : {ref['theme_catalog_version']}")
    print(f"    Monthly Template : {ref['template_version']}")
    print(f"    Safety Rule      : {ref['safety_rule_version']}")
    print(f"    Activity         : {ref['activity_catalog_version']}")
    print(f"    Yearly LLM 경로  : "
          f"{'실제 LLM 호출' if ref['yearly_uses_llm'] else 'Rule 전용 (LLM 없음)'}"
          f"  [{ref['llm_provider']} / {ref['llm_model']}]")
    print()

    # ------------------------------------------------- 1. Yearly Generate
    print("[1] POST /api/yearly/generate  (실제 GenerateYearlyPlan)")
    status, d = call(
        base,
        "/api/yearly/generate",
        {
            "school_year": args.school_year,
            "ages": ages,
            "daycare_ref": "demo_daycare_001",
            "classroom_ref": "demo_classroom_001",
        },
    )
    if status != 200:
        print(f"    HTTP {status} — 실제 오류가 그대로 반환되었습니다")
        show_error(d)
        print()
        print("    Yearly 생성이 실패해 이후 단계를 진행할 수 없습니다.")
        return 1
    y = d["yearly"]
    print(f"    HTTP 200  plan_id={y['plan_id']}  status={y['status']}  "
          f"months={len(y['months'])}")
    run = y["run"] or {}
    print(f"    llm_invoked={run.get('llm_invoked')}  "
          f"llm_call_count={run.get('llm_call_count')}  "
          f"catalog={run.get('catalog_version')}")
    print()
    print("    월별 생활주제")
    for m in y["months"]:
        print(f"      {m['month_label']:>4}  {m['value']:<30} {m['theme_id']}")
    print()

    # ------------------------------- 2. Gate: DRAFT에서 Monthly 생성 시도
    print("[2] DRAFT 상태에서 월간 생성 시도 (실제 Gate가 막아야 한다)")
    status, d = call(base, "/api/monthly/generate", {"target_month": args.month})
    if status == 200:
        print("    !! 차단되지 않았습니다")
        failures += 1
    else:
        print(f"    HTTP {status}")
        show_error(d)
        print(f"    monthly 상태 : {d['state']['monthly']}")
    print()

    # --------------------------------------------------- 3. Yearly Confirm
    print("[3] POST /api/yearly/confirm  (실제 ConfirmYearlyPlan)")
    status, d = call(base, "/api/yearly/confirm", {})
    if status != 200:
        print(f"    HTTP {status}")
        show_error(d)
        return 1
    print(f"    HTTP 200  status={d['yearly']['status']}  "
          f"audit={' → '.join(a['event_type'] for a in d['yearly']['audit'])}")
    print(f"    월간 생성 가능 : {d['monthly_generate_enabled']}")
    print()

    # -------------------------------------------------- 4. Monthly Generate
    print(f"[4] POST /api/monthly/generate  target_month={args.month}")
    status, d = call(base, "/api/monthly/generate", {"target_month": args.month})
    if status != 200:
        print(f"    HTTP {status}")
        show_error(d)
        return 1
    m = d["monthly"]
    mrun = m["run"]
    print(f"    HTTP 200  plan_id={m['plan_id']}  status={m['status']}")
    print(f"    주차 {mrun['week_period_count']}개 · Cell {mrun['generated_cell_count']}개 "
          f"(FILLED {mrun['filled_cell_count']} / EMPTY_VALID "
          f"{mrun['empty_valid_cell_count']} / EMPTY_UNRESOLVED "
          f"{mrun['empty_unresolved_cell_count']})")
    print(f"    Activity Catalog : {m['activity_catalog']['catalog_version']}")
    mode = mrun.get("generation_mode", "RULE_ONLY")
    print(f"    생성 경로        : {mode}")
    print(f"    Monthly LLM 호출 : {mrun['llm_call_count']}")
    if mode == "LLM_PLANNER":
        print(f"    model            : {mrun.get('planner_model')}")
        print(f"    prompt_version   : {mrun.get('prompt_version')}")
        print(f"    L5 repair        : "
              f"{mrun.get('planner_validation_repair_count')}")
        if mrun["llm_call_count"] < 1:
            print("    !! LLM_PLANNER인데 호출이 0회입니다")
            failures += 1
        if not any(r["section_key"] == "focus" for r in m["rows"]):
            print("    !! focus Section이 화면 데이터에 없습니다")
            failures += 1
    elif mrun["llm_call_count"] != 0:
        print("    !! RULE_ONLY는 LLM 0회여야 합니다")
        failures += 1
    print(f"    주제 : {m['theme']['value']}")
    print()
    weeks = [w for w in m["weeks"] if w["active"]]
    header = "      {:<12}".format("구분") + "".join(
        f"{w['week_id'][-2:]:<24}" for w in weeks
    )
    print(header)
    for row in m["rows"]:
        by = {c["week_id"]: c for c in row["cells"]}
        line = "      {:<12}".format(row["label"])
        for w in weeks:
            c = by.get(w["week_id"])
            txt = (c["value"] or "").strip() if c else ""
            if not txt:
                txt = "·" if c and c["cell_state"] == "EMPTY_VALID" else "▲"
            line += f"{txt:<24}"
        print(line)
    print("      (· = 비워 두는 것이 정상 / ▲ = 근거 없어 비워 둠)")
    print()
    print("    Activity Selection Trace")
    for t in mrun["traces"]:
        print(f"      {t['week_id']}  {t['selected_activity_id']:<38} "
              f"{t['reason']:<26} 후보 {t['candidate_count']}")
    print()

    # ---------------------------------------- 4.5 Cell Regenerate (L8)
    target = weeks[min(2, len(weeks) - 1)]["week_id"]
    regeneratable = [
        r["section_key"] for r in m["rows"]
        if r["section_key"] in ("focus", "outdoor_play")
    ]
    for section_key in regeneratable:
        label = "중심 경험" if section_key == "focus" else "바깥놀이"
        print(f"[4.{section_key}] POST /api/monthly/regenerate  {target} / {label}")
        before = {
            (r["section_key"], c["week_id"]): c["value"]
            for r in m["rows"] for c in r["cells"]
        }
        status, d = call(
            base,
            "/api/monthly/regenerate",
            {"section_key": section_key, "week_id": target},
        )
        if status != 200:
            print(f"    HTTP {status}")
            show_error(d)
            failures += 1
            continue
        m = d["monthly"]
        after = {
            (r["section_key"], c["week_id"]): c["value"]
            for r in m["rows"] for c in r["cells"]
        }
        changed = sorted(k for k in before if before[k] != after[k])
        cell = d.get("last_cell_regeneration")
        print(f"    HTTP 200")
        print(f"    이전  {before[(section_key, target)]}")
        print(f"    이후  {after[(section_key, target)]}")
        if cell:
            print(f"    origin={cell.get('activity_origin')} "
                  f"LLM {cell['provider_call_count']}회 "
                  f"repair {cell['validation_repair_count']}")
        print(f"    바뀐 Cell : {changed}")
        if changed != [(section_key, target)]:
            print("    !! Target 외 Cell이 변했습니다")
            failures += 1
    print()

    # ------------------------------------------------------ 4.9 Teacher Edit
    edit_section = "focus" if "focus" in regeneratable else "outdoor_play"
    print(f"[4.edit] POST /api/monthly/edit  {target} / {edit_section}")
    status, d = call(
        base,
        "/api/monthly/edit",
        {
            "section_key": edit_section,
            "week_id": target,
            "new_value": "교사가 직접 고친 값",
        },
    )
    if status != 200:
        print(f"    HTTP {status}")
        show_error(d)
        failures += 1
    else:
        m = d["monthly"]
        row = next(r for r in m["rows"] if r["section_key"] == edit_section)
        cell = next(c for c in row["cells"] if c["week_id"] == target)
        print(f"    HTTP 200  값={cell['value']}")
        print(f"    audit : {' → '.join(a['event_type'] for a in cell['audit'])}")
        if cell["value"] != "교사가 직접 고친 값":
            print("    !! 수정이 반영되지 않았습니다")
            failures += 1
    print()

    # --------------------------------------------------- 5. Monthly Confirm
    print("[5] POST /api/monthly/confirm  (실제 ConfirmMonthlyPlan)")
    status, d = call(base, "/api/monthly/confirm", {})
    if status != 200:
        print(f"    HTTP {status}")
        show_error(d)
        return 1
    m = d["monthly"]
    print(f"    HTTP 200  status={m['status']}")
    print(f"    audit : {' → '.join(a['event_type'] for a in m['audit'])}")
    for c in m["constraints"]:
        print(f"    {c['kind']} = {c['verification']}  (확정해도 그대로)")
    outdoor = next(r for r in m["rows"] if r["section_key"] == "outdoor_play")
    print(f"    바깥놀이 상태 유지 : "
          f"{sorted({c['cell_state'] for c in outdoor['cells']})}")
    print()

    # ------------------------------------- 6. CONFIRMED read-only 재확인
    print("[6] CONFIRMED 이후 수정·재생성 시도 (모두 차단되어야 한다)")
    attempts = [
        ("regenerate", "outdoor_play"),
        ("regenerate", "focus"),
        ("edit", "focus"),
    ]
    for action, section_key in attempts:
        if section_key == "focus" and "focus" not in regeneratable:
            continue
        body = {"section_key": section_key, "week_id": target}
        if action == "edit":
            body["new_value"] = "확정 후 수정"
        status, d = call(base, f"/api/monthly/{action}", body)
        if status == 200:
            print(f"    !! {action}/{section_key} 차단되지 않았습니다")
            failures += 1
        else:
            print(f"    {action}/{section_key:<13} HTTP {status} "
                  f"{d.get('violated_rule') or d.get('kind')}")
    print()

    print("=" * 70)
    print(" 모든 단계 통과" if failures == 0 else f" {failures}건 실패")
    print("=" * 70)
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
