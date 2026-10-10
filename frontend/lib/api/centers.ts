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
/** docs/api-spec.md §1-1. 같은 원 교사를 들이는 1회용 코드. 7일 뒤 만료된다. */
export type Invite = { code: string; expires_at: string };

export const createInvite = (centerId: number) =>
  apiRequest<Invite>(`/api/centers/${centerId}/invites`, { method: "POST" });

export const joinCenter = (code: string) =>
  apiRequest<Center>("/api/centers/join", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ code }),
  });
export const savePlanConfig = (id: number, data: PlanConfig) =>
  apiRequest<PlanConfigResponse>("/api/centers/" + id + "/plan-config", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
