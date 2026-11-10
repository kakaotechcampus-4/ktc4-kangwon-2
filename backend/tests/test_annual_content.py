"""연간 소주제의 문서 단위 생성 계약. 실제 모델 대신 고정 전송 응답을 쓴다."""

import json

import pytest

from app.features.plans.annual_content import parse_subthemes, subthemes_for_month
from app.shared.llm import LlmFailed

MONTHS = (3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 1, 2)


@pytest.mark.parametrize(
    "stored", [{"9": "연간 소주제"}, {"9": [None]}, [], {"9": {"value": "글"}}]
)
def test_corrupt_parent_sidecar_is_not_sent_as_context(stored):
    with pytest.raises(ValueError, match="snapshot"):
        subthemes_for_month(stored, 9)


def test_parent_sidecar_uses_only_the_target_month_and_supports_old_plans():
    assert subthemes_for_month({"9": ["교사 확정값"], "10": ["다른 달"]}, 9) == ("교사 확정값",)
    assert subthemes_for_month(None, 9) == subthemes_for_month({}, 9) == ()
    edited = ["", " ", "긴 문장" * 100] + [f"교사 소주제 {i}" for i in range(8)]
    assert subthemes_for_month({"9": edited}, 9) == tuple(edited)


@pytest.mark.parametrize("teacher_named", [False, True])
def test_annual_subthemes_require_teacher_input_for_a_specific_venue(monkeypatch, teacher_named):
    from types import SimpleNamespace

    from ssuksak.planning.domain.year_month import YearMonth

    from app.features.plans import annual_content

    plan = SimpleNamespace(
        target_ages=frozenset({3}),
        periods=tuple(
            SimpleNamespace(
                period=YearMonth(2026 if m >= 3 else 2027, m),
                theme=SimpleNamespace(value="우리 동네"),
            )
            for m in MONTHS
        ),
    )

    def complete(system, user, **kwargs):
        body = json.loads(user)
        result = {
            "months": [
                {
                    "month": m["month"],
                    "sub_themes": ["배산유아숲터 숲 체험"]
                    + [f"동네 경험 {i}" for i in range(m["week_count"] - 1)],
                }
                for m in body["months"]
            ]
        }
        if teacher_named:
            result.update(memo_applied=[], memo_skipped=[])
        return json.dumps(result)

    monkeypatch.setattr(annual_content, "is_mock", lambda: False)
    monkeypatch.setattr(annual_content, "complete_json", complete)
    memo = "배산유아숲터에서 숲 체험을 할 예정입니다." if teacher_named else ""
    if teacher_named:
        result, _, _ = annual_content.generate_subthemes_with_memo(plan, memo)
        assert result["3"][0] == "배산유아숲터 숲 체험"
    else:
        with pytest.raises(LlmFailed, match="지역·시설명"):
            annual_content.generate_subthemes(plan)


def answer():
    return {
        "months": [{"month": m, "sub_themes": ["함께 알아보기", "놀이로 만나기"]} for m in MONTHS]
    }


def test_teacher_subtheme_provenance_survives_json_and_ignores_noop_or_reorder():
    from datetime import UTC, datetime

    from ssuksak.adapters.deterministic import DeterministicIdGenerator, FixedClock
    from ssuksak.adapters.in_memory_plan_repository import InMemoryPlanRepository
    from ssuksak.planning.application.import_yearly_plan import (
        ImportYearlyPlan,
        ImportYearlyPlanCommand,
    )
    from ssuksak.planning.domain.identifiers import ActorId
    from ssuksak.planning.domain.provenance import GenerationMethod
    from ssuksak.planning.domain.yearly_plan import YearlyPlan

    from app.features.plans.annual_content import with_teacher_subthemes
    from app.features.plans.codec import from_jsonable, to_jsonable

    plan = ImportYearlyPlan(
        plan_repository=InMemoryPlanRepository(),
        clock=FixedClock(datetime(2026, 11, 7, tzinfo=UTC)),
        id_generator=DeterministicIdGenerator(),
    ).execute(
        ImportYearlyPlanCommand(
            2026,
            "test_class",
            frozenset({3}),
            GenerationMethod.MANUAL,
            tuple((m, "우리 동네") for m in MONTHS),
            ActorId("test_teacher"),
        )
    )
    original = ["한강공원 산책", "꽃 살펴보기"]
    assert with_teacher_subthemes(
        plan, 3, original, list(reversed(original))
    ).teacher_subthemes == ((3, ()),)
    edited = with_teacher_subthemes(plan, 3, original, ["부산시민공원 산책", "꽃 살펴보기"])
    restored = from_jsonable(YearlyPlan, to_jsonable(edited))
    assert restored.teacher_subthemes == ((3, ("부산시민공원 산책",)),)
    assert with_teacher_subthemes(
        restored, 3, ["부산시민공원 산책"], ["꽃 살펴보기"]
    ).teacher_subthemes == ((3, ("꽃 살펴보기",)),)
    legacy = to_jsonable(plan)
    legacy.pop("teacher_subthemes")
    assert from_jsonable(YearlyPlan, legacy).teacher_subthemes == ()


