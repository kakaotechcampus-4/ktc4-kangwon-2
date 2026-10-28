import type { PlayMonthlyPlan } from "../api/types";

export type SaveStatus = "idle" | "saving" | "saved" | "failed";

/** 놀이 월간의 쓰기 4종. 모두 같은 revision 을 올리므로 한 줄로 보낸다. */
export type Job =
  | { kind: "cell"; itemId: string; value: string }
  | { kind: "safety"; weekId: string; candidateItemId: string | null }
  /** `cellIds` 는 그 행의 이름 · 설명 칸 — 행이 사라지면 그 칸에 대한 대기 중 글은 버린다. */
  | { kind: "remove"; itemId: string; cellIds: string[] }
  | { kind: "copy"; itemId: string };

export interface IdleResult {
  saved: boolean;
  revision: number;
}

/** 보내지 못한 저장이 남아 있는가 — 탭을 닫기 전에 경고할 때만 참이다. */
export const hasUnsentSave = (status: SaveStatus) => status === "saving" || status === "failed";

interface Options {
  revision: number;
  /** 서버가 확인한 칸 값. 보내기 직전에 같으면 보내지 않는다(서버는 같은 값을 422 로 거절한다). */
  serverValue: (itemId: string) => string | undefined;
  /** 한 번 보낸다. 성공하면 응답의 새 revision. */
  send: (job: Job, expectedRevision: number) => Promise<{ revision: number }>;
  /** 409 `STALE_WRITE` · `ALREADY_CONFIRMED`. */
  isConflict: (error: unknown) => boolean;
  /** 서버가 받지 않는 것(422). 다시 보내도 같은 답이라 그 작업만 버린다. */
  isRejected: (error: unknown) => boolean;
  onStatus: (status: SaveStatus) => void;
  /** 거절된 작업을 버렸다 — 화면을 서버 값으로 되돌린다. */
  onRejected: (job: Job) => void;
  /** 쌓인 작업이 모두 끝났다(성공 · 거절). 화면을 서버가 확인한 계획안으로 맞춘다. */
  onDrained: () => void;
  /** 409 로 멈췄다. 부모가 다시 불러온다. */
  onConflict: () => void;
}

/**
 * 놀이 월간 저장 큐. 한 번에 하나만, 들어온 순서대로 보내고 응답 revision 을 다음 요청에 넘긴다.
 * 칸 글은 같은 칸의 대기 중 글 하나로 합친다 — 단, 그 뒤에 다른 종류 작업이 있으면 합치지 않는다
 * (복사가 같은 칸을 덮어쓰는데 옛 글이 복사 뒤로 가면 안 된다). 보내는 중인 작업은 합치지 않는다.
 * 네트워크 오류 · 5xx 는 그 작업을 맨 앞에 둔 채 멈추고 `retry` 가 다시 보낸다. 자동 재시도는 없다.
 * 422 는 그 작업만 버리고 계속한다. 409 는 모두 버리고 멈춘다 — 이 큐는 더 받지 않는다.
 */
export function createPlayMonthlyQueue(options: Options) {
  let revision = options.revision;
  let jobs: Job[] = [];
  let busy = false;
  let frozen = false;
  let stopped = false;
  let rejections = 0;
  let status: SaveStatus = "idle";
  const waiters: ((result: IdleResult) => void)[] = [];

  const setStatus = (next: SaveStatus) => options.onStatus((status = next));
  const settle = (saved = !stopped && jobs.length === 0) =>
    waiters.splice(0).forEach((resolve) => resolve({ saved, revision }));

  async function pump() {
    if (busy || jobs.length === 0) return;
    busy = true;
    let changed = false;
    while (jobs.length > 0) {
      const job = jobs[0];
      if (job.kind === "cell" && job.value === options.serverValue(job.itemId)) {
        jobs.shift();
        continue;
      }
      setStatus("saving");
      try {
        revision = (await options.send(job, revision)).revision;
        jobs.shift();
        changed = true;
      } catch (error) {
        if (options.isConflict(error)) {
          jobs = [];
          stopped = true;
          busy = false;
          setStatus("idle");
          settle(false);
          options.onConflict();
          return;
        }
        if (!options.isRejected(error)) {
          busy = false;
          setStatus("failed");
          settle();
          return;
        }
        jobs.shift();
        rejections++;
        changed = true;
        options.onRejected(job);
      }
    }
    busy = false;
    if (changed) options.onDrained();
    if (changed || status === "saving" || status === "failed") setStatus("saved");
    settle();
  }

  return {
    /** 받았으면 true. 확정을 시작했거나(freeze) 409 로 멈췄으면 받지 않는다. */
    enqueue(job: Job) {
      if (frozen || stopped) return false;
      if (job.kind === "cell") {
        const last = jobs.findLastIndex((j) => j.kind === "cell" && j.itemId === job.itemId);
        const mergeable =
          last >= (busy ? 1 : 0) && !jobs.slice(last + 1).some((j) => j.kind !== "cell");
        if (mergeable) jobs[last] = job;
        else jobs.push(job);
      } else {
        if (job.kind === "remove")
          jobs = jobs.filter(
            (j, i) => !(j.kind === "cell" && job.cellIds.includes(j.itemId) && !(busy && i === 0)),
          );
        jobs.push(job);
      }
      void pump();
      return true;
    },
    retry() {
      void pump();
    },
    /** 보낼 것도 보내는 중인 것도 없어질 때까지 기다린다. 기다리는 사이 422 가 있었거나 409 로 멈췄으면 `saved` false. */
    whenIdle() {
      if (!busy)
        return Promise.resolve<IdleResult>({ saved: !stopped && jobs.length === 0, revision });
      const start = rejections;
      return new Promise<IdleResult>((resolve) =>
        waiters.push((r) => resolve(rejections === start ? r : { ...r, saved: false })),
      );
    },
    /** 확정 시작 — 이후 새 작업을 받지 않는다. */
    freeze() {
      frozen = true;
    },
    unfreeze() {
      frozen = false;
    },
  };
}

