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
export const savePlanConfig = (id: number, data: PlanConfig) =>
  apiRequest<PlanConfigResponse>("/api/centers/" + id + "/plan-config", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
