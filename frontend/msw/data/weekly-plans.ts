import { read, commit } from "./store";
import { safetyView } from "./monthly-plans";
import type {
  ApiClass,
  MonthlyPlan,
  WeeklyCell,
  WeeklyPlan,
  WeeklyPlanSummary,
  WeeklyActivityGrid,
} from "../../lib/api/types";

/**
 * 주간계획안 목업 (docs/weekly-plan-contract.md §13).
 *
 * 주차 열이 없고 교사 입력 칸 셋은
 * 값을 만들지 않으며(`generation: null`), 토요일 설정이 `operating_days` 로 굳고,
 * 근거로 쓴 부모 월간 칸의 그때 값을 `parent_snapshots` 로 들고 온다.
 * 후보 모드는 요일 칸·종류별 고정 후보·분할 트리를 쓰며 실제 생성 품질을 대신하지 않는다.
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
/** 안전교육은 만들지 않는다 — 월간에서 그 주에 놓은 후보를 복사하고, 없으면 빈칸이다. */
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
  activityCandidates = false,
  indoorCandidates = false,
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
    // 서버 Core(S-1)처럼 월간에서 이 주에 놓은 안전교육 후보를 「[분류] 문장」 그대로 복사한다.
    const placed = safetyView(monthly).safety_weeks.find((w) => w.week_id === weekId);
    const source = placed?.display_value
      ? monthly.safety_candidates.find((c) => c.cell.item_id === placed.candidate_item_id)?.cell
      : undefined;
    const cell = (key: string): WeeklyCell => {
      if (key === "safety_education" && source)
        return {
          item_id: "item_" + id + "_" + key,
          value: placed!.display_value,
          state: "FILLED",
          evidence: [parentEvidence],
          generation: {
            method: "RULE_ONLY",
            rule_id: "weekly.safety.parent_placement",
            rule_version: RULE.rule_version,
          },
          parent_snapshots: [{ parent_item_id: source.item_id, snapshot_value: source.value }],
          teacher_input: false,
        };
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
        teacher_input: teacher,
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
      parent_changed: false, // 저장값은 쓰지 않는다 — 응답 때 handler 가 다시 계산한다.
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
    if (activityCandidates || indoorCandidates) {
      plan.base_template_ref = { ...TEMPLATE_REF, template_version: "weekly-template-a-v0.2.0" };
      for (const section of plan.sections) {
        if (section.section_key !== "group_activity" && section.section_key !== "special_program")
          continue;
        section.repeat_by = "DAY";
        section.cells = plan.operating_days.map((day) => ({
          ...cell(section.section_key),
          item_id: `item_${id}_${section.section_key}_${day}`,
          day: day as WeeklyCell["day"],
          value: "",
          state: "EMPTY_VALID" as const,
        }));
      }
      const group = plan.sections.find((entry) => entry.section_key === "group_activity")!;
      plan.activity_grids = group.cells.map((cell) => ({
        cell_id: cell.item_id,
        split_id: null,
        axis: null,
        ratio: null,
        children: [],
      }));
      plan.activity_candidates = [
        "이야기나누기",
        "음률",
        "신체",
        "미술",
        "과학",
        "동화",
        "게임",
        "동시",
        "요리",
        "동극",
      ].map((kind, index) => {
        const name = `${kind} 함께 즐기기`;
        const description = "관심 있는 대상과 움직임을 탐색합니다.";
        return {
          section_key: "group_activity" as const,
          activity_type: kind,
          name,
          description,
          cell: {
            ...cell("group_activity"),
            item_id: `item_${id}_candidate_${index}`,
            value: `${name}: ${description}`,
            day: null,
            state: "FILLED",
          },
        };
      });
    }
    plan.indoor_play_selection = indoorCandidates;
    if (indoorCandidates) {
      const indoor = plan.sections.find((section) => section.section_key === "indoor_play")!;
      indoor.cells[0].value = "";
      indoor.cells[0].state = "EMPTY_VALID";
      indoor.cells[0].evidence = [];
      indoor.cells[0].parent_snapshots = [];
      indoor.cells[0].generation = {
        method: "RULE_ONLY",
        rule_id: "weekly.indoor_empty",
        rule_version: "v1",
      };
      const examples = [
        ["역할놀이", "열매 가게 꾸미기", "열매를 사고파는 역할을 나누며 친구와 말을 주고받습니다."],
        [
          "쌓기놀이",
          "열매가 구르는 길 만들기",
          "블록 길의 기울기를 바꾸며 열매의 움직임을 살펴봅니다.",
        ],
        ["미술놀이", "나뭇잎 무늬 꾸미기", "잎의 모양과 무늬를 살펴보고 여러 색으로 표현합니다."],
      ];
      plan.activity_candidates = [
        ...(plan.activity_candidates ?? []),
        ...examples.map(([kind, name, description], index) => ({
          section_key: "indoor_play" as const,
          activity_type: kind,
          name,
          description,
          cell: {
            ...cell("indoor_play"),
            item_id: `item_${id}_indoor_candidate_${index}`,
            value: `${name}: ${description}`,
            state: "FILLED" as const,
            day: null,
          },
        })),
      ];
    }
    db.weeklyPlans.push(plan);
    return plan;
  });

