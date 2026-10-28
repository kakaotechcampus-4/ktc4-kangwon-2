export type SaveStatus = "idle" | "saving" | "saved" | "failed" | "reloading";
export type Selections = Record<string, string[]>;

/** 보내지 못한 저장이 남아 있는가 — 탭을 닫기 전에 경고할 때만 참이다. 409 로 버린 변경은 남은 저장이 아니다. */
export const hasUnsentSave = (status: SaveStatus) => status === "saving" || status === "failed";

/** `whenIdle` 의 답. `revision` 은 마지막으로 성공한 응답의 revision 이다(저장이 없었으면 처음 revision). */
export interface IdleResult {
  saved: boolean;
  revision: number;
}

/** 서버가 받지 않아 버린 저장 — 화면은 이 값(서버가 확인한 값)으로 되돌린다. */
export type Rejected =
  { kind: "picks"; selections: Selections } | { kind: "cell"; itemId: string; value: string };

interface Options {
  /** 처음 받은 계획안의 revision. */
  revision: number;
  /** 처음 받은 계획안의 고르기 — 고르기 저장이 거절되면 이 값(또는 마지막으로 저장된 값)으로 되돌린다. */
  selections: Selections;
  /** 고르기를 한 번 보낸다. 성공하면 응답의 새 revision 을 돌려준다. */
  send: (selections: Selections, expectedRevision: number) => Promise<{ revision: number }>;
  /** 칸 하나를 한 번 보낸다. */
  sendCell: (
    itemId: string,
    value: string,
    expectedRevision: number,
  ) => Promise<{ revision: number }>;
  /** 다른 곳에서 바뀐 것(409 `STALE_WRITE` · `ALREADY_CONFIRMED`)인지. */
  isConflict: (error: unknown) => boolean;
  /** 서버가 이 저장을 받지 않는 것(409 가 아닌 4xx)인지. 다시 보내도 같은 답이라 그 저장만 버린다. */
  isRejected: (error: unknown) => boolean;
  onStatus: (status: SaveStatus) => void;
  /** 거절된 저장을 버렸다. 화면을 서버가 확인한 값으로 되돌린다. */
  onRejected: (rejected: Rejected) => void;
  /** 최신 계획안을 다시 불러온다. 끝나면(성공이든 실패든) 돌려준다. */
  onConflict: () => Promise<void>;
}

type Job =
  { kind: "picks"; selections: Selections } | { kind: "cell"; itemId: string; value: string };

/**
 * 놀이 프로젝트 저장 큐 (ADR-044 §1 · §2). 고르기와 칸 글은 같은 revision 을 올리므로 한 줄로 보낸다.
 * 한 번에 하나만 보내고, 응답 revision 을 다음 요청에 넘긴다.
 * 기다리는 고르기가 있으면 칸보다 먼저 보낸다 — 칸 편집은 그 후보가 골라져 있어야 서버가 받는다.
 * 기다리는 동안 쌓인 변경은 합친다 — 고르기는 최신 네 구간 하나, 칸은 item_id 별 최신 값 하나(칸끼리는 바뀐 순서).
 * 칸마다 서버가 확인한 값을 기억하고, 보내기 직전에 그 값과 같으면 보내지 않는다(서버는 같은 값을 422 로 거절한다).
 * 네트워크 오류 · 5xx 는 못 보낸 변경을 들고 있다가 다음 `enqueue` 나 `retry` 때 다시 보낸다. 자동 재시도는 없다.
 * 409 가 아닌 4xx 는 끝난 것이다 — 그 저장만 버리고 큐는 계속 보내며, 화면은 확인된 값으로 되돌린다.
 * 409 는 쓰던 변경을 모두 버리고 최신으로 덮는다(사용자 결정). 다시 불러오는 동안 쌓인 변경도 버린다.
 */
