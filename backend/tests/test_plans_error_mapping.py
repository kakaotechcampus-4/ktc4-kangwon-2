"""연간 오류 응답 정리 (Core Error Audit E-2 · E-3 · E-4 · U-20).

진짜 Postgres 위에서 HTTP 로 부른다.

- 동시 생성이 유니크 인덱스에 걸리면 일반 텍스트 500 이 아니라 409 `ALREADY_EXISTS` 다.
- 생성기 결과가 계약을 어기면 422 가 아니라 500 `GENERATION_FAILED` 다.
- Core 의 영어 문장을 교사에게 보내지 않는다 — 고정 문구로 답한다.
- 그 달 · 반 연령에 맞는 승인 주제가 없으면 503 `DEPENDENCY_UNAVAILABLE` 이다(U-20 B).
"""

import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session
from ssuksak.planning.rules.errors import YearlyRuleError
from ssuksak.planning.rules.yearly_reference_rules import AGE_RULE_ID
from ssuksak.planning.rules.yearly_theme_selection import RULE_ID as THEME_SELECTION_RULE_ID

from app.db import engine
from app.features.centers.models import Center, Class
from app.features.plans import router as annual_router
from app.features.plans.models import Plan
from app.main import app

client = TestClient(app)
NO_CANDIDATE = "지금은 이 반의 연간계획안을 만들 수 없습니다. 관리자에게 문의해 주세요."


def _class(session, name: str, *, commit: bool = False) -> dict:
    center = Center(
        name=name, director_name="김원장", region_sido="강원특별자치도", region_sigungu="춘천시"
    )
    session.add(center)
    session.flush()
    klass = Class(
        center_id=center.id,
        name="햇살반",
        school_year=2026,
        age_min=3,
        age_max=3,
        teacher_name="김선생",
    )
    session.add(klass)
    session.commit() if commit else session.flush()
    return {"center": center.id, "class": klass.id}


def _create(class_id: int):
    return client.post("/api/plans/annual", json={"class_id": class_id, "form_id": None})


def _error(response) -> tuple:
    body = response.json()["error"]
    return response.status_code, body["code"], body["message"], body["fields"]


@pytest.fixture
def mine(db_session, teacher):
    ids = _class(db_session, "오류매핑원")
    teacher.center_id = ids["center"]
    return ids


def _use_case_raises(monkeypatch, error):
    class Raising:
        def __init__(self, **_):
            pass

        def execute(self, command):
            raise error

    monkeypatch.setattr(annual_router, "GenerateYearlyPlan", Raising)


def test_생성기_결과가_계약을_어기면_500_GENERATION_FAILED_이고_저장되지_않는다(
    db_session, mine, monkeypatch
):
    class WrongCount:
        def generate(self, requests):
            return ()  # 12개월을 요청했는데 아무것도 안 돌려준다

    monkeypatch.setattr(annual_router, "theme_text_generator", lambda: WrongCount())

    assert _error(_create(mine["class"])) == (
        500,
        "GENERATION_FAILED",
        "계획안을 만들지 못했습니다. 다시 시도해주세요.",
        [],
    )
    assert (
        db_session.scalar(
            select(func.count()).select_from(Plan).where(Plan.center_id == mine["center"])
        )
        == 0
    )


def test_그_달에_맞는_주제가_없으면_503_DEPENDENCY_UNAVAILABLE(mine, monkeypatch):
    _use_case_raises(
        monkeypatch,
        YearlyRuleError(
            THEME_SELECTION_RULE_ID, "no eligible Theme candidate for 2026-03 and ages [3]"
        ),
    )

    assert _error(_create(mine["class"])) == (503, "DEPENDENCY_UNAVAILABLE", NO_CANDIDATE, [])


def test_다른_도메인_오류는_422_고정_문구이고_영어_문장이_나가지_않는다(mine, monkeypatch):
    _use_case_raises(monkeypatch, YearlyRuleError(AGE_RULE_ID, "ages must not contain duplicates"))

    response = _create(mine["class"])

    assert _error(response) == (422, "VALIDATION_FAILED", "입력값을 확인해주세요.", [])
    assert "duplicates" not in response.text


def test_PUT_도메인_거절도_고정_문구다(mine):
    created = _create(mine["class"])
    assert created.status_code == 201, created.text

    response = client.put(
        f"/api/plans/annual/{created.json()['id']}/months/3",
        json={"theme": "   ", "sub_themes": []},
    )

    assert _error(response) == (422, "VALIDATION_FAILED", "입력값을 확인해주세요.", [])


def test_확정_뒤_수정은_그대로_409_ALREADY_CONFIRMED(mine):
    created = _create(mine["class"]).json()
    assert client.post(f"/api/plans/annual/{created['id']}/confirm").status_code == 200

    response = client.put(
        f"/api/plans/annual/{created['id']}/months/3", json={"theme": "새 주제", "sub_themes": []}
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "ALREADY_CONFIRMED"


# ── 동시 생성 — 진짜 연결 두 개 ─────────────────────────────────────────────


@pytest.fixture
def live(_schema, teacher):
    """커밋된 원 · 반. 요청마다 진짜 session 을 쓴다(get_session 을 바꾸지 않는다)."""
    with Session(engine) as session:
        ids = _class(session, "동시생성원", commit=True)
    teacher.center_id = ids["center"]
    try:
        yield ids
    finally:
        with Session(engine) as session:
            session.execute(delete(Plan).where(Plan.center_id == ids["center"]))
            session.execute(delete(Class).where(Class.id == ids["class"]))
            session.execute(delete(Center).where(Center.id == ids["center"]))
            session.commit()


def test_동시_생성은_하나만_만들고_나머지는_409_ALREADY_EXISTS(live, monkeypatch):
    """둘 다 「없다」를 보고 지나가도, 늦은 쪽이 인덱스에 걸려 409 를 받는다.

    일반 텍스트 500 이 아니다.
    """
    reached, release = threading.Event(), threading.Event()
    original = annual_router.GenerateYearlyPlan
    calls = []

    class PausedAfterSave(original):
        def execute(self, command):
            result = super().execute(command)  # 저장소가 flush 까지 했다 — 행이 잠긴 채 commit 전
            calls.append(command)
            if len(calls) == 1:
                reached.set()
                assert release.wait(timeout=20)
            return result

    monkeypatch.setattr(annual_router, "GenerateYearlyPlan", PausedAfterSave)

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(_create, live["class"])
        assert reached.wait(timeout=20)
        second = executor.submit(_create, live["class"])
        time.sleep(1.0)  # 두 번째가 중복 조회를 통과해 인덱스 앞에서 기다린다
        release.set()
        responses = sorted(
            (first.result(timeout=30), second.result(timeout=30)), key=lambda r: r.status_code
        )

    assert [r.status_code for r in responses] == [201, 409]
    assert _error(responses[1]) == (
        409,
        "ALREADY_EXISTS",
        "이 반의 연간계획안이 이미 있습니다.",
        ["class_id"],
    )
    with Session(engine) as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(Plan)
                .where(Plan.center_id == live["center"], Plan.kind == "annual")
            )
            == 1
        )
