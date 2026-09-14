"""신규 Source의 Activity 후보 · Theme · 연령 차별화 · Source 독립성 (분석 전용).

§8 §9 §10 §13을 계산한다. **Catalog에 반영하지 않는다.**

    python analysis/tools/new_reference_candidates.py
"""

from __future__ import annotations

import collections
import io
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
TMP = ROOT / "analysis" / "tmp"
TEXT = TMP / "corpus_text"
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

CATALOG = ROOT / "data" / "activities" / "activity_reference_v0_2_1.json"

OUTDOOR_HEAD = re.compile(r"(바\s*깥\s*놀?\s*이?|실\s*외\s*놀?\s*이?|바깥|실외)")
INDOOR_HEAD = re.compile(r"(실\s*내\s*놀?\s*이?|실내대체|대체활동|\[대체\])")
SPLIT = re.compile(r"[/·•⦁▸▶,]|\s{3,}")
BULLET = re.compile(r"^\s*[-–—*·•⦁▸▶♥※]+\s*")

TEMPLATE_FAMILY = {"마성어린이집", "우리어린이집", "키즈로스쿨어린이집", "혜솔어린이집"}
"""§5 재분석에서 확인된 Template Family. 독립 source 보정에 쓴다."""


def nrm(s: str) -> str:
    return re.sub(r"[\s.,·…~!?\"'()\[\]<>【】♥•◆▶⦁\-/]+", "", s or "")


