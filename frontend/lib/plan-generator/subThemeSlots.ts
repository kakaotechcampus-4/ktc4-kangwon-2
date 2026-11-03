/**
 * 월별 주제형 연간의 주차별 소주제 칸 (계약 I-A · 화면 #3). 달마다 `week_count` 칸에 소주제를 하나씩 놓는다.
 * 입력 중 목록에는 빈 칸이 있을 수 있고, 저장할 때만 비운 칸을 뺀다(서버도 그렇게 받는다).
 */
export const moveSlot = (list: string[], index: number, delta: -1 | 1) => {
  const to = index + delta;
  if (index < 0 || to < 0 || to >= list.length) return list;
  const next = [...list];
  [next[index], next[to]] = [next[to], next[index]];
  return next;
};
export const removeSlot = (list: string[], index: number) => list.filter((_, i) => i !== index);
export const setSlot = (list: string[], index: number, value: string) =>
  list.map((item, i) => (i === index ? value : item));
/** 저장 값 — 앞뒤 공백을 지우고 빈 칸을 뺀다. */
export const cleanSlots = (list: string[]) => list.map((s) => s.trim()).filter(Boolean);
/** 확정하려면 소주제 수가 주 수와 같아야 한다. */
export const slotMismatch = (list: string[], weekCount: number) =>
  cleanSlots(list).length !== weekCount;
/** 문서에 그릴 줄 수 — 주 수보다 적으면 빈 칸을, 많으면 남는 칸을 그대로 보인다. */
export const slotRows = (list: string[], weekCount: number) => Math.max(weekCount, list.length, 1);
