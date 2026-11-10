"use client";

/**
 * 왼쪽 달력 — 어느 날을 적을지 고른다.
 *
 * 날짜 칸(`<input type="date">`) 하나로는 「지난 금요일」을 찾으려면 달력을 띄워 두 번
 * 눌러야 했다. 교사는 밀린 며칠을 몰아 적는다. 그래서 달을 펴 두고 바로 누르게 한다.
 *
 * 날짜 밑의 점은 **그날 적은 일과가 있다**는 뜻이다. 빈 날을 찾으려고 하루씩 눌러
 * 볼 필요가 없다. 점은 한 가지만 찍는다 — 색이 둘이면 범례를 달아야 하고, 범례를
 * 읽어야 아는 표시는 달력에 둘 것이 아니다.
 *
 * 앞날은 누르지 못한다 — 아직 하지 않은 일과를 적을 수는 없다.
 */

import { useState } from "react";
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

export default function RoutineCalendar({
  date,
  month,
  today,
  marked,
  disabled,
  onMonth,
  onPick,
}: {
  /** 고른 날 (`YYYY-MM-DD`) */
  date: string;
  /** 펴 놓은 달 (`YYYY-MM`) */
  month: string;
  today: string;
  /** 일과를 적어 둔 날들 (`YYYY-MM-DD`) */
  marked: string[];
  disabled: boolean;
  onMonth: (month: string) => void;
  onPick: (date: string) => void;
}) {
  const { blanks, days } = monthDays(month);
  const [year, number] = month.split("-");
  /**
   * 휴대폰(1024px 아래)에서는 고른 날이 든 한 주만 편다 — 달 한 장이 첫 화면 절반을 먹어
   * 정작 적을 칠판이 세 화면 아래로 밀렸다. 머리줄 오른쪽 끝 「한 달 ▾ / 한 주 ▴」로 접고 편다.
   * 접고 펴는 것은 CSS 가 휴대폰에서만 따른다.
   * 데스크톱은 이 값과 상관없이 늘 달 한 장이다.
   */
  const [monthOpen, setMonthOpen] = useState(false);
  // 고른 날이 이 달 몇째 줄인가. 다른 달을 펴 놓았으면 -1 — 그때는 접을 때 고른 날의 달로 돌아간다.
  const pickedAt = days.indexOf(date);
  const week = pickedAt < 0 ? -1 : Math.floor((blanks + pickedAt) / 7);
  const offWeek = (cell: number) => Math.floor(cell / 7) !== week || undefined;
  const toggleMonth = () => {
    if (monthOpen && pickedAt < 0) onMonth(date.slice(0, 7));
    setMonthOpen(!monthOpen);
  };

  return (
    <div className={ws.calendar} data-week={!monthOpen || undefined}>
      <div className={ws.calendarHead}>
        <button
          type="button"
          className={`${ws.calendarStep} tap44`}
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
          className={`${ws.calendarStep} tap44`}
          aria-label="다음 달"
          onClick={() => onMonth(shift(month, 1))}
        >
          ›
        </button>
        {/* 휴대폰에서만 보인다 — 머리줄 오른쪽 끝. 이름에 화면 글자(한 달 · 한 주)를 그대로 담는다. */}
        <button
          type="button"
          className={`${ws.calendarToggle} tap44`}
          aria-expanded={monthOpen}
          aria-label={monthOpen ? "한 주만 보기" : "한 달 모두 보기"}
          onClick={toggleMonth}
        >
          {monthOpen ? "한 주" : "한 달"}
        </button>
      </div>

      <div className={ws.calendarGrid} role="grid" aria-label={`${year}년 ${Number(number)}월`}>
        {WEEK.map((name, index) => (
          <span key={name} className={ws.calendarWeekday} data-day={index}>
            {name}
          </span>
        ))}
        {Array.from({ length: blanks }, (_, i) => (
          <span key={`blank:${i}`} aria-hidden="true" data-off-week={offWeek(i)} />
        ))}
        {days.map((day, i) => {
          const kept = marked.includes(day);
          return (
            <button
              key={day}
              type="button"
              className={`${ws.calendarDay} tap44`}
              data-day={at(day).getUTCDay()}
              data-picked={day === date || undefined}
              data-today={day === today || undefined}
              data-off-week={offWeek(blanks + i)}
              // 앞날은 적을 것이 없다. 흐리게만 두면 왜 안 눌리는지 모른다.
              disabled={disabled || day > today}
              title={day > today ? "아직 오지 않은 날이에요." : kept ? "일과를 적은 날" : undefined}
              aria-label={kept ? `${at(day).getUTCDate()}일, 일과를 적은 날` : undefined}
              aria-pressed={day === date}
              onClick={() => {
                setMonthOpen(false);
                onPick(day);
              }}
            >
              {at(day).getUTCDate()}
              {kept && <i className={ws.calendarDot} aria-hidden="true" />}
            </button>
          );
        })}
      </div>
    </div>
  );
}
