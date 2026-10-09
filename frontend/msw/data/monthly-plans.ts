import { read, commit } from "./store";
import type {
  AnnualPlan,
  ApiClass,
  MonthlyCell,
  MonthlyPlan,
  MonthlyPlanSummary,
  ProfileRef,
  ProfileResolution,
  ReadyProfile,
} from "../../lib/api/types";

/**
 * 월간계획안 · 양식 설정 목업 (docs/api-spec.md §9-1 ~ §9-3).
 *
 * 칸 값은 개발용 고정 문장이다 — LLM 을 부르지 않는다. 서버처럼 주 개수는 달력이 정하고
 * (4 · 5 · 6주), 안전교육은 근거가 없어 비워 둔 「근거 필요」 칸이다.
 */
const RULE = { rule_id: "mock.monthly", rule_version: "mock-v1" };
/** Core 가 다시 만들 수 있다고 하는 Section (§9-3). 나머지는 422 `["item_id"]`. */
export const REGENERATABLE = ["focus", "outdoor_play", "basic_habit", "goals"];
const SECTIONS: ReadyProfile["sections"] = [
  { section_key: "theme", label: "주제", repeat_by: "NONE", visible: true },
  { section_key: "week_axis", label: "주", repeat_by: null, visible: true },
  { section_key: "focus", label: "소주제", repeat_by: "WEEK", visible: true },
  { section_key: "outdoor_play", label: "바깥놀이", repeat_by: "WEEK", visible: true },
  { section_key: "safety_education", label: "안전교육", repeat_by: "WEEK", visible: true },
  { section_key: "goals", label: "목표", repeat_by: "NONE", visible: true },
];

/**
 * 원마다 READY 하나. 서버에는 아직 Profile 만들기 API(BE-1)가 없어 목업이 고정으로 둔다.
 * 운영 서버는 Template 승인 전까지 빈 목록이다(§9-2 「승인 조건」).
 */
export const readyProfile = (centerId: number): ReadyProfile => ({
  profile_ref: { profile_id: "tprofile_mock_" + centerId, profile_version: "v1" },
  status: "READY",
  base_template_ref: {
    template_id: "ssuksak.monthly-template-a",
    template_version: "monthly-template-a-v0.2.1",
  },
  selected_optional_keys: ["focus", "goals"],
  sections: SECTIONS,
  created_at: "2026-03-01T00:00:00+09:00",
});
const sameRef = (a: ProfileRef, b: ProfileRef) =>
  a.profile_id === b.profile_id && a.profile_version === b.profile_version;
export const isReadyProfile = (centerId: number, ref: ProfileRef) =>
  sameRef(readyProfile(centerId).profile_ref, ref);

/** 반 override 는 목업에 없다. 원 기본이 없으면 「선택 필요」 (§9-2 R1 ~ R4). */
export const resolveProfile = (centerId: number): ProfileResolution => {
  const ref = read().profileDefaults[centerId];
  return ref
    ? { source: "INSTITUTION_DEFAULT", profile_ref: ref, reason: null }
    : { source: "SELECTION_REQUIRED", profile_ref: null, reason: "NO_POINTER" };
};
/** 원 기본 포인터. 바꾸는 API 가 아직 없어 테스트 · 개발 콘솔에서만 부른다. */
export const setCenterDefaultProfile = (centerId: number, ref: ProfileRef) =>
  commit((db) => {
    db.profileDefaults[centerId] = ref;
  });

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

export const addMonthly = (klass: ApiClass, annual: AnnualPlan, month: number, ref: ProfileRef) =>
  commit((db) => {
    const id = db.next++,
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
      profile_ref: ref,
      base_template_ref: readyProfile(klass.center_id).base_template_ref,
      parent: { annual_plan_id: annual.id, theme, confirmed_at: new Date().toISOString() },
      weeks,
      sections: SECTIONS.map((s, order) => ({
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
      created_at: new Date().toISOString(),
      confirmed_at: null,
    };
    db.monthlyPlans.push(plan);
    return plan;
  });

/** 칸을 찾아 바꾸고 revision 을 올린다. 다른 칸은 손대지 않는다. */
const changeCell = (id: number, itemId: string, change: (cell: MonthlyCell) => void) =>
  commit((db) => {
    const plan = db.monthlyPlans.find((p) => p.id === id)!;
    change(plan.sections.flatMap((s) => s.cells).find((c) => c.item_id === itemId)!);
    plan.revision += 1;
    return plan;
  });
export const findCell = (plan: MonthlyPlan, itemId: string) => {
  const section = plan.sections.find((s) => s.cells.some((c) => c.item_id === itemId));
  return section && { section, cell: section.cells.find((c) => c.item_id === itemId)! };
};
/** 근거 · 생성 방식은 그대로다 — 교사 수정은 변경 이력에만 남는다(목업은 이력이 없다). */
export const editCell = (id: number, itemId: string, value: string, sectionKey: string) =>
  changeCell(id, itemId, (cell) => {
    cell.value = value;
    cell.state = value
      ? "FILLED"
      : sectionKey === "safety_education"
        ? "EMPTY_UNRESOLVED"
        : "EMPTY_VALID";
  });
/** 다음 revision 을 값에 넣어 매번 다른 결정적 문장을 만든다. */
export const regenerateCell = (id: number, itemId: string, label: string, nextRevision: number) =>
  changeCell(id, itemId, (cell) => {
    cell.value = "다시 만든 " + label + " (" + nextRevision + "판)";
    cell.state = "FILLED";
    cell.generation = { method: "RULE_LLM", ...RULE };
  });
export const confirmMonthly = (id: number) =>
  commit((db) => {
    const plan = db.monthlyPlans.find((p) => p.id === id)!;
    plan.status = "CONFIRMED";
    plan.revision += 1;
    plan.confirmed_at = new Date().toISOString();
    return plan;
  });
