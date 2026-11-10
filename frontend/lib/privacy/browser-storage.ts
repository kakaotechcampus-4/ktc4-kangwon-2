import type { SavedDocument, Workspace } from "../workspace/model";

/** 구조화된 아동 식별 필드만 정리한다. 본문·제목 등 문자열의 내용은 바꾸지 않는다. */
const privateFields = new Set([
  "childName",
  "child_name",
  "childCode",
  "child_code",
  "realName",
  "real_name",
  "pseudonym",
]);
const childContainers = new Set(["children", "child", "roster", "childMetadata"]);

export function withoutChildMetadata<T>(value: T, child = false): T {
  if (Array.isArray(value)) return value.map((item) => withoutChildMetadata(item, child)) as T;
  if (!value || typeof value !== "object") return value;
  const next: Record<string, unknown> = {};
  for (const [key, item] of Object.entries(value)) {
    // childName은 기존 workspace schema가 요구하므로 빈 문자열로 남긴다.
    if (key === "childName") next[key] = "";
    else if (privateFields.has(key) || (child && (key === "name" || key === "code"))) continue;
    else next[key] = withoutChildMetadata(item, child || childContainers.has(key));
  }
  return next as T;
}

const WORKSPACE = "saessak.workspace.v1";
/** 목업 DB 키 앞머리. 뒤에 계정이 붙는다(`msw/data/store.ts`). */
const MOCK_DB = "saessak.mswSS.v1:";
/** 화면이 아직 읽는 것은 계획안의 서버 ID 뿐이다 (`PlanStart`). 일지 · 관찰 문서는 서버에 있다. */
const PLAN_KINDS = new Set(["annual", "monthly", "weekly", "daily"]);

/**
 * 브라우저 workspace 에서 본문을 뺀다 (ADR-013). 필드 이름만 지우면 제목 · 사실 · 본문 · 근거에 적힌
 * 실명이 그대로 남는다. 남기는 것은 계획안의 서버 ID 와 종류 · 반 · 기간 같은 설정뿐이다.
 *
 * `keepImports` 면 예전에 올린 서류(IMPORT)를 그대로 둔다 — 서버로 옮기기 전까지만이다
 * (`moveLegacyImports`). 옮기거나 못 옮긴 뒤 지우는 일은 그 함수가 한다.
 */
export function withoutDocumentBodies(value: unknown, keepImports = false): Workspace {
  const data = (value && typeof value === "object" ? value : {}) as Partial<Workspace>;
  const documents = Array.isArray(data.documents) ? data.documents : [];
  return {
    version: 1,
    observations: [],
    templates: [],
    criteria: Array.isArray(data.criteria) ? data.criteria : [],
    documents: documents.flatMap((d: SavedDocument) => {
      if (!d || typeof d !== "object") return [];
      if (d.origin === "import") return keepImports ? [d] : [];
      if (!PLAN_KINDS.has(d.kind)) return [];
      return [{ ...d, childId: "", childName: "", sections: [], sources: [] }];
    }),
  };
}

/** 현재/다른 계정과 구형 공통 키, 양쪽 storage를 모두 검사한다. */
export function sanitizeBrowserChildMetadata(): string[] {
  if (typeof window === "undefined") return [];
  const unreadable: string[] = [];
  for (const storage of [window.localStorage, window.sessionStorage]) {
    if (!storage) continue;
    const keys = Array.from({ length: storage.length }, (_, i) => storage.key(i));
    for (const key of keys) {
      if (!key?.startsWith("saessak.")) continue;
      // 서버 데이터가 아닌 개발용 mock 캐시는 복구 원본이 아니므로 폐기한다.
      // 그 계정의 반 설정과 목업 id 연결도 같이 버린다 — 남기면 다시 로그인했을 때 없는 목업 반을
      // 불러 404 가 난다(점검 X-E3). 실제 서버 연결(`apiLinks.v1:backend:`)은 건드리지 않는다.
      if (key.startsWith(MOCK_DB)) {
        const account = key.slice(MOCK_DB.length);
        storage.removeItem(key);
        storage.removeItem(`saessak.classSettings:${account}`);
        storage.removeItem(`saessak.apiLinks.v1:development-mock:${account}`);
        continue;
      }
      const raw = storage.getItem(key);
      const workspace = key === WORKSPACE || key.startsWith(WORKSPACE + ":");
      if (!raw || (!workspace && !/^[\s]*[\[{]/.test(raw))) continue;
      let value: unknown;
      try {
        value = JSON.parse(raw);
      } catch {
        // 손상된 workspace 는 본문이 남아 있어도 읽어 옮길 길이 없다. 지운다.
        if (workspace) storage.removeItem(key);
        else unreadable.push(key);
        continue;
      }
      // 계정별 workspace 의 IMPORT 는 그 계정이 로그인할 때 서버로 옮긴다. 계정을 모르는
      // 공통 키(옛 단일 계정)와 sessionStorage 에 든 것은 옮길 길이 없어 바로 지운다.
      if (workspace)
        value = withoutDocumentBodies(value, storage === window.localStorage && key !== WORKSPACE);
      const sanitized = JSON.stringify(withoutChildMetadata(value));
      if (raw !== sanitized) storage.setItem(key, sanitized);
    }
  }
  return unreadable;
}
