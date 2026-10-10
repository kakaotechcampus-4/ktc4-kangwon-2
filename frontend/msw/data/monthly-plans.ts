import { read, commit, type MockAuditEvent, type MockPlanAudit } from "./store";
import { MOCK_USER_ID } from "./template-profiles";
import type {
  AnnualPlan,
  ApiClass,
  MonthlyAuditEvent,
  MonthlyCell,
  MonthlyPlan,
  MonthlyPlanSummary,
  ReadyProfile,
} from "../../lib/api/types";

/**
 * 월간계획안 목업 (docs/api-spec.md §9-1 · §9-3). 양식 설정은 template-profiles.ts 다.
 *
 * 칸 값은 개발용 고정 문장이다 — LLM 을 부르지 않는다. 서버처럼 주 개수는 달력이 정하고
 * (4 · 5 · 6주), 안전교육은 근거가 없어 비워 둔 「근거 필요」 칸이다.
 */
const RULE = { rule_id: "mock.monthly", rule_version: "mock-v1" };
/** 칸 재생성 결과의 생성 방식. 서버처럼 처음 생성과 다른 rule_version 이다. */
const CELL_RULE = { rule_id: "mock.monthly.cell", rule_version: "mock-cell-v1" };
/** 서버 Core 의 생성 행위자(generate_monthly_plan.SYSTEM_ACTOR). */
const SYSTEM_ACTOR = "monthly_application";
/** 서버는 `user_{users.id}` 다. 목업 계정 id 는 하나다. */
const MOCK_ACTOR = "user_" + MOCK_USER_ID;
const event = (
  type: MockAuditEvent["type"],
  occurred_at: string,
  more: Partial<MockAuditEvent> = {},
): MockAuditEvent => ({
  type,
  occurred_at,
  actor: MOCK_ACTOR,
  system_actor: null,
  value_change: null,
  generation_change: null,
  ...more,
});
/**
 * 이 계획안 이력의 다음 시각. 목업 시계는 ms 단위라 같은 ms 에 두 변경이 오면 순서가 뒤집힐 수
 * 있다 — 앞 이벤트보다 1ms 이상 뒤로 둔다(서버 Core 도 이력은 시간순이어야 한다).
 */
function nextStamp(audit: MockPlanAudit): string {
  const all = [audit.plan, ...Object.values(audit.cells)].flat();
  const last = Math.max(0, ...all.map((e) => Date.parse(e.occurred_at)));
  return new Date(Math.max(Date.now(), last + 1)).toISOString();
}
/** Core 가 다시 만들 수 있다고 하는 Section (§9-3). 나머지는 422 `["item_id"]`. */
export const REGENERATABLE = ["focus", "outdoor_play", "basic_habit", "goals"];
/** 평일만 센다. 월요일마다 새 주다 — 개수를 정하지 않는다. */
function weeksOf(targetMonth: string): MonthlyPlan["weeks"] {
  const [year, month] = targetMonth.split("-").map(Number);
  const last = new Date(Date.UTC(year, month, 0)).getUTCDate();
  const spans: { start: number; end: number }[] = [];
  for (let day = 1; day <= last; day++) {
    const weekday = new Date(Date.UTC(year, month - 1, day)).getUTCDay();
    if (weekday === 0 || weekday === 6) continue;
    if (!spans.length || weekday === 1) spans.push({ start: day, end: day });
    else spans[spans.length - 1].end = day;
  }
  const date = (day: number) => targetMonth + "-" + String(day).padStart(2, "0");
  return spans.map((s, i) => ({
    week_id: targetMonth + "-W" + (i + 1),
    label: i + 1 + "주",
    start_date: date(s.start),
    end_date: date(s.end),
    active: true,
  }));
}

const cellValue = (key: string, theme: string, week: number) =>
  ({
    theme,
    focus: theme + " — " + week + "주 놀이",
    outdoor_play: week + "주 바깥 놀이",
    goals: theme + "을(를) 즐겁게 탐색한다",
    basic_habit: week + "주 기본생활 습관",
  })[key] ?? "";

/** 연간은 반당 하나다 (§4). 부모를 요청으로 받지 않고 반으로 찾는다. */
export const annualFor = (classId: number) => read().plans.find((p) => p.class_id === classId);
export const findMonthly = (id: number) => read().monthlyPlans.find((p) => p.id === id);
export const findMonthlyFor = (classId: number, targetMonth: string) =>
  read().monthlyPlans.find((p) => p.class_id === classId && p.target_month === targetMonth);
