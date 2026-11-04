"use client";
/**
 * AI 생성 중 화면 — 원형 (디자인 확정본).
 * - 가운데 캐릭터: /plan-ui/running-ssample.webp (투명 배경, 끊김 없는 루프)
 * - progress 를 주면 링이 그 비율만큼 채워진다. 없으면(서버가 진행률을 안 주면) 9초 주기로 천천히 돈다.
 * - step: 지금 단계(0~2). 없으면 링 진행에 맞춰 자동으로 넘어간다.
 */
import { useEffect, useState } from "react";

const R = 120;
const C = 2 * Math.PI * R; // ≈ 754

export default function GenerationRing({
  title = "연간계획안을 만들고 있어요",
  steps = ["주제 정하기", "소주제 나누기", "문서로 정리하기"],
  progress,
  step,
  onCancel,
}: {
  title?: string;
  steps?: string[];
  /** 0~1. 모르면 생략 */
  progress?: number;
  step?: number;
  onCancel?: () => void;
}) {
  const [t, setT] = useState(0);
  useEffect(() => {
    if (progress !== undefined) return;
    const id = setInterval(() => setT((v) => (v + 0.1) % 9), 100);
    return () => clearInterval(id);
  }, [progress]);
  const p = progress ?? t / 9;
  const cur = step ?? Math.min(steps.length - 1, Math.floor(p * steps.length));

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
