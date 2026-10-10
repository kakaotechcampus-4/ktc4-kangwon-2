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
const SCHOOL_YEAR = [3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 1, 2];
/**
 * 그 달에 고를 수 있는 목업 주제 후보. 첫 번째가 생성 때 고른 것이다. 실제 Theme Reference 도 연령 · 달에
 * 따라 후보가 하나뿐인 달이 많다 — 그런 달은 다시 만들어도 같은 주제다. 목업은 9월만 후보가 둘이다.
 * 목업 후보는 달끼리 겹치지 않아 Core 의 「이웃 달과 같은 주제 피하기」는 일어날 수 없다.
 */
const candidates = (month: number) => [
  { id: "mock_theme_" + month, label: themes[SCHOOL_YEAR.indexOf(month)] },
  ...(month === 9 ? [{ id: "mock_theme_9_b", label: "가을 들판" }] : []),
];
const themeEvidence = (candidate: { id: string; label: string }) => [
  {
    source_type: "THEME_REFERENCE",
    source_id: candidate.id,
    source_version: "mock-theme-reference-v0",
    effective_date: null,
    display_name: candidate.label,
  },
];
export const months = (): AnnualMonth[] =>
  SCHOOL_YEAR.map((month) => {
    const chosen = candidates(month)[0];
    return {
      month,
      theme: chosen.label,
      // 서버처럼 생성 때는 항상 비어 있다 — 교사가 §6 으로 채운다.
      sub_themes: [],
      safety_education: [],
      safety_education_state: "SOURCE_REQUIRED",
      evidence: themeEvidence(chosen),
      generation: { ...GENERATION },
    };
  });
const GENERATION = { method: "RULE_LLM", rule_id: "mock.yearly.theme", rule_version: "mock-v1" };
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
  generation_change: null,
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
    // 주제가 그대로여도 남는다(서버와 같다). 소주제는 이력에 없다.
    record(
      db,
      id,
      event("TEACHER_EDITED", stamp(db, id), {
        month,
        value_change: { before: m.theme, after: input.theme },
      }),
    );
    m.theme = input.theme;
    m.sub_themes = input.sub_themes;
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
 * 그 달 주제만 다시 만든다(LLM 을 부르지 않는다). 서버 Core 와 같은 규칙으로 고른다 — 지금 주제는 뒤로
 * 미룰 뿐 빼지 않는다(soft penalty), 그다음은 id 순이다. **후보가 하나뿐이면 같은 주제가 다시 나온다**
 * — 그래도 200 이고 REGENERATED 가 남는다(값이 같아도). 문구는 후보 이름이다(서버의 결정적 생성기와
 * 같다. 실제 LLM 은 같은 주제라도 문구를 바꿔 쓸 수 있다). 근거는 고른 후보로 다시 만들고, 생성
 * 방식은 처음과 같은 목업 rule 이다. 다른 달은 그대로. 확정 · 소주제 · 옛 목업 데이터 검사는 handler 가 먼저 한다.
 */
export const regenerateMonth = (id: number, month: number) =>
  commit((db) => {
    const plan = db.plans.find((p) => p.id === id)!;
    const m = plan.months.find((m) => m.month === month)!;
    const current = m.evidence[0]?.source_id;
    const [chosen] = candidates(month).sort(
      (a, b) => Number(a.id === current) - Number(b.id === current) || a.id.localeCompare(b.id),
    );
    record(
      db,
      id,
      event("REGENERATED", stamp(db, id), {
        month,
        value_change: { before: m.theme, after: chosen.label },
        generation_change: { before: m.generation, after: { ...GENERATION } },
      }),
    );
    m.theme = chosen.label;
    m.evidence = themeEvidence(chosen);
    m.generation = { ...GENERATION };
    return m;
  });
/**
 * 저장 순서가 곧 서버 정렬이다 — 시각은 계속 늘어나고(stamp), 같은 시각인 생성 이벤트는 계획안 →
 * 3월 ~ 익년 2월 순서로 넣는다. 이 변경 전에 만든 옛 목업 계획안은 이력이 없어 빈 목록이다(지어내지 않는다).
 */
export const listAnnualAudit = (id: number): AnnualAuditEvent[] => read().annualAudit[id] ?? [];
