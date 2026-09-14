"""Evidence Store 빌드 + Outdoor Loss 감사 (L1).

    PYTHONPATH="<pdftools 경로>;src" python -m ssuksak.dev.build_evidence_store

`pymupdf`가 필요하다. Evidence Store **빌드 전용** 의존성이며 Planning Core
런타임에는 필요 없다(`adapters/pymupdf_source_reader.py` 참조).

Outdoor Loss 정의
-----------------
    분모  Source에 바깥놀이 행이 있고 그 행의 내용 칸에 글자가 있는 경우
    분자  그 행에서 usable body(= extraction_quality가 INVALID가 아닌 record)를
          하나도 복원하지 못한 경우

**loss를 0으로 만들려고 억지로 결합하지 않는다.** 잘못된 결합(false merge)과
실내대체 누출(leakage)을 따로 센다.
"""

from __future__ import annotations

import argparse
import collections
import io
import json
import pathlib
import sys
from datetime import datetime, timedelta, timezone

from ..adapters.pymupdf_source_reader import PyMuPdfSourceReader
from ..ingestion.classifiers import row_label_setting
from ..ingestion.evidence_builder import outdoor_rows_of
from ..ingestion.models import ExtractionQuality, Setting, SourceSection
from ..ingestion.pipeline import (
    INGESTION_VERSION,
    SourceFile,
    content_sha256,
    ingest_corpus,
    sha256_of,
    store_payload,
    summarize,
)

ROOT = pathlib.Path(__file__).resolve().parents[3]
SAMPLES = ROOT / "references" / "samples"
DEFAULT_OUT = ROOT / "data" / "evidence" / "institution_evidence_v0_1_0.json"
KST = timezone(timedelta(hours=9))

import re

_ALT_MARKER = re.compile(r"대\s*체")
"""outdoor record 본문에 이것이 남아 있으면 실내대체 누출 의심이다."""


def discover(reader) -> list[SourceFile]:
    """Corpus 파일 목록 + SHA-256 + 텍스트 레이어 유무."""
    out: list[SourceFile] = []
    for p in sorted(SAMPLES.rglob("*.pdf")):
        rel = str(p.relative_to(ROOT)).replace("\\", "/")
        readable = False
        try:
            doc = reader.open(str(p))
            try:
                readable = any(
                    doc.page_text(i + 1).strip() for i in range(doc.page_count)
                )
            finally:
                doc.close()
        except Exception:  # noqa: BLE001
            readable = False
        out.append(SourceFile(path=rel, sha256=sha256_of(p), readable=readable))
    return out


def outdoor_loss_audit(sources: list[SourceFile], reader, records) -> dict:
    """바깥놀이 행 단위 복원률."""
    by_page: dict[tuple[str, int], list] = collections.defaultdict(list)
    for r in records:
        by_page[(r.source_sha256, r.page)].append(r)

    rows_total = 0
    rows_recovered = 0
    lost: list[dict] = []
    leakage = 0
    false_outdoor = 0

    for src in sources:
        if not src.readable:
            continue
        try:
            doc = reader.open(str(ROOT / src.path))
        except Exception:  # noqa: BLE001
            continue
        try:
            for page in range(1, doc.page_count + 1):
                cells = doc.page_cells(page)
                if not cells.has_cells:
                    continue
                page_records = by_page.get((src.sha256, page), [])
                for row_top, row_label, bodies in outdoor_rows_of(cells):
                    if not any(b.strip() for b in bodies):
                        continue  # 내용 칸 자체가 빈 행은 분모가 아니다
                    rows_total += 1
                    same_row = [
                        r for r in page_records
                        if r.source_cell is not None
                        and abs(r.source_cell.row_top - row_top) < 0.5
                    ]
                    usable = [
                        r for r in same_row
                        if r.extraction_quality is not ExtractionQuality.INVALID
                    ]
                    if usable:
                        rows_recovered += 1
                    else:
                        lost.append({
                            "source": src.path, "page": page,
                            "row_label": row_label, "bodies": bodies[:4],
                        })
                    # 누출 = outdoor 후보로 쓰이는데 본문에 대체 표시가 남아 있는 것
                    leakage += sum(
                        1 for r in same_row
                        if r.outdoor_activity_eligible
                        and _ALT_MARKER.search(r.text or "")
                    )
        finally:
            doc.close()

    # outdoor로 분류됐지만 행 label이 바깥 계열이 아닌 record (false outdoor)
    for r in records:
        if r.source_section is SourceSection.OUTDOOR_PLAY and (
            r.setting is Setting.OUTDOOR
        ):
            if row_label_setting(r.source_label) is Setting.INDOOR:
                false_outdoor += 1

    return {
        "outdoor_rows_observed": rows_total,
        "outdoor_rows_recovered": rows_recovered,
        "outdoor_rows_lost": rows_total - rows_recovered,
        "outdoor_loss_rate": (
            (rows_total - rows_recovered) / rows_total if rows_total else 0.0
        ),
        "indoor_alternative_leakage": leakage,
        "false_outdoor_classification": false_outdoor,
        "lost_samples": lost[:20],
    }


