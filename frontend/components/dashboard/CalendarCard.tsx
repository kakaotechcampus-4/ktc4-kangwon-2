"use client";

import { useState } from "react";
import { Icon } from "@/components/app/icons";
import { calendarMarksFor, type Tone } from "@/lib/dashboard/mock";

const DOW = ["일", "월", "화", "수", "목", "금", "토"];
const MARK: Record<Tone, string> = { sage: "bg-sage-ink", mint: "bg-mint-strong", peach: "bg-peach-strong" };

/** 월간 달력 (UI만). 오늘 = Main 배경, 일정/기록 있는 날 = Point 컬러 dot */
export default function CalendarCard({ today = new Date() }: { today?: Date }) {
  const [ym, setYm] = useState({ y: today.getFullYear(), m: today.getMonth() });
  const move = (d: number) =>
    setYm(({ y, m }) => {
      const nm = m + d;
      return { y: y + Math.floor(nm / 12), m: ((nm % 12) + 12) % 12 };
    });

  const start = new Date(ym.y, ym.m, 1).getDay();
  const days = new Date(ym.y, ym.m + 1, 0).getDate();
  const prevDays = new Date(ym.y, ym.m, 0).getDate();
  const marks = calendarMarksFor(ym.y, ym.m);

  const cells: { n: number; out?: boolean }[] = [];
  for (let i = start - 1; i >= 0; i--) cells.push({ n: prevDays - i, out: true });
  for (let d = 1; d <= days; d++) cells.push({ n: d });
  let trailing = 1;
  while (cells.length % 7) cells.push({ n: trailing++, out: true });

  const isThisMonth = ym.y === today.getFullYear() && ym.m === today.getMonth();

  return (
    <section aria-label="달력">
      <div className="flex items-center justify-between">
        <button type="button" onClick={() => move(-1)} aria-label="이전 달" className="w-8 h-8 rounded-[10px] inline-flex items-center justify-center text-ink-soft hover:bg-cream hover:text-ink">
          <Icon name="chevronLeft" className="w-4 h-4" strokeWidth={1.8} />
        </button>
        <span className="font-mono text-[13px] font-medium text-ink">
          {ym.y}년 {ym.m + 1}월
        </span>
        <button type="button" onClick={() => move(1)} aria-label="다음 달" className="w-8 h-8 rounded-[10px] inline-flex items-center justify-center text-ink-soft hover:bg-cream hover:text-ink">
          <Icon name="chevron" className="w-4 h-4" strokeWidth={1.8} />
        </button>
      </div>
      <div className="grid grid-cols-7 gap-y-0.5 mt-2.5 font-mono tabular-nums">
        {DOW.map((d) => (
          <div key={d} className="text-center text-[10.5px] text-ink-soft pt-1 pb-2">{d}</div>
        ))}
        {cells.map((c, i) => {
          const isToday = !c.out && isThisMonth && c.n === today.getDate();
          const mark = !c.out ? marks[c.n] : undefined;
          return (
            <div
              key={i}
              aria-current={isToday ? "date" : undefined}
              className={`relative h-9 flex items-center justify-center rounded-[10px] text-[12px] ${c.out ? "text-ink-soft opacity-45" : "text-ink"} ${isToday ? "bg-sage font-bold" : ""}`}
            >
              {c.n}
              {mark && <span className={`absolute bottom-1 w-1 h-1 rounded-full ${isToday ? "bg-ink" : MARK[mark]}`} aria-hidden="true" />}
            </div>
          );
        })}
      </div>
    </section>
  );
}
