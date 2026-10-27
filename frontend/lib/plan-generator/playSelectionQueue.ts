export type SaveStatus = "idle" | "saving" | "saved" | "failed" | "reloading";
export type Selections = Record<string, string[]>;

/** 보내지 못한 저장이 남아 있는가 — 탭을 닫기 전에 경고할 때만 참이다. 409 로 버린 변경은 남은 저장이 아니다. */
export const hasUnsentSave = (status: SaveStatus) => status === "saving" || status === "failed";

interface Options {
  /** 처음 받은 계획안의 revision. */
  revision: number;
  /** 한 번 보낸다. 성공하면 응답의 새 revision 을 돌려준다. */
  send: (selections: Selections, expectedRevision: number) => Promise<{ revision: number }>;
  /** 다른 곳에서 바뀐 것(409 `STALE_WRITE` · `ALREADY_CONFIRMED`)인지. */
  isConflict: (error: unknown) => boolean;
  onStatus: (status: SaveStatus) => void;
  /** 최신 계획안을 다시 불러온다. 끝나면(성공이든 실패든) 돌려준다. */
  onConflict: () => Promise<void>;
}

/**
 * 고른 놀이 저장 큐 (ADR-044 §1). 한 번에 하나만 보내고, 응답 revision 을 다음 요청에 넘긴다.
 * 기다리는 동안 쌓인 변경은 최신 네 구간 하나로 합친다 — 중간 상태는 서버에 갈 필요가 없다.
 * 실패하면 못 보낸 변경을 들고 있다가 다음 `enqueue` 나 `retry` 때 다시 보낸다. 자동 재시도는 없다.
 * 409 는 다르다 — 쓰던 변경을 버리고 최신으로 덮는다(사용자 결정). 다시 불러오는 동안 쌓인 변경도 버린다.
 */
export function createSaveQueue(options: Options) {
  let revision = options.revision;
  let pending: Selections | null = null;
  let busy = false;
  let active = true;

  async function pump() {
    if (busy) return;
    busy = true;
    while (pending) {
      const sending = pending;
      pending = null;
      options.onStatus("saving");
      try {
        revision = (await options.send(sending, revision)).revision;
      } catch (error) {
        if (options.isConflict(error)) {
          pending = null;
          options.onStatus("reloading");
          if (active) await options.onConflict();
          pending = null;
          busy = false;
          options.onStatus("idle");
          return;
        }
        pending ??= sending; // 그 사이 더 새 변경이 쌓였으면 그쪽이 최신이다.
        busy = false;
        options.onStatus("failed");
        return;
      }
    }
    busy = false;
    options.onStatus("saved");
  }

  return {
    enqueue(selections: Selections) {
      pending = selections;
      void pump();
    },
    retry() {
      void pump();
    },
    /** 화면이 내려가면 false. 늦게 온 409 가 새 화면을 또 다시 불러오게 하지 않는다. */
    setActive(value: boolean) {
      active = value;
    },
  };
}
