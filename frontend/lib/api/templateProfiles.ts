import { apiRequest } from "./client";
import type { ProfileResolution, ReadyProfile } from "./types";

/** 월간 양식 설정 조회 둘뿐이다 (docs/api-spec.md §9-2). 만들기 · 바꾸기 API 는 아직 없다. */
export const getClassTemplateProfile = (classId: number, signal?: AbortSignal) =>
  apiRequest<ProfileResolution>("/api/classes/" + classId + "/template-profile", { signal });
/** READY 만 온다. 화면은 여기서 고른 정확한 `profile_ref` 를 생성에 보낸다. */
export const listReadyTemplateProfiles = (centerId: number, signal?: AbortSignal) =>
  apiRequest<{ items: ReadyProfile[] }>("/api/centers/" + centerId + "/template-profiles", {
    signal,
  });
