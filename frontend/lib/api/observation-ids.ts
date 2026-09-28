/** 서버 관찰 기록의 반·아동 id 를 온보딩이 저장해 둔 화면 id 로 바꾼다. */
import { classLocalId, childLocalId } from "./onboarding";
import { toObservation, type ServerObservation } from "./observations";
import type { ApiObservation } from "./types";

/** 매핑이 없으면 서버 접두사를 그대로 둔다 — 화면 id 를 지어내지 않는다. */
export function toLocalObservation(dto: ApiObservation): ServerObservation {
  const observation = toObservation(dto);
  return {
    ...observation,
    classId: classLocalId(dto.class_id) ?? observation.classId,
    childId: childLocalId(dto.child_id) ?? observation.childId,
  };
}
