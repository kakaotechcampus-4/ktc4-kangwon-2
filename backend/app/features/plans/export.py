"""계획안 내보내기 — `GET /api/plans/{id}/export/hwp` (docs/api-spec.md §9).

경로는 `hwp` 지만 내려가는 파일은 hwpx 다. `.hwp` 는 만들지 않는다(`hwpx.py`).

**확정본만 내보낸다.** 내보낸 파일은 제출 문서다. DRAFT 를 내보낼 수 있으면 교사가
확인하지 않은 초안이 그대로 제출되는 길이 생긴다. 확정 전 내용은 화면에서 본다.

**출처를 싣지 않는다.** evidence · generation 은 화면에서 근거를 보여주는 값이다.
제출 문서에 섞이면 안 된다 — 여기서는 교사가 읽는 글자만 꺼낸다.
"""

from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Response, status
from ssuksak.planning import PlanId

from app.features.plans.hwpx import TEMPLATE_DIR, fill_table
from app.features.plans.router import DbSession, _detail, _repo, _row
from app.shared.auth.dependency import CurrentUser
from app.shared.auth.ownership import require_own_class

router = APIRouter(prefix="/plans", tags=["plans"])

MEDIA_TYPE = "application/hwp+zip"

# 양식의 머리행(월 · 주제 · 소주제 · 안전교육) 줄 수.
ANNUAL_HEADER_ROWS = 1


@router.get("/{plan_id}/export/hwp")
def export_plan(plan_id: int, session: DbSession, user: CurrentUser) -> Response:
    """지금은 연간만 있다. 월간은 월간 API 가 생길 때 양식과 함께 붙인다."""
    row = _row(session, user, plan_id)
    if row.status != "CONFIRMED":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={
                "code": "GATE_BLOCKED",
                "message": "확정된 계획안만 내보낼 수 있습니다.",
                "fields": [],
            },
        )
    plan = _detail(row, _repo(session, user).get(PlanId(row.plan_ref)))
    klass = require_own_class(session, user, plan.class_id)

    title = f"{klass.name} {plan.school_year}학년도 연간 보육계획안"
    rows = [
        [
            f"{month.month}월",
            month.theme,
            "\n".join(month.sub_themes),
            "\n".join(month.safety_education),
        ]
        for month in plan.months
    ]
    content = fill_table(
        (TEMPLATE_DIR / "annual.hwpx").read_bytes(), title, ANNUAL_HEADER_ROWS, rows
    )
    # 한글 파일명은 filename* 로만 안전하게 간다. filename 은 그걸 못 읽는 브라우저용이다.
    disposition = (
        f"attachment; filename=\"plan-{row.id}.hwpx\"; filename*=UTF-8''{quote(title + '.hwpx')}"
    )
    return Response(content, media_type=MEDIA_TYPE, headers={"Content-Disposition": disposition})
