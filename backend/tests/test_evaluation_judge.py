"""평가제 기간 · 판정 함수 검증. DB 를 연결하지 않는다."""

from datetime import date, datetime, timedelta, tzinfo

import pytest

from app.features.evaluation.judge import (
    INSUFFICIENT,
    NONE,
    SUPPORTED,
    AssessmentFact,
    DailyLogFact,
    PlanFact,
    Ratio,
    Window,
    judge_4_1,
    judge_4_2,
    previous_month_start_window,
    today_kst,
    twelve_months_start_window,
    window_for,
)


@pytest.mark.parametrize(
    ("moment", "expected"),
    [
        ("2026-10-02T15:00:00+00:00", date(2026, 10, 3)),
        ("2026-10-02T14:59:59+00:00", date(2026, 10, 2)),
        ("2026-10-02T14:59:59Z", date(2026, 10, 2)),
    ],
)
def test_today_kst(moment, expected):
    assert today_kst(datetime.fromisoformat(moment)) == expected


def test_today_kst_rejects_naive():
    class NoOffset(tzinfo):
        def utcoffset(self, dt):
            return None

    for moment in (datetime(2026, 10, 3), datetime(2026, 10, 3, tzinfo=NoOffset())):
        with pytest.raises(ValueError, match="시각대 없는"):
            today_kst(moment)


# 평일 수는 calendar 모듈로 미리 따로 세어 둔 값이다 — 구현과 같은 방식으로 세면 같이 틀린다.
@pytest.mark.parametrize(
    ("today", "start", "end", "weekdays"),
    [
        (date(2026, 10, 3), date(2026, 9, 1), date(2026, 10, 2), 24),
        (date(2026, 10, 1), date(2026, 9, 1), date(2026, 9, 30), 22),
        (date(2026, 1, 15), date(2025, 12, 1), date(2026, 1, 14), 33),
        (date(2026, 1, 1), date(2025, 12, 1), date(2025, 12, 31), 23),
        (date(2026, 3, 1), date(2026, 2, 1), date(2026, 2, 28), 20),
        (date(2028, 3, 1), date(2028, 2, 1), date(2028, 2, 29), 21),
    ],
)
def test_previous_month_window(today, start, end, weekdays):
    window = previous_month_start_window(today)
    assert window == Window(start, end) == window_for("PREVIOUS_MONTH_START", today)
    assert window.contains(start) and window.contains(end)
    assert not window.contains(start - timedelta(days=1)) and not window.contains(today)
    assert len(window.weekdays()) == weekdays
    assert all(day.weekday() < 5 and window.contains(day) for day in window.weekdays())


@pytest.mark.parametrize(
    ("today", "expected"),
    [
        (date(2026, 10, 3), Window(date(2025, 10, 1), date(2026, 10, 2))),
        (date(2026, 10, 1), Window(date(2025, 10, 1), date(2026, 9, 30))),
        (date(2026, 1, 10), Window(date(2025, 1, 1), date(2026, 1, 9))),
        (date(2026, 1, 1), Window(date(2025, 1, 1), date(2025, 12, 31))),
        (date(2028, 2, 29), Window(date(2027, 2, 1), date(2028, 2, 28))),
        (date(2028, 3, 1), Window(date(2027, 3, 1), date(2028, 2, 29))),
    ],
)
def test_twelve_month_window(today, expected):
    assert twelve_months_start_window(today) == expected
    assert window_for("TWELVE_MONTHS_START", today) == expected


def test_months_and_unknown_window():
    assert previous_month_start_window(date(2026, 10, 1)).months() == ((2026, 9),)
    assert previous_month_start_window(date(2026, 10, 3)).months() == ((2026, 9), (2026, 10))
    assert previous_month_start_window(date(2026, 1, 15)).months() == ((2025, 12), (2026, 1))
    with pytest.raises(ValueError, match="알 수 없는"):
        window_for("UNKNOWN", date(2026, 10, 3))
    with pytest.raises(ValueError, match="뒤집혔다"):
        Window(date(2026, 10, 2), date(2026, 10, 1))


def test_weekdays_full_tuple():
    september = [date(2026, 9, day) for day in (28, 29, 30)]
    october = [date(2026, 10, day) for day in (1, 2, 5)]
    assert Window(date(2026, 9, 26), date(2026, 10, 5)).weekdays() == tuple(september + october)


def logs_for(window, class_id):
    return [
        DailyLogFact(class_id * 100 + n, class_id, day) for n, day in enumerate(window.weekdays())
    ]


@pytest.mark.parametrize("roster", [[], [1, 2]])
def test_4_1_no_facts(roster):
    result = judge_4_1(previous_month_start_window(date(2026, 10, 3)), roster, [], [])
    assert (result.verdict, result.count, result.classes) == (NONE, 0, Ratio(0, len(roster)))


