"use client";

/**
 * 한 일과의 시간 — 「오전 09:20 ~ 10:40」 한 칸이다.
 *
 * 시작과 종료를 칸 두 개로 두니 줄이 가로로 길어졌고, 시계판에서 고르는 것도 점 하나였다.
 * 일과는 점이 아니라 **구간**이다. 그래서 초등학교 방학 생활계획표처럼 시계판에 구간을
 * 칠하고, 양 끝 손잡이를 끌어 늘리고 줄인다.
 *
 * 끌기는 마우스 · 손가락의 길이다. 키보드와 화면 읽기 프로그램은 아래의 시작 · 종료
 * 칸(`<input type="time">`)을 쓴다 — 같은 값을 고치는 다른 길이다.
 */

import { useEffect, useRef, useState } from "react";
import { ws } from "./WorkspaceUI";

/** 시계판 한 바퀴는 12시간이다. 분으로 센다. */
const SPAN = 720;
/** 끌 때는 5분 단위로 붙는다. 1분이 필요하면 아래 칸에 직접 친다. */
const STEP = 5;
const LAST = 23 * 60 + 55;
/** 시각이 없을 때 시계판이 여는 자리. 어린이집 하루가 대개 여기서 시작한다. */
const FALLBACK = { start: 9 * 60, end: 10 * 60 };

const RING = 66;
const HAND = 15;

const minutesOf = (value: string) => {
  const [h, m] = value.split(":").map(Number);
  return Number.isNaN(h) ? null : h * 60 + (m || 0);
};
/** 서버 · `<input type="time">` 이 쓰는 24시간 모양. */
const textOf = (minutes: number) =>
  `${String(Math.floor(minutes / 60)).padStart(2, "0")}:${String(minutes % 60).padStart(2, "0")}`;

/** 화면에 적는 12시간 모양. `780` → `01:00` */
const dialText = (minutes: number) =>
  `${String(Math.floor(minutes / 60) % 12 || 12).padStart(2, "0")}:${String(minutes % 60).padStart(2, "0")}`;

/** `550` → `오전 09:10`. 교사가 종이에 쓰는 모양 그대로다. */
const spokenOf = (minutes: number) =>
  `${minutes < 12 * 60 ? "오전" : "오후"} ${dialText(minutes)}`;

/** 12시 위, 시계 방향. `minutes` 는 하루 기준이고 시계판은 12시간이라 나머지만 쓴다. */
const angleOf = (minutes: number) => ((minutes % SPAN) / SPAN) * 2 * Math.PI - Math.PI / 2;
const pointOf = (minutes: number, radius: number) => ({
  x: 100 + radius * Math.cos(angleOf(minutes)),
  y: 100 + radius * Math.sin(angleOf(minutes)),
});

/**
 * 시작에서 종료까지 시계 방향으로 그은 호.
 *
 * 12시간을 넘는 일과는 없다. 넘어 보이면 시계판을 한 바퀴 돈 것이라 긴 쪽으로 긋는다.
 */
function arcPath(from: number, to: number) {
  const sweep = ((to % SPAN) - (from % SPAN) + SPAN) % SPAN;
  const a = pointOf(from, RING);
  const b = pointOf(to, RING);
  return `M ${a.x} ${a.y} A ${RING} ${RING} 0 ${sweep > SPAN / 2 ? 1 : 0} 1 ${b.x} ${b.y}`;
}

/**
 * 손잡이를 끌어 옮긴 자리.
 *
 * 시계판은 12시간이라 끈 자리만으로는 오전인지 오후인지 모른다. **끌기 전 시각의 반**을
 * 쓰되, 12시 눈금을 지나갔으면 반을 넘긴 것으로 본다 — 11:30 에서 12시 쪽으로 끌면
 * 00:30 이 아니라 12:30 이어야 한다.
 */
function movedTo(was: number, angle: number) {
  const raw = (((angle + Math.PI / 2) / (2 * Math.PI)) * SPAN + SPAN) % SPAN;
  const spot = (Math.round(raw / STEP) * STEP) % SPAN;
  const half = Math.floor(was / SPAN) * SPAN;
  const before = was % SPAN;
  let next = half + spot;
  if (spot - before > SPAN / 2) next -= SPAN;
  else if (before - spot > SPAN / 2) next += SPAN;
  return Math.max(0, Math.min(LAST, next));
}

