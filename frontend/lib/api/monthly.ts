import { apiRequest } from "./client";
import type { MonthlyAuditEvent, MonthlyInput, MonthlyPlan, MonthlyPlanSummary } from "./types";

/** 월간계획안 (docs/api-spec.md §9-1 · §9-3). 응답 · 오류는 바꾸지 않고 그대로 넘긴다. */
const json = (method: string, data: unknown, signal?: AbortSignal): RequestInit => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(data),
  signal,
});
const cell = (id: number, itemId: string) =>
  "/api/plans/monthly/" + id + "/cells/" + encodeURIComponent(itemId);

/** 동기 생성이라 10 ~ 15초 걸린다. 같은 요청을 다시 보내지 않는다 (§9-1). */
export const createMonthlyPlan = (data: MonthlyInput, signal?: AbortSignal) =>
  apiRequest<MonthlyPlan>("/api/plans/monthly", json("POST", data, signal));
export const getMonthlyPlan = (id: number, signal?: AbortSignal) =>
  apiRequest<MonthlyPlan>("/api/plans/monthly/" + id, { signal });
/** `classId` 를 빼면 내 원 전체. 대상 달 오름차순. */
export const listMonthlyPlans = (classId?: number, signal?: AbortSignal) =>
  apiRequest<{ items: MonthlyPlanSummary[] }>(
    "/api/plans/monthly" + (classId === undefined ? "" : "?class_id=" + classId),
    { signal },
  );
/** `expectedRevision` 은 마지막으로 받은 `revision`. 다르면 409 `STALE_WRITE` (§9-3). */
export const editMonthlyCell = (
  id: number,
  itemId: string,
  value: string,
  expectedRevision: number,
  signal?: AbortSignal,
) =>
  apiRequest<MonthlyPlan>(
    cell(id, itemId),
    json("PUT", { value, expected_revision: expectedRevision }, signal),
  );
/** 그 칸만 다시 만든다. 교사가 고친 칸도 덮어쓴다 — 확인은 화면이 한다. */
export const regenerateMonthlyCell = (
  id: number,
  itemId: string,
  expectedRevision: number,
  signal?: AbortSignal,
) =>
  apiRequest<MonthlyPlan>(
    cell(id, itemId) + "/regenerate",
    json("POST", { expected_revision: expectedRevision }, signal),
  );
/**
 * 변경 이력 (§9-5). `itemId` 를 주면 그 칸의 이력과 계획안 단위 CONFIRMED 만 온다.
 * 읽기만 한다. 이 계획안에 없는 칸이면 404 `["item_id"]`.
 */
export const getMonthlyPlanAudit = (id: number, itemId?: string, signal?: AbortSignal) =>
  apiRequest<{ items: MonthlyAuditEvent[] }>(
    "/api/plans/monthly/" +
      id +
      "/audit" +
      (itemId === undefined ? "" : "?item_id=" + encodeURIComponent(itemId)),
    { signal },
  );
/** 이미 확정이면 revision 과 상관없이 200 — 재시도 · 더블클릭은 실패가 아니다. */
export const confirmMonthlyPlan = (id: number, expectedRevision: number, signal?: AbortSignal) =>
  apiRequest<MonthlyPlan>(
    "/api/plans/monthly/" + id + "/confirm",
    json("POST", { expected_revision: expectedRevision }, signal),
  );
