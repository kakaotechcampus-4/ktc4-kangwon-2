import { apiRequest } from "./client";
import type { ApiChild, ApiChildTracking, ChildInput } from "./types";
export const getChildren = (classId: number) =>
  // 목록 봉투는 { items } 하나다 — count 를 따로 주지 않는다 (docs/api-spec.md §2-1).
  apiRequest<{ items: ApiChild[] }>("/api/classes/" + classId + "/children");
export const createChild = (classId: number, data: ChildInput) =>
  apiRequest<ApiChild>("/api/classes/" + classId + "/children", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
export const deleteChild = (id: number) =>
  apiRequest<void>("/api/children/" + id, { method: "DELETE" });
// 발달 추적 — 아이 · 영역별 관찰 기록 수. 기록 본문은 getObservations({ child_id }) 로 따로 받는다.
export const getChildTracking = (classId: number) =>
  apiRequest<{ items: ApiChildTracking[] }>("/api/classes/" + classId + "/children/tracking");
