import { apiRequest } from "./client";
import type { PlayMonthlyPlan, PlayMonthlySummary } from "./types";

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

/** 지금은 항상 503 이다(생성 규칙이 서버에 아직 없다). 게이트는 통과한다 — 이미 있으면 409. */
export const createPlayMonthly = (
  data: { class_id: number; month: number; emphasized_row_keys: string[] },
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
