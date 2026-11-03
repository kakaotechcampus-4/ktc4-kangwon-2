"use client";

import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { Posty } from "@/components/app/Posty";
import { STEP_LABELS, type OnboardingStep } from "@/lib/onboarding/types";

type StepState = "done" | "current" | "pending";

function stateOf(n: Exclude<OnboardingStep, "done">, current: OnboardingStep): StepState {
  if (current === "done") return "done";
  if (n < current) return "done";
  if (n === current) return "current";
  return "pending";
}

/**
 * [① 원 정보] ─ [② 반 정보] ─ [③ 아동 명단]
 * 지금 단계만 보라 면으로 선다. 끝난 단계는 체크, 남은 단계는 테두리만.
 * 모바일에서는 라벨이 원 아래로 내려가 폭을 절약한다.
 *
 * 지금 단계 위에서 포스티가 걷고, 단계가 넘어가면 그 자리까지 걸어서 옮겨 간다.
 * 자리는 동그라미를 재서 잡는다 — 라벨 길이가 달라 칸을 n 등분할 수 없다.
 */
export default function OnboardingStepIndicator({ current }: { current: OnboardingStep }) {
  const steps: Exclude<OnboardingStep, "done">[] = [1, 2, 3];
  const list = useRef<HTMLOListElement>(null);
  const dots = useRef<(HTMLSpanElement | null)[]>([]);
  const [walkerX, setWalkerX] = useState<number | null>(null);

  const standing = current === "done" ? steps.length : steps.indexOf(current as 1 | 2 | 3) + 1;

  useLayoutEffect(() => {
    const place = () => {
      const dot = dots.current[standing - 1];
      if (!dot || !list.current) return;
      setWalkerX(dot.offsetLeft + dot.offsetWidth / 2);
    };
    place();
    window.addEventListener("resize", place);
    return () => window.removeEventListener("resize", place);
  }, [standing]);

  // 글꼴이 늦게 와서 라벨 폭이 바뀌면 자리도 어긋난다.
  useEffect(() => {
    document.fonts?.ready.then(() => {
      const dot = dots.current[standing - 1];
      if (dot) setWalkerX(dot.offsetLeft + dot.offsetWidth / 2);
    });
  }, [standing]);

  return (
    <ol
      ref={list}
      className="relative flex items-center justify-center pt-[56px]"
      aria-label="온보딩 진행 단계"
    >
      {walkerX !== null && (
        <span
          aria-hidden="true"
          className="pointer-events-none absolute top-0 -ml-[19px] transition-[left] duration-500 ease-out motion-reduce:transition-none"
          style={{ left: walkerX }}
        >
          {current === "done" ? (
            <Posty pose="cheer" face="done" tone="sage" size={38} label={null} />
          ) : (
            <Posty pose="stand" size={38} walk label={null} />
          )}
        </span>
      )}
      {steps.map((n, i) => {
        const st = stateOf(n, current);
        const dot =
          st === "done"
            ? "bg-primary border-primary-line text-white"
            : st === "current"
              ? "bg-primary-tint border-primary-tint-line text-primary-ink"
              : "bg-paper border-line text-ink-soft";
        const label =
          st === "done"
            ? "text-primary"
            : st === "current"
              ? "text-primary-ink font-semibold"
              : "text-ink-soft";
        const connectorDone = current === "done" || n < current;
        return (
          <li key={n} className="flex items-center">
            <div className="flex flex-col lg:flex-row items-center gap-1.5 lg:gap-2.5">
              <span
                ref={(el) => {
                  dots.current[i] = el;
                }}
                aria-current={st === "current" ? "step" : undefined}
                className={`inline-flex items-center justify-center w-[30px] h-[30px] rounded-full border-[1.5px] font-mono text-[12.5px] font-medium transition-colors ${dot}`}
              >
                {st === "done" ? (
                  <svg width="13" height="13" viewBox="0 0 24 24" aria-hidden="true">
                    <path
                      d="M4 12.5L9.5 18L20 6"
                      stroke="currentColor"
                      strokeWidth={3}
                      fill="none"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </svg>
                ) : (
                  n
                )}
              </span>
              <span className={`text-[15px] lg:text-[13.5px] whitespace-nowrap ${label}`}>
                {STEP_LABELS[n]}
              </span>
            </div>
            {i < steps.length - 1 && (
              // 지나온 구간은 진한 실선, 남은 구간은 발자국 점. 1.5px 연한 선은 화면에서 사라졌다.
              <span
                aria-hidden="true"
                className={`w-5 sm:w-8 lg:w-9 mx-1.5 lg:mx-3 self-start mt-[14px] lg:self-center lg:mt-0 ${
                  connectorDone ? "h-[2.5px] rounded bg-primary" : "stepTrail h-[3px]"
                }`}
              />
            )}
          </li>
        );
      })}
    </ol>
  );
}