def test_12개월_순서대로_소주제가_검증된다():
    assert list(parse_subthemes(json.dumps(answer()), MONTHS)) == [str(m) for m in MONTHS]


@pytest.mark.parametrize(
    "broken", ["missing", "duplicate", "extra", "blank", "type", "field", "too_many"]
)
def test_잘못된_생성은_조용히_채우지_않는다(broken):
    data = answer()
    if broken == "missing":
        data["months"].pop()
    elif broken == "duplicate":
        data["months"][1]["month"] = 3
    elif broken == "extra":
        data["months"].append({"month": 13, "sub_themes": ["하나", "둘"]})
    elif broken == "blank":
        data["months"][0]["sub_themes"] = ["   ", "둘"]
    elif broken == "type":
        data["months"][0]["month"] = "3"
    elif broken == "field":
        data["months"][0]["safety_education"] = ["traffic_safety"]
    else:
        data["months"][0]["sub_themes"] *= 3
    with pytest.raises(LlmFailed):
        parse_subthemes(json.dumps(data), MONTHS)


def test_모든_달과_연령을_소주제_호출_한번에_보낸다(monkeypatch):
    from types import SimpleNamespace

    from ssuksak.planning.domain.year_month import YearMonth

    from app.features.plans import annual_content

    plan = SimpleNamespace(
        target_ages=frozenset({3, 4, 5}),
        periods=tuple(
            SimpleNamespace(
                period=YearMonth(2026 if month >= 3 else 2027, month),
                theme=SimpleNamespace(value=f"주제 {month}"),
            )
            for month in MONTHS
        ),
    )
    calls = []

    def complete(system, user, **kwargs):
        calls.append(json.loads(user))
        assert calls[-1]["prompt_version"] == "annual-subthemes-v4+teacher-venues-v2"
        assert "월 주제가 담은 주요 대상과 경험을 목록 전체에서 유지" in system
        return json.dumps(
            {
                "months": [
                    {
                        "month": m["month"],
                        "sub_themes": [f"예상 경험 {i}" for i in range(m["week_count"])],
                    }
                    for m in calls[-1]["months"]
                ]
            }
        )

    monkeypatch.setattr(annual_content, "is_mock", lambda: False)
    monkeypatch.setattr(annual_content, "complete_json", complete)
    result = annual_content.generate_subthemes(plan)
    assert len(result) == 12
    assert len(calls) == 1
    assert calls[0]["target_ages"] == [3, 4, 5]
    assert [month["month"] for month in calls[0]["months"]] == list(MONTHS)
    assert len(calls[0]["curriculum_context"]["contents"]) == 59
    assert {m["month"]: m["week_count"] for m in calls[0]["months"]}[9] == 5
    assert len(result["9"]) == 5 and len(result["10"]) == 4


def test_생성_소주제가_주차보다_적으면_성공으로_저장하지_않는다(monkeypatch):
    from types import SimpleNamespace

    from ssuksak.planning.domain.year_month import YearMonth

    from app.features.plans import annual_content

    plan = SimpleNamespace(
        target_ages=frozenset({3}),
        periods=tuple(
            SimpleNamespace(
                period=YearMonth(2026 if m >= 3 else 2027, m),
                theme=SimpleNamespace(value="월별 주제"),
            )
            for m in MONTHS
        ),
    )
    monkeypatch.setattr(annual_content, "is_mock", lambda: False)
    monkeypatch.setattr(
        annual_content, "complete_json", lambda *args, **kwargs: json.dumps(answer())
    )
    with pytest.raises(LlmFailed, match="주차 수"):
        annual_content.generate_subthemes(plan)


