"use client";

/**
 * 시간 한 칸 — 글자로 치거나, 시계를 눌러 고른다.
 *
 * 교사가 하루에 시간을 스무 번 고친다. 글자로 치는 길만 두면 숫자 네 자를 매번 쳐야 하고,
 * 시계만 두면 이미 아는 시간을 넣을 때 돌아가야 한다. **둘 다 둔다** — 칸은 그대로 치고,
 * 옆의 시계를 누르면 시계판이 뜬다.
 *
 * 브라우저가 `<input type="time">` 에 붙여 주는 시계 아이콘은 숨긴다. 같은 자리에 아이콘이
 * 둘이면 어느 것이 우리 시계판인지 알 수 없다.
 */

import { useEffect, useRef, useState } from "react";
import { ws } from "./WorkspaceUI";

/** 시계판 반지름. viewBox 는 0~200 이고 가운데가 (100, 100) 이다. */
const FACE = 100;
const HOUR_RING = 74;
const MINUTE_RING = 74;
/** 분은 5분 단위로 고른다. 1분 단위가 필요하면 칸에 직접 친다. */
const MINUTE_STEP = 5;

/** 12시가 위, 시계 방향. `index` 는 0 이 12시 자리다. */
function pointOf(index: number, count: number, radius: number) {
  const angle = (index / count) * 2 * Math.PI - Math.PI / 2;
  return { x: 100 + radius * Math.cos(angle), y: 100 + radius * Math.sin(angle) };
}

/** `"13:05"` → `{ hour12: 1, minute: 5, pm: true }`. 빈 값은 오전 9시로 연다. */
function parts(value: string) {
  const [h, m] = value.split(":");
  const hour24 = Number(h);
  if (!value || Number.isNaN(hour24)) return { hour12: 9, minute: 0, pm: false };
  return { hour12: hour24 % 12 || 12, minute: Number(m) || 0, pm: hour24 >= 12 };
}

const compose = (hour12: number, minute: number, pm: boolean) =>
  `${String((hour12 % 12) + (pm ? 12 : 0)).padStart(2, "0")}:${String(minute).padStart(2, "0")}`;

export default function RoutineClock({
  label,
  value,
  disabled,
  onChange,
}: {
  label: string;
  value: string;
  disabled: boolean;
  onChange: (value: string) => void;
}) {
  const [open, setOpen] = useState(false);
  /** 시를 고르면 분으로 넘어간다. 두 판을 한 화면에 늘어놓으면 숫자 스물넷이 겹친다. */
  const [step, setStep] = useState<"hour" | "minute">("hour");
  const box = useRef<HTMLDivElement | null>(null);

  // 바깥을 누르거나 ESC 를 누르면 닫는다. 고른 것은 누를 때마다 이미 반영돼 있다.
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

  const now = parts(value);

  function pickHour(hour12: number) {
    onChange(compose(hour12, now.minute, now.pm));
    setStep("minute");
  }
  function pickMinute(minute: number) {
    onChange(compose(now.hour12, minute, now.pm));
    setOpen(false);
  }

  return (
    <div className={ws.clock} ref={box}>
      <input
        type="time"
        aria-label={`${label} 시간`}
        disabled={disabled}
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
      <button
        type="button"
        className={ws.clockOpen}
        aria-label={`${label} 시간 시계로 고르기`}
        aria-expanded={open}
        disabled={disabled}
        onClick={() => {
          setStep("hour");
          setOpen((was) => !was);
        }}
      >
        {/* 시계 그림. 글자가 아니라서 글꼴 · 배율이 달라도 모양이 같다. */}
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

      {open && (
        <div className={ws.clockFace} role="dialog" aria-label={`${label} 시간 고르기`}>
          <div className={ws.clockHead}>
            <strong>{value || "--:--"}</strong>
            <div className={ws.clockMeridiem}>
              {(["AM", "PM"] as const).map((side) => (
                <button
                  key={side}
                  type="button"
                  aria-pressed={now.pm === (side === "PM")}
                  onClick={() => onChange(compose(now.hour12, now.minute, side === "PM"))}
                >
                  {side === "AM" ? "오전" : "오후"}
                </button>
              ))}
            </div>
          </div>

          <svg viewBox="0 0 200 200" className={ws.clockDial}>
            <circle cx="100" cy="100" r={FACE} className={ws.clockPlate} />
            {/* 분 눈금. 숫자 사이를 재는 눈이 있어야 시계로 읽힌다. */}
            {Array.from({ length: 60 }, (_, i) => {
              const outer = pointOf(i, 60, 94);
              const inner = pointOf(i, 60, i % 5 === 0 ? 86 : 90);
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
            {/* 고른 시각을 가리키는 바늘. 어디를 골랐는지 숫자 색만으로는 멀다. */}
            <line
              x1="100"
              y1="100"
              x2={
                pointOf(
                  step === "hour" ? now.hour12 % 12 : now.minute / MINUTE_STEP,
                  12,
                  step === "hour" ? HOUR_RING : MINUTE_RING,
                ).x
              }
              y2={
                pointOf(
                  step === "hour" ? now.hour12 % 12 : now.minute / MINUTE_STEP,
                  12,
                  step === "hour" ? HOUR_RING : MINUTE_RING,
                ).y
              }
              className={ws.clockHand}
            />
            <circle cx="100" cy="100" r="3.5" className={ws.clockPin} />

            {Array.from({ length: 12 }, (_, i) => {
              const hour12 = i === 0 ? 12 : i;
              const minute = i * MINUTE_STEP;
              const chosen = step === "hour" ? now.hour12 === hour12 : now.minute === minute;
              const at = pointOf(i, 12, step === "hour" ? HOUR_RING : MINUTE_RING);
              const text = step === "hour" ? String(hour12) : String(minute).padStart(2, "0");
              return (
                <g key={i}>
                  <circle
                    cx={at.x}
                    cy={at.y}
                    r="17"
                    className={chosen ? ws.clockPickedSpot : ws.clockSpot}
                  />
                  <text x={at.x} y={at.y} className={chosen ? ws.clockPicked : ws.clockNumber}>
                    {text}
                  </text>
                  {/* 숫자와 동그라미 위를 덮는 누르는 자리. 글자만 누르게 하면 빗나간다. */}
                  <circle
                    cx={at.x}
                    cy={at.y}
                    r="17"
                    className={ws.clockHit}
                    role="button"
                    tabIndex={0}
                    aria-label={step === "hour" ? `${hour12}시` : `${minute}분`}
                    onClick={() => (step === "hour" ? pickHour(hour12) : pickMinute(minute))}
                    onKeyDown={(e) => {
                      if (e.key !== "Enter" && e.key !== " ") return;
                      e.preventDefault();
                      if (step === "hour") pickHour(hour12);
                      else pickMinute(minute);
                    }}
                  />
                </g>
              );
            })}
          </svg>

          <div className={ws.clockFoot}>
            <button
              type="button"
              aria-pressed={step === "hour"}
              onClick={() => setStep("hour")}
            >
              시
            </button>
            <button
              type="button"
              aria-pressed={step === "minute"}
              onClick={() => setStep("minute")}
            >
              분
            </button>
            <button type="button" className={ws.clockDone} onClick={() => setOpen(false)}>
              닫기
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