// ---- 화면에 바로 입히는 순수 함수 (저장은 큐가, 화면은 이것이) ----

type Node = unknown;
const isObject = (node: Node): node is Record<string, unknown> =>
  typeof node === "object" && node !== null;

/** 계획안 안의 칸(`item_id` 가 있는 객체) 값을 바꾼 새 계획안. 바뀐 곳이 없으면 같은 객체를 돌려준다. */
export function overlayCells(plan: PlayMonthlyPlan, values: Record<string, string>) {
  const walk = (node: Node): Node => {
    if (Array.isArray(node)) {
      const next = node.map(walk);
      return next.some((v, i) => v !== node[i]) ? next : node;
    }
    if (!isObject(node)) return node;
    const own = typeof node.item_id === "string" ? values[node.item_id] : undefined;
    let copy: Record<string, unknown> | null = null;
    for (const [key, child] of Object.entries(node)) {
      const next = key === "value" && own !== undefined ? own : walk(child);
      if (next !== child) (copy ??= { ...node })[key] = next;
    }
    return copy ?? node;
  };
  return walk(plan) as PlayMonthlyPlan;
}

/** 칸 하나의 값. 없는 칸이면 undefined. */
export function cellValue(plan: PlayMonthlyPlan, itemId: string): string | undefined {
  const find = (node: Node): string | undefined => {
    if (Array.isArray(node)) return node.map(find).find((v) => v !== undefined);
    if (!isObject(node)) return undefined;
    if (node.item_id === itemId && typeof node.value === "string") return node.value;
    return Object.values(node)
      .map(find)
      .find((v) => v !== undefined);
  };
  return find(plan);
}

export const safetyOf = (plan: PlayMonthlyPlan, weekId: string) =>
  plan.safety_weeks.find((w) => w.week_id === weekId)?.candidate_item_id ?? null;

export const withSafety = (
  plan: PlayMonthlyPlan,
  weekId: string,
  candidateItemId: string | null,
): PlayMonthlyPlan => ({
  ...plan,
  safety_weeks: plan.safety_weeks.map((w) =>
    w.week_id === weekId ? { ...w, candidate_item_id: candidateItemId } : w,
  ),
});

export const withoutActivity = (plan: PlayMonthlyPlan, itemId: string): PlayMonthlyPlan => ({
  ...plan,
  together: plan.together.filter((row) => row.activity_id !== itemId),
  free_play: plan.free_play.filter((row) => row.activity_id !== itemId),
});

// ---- 되돌리기 · 다시 하기 (칸 글 · 안전 배치만, 30번) ----

export type Step =
  | { kind: "cell"; itemId: string; before: string; after: string }
  | { kind: "safety"; weekId: string; before: string | null; after: string | null };
export interface History {
  undo: Step[];
  redo: Step[];
}
export const HISTORY_LIMIT = 30;
export const EMPTY_HISTORY: History = { undo: [], redo: [] };

/** 새 변경이 오면 다시 하기 목록은 비운다. */
export const pushStep = (h: History, step: Step): History => ({
  undo: [...h.undo, step].slice(-HISTORY_LIMIT),
  redo: [],
});

/** 한 걸음을 꺼내 반대쪽 목록으로 옮긴다. 없으면 null. */
export function moveStep(h: History, direction: "undo" | "redo") {
  const from = h[direction];
  const step = from.at(-1);
  if (!step) return null;
  const to = direction === "undo" ? h.redo : h.undo;
  const rest = from.slice(0, -1);
  return {
    step,
    history:
      direction === "undo"
        ? { undo: rest, redo: [...to, step] }
        : { undo: [...to, step], redo: rest },
  };
}
