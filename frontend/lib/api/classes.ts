import { apiRequest } from "./client";
import type { ApiClass, ClassInput, ClassUpdate } from "./types";
export const getClasses = (centerId: number) =>
  apiRequest<{ items: ApiClass[] }>("/api/centers/" + centerId + "/classes");
// 남이 주인인 반은 쓸 수 없다 (ADR-059). 칸이 없는 건 옛 서버 응답이라 지금처럼 쓴다.
export const isMyClass = (item: ApiClass) =>
  !item.my_access || item.my_access === "OWNER" || item.my_access === "OPEN";
export const createClass = (centerId: number, data: ClassInput) =>
  apiRequest<ApiClass>("/api/centers/" + centerId + "/classes", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
// 반 수정 (§2). 보낸 칸만 바뀐다 — 원 정보 수정(updateCenter)과 같은 방식이다.
export const updateClass = (classId: number, patch: ClassUpdate) =>
  apiRequest<ApiClass>("/api/classes/" + classId, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  });
