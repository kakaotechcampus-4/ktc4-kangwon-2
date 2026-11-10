import { apiRequest } from "./client";
import type { Center, CenterInput, Daycare, PlanConfig, PlanConfigResponse } from "./types";
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
 * docs/api-spec.md §1 「어린이집 찾기」. 그 시군구 정부 어린이집 목록에서 이름으로 찾는다.
 * 원 정보는 고칠 수 없다(ADR-068) — 수정 API 가 없다.
 */
export const searchDaycares = (sido: string, sigungu: string, q: string) =>
  apiRequest<{ items: Daycare[] }>(
    `/api/daycares?${new URLSearchParams({ sido, sigungu, q })}`,
  ).then((r) => r.items);

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
  /** 어제 지원을 반영한 줄에 종이가 붙이는 글자 (ADR-086). 옛 서버는 안 보낸다. */
  reflect_mark?: ReflectMark;
  /** 이 계정이 바꿀 수 있는지 — 원을 처음 등록한 교사만 참이다 (ADR-087). 보내지 않는다. */
  can_edit?: boolean;
};

/** 빈 글은 「붙이지 않음」이다. */
export type ReflectMark = "(반영)" | "(놀이반영)" | "";

export const getCenterSettings = (centerId: number) =>
  apiRequest<CenterSettings>(`/api/centers/${centerId}/settings`);

export const saveCenterSettings = (
  centerId: number,
  data: Partial<Omit<CenterSettings, "can_edit">>,
) =>
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
