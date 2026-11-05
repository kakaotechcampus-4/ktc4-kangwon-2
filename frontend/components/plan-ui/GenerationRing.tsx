"use client";
/**
 * AI 생성 중 화면 — 원형 (디자인 확정본).
 * - 가운데 캐릭터: /plan-ui/running-ssample.webp (투명 배경, 끊김 없는 루프)
 * - 서버는 진행률을 주지 않는다. 링은 「예상 시간」에 90% 가 되도록 서서히 차고, 넘으면 99% 쪽으로
 *   점점 느리게 다가간다(멈추지 않는다).
 *   예상 시간은 이 브라우저에서 같은 종류(`kind`)가 실제로 걸린 시간을 기억해 맞춘다. 처음엔 `expect`(초).
 * - 단계(steps)는 예상 시간을 고르게 나눠 한 번만 넘어간다.
 * - 다 만들면 부모가 `done` 을 켜고 `ringFinished()` 만큼 기다린 뒤 화면을 바꾼다 — 링이 끝까지 차는 걸 보여준다.
 */
import { useEffect, useState } from "react";

const R = 120;
const C = 2 * Math.PI * R; // ≈ 754
const KEY = "ssample.generation-seconds";

function remembered(kind: string, fallback: number) {
  try {
    const seconds = JSON.parse(localStorage.getItem(KEY) ?? "{}")[kind];
    return typeof seconds === "number" && seconds > 0 ? seconds : fallback;
  } catch {
    return fallback;
  }
}
function remember(kind: string, seconds: number) {
  try {
    const all = JSON.parse(localStorage.getItem(KEY) ?? "{}");
    // 지난 값과 반씩 섞는다 — 한 번 유난히 빠르거나 느려도 다음 링이 크게 흔들리지 않게.
    all[kind] = typeof all[kind] === "number" ? (all[kind] + seconds) / 2 : seconds;
    localStorage.setItem(KEY, JSON.stringify(all));
  } catch {}
}

/**
 * 지난 시간 `t` · 예상 `expect`(초) → 0~0.99. 예상의 절반에 약 62%, 예상 시간에 90%, 1.5배에 97%, 2배에 99%.
 * 앞에서 확 차고 95% 에서 딱 멈추던 곡선 대신, 고르게 차다가 끝으로 갈수록 느려진다.
 */
export function ringProgress(t: number, expect: number) {
  return 0.99 * (1 - Math.exp(-2.4 * Math.pow(t / expect, 1.3)));
}

/** `done` 을 켠 뒤 링이 끝까지 차는 시간. 부모는 이만큼 기다렸다가 화면을 바꾼다. */
export const ringFinished = () => new Promise<void>((resolve) => setTimeout(resolve, 600));

export default function GenerationRing({
  title = "연간계획안을 만들고 있어요",
  steps = ["주제 정하기", "소주제 나누기", "문서로 정리하기"],
  kind,
  expect,
  done = false,
  onCancel,
}: {
  title?: string;
  steps?: string[];
  /** 걸린 시간을 기억할 종류(예: "annual-theme"). */
  kind: string;
  /** 처음 쓸 예상 시간(초). 한 번 만들고 나면 실제 걸린 시간으로 바뀐다. */
  expect: number;
  /** 다 만들었다 — 링을 끝까지 채우고 단계를 모두 끝낸 것으로 보인다. */
  done?: boolean;
  onCancel?: () => void;
}) {
  const [t, setT] = useState(0);
  const [guess] = useState(() => remembered(kind, expect));
  const [started] = useState(() => Date.now());
  useEffect(() => {
    if (done) return;
    const id = setInterval(() => setT((Date.now() - started) / 1000), 200);
    return () => clearInterval(id);
  }, [done, started]);
  // 다 만들었을 때만 걸린 시간을 적는다 — 그만 만들기 · 실패는 생성 시간이 아니다.
  useEffect(() => {
    if (done) remember(kind, (Date.now() - started) / 1000);
  }, [done, kind, started]);
  const p = done ? 1 : ringProgress(t, guess);
  // 단계는 예상 시간을 고르게 나눠 넘긴다. 다 만들면 모두 끝난 단계가 된다.
  const cur = done
    ? steps.length
    : Math.min(steps.length - 1, Math.floor((t / guess) * steps.length));

  return (
    <div className="flex flex-1 items-center justify-center p-8 text-[#2b2826]">
      <section
        aria-live="polite"
        aria-busy={!done}
        className="flex w-[720px] max-w-full flex-col items-center gap-7 rounded-[28px] border border-[#e8e2d8] bg-white px-12 py-14"
      >
        <div className="relative h-[280px] w-[280px]">
          <svg
            viewBox="0 0 280 280"
            width="280"
            height="280"
            aria-hidden="true"
            className="absolute inset-0 -rotate-90"
          >
            <circle cx="140" cy="140" r={R} fill="none" stroke="#f1ece4" strokeWidth="14" />
            <circle
              cx="140"
              cy="140"
              r={R}
              fill="none"
              stroke="#7053a0"
              strokeWidth="14"
              strokeLinecap="round"
              strokeDasharray={C}
              strokeDashoffset={C * (1 - p)}
              className={`transition-[stroke-dashoffset] motion-reduce:transition-none ${done ? "duration-500 ease-out" : "duration-300 ease-linear"}`}
            />
          </svg>
          <div className="absolute inset-0 flex items-center justify-center">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src="/plan-ui/running-ssample.webp"
              alt=""
              width={165}
              className="block h-auto w-[165px]"
            />
          </div>
        </div>
        <div className="flex flex-col items-center gap-2">
          <h1 className="m-0 text-[26px] font-bold tracking-[-0.5px]">{title}</h1>
        </div>
        <ol className="m-0 flex list-none gap-7 p-0 text-[15px]">
          {steps.map((s, i) => (
            <li
              key={s}
              aria-current={i === cur ? "step" : undefined}
              className={
                i === cur
                  ? "font-bold text-[#7053a0]"
                  : i < cur
                    ? "text-ink-soft"
                    : "text-[#c9c1b6]"
              }
            >
              {i + 1} {s}
            </li>
          ))}
        </ol>
        {onCancel && !done && (
          <button
            type="button"
            onClick={onCancel}
            className="flex min-h-[44px] items-center text-sm text-[#5c5243] underline"
          >
            그만 만들기
          </button>
        )}
      </section>
    </div>
  );
}
