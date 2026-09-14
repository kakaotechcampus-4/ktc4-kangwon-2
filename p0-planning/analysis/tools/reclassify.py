"""본문 기준 재분류 (분류기 v2).

v1이 표제어를 `월간보육계획안` 계열로만 봐서 대량 UNKNOWN이 났다. 실제 Corpus는
`5세 5월 교육계획안`, `햇살반 놀이계획안 (3~5세)`처럼 쓴다. 연령도 `만` 없이
`3~5세` / `5세`로 적는 문서가 많다.

    python analysis/tools/reclassify.py

`analysis/tmp/inventory.json`을 읽어 `analysis/tmp/inventory2.json`을 쓴다.
추정하지 않는다 — 관찰된 표기만 기록하고, 못 읽으면 UNKNOWN으로 둔다.
"""

from __future__ import annotations

import io
import json
import pathlib
import re
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = pathlib.Path(__file__).resolve().parents[2]
TMP = ROOT / "analysis" / "tmp"
TEXT = TMP / "corpus_text"
INV = json.loads((TMP / "inventory.json").read_text("utf-8"))

PLAN_WORD = r"(?:보육|교육|놀이|운영)?\s*계획\s*(?:안|서)?"

# 문서 범위(scope) marker — 본문 상단 우선
RE_YEARLY = re.compile(rf"연간\s*{PLAN_WORD}")
RE_MONTHLY_TITLE = re.compile(
    rf"(\d{{1,2}})\s*월\s*[^\n]{{0,24}}?{PLAN_WORD}"
    rf"|(\d{{1,2}})\s*월\s*[^\n]{{0,16}}?놀이\s*안내"  # 서진: 'N월 놀이 안내'
)
RE_MONTHLY_WORD = re.compile(
    rf"(?:월간|원간|월별)\s*{PLAN_WORD}|^\s*월간\s*$", re.M
)
RE_WEEKLY = re.compile(rf"주간\s*{PLAN_WORD}|주\s*보육\s*계획")
RE_SAFETY = re.compile(r"안전\s*교육\s*(?:연간)?\s*계획")

# 연령: '만' 유무 모두 허용. 0~5세만 인정한다.
RE_AGE_RANGE = re.compile(r"(?:만\s*)?([0-5])\s*[~\-–]\s*([0-5])\s*세")
RE_AGE_DOT = re.compile(r"만?\s*([0-5])\s*[.·]\s*([0-5])\s*세")
RE_AGE_PLUS = re.compile(r"(?:만\s*)?([0-5])\s*\+\s*([0-5])\s*세")
RE_AGE_LIST = re.compile(r"만\s*([0-5])\s*,\s*(?:만\s*)?([0-5])\s*(?:,\s*(?:만\s*)?([0-5])\s*)?세")
RE_AGE_SINGLE = re.compile(r"(?:만\s*)?([0-5])\s*세")
RE_MIXED = re.compile(r"혼합\s*연?령?\s*반?")
RE_LEVEL = re.compile(r"([12345])\s*수준")

APPENDIX = (
    "동요", "동시", "속담", "가정통신문", "안내문", "부록", "식단표",
    "귀가동의", "이달의 노래", "예쁜 말", "생활주간",
)


def head_lines(text: str, n: int = 12) -> str:
    return "\n".join([l.strip() for l in text.splitlines() if l.strip()][:n])


def squeeze(s: str) -> str:
    """공백을 모두 제거한 사본. `주 간 보 육 계 획 안`처럼 자간이 벌어진
    표제와 `연간 , 기본 , 생활안전 계획안`처럼 중간에 다른 말이 끼는 표제를
    같은 규칙으로 잡기 위해서다. 표기를 바꾸지 않고 탐지에만 쓴다."""
    return re.sub(r"[\s,·.]+", "", s)


SQ_YEARLY = re.compile(r"연간.{0,12}?계획")
SQ_MONTHLY = re.compile(r"(\d{1,2})월.{0,16}?계획|(?:월간|원간|월별).{0,12}?계획")
SQ_WEEKLY = re.compile(r"주간.{0,12}?계획")
SQ_SAFETY = re.compile(r"안전교육.{0,12}?계획")


