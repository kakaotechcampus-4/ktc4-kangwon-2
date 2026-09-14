"""Activity Reference v0.2.1 Draft 생성 (Quality Patch 1).

v0.2.0을 계승하고 **Source로 확정된 correction만** 반영한다.

    · 추출 결함 2건 (cell wrap / 구두점 분절) → 원문 Activity로 복원
    · display_quality metadata 부여 (원문 검증분만 HUMAN_CONFIRMED)

승인 artifact `activity_reference_v0_2.json`은 **읽기만** 한다.
결과는 `PENDING_HUMAN_REVIEW`다.

    python analysis/tools/build_v0_2_1_draft.py
"""

from __future__ import annotations

import hashlib
import io
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

SRC = ROOT / "data" / "activities" / "activity_reference_v0_2.json"
OUT = ROOT / "data" / "activities" / "activity_reference_v0_2_1_draft.json"
NEW_VERSION = "activity-reference-v0.2.1"

# ---------------------------------------------------------------- 확정 correction
# analysis/tools/scan_extraction_defects.py 가 SOURCE_CONFIRMED_DEFECT로 판정하고
# 원문 geometry로 수동 확인한 것만 넣는다.
MERGES = [
    {
        "restored_label": "장화 신고 물웅덩이 건너기",
        "parts": ["장화 신고 물웅덩이", "건너기"],
        "correction_type": "SOURCE_CONFIRMED_EXTRACTION_DEFECT",
        "correction_note": (
            "표 셀 안의 시각적 줄바꿈을 Activity 구분자로 오판해 한 Activity가 "
            "두 개로 분리되었다. 셀 geometry로 원문 복원."
        ),
        "source_reference": (
            "references/samples/monthly/2026_민간_우리어린이집_만3-5세_월간보육계획안(7월).pdf "
            "p1 row[598-646] col2 / "
            "references/samples/monthly/2026_가정_키즈로스쿨어린이집_3-5세_월간보육계획안(7월).pdf "
            "p1 row[620-672] col4"
        ),
    },
    {
        "restored_label": "우리집에 왜 왔니? 놀이를 해요.",
        "parts": ["우리집에 왜 왔니?", "놀이를 해요."],
        "correction_type": "SOURCE_CONFIRMED_EXTRACTION_DEFECT",
        "correction_note": (
            "괄선 없는 하위 열을 인식하지 못해 물음표에서 분절되었다. "
            "셀 geometry로 원문 복원."
        ),
        "source_reference": (
            "references/samples/monthly/2026_민간_서진어린이집_만3세,만4-5세_"
            "월간보육계획안(5월).pdf p1 row[428-485] col1"
        ),
    },
]

# 원문 대조로 검증한 display quality만 HUMAN_CONFIRMED로 둔다.
HUMAN_CONFIRMED_QUALITY = {
    "전통놀이": (
        "TOO_GENERIC",
        "원문 4개 기관이 모두 '전통놀이 종류', '전통 놀이를 경험해 본다'처럼 "
        "범주어로 쓴다. 구체 놀이명이 합쳐진 것이 아니라 원문 자체가 범주다.",
    ),
    "모래놀이": ("GOOD_STANDALONE", "원문 '조물조물 모래놀이를 해요' 및 나열 목록 항목."),
    "투호놀이": ("GOOD_STANDALONE", "원문 '♥바깥놀이-투호놀이'. 구체 전통놀이명."),
    "대문놀이": ("GOOD_STANDALONE", "원문 '대문놀이를 해요'. 구체 전통놀이명."),
    "물길 놀이": ("GOOD_STANDALONE", "원문 나열 목록 '모래놀이, 물길 놀이, 줄넘기 …' 항목."),
    "줄넘기": ("GOOD_STANDALONE", "원문 나열 목록 '롤러장 나들이, 줄넘기' 항목."),
}

# 자동 탐지 결과. Selection에 영향을 주지 않는다(AUTO_CANDIDATE).
AUTO_QUALITY = {
    "팽이 놀이": ("NEEDS_HUMAN_REVIEW", "원문이 '<실내놀이> … 실팽이 놀이 …' 맥락이다."),
    "전통 놀이 한마당": ("INSTITUTION_SPECIFIC", "행사성 표현. 자동 탐지."),
    "숲속 동물 보호소": ("INSTITUTION_SPECIFIC", "자동 탐지."),
    "비온 뒤 놀이터 탐험": ("INSTITUTION_SPECIFIC", "자동 탐지."),
    "놀이터를 탐색하며 놀이해요": ("INSTITUTION_SPECIFIC", "자동 탐지."),
    "바깥 놀이터 사진을 찍어요": ("INSTITUTION_SPECIFIC", "자동 탐지."),
    "바깥 놀이터에서 지켜야 할 약속을 정해요": ("INSTITUTION_SPECIFIC", "자동 탐지."),
    "가을담기": ("POSSIBLE_FRAGMENT", "원문 wrap 여부를 확정하지 못했다. 사람 확인 필요."),
    "자연물 물감": ("POSSIBLE_FRAGMENT", "'가을담기'와 같은 셀일 가능성. 사람 확인 필요."),
}


