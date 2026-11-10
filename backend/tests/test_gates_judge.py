"""shared/gates/judge.py v3 — 때 대조(모델 없음)와 답 읽기. DB · jev 를 쓰지 않는다 (ADR-071)."""

from datetime import date

import pytest

from app.shared.gates import judge as J

MON, WED, FRI = date(2026, 11, 2), date(2026, 11, 4), date(2026, 11, 6)
WEEK = [J.Source(10, MON, "가"), J.Source(11, WED, "나"), J.Source(12, FRI, "다")]
DAY = [
    J.Source(20, MON, "[등원 08:50~09:10] 가"),
    J.Source(21, MON, "[점심 11:30~12:10] 나"),
    J.Source(22, MON, "[바깥놀이 14:00~14:40] 다"),
]


@pytest.mark.parametrize(
    ("sentence", "gap"),
    [
        ("공을 굴리고 이틀 뒤에 다시 굴렸다.", 2),
        ("이튿날 다시 굴렸다.", 1),
        ("3일 만에 굴렸다.", 3),
    ],
)
def test_day_gap_is_read(sentence, gap):
    assert J.time_claim(sentence, WEEK).gap == gap


def test_future_and_plain_sentences_have_no_claim():
    assert J.time_claim("다음 주 화요일에 공을 굴려 보겠다.", WEEK) is None
    assert J.time_claim("공을 굴리는 놀이에 관심을 보였다.", WEEK) is None


def test_wrong_day_gap_points_at_the_later_record():
    claim = J.time_claim("공을 굴리고 이틀 뒤에 다시 굴렸다.", WEEK)
    assert J.time_conflict(claim, WEEK[2], WEEK[0], WEEK) is WEEK[2]  # 월 → 금은 나흘
    assert J.time_conflict(claim, WEEK[1], WEEK[0], WEEK) is None  # 월 → 수는 이틀


def test_first_record_is_the_earliest_whatever_the_activity():
    claim = J.time_claim("첫 기록 나흘 뒤에 다시 굴렸다.", WEEK)
    assert not claim.needs_anchor
    assert J.time_conflict(claim, WEEK[2], None, WEEK) is None
    assert J.time_conflict(claim, WEEK[1], None, WEEK) is WEEK[1]


def test_weekday_is_checked_against_the_record_date():
    claim = J.time_claim("화요일에 공을 굴렸다.", WEEK)
    assert J.time_conflict(claim, WEEK[0], None, WEEK) is WEEK[0]  # 11/2 는 월요일
    # 하루치 기록(일일)은 기록을 못 골라도 날짜가 하나라 셀 수 있다.
    assert J.time_conflict(J.time_claim("월요일에 놀았다.", DAY), None, None, DAY) is None
    assert J.time_conflict(J.time_claim("수요일에 놀았다.", DAY), None, None, DAY) is DAY[0]


def test_part_of_day_and_routine_order_use_the_routine_times():
    after_lunch = J.time_claim("점심 뒤에 모래를 팠다.", DAY)
    assert after_lunch.routine == ("점심", "뒤")
    assert J.time_conflict(after_lunch, DAY[0], None, DAY) is DAY[0]  # 등원은 점심 전
    assert J.time_conflict(after_lunch, DAY[2], None, DAY) is None
    morning = J.time_claim("오전에 모래를 팠다.", DAY)
    assert J.time_conflict(morning, DAY[2], None, DAY) is DAY[2]
    assert J.time_conflict(morning, DAY[0], None, DAY) is None


def test_record_with_several_routines_is_not_timed():
    # 주간 기록 한 줄에 일과가 여럿이면 그 일이 어느 때인지 모른다 — 말하지 않는다.
    mixed = J.Source(30, MON, "[놀이 09:00~10:00] 가\n[귀가 16:00~16:20] 나")
    claim = J.time_claim("오후에 놀았다.", [mixed])
    assert J.time_conflict(claim, mixed, None, [mixed]) is None


def _clear(questions, picks=None):
    out = {}
    for name, q in questions.items():
        if q["type"] == "noul":
            out[name] = {"noul": 0.95 if name == "지원.구체" else 0.02}
        elif name.endswith(".대조"):
            probs = {J.CONFLICT: 0.01, J.SAME: 0.97, J.NEW_FACT: 0.01, J.INTERPRETATION: 0.01}
            out[name] = {"choice": J.SAME, "probabilities": probs}
        else:
            out[name] = {"choice": (picks or {}).get(name.split(".")[1], "없음")}
    return out


def test_judge_flags_a_wrong_day_count_jev_called_same():
    asked = []

    def decide(state, questions):
        asked.append(questions)
        return _clear(questions, {"때": "r3", "기준": "r1"})

    bodies = {
        "해석": "공을 굴리고 이틀 뒤에 다시 굴렸다.",
        "지원": "내일 공을 하나 더 꺼내 두겠다.",
    }
    issues = J.judge("weeklyLog", "주간 보육일지", bodies, WEEK, decide)
    assert [(i.code, i.source_id) for i in issues] == [("CONTRADICTS_SOURCE", 12)]
    # 해석 문장에만 「어느 기록인가」를 묻는다. 지원 칸은 계획이라 묻지 않는다.
    assert {"s1.때", "s1.기준"} <= set(asked[0]) and "s2.때" not in asked[0]


def test_every_question_names_its_sentence():
    text = "공을 굴리고 이틀 뒤에 다시 굴렸다."
    claim = J.time_claim(text, WEEK)
    _state, questions = J.build_questions("관찰일지", [("해석", text)], {"r1": "가"}, [claim])
    assert all(text in q["instructions"] for q in questions.values())
    assert not any("{" in q["instructions"] for q in questions.values())


