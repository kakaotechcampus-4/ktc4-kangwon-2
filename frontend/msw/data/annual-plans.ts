import { read, commit, type MockAnnualPlan } from "./store";
import type {
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
export const months = (): AnnualMonth[] =>
  [3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 1, 2].map((month, i) => ({
    month,
    theme: themes[i],
    // 서버처럼 생성 때는 항상 비어 있다 — 교사가 §6 으로 채운다.
    sub_themes: [],
    safety_education: [],
    safety_education_state: "SOURCE_REQUIRED",
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
    const plan: MockAnnualPlan = {
      id: db.next++,
      class_id: input.class_id,
      school_year: schoolYear,
      status: "DRAFT",
      months: months(),
      checked_rules: ["legal_hours"],
      checks: checks(),
      created_at: new Date().toISOString(),
      confirmed_at: null,
    };
    db.plans.push(plan);
    return detail(plan);
  });
/** 그 달 전체 교체. 교사가 고쳐도 `evidence` · `generation` 은 그대로다 (§6). */
export const putMonth = (id: number, month: number, input: MonthInput) =>
  commit((db) => {
    const plan = db.plans.find((p) => p.id === id)!;
    const m = plan.months.find((m) => m.month === month)!;
    m.theme = input.theme;
    m.sub_themes = input.sub_themes;
    return m;
  });
/** 재호출은 멱등이다 — 이미 확정이면 아무것도 바꾸지 않고 최초 확정 시각을 돌려준다 (§7). */
export const confirmPlan = (id: number): ConfirmResult =>
  commit((db) => {
    const plan = db.plans.find((p) => p.id === id)!;
    if (plan.status !== "CONFIRMED") {
      plan.status = "CONFIRMED";
      plan.confirmed_at = new Date().toISOString();
    }
    return { id, status: "CONFIRMED", confirmed_at: plan.confirmed_at! };
  });
