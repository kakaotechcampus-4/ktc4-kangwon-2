import { apiRequest } from "./client";
import type { Center, CenterInput, PlanConfig, PlanConfigResponse } from "./types";
import type { Month } from "../onboarding/types";

/** docs/api-spec.md §3. 1~12월을 각각 한 번씩 담는 전체 설정. */
export type Greetings = { enabled: boolean; items: { month: Month; text: string }[] };

export const getGreetings = (centerId: number) =>
  apiRequest<Greetings>(`/api/centers/${centerId}/greetings`);

export const saveGreetings = (centerId: number, data: Greetings) =>
  apiRequest<Greetings>(`/api/centers/${centerId}/greetings`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });

export const createCenter = (data: CenterInput) =>
  apiRequest<Center>("/api/centers", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
/** docs/api-spec.md §1. 자기 원만 읽는다. */
export const getCenter = (centerId: number) => apiRequest<Center>(`/api/centers/${centerId}`);
/**
 * docs/api-spec.md §1. 원명 · 원장 이름 · 지역을 고친다. **보낸 칸만 바뀐다.**
 *
 * 지역 두 칸은 함께 보낸다 — 시·도만 바꾸면 시·군·구가 그 시·도에 없는 값으로 남는다.
 */
export const updateCenter = (centerId: number, data: Partial<CenterInput>) =>
  apiRequest<Center>(`/api/centers/${centerId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });

/**
 * docs/api-spec.md §3-1. 켜고 끄는 값만 모은다.
 *
 * **성품인사(§3)와 달리 전체 교체가 아니다.** 보낸 칸만 바뀐다 — 토글이 늘어도
 * 서로를 덮지 않는다.
 */
export type CenterSettings = {
  trends_enabled: boolean;
  weekly_saturday_enabled?: boolean;
  /** 관찰 기록의 영역 축 (lib/workspace/observation-axis.ts). */
  observation_axis: "NURI_5" | "DAILY_PLAY_2";
};

export const getCenterSettings = (centerId: number) =>
  apiRequest<CenterSettings>(`/api/centers/${centerId}/settings`);

export const saveCenterSettings = (centerId: number, data: Partial<CenterSettings>) =>
  apiRequest<CenterSettings>(`/api/centers/${centerId}/settings`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });

export const savePlanConfig = (id: number, data: PlanConfig) =>
  apiRequest<PlanConfigResponse>("/api/centers/" + id + "/plan-config", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