def test_change_needs_a_higher_bar_than_other_flags():
    sentences = [("해석", "공을 전보다 멀리 굴렸다.")]
    _state, questions = J.build_questions("관찰일지", sentences, {"r1": "가"})
    answers = _clear(questions)
    answers["s1.변화"]["noul"] = 0.7
    assert J.read_issues(sentences, answers, {"r1": 1}, None) == []
    answers["s1.변화"]["noul"] = 0.85
    assert [i.code for i in J.read_issues(sentences, answers, {"r1": 1}, None)] == [
        "UNSUPPORTED_CHANGE"
    ]


def _conflicting(questions):
    answers = _clear(questions, {"근거": "r1"})
    for name in answers:
        if name.endswith(".대조"):
            answers[name] = {
                "choice": J.CONFLICT,
                "probabilities": {
                    J.CONFLICT: 0.9,
                    J.SAME: 0.05,
                    J.NEW_FACT: 0.03,
                    J.INTERPRETATION: 0.02,
                },
            }
    return answers


def test_new_fact_is_still_read_when_the_sentence_also_conflicts():
    """v4 — 대조가 「어긋남」을 고르면 「새 사실」 확률은 낮다. 덧붙임 답으로 따로 본다."""
    sentences = [("해석", "공 다섯 개를 넣고 손뼉을 쳤다.")]
    _state, questions = J.build_questions("관찰일지", sentences, {"r1": "공 두 개를 넣었다"})
    answers = _conflicting(questions)
    answers["s1.덧붙임"]["noul"] = 0.8
    codes = [i.code for i in J.read_issues(sentences, answers, {"r1": 1}, None)]
    assert codes == ["CONTRADICTS_SOURCE", "UNSUPPORTED_FACT"]
    answers["s1.덧붙임"]["noul"] = 0.2
    assert [i.code for i in J.read_issues(sentences, answers, {"r1": 1}, None)] == [
        "CONTRADICTS_SOURCE"
    ]


def test_added_fact_question_is_only_for_interpretation_and_support_conflict_reads_fine():
    sentences = [("해석", "공을 넣었다."), ("지원", "다음에는 공 세 개를 넣어 보겠다.")]
    _state, questions = J.build_questions("관찰일지", sentences, {"r1": "공을 넣었다"})
    assert "s1.덧붙임" in questions and "s2.덧붙임" not in questions
    # 지원 문장에 어긋남이 떠도 없는 덧붙임 답을 찾다가 깨지면 안 된다(500 이 된다).
    codes = [
        (i.heading, i.code)
        for i in J.read_issues(sentences, _conflicting(questions), {"r1": 1}, None)
    ]
    assert ("지원", "CONTRADICTS_SOURCE") in codes and ("지원", "UNSUPPORTED_FACT") not in codes


def test_compared_or_several_weekdays_are_only_checked_to_exist():
    """v5 — 「월요일과 견주면」의 월요일 · 한 문장의 여러 요일은 고른 기록과 견주지 않는다."""
    compared = J.time_claim("월요일과 견주면 금요일에는 공을 멀리 굴렸다.", WEEK)
    assert compared.weekday is None and compared.any_weekdays == {0, 4}
    assert J.time_conflict(compared, WEEK[1], None, WEEK) is None
    alone = J.time_claim("월요일과 견주면 공을 멀리 굴렸다.", WEEK)
    assert alone.weekday is None and J.time_conflict(alone, WEEK[2], None, WEEK) is None
    several = J.time_claim("월요일에는 공을 굴렸고 수요일에는 공을 던졌다.", WEEK)
    assert several.weekday is None and several.any_weekdays == {0, 2}
    assert J.time_conflict(several, WEEK[2], None, WEEK) is None
    wrong = J.time_claim("화요일에는 공을 굴렸고 수요일에는 공을 던졌다.", WEEK)
    assert J.time_conflict(wrong, WEEK[1], None, WEEK) is WEEK[1]  # 화요일 기록이 없다
    days = J.time_claim("11월 2일과 4일에 공을 굴렸다.", WEEK)
    assert days.day is None and J.time_conflict(days, WEEK[2], None, WEEK) is None


def test_conflict_without_a_record_is_not_flagged():
    """v5 — 부딪히는 기록을 못 고른 「어긋남」은 띄우지 않는다(어느 기록인지 보여 줄 수 없다)."""
    sentences = [("해석", "공을 굴렸다.")]
    _state, questions = J.build_questions("관찰일지", sentences, {"r1": "공을 굴렸다"})
    answers = _conflicting(questions)
    assert [i.code for i in J.read_issues(sentences, answers, {"r1": 1}, None)] == [
        "CONTRADICTS_SOURCE"
    ]
    answers["s1.근거"]["choice"] = "없음"
    assert J.read_issues(sentences, answers, {"r1": 1}, None) == []


def test_several_weekdays_point_at_the_record_jev_found_conflicting():
    text = "화요일에는 공을 굴렸고 수요일에는 공을 던졌다."
    claim = J.time_claim(text, WEEK)
    sentences = [("해석", text)]
    records = {"r1": "가", "r2": "나", "r3": "다"}
    _state, questions = J.build_questions("주간 보육일지", sentences, records, [claim])
    answers = _clear(questions, {"때": "r1", "근거": "r2"})
    sources = dict(zip(records, WEEK, strict=True))
    ids = {key: src.source_id for key, src in sources.items()}
    issues = J.read_issues(sentences, answers, ids, None, "weeklyLog", [claim], sources)
    assert [(i.code, i.source_id) for i in issues] == [("CONTRADICTS_SOURCE", 11)]
