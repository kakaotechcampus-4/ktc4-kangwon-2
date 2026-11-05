import { read, commit } from "./store";
import type { ApiClass, ClassInput, ClassUpdate } from "../../lib/api/types";

/**
 * 학년도는 서버가 정한다 — 3월 시작이다 (docs/api-spec.md §2).
 *
 * **먼저 KST 로 옮기고 나서 3월 경계를 본다.** `getMonth()` 는 기기 시간대 기준이라
 * 브라우저가 UTC 면 KST 3월 1일 새벽에 만든 반이 전년도로 들어간다. 서버
 * (`app/shared/school_year.py`)가 같은 이유로 KST 로 변환하므로 목업도 맞춘다 —
 * 다르면 목업을 끌 때 화면의 학년도가 바뀐다.
 */
const KST_OFFSET_MINUTES = 9 * 60;

function schoolYearOf(now: Date) {
  const kst = new Date(now.getTime() + (KST_OFFSET_MINUTES + now.getTimezoneOffset()) * 60000);
  return kst.getMonth() + 1 >= 3 ? kst.getFullYear() : kst.getFullYear() - 1;
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
      my_access: "OWNER",
    };
    db.classes.push(c);
    return c;
  });
// 같은 원 · 같은 학년도에 같은 이름이 있나 (자기 자신은 뺀다).
export const classNameTaken = (centerId: number, name: string, exceptId?: number) =>
  read().classes.some(
    (c) =>
      c.center_id === centerId &&
      c.school_year === schoolYearOf(new Date()) &&
      c.name === name &&
      c.id !== exceptId,
  );
export const patchClass = (id: number, patch: ClassUpdate): ApiClass =>
  commit((db) => {
    const c = db.classes.find((x) => x.id === id) as ApiClass;
    // null 은 「안 보냄」이다(api-spec §2 반 수정) — 지우지 않고 그대로 둔다.
    if (patch.name != null) c.name = patch.name;
    if (patch.teacher_name != null) c.teacher_name = patch.teacher_name;
    if (patch.age_min != null) c.age_min = patch.age_min;
    if (patch.age_max != null) c.age_max = patch.age_max;
    // 이미 있는 시각은 그대로 둔다. 체크박스 복원용이다.
    if (patch.consent_confirmed === true && !c.consent_confirmed_at)
      c.consent_confirmed_at = new Date().toISOString();
    if (patch.consent_confirmed === false) c.consent_confirmed_at = null;
    return c;
  });
