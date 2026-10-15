"""올해 원의 반 · 아동과 확정 문서를 모아 자동 판정한다 (api-spec §12)."""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.features.centers.models import Child, Class
from app.features.documents.service import list_confirmed_by_child, list_confirmed_by_class
from app.features.evaluation import judge
from app.features.evaluation.catalog import load_catalog
from app.shared.school_year import school_year_of


def judge_auto(session: Session, center_id: int, now: datetime) -> dict[str, judge.AutoResult]:
    today = judge.today_kst(now)
    school_year = school_year_of(now)
    class_ids = session.scalars(
        select(Class.id).where(Class.center_id == center_id, Class.school_year == school_year)
    ).all()
    child_ids = session.scalars(select(Child.id).where(Child.class_id.in_(class_ids))).all()
    catalog = load_catalog()
    class_rule, child_rule = catalog.get("4-1").rule, catalog.get("4-2").rule
    class_window = judge.window_for(class_rule["window"], today)
    child_window = judge.window_for(child_rule["window"], today)
    daily_logs = [
        judge.DailyLogFact(doc.id, doc.class_id, doc.end_date)
        for doc in list_confirmed_by_class(
            session,
            center_id,
            kind=class_rule["daily_log"]["document_kind"],
            class_ids=class_ids,
            start=class_window.start,
            end=class_window.end,
        )
    ]
    # ponytail: 월간계획안 저장 · plans 조회 함수(승석)가 생기면 교체 — §12 아직 정하지 않은 것.
    plans = []
    assessments = [
        judge.AssessmentFact(doc.id, doc.child_id, doc.end_date)
        for doc in list_confirmed_by_child(
            session,
            center_id,
            kind=child_rule["document_kind"],
            child_ids=child_ids,
            start=child_window.start,
            end=child_window.end,
        )
    ]
    return {
        "4-1": judge.judge_4_1(
            class_window,
            class_ids,
            plans,
            daily_logs,
            min_plans_per_class=class_rule["plan"]["min_per_class"],
        ),
        "4-2": judge.judge_4_2(
            child_window, child_ids, assessments, min_per_child=child_rule["min_per_child"]
        ),
    }
