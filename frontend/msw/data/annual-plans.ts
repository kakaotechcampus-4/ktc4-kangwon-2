import { read, commit, type Database, type MockAnnualPlan } from "./store";
import { MOCK_USER_ID } from "./template-profiles";
import type {
  AnnualAuditEvent,
  AnnualInput,
  AnnualMonth,
  MonthInput,
  AnnualPlan,
  AnnualPlanSummary,
  ConfirmResult,
} from "../../lib/api/types";

/**
 * 연간계획안 목업 (docs/api-spec.md §4 ~ §7). 모양은 서버 응답과 같다.
 *
 * 주제 문구 · 근거 id · rule 은 개발용 고정값이다 — LLM 을 부르지 않고, 실제 Theme Reference
 * id · catalog 판을 흉내내지 않는다(목업 id 가 진짜 근거처럼 보이면 안 된다).
 */
const themes = [
  "새로운 우리 반",
  "봄을 찾아요",
  "나와 가족",
  "우리 동네",
  "여름 놀이",
  "건강한 여름",
  "함께하는 우리",
  "가을 자연",
  "생활 속 발견",
  "겨울과 나눔",
  "함께 자라요",
  "즐거웠던 우리 반",
];
/** 표시 이름·id만 모사한다. 법령 수치나 통과 판정을 FE에 복제하지 않는다. */
export const safetyCategories = [
  { category_id: "sexual_violence_prevention", label: "성폭력 예방 교육" },
  { category_id: "child_abuse_prevention", label: "아동학대 예방 교육" },
  { category_id: "missing_and_abduction_prevention", label: "실종·유괴의 예방·방지 교육" },
  {
    category_id: "infectious_disease_and_drug_misuse_prevention",
    label: "감염병 및 약물의 오용·남용 예방 등 보건위생관리 교육",
  },
  { category_id: "disaster_preparedness_safety", label: "재난대비 안전 교육" },
  { category_id: "traffic_safety", label: "교통안전 교육" },
];
export const months = (): AnnualMonth[] =>
  [3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 1, 2].map((month, i) => ({
    month,
    theme: themes[i],
    sub_themes: [`${themes[i]} 알아보기`, `${themes[i]} 함께 놀이하기`],
    safety_education: [],
    safety_education_state: "SOURCE_REQUIRED",
    safety_education_source: null,
    safety_education_generation: null,
    evidence: [
      {
        source_type: "THEME_REFERENCE",
        source_id: "mock_theme_" + month,
        source_version: "mock-theme-reference-v0",
        effective_date: null,
        display_name: themes[i],
      },
    ],
    generation: { method: "RULE_LLM", rule_id: "mock.yearly.theme", rule_version: "mock-v1" },
  }));
/** 서버 Core 의 생성 행위자(generate_yearly_plan). */
const SYSTEM_ACTOR = "yearly_application";
/** 서버는 `user_{users.id}` 다. 목업 계정 id 는 하나다. */
const MOCK_ACTOR = "user_" + MOCK_USER_ID;
const event = (
  type: AnnualAuditEvent["type"],
  occurred_at: string,
  more: Partial<AnnualAuditEvent> = {},
): AnnualAuditEvent => ({
  type,
  occurred_at,
  month: null,
  actor: MOCK_ACTOR,
  system_actor: null,
  value_change: null,
  ...more,
});
/** 이벤트 시각은 앞선 것보다 뒤다 — 같은 밀리초에 두 번 불러도 순서가 뒤집히지 않게. */
function stamp(db: Database, id: number): string {
  const last = Math.max(0, ...(db.annualAudit[id] ?? []).map((e) => Date.parse(e.occurred_at)));
  return new Date(Math.max(Date.now(), last + 1)).toISOString();
}
const record = (db: Database, id: number, ...events: AnnualAuditEvent[]) =>
  (db.annualAudit[id] ??= []).push(...events);
/**
 * 서버 검사기처럼 법정 6구분마다 「주기」 · 「시수」 UNVERIFIED 를 하나씩 낸다(P0 는 배치 입력이 없다).
 * 구분 이름 · 법정 주기 · 시수는 적지 않는다 — 법령 값의 원본은 서버 쪽 하나다.
 */
const checks = (): AnnualPlan["checks"] =>
  [1, 2, 3, 4, 5, 6].flatMap((n) =>
    ["주기", "연간 시수"].map((what) => ({
      rule: "legal_hours",
      severity: "UNVERIFIED",
      detail: `법정 안전교육 ${n} — 배치 계획이 없어 ${what}를 확인할 수 없습니다 (목업)`,
      month: null,
    })),
  );
