"use client";

/**
 * 주간계획안 화면 (FR-304 · docs/weekly-plan-contract.md).
 *
 * 주소에 고른 계획안(`plan_id` · `class_id` · `week_id`)이 있으면 다듬기(Ⓦ3), 없으면 만들기(Ⓦ1).
 * 화면을 바꿀 때 주소도 바꿔 둔다 — 새로고침해도 같은 화면이다.
 * **월간을 확정해야 만든다** (§4-1 G3). 주는 부모 월간이 준 `week_id` 만 쓴다 (§3-1).
 */

import { useEffect, useState } from "react";
import { ApiError } from "@/lib/api/client";
import { getWeeklyPlan } from "@/lib/api/weekly";
import { classServerId } from "@/lib/api/onboarding";
import { planClassLine } from "@/lib/onboarding/types";
import type { WeeklyPlan } from "@/lib/api/types";
import { useClientState } from "@/lib/hooks/use-client-state";
import { archivePlanEntry } from "@/lib/workspace/document-archive";
import { WorkspacePage, Message, useClasses, ws } from "./WorkspaceUI";
import WeeklyEditor from "./WeeklyEditor";
import WeeklyNew from "./WeeklyNew";

function readArchiveEntry() {
  return archivePlanEntry(typeof window === "undefined" ? "" : window.location.search);
}
type Entry = NonNullable<ReturnType<typeof archivePlanEntry>>;

export default function WeeklyPlanPage() {
  const [entry, setEntry] = useClientState<Entry | null>(readArchiveEntry, null);
  const go = (next: Entry | null, month?: number) => {
    window.history.replaceState(
      null,
      "",
      next
        ? `/plans/weekly?plan_id=${next.id}&class_id=${next.classId}&week_id=${next.weekId}`
        : `/plans/weekly${month ? `?month=${month}` : ""}`,
    );
    setEntry(next);
  };
  if (!entry) return <WeeklyNew onOpen={go} />;
  return <WeeklyEdit key={entry.id} entry={entry} onBack={() => go(null, entry.month)} />;
}

function WeeklyEdit({ entry, onBack }: { entry: Entry; onBack: () => void }) {
  const [plan, setPlan] = useState<WeeklyPlan | null>(null);
  const [problem, setProblem] = useState("");
  const [message, setMessage] = useState("");
  const [reload, setReload] = useState(0);
  // 409 로 다시 불러올 때마다 올려 편집 화면을 새로 연다.
  const [loaded, setLoaded] = useState(-1);
  const classes = useClasses(setProblem);
  const klass = classes.find((c) => classServerId(c.id) === entry.classId);
  const className = klass ? planClassLine(klass) : "";

  useEffect(() => {
    let alive = true;
    getWeeklyPlan(entry.id).then(
      (next) => {
        if (!alive) return;
        setPlan(next);
        setProblem("");
        setLoaded(reload);
      },
      (e) => {
        if (!alive) return;
        setProblem(e instanceof ApiError ? e.message : "주간계획안을 불러오지 못했어요.");
        setLoaded(reload);
      },
    );
    return () => {
      alive = false;
    };
  }, [entry.id, reload]);

  if (plan && plan.class_id === entry.classId)
    return (
      <WeeklyEditor
        key={plan.id + ":" + loaded}
        plan={plan}
        onPlan={setPlan}
        onConflict={() => {
          setReload((n) => n + 1);
          setMessage("다른 곳에서 바뀌었어요. 최신 내용을 다시 불러왔어요.");
        }}
        onBack={onBack}
        className={className}
        notice={
          (message || problem) && (
            <>
              {message && (
                <p role="status" className="m-0">
                  {message}
                </p>
              )}
              {problem && (
                <p role="alert" className="m-0 text-[#8a2f2f]">
                  {problem}
                </p>
              )}
            </>
          )
        }
      />
    );

  return (
    <WorkspacePage
      title="주간계획안"
      description="확정한 월간계획안을 바탕으로 한 주 계획을 만들어요."
    >
      <Message error>{problem}</Message>
      {loaded < 0 && <p role="status">주간계획안을 불러오는 중…</p>}
      {loaded >= 0 && (
        <div className={ws.actions}>
          <button type="button" className={ws.secondary} onClick={() => setReload((n) => n + 1)}>
            다시 불러오기
          </button>
          <button type="button" className={ws.secondary} onClick={onBack}>
            ← 주간계획안 만들기
          </button>
        </div>
      )}
    </WorkspacePage>
  );
}
