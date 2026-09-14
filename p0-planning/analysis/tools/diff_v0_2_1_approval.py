"""§2. v0.2.1 Draft → Approved Semantic Diff 검증 (분석 전용).

승인 Artifact가 Draft의 **의미를 바꾸지 않았는지** 확인한다.

허용되는 차이는 승인 metadata뿐이다. Activity / Evidence / 품질 metadata /
correction metadata / source lineage에 차이가 있으면 실패로 보고한다.

    python analysis/tools/diff_v0_2_1_approval.py
"""

from __future__ import annotations

import hashlib
import io
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

DRAFT = ROOT / "data" / "activities" / "activity_reference_v0_2_1_draft.json"
APPROVED = ROOT / "data" / "activities" / "activity_reference_v0_2_1.json"

ALLOWED_TOP_LEVEL = {"$schema_note", "draft", "draft_note", "approved_from_draft",
                     "review"}
"""승인 단계에서 바뀌어도 되는 top-level 키. 전부 승인 provenance다."""

ALLOWED_REVIEW = {"domain_owner_approval", "approved_by", "approved_at",
                  "pending_reason", "runtime_rule", "review_document",
                  "approval_note", "base_catalog", "approved_from"}


def sha(p: pathlib.Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main() -> int:
    a = json.loads(DRAFT.read_text("utf-8"))
    b = json.loads(APPROVED.read_text("utf-8"))
    failures: list[str] = []

    print("=" * 78)
    print(" v0.2.1 Draft → Approved Semantic Diff")
    print("=" * 78)
    print(f"  draft    {DRAFT.name}  sha256={sha(DRAFT)}")
    print(f"  approved {APPROVED.name}  sha256={sha(APPROVED)}")
    print()

    # ---------------------------------------------------------- top level
    changed = sorted(
        k for k in set(a) | set(b)
        if json.dumps(a.get(k), ensure_ascii=False, sort_keys=True)
        != json.dumps(b.get(k), ensure_ascii=False, sort_keys=True)
    )
    print(f"  변경된 top-level 키 {len(changed)}개: {changed}")
    for k in changed:
        if k not in ALLOWED_TOP_LEVEL:
            failures.append(f"허용되지 않은 top-level 변경: {k}")

    rc = sorted(
        k for k in set(a["review"]) | set(b["review"])
        if json.dumps(a["review"].get(k), ensure_ascii=False, sort_keys=True)
        != json.dumps(b["review"].get(k), ensure_ascii=False, sort_keys=True)
    )
    print(f"  변경된 review 키 {len(rc)}개: {rc}")
    for k in rc:
        if k not in ALLOWED_REVIEW:
            failures.append(f"허용되지 않은 review 변경: {k}")

    # ------------------------------------------------------ activity 동일성
    if json.dumps(a["activities"], ensure_ascii=False, sort_keys=True) == json.dumps(
        b["activities"], ensure_ascii=False, sort_keys=True
    ):
        print("\n  activities 블록: **바이트 단위로 동일** (196 items)")
    else:
        failures.append("activities 블록이 달라졌다")
        ia = {x["activity_id"]: x for x in a["activities"]}
        ib = {x["activity_id"]: x for x in b["activities"]}
        for k in sorted(set(ia) | set(ib)):
            if ia.get(k) != ib.get(k):
                print(f"    diff activity_id={k}")

    for k in ("origins", "coverage", "exclusion_policy", "setting_semantics",
              "evidence_semantics", "age_semantics", "placement_slot_semantics",
              "label_derivation_semantics", "curriculum_link_semantics",
              "theme_link_semantics", "taxonomy_scope", "source_of_truth_refs",
              "pending_human_review", "safety_exclusion_statement"):
        if a.get(k) != b.get(k):
            failures.append(f"lineage/semantics 블록 변경: {k}")

    # ------------------------------------------------- 축별 명시 동일성 확인
    def axis(cat, fn):
        return {x["activity_id"]: fn(x) for x in cat["activities"]}

    axes = {
        "activity IDs": lambda x: x["activity_id"],
        "labels": lambda x: x["label"],
        "evidence": lambda x: x["evidence"],
        "ages": lambda x: (x["supported_ages"], x["allow_mixed_age"],
                           x["mixed_age_requires_all_supported"]),
        "months": lambda x: x["applicable_months"],
        "settings": lambda x: x["setting"],
        "display_quality": lambda x: x["display_quality"],
        "display_quality_review_status": lambda x: x["display_quality_review_status"],
        "correction metadata": lambda x: (x.get("correction_type"),
                                          x.get("correction_note"),
                                          x.get("supersedes_activity_ids"),
                                          x.get("source_reference")),
        "source lineage": lambda x: (x["origin_id"], x["source_version"],
                                     x["label_derivation_type"],
                                     x.get("label_derivation"),
                                     x.get("origins_used")),
    }
    print()
    for name, fn in axes.items():
        same = axis(a, fn) == axis(b, fn)
        print(f"  {'IDENTICAL' if same else 'DIFFERENT':<10} {name}")
        if not same:
            failures.append(f"{name} 가 달라졌다")

    # --------------------------------------------------------- 승인 상태 확인
    print()
    print(f"  draft    domain_owner_approval = {a['review']['domain_owner_approval']}")
    print(f"  approved domain_owner_approval = {b['review']['domain_owner_approval']}")
    print(f"  approved_by  = {b['review']['approved_by']}")
    print(f"  approved_at  = {b['review']['approved_at']}")
    print(f"  catalog_version  draft={a['catalog_version']}  "
          f"approved={b['catalog_version']}")
    print(f"  item_count       draft={len(a['activities'])}  "
          f"approved={len(b['activities'])}")

    if b["review"]["domain_owner_approval"] != "HUMAN_APPROVED":
        failures.append("승인 Artifact가 HUMAN_APPROVED가 아니다")
    if a["catalog_version"] != b["catalog_version"]:
        failures.append("catalog_version이 달라졌다")

    print()
    print("=" * 78)
    if failures:
        print(" DIFF FAIL")
        for f in failures:
            print(f"   - {f}")
        return 1
    print(" DIFF OK — 승인 metadata 외 의미 변경 없음")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
