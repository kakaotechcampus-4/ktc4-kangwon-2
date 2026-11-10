/** 같은 원 다른 반 열람 요청 · 승인과 잠긴 반 요약 (docs/api-spec.md §2-2, ADR-059). */
import { apiRequest, errorCode } from "./client";

/** 요약이 주는 종류. 계획안 셋과 문서 넷이다. */
export type ArchiveKind =
  "annual" | "monthly" | "weekly" | "dailyLog" | "weeklyLog" | "observation" | "assessment";

/** 잠긴 반에서도 보이는 한 줄 — **제목 · 아이 이름 · 문서 id 는 없다.** */
export interface ArchiveSummaryItem {
  kind: ArchiveKind;
  start: string;
  end: string;
  status: "DRAFT" | "CONFIRMED";
}

export type AccessStatus = "PENDING" | "APPROVED" | "REJECTED" | "REVOKED";

/** 내가 주인인 반에 온 요청 하나. */
export interface ReceivedRequest {
  id: number;
  class_id: number;
  class_name: string;
  requester_name: string;
  status: AccessStatus;
  created_at: string;
  updated_at: string;
}

export const getArchiveSummary = (classId: number) =>
  apiRequest<{ items: ArchiveSummaryItem[] }>(`/api/classes/${classId}/archive-summary`);

/** body 없이 보낸다. 거절 · 취소 뒤 다시 보내면 같은 줄이 PENDING 으로 돌아온다. */
export const requestClassAccess = (classId: number) =>
  apiRequest<{ id: number; class_id: number; status: AccessStatus }>(
    `/api/classes/${classId}/access-requests`,
    { method: "POST" },
  );

/** PENDING 이 먼저, 그 안에서 최근 것이 위다. */
export const listReceivedRequests = () =>
  apiRequest<{ items: ReceivedRequest[] }>("/api/access-requests/received");

/** PENDING → APPROVED · REJECTED, APPROVED → REVOKED 만 된다. 나머지는 409 `STALE_WRITE`. */
export const decideRequest = (id: number, status: Exclude<AccessStatus, "PENDING">) =>
  apiRequest<ReceivedRequest>(`/api/access-requests/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status }),
  });

/**
 * 403 두 코드에 교사가 읽을 말. 다른 오류면 `null` 이다.
 *
 * 승인이 없거나 거둬졌으면 **다시 요청하는 길**을, 보기만 되는 반이면 **누가 고칠 수 있는지**를
 * 말한다 — 둘 다 「권한이 없습니다」로 묶으면 교사가 무엇을 해야 할지 모른다.
 */
export function classAccessMessage(error: unknown): string | null {
  const code = errorCode(error);
  if (code === "CLASS_ACCESS_REQUIRED")
    return "이 반은 담임 선생님이 승인해야 볼 수 있어요. 승인이 취소됐을 수 있으니 다시 요청해 주세요.";
  if (code === "CLASS_READ_ONLY")
    return "승인받은 반은 보기와 내려받기만 돼요. 수정 · 확정 · 삭제는 담임 선생님만 할 수 있어요.";
  return null;
}
