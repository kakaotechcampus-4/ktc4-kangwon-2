import { apiRequest } from "./client";
import { downloadHwpx, type ExportFormat } from "./export";
import type {
  PlayMonthlyAuditEvent,
  PlayMonthlyPlan,
  PlayMonthlySummary,
  PlayMonthlyTimetableSize,
} from "./types";

const BASE = "/api/plans/monthly/play";
const json = (method: "PUT" | "POST", data: unknown, signal?: AbortSignal): RequestInit => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(data),
  signal,
});
/**
 * 변경 API 는 모두 읽은 `revision` 을 보내고 단건 전체를 돌려받는다. 다르면 409 `STALE_WRITE`,
 * 확정본이면 409 `ALREADY_CONFIRMED` 다 — `plans.ts` 의 `isSaveConflict` · `isRejectedSave` 가 그대로 맞는다.
 */

/** 연간 확정 뒤 그 달 초안을 만든다(201). 그 달이 이미 있으면 409, 자료가 없으면 503. */
export const createPlayMonthly = (
  data: { class_id: number; month: number; emphasized_row_keys: string[]; memo?: string },
  signal?: AbortSignal,
) => apiRequest<PlayMonthlyPlan>(BASE, json("POST", data, signal));
/** 대상 달 오름차순 요약. 기존 월간은 들어 있지 않다. */
export const listPlayMonthly = (classId?: number, signal?: AbortSignal) =>
  apiRequest<{ items: PlayMonthlySummary[] }>(BASE + (classId ? "?class_id=" + classId : ""), {
    signal,
  });
export const getPlayMonthly = (id: number, signal?: AbortSignal) =>
  apiRequest<PlayMonthlyPlan>(BASE + "/" + id, { signal });
/** 확정 전만 지운다(204). revision 은 받지 않는다. 확정본은 409 `GATE_BLOCKED`. */
export const deletePlayMonthly = (id: number) =>
  apiRequest<void>(BASE + "/" + id, { method: "DELETE" });
/**
 * 칸 하나의 글. 앞뒤 공백을 턴 0~600자이고 빈 값도 된다(칸을 비운다).
 * 지금 값과 같으면 422 `["value"]` 라 같은 값은 보내지 않는다(빈 값 → 빈 값 포함).
 */
export const editPlayMonthlyCell = (
  id: number,
  itemId: string,
  value: string,
  expectedRevision: number,
  signal?: AbortSignal,
) =>
  apiRequest<PlayMonthlyPlan>(
    BASE + "/" + id + "/cells/" + encodeURIComponent(itemId),
    json("PUT", { value, expected_revision: expectedRevision }, signal),
  );
/** 행 삭제. revision 은 본문이 아니라 쿼리다. 되돌리기는 없다. */
export const removePlayMonthlyActivity = (
  id: number,
  itemId: string,
  expectedRevision: number,
  signal?: AbortSignal,
) =>
  apiRequest<PlayMonthlyPlan>(
    BASE +
      "/" +
      id +
      "/activities/" +
      encodeURIComponent(itemId) +
      "?expected_revision=" +
      expectedRevision,
    { method: "DELETE", signal },
  );
/**
 * 한 목록(함께 하는 활동 · 자유놀이) 안의 행 순서. `itemIds` 는 그 목록 행의 `activity_id` 를 빠짐없이 한 번씩 —
 * 아니면 422 `["item_ids"]`. 같은 순서면 200 · 무변경.
 */
export const orderPlayMonthlyActivities = (
  id: number,
  section: "together" | "free_play",
  itemIds: string[],
  expectedRevision: number,
  signal?: AbortSignal,
) =>
  apiRequest<PlayMonthlyPlan>(
    BASE + "/" + id + "/activities/order",
    json("PUT", { section, item_ids: itemIds, expected_revision: expectedRevision }, signal),
  );
/** 그 주에 둘 안전 후보. `null` 이면 비운다. 같은 입력이면 200 · 무변경(revision 그대로). */
export const placePlayMonthlySafety = (
  id: number,
  weekId: string,
  candidateItemId: string | null,
  expectedRevision: number,
  signal?: AbortSignal,
) =>
  apiRequest<PlayMonthlyPlan>(
    BASE + "/" + id + "/safety-weeks/" + encodeURIComponent(weekId),
    json(
      "PUT",
      { candidate_item_id: candidateItemId, expected_revision: expectedRevision },
      signal,
    ),
  );
