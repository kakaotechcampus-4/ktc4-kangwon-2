import { read, commit, type Database } from "./store";
import type {
  MonthlyTemplate,
  ProfilePointer,
  ProfilePointerInput,
  ProfileRef,
  ProfileResolution,
  ReadyProfile,
  TemplateProfileInput,
  TemplateRef,
} from "../../lib/api/types";

/**
 * 월간 양식 설정 목업 (docs/api-spec.md §9-2 · §9-4). 월간 생성 목업과 **같은 저장소**를 쓴다.
 *
 * 기반 Template 은 서버처럼 v0.1.1 · v0.2.1 둘이고 **둘 다 승인 대기**다. 승인된 경로는
 * `approveTemplateForTest` 로만 연다(서버 테스트의 OD-N11 (A) 와 같은 뜻) — 화면 코드는 부르지 않는다.
 */
const TEMPLATE_ID = "ssuksak.monthly-template-a";
const TEMPLATE_VERSIONS = ["monthly-template-a-v0.1.1", "monthly-template-a-v0.2.1"];
/** 목업에는 로그인 계정 id 가 없다 — 목업 로그인 응답의 id(1)를 쓴다. */
export const MOCK_USER_ID = 1;
type Section = MonthlyTemplate["sections"][number];
const section = (
  section_key: string,
  role: Section["role"],
  repeat_by: Section["repeat_by"],
  selection: Section["selection"],
  label = section_key,
): Section => ({ section_key, label, role, repeat_by, selection });
/** Template A 데이터 순서 그대로. label 은 데이터 값(칸 이름)이다. */
const SECTIONS: Section[] = [
  section("theme", "CONTENT", "NONE", "REQUIRED"),
  section("week_axis", "AXIS", null, "REQUIRED"),
  section("outdoor_play", "CONTENT", "WEEK", "REQUIRED"),
  section("safety_education", "CONTENT", "WEEK", "REQUIRED"),
  section("focus", "CONTENT", "WEEK", "OPTIONAL"),
  section("goals", "CONTENT", "NONE", "OPTIONAL"),
  section("basic_habit", "CONTENT", "WEEK", "OPTIONAL", "habits"),
  section("emergency_response", "CONTENT", null, "NOT_SUPPORTED"),
  section("drill", "CONTENT", null, "INSTITUTION_INPUT"),
  section("indoor_alternative", "CONTENT", null, "NOT_SUPPORTED"),
  section("special_program", "CONTENT", null, "NOT_SUPPORTED"),
  section("event_schedule", "CONTENT", null, "INSTITUTION_INPUT"),
];
const REQUIRED = SECTIONS.filter((s) => s.selection === "REQUIRED").map((s) => s.section_key);
const SELECTABLE = SECTIONS.filter((s) => s.selection === "OPTIONAL").map((s) => s.section_key);
const FOCUS_VARIANTS = ["SUBTHEME", "EXPECTED_PLAY", "WEEKLY_THEME"];
const EMPTY: ProfilePointer = { profile_ref: null, changed_by: null, changed_at: null };

const templateKey = (ref: TemplateRef) => ref.template_id + "@" + ref.template_version;
const sameRef = (a: ProfileRef | null, b: ProfileRef | null) =>
  a === b ||
  (!!a && !!b && a.profile_id === b.profile_id && a.profile_version === b.profile_version);

export const listTemplates = (): MonthlyTemplate[] => {
  const approved = read().approvedTemplates;
  return TEMPLATE_VERSIONS.map((template_version) => {
    const template_ref = { template_id: TEMPLATE_ID, template_version };
    return {
      template_ref,
      approved: approved.includes(templateKey(template_ref)),
      sections: SECTIONS,
      focus_variants: FOCUS_VARIANTS,
    };
  });
};
export const findTemplate = (ref: TemplateRef) =>
  listTemplates().find((t) => templateKey(t.template_ref) === templateKey(ref));
/** **테스트 · 개발 전용 승인 Fixture.** 운영 Template 의 승인 상태가 아니다. */
export const approveTemplateForTest = (ref: TemplateRef) =>
  commit((db) => {
    if (!db.approvedTemplates.includes(templateKey(ref)))
      db.approvedTemplates.push(templateKey(ref));
  });

/**
 * 시작 요청의 입력 문제(서버 `_check_start` 와 같은 순서). 없으면 null.
 * 고를 수 없는 칸(event_schedule · drill 포함) · 표시 이름 · focus_variant 를 본다.
 */
