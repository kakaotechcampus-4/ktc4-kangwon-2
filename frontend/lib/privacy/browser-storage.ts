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
      if (key.startsWith("saessak.mswSS.v1:")) {
        storage.removeItem(key);
        continue;
      }
      const raw = storage.getItem(key);
      if (!raw || !/^[\s]*[\[{]/.test(raw)) continue;
      let value: unknown;
      try {
        value = JSON.parse(raw);
      } catch {
        // 손상된 workspace에도 본문이 남아 있을 수 있다. 임의 삭제하지 않는다.
        unreadable.push(key);
        continue;
      }
      const sanitized = JSON.stringify(withoutChildMetadata(value));
      if (raw !== sanitized) storage.setItem(key, sanitized);
    }
  }
  return unreadable;
}
