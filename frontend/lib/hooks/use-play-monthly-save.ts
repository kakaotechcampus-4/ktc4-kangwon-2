"use client";

import { useEffect, useRef, useState } from "react";
import {
  copyPlayMonthlyDrill,
  editPlayMonthlyCell,
  placePlayMonthlySafety,
  removePlayMonthlyActivity,
  removePlayMonthlyCell,
  resizePlayMonthlySplit,
  resizePlayMonthlyTable,
  splitPlayMonthlyCell,
} from "@/lib/api/playMonthly";
import { isRejectedSave, isSaveConflict } from "@/lib/api/plans";
import type { PlayMonthlyPlan, PlayMonthlyTimetableSize } from "@/lib/api/types";
import { boundaries } from "@/lib/plan-generator/playMonthlyTimetable";
import {
  EMPTY_HISTORY,
  cellValue,
  createPlayMonthlyQueue,
  drillTarget,
  grown,
  hasUnsentSave,
  moveStep,
  overlayCells,
  pushStep,
  remapHistory,
  removal,
  safetyOf,
  withSafety,
  withTimetableRatio,
  withTimetableSize,
  withoutActivity,
  withoutTimetableCell,
  type History,
  type RemovedCell,
  type IdleResult,
  type Job,
  type SaveStatus,
  type Step,
} from "@/lib/plan-generator/playMonthlyQueue";

export type PlayMonthlySave = {
  status: SaveStatus;
  /** 큐가 받았으면(또는 바꿀 것이 없으면) true. 확정 중 · 409 로 멈춘 뒤에는 false. */
  editCell(itemId: string, value: string): boolean;
  placeSafety(weekId: string, candidateItemId: string | null): void;
  removeActivity(itemId: string): void;
  copyDrill(itemId: string): boolean;
  /** 특별활동 시간표. 나누기는 새 id 를 서버가 정해 응답 뒤에 화면이 바뀐다 — 그동안 `structuring`. */
  splitCell(itemId: string, axis: "VERTICAL" | "HORIZONTAL"): boolean;
  /** 형제가 묶음이면 되돌릴 수 없어 되돌리기 목록을 비운다. */
  removeCell(itemId: string): boolean;
  resizeSplit(splitId: string, ratio: number): void;
  resizeTable(size: PlayMonthlyTimetableSize): void;
  /** 응답을 기다리는 구조 변경(나누기 · 되살리기)이 있다 — 그동안 편집을 잠근다. */
  structuring: boolean;
  whenIdle(): Promise<IdleResult>;
  freeze(): void;
  unfreeze(): void;
  retry(): void;
  /** 큐가 받았으면 true. */
  undo(): boolean;
  redo(): boolean;
  canUndo: boolean;
  canRedo: boolean;
};

function call(id: number, job: Job, revision: number): Promise<PlayMonthlyPlan> {
  switch (job.kind) {
    case "cell":
      return editPlayMonthlyCell(id, job.itemId, job.value, revision);
    case "safety":
      return placePlayMonthlySafety(id, job.weekId, job.candidateItemId, revision);
    case "remove":
      return removePlayMonthlyActivity(id, job.itemId, revision);
    case "copy":
      return copyPlayMonthlyDrill(id, job.itemId, revision);
    case "split":
      return splitPlayMonthlyCell(id, job.itemId, job.axis, revision);
    case "removeCell":
      return removePlayMonthlyCell(id, job.itemId, revision);
    case "ratio":
      return resizePlayMonthlySplit(id, job.splitId, job.ratio, revision);
    case "size":
      return resizePlayMonthlyTable(id, job.size, revision);
    case "restore":
      return restore(id, job.step, revision);
  }
}
/** 되살리기가 나누기 뒤에 멈췄다 — 다시 보내면 또 나뉘므로 충돌처럼 새로 불러온다. */
const MIDWAY = new Error("timetable restore stopped after the split");
/** 뺀 칸 되살리기: 형제를 같은 축으로 나누고(원래 칸이 위 · 왼쪽에 남는다) 글 · 비율을 되돌린다. */
async function restore(id: number, step: RemovedCell, revision: number) {
  let plan = await splitPlayMonthlyCell(id, step.siblingId, step.axis, revision);
  try {
    const { newId, splitId } = grown(plan, step.siblingId);
    const sibling = cellValue(plan, step.siblingId) ?? "";
    const writes = step.first
      ? [
          [step.siblingId, step.text],
          [newId, sibling],
        ]
      : [[newId, step.text]];
    for (const [itemId, text] of writes)
      if (text.trim() !== (cellValue(plan, itemId) ?? "").trim())
        plan = await editPlayMonthlyCell(id, itemId, text, plan.revision);
    if (step.ratio !== 50)
      plan = await resizePlayMonthlySplit(id, splitId, step.ratio, plan.revision);
  } catch {
    throw MIDWAY;
  }
  return plan;
}

