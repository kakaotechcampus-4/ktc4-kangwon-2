import { read, commit } from "./store";
import type { ApiClass, ClassInput } from "../../lib/api/types";

/** 학년도는 서버가 정한다 — 3월 시작이다 (docs/api-spec.md §2). */
function schoolYearOf(now: Date) {
  return now.getMonth() + 1 >= 3 ? now.getFullYear() : now.getFullYear() - 1;
}

export const findClass = (id: number) => read().classes.find((c) => c.id === id);
export const listClasses = (id: number) => read().classes.filter((c) => c.center_id === id);
export const addClass = (id: number, data: ClassInput): ApiClass =>
  commit((db) => {
    const now = new Date();
    const c: ApiClass = {
      id: db.next++,
      center_id: id,
      name: data.name,
      school_year: schoolYearOf(now),
      age_min: data.age_min,
      age_max: data.age_max,
      child_count: data.child_count ?? null,
      teacher_name: data.teacher_name,
      consent_confirmed_at: data.consent_confirmed ? now.toISOString() : null,
      created_at: now.toISOString(),
    };
    db.classes.push(c);
    return c;
  });
