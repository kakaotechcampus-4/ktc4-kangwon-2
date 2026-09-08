import { STEP_LABELS, type OnboardingStep } from "@/lib/onboarding/types";

type StepState = "done" | "current" | "pending";

function stateOf(n: 1 | 2 | 3, current: OnboardingStep): StepState {
  if (current === "done") return "done";
  if (n < current) return "done";
  if (n === current) return "current";
  return "pending";
}

/**
 * [● 기본 정보] ─ [○ 반·아동] ─ [○ 성품인사]
 * 현재: Main #AFCDB5 · 완료: Dark #7EAD8B · 미진행: 중립 회색
 * 모바일에서는 라벨이 원 아래로 내려가 폭을 절약한다.
 */
export default function OnboardingStepIndicator({ current }: { current: OnboardingStep }) {
  const steps: (1 | 2 | 3)[] = [1, 2, 3];
  return (
    <ol className="flex items-center justify-center" aria-label="온보딩 진행 단계">
      {steps.map((n, i) => {
        const st = stateOf(n, current);
        const dot =
          st === "done"
            ? "bg-sage-ink border-sage-ink text-white"
            : st === "current"
              ? "bg-sage border-sage-ink text-ink"
              : "bg-paper border-line text-ink-soft";
        const label = st === "done" ? "text-sage-ink" : st === "current" ? "text-ink font-bold" : "text-ink-soft";
        const connectorDone = current === "done" || n < current;
        return (
          <li key={n} className="flex items-center">
            <div className="flex flex-col lg:flex-row items-center gap-1.5 lg:gap-2.5">
              <span
                aria-current={st === "current" ? "step" : undefined}
                className={`inline-flex items-center justify-center w-[30px] h-[30px] rounded-full border-[1.5px] font-mono text-[12.5px] font-medium transition-colors ${dot}`}
              >
                {st === "done" ? (
                  <svg width="13" height="13" viewBox="0 0 24 24" aria-hidden="true">
                    <path d="M4 12.5L9.5 18L20 6" stroke="currentColor" strokeWidth={3} fill="none" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                ) : (
                  n
                )}
              </span>
              <span className={`text-[11.5px] lg:text-[13.5px] whitespace-nowrap ${label}`}>{STEP_LABELS[n]}</span>
            </div>
            {i < steps.length - 1 && (
              <span
                aria-hidden="true"
                className={`h-[1.5px] w-7 lg:w-14 mx-1.5 lg:mx-3.5 self-start mt-[14px] lg:self-center lg:mt-0 rounded ${connectorDone ? "bg-sage-ink" : "bg-line"}`}
              />
            )}
          </li>
        );
      })}
    </ol>
  );
}
