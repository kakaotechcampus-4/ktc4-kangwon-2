import { read, commit, type MockAuditEvent, type MockPlanAudit } from "./store";
import { MOCK_USER_ID } from "./template-profiles";
import type {
  AnnualPlan,
  ApiClass,
  MonthlyAuditEvent,
  MonthlyCell,
  MonthlyPlan,
  MonthlyPlanSummary,
  MonthlyTeacherTable,
  ReadyProfile,
} from "../../lib/api/types";
import { drillText } from "../../lib/monthly/section-labels";
import {
  leaf,
  leaves,
  removeLeaf,
  splitLeaf,
  withRatio,
} from "../../lib/plan-generator/playMonthlyTimetable";

/**
 * 월간계획안 목업 (docs/api-spec.md §9-1 · §9-3). 양식 설정은 template-profiles.ts 다.
 *
 * 칸 값은 개발용 고정 문장이다 — LLM 을 부르지 않는다. 서버처럼 주 개수는 달력이 정하고
 * (4 · 5 · 6주), 안전교육은 근거가 없어 비워 둔 「근거 필요」 칸이다.
 */
const RULE = { rule_id: "mock.monthly", rule_version: "mock-v1" };
/** 칸 재생성 결과의 생성 방식. 서버처럼 처음 생성과 다른 rule_version 이다. */
const CELL_RULE = { rule_id: "mock.monthly.cell", rule_version: "mock-cell-v1" };
/** 훈련 후보 복사 칸의 생성 방식 (Core `DRILL_COPY_GENERATION`). */
const DRILL_COPY = { rule_id: "monthly.drill_copy", rule_version: "v1" };
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
  arrangement_change: null,
  copied_from: null,
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
export function weeksOf(targetMonth: string): MonthlyPlan["weeks"] {
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
    indoor_alternative: week + "주 실내 대체 놀이",
    goals: theme + "을(를) 즐겁게 탐색한다",
    basic_habit: week + "주 기본생활 습관",
  })[key] ?? "";

/**
 * 안전교육 후보 8 · 훈련 주제 5 — 서버 Core 가 주제형(v1) · 놀이형(v2) 월간에 같이 주는 후보다
 * (monthly_router `SAFETY_CANDIDATES` · `DRILL_TOPICS`). 두 목업이 같은 목록을 쓴다.
 */