def sha256_of(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    src_sha = sha256_of(SRC)
    print(f"  원본 : {SRC.name}  sha={src_sha[:16]}…")
    cat = json.loads(SRC.read_text("utf-8"))
    acts = {a["label"]: a for a in cat["activities"]}
    assert len(acts) == len(cat["activities"]), "label 중복 — 병합 로직 재검토 필요"

    removed: list[str] = []
    added: list[dict] = []

    for m in MERGES:
        parts = [acts[p] for p in m["parts"] if p in acts]
        if len(parts) != len(m["parts"]):
            print(f"  ! 건너뜀 (부분 없음): {m['restored_label']}")
            continue
        base = max(parts, key=lambda a: len(a.get("evidence", [])))
        merged = json.loads(json.dumps(base, ensure_ascii=False))
        merged["label"] = m["restored_label"]
        merged["activity_id"] = (
            "act_outdoor_v021_"
            + hashlib.sha256(m["restored_label"].encode("utf-8")).hexdigest()[:10]
        )
        # Evidence lineage 손실 없이 이동
        seen, ev = set(), []
        for p in parts:
            for e in p.get("evidence", []):
                key = (e["origin_id"], e.get("page"), e.get("observed_label"))
                if key in seen:
                    continue
                seen.add(key)
                ev.append(e)
        merged["evidence"] = ev
        # 파생 값 재계산 — 추측하지 않고 evidence에서 되뽑는다
        merged["applicable_months"] = sorted({e["observed_month"] for e in ev})
        scopes = {a for e in ev for a in e.get("age_scope", [])}
        merged["supported_ages"] = sorted(
            set().union(*[set(p["supported_ages"]) for p in parts]) & scopes
        ) or sorted(scopes)
        merged["label_derivation_type"] = "DIRECT_TRANSCRIPTION"
        merged["label_derivation"] = "cell geometry 기반 원문 복원"
        merged["aliases"] = sorted(
            {al for p in parts for al in p.get("aliases", [])}
            | {p["label"] for p in parts}
        )
        merged["correction_type"] = m["correction_type"]
        merged["correction_note"] = m["correction_note"]
        merged["supersedes_activity_ids"] = [p["activity_id"] for p in parts]
        merged["source_reference"] = m["source_reference"]
        merged["display_quality"] = "GOOD_STANDALONE"
        merged["display_quality_review_status"] = "HUMAN_CONFIRMED"
        added.append(merged)
        removed.extend(p["label"] for p in parts)
        print(f"  merge: {' + '.join(m['parts'])}  →  {m['restored_label']}  "
              f"(evidence {len(ev)}건)")

    new_acts = [a for a in cat["activities"] if a["label"] not in set(removed)]
    new_acts.extend(added)

    # display quality 부여
    n_human = n_auto = n_unrev = 0
    for a in new_acts:
        if "display_quality" in a and a.get("display_quality_review_status"):
            n_human += 1
            continue
        lab = a["label"]
        if lab in HUMAN_CONFIRMED_QUALITY:
            q, note = HUMAN_CONFIRMED_QUALITY[lab]
            a["display_quality"] = q
            a["display_quality_review_status"] = "HUMAN_CONFIRMED"
            a["correction_note"] = note
            n_human += 1
        elif lab in AUTO_QUALITY:
            q, note = AUTO_QUALITY[lab]
            a["display_quality"] = q
            a["display_quality_review_status"] = "AUTO_CANDIDATE"
            a["correction_note"] = note
            n_auto += 1
        else:
            a["display_quality"] = "GOOD_STANDALONE"
            a["display_quality_review_status"] = "UNREVIEWED"
            n_unrev += 1
        # source_version은 catalog_version과 일치해야 한다 (Domain 불변식)
    for a in new_acts:
        a["source_version"] = NEW_VERSION

    cat["catalog_version"] = NEW_VERSION
    cat["activities"] = new_acts
    cat["coverage"] = dict(cat.get("coverage", {}))
    months = sorted({m for a in new_acts for m in a["applicable_months"]})
    if "month_coverage" in cat:
        cat["month_coverage"] = months
    cat["coverage"]["month_coverage"] = months
    cat["coverage"]["item_count"] = len(new_acts)
    cat["review"] = dict(cat["review"])
    cat["review"]["domain_owner_approval"] = "PENDING_HUMAN_REVIEW"
    cat["review"]["approved_by"] = None
    cat["review"]["approved_at"] = None
    cat["review"]["supersedes"] = "activity-reference-v0.2.0"
    cat["review"]["patch"] = {
        "patch_id": "monthly-quality-patch-1",
        "base_version": "activity-reference-v0.2.0",
        "base_sha256": src_sha,
        "extraction_corrections": len(added),
        "removed_fragment_labels": sorted(set(removed)),
        "display_quality_human_confirmed": n_human,
        "display_quality_auto_candidate": n_auto,
        "display_quality_unreviewed": n_unrev,
    }

    OUT.write_text(json.dumps(cat, ensure_ascii=False, indent=1), encoding="utf-8")
    print()
    print(f"  항목 : {len(cat['activities'])} (v0.2.0 = 198)")
    print(f"  월 coverage : {months}")
    print(f"  품질 검토 : HUMAN {n_human} / AUTO {n_auto} / UNREVIEWED {n_unrev}")
    print(f"  출력 : {OUT.relative_to(ROOT)}")
    print(f"  sha256 : {sha256_of(OUT)}")
    print(f"  원본 불변 확인 : {sha256_of(SRC) == src_sha}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
