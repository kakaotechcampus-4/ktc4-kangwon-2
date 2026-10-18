/** 일과 기록 API (docs/api-spec.md §10-1 · ADR-025). 일일 보육일지의 사실 층이다. */
import { apiRequest } from "./client";
import { createMutationBarrier } from "./pending-mutations";

// Shared by every page instance in this tab, including a page revisited during a pending write.
const mutations = createMutationBarrier<string>();
export const trackRoutineMutation = mutations.track;
export const waitForRoutineScope = mutations.wait;

/** `POST · GET · PUT` 응답 한 줄. 시간은 `09:20:00` 으로 온다. */
export interface ApiRoutine {
  id: number;
  class_id: number;
  class_name: string;
  date: string;
  position: number;
  start: string | null;
  end: string | null;
  name: string;
  plan: string;
  execution: string;
  created_at: string;
  /** include_impact=true PUT 응답에서만 온다. */
  review_impact?: RoutineReviewImpact;
}

/** 직접 영향을 받은 확정 일일 보육일지. 전파된 주간 문서와 초안은 포함하지 않는다. */
export interface RoutineReviewImpact {
  affected_document_ids: number[];
  newly_stale_document_ids: number[];
}
export type Routine = ApiRoutine;

/**
 * `PUT` 의 body 다 — 통째로 바꾼다. **`class_id` 를 넣으면 422 다** (반이 바뀌면 다른 기록이다).
 * `POST` 만 `class_id` 를 함께 보낸다.
 */
export interface RoutineInput {
  date: string;
  position?: number;
  start?: string | null;
  end?: string | null;
  name: string;
  plan?: string;
  execution?: string;
}
export type RoutineCreateInput = RoutineInput & { class_id: number };
export type RoutineDraft = RoutineInput & { id?: number };

/** 셋 다 선택이다 (§10-1). */
export interface RoutineQuery {
  class_id?: number;
  from?: string;
  to?: string;
}

// 서버 id 는 테이블마다 1 부터 센다. 화면 id 와 섞이지 않게 접두사를 붙인다 (observations 와 같은 규칙).
const ROUTINE_PREFIX = "routine:";
// 안전한 양의 정수 id 만 받는다.
const SERVER_ID = /^[1-9][0-9]*$/;

export const routineLocalId = (serverId: number) => ROUTINE_PREFIX + serverId;

/** 화면 id 에서 서버 id 를 되찾는다. 서버에서 온 id 가 아니면 `null`. */
export function routineServerId(localId: string): number | null {
  if (!localId.startsWith(ROUTINE_PREFIX)) return null;
  const raw = localId.slice(ROUTINE_PREFIX.length);
  if (!SERVER_ID.test(raw)) return null;
  const id = Number(raw);
  return Number.isSafeInteger(id) ? id : null;
}

/** 서버는 `09:20:00` 으로 주고 `<input type="time">` 은 분까지만 쓴다. 빈 값이 「시간 없음」이다. */
export const routineTime = (value: string | null) => value?.slice(0, 5) ?? "";

/** 빈 칸은 보내지 않고 지운다 — 시간은 선택이다 (§10-1). */
export const routineTimeValue = (value: string) => value || null;

function query(params: RoutineQuery): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params))
    if (value !== undefined) search.set(key, String(value));
  const text = search.toString();
  return text ? "?" + text : "";
}

const json = (method: string, body: unknown) => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

/** 정렬은 서버가 날짜 · `position` · 시작 시간 · id 로 고정한다 — 종이의 행 순서다 (§10-1). */
export const listRoutines = (params: RoutineQuery = {}) =>
  apiRequest<{ items: ApiRoutine[] }>("/api/routines" + query(params)).then((body) => body.items);

export const listRoutinesOfDay = (classId: number, date: string) =>
  listRoutines({ class_id: classId, from: date, to: date });

/** 기존 S-J1 호출과 #164의 객체 호출을 모두 지원한다. */
export function createRoutine(data: RoutineCreateInput): Promise<ApiRoutine>;
export function createRoutine(classId: number, input: RoutineInput): Promise<ApiRoutine>;
export function createRoutine(data: number | RoutineCreateInput, input?: RoutineInput) {
  const row = typeof data === "number" ? input! : data;
  const class_id = typeof data === "number" ? data : data.class_id;
  return apiRequest<ApiRoutine>("/api/routines", json("POST", { class_id, ...routineBody(row) }));
}

const routineBody = (input: RoutineInput): RoutineInput => ({
  date: input.date,
  position: input.position ?? 0,
  start: input.start ?? null,
  end: input.end ?? null,
  name: input.name,
  plan: input.plan ?? "",
  execution: input.execution ?? "",
});

const impactQuery = (options?: { includeImpact: boolean }) =>
  options?.includeImpact ? "?include_impact=true" : "";

/** 런타임의 추가 필드를 빼고 계약에 있는 값만 보낸다 — 서버가 `extra="forbid"` 다. */
export const updateRoutine = (
  id: number,
  input: RoutineInput,
  options?: { includeImpact: boolean },
) =>
  apiRequest<ApiRoutine>(
    "/api/routines/" + id + impactQuery(options),
    json("PUT", routineBody(input)),
  );

/** 204 No Content — 본문이 없어 `undefined` 를 돌려준다. */
export const deleteRoutine = (id: number, options?: { includeImpact: boolean }) =>
  apiRequest<{ review_impact: RoutineReviewImpact } | void>(
    "/api/routines/" + id + impactQuery(options),
    { method: "DELETE" },
  );

/** #164의 저장 API. 배열 순서를 저장하므로 과거 position을 다시 보내지 않는다. */
export async function saveRoutines(
  classId: number,
  rows: RoutineDraft[],
  removedIds: number[] = [],
) {
  for (const id of removedIds) await deleteRoutine(id);
  const saved: ApiRoutine[] = [];
  for (const [position, row] of rows.entries()) {
    const body = routineBody({ ...row, position });
    saved.push(
      row.id === undefined
        ? await createRoutine({ ...body, class_id: classId })
        : await updateRoutine(row.id, body),
    );
  }
  return saved;
}

export function previousDay(date: string): string {
  const [year, month, day] = date.split("-").map(Number);
  return new Date(Date.UTC(year, month - 1, day - 1)).toISOString().slice(0, 10);
}

export async function copyFromPreviousDay(classId: number, date: string): Promise<RoutineDraft[]> {
  const rows = await listRoutinesOfDay(classId, previousDay(date));
  return rows.map((row, position) => ({
    date,
    position,
    start: row.start,
    end: row.end,
    name: row.name,
    plan: "",
    execution: "",
  }));
}

/** 일지가 근거 사본으로 남기는 한 줄과 같은 모양이다 — `[오전 실내놀이 09:20~10:40] 활동실행` (§10-1). */
export function routineFactText(row: Pick<ApiRoutine, "name" | "start" | "end" | "execution">) {
  const from = routineTime(row.start);
  const to = routineTime(row.end);
  const when = from || to ? ` ${from}~${to}` : "";
  return `[${row.name.trim()}${when}] ${row.execution.trim()}`;
}
