import { apiRequest } from "./client";
import type { GenerationRun } from "./types";

/** 생성 기록 (docs/api-spec.md §9-8). 생성 POST 에 이 헤더로 id 를 주면 그 id 로 기록이 남는다. */
export const RUN_HEADER = "X-Generation-Run-Id";

/** 요청마다 새로 만든다. 안전한 출처가 아니라 못 만들면 `undefined` — 그러면 헤더 없이 보낸다. */
export const newRunId = (): string | undefined => globalThis.crypto?.randomUUID?.();

/** 헤더 한 칸. id 가 없으면 아무것도 붙이지 않는다. */
export const runHeaders = (runId?: string): Record<string, string> =>
  runId ? { [RUN_HEADER]: runId } : {};

export const getGenerationRun = (id: string, signal?: AbortSignal) =>
  apiRequest<GenerationRun>("/api/generation-runs/" + id, { signal });

/**
 * `every` ms 마다 그 생성의 단계를 물어 `onStage` 로 넘긴다. 겹쳐 묻지 않는다(끝난 뒤 다시 기다린다).
 * 조회 실패는 삼키고 다음 차례에 다시 묻는다 — 404(첫 기록 전) · 5xx · 연결 오류 모두 생성 실패가 아니다.
 * RUNNING 이 아니면 멈춘다. `signal` 이 끊기면 기다림 · 조회 · 콜백 모두 하지 않는다.
 */
export async function watchStage(
  id: string,
  onStage: (stage: string) => void,
  signal: AbortSignal,
  every = 2000,
) {
  while (!signal.aborted) {
    await new Promise((resolve) => setTimeout(resolve, every));
    if (signal.aborted) return;
    try {
      const run = await getGenerationRun(id, signal);
      if (signal.aborted) return;
      onStage(run.stage);
      if (run.status !== "RUNNING") return;
    } catch {}
  }
}
