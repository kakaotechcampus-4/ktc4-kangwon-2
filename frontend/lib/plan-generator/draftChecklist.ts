import type { AnnualPlanResponse, MonthlyPlan, PlayMonthlyPlan, WeeklyPlan } from "../api/types";

/**
 * 「이어서 하기」 메모지의 체크 줄 — 그 초안에서 **AI 후보로 채우는 줄**만, 다 채웠으면 체크.
 * 조건은 편집 화면이 「AI 후보」 탭을 여는 줄과 같다. 메모지 칸이 좁아 이름은 짧게 쓴다.
 * 월별 주제형 연간은 AI 후보가 없어 빈 목록이다.
 */
export type CheckItem = { label: string; done: boolean };

const filled = (value?: string | null) => !!value?.trim();

/** 놀이 중심형 연간 — 구간마다 놀이를 5개 골라야 확정된다. */
export const annualChecklist = (plan: AnnualPlanResponse): CheckItem[] =>
  plan.format === "PLAY_PROJECT"
    ? plan.periods.map((p) => ({ label: p.label, done: p.selected.length >= 5 }))
    : [];

/** 월별 주제형 월간 — 안전교육 후보 · 훈련 후보가 있을 때. */
export function monthlyChecklist(plan: MonthlyPlan): CheckItem[] {
  const items: CheckItem[] = [];
  if (plan.safety_candidates.length)
    items.push({
      label: "안전교육",
      done: plan.safety_weeks.every((w) => filled(w.display_value)),
    });
  if (plan.drill_candidates.length) {
    const drill = plan.sections.find((s) => s.section_key === "drill")?.cells[0];
    items.push({ label: "소방대피", done: filled(drill?.value) });
  }
  return items;
}

/** 놀이 중심형 월간 — 안전교육 · 훈련 후보, 그리고 AI 후보에서 고르는 두 목록(ADR-065). */
export function playMonthlyChecklist(plan: PlayMonthlyPlan): CheckItem[] {
  const value = (id: string | null) =>
    id ? plan.safety_candidates.find((c) => c.cell.item_id === id)?.cell.value : "";
  const items: CheckItem[] = [];
  if (plan.safety_weeks.length)
    items.push({
      label: "안전교육",
      done: plan.safety_weeks.every((w) => filled(value(w.candidate_item_id))),
    });
  const drill = plan.teacher_inputs.find((t) => t.key === "fire_disaster_drill");
  if (drill && plan.drill_candidates.length)
    items.push({ label: "소방대피", done: filled(drill.cell.value) });
  const pick = plan.activity_pick;
  if (pick != null) {
    items.push({ label: "함께 활동", done: plan.together.length >= pick });
    items.push({ label: "자유놀이", done: plan.free_play.length >= pick });
  }
  return items;
}

/** 주간 — 후보가 있는 대·소집단활동 칸 · 후보형 실내 자유놀이 칸. */
export function weeklyChecklist(plan: WeeklyPlan): CheckItem[] {
  const done = (key: string) =>
    plan.sections
      .filter((s) => s.visible && s.section_key === key)
      .every((s) => s.cells.every((c) => c.teacher_input || filled(c.value)));
  const items: CheckItem[] = [];
  const candidates = (plan.activity_candidates ?? []).filter(
    (c) => c.section_key !== "indoor_play",
  );
  if ((plan.activity_grids ?? []).length && candidates.length)
    items.push({ label: "대·소집단", done: done("group_activity") });
  if (plan.indoor_play_selection) items.push({ label: "실내놀이", done: done("indoor_play") });
  return items;
}
