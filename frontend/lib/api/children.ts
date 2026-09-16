import { apiRequest } from "./client";
import type { ApiChild, ChildInput } from "./types";
export const getChildren = (classId: number) =>
  apiRequest<{ items: ApiChild[]; count: number }>("/api/classes/" + classId + "/children");
export const createChild = (classId: number, data: ChildInput) =>
  apiRequest<ApiChild>("/api/classes/" + classId + "/children", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
export const deleteChild = (id: number) =>
  apiRequest<void>("/api/children/" + id, { method: "DELETE" });
