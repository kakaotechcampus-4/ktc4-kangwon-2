/** 관찰 기록 화면이 쓰는 서버 접근. id 변환을 여기서 끝내고 화면에는 화면 id 만 준다. */
import {
  getObservations,
  createObservation,
  updateObservation,
  deleteObservation,
  suggestDomain,
  checkMissing,
  observationServerId,
  type ApiReviewImpact,
  type ServerObservation,
} from "./observations";
import { classServerId, childServerId } from "./onboarding";
import { toLocalObservation } from "./observation-ids";
import type { ObservationUpdate } from "./types";
import { chosenClassFor, loadClassSettings } from "../onboarding/settings";

/** 반·아동이 서버의 무엇인지 모르는 상태. 서버 id 를 지어내지 않고 여기서 멈춘다. */
export const UNMAPPED =
  "연결된 반·아동 정보를 확인할 수 없어요. 반·아동 관리에서 다시 저장해주세요.";

/** 반을 고르지 않았으면 주 반. 그것도 없으면 조회하지 않고 반 선택을 기다린다 (FR-405). */
export async function listRecords(
  classId?: string,
  period: { from?: string; to?: string } = {},
): Promise<ServerObservation[]> {
  const localId = classId ?? chosenClassFor(loadClassSettings())?.id;
  if (!localId) return [];
  const class_id = classServerId(localId);
  if (class_id === null) throw new Error(UNMAPPED);
  const { items } = await getObservations({ class_id, ...period });
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

/**
 * 고치거나 지워서 「다시 검토」가 된 확정 문서의 **서버 id** (§10 「저장 뒤 재검토 안내」).
 * `newlyStale` 은 이번에 처음 stale 이 된 것, `affected` 는 이미 stale 이던 것까지.
 */
export interface ReviewImpact {
  affected: number[];
  newlyStale: number[];
}

const impactOf = (raw?: ApiReviewImpact): ReviewImpact => ({
  affected: raw?.affected_document_ids ?? [],
  newlyStale: raw?.newly_stale_document_ids ?? [],
});

/** 반·아동은 바꾸지 못한다 — 대상이 바뀌면 다른 기록이다 (§10). */
export async function editRecord(
  localId: string,
  record: ObservationUpdate,
): Promise<{ record: ServerObservation; impact: ReviewImpact }> {
  const id = observationServerId(localId);
  if (id === null) throw new Error(UNMAPPED);
  const saved = await updateObservation(id, record, { impact: true });
  return { record: toLocalObservation(saved), impact: impactOf(saved.review_impact) };
}

export async function removeRecord(localId: string): Promise<ReviewImpact> {
  const id = observationServerId(localId);
  if (id === null) throw new Error(UNMAPPED);
  const done = await deleteObservation(id, { impact: true });
  return impactOf(done ? done.review_impact : undefined);
}

/**
 * 적던 사실로 AI 가 제안하는 영역. 없거나 실패하면 `null` — 덤이라 화면을 멈추지 않는다 (ADR-082).
 */
export async function suggestRecordDomain(
  classId: string,
  fact: string,
  context: string,
): Promise<string | null> {
  const class_id = classServerId(classId);
  if (class_id === null) return null;
  try {
    return (await suggestDomain({ class_id, fact, context })).domain;
  } catch {
    return null;
  }
}

/** 저장한 기록에서 빠진 것. 실패하면 빈 목록 — 쪽지를 안 띄울 뿐이다 (ADR-082). */
export async function missingInRecord(localId: string): Promise<string[]> {
  const id = observationServerId(localId);
  if (id === null) return [];
  try {
    return (await checkMissing(id)).missing;
  } catch {
    return [];
  }
}
