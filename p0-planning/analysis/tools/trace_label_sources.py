"""§11/Q6. 문제 Activity Label의 원본 역추적 (분석 전용).

Activity Reference v0.2.0의 evidence origin을 실제 PDF 원문 줄로 되돌려
`REFERENCE_PROBLEM / PARSER_PROBLEM / DISPLAY_PROBLEM / CONTEXT_PROBLEM` 중
무엇인지 판정한다. 추측하지 않고 원문 줄을 그대로 인용한다.

    python analysis/tools/trace_label_sources.py
"""

from __future__ import annotations

import io
import json
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
PDFTOTEXT = r"C:\Program Files\Git\mingw64\bin\pdftotext.exe"

RAW = json.loads(
    (ROOT / "data" / "activities" / "activity_reference_v0_2.json").read_text("utf-8")
)
ORIGINS = {o["origin_id"]: o for o in RAW.get("origins", [])}
BY_LABEL = {a["label"]: a for a in RAW["activities"]}
ALL_LABELS = {a["label"] for a in RAW["activities"]}


def layout_of(path: str) -> list[str]:
    p = ROOT / path
    if not p.exists():
        return []
    res = subprocess.run(
        [PDFTOTEXT, "-layout", "-enc", "UTF-8", str(p), "-"],
        capture_output=True,
        timeout=120,
    )
    return res.stdout.decode("utf-8", errors="replace").splitlines()


def find_context(lines: list[str], needle: str, before=2, after=2):
    out = []
    for i, ln in enumerate(lines):
        if needle in ln:
            lo, hi = max(0, i - before), min(len(lines), i + after + 1)
            out.append((i, lines[lo:hi]))
    return out


TARGETS = ["건너기", "놀이를 해요.", "가을담기", "전통놀이", "장화 신고 물웅덩이"]


def verdict_for(label: str, contexts) -> str:
    """원문 줄을 보고 판정한다."""
    if not contexts:
        return "SOURCE_NOT_LOCATED"
    # 같은 줄에 라벨만 단독으로 있고 인접 줄이 이어지는 문장이면 파서 분할이다
    return "SEE_NOTES"


def main() -> int:
    print("=" * 78)
    print(" Q6. 문제 Label 원본 역추적")
    print("=" * 78)

    for label in TARGETS:
        act = BY_LABEL.get(label)
        print()
        print("-" * 78)
        if act is None:
            print(f" [{label}] — Catalog에 없음")
            continue
        print(f" [{label}]  id={act['activity_id']}  "
              f"months={act.get('applicable_months')} ages={act.get('supported_ages')}")
        for e in act.get("evidence", [])[:3]:
            origin = ORIGINS.get(e["origin_id"], {})
            path = origin.get("path") or origin.get("source_path") or ""
            print(f"   evidence: origin={e['エ'] if False else e['origin_id']}")
            print(f"     observed_label = {e.get('observed_label')!r}")
            print(f"     source = {path}")
            lines = layout_of(path)
            if not lines:
                print("     (원문 추출 실패)")
                continue
            needle = re.sub(r"^[-♥<>\s]+", "", str(e.get("observed_label") or label))[:12]
            ctx = find_context(lines, needle)
            if not ctx:
                ctx = find_context(lines, label[:10])
            for idx, block in ctx[:2]:
                print(f"     원문 line {idx}:")
                for b in block:
                    print(f"       | {b.rstrip()[:96]}")
    print()
    print("=" * 78)
    print(" 파서 분할 의심 쌍 자동 탐색")
    print("=" * 78)
    # 같은 origin에서 나온 두 라벨이 원문에서 연속 줄이면 분할 의심
    by_origin: dict[str, list[tuple[str, str]]] = {}
    for a in RAW["activities"]:
        for e in a.get("evidence", []):
            by_origin.setdefault(e["origin_id"], []).append(
                (a["label"], str(e.get("observed_label") or ""))
            )
    suspects = []
    for origin_id, pairs in by_origin.items():
        if len(pairs) < 2:
            continue
        origin = ORIGINS.get(origin_id, {})
        path = origin.get("path") or origin.get("source_path") or ""
        lines = layout_of(path)
        if not lines:
            continue
        pos = {}
        for lab, obs in pairs:
            needle = re.sub(r"^[-♥<>\s]+", "", obs or lab)[:10]
            for i, ln in enumerate(lines):
                if needle and needle in ln:
                    pos.setdefault(lab, []).append(i)
                    break
        labs = sorted(pos)
        for i in range(len(labs)):
            for j in range(len(labs)):
                if i == j:
                    continue
                a_l, b_l = labs[i], labs[j]
                if not pos.get(a_l) or not pos.get(b_l):
                    continue
                if pos[b_l][0] - pos[a_l][0] in (1, 2) and len(b_l) <= 6:
                    suspects.append((origin_id, a_l, b_l, pos[a_l][0], pos[b_l][0]))
    seen = set()
    for origin_id, a_l, b_l, pa, pb in suspects:
        key = (a_l, b_l)
        if key in seen:
            continue
        seen.add(key)
        print(f"   {origin_id}")
        print(f"     line {pa}: {a_l!r}")
        print(f"     line {pb}: {b_l!r}   ← 짧은 후속 줄. 한 셀의 wrap일 가능성")
    if not suspects:
        print("   (자동 탐색에서 추가 의심 쌍 없음)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
