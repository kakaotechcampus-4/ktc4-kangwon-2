import { ApiError, apiRequest } from "./client";
import { downloadHwpx, type ExportFormat } from "./export";
import { isAlreadyConfirmed, isStaleWrite } from "./documents";
import type {
  AnnualInput,
  AnnualPlanResponse,
  AnnualPlanSummary,
  AnnualMonth,
  AnnualAuditEvent,
  MonthInput,
  ConfirmResult,
  PlayProjectAnnualPlan,
} from "./types";
export const createAnnualPlan = (data: AnnualInput, signal?: AbortSignal) =>
  apiRequest<AnnualPlanResponse>("/api/plans/annual", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
    signal,
  });
/** 계획안 목록. 이게 없으면 번호를 잃은 계획안을 다시 못 찾는다(§5). */
export const listAnnualPlans = (classId?: number, signal?: AbortSignal) =>
  apiRequest<{ items: AnnualPlanSummary[] }>(
    "/api/plans/annual" + (classId ? "?class_id=" + classId : ""),
    { signal },
  );
export const getAnnualPlan = (id: number, signal?: AbortSignal) =>
  apiRequest<AnnualPlanResponse>("/api/plans/annual/" + id, { signal });
/** 전체 교체다. theme 과 sub_themes 를 둘 다 보낸다 — 하나만 보내면 나머지가 지워진다(§6). */
export const putAnnualMonth = (id: number, month: number, data: MonthInput) =>
  apiRequest<AnnualMonth>("/api/plans/annual/" + id + "/months/" + month, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
/**
 * 놀이 프로젝트형의 고른 놀이를 저장한다 (§6-1). 네 구간을 전부 보낸다 — 빠지면 422 다.
 * `expectedRevision` 이 다르면 409 `STALE_WRITE`, 확정본이면 409 `ALREADY_CONFIRMED`.
 */
export const savePlaySelection = (
  id: number,
  selections: Record<string, string[]>,
  expectedRevision: number,
  signal?: AbortSignal,
) =>
  apiRequest<PlayProjectAnnualPlan>("/api/plans/annual/" + id + "/selection", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ selections, expected_revision: expectedRevision }),
    signal,
  });
/**
 * 놀이 프로젝트형 칸 하나를 고친다 (§6-1). 값은 앞뒤 공백을 턴 1~600자다.
 * 지금 값과 같으면 422 라 같은 값은 보내지 않는다. 배움 칸 · 안 고른 후보 · 모르는 item 은 422 `["item_id"]`.
 */
export const editPlayCell = (
  id: number,
  itemId: string,
  value: string,
  expectedRevision: number,
  signal?: AbortSignal,
) =>
  apiRequest<PlayProjectAnnualPlan>(
    "/api/plans/annual/" + id + "/cells/" + encodeURIComponent(itemId),
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ value, expected_revision: expectedRevision }),
      signal,
    },
  );
/** 다른 곳에서 바뀌어 저장이 막힌 것인가 — 409 `STALE_WRITE` · `ALREADY_CONFIRMED`. */
export const isSaveConflict = (error: unknown) => isStaleWrite(error) || isAlreadyConfirmed(error);
/** 서버가 이 저장을 받지 않는 것인가 — 422. 다시 보내도 같은 답이다. 401 · 403 · 404 · 408 · 429 · 5xx 는 아니다(다시 저장하면 될 수 있다). */
export const isRejectedSave = (error: unknown) => error instanceof ApiError && error.status === 422;
/** 변경 이력. 시간순이고 필터 · 페이지가 없다 — 화면이 `month` 로 거른다. */
export const getAnnualPlanAudit = (id: number, signal?: AbortSignal) =>
  apiRequest<{ items: AnnualAuditEvent[] }>("/api/plans/annual/" + id + "/audit", { signal });
/**
 * 연간계획안을 지운다(확정본도, ADR-064). 반 하나에 연간은 하나라, 다시 만들려면 먼저 지워야 한다.
 *
 * 월간이 딸려 있으면 409 `IN_USE` 다.
 */
export const deleteAnnualPlan = (id: number) =>
  apiRequest<void>("/api/plans/annual/" + id, { method: "DELETE" });
/**
 * **시험용.** 연간과 딸린 월간을 한 번에 지운다. 확정 여부를 보지 않는다.
 *
 * **파일럿 시작 전에 끈다.** 서버 `ALLOW_TEST_RESET` 과 화면 `NEXT_PUBLIC_ALLOW_TEST_RESET`
 * 둘 다 기본이 꺼짐이다. 서버가 꺼져 있으면 이 경로는 404 다.
 *
 * 딸린 월간이 있으면 `deleteAnnualPlan` 이 막아서 시험할 때 하나씩 지워야 한다.
 * 그 길을 줄여 두는 것이고, 교사가 쓰는 `deleteAnnualPlan` 은 그대로 둔다.
 */
export const testResetAnnualPlan = (id: number) =>
  apiRequest<void>("/api/plans/annual/" + id + "/test-reset", { method: "DELETE" });
/** 시험용 지우기 단추를 띄울지. 켜는 곳이 둘이라 어긋나도 안전하다 — 서버가 최종이다. */
export const TEST_RESET_ENABLED = process.env.NEXT_PUBLIC_ALLOW_TEST_RESET === "1";
/** 월별 주제형 확정. 소주제 수가 그 달 `week_count` 와 다른 달이 있으면 422 이고 `fields` 가 그 달 번호(`["10", "2"]`)다. */
export const confirmAnnualPlan = (id: number) =>
  apiRequest<ConfirmResult>("/api/plans/annual/" + id + "/confirm", { method: "POST" });
/**
 * 확정 취소 — CONFIRMED → DRAFT. 본문은 그 형식의 confirm 과 같다(월별 주제형은 없음, 놀이 프로젝트형은 revision).
 * 이미 초안이면 200 · 그대로다. 딸린 월간이 있어도 풀린다. 응답은 상세와 같은 모양이다.
 */
export const unconfirmAnnualPlan = (id: number, expectedRevision?: number) =>
  apiRequest<AnnualPlanResponse>(
    "/api/plans/annual/" + id + "/unconfirm",
    expectedRevision === undefined
      ? { method: "POST" }
      : {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ expected_revision: expectedRevision }),
        },
  );
/** 422 `fields` — 서버가 준 위치 목록(문자열이 아닌 것은 버린다). */
export function errorFields(error: unknown): string[] {
  if (!(error instanceof ApiError)) return [];
  const fields = (error.body as { error?: { fields?: unknown } } | null)?.error?.fields;
  return Array.isArray(fields) ? fields.filter((f): f is string => typeof f === "string") : [];
}

/**
 * 놀이 프로젝트형 확정 (§7). 읽은 revision 을 같이 보내고, 응답은 계획안 전체다.
 * 부족하면 422 `fields` 가 부족 구간 키 배열, revision 이 다르면 409 `STALE_WRITE`.
 * 이미 확정이면 revision 과 무관하게 200 이다.
 */
export const confirmPlayProject = (id: number, expectedRevision: number) =>
  apiRequest<PlayProjectAnnualPlan>("/api/plans/annual/" + id + "/confirm", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ expected_revision: expectedRevision }),
  });

/** 확정한 연간계획안을 내려받는다 (§9). 기본 hwpx, `format` 으로 pdf · hwp. */
export const downloadAnnualHwpx = (id: number, format: ExportFormat = "hwpx") =>
  downloadHwpx(`/api/plans/${id}/export/hwp?format=${format}`, `연간계획안.${format}`);