/** 훈련 후보를 「소방대피/재난대비」 교사 입력 칸에 복사한다. 이미 복사한 후보면 200 · 무변경. */
export const copyPlayMonthlyDrill = (
  id: number,
  itemId: string,
  expectedRevision: number,
  signal?: AbortSignal,
) =>
  apiRequest<PlayMonthlyPlan>(
    BASE + "/" + id + "/drill-candidates/" + encodeURIComponent(itemId) + "/copy",
    json("POST", { expected_revision: expectedRevision }, signal),
  );
/**
 * 확정. 이미 확정이면 revision 과 무관하게 200 · 저장된 그대로다. 낡은 revision 은 409 `STALE_WRITE`,
 * 부족하면 422 이고 `fields` 가 위치 키다(`theme` · `together.<item_id>` · `together.<item_id>.content_ids`).
 */
export const confirmPlayMonthly = (id: number, expectedRevision: number, signal?: AbortSignal) =>
  apiRequest<PlayMonthlyPlan>(
    BASE + "/" + id + "/confirm",
    json("POST", { expected_revision: expectedRevision }, signal),
  );
/** 확정 취소. 본문은 확정과 같다. 이미 초안이면 200 · 그대로, 낡은 revision 은 409 `STALE_WRITE`. */
export const unconfirmPlayMonthly = (id: number, expectedRevision: number, signal?: AbortSignal) =>
  apiRequest<PlayMonthlyPlan>(
    BASE + "/" + id + "/unconfirm",
    json("POST", { expected_revision: expectedRevision }, signal),
  );
/**
 * 특별활동 시간표 칸 나누기(ADR-047 · 제안 경로). 원래 칸(id · 글)은 위 · 왼쪽에 남고
 * 빈 새 칸이 50:50 으로 생긴다. 한 요일은 네 번까지 — 넘으면 422.
 */
export const splitPlayMonthlyCell = (
  id: number,
  itemId: string,
  axis: "VERTICAL" | "HORIZONTAL",
  expectedRevision: number,
) =>
  apiRequest<PlayMonthlyPlan>(
    BASE + "/" + id + "/cells/" + encodeURIComponent(itemId) + "/split",
    json("POST", { axis, expected_revision: expectedRevision }),
  );
/** 시간표 칸을 문서에서 뺀다. 형제가 자리를 채운다. 요일의 마지막 칸은 422. revision 은 쿼리다. */
export const removePlayMonthlyCell = (id: number, itemId: string, expectedRevision: number) =>
  apiRequest<PlayMonthlyPlan>(
    BASE +
      "/" +
      id +
      "/cells/" +
      encodeURIComponent(itemId) +
      "/split?expected_revision=" +
      expectedRevision,
    { method: "DELETE" },
  );
/** 경계 하나의 첫 갈래(위 · 왼쪽) 비율 10~90. 같은 값이면 200 · 무변경. */
export const resizePlayMonthlySplit = (
  id: number,
  splitId: string,
  ratio: number,
  expectedRevision: number,
) =>
  apiRequest<PlayMonthlyPlan>(
    BASE + "/" + id + "/timetable/splits/" + encodeURIComponent(splitId),
    json("PUT", { ratio, expected_revision: expectedRevision }),
  );
/** 요일 열 폭 다섯(합 100, 각 5 이상) · 표 높이 16~80mm. 칸이 3.5% 보다 좁아지면 422. */
export const resizePlayMonthlyTable = (
  id: number,
  size: PlayMonthlyTimetableSize,
  expectedRevision: number,
) =>
  apiRequest<PlayMonthlyPlan>(
    BASE + "/" + id + "/timetable/size",
    json("PUT", { ...size, expected_revision: expectedRevision }),
  );
/** 확정본만 내려받는다(초안은 409 `GATE_BLOCKED`). 교사가 나눈 시간표 모양 그대로다. */
export const downloadPlayMonthlyHwpx = (id: number, format: ExportFormat = "hwpx") =>
  downloadHwpx(`${BASE}/${id}/export/hwp?format=${format}`, `월간계획안.${format}`);
/** 변경 이력. 발생 시각순이고 필터 · 페이지가 없다. */
export const getPlayMonthlyAudit = (id: number, signal?: AbortSignal) =>
  apiRequest<{ items: PlayMonthlyAuditEvent[] }>(BASE + "/" + id + "/audit", { signal });
