import { apiRequest, ApiError } from "./client";
import { readToken } from "../auth/token";
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

/**
 * 확정한 연간계획안을 hwpx 로 내려받는다 (§9).
 *
 * `apiRequest` 를 못 쓴다 — 그건 JSON 을 되돌려 주는데 여기는 파일이다.
 * 실패 응답만 JSON 이라, 그때는 같은 모양(`ApiError`)으로 던져 화면이 서버 문구를 띄운다.
 *
 * 파일 이름은 서버가 `Content-Disposition` 에 담아 준다. 한글이라 `filename*` 쪽을 읽는다 —
 * 우리가 지어내면 서버가 양식을 바꿀 때 이름만 옛 것으로 남는다.
 */
export async function downloadAnnualHwpx(id: number): Promise<void> {
  const token = readToken();
  const response = await fetch(`/api/plans/${id}/export/hwp`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!response.ok) {
    let body: unknown;
    try {
      body = await response.json();
    } catch {
      body = null;
    }
    throw new ApiError(response.status, body);
  }

  const disposition = response.headers.get("Content-Disposition") ?? "";
  const encoded = /filename\*=UTF-8''([^;]+)/i.exec(disposition)?.[1];
  const name = encoded ? decodeURIComponent(encoded) : "연간계획안.hwpx";

  const url = URL.createObjectURL(await response.blob());
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = name;
  anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