def main() -> int:
    D = json.loads((TMP / "new_reference_impact.json").read_text("utf-8"))
    Y = json.loads((TMP / "new_reference_yield.json").read_text("utf-8"))
    cat = json.loads(CATALOG.read_text("utf-8"))
    known = {nrm(a["label"]) for a in cat["activities"]}
    known |= {nrm(x) for a in cat["activities"] for x in a.get("aliases", [])}
    ingested = {o["path"] for o in cat["origins"]}
    recs = {r["path"]: r for r in D["records"]}
    obs = Y["observations"]
    line = "=" * 96

    # ============================================ §8 Activity 후보
    print(line)
    print(" §8. 신규 Source의 바깥놀이 Activity 후보 관찰")
    print(line)
    print("  주의: 이 목록은 **관찰**이다. Catalog 반영 형태가 아니다.")
    print("        pdftotext layout 줄 기반이므로 v0.2.1을 만든 셀 기하 추출보다 거칠다.")

    found = collections.defaultdict(list)   # (month, age) -> [(label, inst, path)]
    for o in obs:
        if o["dir"] != "monthly" or o["cls"] == "EXISTING_SOURCE":
            continue
        if o["single_age"] is None:
            continue
        path = o["path"]
        pages = (TEXT / f"{recs[path]['sha12']}.layout.txt").read_text(
            "utf-8", errors="replace").split("\f")
        i = o["page"] - 1
        if i >= len(pages):
            continue
        month = o["fn_month"] or (o["page_months"][0] if o["page_months"] else None)
        if month is None:
            continue
        for ln in pages[i].splitlines():
            if not OUTDOOR_HEAD.search(ln) or INDOOR_HEAD.search(ln):
                continue
            body = OUTDOOR_HEAD.sub(" ", ln)
            for piece in SPLIT.split(body):
                lab = BULLET.sub("", piece).strip()
                if len(nrm(lab)) < 4 or len(lab) > 40:
                    continue
                if not re.search(r"[가-힣]", lab):
                    continue
                found[(month, o["single_age"])].append(
                    (lab, o["institution"], path))

    total = sum(len(v) for v in found.values())
    uniq = {nrm(l) for v in found.values() for l, _, _ in v}
    new_only = {n for n in uniq if n not in known}
    print(f"\n  관찰된 바깥놀이 후보 줄 : {total}")
    print(f"  정규화 고유 label       : {len(uniq)}")
    print(f"  v0.2.1에 없는 label     : {len(new_only)}  "
          f"({len(new_only)/max(1,len(uniq)):.0%})")

    print("\n  월 × 단일연령별 신규 후보 관찰 수 (v0.2.1 미보유 label 기준)")
    print(f"  {'월':<5}{'만3세':>10}{'만4세':>10}{'만5세':>10}")
    for m in range(1, 13):
        row = f"  {m:>2}월 "
        for age in (3, 4, 5):
            labs = {nrm(l) for l, _, _ in found.get((m, age), [])}
            row += f"{len(labs - known):>10}"
        print(row)

    print("\n  기존에 후보가 얇았던 Month/Age의 신규 관찰 예")
    for m, age in ((6, 4), (7, 4), (8, 4), (1, 4), (2, 4), (11, 4), (2, 5), (11, 5)):
        labs = [(l, i) for l, i, _ in found.get((m, age), []) if nrm(l) not in known]
        seen, out = set(), []
        for l, i in labs:
            if nrm(l) in seen:
                continue
            seen.add(nrm(l))
            out.append(f"{l}({i})")
        print(f"    {m:>2}월 만{age}세  신규 {len(out)}건: {out[:6]}")

    # ============================================ §9 Theme
    print("\n" + line)
    print(" §9. 문제 Theme별 신규 Source 관찰")
    print(line)
    THEMES = {
        "우리 동네": ("우리 동네", "우리동네", "동네"),
        "여름": ("여름",),
        "교통기관": ("교통기관", "교통", "탈것"),
        "성장한 우리": ("성장", "형님", "졸업", "소중했던 우리반"),
    }
    for name, keys in THEMES.items():
        hit_new = collections.Counter()
        sample = []
        for o in obs:
            if o["dir"] != "monthly":
                continue
            path = o["path"]
            pages = (TEXT / f"{recs[path]['sha12']}.layout.txt").read_text(
                "utf-8", errors="replace").split("\f")
            i = o["page"] - 1
            if i >= len(pages):
                continue
            txt = pages[i]
            if not any(k in txt for k in keys):
                continue
            hit_new[o["cls"]] += 1
            if o["cls"] != "EXISTING_SOURCE" and len(sample) < 6:
                theme_ln = next((ln.strip() for ln in txt.splitlines()
                                 if any(k in ln for k in keys)
                                 and re.search(r"주제", ln)), None)
                if theme_ln:
                    sample.append(f"{o['institution']}: {theme_ln[:70]}")
        print(f"\n  Theme `{name}`")
        print(f"    면 수: 기존 {hit_new.get('EXISTING_SOURCE',0)} / "
              f"신규 {sum(v for k,v in hit_new.items() if k!='EXISTING_SOURCE')}")
        for s in sample:
            print(f"      {s}")

    # ============================================ §10 연령 차별화
    print("\n" + line)
    print(" §10. 같은 기관 · 같은 월 · 연령별 면이 함께 있는 Source")
    print(line)
    by_doc = collections.defaultdict(list)
    for o in obs:
        if o["single_age"] is not None:
            by_doc[o["path"]].append(o)
    multi = {p: v for p, v in by_doc.items()
             if len({x["single_age"] for x in v}) >= 2}
    print(f"  한 문서 안에 서로 다른 단일연령 면이 2개 이상: {len(multi)}건")
    newmulti = {p: v for p, v in multi.items() if recs[p]["_cls"] != "EXISTING_SOURCE"}
    print(f"    그중 신규: {len(newmulti)}건  "
          f"기관 {sorted({recs[p]['institution'] for p in newmulti})}")
    print(f"    monthly 만: "
          f"{len([p for p in newmulti if recs[p]['dir']=='monthly'])}건")

    print("\n  예: 같은 월 문서의 연령별 바깥놀이 행 (원문 그대로)")
    shown = 0
    for p, v in sorted(newmulti.items()):
        if recs[p]["dir"] != "monthly" or shown >= 3:
            continue
        pages = (TEXT / f"{recs[p]['sha12']}.layout.txt").read_text(
            "utf-8", errors="replace").split("\f")
        rows = []
        for o in sorted(v, key=lambda x: x["single_age"]):
            i = o["page"] - 1
            if i >= len(pages):
                continue
            ods = [ln.strip() for ln in pages[i].splitlines()
                   if OUTDOOR_HEAD.search(ln) and not INDOOR_HEAD.search(ln)]
            rows.append((o["single_age"], ods[:2]))
        if len(rows) < 2 or not any(r[1] for r in rows):
            continue
        print(f"\n    {pathlib.Path(p).name}")
        for age, ods in rows:
            for ln in ods:
                print(f"      만{age}세  {ln[:100]}")
        shown += 1

    # ============================================ §13 Source 독립성
    print("\n" + line)
    print(" §13. Source Independence")
    print(line)
    new = [r for r in D["records"] if r["_cls"] != "EXISTING_SOURCE"]
    sha = collections.Counter(r["sha12"] for r in new)
    print(f"  신규 {len(new)}건 / 고유 SHA {len(sha)}  → exact duplicate "
          f"{len(new)-len(sha)}건")
    inst = collections.Counter(r["institution"] for r in new)
    print(f"  기관 {len(inst)}곳. 파일이 많은 기관 상위:")
    for i, n in inst.most_common(8):
        print(f"    {n:>3}  {i}")
    fam = [r for r in new if r["institution"] in TEMPLATE_FAMILY]
    print(f"  기존 Template Family 소속 신규 파일: {len(fam)}건")
    est = collections.Counter(r["establishment"] for r in new)
    print(f"  설립유형: {dict(est)}")

    # 연제구 계열 — 같은 지자체/브랜드 접두어
    pref = collections.Counter()
    for r in new:
        i = r["institution"] or ""
        m = re.match(r"(연제구|부산광역시청|근로복지공단|공립|창원시립)", i)
        if m:
            pref[m.group(1)] += 1
    print(f"  같은 접두어(지자체/운영주체) 계열: {dict(pref)}")
    print("  ※ 접두어가 같다고 곧바로 같은 Source로 보지 않는다. 개별 기관이다.")
    print("     다만 독립 source 수를 셀 때 보수적으로 함께 볼 근거는 된다.")

    print(f"\n  v0.2.1이 ingest한 origin 수: {len(ingested)}")
    print(f"  신규 174건 중 ingest된 것: "
          f"{len([r for r in new if r['path'] in ingested])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