@pytest.mark.parametrize("count", [0, 1, 3, 6])
def test_count_repair_batches_only_wrong_months_and_preserves_memo(monkeypatch, count):
    from types import SimpleNamespace

    from ssuksak.planning.domain.year_month import YearMonth

    from app.features.plans import annual_content

    plan = SimpleNamespace(
        target_ages=frozenset({3, 4}),
        periods=tuple(
            SimpleNamespace(
                period=YearMonth(2026 if m >= 3 else 2027, m),
                theme=SimpleNamespace(value="월별 주제"),
            )
            for m in MONTHS
        ),
    )
    calls = []
    original = {}

    def complete(system, user, **kwargs):
        payload = json.loads(user)
        calls.append(payload)
        items = [
            {"month": m["month"], "sub_themes": [f"경험 {i}" for i in range(m["week_count"])]}
            for m in payload["months"]
        ]
        if len(calls) == 1:
            original.update({str(item["month"]): list(item["sub_themes"]) for item in items})
            for item in items:
                if item["month"] in (9, 10):
                    item["sub_themes"] = [f"다른 경험 {i}" for i in range(count)]
            return json.dumps(
                {
                    "months": items,
                    "memo_applied": ["3", "9"],
                    "memo_skipped": [
                        {"summary": "시간 요청은 반영하지 않았어요", "reason": "RULE_CONFLICT"}
                    ],
                },
                ensure_ascii=False,
            )
        assert [item["month"] for item in payload["months"]] == [9, 10]
        assert set(payload["previous_subthemes"]) == {"9", "10"}
        assert payload["prompt_version"] == annual_content.ANNUAL_SUBTHEMES_REPAIR_PROMPT_VERSION
        assert payload["teacher_memo"]["text"] == "요청 사항 예시"
        assert payload["memo_decision"]["applied"] == ["3", "9"]
        return json.dumps({"months": items}, ensure_ascii=False)

    monkeypatch.setattr(annual_content, "is_mock", lambda: False)
    monkeypatch.setattr(annual_content, "complete_json", complete)
    result, applied, notices = annual_content.generate_subthemes_with_memo(plan, "요청 사항 예시")
    assert len(calls) == 2
    assert result == original
    assert applied == frozenset({3, 9})
    assert len(notices) == 1 and notices[0].reason.value == "RULE_CONFLICT"


@pytest.mark.parametrize("fault", ["count", "extra_month", "venue"])
def test_count_repair_rejects_bad_second_answer_without_third_call(monkeypatch, fault):
    from types import SimpleNamespace

    from ssuksak.planning.domain.year_month import YearMonth

    from app.features.plans import annual_content

    plan = SimpleNamespace(
        target_ages=frozenset({3}),
        periods=tuple(
            SimpleNamespace(
                period=YearMonth(2026 if m >= 3 else 2027, m),
                theme=SimpleNamespace(value="월별 주제"),
            )
            for m in MONTHS
        ),
    )
    calls = []

    def complete(system, user, **kwargs):
        payload = json.loads(user)
        calls.append(payload)
        items = [
            {"month": m["month"], "sub_themes": [f"경험 {i}" for i in range(m["week_count"])]}
            for m in payload["months"]
        ]
        if len(calls) == 1 or fault == "count":
            items[0]["sub_themes"] = items[0]["sub_themes"][:2]
        elif fault == "extra_month":
            items.append({"month": 2, "sub_themes": ["다른 달", "추가 값"]})
        else:
            items[0]["sub_themes"][0] = "배산유아숲터 숲 체험"
        return json.dumps({"months": items}, ensure_ascii=False)

    monkeypatch.setattr(annual_content, "is_mock", lambda: False)
    monkeypatch.setattr(annual_content, "complete_json", complete)
    with pytest.raises(LlmFailed):
        annual_content.generate_subthemes(plan)
    assert len(calls) == 2
