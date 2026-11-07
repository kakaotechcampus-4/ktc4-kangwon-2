/**
 * 만들기가 409(이미 있음)면 목록을 다시 읽어 그 계획안 id 를 찾는다(월간 · 주간 만들기).
 * 기다리는 사이 취소했거나 새 요청이 시작됐으면(`stale`) null — 옛 요청이 화면을 옮기지 않는다.
 */
export async function existingAfterConflict<T extends { id: number }>(
  list: () => Promise<{ items: T[] }>,
  matches: (item: T) => boolean,
  stale: () => boolean,
): Promise<number | null> {
  const again = await list().catch(() => null);
  if (stale()) return null;
  return again?.items.find(matches)?.id ?? null;
}
