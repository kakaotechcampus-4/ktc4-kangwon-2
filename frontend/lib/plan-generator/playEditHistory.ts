import type { Selections } from "./playSelectionQueue";

/** 되돌리기 · 다시 하기 한 걸음. 고르기는 네 구간 전체, 칸은 한 번 저장으로 보낸 단위(칸 하나)다. */
export type EditStep =
  | { kind: "picks"; before: Selections; after: Selections }
  | { kind: "cell"; itemId: string; before: string; after: string };

export interface EditHistory {
  undo: EditStep[];
  redo: EditStep[];
}

/** 최근 30번까지만 되돌린다. */
export const HISTORY_LIMIT = 30;
export const EMPTY_HISTORY: EditHistory = { undo: [], redo: [] };

/** 새 변경이 오면 다시 하기 목록은 비운다. */
export const pushStep = (history: EditHistory, step: EditStep): EditHistory => ({
  undo: [...history.undo, step].slice(-HISTORY_LIMIT),
  redo: [],
});

/** 되돌릴 걸음을 꺼낸다. 꺼낸 걸음은 다시 하기 목록으로 간다. */
export function popUndo(history: EditHistory) {
  const step = history.undo.at(-1);
  if (!step) return null;
  return { step, history: { undo: history.undo.slice(0, -1), redo: [...history.redo, step] } };
}

export function popRedo(history: EditHistory) {
  const step = history.redo.at(-1);
  if (!step) return null;
  return { step, history: { undo: [...history.undo, step], redo: history.redo.slice(0, -1) } };
}

export type StepSave =
  { kind: "picks"; selections: Selections } | { kind: "cell"; itemId: string; value: string };

/**
 * 걸음을 되돌리거나 다시 할 때 보낼 저장. 지금 상태와 이미 같으면 null — 서버와 같아진 것은 보내지 않는다
 * (칸은 같은 값을 422 로 거절한다). 같은 두 API 만 쓴다.
 */
export function stepSave(
  step: EditStep,
  direction: "undo" | "redo",
  current: { selections: Selections; cellValue: (itemId: string) => string },
): StepSave | null {
  const target = direction === "undo" ? "before" : "after";
  if (step.kind === "cell") {
    const value = step[target];
    return value === current.cellValue(step.itemId)
      ? null
      : { kind: "cell", itemId: step.itemId, value };
  }
  const selections = step[target];
  return JSON.stringify(selections) === JSON.stringify(current.selections)
    ? null
    : { kind: "picks", selections };
}
