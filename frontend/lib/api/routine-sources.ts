/** S-J2 표시 변환. 공통 CRUD의 숫자 ID와 화면의 routine: ID를 분리한다. */
import { classServerId } from "./onboarding";
import { listRoutinesOfDay, routineLocalId, routineTime } from "./routines";
export { routineLocalId, routineServerId } from "./routines";

export interface RoutineSource {
  id: string;
  date: string;
  time: string;
  name: string;
  execution: string;
}

export const UNMAPPED_CLASS = "반 정보를 확인할 수 없어요. 다시 불러와주세요.";

export async function listRoutineSources(classId: string, date: string): Promise<RoutineSource[]> {
  const id = classServerId(classId);
  if (id === null) throw new Error(UNMAPPED_CLASS);
  const items = await listRoutinesOfDay(id, date);
  return items.map((r) => ({
    id: routineLocalId(r.id),
    date: r.date,
    name: r.name,
    time: r.start || r.end ? `${routineTime(r.start)} ~ ${routineTime(r.end)}`.trim() : "",
    execution: r.execution.trim(),
  }));
}
