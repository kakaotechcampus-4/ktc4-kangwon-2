import { read, commit } from "./store";
import type { ArchiveSummaryItem, ReceivedAccessRequest } from "../../lib/api/types";

/**
 * 같은 원 다른 반 열람 요청 (docs/api-spec.md §2-2 · ADR-059).
 * 서버 `backend/app/features/class_access/router.py` 를 그대로 따른다.
 *
 * **목업은 계정이 하나다.** 목업 DB 의 반은 모두 그 계정이 만든 반이라 `my_access` 가 전부 OWNER 고,
 * 내가 다른 반에 요청할 일이 없다(요청하면 서버처럼 409). 받은 요청은 다른 교사가 보낸 것이라
 * 목업이 스스로 만들지 않는다 — 테스트가 `accessRequests` 에 넣는다(양식 설정 DRAFT 와 같은 방식).
 */

const lastDay = (year: number, month: number) =>
  `${year}-${String(month).padStart(2, "0")}-${new Date(Date.UTC(year, month, 0)).getUTCDate()}`;
const monthRange = (targetMonth: string): [string, string] => {
  const [year, month] = targetMonth.split("-").map(Number);
  return [`${targetMonth}-01`, lastDay(year, month)];
};

/**
 * 제목 · 아이 이름 · id 는 넣지 않는다. 문서(`/api/documents`)는 목업에 없어 계획안만 센다.
 * 놀이 중심 월간도 `monthly` 다. `start` 내림차순.
 */
export function archiveSummary(classId: number): ArchiveSummaryItem[] {
  const db = read();
  const items: ArchiveSummaryItem[] = [
    ...db.plans
      .filter((p) => p.class_id === classId)
      .map((p) => ({
        kind: "annual" as const,
        start: `${p.school_year}-03-01`,
        end: lastDay(p.school_year + 1, 2),
        status: p.status,
      })),
    ...[...db.monthlyPlans, ...db.playMonthlyPlans]
      .filter((p) => p.class_id === classId)
      .map((p) => {
        const [start, end] = monthRange(p.target_month);
        return { kind: "monthly" as const, start, end, status: p.status };
      }),
    ...db.weeklyPlans
      .filter((p) => p.class_id === classId)
      .map((p) => ({
        kind: "weekly" as const,
        start: p.week_period.start_date,
        end: p.week_period.end_date,
        status: p.status,
      })),
  ];
  return items.sort((a, b) => (a.start < b.start ? 1 : a.start > b.start ? -1 : 0));
}

/** 내 반에 온 요청. PENDING 먼저, 그 안에서 `updated_at` · `id` 내림차순. */
export function listReceived(classIds: number[]): ReceivedAccessRequest[] {
  return read()
    .accessRequests.filter((r) => classIds.includes(r.class_id))
    .sort(
      (a, b) =>
        Number(a.status !== "PENDING") - Number(b.status !== "PENDING") ||
        (a.updated_at < b.updated_at ? 1 : a.updated_at > b.updated_at ? -1 : 0) ||
        b.id - a.id,
    );
}

/** 지금 상태 → 주인이 바꿀 수 있는 상태. 거절 · 취소된 줄은 요청하는 쪽이 다시 PENDING 으로 돌린다. */
const TRANSITIONS: Record<string, readonly string[]> = {
  PENDING: ["APPROVED", "REJECTED"],
  APPROVED: ["REVOKED"],
};

export type Decision = "APPROVED" | "REJECTED" | "REVOKED";
export function decideRequest(
  id: number,
  classIds: number[],
  status: Decision,
): ReceivedAccessRequest | "missing" | "stale" {
  return commit((db) => {
    const row = db.accessRequests.find((r) => r.id === id && classIds.includes(r.class_id));
    if (!row) return "missing" as const;
    if (!TRANSITIONS[row.status]?.includes(status)) return "stale" as const;
    row.status = status;
    row.updated_at = new Date().toISOString();
    return row;
  });
}
