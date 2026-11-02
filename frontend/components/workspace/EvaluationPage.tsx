"use client";
import { useState } from "react";
import { WorkspacePage, ws } from "./WorkspaceUI";
import EvaluationChecklist from "./EvaluationChecklist";
import styles from "./Evaluation.module.css";

export default function EvaluationPage() {
  const [refresh, setRefresh] = useState(0);
  return (
    <WorkspacePage
      title="평가 점검"
      description="평가 때 보여줄 자료가 모였는지, 무엇을 더 쓰면 되는지 알려드려요."
      action={
        <button
          type="button"
          className={`${ws.secondary} ${styles.refresh}`}
          onClick={() => setRefresh((n) => n + 1)}
        >
          현황 새로고침
        </button>
      }
    >
      <EvaluationChecklist refresh={refresh} />
    </WorkspacePage>
  );
}
