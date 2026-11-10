"""계획안 LLM 요청에 아이 실명이 나가지 않는다 — 칸 재생성 · 다른 반 아이 · 연간 가져오기.

멘토 리뷰 #380 (2026-11-05). 생성만 요청 사항을 가렸고 칸 재생성은 가리지 않았다.
가리는 이름도 그 반 아이뿐이었다 — 원 아이 전부를 가린다. 이름은 전부 가명이다(ADR-004).
"""

import io
import json
import zipfile

import pytest
import test_weekly_plans_api as weekly_api
from ssuksak.adapters.request_aware_monthly_llm import RequestAwareMonthlyLlm
from ssuksak.adapters.request_aware_weekly_llm import RequestAwareWeeklyLlm
from test_child_code import BARE_MESSAGES
from test_monthly_lifecycle_api import _approved, _seed, client  # noqa: F401

from app.config import settings
from app.features.centers.models import Center, Child, Class
from app.features.plans import annual_extract, monthly_router, weekly_router
from app.shared.childCode import load_pool, mask, table_for_text

# 우리 반 이가명 · 옆 반 최다솜. 둘 다 이름만(성을 떼고) 적었다.
MEMO = "가명이와 다솜이가 좋아하는 공룡 놀이를 넣어 주세요"


def _children(session, class_id: int) -> int:
    """같은 원 옆 반을 하나 더 만든다. 가명은 반마다 따로 발급해 두 반에서 같을 수 있다."""
    klass = session.get(Class, class_id)
    other = Class(
        center_id=klass.center_id,
        name="달님반",
        school_year=klass.school_year,
        age_min=3,
        age_max=4,
        teacher_name="선생",
    )
    session.add(other)
    session.flush()
    session.add_all(
        [
            Child(class_id=class_id, name="이가명", code="도담"),
            Child(class_id=other.id, name="최다솜", code="도담"),
        ]
    )
    session.flush()
    return other.id


def _no_names(prompt: str) -> None:
    assert "공룡 놀이" in prompt  # 메모는 실렸다
    assert "가명" not in prompt and "다솜" not in prompt


def test_월간_칸을_다시_만들어도_요청_사항의_아이_이름은_가명으로_나간다(
    db_session, teacher, monkeypatch
):
    seed = _seed(db_session, "가원", "a@example.com")
    teacher.center_id = seed["center"]
    _children(db_session, seed["class"])
    annual = client.post(
        "/api/plans/annual", json={"format": "MONTHLY_THEME", "class_id": seed["class"]}
    )
    assert client.post(f"/api/plans/annual/{annual.json()['id']}/confirm").status_code == 200
    plan = client.post(
        "/api/plans/monthly",
        json={"class_id": seed["class"], "month": 9, "profile_ref": seed["profile"], "memo": MEMO},
    ).json()
    sent = []

    class Spy(RequestAwareMonthlyLlm):
        def generate_cell(self, request):
            sent.append(request.user_content)
            return super().generate_cell(request)

    monkeypatch.setattr(monthly_router, "monthly_llm_provider", Spy)
    focus = next(s for s in plan["sections"] if s["section_key"] == "focus")["cells"][0]
    response = client.post(
        f"/api/plans/monthly/{plan['id']}/cells/{focus['item_id']}/regenerate",
        json={"expected_revision": plan["revision"]},
    )

    assert response.status_code == 200, response.json()
    assert response.json()["memo"] == MEMO  # 저장된 메모는 실명 그대로다
    [prompt] = sent
    _no_names(prompt)


ONE_SYLLABLE_MEMO = "민이가 좋아하는 공룡 놀이를 넣어 주세요"


def _monthly_with_one_syllable_child(session, teacher, call_name):
    """외자 아이 김민이 있는 반. 교사는 요청 사항에 「민이가」라고 쓴다."""
    seed = _seed(session, "가원", "a@example.com")
    teacher.center_id = seed["center"]
    session.add(Child(class_id=seed["class"], name="김민", code="가람", call_name=call_name))
    session.flush()
    annual = client.post(
        "/api/plans/annual", json={"format": "MONTHLY_THEME", "class_id": seed["class"]}
    )
    assert client.post(f"/api/plans/annual/{annual.json()['id']}/confirm").status_code == 200
    return seed