/** 칸 하나를 바꾸고 revision 을 올린다. 못 찾으면 그대로 둔다 — 부르는 쪽이 먼저 본다. */
const changeWeeklyCell = (id: number, itemId: string, apply: (cell: WeeklyCell) => void) =>
  commit((db) => {
    const plan = db.weeklyPlans.find((p) => p.id === id)!;
    for (const section of plan.sections)
      for (const cell of section.cells) if (cell.item_id === itemId) apply(cell);
    for (const candidate of plan.activity_candidates ?? [])
      if (candidate.cell.item_id === itemId) {
        apply(candidate.cell);
        const [name, ...description] = candidate.cell.value.split(":");
        candidate.name = name.trim();
        candidate.description = description.join(":").trim();
      }
    plan.revision += 1;
    return plan;
  });

export const findWeeklyCell = (plan: WeeklyPlan, itemId: string) => {
  for (const section of plan.sections)
    for (const cell of section.cells) if (cell.item_id === itemId) return { section, cell };
  const candidate = plan.activity_candidates?.find((entry) => entry.cell.item_id === itemId);
  if (candidate)
    return {
      section: plan.sections.find(
        (entry) => entry.section_key === (candidate.section_key ?? "group_activity"),
      )!,
      cell: candidate.cell,
    };
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

/** 확정 취소 (U). 이미 초안이면 handler 가 먼저 그대로 돌려준다. */
export const unconfirmWeekly = (id: number) =>
  commit((db) => {
    const plan = db.weeklyPlans.find((p) => p.id === id)!;
    plan.status = "DRAFT";
    plan.confirmed_at = null;
    plan.revision += 1;
    return plan;
  });
/** 부모 월간이 지금 확정이 아니거나 확정 시각이 스냅샷과 다르면 바뀐 것이다. */
export const monthlyChanged = (plan: WeeklyPlan) => {
  const monthly = read().monthlyPlans.find((p) => p.id === plan.parent.monthly_plan_id);
  return monthly?.status !== "CONFIRMED" || monthly.confirmed_at !== plan.parent.confirmed_at;
};

export const removeWeekly = (id: number) =>
  commit((db) => {
    db.weeklyPlans = db.weeklyPlans.filter((p) => p.id !== id);
  });

export const changeWeeklyIndoor = (
  id: number,
  operation: "add" | "order" | "remove",
  input: { candidateId?: string | null; itemIds?: string[]; itemId?: string },
) =>
  commit((db) => {
    const plan = db.weeklyPlans.find((entry) => entry.id === id)!;
    if (!plan.indoor_play_selection) throw new Error("후보 방식 계획안이 아니에요.");
    const section = plan.sections.find((entry) => entry.section_key === "indoor_play")!;
    const rows = section.cells;
    const blank = () => ({
      ...rows[0],
      item_id: `item_indoor_${db.next++}`,
      value: "",
      state: "EMPTY_VALID" as const,
      evidence: [],
      parent_snapshots: [],
      generation: {
        method: "RULE_ONLY" as const,
        rule_id: "weekly.indoor_empty",
        rule_version: "v1",
      },
    });
    if (operation === "add") {
      const empty = rows.find((cell) => !cell.value.trim());
      const candidate =
        input.candidateId == null
          ? null
          : plan.activity_candidates?.find(
              (entry) =>
                entry.section_key === "indoor_play" && entry.cell.item_id === input.candidateId,
            );
      if (input.candidateId != null && !candidate?.name.trim())
        throw new Error("후보를 골라주세요.");
      if (
        candidate &&
        rows.some(
          (cell) => cell.value.trim() && db.weeklyIndoorCopies[cell.item_id] === input.candidateId,
        )
      )
        return plan;
      if (!candidate && empty) return plan;
      const cell = empty ?? blank();
      if (candidate) {
        cell.value = `[${candidate.activity_type}] ${candidate.name}`;
        cell.state = "FILLED";
        cell.evidence = candidate.cell.evidence;
        cell.generation = {
          method: "RULE_ONLY",
          rule_id: "weekly.activity_copy",
          rule_version: "v1",
        };
        db.weeklyIndoorCopies[cell.item_id] = candidate.cell.item_id;
      }
      if (!empty) rows.push(cell);
    } else if (operation === "order") {
      const ids = input.itemIds ?? [];
      if (
        ids.length !== rows.length ||
        new Set(ids).size !== rows.length ||
        ids.some((id) => !rows.some((cell) => cell.item_id === id))
      )
        throw new Error("순서가 맞지 않아요.");
      if (ids.every((id, index) => rows[index].item_id === id)) return plan;
      section.cells = ids.map((id) => rows.find((cell) => cell.item_id === id)!);
    } else {
      if (!rows.some((cell) => cell.item_id === input.itemId)) throw new Error("칸이 없어요.");
      section.cells =
        rows.length === 1 ? [blank()] : rows.filter((cell) => cell.item_id !== input.itemId);
      delete db.weeklyIndoorCopies[input.itemId!];
    }
    plan.revision += 1;
    return plan;
  });

export const changeWeeklyActivity = (
  id: number,
  itemId: string,
  operation: "copy" | "split" | "remove",
  candidateId?: string,
  axis?: "VERTICAL" | "HORIZONTAL",
) =>
  commit((db) => {
    const plan = db.weeklyPlans.find((entry) => entry.id === id)!;
    const group = plan.sections.find((entry) => entry.section_key === "group_activity")!;
    const cell = group.cells.find((entry) => entry.item_id === itemId);
    if (!cell || !plan.activity_grids?.length) throw new Error("활동 칸을 찾을 수 없어요.");
    let leaf: WeeklyActivityGrid | undefined;
    let parent: WeeklyActivityGrid | undefined;
    let width = 0,
      depth = 0;
    function visit(
      node: WeeklyActivityGrid,
      previous: WeeklyActivityGrid | undefined,
      w: number,
      d: number,
    ) {
      if (node.cell_id === itemId) {
        leaf = node;
        parent = previous;
        width = w;
        depth = d;
      }
      node.children.forEach((child, index) =>
        visit(
          child,
          node,
          node.axis === "HORIZONTAL"
            ? (w * (index === 0 ? (node.ratio ?? 50) : 100 - (node.ratio ?? 50))) / 100
            : w,
          d + 1,
        ),
      );
    }
    plan.activity_grids.forEach((node) =>
      visit(node, undefined, 500 / (6 * plan.operating_days.length), 0),
    );
    if (!leaf) throw new Error("활동 칸을 찾을 수 없어요.");
    if (operation === "copy") {
      const candidate = plan.activity_candidates?.find(
        (entry) => entry.cell.item_id === candidateId && entry.section_key !== "indoor_play",
      );
      if (!candidate?.name.trim()) throw new Error("후보를 선택해주세요.");
      const value = `[${candidate.activity_type}] ${candidate.name}`;
      if (cell.value === value) return plan;
      cell.value = value;
      cell.state = "FILLED";
      cell.evidence = candidate.cell.evidence;
      cell.generation = {
        method: "RULE_ONLY",
        rule_id: "weekly.activity_copy",
        rule_version: "v1",
      };
    } else if (operation === "split") {
      if (depth >= 4 || (axis === "HORIZONTAL" && width / 2 < 3.5))
        throw new Error("칸 나누기 한도를 넘었어요.");
      const next = `mock_activity_${db.next++}`;
      const first = { ...leaf };
      Object.assign(leaf, {
        cell_id: null,
        split_id: `mock_split_${db.next++}`,
        axis,
        ratio: 50,
        children: [first, { cell_id: next, split_id: null, axis: null, ratio: null, children: [] }],
      });
      group.cells.splice(group.cells.indexOf(cell) + 1, 0, {
        ...cell,
        item_id: next,
        value: "",
        state: "EMPTY_VALID",
        evidence: [],
        generation: { method: "RULE_ONLY", rule_id: "weekly.activity_empty", rule_version: "v1" },
      });
    } else {
      if (!parent) throw new Error("하루에 한 칸은 남겨주세요.");
      const sibling = parent.children.find((node) => node !== leaf)!;
      Object.assign(parent, sibling);
      group.cells = group.cells.filter((entry) => entry.item_id !== itemId);
    }
    plan.revision += 1;
    return plan;
  });
