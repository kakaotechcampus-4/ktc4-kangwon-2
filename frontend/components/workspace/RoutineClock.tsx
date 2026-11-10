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

/** 칠한 부채꼴 끝 · 손잡이가 서는 반지름. 숫자(`NUMBER`)보다 바깥이라 숫자가 칠 위에 읽힌다. */
const RIM = 82;
const NUMBER = 60;
/** 손잡이 그림은 작게, 누르는 자리는 손가락만큼 크게 — 그림만 키우면 숫자를 가린다. */
const KNOB = 8;
const GRAB = 18;

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
const spokenOf = (minutes: number) => `${minutes < 12 * 60 ? "오전" : "오후"} ${dialText(minutes)}`;

/** 12시 위, 시계 방향. `minutes` 는 하루 기준이고 시계판은 12시간이라 나머지만 쓴다. */
const angleOf = (minutes: number) => ((minutes % SPAN) / SPAN) * 2 * Math.PI - Math.PI / 2;
const pointOf = (minutes: number, radius: number) => ({
  x: 100 + radius * Math.cos(angleOf(minutes)),
  y: 100 + radius * Math.sin(angleOf(minutes)),
});

/**
 * 시작에서 종료까지 시계 방향으로 칠한 부채꼴 — 방학 생활계획표의 한 칸.
 *
 * 테두리를 따라 굵은 띠만 긋던 때는 숫자와 손잡이가 띠 위에서 겹쳤다. 가운데부터 칠하면
 * 「이만큼이 이 일과」가 한눈에 보이고 숫자는 칠 위에 그대로 읽힌다.
 * 12시간을 넘는 일과는 없다. 넘어 보이면 시계판을 한 바퀴 돈 것이라 긴 쪽으로 칠한다.
 */
function wedgePath(from: number, to: number) {
  const sweep = ((to % SPAN) - (from % SPAN) + SPAN) % SPAN;
  const a = pointOf(from, RIM);
  const b = pointOf(to, RIM);
  return `M 100 100 L ${a.x} ${a.y} A ${RIM} ${RIM} 0 ${sweep > SPAN / 2 ? 1 : 0} 1 ${b.x} ${b.y} Z`;
}