def test_외자_아이의_부르는_이름도_요청_사항에서_가명으로_나간다(db_session, teacher, monkeypatch):
    seed = _monthly_with_one_syllable_child(db_session, teacher, "민이")
    sent = []

    class Spy(RequestAwareMonthlyLlm):
        def generate_monthly(self, request):
            sent.append(request.user_content)
            return super().generate_monthly(request)

    monkeypatch.setattr(monthly_router, "monthly_llm_provider", Spy)
    response = client.post(
        "/api/plans/monthly",
        json={
            "class_id": seed["class"],
            "month": 9,
            "profile_ref": seed["profile"],
            "memo": ONE_SYLLABLE_MEMO,
        },
    )

    assert response.status_code == 201, response.json()
    assert sent and all("공룡 놀이" in p and "민이가" not in p for p in sent)
    assert any("가람이가" in p for p in sent)


@pytest.mark.parametrize("call_name", [None, "민이"])
def test_외자_아이의_다른_꼴도_요청_사항에서_가명으로_나간다(
    db_session, teacher, monkeypatch, call_name
):
    # 부르는 이름(민이)을 등록해도 「민은」 · 「민한테」가 원문으로 나가면 안 된다(3차 점검 2번).
    seed = _monthly_with_one_syllable_child(db_session, teacher, call_name)
    sent = []

    class Spy(RequestAwareMonthlyLlm):
        def generate_monthly(self, request):
            sent.append(request.user_content)
            return super().generate_monthly(request)

    monkeypatch.setattr(monthly_router, "monthly_llm_provider", Spy)
    response = client.post(
        "/api/plans/monthly",
        json={
            "class_id": seed["class"],
            "month": 9,
            "profile_ref": seed["profile"],
            "memo": "민은 공룡 놀이를 좋아해요. 민한테 맞춰 주세요",
        },
    )

    assert response.status_code == 201, response.json()
    assert sent and all("민은" not in p and "민한테" not in p for p in sent)
    assert any("가람은" in p and "가람한테" in p for p in sent)


@pytest.mark.parametrize("call_name", [None, "민이"])
def test_외자_글자가_홀로_서면_요청_사항을_LLM_에_보내지_않는다(
    db_session, teacher, monkeypatch, call_name
):
    seed = _monthly_with_one_syllable_child(db_session, teacher, call_name)
    monkeypatch.setattr(
        monthly_router, "monthly_llm_provider", lambda: pytest.fail("LLM 을 부르면 안 된다")
    )
    response = client.post(
        "/api/plans/monthly",
        json={
            "class_id": seed["class"],
            "month": 9,
            "profile_ref": seed["profile"],
            "memo": "민 옆자리 친구와 공룡 놀이를 넣어 주세요",
        },
    )

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["fields"] == ["memo"]
    assert error["message"] == BARE_MESSAGES[call_name]


def test_칸_재생성에서_이름을_못_가리면_그_칸을_직접_고치라고_알린다(db_session, teacher):
    """재생성 화면에는 요청 사항을 고치는 칸이 없다 — 「이 칸은 직접 고쳐 주세요」."""
    seed = _seed(db_session, "가원", "a@example.com")
    teacher.center_id = seed["center"]
    _children(db_session, seed["class"])
    annual = client.post(
        "/api/plans/annual", json={"format": "MONTHLY_THEME", "class_id": seed["class"]}
    )
    assert client.post(f"/api/plans/annual/{annual.json()['id']}/confirm").status_code == 200
    plan = client.post(
        "/api/plans/monthly",
        json={"class_id": seed["class"], "month": 9, "profile_ref": seed["profile"], "memo": MEMO},
    ).json()
    # 만든 뒤 같은 반에 「가명」을 같이 쓰는 아이가 들어왔다 — 메모의 「가명이」가 누구인지 모른다.
    db_session.add(Child(class_id=seed["class"], name="박가명", code="나래"))
    db_session.flush()
    focus = next(s for s in plan["sections"] if s["section_key"] == "focus")["cells"][0]

    response = client.post(
        f"/api/plans/monthly/{plan['id']}/cells/{focus['item_id']}/regenerate",
        json={"expected_revision": plan["revision"]},
    )

    assert response.status_code == 422, response.json()
    assert response.json()["error"]["fields"] == ["memo"]
    assert "이 칸은 직접 고쳐 주세요" in response.json()["error"]["message"]


