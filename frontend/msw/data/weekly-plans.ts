import { read, commit } from "./store";
import type {
  ApiClass,
  MonthlyPlan,
  WeeklyCell,
  WeeklyPlan,
  WeeklyPlanSummary,
} from "../../lib/api/types";

/**
 * 주간계획안 목업 (docs/weekly-plan-contract.md §13).
 *
 * 월간 목업과 다른 점 넷 — 주차 열이 없고(Section 마다 칸 하나), 교사 입력 칸 셋은
 * 값을 만들지 않으며(`generation: null`), 토요일 설정이 `operating_days` 로 굳고,
 * 근거로 쓴 부모 월간 칸의 그때 값을 `parent_snapshots` 로 들고 온다.
 *
 * 칸 값은 개발용 고정 문장이다 — LLM 을 부르지 않는다.
 */
const RULE = { rule_id: "mock.weekly", rule_version: "mock-v1" };
const CELL_RULE = { rule_id: "mock.weekly.cell", rule_version: "mock-cell-v1" };
const TEMPLATE_REF = {
  template_id: "ssuksak.weekly-template-a",
  template_version: "weekly-template-a-v0.1.0",
};

/** §6-2 의 Section 차례 그대로. P0 는 켜고 끄는 기능이 없어 전부 항상 켜져 있다. */
const SECTIONS = [
  "theme",
  "focus",
  "goals",
  "basic_habit",
  "safety_education",
  "indoor_play",
  "group_activity",
  "outdoor_play",
  "indoor_alternative",
  "family_link",
  "event_schedule",
  "special_program",
] as const;

/** 교사가 적는 칸. 연간 · 월간에 없는 기관 운영 정보라 만들면 없는 사실이 된다 (§6-2). */
export const TEACHER_INPUT: readonly string[] = [
  "family_link",
  "event_schedule",
  "special_program",
];
/** 안전교육은 근거(SAFETY_RULE)가 없어 비워 둔다 — 월간 목업과 같은 이유다. */
const UNRESOLVED: readonly string[] = ["safety_education"];
/** 다시 만들 수 있는 칸. 교사 입력 칸과 빈 칸은 뺀다 (§9-3 과 같은 모양). */
export const REGENERATABLE = SECTIONS.filter(
  (k) => !TEACHER_INPUT.includes(k) && !UNRESOLVED.includes(k),
) as readonly string[];

const cellValue = (key: string, theme: string, label: string) =>
  ({
    theme,
    focus: theme + " — " + label + " 놀이",
    goals: theme + "을(를) 친구와 함께 즐긴다",
    basic_habit: label + " 기본생활 습관",
    indoor_play: "쌓기 · 역할 · 미술 영역 " + label + " 놀이",
    group_activity: "월: 이야기나누기 / 수: 음률 / 금: 동극",
    outdoor_play: label + " 바깥 놀이 — 모래놀이터",
    indoor_alternative: "비 오는 날: 유희실 신체놀이",
  })[key] ?? "";

export const findWeekly = (id: number) => read().weeklyPlans.find((p) => p.id === id);
export const findWeeklyFor = (classId: number, weekId: string) =>
  read().weeklyPlans.find((p) => p.class_id === classId && p.week_id === weekId);

/** 그 달 주간계획안들. `targetMonth` 는 `YYYY-MM` — `week_id` 앞자리가 그 달이다 (§3-1). */
export const listWeekly = (classIds: number[], targetMonth: string): WeeklyPlanSummary[] =>
  read()
    .weeklyPlans.filter(
      (p) => classIds.includes(p.class_id) && p.week_id.startsWith(targetMonth + "-W"),
    )
    .sort((a, b) => a.week_id.localeCompare(b.week_id) || a.id - b.id)
    .map((p) => ({
      id: p.id,
      class_id: p.class_id,
      school_year: p.school_year,
      week_id: p.week_id,
      target_month: p.target_month,
      status: p.status,
      revision: p.revision,
      created_at: p.created_at,
      confirmed_at: p.confirmed_at,
    }));

/**
 * 한 주를 만든다. 주 주소 · 기간은 **부모 월간이 준 것을 그대로** 쓴다 — 주간이 주차를
 * 다시 세지 않는다 (§3-1). 토요일을 켜면 표시 기간이 하루 늘어난다 (§3-2).
 */