export const listMonthly = (classIds: number[]): MonthlyPlanSummary[] =>
  read()
    .monthlyPlans.filter((p) => classIds.includes(p.class_id))
    .sort((a, b) => a.target_month.localeCompare(b.target_month) || a.id - b.id)
    .map((p) => ({
      id: p.id,
      class_id: p.class_id,
      school_year: p.school_year,
      month: p.month,
      target_month: p.target_month,
      status: p.status,
      revision: p.revision,
      profile_ref: p.profile_ref,
      created_at: p.created_at,
      confirmed_at: p.confirmed_at,
    }));

/** 3~12월은 그 학년도, 1~2월은 다음 해다. */
export const targetMonthOf = (schoolYear: number, month: number) =>
  (month >= 3 ? schoolYear : schoolYear + 1) + "-" + String(month).padStart(2, "0");

/** 칸 모양은 고른 READY Profile 이 정한다(서버의 TemplateSnapshot 과 같은 뜻). */
export const addMonthly = (
  klass: ApiClass,
  annual: AnnualPlan,
  month: number,
  profile: ReadyProfile,
) =>
  commit((db) => {
    const id = db.next++,
      at = new Date().toISOString(),
      targetMonth = targetMonthOf(klass.school_year, month),
      weeks = weeksOf(targetMonth),
      theme = annual.months.find((m) => m.month === month)?.theme ?? null;
    const parentEvidence = {
      source_type: "PARENT_PLAN",
      source_id: "annual_" + annual.id,
      source_version: null,
      effective_date: null,
      display_name: null,
    };
    const cell = (key: string, week: number | null): MonthlyCell => {
      const value = cellValue(key, theme ?? "", week ?? 0);
      return {
        item_id: "item_" + id + "_" + key + (week === null ? "" : "_w" + week),
        week_id: week === null ? null : weeks[week - 1].week_id,
        value,
        state: value ? "FILLED" : "EMPTY_UNRESOLVED",
        evidence: value ? [parentEvidence] : [],
        generation: { method: key === "theme" || !value ? "RULE_ONLY" : "RULE_LLM", ...RULE },
      };
    };
    const plan: MonthlyPlan = {
      id,
      class_id: klass.id,
      school_year: klass.school_year,
      month,
      target_month: targetMonth,
      status: "DRAFT",
      revision: 1,
      generation_mode: "LLM_PLANNER",
      profile_ref: profile.profile_ref,
      base_template_ref: profile.base_template_ref,
      parent: { annual_plan_id: annual.id, theme, confirmed_at: new Date().toISOString() },
      weeks,
      sections: profile.sections.map((s, order) => ({
        ...s,
        role: s.repeat_by === null ? "AXIS" : "CONTENT",
        order,
        semantic_variant: s.section_key === "focus" ? "SUBTHEME" : null,
        cells:
          s.repeat_by === "NONE"
            ? [cell(s.section_key, null)]
            : s.repeat_by === "WEEK"
              ? weeks.map((_, i) => cell(s.section_key, i + 1))
              : [],
      })),
      constraints: [
        {
          code: "STATUTORY_SAFETY_EDUCATION",
          verification: "NOT_VERIFIED_SOURCE_REQUIRED",
          affected_section_keys: ["safety_education"],
          required_source_kinds: ["SAFETY_RULE"],
          rule_version: RULE.rule_version,
          detail: "개발용 목업 — 안전교육 근거가 없어 비워 두었습니다.",
        },
      ],
      verification: { executed_rules: [RULE], findings: [] },
      created_at: at,
      confirmed_at: null,
    };
    db.monthlyPlans.push(plan);
    // 서버 Core 처럼 계획안 단위 CREATED 하나와 칸마다 CREATED 하나. 모두 같은 시각이다.
    const created = () => event("CREATED", at, { actor: null, system_actor: SYSTEM_ACTOR });
    db.monthlyAudit[id] = {
      plan: [created()],
      cells: Object.fromEntries(
        plan.sections.flatMap((s) => s.cells).map((c) => [c.item_id, [created()]]),
      ),
    };
    return plan;
  });

/**
 * 칸을 찾아 바꾸고 revision 을 올리고, **같은 commit 에서** 그 칸 이력에 하나를 더한다.
 * 다른 칸은 손대지 않는다. 성공한 변경만 여기 온다 — 거절 · 실패는 handler 가 먼저 돌려보낸다.
 */
