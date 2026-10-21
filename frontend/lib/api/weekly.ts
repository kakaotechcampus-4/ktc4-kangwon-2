import { apiRequest } from "./client";
import type { WeeklyPlan, WeeklyPlanSummary } from "./types";

/**
 * 주간계획안 (docs/weekly-plan-contract.md §13).
 *
 * 월간(api-spec §9-1 · §9-3)과 **같은 모양 · 같은 공개 오류 코드**다. 새 코드를 만들지 않는다.
 * `profile_ref` 를 보내지 않는다 — 주간에는 양식 설정(TemplateProfile)이 없다 (D-W1-06).
 */
const json = (method: string, data: unknown, signal?: AbortSignal): RequestInit => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(data),
  signal,
});
const cell = (id: number, itemId: string) =>
  "/api/plans/weekly/" + id + "/cells/" + encodeURIComponent(itemId);

/**
 * 한 주를 만든다. `week_id` 는 **부모 월간이 준 주소**를 그대로 보낸다 (§3-1).
 * 그 달 월간이 확정되지 않았으면 409 `GATE_BLOCKED`, 같은 주가 이미 있으면 409 `ALREADY_EXISTS` (§4-1).
 */
export const createWeeklyPlan = (
  data: { class_id: number; week_id: string },
  signal?: AbortSignal,
) => apiRequest<WeeklyPlan>("/api/plans/weekly", json("POST", data, signal));
export const getWeeklyPlan = (id: number, signal?: AbortSignal) =>
  apiRequest<WeeklyPlan>("/api/plans/weekly/" + id, { signal });
/**
 * 그 달의 주간계획안들. `month` 는 **달력 달 1~12** 다 — `YYYY-MM` 이 아니다.
 * 연도는 반의 학년도가 정한다 (월간 생성과 같은 규칙). `month` 는 `classId` 와 함께만 간다.
 */
export const listWeeklyPlans = (classId: number, month: number, signal?: AbortSignal) =>
  apiRequest<{ items: WeeklyPlanSummary[] }>(
    "/api/plans/weekly?class_id=" + classId + "&month=" + month,
    { signal },
  );
/**
 * `expectedRevision` 은 마지막으로 받은 `revision`. 다르면 409 `STALE_WRITE`.
 *
 * **서버 경로가 아직 없다 (W5b).** 지금 부르면 404 다 — 화면이 「준비 중」으로 안내한다.
 */
export const editWeeklyCell = (
  id: number,
  itemId: string,
  value: string,
  expectedRevision: number,
  signal?: AbortSignal,
) =>
  apiRequest<WeeklyPlan>(
    cell(id, itemId),
    json("PUT", { value, expected_revision: expectedRevision }, signal),
  );
/** 그 칸만 다시 만든다. **교사 입력 칸에는 없다** — 만든 적이 없어 다시 만들 것도 없다 (§6-2). */
export const regenerateWeeklyCell = (
  id: number,
  itemId: string,
  expectedRevision: number,
  signal?: AbortSignal,
) =>
  apiRequest<WeeklyPlan>(
    cell(id, itemId) + "/regenerate",
    json("POST", { expected_revision: expectedRevision }, signal),
  );
/** 확정. 계획안에는 확정 취소가 없다 (ADR-030 PM-03). */
export const confirmWeeklyPlan = (id: number, expectedRevision: number, signal?: AbortSignal) =>
  apiRequest<WeeklyPlan>(
    "/api/plans/weekly/" + id + "/confirm",
    json("POST", { expected_revision: expectedRevision }, signal),
  );
/** 확정 전 주간계획안을 지운다. 그 주를 다시 만들려면 먼저 지워야 한다 (G5). 확정본은 409 다. */
export const deleteWeeklyPlan = (id: number) =>
  apiRequest<void>("/api/plans/weekly/" + id, { method: "DELETE" });