export default function RoutineClock({
  start,
  end,
  disabled,
  onStart,
  onEnd,
  onDone,
}: {
  start: string;
  end: string;
  disabled: boolean;
  onStart: (value: string) => void;
  onEnd: (value: string) => void;
  /** 시계를 닫았다 — 이 일과의 시간이 정해졌다. 닫는 길이 넷이라 한곳에서 알린다. */
  onDone?: () => void;
}) {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement | null>(null);
  const dial = useRef<SVGSVGElement | null>(null);
  /** 지금 끌고 있는 손잡이. 끌지 않을 때는 빈 문자열이다. */
  const dragging = useRef<"start" | "end" | "">("");

  /** 열렸다가 닫힌 순간만 잡는다. 닫기 단추 · 바깥 누르기 · Escape · 다시 누르기 전부 여기로 온다. */
  const wasOpen = useRef(false);
  useEffect(() => {
    if (wasOpen.current && !open) onDone?.();
    wasOpen.current = open;
    // `onDone` 은 매 렌더 새 함수다. 여기 넣으면 열고 닫지 않아도 계속 돈다.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const away = (e: MouseEvent) => {
      if (!box.current?.contains(e.target as Node)) setOpen(false);
    };
    const key = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", away);
    document.addEventListener("keydown", key);
    return () => {
      document.removeEventListener("mousedown", away);
      document.removeEventListener("keydown", key);
    };
  }, [open]);

  const from = minutesOf(start) ?? FALLBACK.start;
  const to = minutesOf(end) ?? FALLBACK.end;
  // 같은 반이면 뒤쪽의 「오전 · 오후」는 군더더기다 — 열 줄에 스무 번 나온다.
  const sameHalf = Math.floor(from / 720) === Math.floor(to / 720);
  const shown =
    start && end
      ? `${spokenOf(from)} ~ ${sameHalf ? dialText(to) : spokenOf(to)}`
      : start
        ? `${spokenOf(from)} ~`
        : end
          ? `~ ${spokenOf(to)}`
          : "시간 없음";

  function drag(e: React.PointerEvent<SVGSVGElement>) {
    const which = dragging.current;
    if (!which || !dial.current) return;
    const area = dial.current.getBoundingClientRect();
    const angle = Math.atan2(
      e.clientY - (area.top + area.height / 2),
      e.clientX - (area.left + area.width / 2),
    );
    const next = movedTo(which === "start" ? from : to, angle);
    (which === "start" ? onStart : onEnd)(textOf(next));
  }

  const grab = (which: "start" | "end") => (e: React.PointerEvent) => {
    dragging.current = which;
    (e.target as Element).setPointerCapture?.(e.pointerId);
  };

  return (
    <div className={ws.clock} ref={box}>
      <button
        type="button"
        className={ws.clockShown}
        aria-label={`일과 시간 ${shown}, 눌러서 고치기`}
        aria-expanded={open}
        disabled={disabled}
        onClick={() => setOpen((was) => !was)}
      >
        {shown}
      </button>
      <button
        type="button"
        className={ws.clockOpen}
        aria-label="시계로 시간 고르기"
        aria-expanded={open}
        disabled={disabled}
        onClick={() => setOpen((was) => !was)}
      >
        <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
          <circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" strokeWidth="1.6" />
          <path
            d="M12 7.2V12l3.1 1.9"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.6"
            strokeLinecap="round"
          />
        </svg>
      </button>

      {/*
        닫혀 있어도 자리에 둔다. 시작 · 종료 칸을 꺼냈다 넣었다 하면 적던 칸이
        사라지면서 커서를 잃는다. `hidden` 은 화면 읽기 프로그램에서도 빠진다.
      */}
      <div className={ws.clockFace} hidden={!open} role="group" aria-label="일과 시간 고르기">
        {/*
          적어 둔 시각이 곧 고치는 칸이다. 글자로만 보여 주고 고치는 칸을 따로 아래에
          두었더니, 교사가 그 글자를 눌렀다. 누르면 고쳐지는 자리에 두는 것이 맞다.
        */}
        <div className={ws.clockFields}>
          <label className={ws.clockFrom}>
            <span>시작</span>
            <input
              type="time"
              aria-label="시작 시간"
              disabled={disabled}
              value={start}
              onChange={(e) => onStart(e.target.value)}
            />
          </label>
          <span className={ws.clockTilde} aria-hidden="true">
            ~
          </span>
          <label className={ws.clockTo}>
            <span>종료</span>
            <input
              type="time"
              aria-label="종료 시간"
              disabled={disabled}
              value={end}
              onChange={(e) => onEnd(e.target.value)}
            />
          </label>
        </div>
        <svg
          viewBox="0 0 200 200"
          className={ws.clockDial}
          ref={dial}
          onPointerMove={drag}
          onPointerUp={() => (dragging.current = "")}
          onPointerCancel={() => (dragging.current = "")}
        >
          <circle cx="100" cy="100" r="92" className={ws.clockPlate} />
          {/* 눈금. 숫자 사이를 재는 눈이 있어야 시계로 읽힌다. */}
          {Array.from({ length: 60 }, (_, i) => {
            const outer = pointOf(i * 12, 90);
            const inner = pointOf(i * 12, i % 5 === 0 ? 82 : 86);
            return (
              <line
                key={i}
                x1={inner.x}
                y1={inner.y}
                x2={outer.x}
                y2={outer.y}
                className={i % 5 === 0 ? ws.clockTickLong : ws.clockTick}
              />
            );
          })}
          {Array.from({ length: 12 }, (_, i) => {
            const spot = pointOf(i * 60, 46);
            return (
              <text key={i} x={spot.x} y={spot.y} className={ws.clockNumber}>
                {i === 0 ? 12 : i}
              </text>
            );
          })}

          {/* 칠한 구간. 방학 생활계획표가 하루를 이렇게 가른다. */}
          <path d={arcPath(from, to)} className={ws.clockSpan} />
          {(["start", "end"] as const).map((which) => {
            const spot = pointOf(which === "start" ? from : to, RING);
            return (
              <g key={which}>
                <circle
                  cx={spot.x}
                  cy={spot.y}
                  r={HAND}
                  className={which === "start" ? ws.clockGripFrom : ws.clockGripTo}
                  onPointerDown={grab(which)}
                />
                <text x={spot.x} y={spot.y} className={ws.clockGripMark} aria-hidden="true">
                  {which === "start" ? "시작" : "끝"}
                </text>
              </g>
            );
          })}
        </svg>

        <p className={ws.clockLead}>
          손잡이를 끌어 고치세요.
          <button type="button" className={ws.clockDone} onClick={() => setOpen(false)}>
            닫기
          </button>
        </p>
      </div>
    </div>
  );
}
