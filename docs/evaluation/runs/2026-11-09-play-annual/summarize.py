"""놀이 연간 실행 로그를 다시 센다 — 이 폴더만 읽고 LLM 을 부르지 않는다.

    python -X utf8 docs/evaluation/runs/2026-11-09-play-annual/summarize.py

조건 정의 · 숫자의 뜻은 같은 폴더 README.md. 지침 검사는 낱말로 어림한 하한선이다 — 품질 판정이 아니다.
"""

import itertools
import json
import math
import re
import statistics
from collections import Counter
from pathlib import Path

HERE = Path(__file__).parent
CONDS = {
    "c1": "c1-sequential",
    "c5": "c5-parallel-nuri",
    "c6": "c6-parallel-nuri-materials",
    "c7": "c7-parallel-nuri-nolife",
}
DOMAINS = ["신체운동·건강", "의사소통", "사회관계", "예술경험", "자연탐구"]
NEAR = 0.6  # 글자 두 개 묶음 Jaccard. 이 이상이면 「비슷한 이름」
# 2019 개정 누리과정 고시문 Ⅱ-2 교수·학습 가~사 — 지원 문장에서 낱말로 어림
GUIDE = {
    "가 흥미 · 관심에 따라 자유롭게 참여": r"(의견|제안|생각을|선택|원하는|스스로|자유롭게|궁금|관심)",
    "다 다양한 놀이 환경 구성": r"(공간|자리|영역|환경|바깥|실외|마당|놀이터|배치|마련)",
    "라 능동적 상호작용": r"(친구|함께|서로|나누|이야기 나|소개)",
    "사 개별 특성에 맞게": r"(개별|각자|저마다|자신의 속도|어려워하|도움이 필요|원하는 만큼|자기만의|나만의)",
}
DIRECTIVE = r"(가르칩니다|가르쳐|알려 줍니다|알려줍니다|설명합니다|지도합니다|시킵니다|따라 하게|외우|정답)"
JEV_QUESTIONS = [
    "B1",
    "B2",
    "B3",
    "B5",
    "B6",
    "B7",
    "B8",
]  # B4 는 질문을 고쳐 다시 쟀다 — 여기선 뺀다


def norm(text):
    return re.sub(r"[\s\W_]+", "", text or "")


def sim(a, b):
    ga, gb = (
        {t[i : i + 2] for i in range(len(t) - 1)} or {t} for t in (norm(a), norm(b))
    )
    return len(ga & gb) / len(ga | gb) if ga | gb else 1.0


def same_or_near(a, b, line=NEAR):
    return norm(a) == norm(b) or sim(a, b) >= line


def plans(cond):
    for p in sorted((HERE / CONDS[cond]).glob("annual_play_run*.json")):
        plan = json.loads(p.read_text("utf-8"))
        if not plan.get("error"):
            yield plan


def seconds(cond):
    if cond == "c1":
        return json.loads((HERE / CONDS[cond] / "seconds.json").read_text("utf-8"))
    return [
        json.loads(p.read_text("utf-8"))["seconds"]
        for p in sorted((HERE / CONDS[cond]).glob("annual_play_run*.json"))
    ]


def names(plan):
    return [
        [c["play_name"]["value"] for c in period["candidates"]]
        for period in plan["periods"]
    ]


def diversity(runs):
    """다른 이름 수 · 한 계획 안 구간끼리 겹침 · 다시 만들었을 때 같은 구간에 또 나온 이름(후보 40개당)."""
    every = [norm(n) for r in runs for period in r for n in period]
    within = sum(
        same_or_near(a, b)
        for r in runs
        for i, j in itertools.combinations(range(len(r)), 2)
        for a, b in itertools.product(r[i], r[j])
    )
    same = near = total = 0
    for a, b in itertools.combinations(runs, 2):
        for k in range(min(len(a), len(b))):
            for x in a[k]:
                total += 1
                if any(norm(x) == norm(y) for y in b[k]):
                    same += 1
                elif any(sim(x, y) >= NEAR for y in b[k]):
                    near += 1
    return {
        "names": len(every),
        "distinct": len(set(every)),
        "within_plan_overlap": within,
        "regen_same_per40": round(same / total * 40, 2),
        "regen_near_per40": round(near / total * 40, 2),
    }


def domains(candidate):
    found = []
    for line in candidate["learning"]["value"].split("\n"):
        flat = line.replace(" ", "")
        found += [d for d in DOMAINS if flat.startswith((d, d.replace("·", "")))]
    return found


