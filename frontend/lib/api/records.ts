/** 관찰 기록 화면이 쓰는 서버 접근. id 변환을 여기서 끝내고 화면에는 화면 id 만 준다. */
import {
  getObservations,
  createObservation,
  updateObservation,
  deleteObservation,
  observationServerId,
  type ServerObservation,
} from "./observations";
import { classServerId, childServerId } from "./onboarding";
import { toLocalObservation } from "./observation-ids";
import type { ObservationUpdate } from "./types";

/** 반·아동이 서버의 무엇인지 모르는 상태. 서버 id 를 지어내지 않고 여기서 멈춘다. */
export const UNMAPPED =
  "연결된 반·아동 정보를 확인할 수 없어요. 반·아동 관리에서 다시 저장해주세요.";

/** 정렬은 서버가 정한다. 반·아동 필터는 화면이 화면 id 로 건다. */
export async function listRecords(): Promise<ServerObservation[]> {
  const { items } = await getObservations();
  return items.map(toLocalObservation);
}

export async function addRecord(
  record: ObservationUpdate & { classId: string; childId: string },
): Promise<ServerObservation> {
  const class_id = classServerId(record.classId);
  const child_id = childServerId(record.childId);
  if (class_id === null || child_id === null) throw new Error(UNMAPPED);
  return toLocalObservation(
    await createObservation({
      class_id,
      child_id,
      date: record.date,
      domain: record.domain,
      context: record.context,
      fact: record.fact,
    }),
  );
}

/** 반·아동은 바꾸지 못한다 — 대상이 바뀌면 다른 기록이다 (§10). */
export async function editRecord(
  localId: string,
  record: ObservationUpdate,
): Promise<ServerObservation> {
  const id = observationServerId(localId);
  if (id === null) throw new Error(UNMAPPED);
  return toLocalObservation(await updateObservation(id, record));
}

export async function removeRecord(localId: string): Promise<void> {
  const id = observationServerId(localId);
  if (id === null) throw new Error(UNMAPPED);
  await deleteObservation(id);
}
