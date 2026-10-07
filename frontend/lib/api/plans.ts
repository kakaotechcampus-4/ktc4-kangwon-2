import { apiRequest } from "./client";
import type {
  AnnualInput,
  AnnualPlan,
  AnnualPlanSummary,
  AnnualMonth,
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
/** 계획 노트 목록. 이게 없으면 번호를 잃은 계획안을 다시 못 찾는다(§5). */
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
export const confirmAnnualPlan = (id: number) =>
  apiRequest<ConfirmResult>("/api/plans/annual/" + id + "/confirm", { method: "POST" });
