"use client";

/**
 * 왼쪽 달력 — 어느 날을 적을지 고른다.
 *
 * 날짜 칸(`<input type="date">`) 하나로는 「지난 금요일」을 찾으려면 달력을 띄워 두 번
 * 눌러야 했다. 교사는 밀린 며칠을 몰아 적는다. 그래서 달을 펴 두고 바로 누르게 한다.
 *
 * 날짜 밑의 점은 **그날 남은 것**이다. 보라는 일과 기록, 초록은 보육일지다. 빈 날을
 * 찾으려고 하루씩 눌러 볼 필요가 없다.
 *
 * 앞날은 누르지 못한다 — 아직 하지 않은 일과를 적을 수는 없다.
 */

import { ws } from "./WorkspaceUI";

const WEEK = ["일", "월", "화", "수", "목", "금", "토"];
const MONTHS = [
  "January",
  "February",
  "March",
  "April",
  "May",
  "June",
  "July",
  "August",
  "September",
  "October",
  "November",
  "December",
];

/** `YYYY-MM-DD` 는 시간대가 없다. UTC 로만 다뤄 하루가 밀리지 않게 한다. */
const at = (date: string) => new Date(`${date}T00:00:00Z`);
const iso = (value: Date) => value.toISOString().slice(0, 10);

/** 그 달 1일부터 말일까지. 앞 빈 칸은 첫날의 요일만큼 비워 둔다. */
function monthDays(month: string) {
  const first = at(`${month}-01`);
  const days: string[] = [];
  for (
    let day = new Date(first);
    iso(day).slice(0, 7) === month;
    day.setUTCDate(day.getUTCDate() + 1)
  )
    days.push(iso(day));
  return { blanks: first.getUTCDay(), days };
}

/** 달을 `step` 만큼 옮긴다. `"2026-01"` 에서 -1 이면 `"2025-12"` 다. */
function shift(month: string, step: number) {
  const day = at(`${month}-01`);
  day.setUTCMonth(day.getUTCMonth() + step);
  return iso(day).slice(0, 7);
}

/** 그 달의 첫날과 마지막 날. 달력에 찍을 점을 한 번에 물을 때 쓴다. */
export const monthRange = (month: string) => {
  const days = monthDays(month).days;
  return { from: days[0], to: days[days.length - 1] };
};

/** `2026-11-04` → `{ day: "11월 4일", dow: "수요일" }` */
export function koreanDay(date: string) {
  const day = at(date);
  return {
    day: `${day.getUTCMonth() + 1}월 ${day.getUTCDate()}일`,
    dow: `${WEEK[day.getUTCDay()]}요일`,
  };
}

/** 그날 남은 것. 점 두 개는 색이 다르다 — 같은 색이면 몇 개인지만 보인다. */
export interface DayMarks {
  routines: string[];
  logs: string[];
}

export default function RoutineCalendar({
  date,
  month,
  today,
  marks,
  disabled,
  onMonth,
  onPick,
}: {
  /** 고른 날 (`YYYY-MM-DD`) */
  date: string;
  /** 펴 놓은 달 (`YYYY-MM`) */
  month: string;
  today: string;
  marks: DayMarks;
  disabled: boolean;
  onMonth: (month: string) => void;
  onPick: (date: string) => void;
}) {
  const { blanks, days } = monthDays(month);
  const [year, number] = month.split("-");

  return (
    <div className={ws.calendar}>
      <div className={ws.calendarHead}>
        <button
          type="button"
          className={ws.calendarStep}
          aria-label="지난 달"
          onClick={() => onMonth(shift(month, -1))}
        >
          ‹
        </button>
        <strong className={ws.calendarMonth}>
          {MONTHS[Number(number) - 1]} <span>{year}</span>
        </strong>
        <button
          type="button"
          className={ws.calendarStep}
          aria-label="다음 달"
          onClick={() => onMonth(shift(month, 1))}
        >
          ›
        </button>
      </div>

      <div className={ws.calendarGrid} role="grid" aria-label={`${year}년 ${Number(number)}월`}>
        {WEEK.map((name, index) => (
          <span key={name} className={ws.calendarWeekday} data-day={index}>
            {name}
          </span>
        ))}
        {Array.from({ length: blanks }, (_, i) => (
          <span key={`blank:${i}`} aria-hidden="true" />
        ))}
        {days.map((day) => {
          const routine = marks.routines.includes(day);
          const log = marks.logs.includes(day);
          // 점을 보고 눌렀는데 아무 말이 없으면 무슨 점인지 끝까지 모른다.
          const kept = [routine && "일과 기록", log && "보육일지"].filter(Boolean).join(" · ");
          return (
            <button
              key={day}
              type="button"
              className={ws.calendarDay}
              data-day={at(day).getUTCDay()}
              data-picked={day === date || undefined}
              data-today={day === today || undefined}
              // 앞날은 적을 것이 없다. 흐리게만 두면 왜 안 눌리는지 모른다.
              disabled={disabled || day > today}
              title={day > today ? "아직 오지 않은 날이에요." : kept || undefined}
              aria-label={kept ? `${at(day).getUTCDate()}일 · ${kept}` : undefined}
              aria-pressed={day === date}
              onClick={() => onPick(day)}
            >
              {at(day).getUTCDate()}
              {(routine || log) && (
                <span className={ws.calendarDots} aria-hidden="true">
                  {routine && <i className={ws.calendarDotRoutine} />}
                  {log && <i className={ws.calendarDotLog} />}
                </span>
              )}
            </button>
          );
        })}
      </div>

      <p className={ws.calendarKey}>
        <span>
          <i className={ws.calendarDotRoutine} /> 일과
        </span>
        <span>
          <i className={ws.calendarDotLog} /> 보육일지
        </span>
      </p>
    </div>
  );
}