/** `80` → `1시간 20분`. 가운데에 손글씨로 적는다. */
function lengthText(minutes: number) {
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  if (!hours) return `${rest}분`;
  return rest ? `${hours}시간 ${rest}분` : `${hours}시간`;
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

/** 시간 칸에 적는 글 — `오전 09:20 ~ 10:40`. 휴대폰에서 접은 일과 쪽지도 같은 글을 쓴다. */
export function clockText(start: string, end: string) {
  const from = minutesOf(start) ?? FALLBACK.start;
  const to = minutesOf(end) ?? FALLBACK.end;
  // 같은 반이면 뒤쪽의 「오전 · 오후」는 군더더기다 — 열 줄에 스무 번 나온다.
  const sameHalf = Math.floor(from / 720) === Math.floor(to / 720);
  if (start && end) return `${spokenOf(from)} ~ ${sameHalf ? dialText(to) : spokenOf(to)}`;
  if (start) return `${spokenOf(from)} ~`;
  if (end) return `~ ${spokenOf(to)}`;
  return "시간 없음";
}

/**
 * 오전 · 오후 바꾸기. 시계판은 12시간이라 손잡이로는 반을 못 넘기고, 시간 칸의 「오전」 자리는
 * 눌러서 화살표로 바꿔야 해서 찾기 어려웠다(덕철 점검). 같은 시각에 12시간을 더하거나 뺀다.
 */
function HalfPick({
  word,
  at,
  disabled,
  onPick,
}: {
  word: string;
  at: number;
  disabled: boolean;
  onPick: (value: string) => void;
}) {
  const pm = at >= SPAN;
  return (
    <div className={ws.clockHalf} role="group" aria-label={`${word} 오전 · 오후`}>
      {(["오전", "오후"] as const).map((half) => (
        <button
          key={half}
          type="button"
          className="tap44"
          aria-pressed={(half === "오후") === pm}
          disabled={disabled}
          onClick={() => {
            if ((half === "오후") !== pm)
              onPick(textOf(Math.min(LAST, pm ? at - SPAN : at + SPAN)));
          }}
        >
          {half}
        </button>
      ))}
    </div>
  );
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
    // 휴대폰에서는 판이 아래 메뉴 밑으로 펴져 시계 아래쪽이 가려졌다. 판이 다 보이게 내린다 —
    // 아래 메뉴 높이는 globals.css 의 scroll-padding 이 비운다. 시험의 가짜 창에는 matchMedia 가 없다.
    if (globalThis.matchMedia?.("(max-width: 1023px)").matches)
      box.current?.lastElementChild?.scrollIntoView({ block: "nearest" });
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
  const length = start && end && to > from ? lengthText(to - from) : "";
  const shown = clockText(start, end);

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
        className={`${ws.clockShown} tap44`}
        aria-label={`일과 시간 ${shown}, 눌러서 수정`}
        aria-expanded={open}
        disabled={disabled}
        onClick={() => setOpen((was) => !was)}
      >
        {shown}
      </button>
      <button
        type="button"
        className={`${ws.clockOpen} tap44`}
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
          {/* 한 줄에 「● 시작 [시각] [오전|오후]」. 오전 · 오후는 칸 높이와 같은 납작한 두 칸이다(PM). */}
          <div className={`${ws.clockRow} ${ws.clockFrom}`}>
            <label>
              <span>
                <i className={ws.clockDot} aria-hidden="true" />
                시작
              </span>
              <input
                type="time"
                aria-label="시작 시간"
                disabled={disabled}
                value={start}
                onChange={(e) => onStart(e.target.value)}
              />
            </label>
            <HalfPick word="시작" at={from} disabled={disabled} onPick={onStart} />
          </div>
          <div className={`${ws.clockRow} ${ws.clockTo}`}>
            <label>
              <span>
                <i className={ws.clockDot} aria-hidden="true" />
                종료
              </span>
              <input
                type="time"
                aria-label="종료 시간"
                disabled={disabled}
                value={end}
                onChange={(e) => onEnd(e.target.value)}
              />
            </label>
            <HalfPick word="종료" at={to} disabled={disabled} onPick={onEnd} />
          </div>
        </div>
        <svg
          viewBox="0 0 200 200"
          className={ws.clockDial}
          ref={dial}
          onPointerMove={drag}
          onPointerUp={() => (dragging.current = "")}
          onPointerCancel={() => (dragging.current = "")}
        >
          {/* 펜으로 두른 테두리 두 겹. 포스티와 같은 먹선이라 같은 화면의 물건으로 읽힌다. */}
          <circle cx="100" cy="100" r="96" className={ws.clockRim} />
          <circle cx="100" cy="100" r="88" className={ws.clockPlate} />
          <path d={wedgePath(from, to)} className={ws.clockSpan} />
          {/* 눈금. 시는 길게, 5분은 점으로 — 선만 60개면 톱니처럼 보인다. */}
          {Array.from({ length: 60 }, (_, i) => {
            if (i % 5) {
              const dot = pointOf(i * 12, 84);
              return <circle key={i} cx={dot.x} cy={dot.y} r={0.9} className={ws.clockTick} />;
            }
            const outer = pointOf(i * 12, 86);
            const inner = pointOf(i * 12, 80);
            return (
              <line
                key={i}
                x1={inner.x}
                y1={inner.y}
                x2={outer.x}
                y2={outer.y}
                className={ws.clockTickLong}
              />
            );
          })}
          {Array.from({ length: 12 }, (_, i) => {
            const spot = pointOf(i * 60, NUMBER);
            return (
              <text key={i} x={spot.x} y={spot.y} className={ws.clockNumber}>
                {i === 0 ? 12 : i}
              </text>
            );
          })}

          {/* 가운데 — 이 일과가 얼마나 걸리나. 숫자 둘을 빼 보지 않아도 된다. */}
          <circle cx="100" cy="100" r="3.2" className={ws.clockHub} />
          {length && (
            <text x="100" y="122" className={ws.clockLength}>
              {length}
            </text>
          )}

          {(["start", "end"] as const).map((which) => {
            const spot = pointOf(which === "start" ? from : to, RIM);
            return (
              <g key={which} className={which === "start" ? ws.clockGripFrom : ws.clockGripTo}>
                <line x1="100" y1="100" x2={spot.x} y2={spot.y} className={ws.clockHand} />
                <circle cx={spot.x} cy={spot.y} r={KNOB} className={ws.clockKnob} />
                <circle
                  cx={spot.x}
                  cy={spot.y}
                  r={GRAB}
                  className={ws.clockGrab}
                  onPointerDown={grab(which)}
                />
              </g>
            );
          })}
        </svg>

        <p className={ws.clockLead}>
          동그란 손잡이를 끌어 고치세요.
          <button type="button" className={`${ws.clockDone} tap44`} onClick={() => setOpen(false)}>
            닫기
          </button>
        </p>
      </div>
    </div>
  );
}