def classify(text: str) -> tuple[str, dict]:
    head = head_lines(text, 12)
    body = text[:9000]
    ev = {}

    if RE_WEEKLY.search(head):
        ev["weekly"] = RE_WEEKLY.search(head).group(0)
        return "WEEKLY_PLAN", ev
    if RE_YEARLY.search(head):
        ev["yearly"] = RE_YEARLY.search(head).group(0)
        return "YEARLY_PLAN", ev
    m = RE_MONTHLY_TITLE.search(head) or RE_MONTHLY_WORD.search(head)
    if m:
        ev["monthly"] = m.group(0).strip()
        return "MONTHLY_PLAN", ev
    if RE_SAFETY.search(head):
        ev["safety"] = RE_SAFETY.search(head).group(0)
        return "SAFETY_PLAN", ev

    # 자간이 벌어졌거나 중간에 다른 말이 끼는 표제를 공백 제거 사본으로 재시도
    sq_head = squeeze(head)
    for pat, kind, tag in (
        (SQ_WEEKLY, "WEEKLY_PLAN", "sq_weekly"),
        (SQ_YEARLY, "YEARLY_PLAN", "sq_yearly"),
        (SQ_MONTHLY, "MONTHLY_PLAN", "sq_monthly"),
        (SQ_SAFETY, "SAFETY_PLAN", "sq_safety"),
    ):
        mm = pat.search(sq_head)
        if mm:
            ev[tag] = mm.group(0)
            return kind, ev

    # 상단에서 못 찾으면 본문 앞부분으로 확장 (그래도 못 찾으면 UNKNOWN)
    for name, pat, kind in (
        ("weekly", RE_WEEKLY, "WEEKLY_PLAN"),
        ("yearly", RE_YEARLY, "YEARLY_PLAN"),
        ("monthly_word", RE_MONTHLY_WORD, "MONTHLY_PLAN"),
        ("monthly_title", RE_MONTHLY_TITLE, "MONTHLY_PLAN"),
        ("safety", RE_SAFETY, "SAFETY_PLAN"),
    ):
        mm = pat.search(body)
        if mm:
            ev[name] = mm.group(0).strip()
            return kind, ev
    return "UNKNOWN", ev


def ages_of(text: str) -> dict:
    found: set[int] = set()
    forms: list[str] = []
    explicit_range = False
    for pat, tag in (
        (RE_AGE_DOT, "dot"),
        (RE_AGE_RANGE, "range"),
        (RE_AGE_PLUS, "plus"),
    ):
        for m in pat.finditer(text):
            lo, hi = int(m.group(1)), int(m.group(2))
            found.update(range(min(lo, hi), max(lo, hi) + 1))
            forms.append(f"{tag}:{m.group(0).strip()}")
            explicit_range = True
    for m in RE_AGE_LIST.finditer(text):
        for g in m.groups():
            if g:
                found.add(int(g))
        forms.append(f"list:{m.group(0).strip()}")
    for m in RE_AGE_SINGLE.finditer(text):
        found.add(int(m.group(1)))
        forms.append(f"single:{m.group(0).strip()}")
    return {
        "ages": sorted(found),
        "forms": forms[:14],
        "explicit_mixed_word": bool(RE_MIXED.search(text)),
        "explicit_age_range_token": explicit_range,
        "level_markers": sorted({m.group(1) for m in RE_LEVEL.finditer(text)}),
    }


def month_of(text: str) -> dict:
    head = head_lines(text, 12)
    titles = []
    for m in RE_MONTHLY_TITLE.finditer(head):
        g = next((x for x in m.groups() if x), None)
        if g and 1 <= int(g) <= 12:
            titles.append(int(g))
    if not titles:
        sq = re.sub(r"[\s,·.]+", "", head)
        mm = re.search(r"(\d{1,2})월.{0,16}?계획|(\d{1,2})월.{0,16}?놀이안내", sq)
        if mm:
            g = next((x for x in mm.groups() if x), None)
            if g and 1 <= int(g) <= 12:
                titles.append(int(g))
    if not titles and RE_MONTHLY_WORD.search(head):
        # '월간' 표제 뒤 별도 줄에 '2026년 - 9월'이 오는 형태 (큰빛)
        mm = re.search(r"(\d{1,2})\s*월", head)
        if mm and 1 <= int(mm.group(1)) <= 12:
            titles.append(int(mm.group(1)))
    return {"title_months": titles, "first": titles[0] if titles else None}


def main() -> int:
    out = []
    for r in INV:
        p = TEXT / f"{r['sha12']}.layout.txt"
        text = p.read_text("utf-8") if p.exists() else ""
        raw = (TEXT / f"{r['sha12']}.raw.txt")
        rawt = raw.read_text("utf-8") if raw.exists() else ""
        use = text if len(text) >= len(rawt) else rawt

        doc_type, ev = classify(use)
        a = ages_of(use)
        mo = month_of(use)
        pages = []
        for pa in r["per_page_ages"]:
            pages.append(sorted(set(pa)))

        r2 = dict(r)
        r2["body2"] = {
            "doc_type": doc_type,
            "scope_evidence": ev,
            "ages": a["ages"],
            "age_forms": a["forms"],
            "explicit_mixed_word": a["explicit_mixed_word"],
            "explicit_age_range_token": a["explicit_age_range_token"],
            "level_markers": a["level_markers"],
            "month": mo,
            "appendix_markers": [k for k in APPENDIX if k in use],
            "head": head_lines(use, 3),
        }
        out.append(r2)

    (TMP / "inventory2.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    import collections

    c = collections.Counter(r["body2"]["doc_type"] for r in out)
    print("재분류 결과:", dict(c))
    unk = [r for r in out if r["body2"]["doc_type"] == "UNKNOWN" and r["readable"]]
    print(f"UNKNOWN & readable: {len(unk)}")
    for r in unk[:12]:
        print(f"  {r['dir']:<8} {r['name'][:58]}")
        print(f"    head: {r['body2']['head'][:120]!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
