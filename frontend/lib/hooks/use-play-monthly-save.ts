"use client";

import { useEffect, useRef, useState } from "react";
import {
  copyPlayMonthlyDrill,
  editPlayMonthlyCell,
  placePlayMonthlySafety,
  removePlayMonthlyActivity,
} from "@/lib/api/playMonthly";
import { isRejectedSave, isSaveConflict } from "@/lib/api/plans";
import type { PlayMonthlyPlan } from "@/lib/api/types";
import {
  EMPTY_HISTORY,
  cellValue,
  createPlayMonthlyQueue,
  hasUnsentSave,
  moveStep,
  overlayCells,
  pushStep,
  safetyOf,
  withSafety,
  withoutActivity,
  type History,
  type IdleResult,
  type Job,
  type SaveStatus,
  type Step,
} from "@/lib/plan-generator/playMonthlyQueue";

export type PlayMonthlySave = {
  status: SaveStatus;
  editCell(itemId: string, value: string): void;
  placeSafety(weekId: string, candidateItemId: string | null): void;
  removeActivity(itemId: string): void;
  copyDrill(itemId: string): void;
  whenIdle(): Promise<IdleResult>;
  freeze(): void;
  unfreeze(): void;
  retry(): void;
  undo(): void;
  redo(): void;
  canUndo: boolean;
  canRedo: boolean;
};

const call = (id: number, job: Job, revision: number) =>
  job.kind === "cell"
    ? editPlayMonthlyCell(id, job.itemId, job.value, revision)
    : job.kind === "safety"
      ? placePlayMonthlySafety(id, job.weekId, job.candidateItemId, revision)
      : job.kind === "remove"
        ? removePlayMonthlyActivity(id, job.itemId, revision)
        : copyPlayMonthlyDrill(id, job.itemId, revision);

/**
 * 놀이 월간의 모든 쓰기를 한 줄로 저장한다(규칙은 `createPlayMonthlyQueue`). 바꾼 값은 `onPlan` 으로 화면에 바로 입히고,
 * 큐가 비면 서버가 돌려준 계획안으로 맞춘다. 거절(422)이면 서버 값으로 되돌리고 `onRejected` 를 부른다.
 */
export function usePlayMonthlySave(
  plan: PlayMonthlyPlan,
  onPlan: (plan: PlayMonthlyPlan) => void,
  onConflict: () => void,
  onRejected?: () => void,
): PlayMonthlySave {
  const [status, setStatus] = useState<SaveStatus>("idle");
  const [history, setHistoryState] = useState<History>(EMPTY_HISTORY);
  // view: 지금 화면의 계획안(낙관 반영 포함) · server: 마지막으로 서버가 돌려준 계획안.
  const view = useRef(plan);
  const server = useRef(plan);
  const past = useRef(history);
  const mounted = useRef(true);
  const latest = useRef({ onPlan, onConflict, onRejected });
  useEffect(() => {
    view.current = plan;
    latest.current = { onPlan, onConflict, onRejected };
  });
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);
  const setHistory = (next: History) => setHistoryState((past.current = next));
  const apply = (next: PlayMonthlyPlan) => {
    view.current = next;
    latest.current.onPlan(next);
  };

  // 큐의 콜백은 보낼 때(렌더 밖)에만 ref 를 읽는다.
  // eslint-disable-next-line react-hooks/refs
  const [queue] = useState(() =>
    createPlayMonthlyQueue({
      revision: plan.revision,
      serverValue: (itemId) => cellValue(server.current, itemId),
      send: async (job, expected) => {
        server.current = await call(plan.id, job, expected);
        return { revision: server.current.revision };
      },
      isConflict: isSaveConflict,
      isRejected: isRejectedSave,
      onStatus: setStatus,
      onRejected: () => {
        apply(server.current);
        // 되돌릴 걸음이 서버와 어긋났을 수 있어 목록을 비운다.
        setHistory(EMPTY_HISTORY);
        latest.current.onRejected?.();
      },
      onDrained: () => apply(server.current),
      onConflict: () => mounted.current && latest.current.onConflict(),
    }),
  );

  // 큐가 받았을 때만 화면에 입히고 걸음을 쌓는다. step 이 null 이면 되돌릴 수 없는 작업이다.
  function submit(job: Job, next: PlayMonthlyPlan | null, step: Step | null) {
    if (!queue.enqueue(job)) return false;
    if (next) apply(next);
    // 행 삭제 · 훈련 복사는 되돌리기 목록에 없다 — 사이에 끼면 옛 걸음이 거짓이 되므로 목록을 비운다.
    setHistory(step ? pushStep(past.current, step) : EMPTY_HISTORY);
    return true;
  }
  const setCell = (itemId: string, value: string, step: Step | null) =>
    submit({ kind: "cell", itemId, value }, overlayCells(view.current, { [itemId]: value }), step);
  const setSafety = (weekId: string, candidateItemId: string | null, step: Step | null) =>
    submit(
      { kind: "safety", weekId, candidateItemId },
      withSafety(view.current, weekId, candidateItemId),
      step,
    );

  function through(direction: "undo" | "redo") {
    const moved = moveStep(past.current, direction);
    if (!moved) return;
    const { step } = moved;
    const target = direction === "undo" ? "before" : "after";
    const ok =
      step.kind === "cell"
        ? queue.enqueue({ kind: "cell", itemId: step.itemId, value: step[target] })
        : queue.enqueue({ kind: "safety", weekId: step.weekId, candidateItemId: step[target] });
    if (!ok) return;
    apply(
      step.kind === "cell"
        ? overlayCells(view.current, { [step.itemId]: step[target] })
        : withSafety(view.current, step.weekId, step[target]),
    );
    setHistory(moved.history);
  }

  const unsent = hasUnsentSave(status);
  useEffect(() => {
    if (!unsent) return;
    const warn = (event: BeforeUnloadEvent) => event.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [unsent]);

  return {
    status,
    editCell: (itemId, value) => {
      const before = cellValue(view.current, itemId);
      if (before === undefined || before === value) return;
      setCell(itemId, value, { kind: "cell", itemId, before, after: value });
    },
    placeSafety: (weekId, candidateItemId) => {
      const before = safetyOf(view.current, weekId);
      if (before === candidateItemId) return;
      setSafety(weekId, candidateItemId, {
        kind: "safety",
        weekId,
        before,
        after: candidateItemId,
      });
    },
    removeActivity: (itemId) => {
      const row = [...view.current.together, ...view.current.free_play].find(
        (r) => r.activity_id === itemId,
      );
      if (!row) return;
      submit(
        {
          kind: "remove",
          itemId,
          cellIds: [row.name.item_id, row.description.item_id],
        },
        withoutActivity(view.current, itemId),
        null,
      );
    },
    copyDrill: (itemId) => void submit({ kind: "copy", itemId }, null, null),
    whenIdle: () => queue.whenIdle(),
    freeze: () => queue.freeze(),
    unfreeze: () => queue.unfreeze(),
    retry: () => queue.retry(),
    undo: () => through("undo"),
    redo: () => through("redo"),
    canUndo: history.undo.length > 0,
    canRedo: history.redo.length > 0,
  };
}