export function createSaveQueue(options: Options) {
  let revision = options.revision;
  let picks: Selections | null = null;
  let cells = new Map<string, string>();
  let confirmedPicks = options.selections;
  const confirmedCells = new Map<string, string>();
  let busy = false;
  let active = true;
  // 409 로 멈췄다. 화면은 곧 새 계획안으로 바뀌므로 이 큐는 더 받지 않고, 다 저장됐다고도 하지 않는다.
  let stopped = false;
  // 서버가 거절(422)해 버린 저장의 횟수. whenIdle 이 기다리는 사이 늘었으면 덜 저장된 것이다.
  let rejections = 0;
  let status: SaveStatus = "idle";
  const waiters: ((result: IdleResult) => void)[] = [];

  const setStatus = (next: SaveStatus) => options.onStatus((status = next));
  const empty = () => picks === null && cells.size === 0;
  const idle = (saved = !stopped && empty()): IdleResult => ({ saved, revision });
  const settle = (saved = !stopped && empty()) =>
    waiters.splice(0).forEach((resolve) => resolve(idle(saved)));
  const clear = () => {
    picks = null;
    cells = new Map();
  };
  function take(): Job | null {
    if (picks) {
      const selections = picks;
      picks = null;
      return { kind: "picks", selections };
    }
    const first = cells.entries().next();
    if (first.done) return null;
    cells.delete(first.value[0]);
    return { kind: "cell", itemId: first.value[0], value: first.value[1] };
  }
  function putBack(job: Job) {
    // 그 사이 같은 것의 더 새 변경이 쌓였으면 그쪽이 최신이다.
    if (job.kind === "picks") picks ??= job.selections;
    else if (!cells.has(job.itemId)) cells = new Map([[job.itemId, job.value], ...cells]);
  }

  async function pump() {
    if (busy || empty()) return;
    busy = true;
    let sentAny = false;
    for (let job = take(); job; job = take()) {
      if (job.kind === "cell" && job.value === confirmedCells.get(job.itemId)) continue;
      setStatus("saving");
      try {
        const sent =
          job.kind === "picks"
            ? await options.send(job.selections, revision)
            : await options.sendCell(job.itemId, job.value, revision);
        revision = sent.revision;
        sentAny = true;
        if (job.kind === "picks") confirmedPicks = job.selections;
        else confirmedCells.set(job.itemId, job.value);
      } catch (error) {
        if (options.isConflict(error)) {
          clear();
          stopped = true;
          setStatus("reloading");
          try {
            if (active) await options.onConflict();
          } catch {
            // 다시 불러오지 못해도 큐는 풀어야 한다. 안내는 부르는 쪽 몫이다.
          } finally {
            clear();
            busy = false;
          }
          setStatus("idle");
          settle(false);
          return;
        }
        if (!options.isRejected(error)) {
          putBack(job);
          busy = false;
          setStatus("failed");
          settle();
          return;
        }
        rejections++;
        // 서버가 받지 않는다 — 이 저장과 그 위에 쌓인 같은 종류만 버리고 화면을 확인된 값으로 되돌린다.
        if (job.kind === "picks") {
          picks = null;
          options.onRejected({ kind: "picks", selections: confirmedPicks });
        } else {
          cells.delete(job.itemId);
          options.onRejected({
            kind: "cell",
            itemId: job.itemId,
            value: confirmedCells.get(job.itemId) ?? "",
          });
        }
      }
    }
    busy = false;
    if (sentAny || status === "saving" || status === "failed") setStatus("saved");
    settle();
  }

  return {
    enqueue(selections: Selections) {
      if (!active || stopped) return;
      picks = selections;
      void pump();
    },
    /** `base` 는 이 칸을 처음 넣을 때 서버에 있던 값이다 — 서버가 확인한 값의 시작점이다. */
    enqueueCell(itemId: string, value: string, base: string) {
      if (!active || stopped) return;
      if (!confirmedCells.has(itemId)) confirmedCells.set(itemId, base);
      cells.delete(itemId);
      cells.set(itemId, value);
      void pump();
    },
    retry() {
      void pump();
    },
    /** 보낼 것도 보내는 중인 것도 없어질 때까지 기다린다. 다 저장됐으면 `saved` true, 실패나 409 로 멈췄으면 false. 확정 전에 쓴다(ADR-044 §2). */
    whenIdle() {
      if (!busy) return Promise.resolve(idle());
      const start = rejections;
      // 기다리는 사이 422 로 버려진 저장이 있으면 큐가 비었어도 다 저장된 것이 아니다(ADR-044 §2).
      return new Promise<IdleResult>((resolve) =>
        waiters.push((result) =>
          resolve(rejections === start ? result : { ...result, saved: false }),
        ),
      );
    },
    /** 화면이 내려가면 false. 늦게 온 409 가 새 화면을 또 다시 불러오게 하지 않는다. */
    setActive(value: boolean) {
      active = value;
    },
  };
}
