"use client";

import { useEffect, useState } from "react";
import { savePlaySelection, isSaveConflict } from "@/lib/api/plans";
import {
  createSaveQueue,
  hasUnsentSave,
  type SaveStatus,
  type Selections,
} from "@/lib/plan-generator/playSelectionQueue";

/** 고른 놀이를 바로 저장한다. 큐 규칙은 `createSaveQueue` 가 정한다. */
export function usePlaySelectionSave(
  planId: number,
  revision: number,
  onConflict: () => Promise<void>,
  /** 저장이 끝까지 성공했을 때. */
  onSaved?: () => void,
) {
  const [status, setStatus] = useState<SaveStatus>("idle");
  const [queue] = useState(() =>
    createSaveQueue({
      revision,
      send: (selections, expected) => savePlaySelection(planId, selections, expected),
      isConflict: isSaveConflict,
      onStatus: (next) => {
        setStatus(next);
        if (next === "saved") onSaved?.();
      },
      onConflict,
    }),
  );
  // 이 화면이 이미 내려갔으면(409 뒤 새 계획안으로 다시 그려진 경우) 늦게 온 409 는 무시한다.
  useEffect(() => {
    queue.setActive(true);
    return () => queue.setActive(false);
  }, [queue]);
  const unsent = hasUnsentSave(status);
  useEffect(() => {
    if (!unsent) return;
    const warn = (event: BeforeUnloadEvent) => event.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [unsent]);
  return {
    status,
    save: (selections: Selections) => queue.enqueue(selections),
    retry: () => queue.retry(),
  };
}
