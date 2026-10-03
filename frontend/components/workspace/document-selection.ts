/**
 * 문서 선택과 서버 응답을 묶는다.
 *
 * 선택이 바뀔 때마다 번호를 올리고, 응답은 그 번호일 때만 화면에 반영한다 —
 * 늦게 온 응답이 지금 보고 있는 문서를 바꾸면 사용자가 다른 문서에 저장·삭제하게 된다.
 */
import type { ServerDocument } from "@/lib/api/documents";
import type { SavedDocument, Section } from "@/lib/workspace/model";

export type DetailStatus = "loading" | "ready" | "error";

export interface SelectionState {
  /** 지금 고른 문서의 화면 id. 서버 문서가 아닐 수도 있고 비어 있을 수도 있다. */
  active: string;
  /** 서버 문서일 때만 채워지고, 언제나 `active` 와 같은 문서다. */
  detail: ServerDocument | null;
  status: DetailStatus;
  error: string;
  /** 저장·확정·삭제·최신 조회 중인 문서 id. 비어 있으면 요청이 없다. */
  pending: string;
}

export interface DocumentGateway {
  get(localId: string): Promise<ServerDocument>;
  update(
    localId: string,
    input: { kind: string; sections: Section[]; reviewNote: string; updatedAt: string },
  ): Promise<ServerDocument>;
  confirm(localId: string): Promise<ServerDocument>;
  remove(localId: string): Promise<void>;
}

export const BUSY = "앞선 요청이 끝난 뒤에 다시 시도해주세요.";
export const MOVED = "다른 문서로 옮겨 확정하지 않았어요. 저장한 내용은 그대로입니다.";

const EMPTY: SelectionState = { active: "", detail: null, status: "ready", error: "", pending: "" };

export function createSelection(api: DocumentGateway, describe: (error: unknown) => string) {
  let state = EMPTY;
  let generation = 0;
  // 화면 전환은 상세 조회를 취소하지 않지만, 생성 결과의 자동 열기는 취소한다.
  let creationGeneration = 0;
  const listeners = new Set<() => void>();
  const set = (next: Partial<SelectionState>) => {
    state = { ...state, ...next };
    for (const listener of listeners) listener();
  };

  /** 한 작업의 대상은 시작할 때 정해진다. 끝날 때 선택을 다시 읽지 않는다. */
  async function mutate<T>(work: (doc: ServerDocument, mine: number) => Promise<T>): Promise<T> {
    const doc = state.detail;
    if (!doc || doc.id !== state.active || state.pending) throw new Error(BUSY);
    const mine = generation;
    set({ pending: doc.id });
    try {
      return await work(doc, mine);
    } finally {
      set({ pending: "" });
    }
  }

  async function update(
    doc: ServerDocument,
    mine: number,
    sections: Section[],
    reviewNote: string,
  ) {
    const saved = await api.update(doc.id, {
      kind: doc.kind,
      sections,
      reviewNote,
      updatedAt: doc.updatedAt,
    });
    // 그 사이 다른 문서로 옮겼으면 서버 저장은 그대로 두고 화면만 건드리지 않는다.
    if (mine === generation) set({ detail: saved });
    return saved;
  }

  async function load(localId: string, mine: number) {
    const detail = await api.get(localId);
    if (mine !== generation) return null;
    set({ detail, status: "ready", error: "" });
    return detail;
  }

  return {
    subscribe(listener: () => void) {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
    get: () => state,

    /** 아직 id 가 없는 생성 작업. 서버 생성과 현재 문서를 여는 권한을 분리한다. */
    beginCreation() {
      const selected = generation;
      const mine = ++creationGeneration;
      const isCurrent = () => selected === generation && mine === creationGeneration;
      return {
        isCurrent,
        adopt(detail: ServerDocument) {
          if (!isCurrent()) return false;
          generation += 1;
          set({ active: detail.id, detail, status: "ready", error: "" });
          return true;
        },
      };
    },

    /** 보관함/생성 화면 전환과 unmount 도 생성 시작 이후의 새 사용자 문맥이다. */
    leaveCreation() {
      creationGeneration += 1;
    },

    /** 서버·로컬·해제 어느 쪽으로 옮기든 이전 상세 요청은 여기서 무효가 된다. */
    select(localId: string, serverId: number | null) {
      // 같은 문서의 편집기를 유지한다. 조회 실패 뒤 재클릭만 재시도한다.
      if (localId && localId === state.active && state.status !== "error") return;
      const mine = ++generation;
      set({
        active: localId,
        detail: null,
        error: "",
        status: serverId === null ? "ready" : "loading",
      });
      if (serverId === null) return;
      void load(localId, mine).catch((error) => {
        if (mine === generation) set({ error: describe(error), status: "error" });
      });
    },

    /** 명시적으로 최신 내용을 불러온다. 실패하면 기존 상세와 편집기를 유지한다. */
    reload: () => mutate((doc) => load(doc.id, ++generation)),

    /** 방금 만든 문서를 다시 받아오지 않고 연다. 선택이 바뀌므로 이전 요청은 무효다. */
    adopt(detail: ServerDocument) {
      generation += 1;
      set({ active: detail.id, detail, status: "ready", error: "" });
    },

    /** 저장·확정·삭제는 한 번에 하나만. 화면이 막혀 있어도 여기서 한 번 더 막는다. */
    save: (sections: Section[], reviewNote: string) =>
      mutate((doc, mine) => update(doc, mine, sections, reviewNote)),

    /**
     * 저장과 확정은 하나의 작업이다.
     *
     * 대상은 시작할 때 잡은 문서 하나뿐이다 — `await` 뒤에 선택을 다시 읽으면
     * A 를 저장하고 B 를 확정하게 된다. 그 사이 다른 문서로 옮겼으면 확정하지 않는다.
     */
    saveAndConfirm: (sections: Section[], reviewNote: string) =>
      mutate(async (doc, mine) => {
        await update(doc, mine, sections, reviewNote);
        if (mine !== generation) throw new Error(MOVED);
        const confirmed = await api.confirm(doc.id);
        if (mine === generation) set({ detail: confirmed });
        return confirmed;
      }),

    remove: () =>
      mutate(async (doc) => {
        await api.remove(doc.id);
        // 지운 문서를 그대로 보고 있으면(다시 골랐더라도) 닫는다.
        // 다른 문서를 보고 있으면 그 문서는 건드리지 않는다.
        if (state.active !== doc.id) return;
        // 이 문서의 진행 중인 상세 요청도 여기서 무효가 된다.
        generation += 1;
        set({ active: "", detail: null, status: "ready", error: "" });
      }),
  };
}

export type Selection = ReturnType<typeof createSelection>;

/**
 * 서버 문서 확정 전 최소 확인. 나머지 판정은 서버 게이트가 한다 (§11).
 *
 * `validateDocument` 의 상투어 정규식은 계약에 없는 규칙이라 정상 문장까지 막는다.
 * 서버가 보는 것은 해석·지원의 길이(20자)뿐이다.
 */
export function serverIssues(doc: Pick<SavedDocument, "sections">): string[] {
  return ["해석", "지원"]
    .filter(
      (heading) => (doc.sections.find((s) => s.heading === heading)?.body ?? "").trim().length < 20,
    )
    .map((heading) => `${heading}을 20자 이상 작성해주세요.`);
}
