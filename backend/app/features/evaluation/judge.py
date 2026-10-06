"""평가제 기간과 4-1 · 4-2 판정 (api-spec §12 · ADR-022).

LLM · DB 없이 받은 사실만 센다. 조회에서 확정 문서 · 올해 대상만 넣는다.
"""

from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from app.shared.school_year import KST

SUPPORTED = "SUPPORTED"
INSUFFICIENT = "INSUFFICIENT"
NONE = "NONE"


def today_kst(now: datetime) -> date:
    """요청에서 now 를 한 번 얻어 이 값과 school_year_of(now) 를 만든다. 자정 오차를 막는다."""
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("시각대 없는 datetime 은 평가제 기준일을 정할 수 없다")
    return now.astimezone(KST).date()


@dataclass(frozen=True)
class Window:
    start: date
    end: date

    def __post_init__(self) -> None:
        # 뒤집힌 기간은 평일이 0개라, 계획안만 있는 반이 「충족」이 된다.
        if self.start > self.end:
            raise ValueError(f"기간이 뒤집혔다: {self.start} > {self.end}")

    def contains(self, day: date) -> bool:
        return self.start <= day <= self.end

    def months(self) -> tuple[tuple[int, int], ...]:
        first = self.start.year * 12 + self.start.month - 1
        last = self.end.year * 12 + self.end.month - 1
        return tuple((month // 12, month % 12 + 1) for month in range(first, last + 1))

    def weekdays(self) -> tuple[date, ...]:
        # ponytail: 공휴일 · 방학을 빼지 않는다 — 달력 자료가 없다(§12).
        #           그 주가 있으면 실제보다 부족으로 보인다.
        #           backend/resources/calendars/ 에 달력이 생기면 여기서 뺀다.
        days = (
            self.start + timedelta(days=offset)
            for offset in range((self.end - self.start).days + 1)
        )
        return tuple(day for day in days if day.weekday() < 5)


def previous_month_start_window(today: date) -> Window:
    first = (today.replace(day=1) - timedelta(days=1)).replace(day=1)
    return Window(first, today - timedelta(days=1))


def twelve_months_start_window(today: date) -> Window:
    return Window(today.replace(year=today.year - 1, day=1), today - timedelta(days=1))


def window_for(kind: str, today: date) -> Window:
    factories = {
        "PREVIOUS_MONTH_START": previous_month_start_window,
        "TWELVE_MONTHS_START": twelve_months_start_window,
    }
    if kind not in factories:
        raise ValueError(f"알 수 없는 평가제 기간이다: {kind}")
    return factories[kind](today)


@dataclass(frozen=True)
class PlanFact:
    plan_id: int
    class_id: int
    year: int
    month: int


@dataclass(frozen=True)
class DailyLogFact:
    document_id: int
    class_id: int
    day: date


@dataclass(frozen=True)
class AssessmentFact:
    document_id: int
    child_id: int
    end_date: date


@dataclass(frozen=True)
class Ratio:
    met: int
    total: int


@dataclass(frozen=True)
class AutoResult:
    verdict: str
    required: int | None
    count: int
    children: Ratio | None
    classes: Ratio | None
    plan_ids: tuple[int, ...]
    document_ids: tuple[int, ...]
    period: Window


def _verdict(count: int, ratio: Ratio) -> str:
    if count == 0:
        return NONE
    return INSUFFICIENT if ratio.met < ratio.total else SUPPORTED


def judge_4_1(
    window: Window,
    class_ids: Iterable[int],
    plans: Iterable[PlanFact],
    daily_logs: Iterable[DailyLogFact],
    *,
    min_plans_per_class: int = 1,
) -> AutoResult:
    """반마다 계획안과 기간 안 모든 평일의 일지가 있는지 센다."""
    roster = set(class_ids)
    months = set(window.months())
    # 입력 유일성을 계약이 보장하지 않는다 — 같은 문서를 두 번 세면 거짓 충족. id 로 하나만 남긴다.
    plans = {p.plan_id: p for p in plans if p.class_id in roster and (p.year, p.month) in months}
    daily_logs = {
        log.document_id: log
        for log in daily_logs
        if log.class_id in roster and window.contains(log.day)
    }
    plans, daily_logs = list(plans.values()), list(daily_logs.values())
    plan_counts = Counter(plan.class_id for plan in plans)
    log_days: dict[int, set[date]] = defaultdict(set)
    for log in daily_logs:
        log_days[log.class_id].add(log.day)
    weekdays = set(window.weekdays())
    met = sum(plan_counts[c] >= min_plans_per_class and weekdays <= log_days[c] for c in roster)
    ratio = Ratio(met, len(roster))
    plan_ids = tuple(sorted(plan.plan_id for plan in plans))
    document_ids = tuple(sorted(log.document_id for log in daily_logs))
    count = len(plan_ids) + len(document_ids)
    return AutoResult(
        verdict=_verdict(count, ratio),
        required=None,
        count=count,
        children=None,
        classes=ratio,
        plan_ids=plan_ids,
        document_ids=document_ids,
        period=window,
    )


def judge_4_2(
    window: Window,
    child_ids: Iterable[int],
    assessments: Iterable[AssessmentFact],
    *,
    min_per_child: int = 2,
) -> AutoResult:
    """아동마다 기간 안 평가 건수가 최소 기준 이상인지 센다."""
    roster = set(child_ids)
    # 입력 유일성을 계약이 보장하지 않는다 — 같은 문서를 두 번 세면 거짓 충족. id 로 하나만 남긴다.
    assessments = {
        a.document_id: a
        for a in assessments
        if a.child_id in roster and window.contains(a.end_date)
    }.values()
    counts = Counter(assessment.child_id for assessment in assessments)
    ratio = Ratio(sum(counts[child] >= min_per_child for child in roster), len(roster))
    document_ids = tuple(sorted(assessment.document_id for assessment in assessments))
    count = len(document_ids)
    return AutoResult(
        verdict=_verdict(count, ratio),
        required=min_per_child,
        count=count,
        children=ratio,
        classes=None,
        plan_ids=(),
        document_ids=document_ids,
        period=window,
    )