/**
 * 놀이 월간의 모든 쓰기를 한 줄로 저장한다(규칙은 `createPlayMonthlyQueue`). 바꾼 값은 `onPlan` 으로 화면에 바로 입히고,
 * 큐가 비면 서버가 돌려준 계획안으로 맞춘다. 거절(422)이면 **그 작업의 칸 · 주만** 서버 값으로 되돌리고
 * (다른 대기 작업의 값은 화면에 남긴다) `onRejected(칸 item_id)` 를 부른다. `drafting` 은 입력 중이라 아직 큐에 안 들어간 글이 있다는 뜻이다.
 */
export function usePlayMonthlySave(
  plan: PlayMonthlyPlan,
  onPlan: (plan: PlayMonthlyPlan) => void,
  onConflict: () => void,
  /** 거절돼 되돌린 칸의 item_id(복사면 붙여 넣은 칸). 안전 배치 · 삭제가 거절됐으면 null. kind 는 거절된 작업 종류. */
  onRejected?: (itemId: string | null, kind: Job["kind"]) => void,
  /** 입력 중인 미저장 글이 있는가 — 떠날 때 경고에 더한다. */
  drafting = false,
): PlayMonthlySave {
  const [status, setStatus] = useState<SaveStatus>("idle");
  const [history, setHistoryState] = useState<History>(EMPTY_HISTORY);
  const [structuring, setStructuring] = useState(false);
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
  // 나누기 · 되살리기 응답에서 새 id 를 읽어 걸음을 쌓거나 목록의 옛 id 를 바꾼다.
  function settled(job: Job, fresh: PlayMonthlyPlan) {
    if (job.kind === "split") {
      const made = grown(fresh, job.itemId);
      setHistory(
        job.was
          ? remapHistory(past.current, {
              [job.was.newId]: made.newId,
              [job.was.splitId]: made.splitId,
            })
          : pushStep(past.current, { kind: "split", itemId: job.itemId, axis: job.axis, ...made }),
      );
    } else if (job.kind === "restore") {
      const { step } = job;
      const made = grown(fresh, step.siblingId);
      // 뺀 칸이 첫 갈래였으면 그 글은 형제 id 로, 형제 글은 새 칸으로 갔다.
      setHistory(
        remapHistory(
          past.current,
          step.first
            ? {
                [step.itemId]: step.siblingId,
                [step.siblingId]: made.newId,
                [step.splitId]: made.splitId,
              }
            : { [step.itemId]: made.newId, [step.splitId]: made.splitId },
        ),
      );
    }
  }

  // 큐의 콜백은 보낼 때(렌더 밖)에만 ref 를 읽는다.
  // eslint-disable-next-line react-hooks/refs
  const [queue] = useState(() =>
    createPlayMonthlyQueue({
      revision: plan.revision,
      serverValue: (itemId) => cellValue(server.current, itemId),
      send: async (job, expected) => {
        server.current = await call(plan.id, job, expected);
        settled(job, server.current);
        return { revision: server.current.revision };
      },
      isConflict: (error) => error === MIDWAY || isSaveConflict(error),
      isRejected: isRejectedSave,
      onStatus: setStatus,
      onRejected: (job) => {
        // 거절된 작업의 칸 · 주만 서버 확인값으로 되돌린다. 뒤에 대기 중인 다른 작업의 낙관값은 그대로 둔다.
        apply(
          job.kind === "cell"
            ? overlayCells(view.current, {
                [job.itemId]: cellValue(server.current, job.itemId) ?? "",
              })
            : job.kind === "safety"
              ? withSafety(view.current, job.weekId, safetyOf(server.current, job.weekId))
              : server.current, // ponytail: 삭제 · 복사 거절은 드물어 통째로 서버 계획안(대기 변경은 큐가 비면 다시 맞춰진다)
        );
        // 남은 걸음의 before 가 거짓이 될 수 있어 목록을 비운다.
        setHistory(EMPTY_HISTORY);
        setStructuring(false);
        latest.current.onRejected?.(
          job.kind === "cell"
            ? job.itemId
            : job.kind === "copy"
              ? (drillTarget(view.current) ?? null)
              : null,
          job.kind,
        );
      },
      onDrained: () => {
        setStructuring(false);
        apply(server.current);
      },
      onConflict: () => {
        setStructuring(false);
        if (mounted.current) latest.current.onConflict();
      },
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

  // 응답 뒤에야 모양을 아는 구조 변경 — 화면은 큐가 빈 뒤 서버 계획안으로 바뀐다.
  function later(job: Job) {
    if (!queue.enqueue(job)) return false;
    setStructuring(true);
    return true;
  }

  // 되돌리기 = 반대 요청을 같은 줄로 보낸다. 나누기의 반대는 새 칸 빼기, 칸 빼기의 반대는 되살리기.
  function opposite(step: Step, undo: boolean): [Job, PlayMonthlyPlan | null] {
    const v = view.current;
    const target = undo ? "before" : "after";
    switch (step.kind) {
      case "cell":
        return [
          { kind: "cell", itemId: step.itemId, value: step[target] },
          overlayCells(v, { [step.itemId]: step[target] }),
        ];
      case "safety":
        return [
          { kind: "safety", weekId: step.weekId, candidateItemId: step[target] },
          withSafety(v, step.weekId, step[target]),
        ];
      case "ratio":
        return [
          { kind: "ratio", splitId: step.splitId, ratio: step[target] },
          withTimetableRatio(v, step.splitId, step[target]),
        ];
      case "size":
        return [{ kind: "size", size: step[target] }, withTimetableSize(v, step[target])];
      case "split":
        return undo
          ? [{ kind: "removeCell", itemId: step.newId }, withoutTimetableCell(v, step.newId)]
          : [{ kind: "split", itemId: step.itemId, axis: step.axis, was: step }, null];
      case "removeCell":
        return undo
          ? [{ kind: "restore", step }, null]
          : [{ kind: "removeCell", itemId: step.itemId }, withoutTimetableCell(v, step.itemId)];
    }
  }
  function through(direction: "undo" | "redo") {
    const moved = moveStep(past.current, direction);
    if (!moved) return false;
    const [job, next] = opposite(moved.step, direction === "undo");
    if (!queue.enqueue(job)) return false;
    if (next) apply(next);
    else setStructuring(true);
    setHistory(moved.history);
    return true;
  }

  const unsent = hasUnsentSave(status) || drafting;
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
      if (before === undefined || before === value) return true;
      return setCell(itemId, value, { kind: "cell", itemId, before, after: value });
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
    // 복사는 붙여 넣을 글을 알고 있으니 화면에 바로 입힌다(열린 입력창도 이 글로 다시 열린다).
    copyDrill: (itemId) => {
      const target = drillTarget(view.current);
      const text = view.current.drill_candidates.find((d) => d.cell.item_id === itemId)?.cell.value;
      const next =
        target !== undefined && text !== undefined
          ? overlayCells(view.current, { [target]: text })
          : null;
      return submit({ kind: "copy", itemId }, next, null);
    },
    splitCell: (itemId, axis) => later({ kind: "split", itemId, axis }),
    removeCell: (itemId) => {
      const step = removal(view.current, itemId);
      if (step === undefined) return false;
      return submit(
        { kind: "removeCell", itemId },
        withoutTimetableCell(view.current, itemId),
        step,
      );
    },
    resizeSplit: (splitId, ratio) => {
      const before = view.current.special_activity
        .flatMap(boundaries)
        .find((b) => b.split_id === splitId)?.ratio;
      if (before == null || before === ratio) return;
      submit({ kind: "ratio", splitId, ratio }, withTimetableRatio(view.current, splitId, ratio), {
        kind: "ratio",
        splitId,
        before,
        after: ratio,
      });
    },
    resizeTable: (size) => {
      const before = view.current.special_activity_size;
      if (JSON.stringify(before) === JSON.stringify(size)) return;
      submit({ kind: "size", size }, withTimetableSize(view.current, size), {
        kind: "size",
        before,
        after: size,
      });
    },
    structuring,
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
