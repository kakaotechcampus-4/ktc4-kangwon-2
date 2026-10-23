/**
 * 문서 보관함(S-J5) 정렬 (docs/요구사항명세서.md FR-701).
 *
 * 일지(`GET /api/documents`)와 계획안(`GET /api/plans/annual`)은 다른 표라 서버가 둘을
 * 같이 정렬해 줄 수 없다. 화면이 합친 뒤 다시 정렬한다 — 계획안 묶음이 일지 묶음 아래에
 * 통째로 붙으면 틀린 것이다.
 */
export type ArchiveOrder = {
  source: "document" | "plan";
  /** 브라우저에만 있는 등록 증빙은 서버 번호가 없다. */
  serverId: number | null;
  createdAt: string;
};

/**
 * 최신이 위. 같은 시각이면 일지 먼저, 그다음 같은 종류끼리만 `id` 내림차순.
 *
 * **시각을 문자열로 비교하지 않는다.** `Z` 와 `+09:00` 처럼 표기가 다르면 글자 순서와
 * 시간 순서가 어긋난다. **두 표의 `id` 는 서로 다른 번호다** — 종류가 다르면 비교하지 않는다.
 */
export function byArchiveOrder(a: ArchiveOrder, b: ArchiveOrder): number {
  const newer = Date.parse(b.createdAt) - Date.parse(a.createdAt);
  if (newer) return newer;
  if (a.source !== b.source) return a.source === "document" ? -1 : 1;
  return (b.serverId ?? 0) - (a.serverId ?? 0);
}
