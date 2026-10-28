import { apiRequest } from "./client";
import { downloadHwpx } from "./export";
import type {
  AnnualInput,
  AnnualPlan,
  AnnualPlanSummary,
  AnnualMonth,
  AnnualAuditEvent,
  MonthInput,
  ConfirmResult,
} from "./types";
export const createAnnualPlan = (data: AnnualInput, signal?: AbortSignal) =>
  apiRequest<AnnualPlan>("/api/plans/annual", {
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
  apiRequest<AnnualPlan>("/api/plans/annual/" + id, { signal });
/** 전체 교체다. theme 과 sub_themes 를 둘 다 보낸다 — 하나만 보내면 나머지가 지워진다(§6). */
export const putAnnualMonth = (id: number, month: number, data: MonthInput) =>
  apiRequest<AnnualMonth>("/api/plans/annual/" + id + "/months/" + month, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
/** 변경 이력. 시간순이고 필터 · 페이지가 없다 — 화면이 `month` 로 거른다. */
export const getAnnualPlanAudit = (id: number, signal?: AbortSignal) =>
  apiRequest<{ items: AnnualAuditEvent[] }>("/api/plans/annual/" + id + "/audit", { signal });
/**
 * 확정 전 연간계획안을 지운다. 반 하나에 연간은 하나라, 다시 만들려면 먼저 지워야 한다.
 *
 * 확정본은 409 `GATE_BLOCKED`, 월간이 딸려 있으면 409 `IN_USE` 다. 둘 다 서버 문구를 띄운다.
 */
export const deleteAnnualPlan = (id: number) =>
  apiRequest<void>("/api/plans/annual/" + id, { method: "DELETE" });
/**
 * **시험용.** 연간과 딸린 월간을 한 번에 지운다. 확정 여부를 보지 않는다.
 *
 * **파일럿 시작 전에 끈다.** 서버 `ALLOW_TEST_RESET` 과 화면 `NEXT_PUBLIC_ALLOW_TEST_RESET`
 * 둘 다 기본이 꺼짐이다. 서버가 꺼져 있으면 이 경로는 404 다.
 *
 * 확정하면 고칠 수도 지울 수도 없어서(계획안에는 `unconfirm` 이 없다) 시험할 때 막힌다.
 * 그 막다른 길을 열어 두는 것이고, 교사가 쓰는 `deleteAnnualPlan` 은 그대로 둔다.
 */
export const testResetAnnualPlan = (id: number) =>
  apiRequest<void>("/api/plans/annual/" + id + "/test-reset", { method: "DELETE" });
/** 시험용 지우기 단추를 띄울지. 켜는 곳이 둘이라 어긋나도 안전하다 — 서버가 최종이다. */
export const TEST_RESET_ENABLED = process.env.NEXT_PUBLIC_ALLOW_TEST_RESET === "1";
export const confirmAnnualPlan = (id: number) =>
  apiRequest<ConfirmResult>("/api/plans/annual/" + id + "/confirm", { method: "POST" });

/** 확정한 연간계획안을 hwpx 로 내려받는다 (§9). */
export const downloadAnnualHwpx = (id: number) =>
  downloadHwpx(`/api/plans/${id}/export/hwp`, "연간계획안.hwpx");
