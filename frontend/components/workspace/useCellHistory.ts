import { useRef, useState } from "react";

/** 칸 글 한 번의 변경 — `from` 에서 `to` 로. */
type Step = { itemId: string; from: string; to: string };

/**
 * 칸 글 되돌리기 · 다시 하기 목록(월간 v1 · 주간). 저장이 끝난 변경만 쌓는다.
 * 되돌리기는 `from` 을, 다시 하기는 `to` 를 같은 칸 저장 API 로 다시 저장한다.
 */
export function useCellHistory() {
  const lists = useRef<{ undo: Step[]; redo: Step[] }>({ undo: [], redo: [] });
  // 단추가 읽는 길이 — 목록은 저장 줄(비동기)에서 바뀌어 ref 에 두고, 길이만 화면 상태로 비춘다.
  const [sizes, setSizes] = useState({ undo: 0, redo: 0 });
  const render = () =>
    setSizes({ undo: lists.current.undo.length, redo: lists.current.redo.length });
  /** 저장이 끝난 변경을 적는다. `replay` 는 되돌리기 · 다시 하기로 한 저장 — 새 변경은 다시 하기 목록을 비운다. */
  const record = (itemId: string, from: string, to: string, replay?: "undo" | "redo") => {
    if (from === to) return;
    if (replay === "undo") lists.current.redo.push({ itemId, from: to, to: from });
    else {
      lists.current.undo.push({ itemId, from, to });
      if (!replay) lists.current.redo = [];
    }
    render();
  };
  const pop = (direction: "undo" | "redo") => {
    const step = lists.current[direction].pop();
    render();
    return step && { itemId: step.itemId, text: direction === "undo" ? step.from : step.to };
  };
  /** 문서에서 빠진 칸의 걸음을 지운다 — 남기면 되돌리기가 없는 칸에 저장을 보내 404 가 난다. */
  const forget = (itemId: string) => {
    for (const key of ["undo", "redo"] as const)
      lists.current[key] = lists.current[key].filter((s) => s.itemId !== itemId);
    render();
  };
  return {
    record,
    pop,
    forget,
    canUndo: sizes.undo > 0,
    canRedo: sizes.redo > 0,
  };
}
