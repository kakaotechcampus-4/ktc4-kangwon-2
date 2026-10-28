"use client";

import { useEffect, useRef, useState } from "react";
import { savePlaySelection, editPlayCell, isSaveConflict, isRejectedSave } from "@/lib/api/plans";
import {
  createSaveQueue,
  hasUnsentSave,
  type Rejected,
  type SaveStatus,
  type Selections,
} from "@/lib/plan-generator/playSelectionQueue";

/** 고른 놀이와 칸 글을 바로 저장한다. 큐 규칙은 `createSaveQueue` 가 정한다. */
export function usePlaySelectionSave(
  planId: number,
  revision: number,
  onConflict: () => Promise<void>,
  /** 저장이 끝까지 성공했을 때. */
  onSaved?: () => void,
  /** 서버가 받지 않아 버린 저장. 화면을 확인된 값으로 되돌린다. */
  onRejected?: (rejected: Rejected) => void,
  /** 처음 받은 계획안의 고르기. */
  selections: Selections = {},
  /** 입력 중이라 아직 큐에 안 들어간 글이 있는가 — 떠날 때 경고에 더한다. */
  drafting = false,
) {
  const [status, setStatus] = useState<SaveStatus>("idle");
  const [queue] = useState(() =>
    createSaveQueue({
      revision,
      selections,
      send: (selections, expected) => savePlaySelection(planId, selections, expected),
      sendCell: (itemId, value, expected) => editPlayCell(planId, itemId, value, expected),
      isConflict: isSaveConflict,
      isRejected: isRejectedSave,
      onRejected: (rejected) => onRejected?.(rejected),
      onStatus: (next) => {
        setStatus(next);
        if (next === "saved") onSaved?.();
      },
      onConflict,
    }),
  );
  // 이 화면이 이미 내려갔으면(409 뒤 새 계획안으로 다시 그려진 경우) 늦게 온 409 는 무시한다.
  // 입력창이 사라질 때의 저장이 먼저 큐에 들어가도록, 내리는 것은 한 박자 늦춘다. 다시 올라왔으면(개발 모드) 내리지 않는다.
  const mounts = useRef(0);
  useEffect(() => {
    const mine = ++mounts.current;
    const latest = () => mounts.current === mine;
    queue.setActive(true);
    return () =>
      queueMicrotask(() => {
        if (latest()) queue.setActive(false);
      });
  }, [queue]);
  const unsent = hasUnsentSave(status) || drafting;
  useEffect(() => {
    if (!unsent) return;
    const warn = (event: BeforeUnloadEvent) => event.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [unsent]);
  return {
    status,
    save: (selections: Selections) => queue.enqueue(selections),
    saveCell: (itemId: string, value: string, base: string) =>
      queue.enqueueCell(itemId, value, base),
    retry: () => queue.retry(),
    /** 남은 저장이 모두 끝나면 true, 멈췄으면 false. 확정 버튼이 부른다. */
    whenIdle: () => queue.whenIdle(),
  };
}
