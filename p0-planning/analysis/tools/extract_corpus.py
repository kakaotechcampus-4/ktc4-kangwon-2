"""Full Corpus 텍스트 추출 + 결정론적 Inventory (분석 전용).

Production 파일을 읽지도 쓰지도 않는다. `references/samples/`만 읽고
`analysis/tmp/`에만 쓴다.

    python analysis/tools/extract_corpus.py

산출물:
    analysis/tmp/corpus_text/<sha12>.layout.txt   pdftotext -layout
    analysis/tmp/corpus_text/<sha12>.raw.txt      pdftotext -raw
    analysis/tmp/inventory.json                   파일별 메타 + 본문 기반 분류

**Filename보다 본문이 Truth다.** 파일명에서 뽑은 값과 본문에서 뽑은 값을 각각
따로 저장하고, 불일치를 그대로 남긴다. 추정으로 메우지 않는다.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
SAMPLES = ROOT / "references" / "samples"
OUT = ROOT / "analysis" / "tmp"
TEXT = OUT / "corpus_text"
PDFTOTEXT = r"C:\Program Files\Git\mingw64\bin\pdftotext.exe"

# ------------------------------------------------------------------ 파일명 파싱

FN_YEAR = re.compile(r"(20\d{2})")
FN_MONTH = re.compile(r"\((\d{1,2})월\)")
FN_AGE_RANGE = re.compile(r"만?\s*(\d)\s*[-~+]\s*(\d)\s*세")
FN_AGE_LIST = re.compile(r"만\s*(\d)\s*(?:,\s*(\d)\s*)?(?:,\s*(\d)\s*)?세")
FN_AGE_SINGLE = re.compile(r"만\s*(\d)\s*세")
FN_INST = re.compile(r"([가-힣A-Za-z0-9]+(?:어린이집|유치원))")
FN_ESTAB = re.compile(r"_(국공립|민간|가정|법인단체|직장|협동|사회복지법인|법인)_")

# ------------------------------------------------------------------ 본문 파싱

BODY_YEAR = re.compile(r"(20\d{2})\s*년?\s*도?")
BODY_MONTH_TITLE = re.compile(r"(\d{1,2})\s*월\s*(?:간)?\s*(?:보육|교육)?\s*계획")
BODY_AGE_DOT = re.compile(r"만\s*(\d)\s*[.·]\s*(\d)\s*세")
BODY_AGE_RANGE = re.compile(r"만\s*(\d)\s*[-~]\s*(\d)\s*세")
BODY_AGE_PLUS = re.compile(r"만\s*(\d)\s*\+\s*(\d)\s*세")
BODY_AGE_SINGLE = re.compile(r"만\s*(\d)\s*세")
BODY_MIXED = re.compile(r"혼합\s*(?:연령)?\s*반?|혼합연령")

DOC_MARKERS = {
    "YEARLY_PLAN": (r"연간\s*(?:보육|교육)?\s*계획", r"연간계획"),
    "MONTHLY_PLAN": (r"월간\s*(?:보육|교육)?\s*계획", r"원간\s*보육\s*계획", r"월간계획"),
    "WEEKLY_PLAN": (r"주간\s*(?:보육|교육)?\s*계획", r"주간계획"),
    "SAFETY_PLAN": (r"안전\s*교육\s*계획", r"안전교육\s*연간"),
}

APPENDIX_MARKERS = (
    "동요", "동시", "속담", "가정통신문", "안내문", "부록",
    "이달의 동요", "이달의 동시", "이달의 속담", "귀가동의", "식단표",
)


def sha256_of(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def run_pdftotext(path: pathlib.Path, mode: str) -> str:
    try:
        res = subprocess.run(
            [PDFTOTEXT, mode, "-enc", "UTF-8", str(path), "-"],
            capture_output=True,
            timeout=120,
        )
        return res.stdout.decode("utf-8", errors="replace")
    except Exception:
        return ""


def page_count(path: pathlib.Path) -> int | None:
    try:
        import pymupdf

        with pymupdf.open(str(path)) as doc:
            return doc.page_count
    except Exception:
        return None


def page_texts(path: pathlib.Path) -> list[str]:
    """페이지별 텍스트. Multi-page / Multi-age 판별에 쓴다."""
    try:
        import pymupdf

        with pymupdf.open(str(path)) as doc:
            return [p.get_text() for p in doc]
    except Exception:
        return []


# ------------------------------------------------------------------ 분류


def parse_filename(name: str) -> dict:
    stem = name.rsplit(".", 1)[0]
    years = [int(y) for y in FN_YEAR.findall(stem)]
    month = FN_MONTH.search(stem)
    ages: list[int] = []
    m = FN_AGE_RANGE.search(stem)
    if m:
        lo, hi = int(m.group(1)), int(m.group(2))
        ages = list(range(min(lo, hi), max(lo, hi) + 1))
    else:
        m = FN_AGE_LIST.search(stem)
        if m and (m.group(2) or m.group(3)):
            ages = [int(g) for g in m.groups() if g]
        else:
            m = FN_AGE_SINGLE.search(stem)
            if m:
                ages = [int(m.group(1))]
    inst = FN_INST.search(stem)
    estab = FN_ESTAB.search("_" + stem + "_")
    return {
        "stem": stem,
        "year": years[0] if years else None,
        "month": int(month.group(1)) if month else None,
        "ages": sorted(set(ages)),
        "institution": inst.group(1) if inst else None,
        "establishment": estab.group(1) if estab else None,
        "has_age_range_token": bool(FN_AGE_RANGE.search(stem)),
    }


def classify_doc_type(text: str, fn: dict) -> tuple[str, list[str]]:
    """본문 marker 우선. 없으면 UNKNOWN으로 두고 filename을 별도 보고한다."""
    head = text[:4000]
    hits: list[str] = []
    for kind, patterns in DOC_MARKERS.items():
        for pat in patterns:
            if re.search(pat, head):
                hits.append(kind)
                break
    if not hits:
        # 본문 전체에서 한 번 더
        for kind, patterns in DOC_MARKERS.items():
            for pat in patterns:
                if re.search(pat, text):
                    hits.append(kind)
                    break
    if not hits:
        return "UNKNOWN", []
    # 월간 marker가 있으면 월간이 우선 (월간 문서가 연간을 언급하는 경우가 있다)
    for kind in ("MONTHLY_PLAN", "WEEKLY_PLAN", "YEARLY_PLAN", "SAFETY_PLAN"):
        if kind in hits:
            return kind, hits
    return hits[0], hits


def body_ages(text: str) -> dict:
    """본문에서 관찰된 연령 표기. 추정하지 않는다."""
    found: set[int] = set()
    explicit_mixed = bool(BODY_MIXED.search(text))
    forms: list[str] = []
    for pat, name in (
        (BODY_AGE_DOT, "dot"),
        (BODY_AGE_RANGE, "range"),
        (BODY_AGE_PLUS, "plus"),
    ):
        for m in pat.finditer(text):
            lo, hi = int(m.group(1)), int(m.group(2))
            found.update(range(min(lo, hi), max(lo, hi) + 1))
            forms.append(f"{name}:{m.group(0).strip()}")
    for m in BODY_AGE_SINGLE.finditer(text):
        found.add(int(m.group(1)))
        forms.append(f"single:{m.group(0).strip()}")
    return {
        "ages": sorted(found),
        "explicit_mixed": explicit_mixed,
        "forms": forms[:12],
    }


def body_month(text: str, layout: str) -> dict:
    """제목 줄에서 월을 읽는다. 기간 줄의 시작 월을 쓰지 않는다."""
    lines = [ln.strip() for ln in layout.splitlines() if ln.strip()][:18]
    title_months: list[int] = []
    for ln in lines:
        if re.search(r"기간|\d{1,2}\s*/\s*\d{1,2}|~", ln) and not re.search(
            r"계획", ln
        ):
            continue
        for m in BODY_MONTH_TITLE.finditer(ln):
            v = int(m.group(1))
            if 1 <= v <= 12:
                title_months.append(v)
    all_months = [
        int(m.group(1))
        for m in BODY_MONTH_TITLE.finditer(text)
        if 1 <= int(m.group(1)) <= 12
    ]
    return {
        "title_months": title_months,
        "first_title_month": title_months[0] if title_months else None,
        "all_month_mentions": sorted(set(all_months)),
    }


def appendix_hits(text: str) -> list[str]:
    return [k for k in APPENDIX_MARKERS if k in text]


def main() -> int:
    TEXT.mkdir(parents=True, exist_ok=True)
    records = []
    files = sorted(
        p for p in SAMPLES.rglob("*") if p.is_file() and p.suffix.lower() == ".pdf"
    )
    print(f"대상 PDF {len(files)}개")

    for i, path in enumerate(files, 1):
        rel = path.relative_to(ROOT).as_posix()
        digest = sha256_of(path)
        short = digest[:12]

        layout = run_pdftotext(path, "-layout")
        raw = run_pdftotext(path, "-raw")
        (TEXT / f"{short}.layout.txt").write_text(layout, encoding="utf-8")
        (TEXT / f"{short}.raw.txt").write_text(raw, encoding="utf-8")

        text = layout if len(layout) >= len(raw) else raw
        readable = len(re.sub(r"\s", "", text)) >= 50

        fn = parse_filename(path.name)
        pages = page_texts(path)
        per_page_ages = [body_ages(p)["ages"] for p in pages] if pages else []

        doc_type, doc_hits = classify_doc_type(text, fn)
        ba = body_ages(text)
        bm = body_month(text, layout)

        records.append(
            {
                "path": rel,
                "dir": path.parent.name,
                "name": path.name,
                "sha256": digest,
                "sha12": short,
                "size": path.stat().st_size,
                "mtime_day": __import__("datetime").date.fromtimestamp(
                    path.stat().st_mtime
                ).isoformat(),
                "page_count": page_count(path),
                "readable": readable,
                "text_chars": len(re.sub(r"\s", "", text)),
                "filename": fn,
                "body": {
                    "doc_type": doc_type,
                    "doc_type_hits": doc_hits,
                    "ages": ba["ages"],
                    "explicit_mixed": ba["explicit_mixed"],
                    "age_forms": ba["forms"],
                    "month": bm,
                    "appendix_markers": appendix_hits(text),
                },
                "per_page_ages": per_page_ages,
            }
        )
        if i % 25 == 0:
            print(f"  {i}/{len(files)}")

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "inventory.json").write_text(
        json.dumps(records, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print(f"완료: analysis/tmp/inventory.json  ({len(records)}건)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
