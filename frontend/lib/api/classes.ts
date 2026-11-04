import { apiRequest } from "./client";
import type {
  AccessRequest,
  ApiClass,
  ArchiveSummaryItem,
  ClassInput,
  ReceivedAccessRequest,
} from "./types";
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

/** 같은 원이면 열람 상태와 관계없이 받는다 (docs/api-spec.md §2-2 「요약」). */
export const getArchiveSummary = (classId: number) =>
  apiRequest<{ items: ArchiveSummaryItem[] }>("/api/classes/" + classId + "/archive-summary");
/** body 없음. 거절 · 취소 뒤 다시 보내도 같은 줄이 PENDING 으로 돌아간다 (§2-2 「요청」). */
export const requestClassAccess = (classId: number) =>
  apiRequest<AccessRequest>("/api/classes/" + classId + "/access-requests", { method: "POST" });
/** 내가 주인인 반에 온 요청. PENDING 이 먼저다 (§2-2 「받은 요청」). */
export const getReceivedRequests = () =>
  apiRequest<{ items: ReceivedAccessRequest[] }>("/api/access-requests/received");
/** PENDING → APPROVED · REJECTED, APPROVED → REVOKED 만 된다. 그 밖은 409 STALE_WRITE. */
export const decideAccessRequest = (
  requestId: number,
  status: "APPROVED" | "REJECTED" | "REVOKED",
) =>
  apiRequest<ReceivedAccessRequest>("/api/access-requests/" + requestId, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status }),
  });