/** 응답에는 시각을 담지 않는다 — 목록 요약 · 확정 응답만 준다(§4 · §5). */
const detail = (p: MockAnnualPlan): AnnualPlan => ({
  id: p.id,
  class_id: p.class_id,
  school_year: p.school_year,
  status: p.status,
  months: p.months,
  safety_categories: safetyCategories,
  checked_rules: p.checked_rules,
  checks: p.checks,
});
export const findPlan = (id: number) => {
  const plan = read().plans.find((p) => p.id === id);
  return plan && detail(plan);
};
/** 서버처럼 최근 생성 순이다. */
export const listPlans = (classId?: number): AnnualPlanSummary[] =>
  read()
    .plans.filter((p) => classId === undefined || p.class_id === classId)
    .sort((a, b) => b.created_at.localeCompare(a.created_at) || b.id - a.id)
    .map((p) => ({
      id: p.id,
      class_id: p.class_id,
      school_year: p.school_year,
      status: p.status,
      created_at: p.created_at,
      confirmed_at: p.confirmed_at,
    }));

/** 학년도는 요청이 아니라 반이 정한다 (§4). */
export const addPlan = (input: AnnualInput, schoolYear: number) =>
  commit((db) => {
    const id = db.next++,
      at = stamp(db, id);
    const plan: MockAnnualPlan = {
      id,
      class_id: input.class_id,
      school_year: schoolYear,
      status: "DRAFT",
      months: months(),
      checked_rules: ["legal_hours"],
      checks: checks(),
      created_at: at,
      confirmed_at: null,
    };
    db.plans.push(plan);
    // 서버처럼 계획안 1건 + 달마다 1건, 같은 시각 · 시스템 행위자.
    const created = { actor: null, system_actor: SYSTEM_ACTOR };
    record(
      db,
      id,
      event("CREATED", at, created),
      ...plan.months.map((m) => event("CREATED", at, { ...created, month: m.month })),
    );
    return detail(plan);
  });
/** 그 달 전체 교체. 교사가 고쳐도 `evidence` · `generation` 은 그대로다 (§6). */
export const putMonth = (id: number, month: number, input: MonthInput) =>
  commit((db) => {
    const plan = db.plans.find((p) => p.id === id)!;
    const m = plan.months.find((m) => m.month === month)!;
    // 주제가 그대로여도 남는다(서버와 같다) — 그때 before · after 가 같다. 소주제는 이력에 없다.
    const value_change = { before: m.theme, after: input.theme };
    record(db, id, event("TEACHER_EDITED", stamp(db, id), { month, value_change }));
    m.theme = input.theme;
    m.sub_themes = input.sub_themes;
    if (input.safety_education !== undefined) {
      m.safety_education = input.safety_education ?? [];
      m.safety_education_source = input.safety_education === null ? null : "TEACHER_INPUT";
      m.safety_education_generation =
        input.safety_education === null
          ? null
          : { method: "MANUAL", rule_id: null, rule_version: null };
      m.safety_education_state =
        input.safety_education === null
          ? "SOURCE_REQUIRED"
          : input.safety_education.length
            ? "PLACED"
            : "NOT_PLACED";
    }
    return m;
  });
/** 재호출은 멱등이다 — 이미 확정이면 아무것도 바꾸지 않고 최초 확정 시각을 돌려준다 (§7). */
export const confirmPlan = (id: number): ConfirmResult =>
  commit((db) => {
    const plan = db.plans.find((p) => p.id === id)!;
    if (plan.status !== "CONFIRMED") {
      // 서버처럼 confirmed_at 은 CONFIRMED 이벤트의 시각이다. 재호출은 이벤트를 더하지 않는다.
      const at = stamp(db, id);
      plan.status = "CONFIRMED";
      plan.confirmed_at = at;
      record(db, id, event("CONFIRMED", at));
    }
    return { id, status: "CONFIRMED", confirmed_at: plan.confirmed_at! };
  });
/**
 * 저장 순서가 곧 서버 정렬이다 — 시각은 계속 늘어나고(stamp), 같은 시각인 생성 이벤트는 계획안 →
 * 3월 ~ 익년 2월 순서로 넣는다. 이 변경 전에 만든 옛 목업 계획안은 이력이 없어 빈 목록이다(지어내지 않는다).
 */
/** 이 키가 생기기 전에 저장된 목업 이력에는 `value_change` 가 없다 — 서버처럼 null 로 준다. */
export const listAnnualAudit = (id: number): AnnualAuditEvent[] =>
  (read().annualAudit[id] ?? []).map((e) => ({ ...e, value_change: e.value_change ?? null }));
