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
