/** 상단바 알림함 — 같은 원 열람 요청이 오가면 쌓인다 (docs/api-spec.md, ADR-059 의 보충). */
import { apiRequest } from "./client";

/** 사건은 이 넷이 전부다. */
export type NotificationKind =
  "ACCESS_REQUESTED" | "ACCESS_APPROVED" | "ACCESS_REJECTED" | "ACCESS_REVOKED";

export interface NotificationItem {
  id: number;
  kind: NotificationKind;
  request_id: number;
  /** 요청이 걸린 반 — 받은 쪽에는 내 반, 보낸 쪽에는 남의 반이다. */
  class_id: number;
  class_name: string;
  /** 요청한 교사. 결과 알림(승인 · 거절 · 취소)에서는 쓰지 않는다. */
  requester_name: string;
  created_at: string;
  /** `null` 이 안 읽음. 안 읽은 수는 서버가 주지 않는다 — 화면이 센다. */
  read_at: string | null;
}

/** 나의 것만 최근 30개, 새것이 먼저다. 원 · 반이 없어도 빈 목록이다. */
export const listNotifications = () =>
  apiRequest<{ items: NotificationItem[] }>("/api/me/notifications");

/** 1~30개. 남의 id · 없는 id 는 서버가 조용히 넘긴다. 204. */
export const markNotificationsRead = (ids: number[]) =>
  apiRequest<void>("/api/me/notifications/read", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ids }),
  });