export const evidence = (type: string, id: string, version: string, name: string | null = null) => [
  {
    source_type: type,
    source_id: id,
    source_version: version,
    effective_date: null,
    display_name: name,
  },
];
export const SAFETY: [string, string | null, string | null, string, string][] = [
  ["STATUTORY", "sexual_violence_prevention", null, "성폭력 예방", "내 몸의 소중함"],
  ["STATUTORY", "child_abuse_prevention", null, "아동학대 예방", "나의 권리 찾기(소중한 나)"],
  [
    "STATUTORY",
    "missing_and_abduction_prevention",
    null,
    "실종·유괴 예방",
    "길을 잃을 수 있는 상황 이해하기",
  ],
  [
    "STATUTORY",
    "infectious_disease_and_drug_misuse_prevention",
    null,
    "감염병·약물 예방",
    "감염병 예방을 위한 개인위생 실천 습관",
  ],
  ["STATUTORY", "disaster_preparedness_safety", null, "재난대비", "화재의 원인과 예방법"],
  ["STATUTORY", "traffic_safety", null, "교통안전", "차도, 보도 및 신호등의 의미 알기"],
  ["SUPPLEMENTAL", null, "elevator", "생활안전", "안전교육 및 건강영양교육"],
  ["SUPPLEMENTAL", null, "playground", "생활안전", "안전교육"],
];
export const DRILLS = [
  ["fire_a", "화재 가"],
  ["quake", "지진"],
  ["fire_b", "화재 나"],
  ["fire_c", "화재 다"],
  ["fire_d", "화재 라"],
];
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
        // 서버처럼 후보로 두는 안전교육 주 칸 · 훈련 문서 칸은 비어도 되는 칸으로 시작한다.
        state: value
          ? "FILLED"
          : key === "safety_education" || key === "drill"
            ? "EMPTY_VALID"
            : "EMPTY_UNRESOLVED",
        evidence: value ? [parentEvidence] : [],
        // 훈련 문서 칸은 놀이 월간 교사 칸처럼 생성 방식 없이 시작한다.
        generation:
          key === "drill"
            ? null
            : { method: key === "theme" || !value ? "RULE_ONLY" : "RULE_LLM", ...RULE },
      };
    };
    const candidate = (key: string, value: string, sources: MonthlyCell["evidence"]) => ({
      item_id: "item_" + id + "_" + key,
      week_id: null,
      value,
      state: "FILLED" as const,
      evidence: sources,
      generation: { method: "RULE_LLM" as const, ...RULE },
    });
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
      // 스냅샷은 부모의 그때 확정 시각이다 — 다시 확정하면 달라져 `parent_changed` 가 된다.
      parent: {
        annual_plan_id: annual.id,
        theme,
        confirmed_at: annualFor(klass.id)?.confirmed_at ?? at,
      },
      parent_changed: false, // 저장값은 쓰지 않는다 — 응답 때 handler 가 다시 계산한다.
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
      drill_candidates: [],
      teacher_tables: blankTeacherTables(id),
      // 놀이 월간 목업과 같은 후보 · 문장 · 근거. 주에는 아무것도 두지 않고 시작한다(서버와 같다).
      safety_candidates: SAFETY.map(([kind, category_id, topic_group, text, name], i) => ({
        kind: kind as "STATUTORY" | "SUPPLEMENTAL",
        category_id,
        topic_group,
        cell: candidate(
          "safety_" + i,
          text + " 약속을 함께 알아보아요",
          kind === "STATUTORY"
            ? evidence(
                "SAFETY_RULE",
                "annex6:" + category_id + ":1",
                "child-welfare-act-decree-annex6-2022-06-21",
                name,
              )
            : evidence("INSTITUTION_SAMPLE", "ev_sample_" + i, "v1", name),
        ),
      })),
      safety_weeks: weeks.map((w) => ({
        week_id: w.week_id,
        candidate_item_id: null,
        display_value: "",
      })),
      notices: [], // 응답마다 handler 가 다시 계산한다.
      created_at: at,
      confirmed_at: null,
    };
    // 서버처럼 훈련 문서 칸이 있는 양식(v0.2.3 에서 고른 경우)만 훈련 후보가 온다.
    if (plan.sections.some((s) => s.section_key === "drill" && s.cells.length))
      plan.drill_candidates = DRILLS.map(([topic_id, label], i) => ({
        topic_id,
        label,
        cell: candidate(
          "drill_" + topic_id,
          i + 1 + "번째 상황을 가정해 대피 훈련을 해요",
          evidence("CURRICULUM", "t.4", "test-curriculum-v1"),
        ),
      }));
    db.monthlyPlans.push(plan);
    // 서버 Core 처럼 계획안 단위 CREATED 하나와 칸마다 CREATED 하나. 모두 같은 시각이다.
    const created = () => event("CREATED", at, { actor: null, system_actor: SYSTEM_ACTOR });
    db.monthlyAudit[id] = {
      plan: [created()],
      cells: Object.fromEntries(cellsOf(plan).map(({ cell: c }) => [c.item_id, [created()]])),
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
    const cell = cellsOf(plan).find((x) => x.cell.item_id === itemId)!.cell;
    // 목업 칸은 늘 생성 방식이 있다(null 은 훈련 문서 칸뿐이다).
    const before = { value: cell.value, generation: { ...cell.generation! } };
    change(cell);
    plan.revision += 1;
    const audit = (db.monthlyAudit[id] ??= { plan: [], cells: {} });
    (audit.cells[itemId] ??= []).push(
      event(type, nextStamp(audit), {
        value_change: { before: before.value, after: cell.value },
        generation_change:
          type === "REGENERATED"
            ? { before: before.generation, after: { ...cell.generation! } }
            : null,
      }),
    );
    return plan;
  });
/**
 * 계획안의 모든 칸과 그 칸의 Section. 안전교육 · 훈련 후보 칸은 그 후보를 두는 Section 에 붙인다
 * (고칠 수 있고 이력이 있다 — 다시 만들기는 REGENERATABLE 이 막는다).
 */
