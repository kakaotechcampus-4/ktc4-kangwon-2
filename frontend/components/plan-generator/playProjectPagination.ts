import type { PlayProjectAnnualPlan } from "@/lib/api/types";

export const fields = [
  { key: "play_name", label: "놀이명", heading: "놀이명" },
  { key: "materials", label: "지원매체", heading: "지원매체" },
  { key: "support_direction", label: "지원 방향", heading: "내용 및 지원 방향 예상하기" },
  { key: "learning", label: "놀이를 통한 배움", heading: "놀이를 통한 배움" },
] as const;
export type PlayField = (typeof fields)[number]["key"];
export type SheetZoom = { mode: "fit" | "manual"; percent: number };
export type PreviewRow = {
  key: string;
  period: PlayProjectAnnualPlan["periods"][number];
  candidate: PlayProjectAnnualPlan["periods"][number]["candidates"][number] | null;
  rowSpan: number | undefined;
  height?: number;
  labelHeight?: number;
};

export function buildPlayProjectPreviewRows(
  plan: PlayProjectAnnualPlan,
  picks: Record<string, string[]>,
) {
  return plan.periods.flatMap<PreviewRow>((period) => {
    const selected = (picks[period.period_key] ?? []).map((key) =>
      period.candidates.find((candidate) => candidate.row_key === key)!,
    );
    return selected.length
      ? selected.map<PreviewRow>((candidate, index) => ({
          key: `${period.period_key}-${index}`,
          period,
          candidate,
          rowSpan: index === 0 ? selected.length : undefined,
        }))
      : [{ key: `${period.period_key}-empty`, period, candidate: null, rowSpan: 1 }];
  });
}

export function cellButtonId(periodKey: string, rowKey: string, field: PlayField) {
  return `play-project-cell-${periodKey}-${rowKey}-${field}`;
}

// 한글 받침에 맞춰 을/를. 한글이 아니면 둘 다 적는다.
export function eulReul(name: string) {
  const code = name.trim().charCodeAt(name.trim().length - 1) - 0xac00;
  if (code < 0 || code > 11171) return "을(를)";
  return code % 28 === 0 ? "를" : "을";
}

export function stepPlaySheetZoom(current: number, delta: -1 | 1) {
  return Math.max(50, Math.min(150, Math.round(current / 10) * 10 + delta * 10));
}

export function paginatePlaySheet(
  groups: PreviewRow[][],
  {
    contentHeight,
    titleHeight,
    headerHeight,
  }: {
    contentHeight: number;
    titleHeight: number;
    headerHeight: number;
  },
) {
  const pages: { group: number; title: boolean; rows: PreviewRow[] }[] = [];
  groups.forEach((rows, group) => {
    let page = { group, title: true, rows: [] as PreviewRow[] };
    let used = titleHeight + headerHeight;
    let periodHeight = 0;
    let periodKey = "";
    pages.push(page);
    rows.forEach((row) => {
      const height = row.height ?? 0;
      const labelHeight = row.labelHeight ?? 0;
      const samePeriod = periodKey === row.period.period_key;
      let added = samePeriod
        ? Math.max(periodHeight + height, labelHeight) - Math.max(periodHeight, labelHeight)
        : Math.max(height, labelHeight);
      // 한글은 셀 안에서 나누지만 화면은 놀이 한 행을 통째로 옮긴다.
      if (page.rows.length && used + added > contentHeight) {
        page = { group, title: false, rows: [] };
        pages.push(page);
        used = headerHeight;
        periodHeight = 0;
        periodKey = "";
        added = Math.max(height, labelHeight);
      }
      periodHeight = (periodKey === row.period.period_key ? periodHeight : 0) + height;
      periodKey = row.period.period_key;
      used += added;
      page.rows.push({ ...row, rowSpan: undefined });
    });
  });
  pages.forEach((page) => {
    page.rows.forEach((row, index) => {
      if (index && page.rows[index - 1].period.period_key === row.period.period_key) return;
      row.rowSpan = page.rows.filter(
        (item) => item.period.period_key === row.period.period_key,
      ).length;
    });
  });
  return pages;
}
