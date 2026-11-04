import type {
  PlayMonthlyCell,
  PlayMonthlyPlan,
  PlayMonthlyTimetablePart as Part,
  PlayMonthlyTimetableSize,
} from "../api/types";

/**
 * 특별활동 시간표 나눔 트리(ADR-047) 순수 함수. 최종 검사는 서버 Core 가 한다 — 여기 한도는
 * 화면에서 미리 막고 목업이 서버처럼 거절하는 데만 쓴다.
 */
export const DAYS = ["월", "화", "수", "목", "금"];
export const MAX_DEPTH = 4;
export const RATIO_RANGE = [10, 90] as const;
export const COLUMN_MIN = 5;
export const CELL_MIN_WIDTH = 3.5;
export const HEIGHT_RANGE = [16, 80] as const;

export const leaf = (cell: PlayMonthlyCell): Part => ({
  cell,
  split_id: null,
  axis: null,
  ratio: null,
  children: [],
});
export const leaves = (part: Part): PlayMonthlyCell[] =>
  part.cell ? [part.cell] : part.children.flatMap(leaves);
export const boundaries = (part: Part): Part[] =>
  part.cell ? [] : [part, ...part.children.flatMap(boundaries)];

/** 칸이 든 요일과 뿌리 → 칸까지의 마디. 시간표 칸이 아니면 null. */
export function locate(days: Part[], itemId: string) {
  const walk = (part: Part): Part[] | null => {
    if (part.cell) return part.cell.item_id === itemId ? [part] : null;
    for (const child of part.children) {
      const found = walk(child);
      if (found) return [part, ...found];
    }
    return null;
  };
  for (const [day, root] of days.entries()) {
    const path = walk(root);
    if (path) return { day, path };
  }
  return null;
}

/** 칸의 실제 폭 중 가장 좁은 것 — 좌우 경계의 비율을 곱해 내려간다(Core `narrowest`). */
export function narrowest(part: Part, width: number): number {
  if (part.cell) return width;
  const [first, second] = part.children;
  if (part.axis === "VERTICAL") return Math.min(narrowest(first, width), narrowest(second, width));
  const left = (width * part.ratio!) / 100;
  return Math.min(narrowest(first, left), narrowest(second, width - left));
}
export const tooNarrow = (days: Part[], widths: number[]) =>
  days.some((day, i) => narrowest(day, widths[i]) < CELL_MIN_WIDTH);

const rebuild = (part: Part, visit: (p: Part) => Part | null): Part =>
  visit(part) ??
  (part.cell ? part : { ...part, children: part.children.map((c) => rebuild(c, visit)) });

/** 칸을 둘로 — 원래 칸은 첫 갈래, `added` 는 둘째, 50:50. */
export const splitLeaf = (
  part: Part,
  itemId: string,
  axis: "VERTICAL" | "HORIZONTAL",
  splitId: string,
  added: PlayMonthlyCell,
) =>
  rebuild(part, (p) =>
    p.cell?.item_id === itemId
      ? { cell: null, split_id: splitId, axis, ratio: 50, children: [p, leaf(added)] }
      : null,
  );
/** 칸을 빼고 그 형제(묶음)가 부모 자리를 채운다. */
export const removeLeaf = (part: Part, itemId: string) =>
  rebuild(part, (p) => {
    const at = p.children.findIndex((c) => c.cell?.item_id === itemId);
    return at < 0 ? null : p.children[1 - at];
  });
export const withRatio = (part: Part, splitId: string, ratio: number) =>
  rebuild(part, (p) => (p.split_id === splitId ? { ...p, ratio } : null));

export const validSize = ({ column_widths: w, height_mm: h }: PlayMonthlyTimetableSize) =>
  w.length === DAYS.length &&
  w.every((x) => Number.isInteger(x) && x >= COLUMN_MIN) &&
  w.reduce((a, b) => a + b, 0) === 100 &&
  Number.isInteger(h) &&
  h >= HEIGHT_RANGE[0] &&
  h <= HEIGHT_RANGE[1];

/** 시간표 칸 하나의 위치 이름(「특별활동 · 월요일」). 시간표 칸이 아니면 null. */
export function timetablePlace(plan: PlayMonthlyPlan, itemId: string) {
  const at = plan.specialized_timetable.findIndex((c) => c.item_id === itemId);
  if (at >= 0) return `특성화 · ${(at % 5) + 1}열 ${at < 5 ? "제목" : "내용"}`;
  const found = locate(plan.special_activity, itemId);
  return found ? `특별활동 · ${DAYS[found.day]}요일` : null;
}
