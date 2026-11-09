/**
 * 승인받은 남의 반 문서 목록 (components/workspace/ClassAccessPanels.tsx 의 ApprovedList, ADR-059).
 *
 * 일지 · 연간 · 기존 월간 · 놀이 중심 월간 · 주간을 다 부른다. **놀이 중심 월간은 따로 부른다** —
 * 기존 월간 목록이 놀이형을 빼고 주므로, 그것만 있는 반이 「아직 만든 문서가 없어요」로 보였다(#373).
 * 남의 반이라 줄마다 보기와 확정본 내려받기뿐이다. 편집 화면 주소(`href`)는 늘 비운다.
 */

import type { PlanPreviewTarget } from "../../components/workspace/DocumentArchivePreview";
import type { ApiClass } from "../api/types";
import { downloadDocumentHwpx, listDocuments } from "../api/documents";
import { downloadAnnualHwpx, listAnnualPlans } from "../api/plans";
import { downloadMonthlyHwpx, listMonthlyPlans } from "../api/monthly";
import { downloadPlayMonthlyHwpx, listPlayMonthly } from "../api/playMonthly";
import { downloadWeeklyHwpx, listWeeklyPlans } from "../api/weekly";
import { monthLabel, weekIdLabel } from "./document-archive";
import { DOCUMENT_KINDS } from "./model";

export const PLAN_NAME = {
  annual: "연간 계획안",
  monthly: "월간 계획안",
  weekly: "주간 계획안",
} as const;

/** 승인받은 반의 한 줄. 보기는 미리보기 칸, 내려받기는 확정본만이다. */
export type ApprovedRow = {
  key: string;
  /** 정렬 열쇠 — 최근 것이 위다. */
  order: string;
  name: string;
  title: string;
  period: string;
  confirmed: boolean;
  view: { doc: string } | { plan: PlanPreviewTarget };
  /** 없으면 한글 파일로 못 만든다 — 증빙으로 올린 원문(IMPORT)은 서버가 409 로 막는다. */
  hwp?: () => Promise<void>;
};

/** 다섯 목록을 받아 최근 것이 위인 줄로. 하나라도 실패하면 `failed` 에 그 이유를 담는다. */
export async function loadApprovedRows(
  room: Pick<ApiClass, "id" | "name">,
): Promise<{ rows: ApprovedRow[]; failed: unknown[] }> {
  const plan = (
    kind: PlanPreviewTarget["kind"],
    id: number,
    title: string,
    period: string,
    createdAt: string,
    play = false,
  ): PlanPreviewTarget => ({
    kind,
    id,
    classId: room.id,
    className: room.name,
    title,
    period,
    periodKey: period,
    createdAt,
    // 비우면 미리보기가 「문서 열기」를 그리지 않는다 — 남의 반을 편집 화면으로 보내지 않는다.
    href: "",
    ...(play ? { play: true } : {}),
  });
  // 승인된 반도 반을 짚어야 준다 — `class_id` 없는 목록은 내 반 것만이다 (§2-2).
  const [docs, annual, monthly, playMonthly, weekly] = await Promise.allSettled([
    listDocuments({ class_id: room.id }),
    listAnnualPlans(room.id),
    listMonthlyPlans(room.id),
    listPlayMonthly(room.id),
    listWeeklyPlans(room.id),
  ]);
  const rows: ApprovedRow[] = [];
  if (docs.status === "fulfilled")
    for (const d of docs.value)
      rows.push({
        key: d.id,
        order: d.start,
        name: DOCUMENT_KINDS[d.kind],
        title: d.title,
        period: d.start === d.end ? d.start : `${d.start} ~ ${d.end}`,
        confirmed: d.status === "confirmed",
        view: { doc: d.id },
        hwp: d.origin === "import" ? undefined : () => downloadDocumentHwpx(d.id),
      });
  if (annual.status === "fulfilled")
    for (const p of annual.value.items) {
      const title = `${p.school_year}학년도 연간 계획안`;
      rows.push({
        key: `annual:${p.id}`,
        order: `${p.school_year}-03`,
        name: PLAN_NAME.annual,
        title,
        period: `${p.school_year}학년도`,
        confirmed: p.status === "CONFIRMED",
        view: { plan: plan("annual", p.id, title, `${p.school_year}학년도`, p.created_at) },
        hwp: () => downloadAnnualHwpx(p.id),
      });
    }
  const monthRows = (
    items: { id: number; target_month: string; status: string; created_at: string }[],
    play: boolean,
  ) => {
    for (const p of items) {
      const period = monthLabel(p.target_month);
      const title = `${period} 월간 계획안`;
      rows.push({
        // 기존 월간과 놀이 월간은 id 가 겹칠 수 있다 — 열쇠를 나눈다.
        key: `${play ? "play-monthly" : "monthly"}:${p.id}`,
        order: p.target_month,
        name: PLAN_NAME.monthly,
        title,
        period,
        confirmed: p.status === "CONFIRMED",
        view: { plan: plan("monthly", p.id, title, period, p.created_at, play) },
        hwp: play ? () => downloadPlayMonthlyHwpx(p.id) : () => downloadMonthlyHwpx(p.id),
      });
    }
  };
  if (monthly.status === "fulfilled") monthRows(monthly.value.items, false);
  if (playMonthly.status === "fulfilled") monthRows(playMonthly.value.items, true);
  if (weekly.status === "fulfilled")
    for (const p of weekly.value.items) {
      const period = weekIdLabel(p.week_id);
      rows.push({
        key: `weekly:${p.id}`,
        order: p.week_id,
        name: PLAN_NAME.weekly,
        title: `${period} 주간 계획안`,
        period,
        confirmed: p.status === "CONFIRMED",
        view: { plan: plan("weekly", p.id, `${period} 주간 계획안`, period, p.created_at) },
        hwp: () => downloadWeeklyHwpx(p.id),
      });
    }
  rows.sort((a, b) => b.order.localeCompare(a.order));
  const failed = [docs, annual, monthly, playMonthly, weekly]
    .filter((r) => r.status === "rejected")
    .map((r) => (r as PromiseRejectedResult).reason);
  return { rows, failed };
}
