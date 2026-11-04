"use client";
import { WorkspacePage } from "./WorkspaceUI";
import EvaluationChecklist from "./EvaluationChecklist";

export default function EvaluationPage() {
  return (
    <WorkspacePage
      title="평가 점검"
      description="평가 때 보여줄 서류가 모였는지, 무엇을 더 쓰면 되는지 봅니다."
    >
      {/* 「다시 세기」는 왼쪽 요약 칸 안에 있다. 머리 오른쪽 끝에 두면 무엇을 세는지 떨어져 보였다. */}
      <EvaluationChecklist />
    </WorkspacePage>
  );
}
