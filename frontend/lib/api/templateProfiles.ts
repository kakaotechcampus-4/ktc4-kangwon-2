import { apiRequest } from "./client";
import type {
  MonthlyTemplate,
  ProfilePointer,
  ProfilePointerInput,
  ProfileResolution,
  ReadyProfile,
  TemplateProfileInput,
} from "./types";

/** 월간 양식 설정 (docs/api-spec.md §9-2 조회 · §9-4 관리). DRAFT 편집 · 보관 API 는 아직 없다. */
const json = (method: string, data: unknown, signal?: AbortSignal): RequestInit => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(data),
  signal,
});

/** 반에 실제로 쓰이는 Profile (override → 원 기본 → 선택 필요). 포인터 그대로는 아래 GET 이 준다. */
export const getClassTemplateProfile = (classId: number, signal?: AbortSignal) =>
  apiRequest<ProfileResolution>("/api/classes/" + classId + "/template-profile", { signal });
/** READY 만 온다. 화면은 여기서 고른 정확한 `profile_ref` 를 생성에 보낸다. */
export const listReadyTemplateProfiles = (centerId: number, signal?: AbortSignal) =>
  apiRequest<{ items: ReadyProfile[] }>("/api/centers/" + centerId + "/template-profiles", {
    signal,
  });
/** 기반 Template 목록. 승인 대기도 `approved: false` 로 온다. */
export const listMonthlyTemplates = (signal?: AbortSignal) =>
  apiRequest<{ items: MonthlyTemplate[] }>("/api/monthly-templates", { signal });
/**
 * 「Reference 기반 시작」 → 원 소유 READY v1 (201). **멱등이 아니다** — 재시도하지 않는다.
 * 원 기본은 바꾸지 않는다. 승인 전 Template 이면 409 `GATE_BLOCKED`.
 */
export const createTemplateProfile = (
  centerId: number,
  data: TemplateProfileInput,
  signal?: AbortSignal,
) =>
  apiRequest<ReadyProfile>(
    "/api/centers/" + centerId + "/template-profiles",
    json("POST", data, signal),
  );
export const getCenterDefaultProfile = (centerId: number, signal?: AbortSignal) =>
  apiRequest<ProfilePointer>("/api/centers/" + centerId + "/template-profile-default", { signal });
/** 지정 · 해제. 본 값(`expected_profile_ref`)이 지금 값과 다르면 409 `STALE_WRITE`. */
export const putCenterDefaultProfile = (
  centerId: number,
  data: ProfilePointerInput,
  signal?: AbortSignal,
) =>
  apiRequest<ProfilePointer>(
    "/api/centers/" + centerId + "/template-profile-default",
    json("PUT", data, signal),
  );
/** 반 override 포인터 그대로. 대상을 못 쓰게 된 포인터도 보인다 — 해제할 때 expected 로 쓴다. */
export const getClassProfileOverride = (classId: number, signal?: AbortSignal) =>
  apiRequest<ProfilePointer>("/api/classes/" + classId + "/template-profile-override", { signal });
/** 해제(`profile_ref: null`)하면 원 기본으로 돌아간다. Profile 을 지우지 않는다. */
export const putClassProfileOverride = (
  classId: number,
  data: ProfilePointerInput,
  signal?: AbortSignal,
) =>
  apiRequest<ProfilePointer>(
    "/api/classes/" + classId + "/template-profile-override",
    json("PUT", data, signal),
  );
