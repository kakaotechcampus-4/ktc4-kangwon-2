import { apiRequest } from "./client";

/**
 * 일과 기록 (docs/api-spec.md §10-1). **일일 보육일지의 「사실」이 여기서 나온다.**
 *
 * 생성 엔드포인트가 없다 — 활동실행은 있었던 일이라 AI 가 쓰면 위조다. 교사가 적은
 * 그대로 저장한다 (ADR-025).
 */
export type Routine = {
  id: number;
  class_id: number;
  class_name: string;
  /** YYYY-MM-DD */
  date: string;
  /** 하루 안의 표시 순서. 종이의 행 순서다. */
  position: number;
  /** HH:MM. 둘 다 있으면 start < end. 없을 수 있다. */
  start: string | null;
  end: string | null;
  name: string;
  /** 활동계획. 선택. */
  plan: string;
  /** 활동실행 — 이 칸이 일지의 사실이 된다. 비어 있어도 저장된다. */
  execution: string;
  created_at: string;
};

/** `PUT` 은 통째로 바꾼다. **안 보낸 칸은 지워진다** (§10-1). */
export type RoutineInput = {
  date: string;
  position?: number;
  start?: string | null;
  end?: string | null;
  name: string;
  plan?: string;
  execution?: string;
};

/** `POST` 는 반을 같이 보낸다. `PUT` 에 반을 보내면 422 다 — 반이 바뀌면 다른 기록이다. */
export type RoutineCreateInput = RoutineInput & { class_id: number };

/**
 * 셋 다 선택이지만 **`class_id` 를 빼지 않는다.** 빼면 그 교사의 원 전체가 와서
 * 다른 반 기록이 섞인다 (FR-405).
 */
export type RoutineQuery = { class_id?: number; from?: string; to?: string };

const query = (q: RoutineQuery) => {
  const params = new URLSearchParams();
  if (q.class_id !== undefined) params.set("class_id", String(q.class_id));
  if (q.from) params.set("from", q.from);
  if (q.to) params.set("to", q.to);
  const text = params.toString();
  return text ? `?${text}` : "";
};

/** 날짜 오름차순, 하루 안에서는 position · start · id 순으로 온다 — 종이의 행 순서다. */
export const listRoutines = (q: RoutineQuery = {}) =>
  apiRequest<{ items: Routine[] }>(`/api/routines${query(q)}`).then((body) => body.items);

/** 하루치. S-J1 이 여는 화면이 이것이다. */
export const listRoutinesOfDay = (classId: number, date: string) =>
  listRoutines({ class_id: classId, from: date, to: date });

export const createRoutine = (data: RoutineCreateInput) =>
  apiRequest<Routine>("/api/routines", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });

export const updateRoutine = (id: number, data: RoutineInput) =>
  apiRequest<Routine>(`/api/routines/${id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });

export const deleteRoutine = (id: number) =>
  apiRequest<void>(`/api/routines/${id}`, { method: "DELETE" });

/**
 * 화면이 들고 있는 줄. 서버에 아직 없는 줄은 `id` 가 없다.
 *
 * **저장을 누를 때만 서버에 간다**(S-J1). 그래서 화면은 「새 줄 · 고친 줄 · 지운 줄」을
 * 모아 뒀다가 한 번에 보낸다.
 */
export type RoutineDraft = RoutineInput & { id?: number };

/**
 * 한 번에 저장한다. **지우기도 여기서 보낸다** — 잘못 눌러도 저장 안 하고 나가면
 * 서버에 그대로 있다.
 *
 * 순서가 있다. **지우기를 먼저** 한다 — 같은 자리(position)에 새 줄이 들어올 때
 * 지운 줄이 남아 있으면 순서가 겹친다.
 *
 * 하나라도 실패하면 **거기서 멈추고 던진다.** 반쯤 저장된 채로 「저장됐다」고 하면
 * 교사가 적은 것이 사라진 줄 모른다. 어디까지 됐는지는 화면이 다시 불러서 본다.
 */
export async function saveRoutines(
  classId: number,
  rows: RoutineDraft[],
  removedIds: number[] = [],
): Promise<Routine[]> {
  for (const id of removedIds) await deleteRoutine(id);
  const saved: Routine[] = [];
  for (const [index, row] of rows.entries()) {
    const body = { ...row, position: row.position ?? index };
    saved.push(
      row.id === undefined
        ? await createRoutine({ ...body, class_id: classId })
        : await updateRoutine(row.id, body),
    );
  }
  return saved;
}

/**
 * 어제 줄에서 **시간과 일과 이름만** 가져온다 (FR-403).
 *
 * 활동계획·활동실행은 비운다 — 어제 한 일이 오늘 한 일처럼 적히면 그건 위조다.
 * 불러오기는 조회일 뿐이고, 저장은 교사가 [저장] 을 눌러야 일어난다.
 */
/**
 * 하루 전 날짜. **`toISOString()` 을 쓰지 않는다** — 그 함수는 UTC 로 바꿔서 한국
 * 시간으로는 하루가 더 밀린다(아침 9시 전이면 그제가 된다). 글자만 계산한다.
 */
export function previousDay(date: string): string {
  const [year, month, day] = date.split("-").map(Number);
  const moved = new Date(Date.UTC(year, month - 1, day - 1));
  return moved.toISOString().slice(0, 10);
}

export async function copyFromPreviousDay(classId: number, date: string): Promise<RoutineDraft[]> {
  const rows = await listRoutinesOfDay(classId, previousDay(date));
  return rows.map((row, index) => ({
    date,
    position: index,
    start: row.start,
    end: row.end,
    name: row.name,
    plan: "",
    execution: "",
  }));
}
