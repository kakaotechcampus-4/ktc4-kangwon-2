"""§8. 전 Corpus에서 동일 Root Cause 결함 탐색.

Cell 인식 추출기로 복원한 Activity가 **v0.2.0의 기존 항목 2개 이상으로 정확히
분해되면** 그것은 분할 결함이 확정된 것이다. 문자열 포함이 아니라 **완전 분해**를
요구하므로 세로 나열 오탐이 원리적으로 발생하지 않는다.

    복원: '장화 신고 물웅덩이 건너기'
    분해: '장화 신고 물웅덩이' + '건너기'   ← 둘 다 v0.2.0에 존재 → 확정

    python analysis/tools/scan_extraction_defects.py
"""

from __future__ import annotations

import io
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "analysis" / "tools"))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from cell_extract import extract_cells  # noqa: E402

CAT = json.loads(
    (ROOT / "data" / "activities" / "activity_reference_v0_2.json").read_text("utf-8")
)
ORIGINS = {o["origin_id"]: o for o in CAT.get("origins", [])}
BY_LABEL = {a["label"]: a for a in CAT["activities"]}

OUTDOOR_ROW = re.compile(r"^(바깥\s*놀이|실외\s*놀이|야외\s*놀이|바깥)")
STRIP_PREFIX = re.compile(r"^[-♥•·◆▶\s]*(\[[^\]]{1,12}\])?\s*")
INDOOR_MARK = re.compile(r"\[(실내\s*대체|대체)[^\]]*\]")


def norm(s: str) -> str:
    return re.sub(r"[\s.,·…~!?\"'()\[\]♥•◆▶\-]+", "", s)


NORM_LABELS = {norm(lab): lab for lab in BY_LABEL}


def decompose(text: str) -> list[str] | None:
    """문자열을 기존 Catalog label들로 **완전 분해**한다. 실패하면 None."""
    n = norm(text)
    if not n or n in NORM_LABELS:
        return None  # 통째로 존재하면 결함이 아니다

    def walk(rest: str, acc: list[str]) -> list[str] | None:
        if not rest:
            return acc if len(acc) >= 2 else None
        for k in sorted(NORM_LABELS, key=len, reverse=True):
            if len(k) < 2:
                continue
            if rest.startswith(k):
                got = walk(rest[len(k):], acc + [NORM_LABELS[k]])
                if got:
                    return got
        return None

    return walk(n, [])


def main() -> int:
    import pymupdf

    monthly = sorted((ROOT / "references" / "samples" / "monthly").glob("*.pdf"))
    print("=" * 78)
    print(f" 전 Corpus 분할 결함 탐색 — Monthly {len(monthly)}개")
    print("=" * 78)

    confirmed: list[dict] = []
    scanned_pdfs = 0
    for path in monthly:
        try:
            doc = pymupdf.open(str(path))
        except Exception:
            continue
        found_any = False
        for pno in range(doc.page_count):
            cells = extract_cells(doc[pno])
            if not cells:
                continue
            found_any = True
            # 행 label이 바깥놀이인 row를 찾는다
            rows: dict[tuple[float, float], dict[int, list[str]]] = {}
            for (top, bot, col), items in cells.items():
                rows.setdefault((top, bot), {})[col] = items
            for (top, bot), cols in rows.items():
                first = cols.get(min(cols), [])
                if not first or not OUTDOOR_ROW.match(
                    STRIP_PREFIX.sub("", first[0]).strip()
                ):
                    continue
                for col, items in cols.items():
                    if col == min(cols):
                        continue
                    for raw in items:
                        text = INDOOR_MARK.split(raw)[0]
                        text = STRIP_PREFIX.sub("", text).strip()
                        if len(norm(text)) < 4:
                            continue
                        parts = decompose(text)
                        if parts:
                            confirmed.append({
                                "source": path.relative_to(ROOT).as_posix(),
                                "page": pno + 1,
                                "row": [round(top, 1), round(bot, 1)],
                                "col": col,
                                "restored": text,
                                "existing_parts": parts,
                            })
        if found_any:
            scanned_pdfs += 1
        doc.close()

    print(f"  표 선이 있어 셀 복원이 가능한 PDF : {scanned_pdfs}/{len(monthly)}")
    print(f"  SOURCE_CONFIRMED_DEFECT           : {len(confirmed)}건")
    print()
    seen = set()
    uniq = []
    for c in confirmed:
        key = (c["restored"], tuple(c["existing_parts"]))
        if key in seen:
            continue
        seen.add(key)
        uniq.append(c)
    print(f"  고유 결함 : {len(uniq)}건")
    for c in uniq:
        print(f"\n   복원 : {c['restored']}")
        print(f"   분해 : {' + '.join(repr(p) for p in c['existing_parts'])}")
        print(f"   출처 : {c['source']} p{c['page']} row{c['row']} col{c['col']}")

    out = ROOT / "analysis" / "tmp" / "extraction_defects.json"
    out.write_text(json.dumps(uniq, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n  저장: {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
