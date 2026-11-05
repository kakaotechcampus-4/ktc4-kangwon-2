import { apiRequest } from "./client";
import { downloadHwpx, type ExportFormat } from "./export";
import type {
  MonthlyAuditEvent,
  MonthlyInput,
  MonthlyPlan,
  MonthlyPlanSummary,
  MonthlyTeacherTable,
} from "./types";

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
/** 확정본만 서버 서식으로 내려받는다. 초안은 서버가 409 로 막는다. */
export const downloadMonthlyHwpx = (id: number, format: ExportFormat = "hwpx") =>
  downloadHwpx(`/api/plans/monthly/${id}/export/hwp?format=${format}`, `월간계획안.${format}`);
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
/**
 * 교사 표(행사 일정 · 특성화 · 특별활동) 칸 나누기 · 빼기 · 크기. 경로 · 본문은 놀이 월간
 * 시간표와 같고, 표 크기만 `table_key` 를 더 보낸다 (Human Decision 2026-11-05).
 */
export const splitMonthlyTableCell = (
  id: number,
  itemId: string,
  axis: "VERTICAL" | "HORIZONTAL",
  expectedRevision: number,
) =>
  apiRequest<MonthlyPlan>(
    cell(id, itemId) + "/split",
    json("POST", { axis, expected_revision: expectedRevision }),
  );
/** 열의 마지막 칸은 422. revision 은 쿼리다. */
export const removeMonthlyTableCell = (id: number, itemId: string, expectedRevision: number) =>
  apiRequest<MonthlyPlan>(cell(id, itemId) + "/split?expected_revision=" + expectedRevision, {
    method: "DELETE",
  });
/** 경계 하나의 첫 갈래(위 · 왼쪽) 비율 10~90. 같은 값이면 200 · 무변경. */
export const resizeMonthlyTableSplit = (
  id: number,
  splitId: string,
  ratio: number,
  expectedRevision: number,
) =>
  apiRequest<MonthlyPlan>(
    "/api/plans/monthly/" + id + "/timetable/splits/" + encodeURIComponent(splitId),
    json("PUT", { ratio, expected_revision: expectedRevision }),
  );
/** 표 하나의 열 폭(합 100, 각 5 이상) · 높이 10~80mm. 칸이 3.5% 보다 좁아지면 422. */
export const resizeMonthlyTable = (
  id: number,
  tableKey: MonthlyTeacherTable["table_key"],
  size: { column_widths: number[]; height_mm: number },
  expectedRevision: number,
) =>
  apiRequest<MonthlyPlan>(
    "/api/plans/monthly/" + id + "/timetable/size",
    json("PUT", { table_key: tableKey, ...size, expected_revision: expectedRevision }),
  );
/** 훈련 후보를 「소방대피/재난대비」 칸에 복사한다. 같은 복사면 200 · 무변경. */
export const copyMonthlyDrill = (
  id: number,
  itemId: string,
  expectedRevision: number,
  signal?: AbortSignal,
) =>
  apiRequest<MonthlyPlan>(
    "/api/plans/monthly/" + id + "/drill-candidates/" + encodeURIComponent(itemId) + "/copy",
    json("POST", { expected_revision: expectedRevision }, signal),
  );
/** 그 주에 둘 안전 후보. `null` 이면 비운다. 같은 입력이면 200 · 무변경(revision 그대로). */
export const placeMonthlySafety = (
  id: number,
  weekId: string,
  candidateItemId: string | null,
  expectedRevision: number,
  signal?: AbortSignal,
) =>
  apiRequest<MonthlyPlan>(
    "/api/plans/monthly/" + id + "/safety-weeks/" + encodeURIComponent(weekId),
    json(
      "PUT",
      { candidate_item_id: candidateItemId, expected_revision: expectedRevision },
      signal,
    ),
  );
/** 이미 확정이면 revision 과 상관없이 200 — 재시도 · 더블클릭은 실패가 아니다. */
/** 월간계획안을 지운다(확정본도, ADR-062). 그 달을 다시 만들려면 먼저 지워야 한다. 주간이 딸려 있으면 409 `IN_USE`. */
export const deleteMonthlyPlan = (id: number) =>
  apiRequest<void>("/api/plans/monthly/" + id, { method: "DELETE" });
export const confirmMonthlyPlan = (id: number, expectedRevision: number, signal?: AbortSignal) =>
  apiRequest<MonthlyPlan>(
    "/api/plans/monthly/" + id + "/confirm",
    json("POST", { expected_revision: expectedRevision }, signal),
  );
/** 확정 취소. 이미 초안이면 200 · 그대로. 낡은 revision 은 409 `STALE_WRITE`. 딸린 주간은 그대로다. */
export const unconfirmMonthlyPlan = (id: number, expectedRevision: number, signal?: AbortSignal) =>
  apiRequest<MonthlyPlan>(
    "/api/plans/monthly/" + id + "/unconfirm",
    json("POST", { expected_revision: expectedRevision }, signal),
  );
