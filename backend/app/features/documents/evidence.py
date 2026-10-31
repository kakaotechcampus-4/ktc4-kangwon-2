"""증빙 등록의 형식 점검 — `POST /api/documents/import` (docs/api-spec.md §11 「증빙 등록」).

**내용을 판정하지 않는다.** 「이 문서가 지표를 충족한다」는 모델도 우리도 말하지 않는다
(§12 · ADR-019 · ADR-022). 여기서 보는 것은 **집계에 들어갈 수 있는 모양인가**뿐이고,
어긋나도 등록을 막지 않는다 — 교사가 보고 고치게 한 줄씩 돌려줄 뿐이다.

막지 않는 이유는 간단하다. 원에서 쓰던 서류는 우리 규격을 모르고 쓰였다.
못 올리게 하면 교사는 평가 점검 화면을 포기한다.

나중에 내용 점검(사람이든 모델이든)을 붙인다면 이 함수가 그 자리다 — 등록 경로에서
점검을 부르는 곳은 여기 하나다.
"""

from datetime import date as date_
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.features.centers.models import Class
from app.features.documents.models import Document
from app.features.evaluation import judge
from app.features.evaluation.catalog import load_catalog

#: 「특성과 변화 정도」를 서술했다고 보기 어려운 길이. 숫자에 근거는 없다 — 빈 파일과
#: 제목만 있는 파일을 걸러내려는 하한이다.
MIN_BODY = 50


def check_evidence(
    session: Session,
    *,
    center_id: int,
    kind: str,
    class_id: int,
    child_id: int | None,
    start: date_,
    end: date_,
    body: str,
    now: datetime,
) -> list[dict[str, str]]:
    """등록해도 되지만 교사가 알아야 하는 것들. 비어 있으면 아무 문제 없다는 뜻이다."""
    notices: list[dict[str, str]] = []

    if kind == "assessment" and child_id is None:
        notices.append(
            {
                "code": "ASSESSMENT_NEEDS_CHILD",
                "message": (
                    "영유아 평가는 아이마다 세어요. "
                    "아동을 고르지 않으면 4-2 집계에 들어가지 않아요."
                ),
            }
        )

    if kind == "assessment" and child_id is not None:
        rule = load_catalog().get("4-2").rule
        period = judge.window_for(rule["window"], judge.today_kst(now))
        if not period.contains(end):
            notices.append(
                {
                    "code": "OUT_OF_REVIEW_PERIOD",
                    "message": (
                        f"평가제가 보는 기간은 {period.start} ~ {period.end} 예요. "
                        "이 문서는 그 밖이라 4-2 집계에 들어가지 않아요."
                    ),
                }
            )

    if len(body.strip()) < MIN_BODY:
        notices.append(
            {
                "code": "BODY_TOO_SHORT",
                "message": "원문이 너무 짧아요. 파일을 제대로 읽었는지 확인해주세요.",
            }
        )

    overlapping = session.scalar(
        select(Document.id)
        .join(Class, Class.id == Document.class_id)
        .where(
            Class.center_id == center_id,
            Document.kind == kind,
            Document.class_id == class_id,
            Document.child_id == child_id,
            Document.origin == "IMPORT",
            Document.start_date <= end,
            Document.end_date >= start,
        )
        .limit(1)
    )
    if overlapping is not None:
        notices.append(
            {
                "code": "ALREADY_REGISTERED",
                "message": (
                    "같은 아동·종류로 기간이 겹치는 증빙이 이미 있어요. "
                    "같은 문서를 두 번 올린 건 아닌지 확인해주세요."
                ),
            }
        )

    return notices
