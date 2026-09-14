"""승인 Activity Reference artifact의 Runtime Projection (HD-I, 선택지 B).

승인 Catalog(`data/activities/activity_reference_v0_2_1.json`)는 Human Review와
품질 metadata를 함께 담은 **Source of Truth**다. Production Domain Model에는 그
metadata를 추가하지 않기로 했으므로(HD-I), adapter 계층에서 runtime에 필요한
필드만 남기는 **명시적 projection**을 거쳐 기존 strict schema로 파싱한다.

    HUMAN_APPROVED artifact
        → project_runtime_payload()      (allowlist 기반 제거)
        → parse_activity_reference_payload()   (기존 strict schema 그대로)
        → ActivityCatalog

**핵심 규칙**

1. 제거 대상은 **allowlist로 고정**한다. 알 수 없는 extra field를 자동으로
   제거하지 않는다. 새 필드가 나타나면 기존처럼 schema error가 나야 한다.

       known review metadata  → projection에서 제거
       unknown field          → schema error (그대로 실패)

2. **Approval Override가 아니다.** `review.domain_owner_approval`,
   `approved_by`, `approved_at`, `catalog_version`, `origins`, `activities`를
   건드리지 않는다. `is_active`는 여전히 승인 상태에서만 파생된다.

3. 입력을 변형하지 않는다. 항상 새 dict를 반환한다.
"""

from __future__ import annotations

import copy
from typing import Any

__all__ = [
    "REVIEW_ONLY_ACTIVITY_FIELDS",
    "REVIEW_ONLY_CATALOG_FIELDS",
    "REVIEW_ONLY_EVIDENCE_FIELDS",
    "RUNTIME_REQUIRED_CATALOG_FIELDS",
    "project_runtime_payload",
]

REVIEW_ONLY_CATALOG_FIELDS: frozenset[str] = frozenset(
    {
        "draft",
        "draft_note",
        "approved_from_draft",
        "pending_human_review",
    }
)
"""Catalog 수준의 Draft/Review 기록. runtime 의미가 없다.

`supersedes` / `disclaimer` / `*_semantics` / `exclusion_policy` /
`taxonomy_scope` 등은 **제거하지 않는다.** 승인 artifact의 해석 규정이며
`_Catalog`가 extra를 허용하므로 runtime 파싱을 막지 않는다.
"""

REVIEW_ONLY_ACTIVITY_FIELDS: frozenset[str] = frozenset(
    {
        "age_support_basis",
        "age_support_review_required",
        "alias_candidates_pending_review",
        "draft_delta",
        "draft_review_flags",
        "draft_status",
        "evidence_count",
        "hd_g_reason",
        "hd_g_verdict",
        "observed_institution_count",
        "observed_institutions",
        "origins_used",
        # v0.2.1에서 추가된 correction 기록. runtime 의미가 없다.
        "correction_type",
        "correction_note",
        "supersedes_activity_ids",
        "source_reference",
    }
)
"""Activity 수준의 품질·검토 metadata. `_Activity`가 extra="forbid"라 제거해야 한다.

`display_quality` / `display_quality_review_status`는 여기에 **넣지 않는다.**
그 둘은 runtime Selection이 읽는 값이므로 review-only가 아니다.
"""

REVIEW_ONLY_EVIDENCE_FIELDS: frozenset[str] = frozenset({"age_evidence_basis"})
"""Evidence 수준의 연령 근거 강도 표시. `_Evidence`가 extra="forbid"라 제거해야 한다."""

RUNTIME_REQUIRED_CATALOG_FIELDS: frozenset[str] = frozenset(
    {
        "schema_version",
        "catalog_id",
        "catalog_version",
        "review",
        "coverage",
        "origins",
        "activities",
    }
)
"""projection이 절대 건드리지 않는 runtime 필수 필드."""

_PROTECTED_REVIEW_KEYS = ("domain_owner_approval", "approved_by", "approved_at")


def project_runtime_payload(payload: object) -> Any:
    """승인 artifact에서 **allowlist에 선언된 review metadata만** 제거한다.

    Args:
        payload: 승인 Catalog 원시 payload. 변형하지 않는다.

    Returns:
        runtime strict schema에 넘길 값. dict가 아니면 **그대로 통과**시켜
        기존과 동일한 schema 오류가 나게 한다. projection은 형식 검증을 하지
        않으며 오류 타입을 바꾸지 않는다.

    Notes:
        알 수 없는 필드는 남겨 둔다. 그래야 strict schema가 기존대로 거부한다.
        승인 상태(`review.domain_owner_approval`)를 읽지도 바꾸지도 않는다.
    """
    if not isinstance(payload, dict):
        return payload  # 형식 검증은 strict schema의 몫이다

    out = copy.deepcopy(payload)

    for key in REVIEW_ONLY_CATALOG_FIELDS:
        out.pop(key, None)

    activities = out.get("activities")
    if isinstance(activities, list):
        for activity in activities:
            if not isinstance(activity, dict):
                continue
            for key in REVIEW_ONLY_ACTIVITY_FIELDS:
                activity.pop(key, None)
            evidence = activity.get("evidence")
            if isinstance(evidence, list):
                for item in evidence:
                    if not isinstance(item, dict):
                        continue
                    for key in REVIEW_ONLY_EVIDENCE_FIELDS:
                        item.pop(key, None)

    # 승인 상태를 건드리지 않았는지 확인한다. projection은 Approval Override가 아니다.
    before, after = payload.get("review"), out.get("review")
    if isinstance(before, dict) and isinstance(after, dict):
        for key in _PROTECTED_REVIEW_KEYS:
            if before.get(key) != after.get(key):
                raise AssertionError(
                    f"projection이 승인 상태를 변경했다: review.{key}"
                )

    return out
