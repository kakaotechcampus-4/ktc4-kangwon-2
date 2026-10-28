import type { AnnualPlanSummary } from "@/lib/api/types";

/** 반의 연간이 놀이 프로젝트형인가. 목록을 못 읽었으면(null) 아니다 — 기존 월간 화면으로 둔다. */
export const isPlayAnnual = (annual: { items: AnnualPlanSummary[] } | null) =>
  annual?.items[0]?.format === "PLAY_PROJECT";