def test_주간_칸을_다시_만들어도_요청_사항의_아이_이름은_가명으로_나간다(
    db_session, teacher, monkeypatch
):
    seed = weekly_api._seed(db_session, "가원", "a@example.com")
    teacher.center_id = seed["center"]
    _children(db_session, seed["class"])
    weekly_api._monthly(seed)
    plan = client.post(
        "/api/plans/weekly",
        json={"class_id": seed["class"], "week_id": weekly_api.WEEK, "memo": MEMO},
    ).json()
    sent = []

    class Spy(RequestAwareWeeklyLlm):
        def generate_weekly(self, request):
            sent.append(request.user_content)
            return super().generate_weekly(request)

    monkeypatch.setattr(weekly_router, "_weekly_provider", Spy)
    response = weekly_api._regenerate(plan, "goals")

    assert response.status_code == 200, response.json()
    assert response.json()["memo"] == MEMO
    [prompt] = sent
    _no_names(prompt)


def test_월간_칸을_다시_만들면_교사가_고친_다른_칸의_아이_이름도_가명으로_나간다(
    db_session, teacher, monkeypatch
):
    # 칸 재생성은 같은 달의 다른 칸 값(month_snapshot)을 맥락으로 싣는다. 메모만 가리면
    # 교사가 칸에 적은 아이 이름이 그대로 나간다.
    seed = _seed(db_session, "가원", "a@example.com")
    teacher.center_id = seed["center"]
    _children(db_session, seed["class"])
    annual = client.post(
        "/api/plans/annual", json={"format": "MONTHLY_THEME", "class_id": seed["class"]}
    )
    assert client.post(f"/api/plans/annual/{annual.json()['id']}/confirm").status_code == 200
    plan = client.post(
        "/api/plans/monthly",
        json={"class_id": seed["class"], "month": 9, "profile_ref": seed["profile"]},
    ).json()
    outdoor = next(s for s in plan["sections"] if s["section_key"] == "outdoor_play")["cells"][0]
    edited = client.put(
        f"/api/plans/monthly/{plan['id']}/cells/{outdoor['item_id']}",
        json={"value": "가명이가 다솜이와 개미를 관찰한다", "expected_revision": plan["revision"]},
    )
    assert edited.status_code == 200, edited.json()
    sent = []

    class Spy(RequestAwareMonthlyLlm):
        def generate_cell(self, request):
            sent.append(request.user_content)
            return super().generate_cell(request)

    monkeypatch.setattr(monthly_router, "monthly_llm_provider", Spy)
    focus = next(s for s in plan["sections"] if s["section_key"] == "focus")["cells"][0]
    response = client.post(
        f"/api/plans/monthly/{plan['id']}/cells/{focus['item_id']}/regenerate",
        json={"expected_revision": edited.json()["revision"]},
    )

    assert response.status_code == 200, response.json()
    [prompt] = sent
    assert "개미를 관찰한다" in prompt  # 고친 칸은 맥락으로 실렸다
    assert "가명" not in prompt and "다솜" not in prompt


def test_주간_칸을_다시_만들면_교사가_고친_다른_칸의_아이_이름도_가명으로_나간다(
    db_session, teacher, monkeypatch
):
    # 주간 칸 재생성은 다른 칸 값을 current_plan 으로 싣는다.
    seed = weekly_api._seed(db_session, "가원", "a@example.com")
    teacher.center_id = seed["center"]
    _children(db_session, seed["class"])
    weekly_api._monthly(seed)
    plan = client.post(
        "/api/plans/weekly", json={"class_id": seed["class"], "week_id": weekly_api.WEEK}
    ).json()
    edited = weekly_api._put(plan, "event_schedule", "가명이 생일 잔치 · 다솜이 발표")
    assert edited.status_code == 200, edited.json()
    sent = []

    class Spy(RequestAwareWeeklyLlm):
        def generate_weekly(self, request):
            sent.append(request.user_content)
            return super().generate_weekly(request)

    monkeypatch.setattr(weekly_router, "_weekly_provider", Spy)
    response = weekly_api._regenerate(edited.json(), "goals")

    assert response.status_code == 200, response.json()
    [prompt] = sent
    assert "생일 잔치" in prompt  # 고친 칸은 맥락으로 실렸다
    assert "가명" not in prompt and "다솜" not in prompt


