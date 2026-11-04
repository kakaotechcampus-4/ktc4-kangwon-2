"use client";
/**
 * AI 생성 중 화면 — 원형 (디자인 확정본).
 * - 가운데 캐릭터: /plan-ui/running-ssample.webp (투명 배경, 끊김 없는 루프)
 * - 서버는 진행률을 주지 않는다. 링은 「예상 시간」 동안 90% 까지 차고, 넘으면 아주 천천히 더 찬다.
 *   예상 시간은 이 브라우저에서 같은 종류(`kind`)가 실제로 걸린 시간을 기억해 맞춘다. 처음엔 `expect`(초).
 * - 단계(steps)는 예상 시간을 고르게 나눠 한 번만 넘어간다.
 */
import { useEffect, useRef, useState } from "react";

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

/** 지난 시간 `t` · 예상 `expect`(초) → 0~0.95. 예상 시간에 0.9, 그 뒤로는 0.95 를 넘지 않는다. */
export function ringProgress(t: number, expect: number) {
  return Math.min(0.95, 1 - Math.exp((-2.3 * t) / expect));
}

export default function GenerationRing({
  title = "연간계획안을 만들고 있어요",
  steps = ["주제 정하기", "소주제 나누기", "문서로 정리하기"],
  kind,
  expect,
  onCancel,
}: {
  title?: string;
  steps?: string[];
  /** 걸린 시간을 기억할 종류(예: "annual-theme"). */
  kind: string;
  /** 처음 쓸 예상 시간(초). 한 번 만들고 나면 실제 걸린 시간으로 바뀐다. */
  expect: number;
  onCancel?: () => void;
}) {
  const [t, setT] = useState(0);
  const [guess] = useState(() => remembered(kind, expect));
  const cancelled = useRef(false);
  useEffect(() => {
    const started = Date.now();
    const id = setInterval(() => setT((Date.now() - started) / 1000), 200);
    return () => {
      clearInterval(id);
      // 그만 만들기 · 바로 실패(3초 안)는 생성 시간이 아니다. 끝나서 화면이 바뀔 때만 적는다.
      const seconds = (Date.now() - started) / 1000;
      if (!cancelled.current && seconds >= 3) remember(kind, seconds);
    };
  }, [kind]);
  const p = ringProgress(t, guess);
  // 단계는 예상 시간을 고르게 나눠 넘긴다(링은 앞쪽이 빨리 찬다).
  const cur = Math.min(steps.length - 1, Math.floor((t / guess) * steps.length));

  return (
    <div className="flex flex-1 items-center justify-center p-8 text-[#2b2826]">
      <section
        aria-live="polite"
        aria-busy="true"
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
              className="transition-[stroke-dashoffset] duration-300 ease-linear motion-reduce:transition-none"
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
                    ? "text-[#8a8178]"
                    : "text-[#c9c1b6]"
              }
            >
              {i + 1} {s}
            </li>
          ))}
        </ol>
        {onCancel && (
          <button
            type="button"
            onClick={() => {
              cancelled.current = true;
              onCancel();
            }}
            className="flex min-h-[44px] items-center text-sm text-[#5c5243] underline"
          >
            그만 만들기
          </button>
        )}
      </section>
    </div>
  );
}
