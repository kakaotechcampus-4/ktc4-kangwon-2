/** 일과 기록 API (docs/api-spec.md §10-1). 일일 보육일지 만들기(S-J2)가 근거로 읽는다. */
import { apiRequest } from "./client";
import { classServerId } from "./onboarding";

// 서버 id 는 테이블마다 1 부터 센다. 관찰 기록 · 문서 id 와 섞이지 않게 접두사를 붙인다.
const ROUTINE_PREFIX = "routine:";
const SERVER_ID = /^[1-9][0-9]*$/;

export const routineLocalId = (serverId: number) => ROUTINE_PREFIX + serverId;

export function routineServerId(localId: string): number | null {
  if (!localId.startsWith(ROUTINE_PREFIX)) return null;
  const raw = localId.slice(ROUTINE_PREFIX.length);
  if (!SERVER_ID.test(raw)) return null;
  const id = Number(raw);
  return Number.isSafeInteger(id) ? id : null;
}

interface ApiRoutine {
  id: number;
  date: string;
  position: number;
  start: string | null; // "09:00:00" — 시간대가 없는 시각이라 잘라 써도 된다
  end: string | null;
  name: string;
  plan: string;
  execution: string;
}

export interface Routine {
  id: string;
  date: string;
  time: string;
  name: string;
  execution: string;
}

const hhmm = (t: string | null) => (t ? t.slice(0, 5) : "");

/** 「09:20 ~ 10:40」. 한쪽만 있으면 그쪽만, 둘 다 없으면 빈 문자열 — 서버 사실 줄과 같은 규칙이다. */
function timeRange(start: string | null, end: string | null) {
  if (start && end) return `${hhmm(start)} ~ ${hhmm(end)}`;
  if (start) return `${hhmm(start)} ~`;
  if (end) return `~ ${hhmm(end)}`;
  return "";
}

export const UNMAPPED_CLASS = "반 정보를 확인할 수 없어요. 다시 불러와주세요.";

/** 그 반 · 그 날의 일과. 서버가 종이의 행 순서(position · 시작 시간)로 준다. */
export async function listRoutines(classId: string, date: string): Promise<Routine[]> {
  const id = classServerId(classId);
  if (id === null) throw new Error(UNMAPPED_CLASS);
  const params = new URLSearchParams({ class_id: String(id), from: date, to: date });
  const { items } = await apiRequest<{ items: ApiRoutine[] }>("/api/routines?" + params);
  return items.map((r) => ({
    id: routineLocalId(r.id),
    date: r.date,
    time: timeRange(r.start, r.end),
    name: r.name,
    execution: r.execution.trim(),
  }));
}