export function startProblem(input: Required<TemplateProfileInput>): string[] | null {
  const keys = input.selected_optional_keys;
  if (new Set(keys).size !== keys.length || !keys.every((k) => SELECTABLE.includes(k)))
    return ["selected_optional_keys"];
  const chosen = [...REQUIRED, ...keys];
  for (const [key, label] of Object.entries(input.display_labels))
    if (!chosen.includes(key) || !label.trim()) return ["display_labels." + key];
  const missing = chosen.filter((k) => !(k in input.display_labels)).sort();
  if (missing.length) return missing.map((k) => "display_labels." + k);
  if (
    keys.includes("focus")
      ? !FOCUS_VARIANTS.includes(String(input.focus_variant))
      : input.focus_variant !== null
  )
    return ["focus_variant"];
  return null;
}

/** 원 소유 READY v1. 원 기본은 걸지 않는다. 요청마다 새 Profile 이다(멱등 아님). */
export const addReadyProfile = (centerId: number, input: Required<TemplateProfileInput>) =>
  commit((db) => {
    const chosen = [...REQUIRED, ...input.selected_optional_keys];
    const profile: ReadyProfile = {
      profile_ref: { profile_id: "tprofile_mock_" + db.next++, profile_version: "v1" },
      status: "READY",
      base_template_ref: input.base_template_ref,
      selected_optional_keys: [...input.selected_optional_keys],
      sections: SECTIONS.filter((s) => chosen.includes(s.section_key)).map((s) => ({
        section_key: s.section_key,
        label: input.display_labels[s.section_key] ?? null,
        repeat_by: s.repeat_by,
        visible: true,
      })),
      created_at: new Date().toISOString(),
    };
    db.profiles.push({ center_id: centerId, status: "READY", profile });
    return profile;
  });
const readyIn = (db: Database, centerId: number, ref: ProfileRef) =>
  db.profiles.find(
    (p) => p.center_id === centerId && p.status === "READY" && sameRef(p.profile.profile_ref, ref),
  )?.profile;
export const listReady = (centerId: number) =>
  read()
    .profiles.filter((p) => p.center_id === centerId && p.status === "READY")
    .map((p) => p.profile);
/** 없음 · READY 아님 · 남의 원 것을 가르지 않는다(서버와 같다). */
export const findReady = (centerId: number, ref: ProfileRef) => readyIn(read(), centerId, ref);

export const defaultPointer = (centerId: number): ProfilePointer =>
  read().defaultPointers[centerId] ?? EMPTY;
export const overridePointer = (classId: number): ProfilePointer =>
  read().overridePointers[classId] ?? EMPTY;

/**
 * 지정 · 해제 CAS (서버 `_move` 와 같은 순서: 대상 검사 → 본 값 비교).
 * 목업은 한 흐름에서 돌아 실제 DB 동시성은 보여 주지 못한다 — 그건 BE-1 PostgreSQL 테스트가 본다.
 */
export const movePointer = (
  table: "defaultPointers" | "overridePointers",
  key: number,
  centerId: number,
  { profile_ref, expected_profile_ref }: ProfilePointerInput,
) =>
  commit((db): ProfilePointer | "NOT_FOUND" | "INVALID" | "STALE" => {
    if (profile_ref && !readyIn(db, centerId, profile_ref)) return "NOT_FOUND";
    if (!profile_ref && !expected_profile_ref) return "INVALID";
    if (!sameRef(db[table][key]?.profile_ref ?? null, expected_profile_ref)) return "STALE";
    if (profile_ref)
      db[table][key] = {
        profile_ref,
        changed_by: MOCK_USER_ID,
        changed_at: new Date().toISOString(),
      };
    else delete db[table][key];
    return db[table][key] ?? EMPTY;
  });

/** R1 반 override → R2 원 기본 → 선택 필요. 대상을 못 쓰면 내려가지 않는다(R3). */
export const resolveProfile = (classId: number, centerId: number): ProfileResolution => {
  const db = read();
  const steps = [
    ["CLASSROOM_OVERRIDE", db.overridePointers[classId]],
    ["INSTITUTION_DEFAULT", db.defaultPointers[centerId]],
  ] as const;
  for (const [source, pointer] of steps) {
    if (!pointer) continue;
    if (!readyIn(db, centerId, pointer.profile_ref))
      return { source: "SELECTION_REQUIRED", profile_ref: null, reason: source + "_NOT_READY" };
    return { source, profile_ref: pointer.profile_ref, reason: null };
  }
  return { source: "SELECTION_REQUIRED", profile_ref: null, reason: "NO_POINTER" };
};