@pytest.mark.parametrize("repetitions", [1, 2])
def test_4_1_all_classes_supported_and_threshold(repetitions):
    window = previous_month_start_window(date(2026, 10, 3))
    plans = [PlanFact(20, 1, 2026, 10), PlanFact(10, 2, 2026, 9)]
    logs = logs_for(window, 1) + logs_for(window, 2)
    result = judge_4_1(window, [1, 2, 1], plans * repetitions, reversed(logs * repetitions))
    assert (result.verdict, result.classes) == (SUPPORTED, Ratio(2, 2))
    assert result.required is None and result.children is None and result.period == window
    assert result.plan_ids == (10, 20)
    assert result.document_ids == tuple(sorted(log.document_id for log in logs))
    assert result.count == len(result.plan_ids) + len(result.document_ids)
    assert judge_4_1(
        window, [1, 2], plans * repetitions, logs * repetitions, min_plans_per_class=2
    ).classes == Ratio(0, 2)


def test_4_1_missing_day_with_weekend_and_duplicate_logs():
    window = previous_month_start_window(date(2026, 10, 3))
    logs = logs_for(window, 1)[1:] + logs_for(window, 2)
    logs += [DailyLogFact(999, 1, date(2026, 9, 5)), DailyLogFact(998, 1, logs[0].day)]
    result = judge_4_1(window, [1, 2], [PlanFact(1, 1, 2026, 9), PlanFact(2, 2, 2026, 9)], logs)
    assert (result.verdict, result.classes) == (INSUFFICIENT, Ratio(1, 2))
    assert result.document_ids == tuple(sorted(log.document_id for log in logs))
    assert result.count == 2 + len(logs)


@pytest.mark.parametrize(
    ("roster", "plans", "expected"),
    [([1], [], Ratio(0, 1)), ([1, 2], [PlanFact(1, 1, 2026, 9)], Ratio(1, 2))],
)
def test_4_1_logs_without_plan(roster, plans, expected):
    window = previous_month_start_window(date(2026, 10, 3))
    logs = [log for class_id in roster for log in logs_for(window, class_id)]
    result = judge_4_1(window, roster, plans, logs)
    assert (result.verdict, result.classes) == (INSUFFICIENT, expected)


def test_4_1_filters_roster_month_and_dates():
    window = previous_month_start_window(date(2026, 10, 1))
    plans = [PlanFact(1, 1, 2026, 10), PlanFact(2, 9, 2026, 9), PlanFact(3, 1, 2025, 9)]
    logs = [
        DailyLogFact(1, 9, window.start),
        DailyLogFact(2, 1, window.start - timedelta(days=1)),
        DailyLogFact(3, 1, date(2026, 10, 1)),
    ]
    result = judge_4_1(window, [1], plans, logs)
    assert (result.verdict, result.count, result.plan_ids, result.document_ids) == (NONE, 0, (), ())
    assert result.classes == Ratio(0, 1)
    empty = judge_4_1(window, [], [PlanFact(4, 1, 2026, 9)], logs_for(window, 1))
    assert (empty.verdict, empty.classes, empty.count) == (NONE, Ratio(0, 0), 0)


@pytest.mark.parametrize("roster", [[], [1, 2]])
def test_4_2_no_facts(roster):
    result = judge_4_2(twelve_months_start_window(date(2026, 10, 3)), roster, [])
    assert (result.verdict, result.count, result.children) == (NONE, 0, Ratio(0, len(roster)))


@pytest.mark.parametrize("repetitions", [1, 2])
def test_4_2_insufficient_evidence_and_threshold(repetitions):
    window = twelve_months_start_window(date(2026, 10, 3))
    assessments = [AssessmentFact(8, 1, window.end)] * repetitions
    result = judge_4_2(window, [1], assessments)
    assert (result.verdict, result.children) == (INSUFFICIENT, Ratio(0, 1))
    assert result.document_ids == (8,) and result.count == 1 and result.required == 2
    single = judge_4_2(window, [1], assessments, min_per_child=1)
    assert single.verdict == SUPPORTED and single.required == 1


def test_4_2_all_supported_and_two_of_three():
    window = twelve_months_start_window(date(2026, 10, 3))
    assessments = [
        AssessmentFact(4, 1, window.start),
        AssessmentFact(3, 1, window.end),
        AssessmentFact(2, 2, window.start),
        AssessmentFact(1, 2, window.end),
    ]
    result = judge_4_2(window, [1, 2, 1], assessments)
    assert (result.verdict, result.children) == (SUPPORTED, Ratio(2, 2))
    assert result.required == 2 and result.classes is None and result.plan_ids == ()
    assert result.period == window and result.document_ids == (1, 2, 3, 4) and result.count == 4
    partial = judge_4_2(window, [1, 2, 3], assessments + [AssessmentFact(5, 3, window.end)])
    assert (partial.verdict, partial.children) == (INSUFFICIENT, Ratio(2, 3))
    assert partial.document_ids == (1, 2, 3, 4, 5)


def test_4_2_filters_roster_and_dates():
    window = twelve_months_start_window(date(2026, 10, 3))
    assessments = [
        AssessmentFact(1, 9, window.start),
        AssessmentFact(2, 1, window.start - timedelta(days=1)),
        AssessmentFact(3, 1, window.end + timedelta(days=1)),
    ]
    result = judge_4_2(window, [1], assessments)
    assert (result.verdict, result.document_ids, result.count) == (NONE, (), 0)
    assert result.children == Ratio(0, 1)
    empty = judge_4_2(window, [], [AssessmentFact(4, 1, window.start)])
    assert (empty.verdict, empty.children, empty.count) == (NONE, Ratio(0, 0), 0)