const cellsOf = (plan: MonthlyPlan) => {
  const of = (key: string) => plan.sections.find((s) => s.section_key === key)!;
  return [
    ...plan.sections.flatMap((section) => section.cells.map((cell) => ({ section, cell }))),
    // 후보를 넣기 전에 저장된 옛 목업 계획안에는 두 목록이 없다.
    ...(plan.safety_candidates ?? []).map((c) => ({
      section: of("safety_education"),
      cell: c.cell,
    })),
    ...(plan.drill_candidates ?? []).map((d) => ({ section: of("drill"), cell: d.cell })),
  ];
};
export const findCell = (plan: MonthlyPlan, itemId: string) =>
  cellsOf(plan).find(({ cell }) => cell.item_id === itemId);
/** 그 주에 후보를 두거나(null 이면 비운다) 바꾼다. 같은 입력이면 그대로(revision · 이력 그대로). */
export const placeMonthlySafety = (id: number, weekId: string, candidate: string | null) =>
  commit((db) => {
    const plan = db.monthlyPlans.find((p) => p.id === id)!;
    const week = plan.safety_weeks.find((w) => w.week_id === weekId)!;
    const before = week.candidate_item_id;
    if (before === candidate) return plan;
    week.candidate_item_id = candidate;
    plan.revision += 1;
    const audit = (db.monthlyAudit[id] ??= { plan: [], cells: {} });
    audit.plan.push(
      event("ARRANGEMENT_CHANGED", nextStamp(audit), {
        arrangement_change: {
          scope: weekId,
          before: before ? [before] : [],
          after: candidate ? [candidate] : [],
        },
      }),
    );
    return plan;
  });
/**
 * 훈련 후보를 훈련 문서 칸에 복사한다 — 칸은 후보의 값 · 근거, `RULE_ONLY`(monthly.drill_copy).
 * 서버처럼 값 · 근거 · 방식에 복사 원본까지 같아야 같은 복사다(그대로 돌려준다).
 */
export const copyMonthlyDrill = (id: number, itemId: string) =>
  commit((db) => {
    const plan = db.monthlyPlans.find((p) => p.id === id)!;
    const drill = plan.drill_candidates.find((d) => d.cell.item_id === itemId)!;
    const from = { ...drill.cell, value: drillText(drill) };
    const to = plan.sections.find((s) => s.section_key === "drill")!.cells[0];
    const audit = (db.monthlyAudit[id] ??= { plan: [], cells: {} });
    const log = (audit.cells[to.item_id] ??= []);
    const source = log.findLast((e) => e.type === "CANDIDATE_COPIED")?.copied_from;
    const generation = { method: "RULE_ONLY" as const, ...DRILL_COPY };
    const same = (c: Pick<MonthlyCell, "value" | "evidence" | "generation">, src?: string | null) =>
      JSON.stringify([c.value, c.evidence, c.generation, src]);
    if (same(to, source) === same({ ...from, generation }, itemId)) return plan;
    log.push(
      event("CANDIDATE_COPIED", nextStamp(audit), {
        value_change: { before: to.value, after: from.value },
        generation_change: to.generation ? { before: to.generation, after: generation } : null,
        copied_from: itemId,
      }),
    );
    Object.assign(to, {
      value: from.value,
      state: from.value.trim() ? "FILLED" : "EMPTY_VALID",
      evidence: structuredClone(from.evidence),
      generation,
    });
    plan.revision += 1;
    return plan;
  });
