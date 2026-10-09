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
 */
export default function OnboardingStepIndicator({ current }: { current: OnboardingStep }) {
  const steps: Exclude<OnboardingStep, "done">[] = [1, 2, 3];
  return (
    <ol className="flex items-center justify-center" aria-label="온보딩 진행 단계">
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
              <span className={`text-[11.5px] lg:text-[13.5px] whitespace-nowrap ${label}`}>
                {STEP_LABELS[n]}
              </span>
            </div>
            {i < steps.length - 1 && (
              <span
                aria-hidden="true"
                className={`h-[1.5px] w-4 sm:w-7 lg:w-8 mx-1.5 lg:mx-3 self-start mt-[14px] lg:self-center lg:mt-0 rounded ${connectorDone ? "bg-primary" : "bg-line"}`}
              />
            )}
          </li>
        );
      })}
    </ol>
  );
}
