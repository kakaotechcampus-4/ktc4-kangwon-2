"use client";
import { WorkspacePage } from "./WorkspaceUI";
import EvaluationChecklist from "./EvaluationChecklist";

export default function EvaluationPage() {
  return (
    <WorkspacePage
      title="평가 점검"
      description="평가 때 보여줄 서류가 모였는지, 무엇을 더 쓰면 되는지 봅니다."
    >
      <AboutEvaluation />
      {/* 「다시 세기」는 왼쪽 요약 칸 안에 있다. 머리 오른쪽 끝에 두면 무엇을 세는지 떨어져 보였다. */}
      <EvaluationChecklist />
    </WorkspacePage>
  );
}

/**
 * 「평가제가 뭐예요?」 — 평가인증을 처음 준비하는 선생님이 이 화면이 무엇을 세는지 알게(멘토 11-05).
 * 누르면 펼치는 작은 쪽지. 사실은 ADR-019 근거(2025 자체평가 보고서 서식)만 적는다.
 */
function AboutEvaluation() {
  return (
    <details className="group mb-4 max-w-[640px] text-[14px] text-ink-soft">
      <summary className="inline-flex min-h-9 cursor-pointer list-none items-center gap-2 font-bold text-primary-ink [&::-webkit-details-marker]:hidden">
        <span
          aria-hidden="true"
          className="grid h-6 w-6 place-items-center rounded-full border-[1.5px] border-primary-ink text-[13px]"
        >
          ?
        </span>
        평가제가 뭐예요?
      </summary>
      <div className="mt-2 rounded-md border border-line bg-paper px-4 py-3 leading-relaxed text-ink">
        <p className="m-0">
          <b>어린이집 평가제</b>는 한국보육진흥원이 어린이집을 정기적으로 평가하는 제도예요. 원은
          먼저 자체평가 지표(영역 6개 · 지표 15개)로 스스로 점검해요.
        </p>
        <p className="m-0 mt-2 text-ink-soft">
          이 화면은 그중 <b>쌤플 문서로 보여 줄 수 있는 서류</b>가 모였는지만 세요. 충족했는지는
          선생님께서 확인해 주세요.
        </p>
      </div>
    </details>
  );
}
