"use client";
/**
 * AI 생성 중 화면 — 원형 (디자인 확정본).
 * - 가운데 캐릭터: /plan-ui/running-ssample.webp (투명 배경, 끊김 없는 루프)
 * - 링은 시간을 짐작하지 않는다. 서버가 알려 준 단계(`runId` 로 묻는다, api-spec §9-8)로 끝난 칸만큼만 차고,
 *   지금 칸은 옅게 맥박친다. 퍼센트 · 초는 보이지 않는다. 단계는 앞으로만 간다.
 * - 조회가 안 돼도(404 · 5xx · 연결 오류) 지금 단계에 머문다. 생성 실패는 각 화면이 생성 POST 의 오류로만 그린다.
 * - 다 만들면 부모가 `done` 을 켜고 `ringFinished()` 만큼 기다린 뒤 화면을 바꾼다 — 링이 끝까지 차는 걸 보여준다.
 */
import { useEffect, useState } from "react";
import { watchStage } from "@/lib/api/generationRuns";
import { Tape } from "@/components/workspace/WorkspaceUI";

const R = 120;
const C = 2 * Math.PI * R; // ≈ 754

/** `done` 을 켠 뒤 링이 끝까지 차는 시간. 부모는 이만큼 기다렸다가 화면을 바꾼다. */
export const ringFinished = () => new Promise<void>((resolve) => setTimeout(resolve, 600));

/**
 * [생성 멈추기] 뒤 만들기 화면에 한 줄 — 연간 · 월간 · 주간이 같은 모양을 쓴다. 적은 메모 · 고른 값은 그대로 둔다.
 * 놀이 중심형 연간은 서버도 구간 사이에서 멈추고 저장하지 않는다(router `_disconnected`). 한 번에
 * 끝나는 다른 생성은 이미 보낸 요청을 서버가 끝까지 처리할 수 있다.
 */
export const STOPPED_NOTE = (
  <p role="status" className="m-0 rounded-md bg-cream px-4 py-3 text-sm text-ink-soft">
    생성을 멈췄어요.
  </p>
);

export default function GenerationRing({
  title = "연간계획안을 만들고 있어요",
  steps = [
    ["generate", "주제 정하기"],
    ["subthemes", "소주제 나누기"],
    ["save", "문서로 정리하기"],
  ],
  runId,
  done = false,
  spin = false,
  cancelLabel = "생성 멈추기",
  onCancel,
}: {
  title?: string;
  /** [서버 단계 키, 화면 글자] 쌍. 순서가 곧 단계 순서다(api-spec §9-8). */
  steps?: readonly (readonly [key: string, label: string])[];
  /** 이 생성 POST 의 `X-Generation-Run-Id` 와 같은 값. 없으면 서버에 묻지 않고 첫 단계에 머문다. */
  runId?: string;
  /** 다 만들었다 — 링을 끝까지 채우고 단계를 모두 끝낸 것으로 보인다. */
  done?: boolean;
  /** 단계 대신 짧은 호가 휙 돌고 쉬기를 되풀이한다(globals.css `.ringSweep`) — 연간 파일 가져오기 대기. 서버 기록이 없다. */
  spin?: boolean;
  cancelLabel?: string;
  onCancel?: () => void;
}) {
  const [at, setAt] = useState(0);
  // 매 렌더 새 배열이 와도 effect 가 다시 돌지 않게 키만 문자열로 둔다.
  const keys = steps.map(([k]) => k).join();
  useEffect(() => {
    if (!runId || done || spin) return;
    const ctl = new AbortController();
    // 앞으로만 간다 — 늦게 온 옛 응답이나 모르는 키(-1)는 무시한다.
    const toStage = (key: string) => setAt((i) => Math.max(i, keys.split(",").indexOf(key)));
    void watchStage(runId, toStage, ctl.signal);
    return () => ctl.abort();
  }, [runId, done, spin, keys]);
  const N = steps.length;
  // 끝난 칸만큼 찬다. 다 만들면 모두 끝난 단계가 되고, spin 은 강조하는 단계가 없다.
  const cur = done ? N : spin ? -1 : at;

  return (
    <div className="flex flex-1 items-center justify-center p-8 text-ink">
      <section
        aria-live="polite"
        aria-busy={!done}
        className="relative flex w-[720px] max-w-full flex-col items-center gap-7 bg-paper px-12 py-14 shadow-pg"
      >
        <Tape />
        <div className="relative h-[280px] w-[280px]">
          <svg
            viewBox="0 0 280 280"
            width="280"
            height="280"
            aria-hidden="true"
            className={`absolute inset-0 ${spin ? "ringSweep" : "-rotate-90"}`}
          >
            <circle cx="140" cy="140" r={R} fill="none" stroke="var(--pg-cream)" strokeWidth="14" />
            <circle
              cx="140"
              cy="140"
              r={R}
              fill="none"
              stroke="var(--pg-primary)"
              strokeWidth="14"
              strokeLinecap="round"
              strokeDasharray={C}
              strokeDashoffset={C * (1 - (spin ? 0.28 : cur / N))}
              className={
                spin
                  ? undefined
                  : `transition-[stroke-dashoffset] motion-reduce:transition-none ${done ? "duration-500 ease-out" : "duration-300 ease-linear"}`
              }
            />
            {/* 지금 하고 있는 칸 — 옅은 보라가 맥박친다(움직임 줄이기면 멈춘 채). 몇 % 인지는 모른다. */}
            {!done && !spin && (
              <circle
                cx="140"
                cy="140"
                r={R}
                fill="none"
                stroke="var(--pg-primary)"
                strokeWidth="14"
                strokeOpacity="0.4"
                strokeDasharray={`${C / N} ${C}`}
                strokeDashoffset={(-C * cur) / N}
                className="animate-pulse motion-reduce:animate-none"
              />
            )}
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
          <h1 className="m-0 font-display text-[34px] font-bold leading-[1.2] text-ink">{title}</h1>
        </div>
        <ol className="m-0 flex list-none flex-wrap justify-center gap-x-7 gap-y-2 p-0 text-[15px]">
          {steps.map(([key, s], i) => (
            <li
              key={key}
              aria-current={i === cur ? "step" : undefined}
              className={
                i === cur ? "font-bold text-primary" : i < cur ? "text-ink-soft" : "text-ink-hint"
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
            className="flex min-h-[44px] items-center gap-2 rounded-md border border-line bg-paper px-4 text-sm text-ink-soft hover:bg-cream hover:text-ink"
          >
            <span aria-hidden="true" className="h-2.5 w-2.5 rounded-[2px] bg-current" />
            {cancelLabel}
          </button>
        )}
      </section>
    </div>
  );
}