def main(argv: list[str]) -> int:
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout = io.TextIOWrapper(
            sys.stdout.buffer, encoding="utf-8", errors="replace"
        )
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--audit-out", default=str(ROOT / "analysis" / "tmp"
                                               / "l1_ingestion_audit.json"))
    ap.add_argument("--no-write", action="store_true")
    args = ap.parse_args(argv)

    reader = PyMuPdfSourceReader()
    print("Corpus 탐색 중…", flush=True)
    sources = discover(reader)
    print(f"  파일 {len(sources)}개", flush=True)

    print("Ingestion 실행 중…", flush=True)
    result = ingest_corpus(sources, reader)
    summary = summarize(result)

    print("Outdoor Loss 감사 중…", flush=True)
    audit = outdoor_loss_audit(sources, reader, result.records)

    payload = store_payload(result)
    sha = content_sha256(payload)

    line = "=" * 92
    print("\n" + line)
    print(f" Evidence Store  {INGESTION_VERSION}")
    print(line)
    for k, v in summary.items():
        print(f"  {k:<32}{v}")
    print("\n  Outdoor Loss Audit")
    for k, v in audit.items():
        if k == "lost_samples":
            continue
        print(f"    {k:<34}{v if not isinstance(v, float) else f'{v:.2%}'}")
    if audit["lost_samples"]:
        print("\n    손실 사례")
        for s in audit["lost_samples"][:10]:
            print(f"      {pathlib.PurePath(s['source']).name[:52]} p{s['page']} "
                  f"[{s['row_label'][:16]}] {s['bodies'][:2]}")
    print(f"\n  content_sha256 : {sha}")

    if not args.no_write:
        out = pathlib.Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        artifact = dict(payload)
        artifact["build"] = {
            "generated_at": datetime.now(KST).replace(microsecond=0).isoformat(),
            "content_sha256": sha,
        }
        # 12k record 규모라 사람이 직접 편집하는 파일이 아니다. 들여쓰기를 넣으면
        # 파일이 두 배가 된다. 기계가 읽는 Artifact이므로 compact로 쓰되 key를
        # 정렬해 같은 content가 같은 바이트가 되게 한다.
        out.write_text(
            json.dumps(artifact, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":")) + "\n",
            encoding="utf-8", newline="",
        )
        print(f"  저장 : {out.relative_to(ROOT)}  ({out.stat().st_size:,} bytes)")

        ap_out = pathlib.Path(args.audit_out)
        ap_out.parent.mkdir(parents=True, exist_ok=True)
        ap_out.write_text(
            json.dumps({"summary": summary, "outdoor_audit": audit,
                        "files_without_cells": result.files_without_cells,
                        "files_failed": result.files_failed},
                       ensure_ascii=False, indent=1),
            encoding="utf-8",
        )
        print(f"  감사 : {ap_out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