const changeCell = (
  id: number,
  itemId: string,
  type: "TEACHER_EDITED" | "REGENERATED",
  change: (cell: MonthlyCell) => void,
) =>
  commit((db) => {
    const plan = db.monthlyPlans.find((p) => p.id === id)!;
    const cell = plan.sections.flatMap((s) => s.cells).find((c) => c.item_id === itemId)!;
    const before = { value: cell.value, generation: { ...cell.generation } };
    change(cell);
    plan.revision += 1;
    const audit = (db.monthlyAudit[id] ??= { plan: [], cells: {} });
    (audit.cells[itemId] ??= []).push(
      event(type, nextStamp(audit), {
        value_change: { before: before.value, after: cell.value },
        generation_change:
          type === "REGENERATED"
            ? { before: before.generation, after: { ...cell.generation } }
            : null,
      }),
    );
    return plan;
  });
export const findCell = (plan: MonthlyPlan, itemId: string) => {
  const section = plan.sections.find((s) => s.cells.some((c) => c.item_id === itemId));
  return section && { section, cell: section.cells.find((c) => c.item_id === itemId)! };
};
/** 근거 · 생성 방식은 그대로다 — 교사 수정은 변경 이력(TEACHER_EDITED)에만 남는다. */
export const editCell = (id: number, itemId: string, value: string, sectionKey: string) =>
  changeCell(id, itemId, "TEACHER_EDITED", (cell) => {
    cell.value = value;
    cell.state = value
      ? "FILLED"
      : sectionKey === "safety_education"
        ? "EMPTY_UNRESOLVED"
        : "EMPTY_VALID";
  });
/** 다음 revision 을 값에 넣어 매번 다른 결정적 문장을 만든다. */
export const regenerateCell = (id: number, itemId: string, label: string, nextRevision: number) =>
  changeCell(id, itemId, "REGENERATED", (cell) => {
    cell.value = "다시 만든 " + label + " (" + nextRevision + "판)";
    cell.state = "FILLED";
    cell.generation = { method: "RULE_LLM", ...CELL_RULE };
  });
export const confirmMonthly = (id: number) =>
  commit((db) => {
    const plan = db.monthlyPlans.find((p) => p.id === id)!;
    const audit = (db.monthlyAudit[id] ??= { plan: [], cells: {} });
    const at = nextStamp(audit);
    plan.status = "CONFIRMED";
    plan.revision += 1;
    // 서버처럼 confirmed_at 은 CONFIRMED 이벤트의 시각이다. 재호출은 handler 가 여기 오기 전에 막는다.
    plan.confirmed_at = at;
    audit.plan.push(event("CONFIRMED", at));
    return plan;
  });

/**
 * 변경 이력 조회 (§9-5). **읽기만 한다** — 저장소 사본(read)을 정렬하고 원본은 건드리지 않는다.
 * 순서: 시각 → 계획안 먼저 → 칸은 계획안 안의 순서 → 한 칸 안에서는 저장된 순서.
 * `itemId` 를 주면 그 칸 이력과 계획안 CONFIRMED 만. 없는 칸이면 null(→ 404).
 */
export function listAudit(plan: MonthlyPlan, itemId: string | null): MonthlyAuditEvent[] | null {
  const audit = read().monthlyAudit[plan.id] ?? { plan: [], cells: {} };
  let located = plan.sections.flatMap((section) =>
    section.cells.map((cell) => ({ section, cell })),
  );
  if (itemId !== null) {
    located = located.filter(({ cell }) => cell.item_id === itemId);
    if (!located.length) return null;
  }
  const at = (e: MockAuditEvent) => Date.parse(e.occurred_at);
  const keyed: { key: number[]; out: MonthlyAuditEvent }[] = [
    ...audit.plan
      .filter((e) => itemId === null || e.type === "CONFIRMED")
      .map((e, i) => ({
        key: [at(e), 0, 0, i],
        out: { ...placed(e), scope: "PLAN" as const },
      })),
    ...located.flatMap(({ section, cell }, position) =>
      (audit.cells[cell.item_id] ?? []).map((e, i) => ({
        key: [at(e), 1, position, i],
        out: {
          ...placed(e),
          scope: "CELL" as const,
          item_id: cell.item_id,
          section_key: section.section_key,
          week_id: cell.week_id,
        },
      })),
    ),
  ];
  keyed.sort((a, b) => {
    const i = a.key.findIndex((v, j) => v !== b.key[j]);
    return i === -1 ? 0 : a.key[i] - b.key[i];
  });
  return keyed.map(({ out }) => out);
}
/** 서버 응답과 같은 키 순서 · 같은 null. */
const placed = (e: MockAuditEvent): MonthlyAuditEvent => ({
  type: e.type,
  occurred_at: e.occurred_at,
  scope: "PLAN",
  item_id: null,
  section_key: null,
  week_id: null,
  actor: e.actor,
  system_actor: e.system_actor,
  value_change: e.value_change,
  generation_change: e.generation_change,
});