export const addWeekly = (
  klass: ApiClass,
  monthly: MonthlyPlan,
  weekId: string,
  saturday: boolean,
) =>
  commit((db) => {
    const id = db.next++;
    const at = new Date().toISOString();
    const week = monthly.weeks.find((w) => w.week_id === weekId)!;
    const theme = monthly.parent.theme ?? "";
    const parentEvidence = {
      source_type: "PARENT_PLAN",
      source_id: "monthly_" + monthly.id,
      source_version: null,
      effective_date: null,
      display_name: null,
    };
    /** 부모 월간의 같은 칸. 그때 값을 스냅샷으로 남긴다 (§5-3). */
    const parentSnapshot = (key: string) => {
      const cells = monthly.sections.find((s) => s.section_key === key)?.cells ?? [];
      const parent = cells.find((c) => c.week_id === weekId) ?? cells[0];
      return parent && parent.value
        ? [{ parent_item_id: parent.item_id, snapshot_value: parent.value }]
        : [];
    };
    const cell = (key: string): WeeklyCell => {
      const teacher = TEACHER_INPUT.includes(key);
      const value = teacher ? "" : cellValue(key, theme, week.label);
      return {
        item_id: "item_" + id + "_" + key,
        value,
        state: value ? "FILLED" : teacher ? "EMPTY_VALID" : "EMPTY_UNRESOLVED",
        evidence: value ? [parentEvidence] : [],
        // 교사 입력 칸은 처음 쓰기 전까지 만든 것이 없다 (§10-2).
        generation: teacher ? null : { method: value ? "RULE_LLM" : "RULE_ONLY", ...RULE },
        parent_snapshots: teacher ? [] : parentSnapshot(key),
      };
    };
    // 토요일은 WeekPeriod 가 아니라 주간계획안이 가진다 (§3-2). 표시 기간만 하루 늘어난다.
    const end = new Date(week.end_date + "T00:00:00Z");
    if (saturday) end.setUTCDate(end.getUTCDate() + 1);
    const plan: WeeklyPlan = {
      id,
      class_id: klass.id,
      school_year: klass.school_year,
      week_id: weekId,
      target_month: monthly.target_month,
      generation_mode: "LLM_PLANNER",
      // WeekPeriod 는 늘 월~금이다. 토요일은 표시 기간(display_end_date)에만 나타난다 (§3-2).
      week_period: {
        label: week.label,
        start_date: week.start_date,
        end_date: week.end_date,
      },
      operating_days: saturday
        ? ["MON", "TUE", "WED", "THU", "FRI", "SAT"]
        : ["MON", "TUE", "WED", "THU", "FRI"],
      display_end_date: saturday ? end.toISOString().slice(0, 10) : week.end_date,
      status: "DRAFT",
      revision: 1,
      base_template_ref: TEMPLATE_REF,
      parent: {
        monthly_plan_id: monthly.id,
        theme: monthly.parent.theme,
        confirmed_at: monthly.confirmed_at ?? at,
      },
      // 서버는 교사 입력 칸을 따로 표시하지 않는다 — 칸의 `generation` 이 가른다 (§10-2).
      sections: SECTIONS.map((key, order) => ({
        section_key: key,
        label: null,
        role: "CONTENT",
        visible: true,
        order,
        semantic_variant: null,
        cells: [cell(key)],
      })),
      constraints: [],
      verification: { executed_rules: [RULE], findings: [] },
      created_at: at,
      confirmed_at: null,
    };
    db.weeklyPlans.push(plan);
    return plan;
  });

/** 칸 하나를 바꾸고 revision 을 올린다. 못 찾으면 그대로 둔다 — 부르는 쪽이 먼저 본다. */
const changeWeeklyCell = (id: number, itemId: string, apply: (cell: WeeklyCell) => void) =>
  commit((db) => {
    const plan = db.weeklyPlans.find((p) => p.id === id)!;
    for (const section of plan.sections)
      for (const cell of section.cells) if (cell.item_id === itemId) apply(cell);
    plan.revision += 1;
    return plan;
  });

export const findWeeklyCell = (plan: WeeklyPlan, itemId: string) => {
  for (const section of plan.sections)
    for (const cell of section.cells) if (cell.item_id === itemId) return { section, cell };
  return null;
};

/** 교사가 고치면 값만 바뀐다. `generation` 은 처음 무엇이 만들었는지라 그대로 둔다 (§5-3). */
export const editWeeklyCellValue = (id: number, itemId: string, value: string) =>
  changeWeeklyCell(id, itemId, (cell) => {
    cell.value = value;
    cell.state = value ? "FILLED" : "EMPTY_VALID";
    // 교사가 처음 쓴 칸은 그때 MANUAL 이 된다 (§10-2).
    if (cell.generation === null && value) cell.generation = { method: "MANUAL", ...RULE };
  });

export const regenerateWeeklyCellValue = (
  id: number,
  itemId: string,
  label: string,
  revision: number,
) =>
  changeWeeklyCell(id, itemId, (cell) => {
    cell.value = label + " 다시 만든 내용 (rev " + revision + ")";
    cell.state = "FILLED";
    cell.generation = { method: "RULE_LLM", ...CELL_RULE };
  });

export const confirmWeekly = (id: number) =>
  commit((db) => {
    const plan = db.weeklyPlans.find((p) => p.id === id)!;
    plan.status = "CONFIRMED";
    plan.confirmed_at = new Date().toISOString();
    plan.revision += 1;
    return plan;
  });

export const removeWeekly = (id: number) =>
  commit((db) => {
    db.weeklyPlans = db.weeklyPlans.filter((p) => p.id !== id);
  });
