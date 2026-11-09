"use client";
import { TEACHER_DOCS } from "@/lib/workspace/evaluation-files";
import { WorkspacePage } from "./WorkspaceUI";
import EvaluationChecklist from "./EvaluationChecklist";
import { NameRule } from "./EvaluationSheet";

export default function EvaluationPage() {
  return (
    // 설명 한 줄은 지웠다 — 도장판 머리가 같은 말을 한다(2026-11-08). 빈 설명은 다른 화면과 같은 방식.
    <WorkspacePage title="평가 점검" description="" action={<AboutEvaluation />}>
      {/* 「다시 세기」는 도장판 머리의 기준일 옆에 있다. 화면 머리 오른쪽 끝에 두면 무엇을 세는지 떨어져 보였다. */}
      <EvaluationChecklist />
    </WorkspacePage>
  );
}

/**
 * 「평가제가 뭐예요?」 — 평가인증을 처음 준비하는 선생님이 이 화면이 무엇을 세는지 알게(멘토 11-05).
 * 누르면 펼치는 작은 쪽지. 사실은 ADR-019 근거(2025 자체평가 보고서 서식)만 적는다.
 * 화면 머리 오른쪽에 선다. 쪽지는 단추 밑에 떠서 열려도 제목 줄이 움직이지 않는다.
 */
function AboutEvaluation() {
  return (
    <details className="group relative text-[14px] text-ink-soft">
      <summary className="inline-flex min-h-11 cursor-pointer list-none items-center gap-2 font-bold text-primary-ink [&::-webkit-details-marker]:hidden">
        <span
          aria-hidden="true"
          className="grid h-6 w-6 place-items-center rounded-full border-[1.5px] border-primary-ink text-[13px]"
        >
          ?
        </span>
        평가제가 뭐예요?
      </summary>
      {/* 스마트폰(390)에서도 단추는 제목 줄 오른쪽에 남는다. 왼쪽에 맞춰 열면 쪽지가 화면 밖으로 나갔다. */}
      {/* 이름 규칙 여섯 줄이 들어가 길어졌다 — 낮은 창에서는 쪽지 안에서 스크롤한다(--app-vh, globals.css). */}
      <div className="absolute right-0 top-full z-20 mt-2 max-h-[calc(calc(100*var(--app-vh))-160px)] w-[min(420px,calc(100vw-32px))] overflow-y-auto rounded-md border border-line bg-paper px-4 py-3 leading-relaxed text-ink shadow-pg-card">
        <p className="m-0">
          <b>어린이집 평가제</b>는 한국보육진흥원이 어린이집을 정기적으로 평가하는 제도예요. 원은
          먼저 자체평가 지표(영역 6개 · 지표 15개)로 스스로 점검해요.
        </p>
        <p className="m-0 mt-2 text-ink-soft">
          이 화면은 그중 <b>쌤플 문서로 보여 줄 수 있는 서류</b>가 모였는지만 세요. 충족했는지는
          선생님께서 확인해 주세요.
        </p>
        {/* 서류마다 카드 쪽지에 흩어져 있던 이름 규칙을 한곳에서 본다(사용자 요청 11-09). */}
        <div className="mt-3 border-t border-dashed border-line pt-3">
          <p className="m-0 font-bold">파일 이름 규칙</p>
          <p className="m-0 mt-1 text-[13px] text-ink-soft">
            내 컴퓨터 폴더를 고르면 이 이름으로 서류를 찾아요.
          </p>
          <ul className="m-0 mt-2 grid list-none gap-2 p-0">
            {TEACHER_DOCS.map((doc) => (
              <li key={doc.id} className="text-[13px]">
                <b>{doc.title}</b>
                <span className="block text-ink-soft">
                  <NameRule doc={doc} />
                </span>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </details>
  );
}
