/** 관찰 기록 API 와 화면 model 사이의 변환 (docs/api-spec.md §10). */
import { apiRequest } from "./client";
import { CLASS_PREFIX, CHILD_PREFIX } from "./onboarding";
import type { ApiObservation, ObservationInput, ObservationUpdate } from "./types";
import type { Observation } from "../workspace/model";

// 서버 id 는 테이블마다 1 부터 센다. 화면 id 와 섞이지 않게 접두사를 붙인다.
const OBSERVATION_PREFIX = "observation:";
// 접두사는 onboarding.ts 가 정한다 — 세 군데서 따로 들면 어긋나는 순간 id 가 갈린다.

// 안전한 양의 정수 id 만 받는다.
const SERVER_ID = /^[1-9][0-9]*$/;

export const observationLocalId = (serverId: number) => OBSERVATION_PREFIX + serverId;

/** 화면 id 에서 서버 id 를 되찾는다. 서버에서 온 id 가 아니면 `null`. */
export function observationServerId(localId: string): number | null {
  if (!localId.startsWith(OBSERVATION_PREFIX)) return null;
  const raw = localId.slice(OBSERVATION_PREFIX.length);
  if (!SERVER_ID.test(raw)) return null;
  const id = Number(raw);
  return Number.isSafeInteger(id) ? id : null;
}

/** 화면 model + 서버에만 있는 값. `childCode` 는 아동 실명(`childName`)의 대체 코드다. */
export interface ServerObservation extends Observation {
  childCode: string;
  serverId: number;
  serverClassId: number;
  serverChildId: number;
}

/**
 * 서버 응답 → 화면 model.
 *
 * `classId` · `childId` 는 온보딩의 로컬 id 가 아니라 접두사를 붙인 서버 id 다.
 * 문자열은 자르거나 고치지 않는다.
 */
export function toObservation(dto: ApiObservation): ServerObservation {
  return {
    id: observationLocalId(dto.id),
    classId: CLASS_PREFIX + dto.class_id,
    className: dto.class_name,
    childId: CHILD_PREFIX + dto.child_id,
    childName: dto.child_name,
    childCode: dto.child_code,
    date: dto.date,
    domain: dto.domain,
    context: dto.context,
    fact: dto.fact,
    createdAt: dto.created_at,
    serverId: dto.id,
    serverClassId: dto.class_id,
    serverChildId: dto.child_id,
  };
}

/** 넷 다 선택이다 (§10). */
export interface ObservationQuery {
  class_id?: number;
  child_id?: number;
  from?: string;
  to?: string;
}

function query(params: ObservationQuery): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params))
    if (value !== undefined) search.set(key, String(value));
  const text = search.toString();
  return text ? "?" + text : "";
}

/** 정렬은 서버가 `date` 내림차순으로 고정한다 (§10). */
export const getObservations = (params: ObservationQuery = {}) =>
  apiRequest<{ items: ApiObservation[] }>("/api/observations" + query(params));

export const createObservation = (data: ObservationInput) => {
  // 런타임의 추가 필드를 제외한다.
  const body: ObservationInput = {
    class_id: data.class_id,
    child_id: data.child_id,
    date: data.date,
    domain: data.domain,
    context: data.context,
    fact: data.fact,
  };
  return apiRequest<ApiObservation>("/api/observations", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
};

/** 이 기록을 직접 쓴 확정 문서. `include_impact=true` 일 때만 온다 (§10 「저장 뒤 재검토 안내」). */
export interface ApiReviewImpact {
  affected_document_ids: number[];
  newly_stale_document_ids: number[];
}

const IMPACT = "?include_impact=true";

export const updateObservation = (
  id: number,
  data: ObservationUpdate,
  { impact = false }: { impact?: boolean } = {},
) => {
  // 런타임의 추가 필드를 제외한다.
  const body: ObservationUpdate = {
    date: data.date,
    domain: data.domain,
    context: data.context,
    fact: data.fact,
  };
  return apiRequest<ApiObservation & { review_impact?: ApiReviewImpact }>(
    "/api/observations/" + id + (impact ? IMPACT : ""),
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    },
  );
};

/** 204 No Content — 본문이 없어 `undefined` 를 돌려준다. `impact` 면 영향을 담은 200 이다. */
export const deleteObservation = (id: number, { impact = false }: { impact?: boolean } = {}) =>
  apiRequest<{ review_impact: ApiReviewImpact } | void>(
    "/api/observations/" + id + (impact ? IMPACT : ""),
    { method: "DELETE" },
  );

/** 영역 추천 (ADR-082). `domain` 은 제안일 뿐이다 — 화면은 교사가 눌러야 고른다. */
export const suggestDomain = (data: { class_id: number; fact: string; context: string }) =>
  apiRequest<{ domain: string | null; confidence: number | null }>(
    "/api/observations/domain-suggest",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ class_id: data.class_id, fact: data.fact, context: data.context }),
    },
  );

/** 저장한 기록에서 빠진 것 — 「상황」 「행동」 「반응」 중 (ADR-082). */
export const checkMissing = (id: number) =>
  apiRequest<{ missing: string[] }>(`/api/observations/${id}/missing`, { method: "POST" });