/** 근거 · 생성 방식은 그대로다 — 교사 수정은 변경 이력(TEACHER_EDITED)에만 남는다. */
export const editCell = (id: number, itemId: string, value: string, sectionKey: string) =>
  changeCell(id, itemId, "TEACHER_EDITED", (cell) => {
    cell.value = value;
    // 처음 쓰는 훈련 문서 칸만 MANUAL 이 된다(놀이 월간 교사 칸과 같다).
    cell.generation ??= { method: "MANUAL", rule_id: null, rule_version: null };
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

/** 서버 `DELETE` 와 같다 — 확정본도 지우고(ADR-062), 이 월간으로 만든 주간이 있으면 「IN_USE」. */
export const removeMonthly = (id: number) =>
  commit((db): "IN_USE" | null => {
    if (db.weeklyPlans.some((w) => w.parent.monthly_plan_id === id)) return "IN_USE";
    db.monthlyPlans = db.monthlyPlans.filter((p) => p.id !== id);
    delete db.monthlyAudit[id];
    return null;
  });

/** 확정 취소. 값 · 이력은 그대로 두고 `UNCONFIRMED` 를 남긴다. 이미 초안이면 handler 가 먼저 막는다. */
export const unconfirmMonthly = (id: number) =>
  commit((db) => {
    const plan = db.monthlyPlans.find((p) => p.id === id)!;
    const audit = (db.monthlyAudit[id] ??= { plan: [], cells: {} });
    plan.status = "DRAFT";
    plan.revision += 1;
    plan.confirmed_at = null;
    audit.plan.push(event("UNCONFIRMED", nextStamp(audit)));
    return plan;
  });
/**
 * 교사 표 셋(Human Decision 2026-11-05) — 서버 `blank_teacher_tables` 와 같은 모양 · 같은 주소 규칙.
 * 표를 넣기 전에 저장된 옛 목업 계획안도 같은 빈 표를 받는다.
 */
const TABLE_SHAPES = [
  ["event_schedule", "행사 일정", 1, false, 12],
  ["specialized_timetable", "특성화 시간표", 5, true, 14],
  ["special_activity_timetable", "특별활동 시간표", 5, false, 21],
] as const;
const blankTableCell = (item_id: string) => ({
  item_id,
  value: "",
  evidence: [],
  generation: null,
});
export const blankTeacherTables = (planId: number): MonthlyTeacherTable[] =>
  TABLE_SHAPES.map(([key, label, count, titled, height]) => {
    const n = Array.from({ length: count }, (_, i) => i + 1);
    return {
      table_key: key,
      label,
      titles: titled ? n.map((i) => blankTableCell(`${planId}.${key}.title.${i}`)) : [],
      columns: n.map((i) => leaf(blankTableCell(`${planId}.${key}.${i}.1`))),
      column_widths: n.map(() => Math.floor(100 / count)),
      height_mm: height,
    };
  });
export const tablesOf = (p: MonthlyPlan) => p.teacher_tables ?? blankTeacherTables(p.id);
export const findTableCell = (p: MonthlyPlan, itemId: string) =>
  tablesOf(p)
    .flatMap((table) =>
      [...table.titles, ...table.columns.flatMap(leaves)].map((cell) => ({ table, cell })),
    )
    .find((c) => c.cell.item_id === itemId);
/** 표 하나를 바꾼다. `change` 가 false 면(같은 크기) revision 그대로. */
const changeTable = (
  id: number,
  pick: (tables: MonthlyTeacherTable[]) => MonthlyTeacherTable,
  change: (table: MonthlyTeacherTable) => boolean,
) =>
  commit((db) => {
    const plan = db.monthlyPlans.find((p) => p.id === id)!;
    plan.teacher_tables = tablesOf(plan);
    if (change(pick(plan.teacher_tables))) plan.revision += 1;
    return plan;
  });
const holding = (itemId: string) => (tables: MonthlyTeacherTable[]) =>
  tables.find((t) => JSON.stringify(t).includes(`"${itemId}"`))!;
/** 표 칸 글은 교사만 쓴다 — 처음 쓰면 MANUAL. */
export const editTableCell = (id: number, itemId: string, value: string) =>
  commit((db) => {
    const plan = db.monthlyPlans.find((p) => p.id === id)!;
    plan.teacher_tables = tablesOf(plan);
    const cell = findTableCell(plan, itemId)!.cell;
    const audit = (db.monthlyAudit[id] ??= { plan: [], cells: {} });
    (audit.cells[itemId] ??= []).push(
      event("TEACHER_EDITED", nextStamp(audit), {
        value_change: { before: cell.value, after: value },
      }),
    );
    cell.value = value;
    cell.generation ??= { method: "MANUAL", rule_id: null, rule_version: null };
    plan.revision += 1;
    return plan;
  });
export const splitTableCell = (id: number, itemId: string, axis: "VERTICAL" | "HORIZONTAL") =>
  changeTable(id, holding(itemId), (table) => {
    const at = table.columns.findIndex((c) => leaves(c).some((x) => x.item_id === itemId));
    const n = Math.max(
      ...leaves(table.columns[at]).map((c) => Number(c.item_id.split(".").at(-1)) || 0),
    );
    const added = blankTableCell(`${id}.${table.table_key}.${at + 1}.${n + 1}.${Date.now()}`);
    table.columns[at] = splitLeaf(table.columns[at], itemId, axis, "split_" + added.item_id, added);
    return true;
  });
export const removeTableCell = (id: number, itemId: string) =>
  changeTable(id, holding(itemId), (table) => {
    table.columns = table.columns.map((c) => removeLeaf(c, itemId));
    return true;
  });
export const resizeTableSplit = (id: number, splitId: string, ratio: number) =>
  changeTable(id, holding(splitId), (table) => {
    const before = JSON.stringify(table.columns);
    table.columns = table.columns.map((c) => withRatio(c, splitId, ratio));
    return JSON.stringify(table.columns) !== before;
  });
export const resizeTable = (
  id: number,
  key: string,
  size: { column_widths: number[]; height_mm: number },
) =>
  changeTable(
    id,
    (tables) => tables.find((t) => t.table_key === key)!,
    (table) => {
      if (
        table.column_widths.join() === size.column_widths.join() &&
        table.height_mm === size.height_mm
      )
        return false;
      Object.assign(table, structuredClone(size));
      return true;
    },
  );
/** 서버 `candidate_display_value` — 「[교통안전] - 문장」 · 「[생활안전] - 문장」, 빈 문장은 "". */
const LABELS = Object.fromEntries(SAFETY.map(([, category_id, , label]) => [category_id, label]));
const shownSafety = (c: MonthlyPlan["safety_candidates"][number]) =>
  !c.cell.value.trim()
    ? ""
    : "[" + (c.kind === "STATUTORY" ? LABELS[c.category_id!] : "생활안전") + "] - " + c.cell.value;
/** 주별 표시 문장과 빈 주 안내. 서버처럼 저장하지 않고 응답마다 계산한다(확정을 막지 않는다). */
export const safetyView = (p: MonthlyPlan) => {
  // 후보를 넣기 전에 저장된 옛 목업 계획안에는 두 목록이 없다.
  const byId = new Map((p.safety_candidates ?? []).map((c) => [c.cell.item_id, c]));
  const weeks = (p.safety_weeks ?? []).map((w) => {
    const c = w.candidate_item_id ? byId.get(w.candidate_item_id) : undefined;
    return { ...w, display_value: c ? shownSafety(c) : "" };
  });
  return {
    safety_weeks: weeks,
    notices: weeks
      .filter((w) => !w.display_value)
      .map((w) => ({
        code: (w.candidate_item_id === null ? "SAFETY_UNPLACED" : "SAFETY_BLANK") as
          "SAFETY_UNPLACED" | "SAFETY_BLANK",
        week_id: w.week_id,
      })),
  };
};
/** 부모 연간이 지금 확정이 아니거나 확정 시각이 스냅샷과 다르면 바뀐 것이다. */
export const annualChanged = (annualId: number, confirmedAt: string) => {
  const annual = read().plans.find((p) => p.id === annualId);
  return annual?.status !== "CONFIRMED" || annual.confirmed_at !== confirmedAt;
};

/**
 * 변경 이력 조회 (§9-5). **읽기만 한다** — 저장소 사본(read)을 정렬하고 원본은 건드리지 않는다.
 * 순서: 시각 → 계획안 먼저 → 칸은 계획안 안의 순서 → 한 칸 안에서는 저장된 순서.
 * `itemId` 를 주면 그 칸 이력과 계획안 CONFIRMED 만. 없는 칸이면 null(→ 404).
 */
export function listAudit(plan: MonthlyPlan, itemId: string | null): MonthlyAuditEvent[] | null {
  const audit = read().monthlyAudit[plan.id] ?? { plan: [], cells: {} };
  let located = cellsOf(plan);
  if (itemId !== null) {
    located = located.filter(({ cell }) => cell.item_id === itemId);
    if (!located.length) return null;
  }
  const at = (e: MockAuditEvent) => Date.parse(e.occurred_at);
  const keyed: { key: number[]; out: MonthlyAuditEvent }[] = [
    ...audit.plan
      // 칸 하나를 물어도 계획안 확정 · 확정 취소는 같이 준다(서버 get_monthly_audit).
      .filter((e) => itemId === null || e.type === "CONFIRMED" || e.type === "UNCONFIRMED")
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
  day: null,
  actor: e.actor,
  system_actor: e.system_actor,
  value_change: e.value_change,
  generation_change: e.generation_change,
  arrangement_change: e.arrangement_change ?? null,
  copied_from: e.copied_from ?? null,
});
