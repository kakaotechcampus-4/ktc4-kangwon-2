import type {
  DocumentQuery,
  DocumentSummary,
  RelatedDocuments,
  ServerDocument,
} from "@/lib/api/documents";

export interface CompareResource<T> {
  status: "idle" | "loading" | "ready" | "error";
  data: T | null;
  error: string;
}

interface CompareState {
  list: CompareResource<DocumentSummary[]>;
  baseId: string;
  relatedId: string;
  base: CompareResource<ServerDocument>;
  related: CompareResource<RelatedDocuments>;
  comparison: CompareResource<ServerDocument>;
}

interface CompareGateway {
  list(query: DocumentQuery): Promise<DocumentSummary[]>;
  get(id: string): Promise<ServerDocument>;
  related(id: string): Promise<RelatedDocuments>;
}

const empty = <T>(): CompareResource<T> => ({ status: "idle", data: null, error: "" });
const describe = (error: unknown) =>
  error instanceof Error ? error.message : "요청을 처리하지 못했어요.";

/** 선택과 재시도마다 요청 번호를 올린다. 실패한 재조회는 보고 있던 원문을 유지한다. */
export function createCompareSelection(api: CompareGateway) {
  let state: CompareState = {
    list: { ...empty(), status: "loading" },
    baseId: "",
    relatedId: "",
    base: empty(),
    related: empty(),
    comparison: empty(),
  };
  const requests = { list: 0, base: 0, related: 0, comparison: 0 };
  const listeners = new Set<() => void>();
  const set = (next: Partial<CompareState>) => {
    state = { ...state, ...next };
    for (const listener of listeners) listener();
  };

  async function load<K extends "list" | "base" | "related" | "comparison">(
    key: K,
    work: () => Promise<NonNullable<CompareState[K]["data"]>>,
  ) {
    const mine = ++requests[key];
    set({ [key]: { ...state[key], status: "loading", error: "" } });
    try {
      const data = await work();
      if (mine !== requests[key]) return;
      set({ [key]: { status: "ready", data, error: "" } });
      if (
        key === "related" &&
        state.relatedId &&
        !state.related.data?.items.some((item) => item.id === state.relatedId)
      ) {
        requests.comparison += 1;
        set({ relatedId: "", comparison: empty() });
      }
    } catch (error) {
      if (mine === requests[key])
        set({ [key]: { ...state[key], status: "error", error: describe(error) } });
    }
  }

  const loadList = () => load("list", () => api.list({ status: "CONFIRMED" }));
  const reloadBase = () =>
    state.baseId ? load("base", () => api.get(state.baseId)) : Promise.resolve();
  const reloadRelated = () =>
    state.baseId ? load("related", () => api.related(state.baseId)) : Promise.resolve();
  const reloadComparison = () =>
    state.relatedId ? load("comparison", () => api.get(state.relatedId)) : Promise.resolve();

  return {
    get: () => state,
    subscribe(listener: () => void) {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
    loadList,
    reloadBase,
    reloadRelated,
    reloadComparison,
    selectBase(id: string) {
      if (id === state.baseId) return Promise.resolve();
      if (id && !state.list.data?.some((item) => item.id === id)) return Promise.resolve();
      requests.base += 1;
      requests.related += 1;
      requests.comparison += 1;
      set({ baseId: id, relatedId: "", base: empty(), related: empty(), comparison: empty() });
      // 기준 상세와 관련 목록은 독립적으로 읽는다. 한쪽이 실패해도 다른 쪽을 지우지 않는다.
      return Promise.all([reloadBase(), reloadRelated()]);
    },
    selectRelated(id: string) {
      if (id === state.relatedId) return Promise.resolve();
      if (id && !state.related.data?.items.some((item) => item.id === id)) return Promise.resolve();
      requests.comparison += 1;
      set({ relatedId: id, comparison: empty() });
      return reloadComparison();
    },
    dispose() {
      // 언마운트와 StrictMode의 effect 재실행에서도 이전 응답은 무효다.
      for (const key of Object.keys(requests) as (keyof typeof requests)[]) requests[key] += 1;
    },
  };
}
