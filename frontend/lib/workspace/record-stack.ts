/**
 * 쌓인 기록의 같은 날 · 같은 아이 기록을 한 벌로 묶는다 (수민 제안 · PM 결정 11-10).
 *
 * - **날짜 묶음 하나 안에서만** 묶는다. 다른 날 기록은 그날 묶음에 따로 선다.
 * - 한 벌은 그 아이 **가장 최근** 기록 자리에 선다 — 목록이 시간 순서를 잃지 않게.
 *   목록이 어떤 순서로 오든 `createdAt` 으로 가장 최근을 고른다.
 * - 벌 안은 최근 것부터. 맨 위 장이 그 아이가 마지막으로 남긴 기록이다.
 * - 받은 목록이 이미 찾기 · 영역 거르기를 거쳤으면 맞은 기록만 묶인다(「+n」 도 맞은 수).
 *
 * 이 파일은 아무것도 import 하지 않는다 — 시험이 그대로 불러 쓴다.
 */
export function stackByChild<T extends { childId: string; createdAt: string }>(day: T[]): T[][] {
  const time = (r: T) => Date.parse(r.createdAt) || 0;
  const piles = new Map<string, T[]>();
  for (const r of day) piles.set(r.childId, [...(piles.get(r.childId) ?? []), r]);
  for (const pile of piles.values()) pile.sort((a, b) => time(b) - time(a));
  // 벌마다 맨 위(가장 최근) 장이 원래 목록에 있던 자리를 지킨다.
  return [...piles.values()].sort((a, b) => day.indexOf(a[0]) - day.indexOf(b[0]));
}