def _docx(rows) -> bytes:
    ns = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
    cells = "".join(
        "<w:tr>"
        + "".join(f"<w:tc><w:p><w:r><w:t>{t}</w:t></w:r></w:p></w:tc>" for t in row)
        + "</w:tr>"
        for row in rows
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as package:
        body = f"<w:document {ns}><w:body><w:tbl>{cells}</w:tbl></w:body></w:document>"
        package.writestr("word/document.xml", body)
    return buffer.getvalue()


def test_연간_가져오기_원문의_원_아이_이름을_가리고_주제는_원문_표기로_돌려준다(
    db_session, teacher, monkeypatch
):
    center = Center(
        name="가원", director_name="김원장", region_sido="강원특별자치도", region_sigungu="춘천시"
    )
    db_session.add(center)
    db_session.flush()
    klass = Class(
        center_id=center.id,
        name="햇살반",
        school_year=2026,
        age_min=3,
        age_max=4,
        teacher_name="선생",
    )
    db_session.add(klass)
    db_session.flush()
    teacher.center_id = center.id
    other = _children(db_session, klass.id)
    # 옆 반 김여름은 이름이 7월 주제 「여름」과 같다.
    # 가려서 보내고, 돌려줄 때는 「김여름」이 아니라 원문 그대로 「여름」이다.
    db_session.add(Child(class_id=other, name="김여름", code="새봄"))
    db_session.flush()
    sent = {}

    def fake(system, user, **kwargs):
        sent["source"] = json.loads(user)["source"]
        return annual_extract._mock_answer(sent["source"])

    monkeypatch.setattr(settings, "llm_mode", "real")
    monkeypatch.setattr(annual_extract, "complete_json", fake)
    data = _docx([["3월", "가명이와 다솜이 친구"], ["7월", "여름"]])
    response = client.post(
        "/api/plans/annual/import/extract",
        data={"class_id": str(klass.id)},
        files={"file": ("연간.docx", data, "application/octet-stream")},
    )

    assert response.status_code == 200, response.text
    for name in ("가명", "다솜", "여름"):
        assert name not in sent["source"]
    themes = {m["month"]: m["theme"] for m in response.json()["months"]}
    assert (themes[3], themes[7]) == ("가명이와 다솜이 친구", "여름")


def test_다른_반_아이와_가명이나_이름이_겹쳐도_에러_없이_다_가린다():
    # 옆 반 박가명은 우리 반 이가명과 「가명」이 겹친다 — 이미 가려지므로 표에 넣지 않는다.
    # 옆 반 최다솜은 가명이 우리 반 아이와 같다 — 이번 호출에서만 새로 뽑는다.
    text = "가명이 · 박가명 · 다솜이"
    table = table_for_text(
        load_pool(),
        [("이가명", "도담", None)],
        [("박가명", "새롬", None), ("최다솜", "도담", None)],
        text,
    )

    assert set(table.restoring.values()) == {"이가명", "최다솜"}
    assert table.masking["가명"] == "도담" and table.masking["다솜"] != "도담"
    masked = mask(text, table)
    assert "가명" not in masked and "다솜" not in masked
    assert table_for_text(load_pool(), [("이가명", "도담", None)], [], "공룡 놀이") is None


def test_연간_메모_답은_메모에_적힌_표기로_돌아온다():
    # 다른 반 「김하늘」의 「하늘」이 메모 낱말과 겹쳐 가려져도
    # 소주제에 「김하늘」이 생기지 않는다.
    from app.features.plans.memo_privacy import unmask_text

    table = table_for_text(load_pool(), [], [("김하늘", "하람", None)], "하늘 관찰 놀이")
    code = table.masking["하늘"]
    assert unmask_text(f"{code} 관찰", table, "하늘 관찰 놀이") == "하늘 관찰"
    assert unmask_text("봄 소풍", None, "하늘 관찰 놀이") == "봄 소풍"