def area(runs):
    """계획마다 5영역을 다 덮었나 · 고르게(정규화 엔트로피, 1 = 완전히 고름) · 가장 큰 영역 비율."""
    rows = []
    for plan in runs:
        count = Counter(
            d for p in plan["periods"] for c in p["candidates"] for d in domains(c)
        )
        shares = [v / sum(count.values()) for v in count.values()]
        rows.append(
            (
                len(count) == 5,
                -sum(s * math.log(s) for s in shares) / math.log(5),
                max(shares),
            )
        )
    return {
        "all_5_areas": f"{sum(r[0] for r in rows)}/{len(rows)}",
        "evenness": round(statistics.mean(r[1] for r in rows), 2),
        "top_area_share": round(statistics.mean(r[2] for r in rows), 2),
    }


def guide(runs):
    cands = [c for plan in runs for p in plan["periods"] for c in p["candidates"]]
    support = [c["support_direction"]["value"] for c in cands]
    out = {
        k: sum(bool(re.search(p, s)) for s in support) / len(cands)
        for k, p in GUIDE.items()
    }
    out["마 두 영역 이상 통합"] = sum(len(set(domains(c))) >= 2 for c in cands) / len(
        cands
    )
    out["지시 · 훈화형 지원 문장 (낮을수록 좋음)"] = sum(
        bool(re.search(DIRECTIVE, s)) for s in support
    ) / len(cands)
    return {k: f"{v:.0%}" for k, v in out.items()}


def overlap_fix(cond):
    if cond == "c1":
        return "순차라 해당 없음"
    rs = [
        json.loads(p.read_text("utf-8"))
        for p in sorted((HERE / CONDS[cond]).glob("annual_play_run*.json"))
    ]
    count = lambda v: len(v) if isinstance(v, list) else int(v or 0)
    return {
        "before": sum(count(r["conflicts_before"]) for r in rs),
        "after": sum(count(r["conflicts_after"]) for r in rs),
        "replace_calls": sum(len(r.get("rounds") or []) for r in rs),
    }


def jev():
    """질문마다 ① 400개의 하위 5%(나쁜 쪽에서 20번째) 점수를 선으로 — 그 선보다 낮은 후보 수.

    ①은 정의상 약 20개다. 20보다 많으면 「①보다 못함」(하민 결정 2026-11-09).
    """
    scores = {
        c: [
            json.loads(x)["p"]
            for x in (HERE / "jev" / f"{c}.jsonl").read_text("utf-8").splitlines()
        ]
        for c in CONDS
    }
    lines = {}
    for q in JEV_QUESTIONS:
        base = sorted(s[q] for s in scores["c1"])
        lines[q] = base[len(base) // 20]
    return {
        c: {q: sum(s[q] < lines[q] for s in scores[c]) for q in JEV_QUESTIONS}
        for c in CONDS
    }


def human():
    rows = json.loads((HERE / "human60.json").read_text("utf-8"))
    tally = Counter((r["cond"], r["mark"]) for r in rows)
    return {
        c: f"○ {tally[c, 'good']} · △ {tally[c, 'mid']} · ✗ {tally[c, 'bad']}"
        for c in ("c1", "c5", "c6")
    }


def pair_checker():
    """같은 놀이(same) 짝을 몇 개 잡고, 다른 놀이(diff) 짝을 몇 개 잘못 잡나."""
    pairs = json.loads((HERE / "dup-pairs.json").read_text("utf-8"))["pairs"]
    out = {}
    for line in (NEAR, 0.45, 0.3):
        hit = [(p["label"], same_or_near(p["a"], p["b"], line)) for p in pairs]
        same = [h for label, h in hit if label == "same"]
        diff = [h for label, h in hit if label == "diff"]
        out[f"{line:.2f}"] = (
            f"same {sum(same)}/{len(same)} 잡음 · diff {sum(diff)}/{len(diff)} 잘못 잡음"
        )
    return out


def main():
    report = {}
    for cond in CONDS:
        runs = list(plans(cond))
        s = seconds(cond)
        report[cond] = {
            "seconds": {
                "mean": round(statistics.mean(s), 1),
                "median": round(statistics.median(s), 1),
            },
            "diversity": diversity([names(p) for p in runs]),
            "overlap_fix": overlap_fix(cond),
            "area": area(runs),
            "guide": guide(runs),
        }
    report["jev_below_c1_min"] = jev()
    report["human60"] = human()
    report["pair_checker"] = pair_checker()
    print(json.dumps(report, ensure_ascii=False, indent=1))
    return report


if __name__ == "__main__":
    main()
