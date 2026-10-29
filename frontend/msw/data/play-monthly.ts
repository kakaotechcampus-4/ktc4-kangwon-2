import { read, commit, type Database } from "./store";
import { annualFor } from "./monthly-plans";
import { MOCK_USER_ID } from "./template-profiles";
import type {
  PlayMonthlyActivity,
  PlayMonthlyAuditEvent,
  PlayMonthlyCell,
  PlayMonthlyPlan,
} from "../../lib/api/types";

/**
 * 놀이 중심 월간 목업 (api-spec §9-7). 고정 데이터는 서버를 실제로 찍은 단건 응답(2026-10-28)의
 * 칸 · 개수 · 문장을 그대로 따른다 — 시안 json 은 Core 옛 모양이라 쓰지 않았다.
 * 서버는 대상 달을 반 학년도로 계산하지만 이 목업은 찍은 응답처럼 2026년 11월로 고정한다.
 */
const GEN = {
  method: "RULE_LLM",
  rule_id: "play_monthly.generate",
  rule_version: "play-monthly-planner-v2",
};
/** 서버는 계획안을 만든 쪽을 `play_monthly_application`, 사람이 한 일은 `user_{id}` 로 적는다. */
const SYSTEM_ACTOR = "play_monthly_application";
const ACTOR = "user_" + MOCK_USER_ID;
const DRILL_COPY = "play_monthly.drill_copy";
const evidence = (type: string, id: string, version: string, name: string | null = null) => [
  {
    source_type: type,
    source_id: id,
    source_version: version,
    effective_date: null,
    display_name: name,
  },
];
const curriculum = (...ids: string[]) =>
  ids.flatMap((id) => evidence("CURRICULUM", id, "test-curriculum-v1"));
const SAFETY: [string, string | null, string | null, string, string][] = [
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
const DRILLS = [
  ["fire_a", "화재 가"],
  ["quake", "지진"],
  ["fire_b", "화재 나"],
  ["fire_c", "화재 다"],
  ["fire_d", "화재 라"],
];
const TEACHER_KEYS = [
  "fire_disaster_drill",
  "specialized_timetable",
  "special_activity_timetable",
  "class_notice",
  "class_birthdays",
  "home_connection",
];

/** 이력 이벤트. 열한 키가 항상 있고 기본은 시스템이 만든 `CREATED` 다. */
type AuditInput = Partial<PlayMonthlyAuditEvent> & Pick<PlayMonthlyAuditEvent, "scope">;
const NONE = {
  item_id: null,
  actor: null,
  system_actor: SYSTEM_ACTOR,
  value_change: null,
  generation_change: null,
  link_change: null,
  arrangement_change: null,
  copied_from: null,
};
/** 시각은 앞선 이벤트보다 뒤다 — 같은 밀리초에 두 번 고쳐도 순서가 뒤집히지 않게. 한 번에 넣은 이벤트는 한 시각이다. */
function record(db: Database, id: number, ...inputs: AuditInput[]) {
  const list = (db.playMonthlyAudit[id] ??= []);
  const last = Math.max(0, ...list.map((e) => Date.parse(e.occurred_at)));
  const at = new Date(Math.max(Date.now(), last + 1));
  list.push(
    ...inputs.map(({ scope, ...e }): PlayMonthlyAuditEvent => ({
      // 키 순서는 서버 응답과 같다.
      type: e.type ?? "CREATED",
      occurred_at: at.toISOString(),
      scope,
      ...NONE,
      ...(e.actor ? { system_actor: null } : {}),
      ...e,
    })),
  );
}
export const listPlayMonthlyAudit = (id: number): PlayMonthlyAuditEvent[] =>
  structuredClone(read().playMonthlyAudit[id] ?? []);

/** 새 놀이 월간 하나. `confirmed` 면 같은 데이터의 확정본이다. */
export const addPlayMonthly = (classId: number, confirmed = false) =>
  commit((db) => {
    let n = 0;
    const cell = (value: string, ev: PlayMonthlyCell["evidence"]): PlayMonthlyCell => ({
      item_id: "item_" + String(++n).padStart(32, "0"),
      value,
      evidence: ev,
      generation: { ...GEN },
    });
    const parentEv = evidence("PARENT_PLAN", "parent-1", "m09_m11", "9월~11월");
    const rows = (label: string, ev: string): PlayMonthlyActivity[] =>
      [1, 2, 3, 4, 5].map((i) => {
        const name = cell(label + " " + i, curriculum(ev, ...(ev === "t.1" ? ["t.2"] : [])));
        return {
          activity_id: name.item_id,
          name,
          description: cell(label + " " + i + "을 설명해요.", name.evidence),
          content_ids: name.evidence.map((e) => e.source_id),
          parent_item_id: null,
        };
      });
    const now = new Date().toISOString();
    const plan: PlayMonthlyPlan = {
      id: db.next++,
      class_id: classId,
      school_year: 2026,
      month: 11,
      target_month: "2026-11",
      status: confirmed ? "CONFIRMED" : "DRAFT",
      revision: 1,
      format: "PLAY_MONTHLY",
      format_version: "play-monthly-layout-v0.1.0",
      created_at: now,
      confirmed_at: confirmed ? now : null,
      target_ages: [4, 5],
      weeks: [1, 2, 3, 4].map((w) => ({
        week_id: "2026-11-W" + w,
        label: "11월 " + w + "주",
        start_date: "2026-11-" + String(2 + 7 * (w - 1)).padStart(2, "0"),
        end_date: "2026-11-" + String(6 + 7 * (w - 1)).padStart(2, "0"),
        active: true,
      })),
      parent: {
        annual_plan_id: annualFor(classId)?.id ?? 0,
        period_key: "m09_m11",
        layout_version: "play-project-layout-v0.2.0",
        confirmed_at: now,
        plays: [9, 2, 4, 5, 7].map((i) => ({
          row_key: "cand" + i,
          play_name_item_id: "m09_m11-" + i + "-name",
          play_name: "m09_m11 놀이 " + i,
          materials: "종이 상자",
          support_direction: "자료를 더해 줍니다.",
          emphasized: false,
        })),
      },
      theme: cell("봄 길을 걸어요", parentEv),
      rationale: cell(
        "봄에는 바깥에서 새싹과 꽃을 만나는 놀이가 이어질 것으로 예상합니다.",
        parentEv,
      ),
      together: rows("함께 놀이", "t.1"),
      free_play: rows("자유놀이", "t.3"),
      habits: [1, 2, 3, 4].map((w) => ({
        week_id: "2026-11-W" + w,
        entry_id: "h" + w,
        cell: cell("합성 습관 " + w, curriculum("t.1")),
      })),
      safety_candidates: SAFETY.map(([kind, category_id, topic_group, text, name], i) => ({
        kind: kind as "STATUTORY" | "SUPPLEMENTAL",
        category_id,
        topic_group,
        cell: cell(
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
      safety_weeks: [1, 2, 3, 4].map((w) => ({
        week_id: "2026-11-W" + w,
        candidate_item_id: null,
      })),
      health: { entry_id: "he1", cell: cell("합성 건강 1", curriculum("t.2")) },
      nutrition: { entry_id: "nu1", cell: cell("합성 영양 1", curriculum("t.3")) },
      drill_candidates: DRILLS.map(([topic_id, label], i) => ({
        topic_id,
        label,
        cell: cell(i + 1 + "번째 상황을 가정해 대피 훈련을 해요", curriculum("t.4")),
      })),
      // 한 번도 쓰지 않은 교사 입력 칸 — 근거 없고 generation 이 null 이다.
      teacher_inputs: TEACHER_KEYS.map((key) => ({
        key,
        cell: { ...cell("", []), generation: null },
      })),
      notices: [],
    };
    db.playMonthlyPlans.push(plan);
    // 계획안 1건 + 칸마다 1건(서버 순서: 계획안 → 칸). 확정본이면 확정 한 건이 더 있다.
    record(
      db,
      plan.id,
      { scope: "PLAN" },
      ...playCells(plan).map((c) => ({ scope: "CELL" as const, item_id: c.item_id })),
    );
    if (confirmed) record(db, plan.id, { type: "CONFIRMED", scope: "PLAN", actor: ACTOR });
    return view(plan);
  });

/** 빈 칸 안내. 서버(play_monthly_notices)와 같은 규칙이고 응답마다 계산한다. */
function notices(p: PlayMonthlyPlan): PlayMonthlyPlan["notices"] {
  const text = (id: string) => p.safety_candidates.find((c) => c.cell.item_id === id)!.cell.value;
  return [
    ...p.safety_weeks
      .filter((w) => w.candidate_item_id === null || !text(w.candidate_item_id).trim())
      .map((w) => ({
        code: (w.candidate_item_id === null
          ? "SAFETY_UNPLACED"
          : "SAFETY_BLANK") as "SAFETY_UNPLACED",
        week_id: w.week_id,
      })),
    ...p.habits
      .filter((h) => !h.cell.value.trim())
      .map((h) => ({ code: "HABIT_BLANK" as const, week_id: h.week_id })),
    ...(p.health.cell.value.trim() ? [] : [{ code: "HEALTH_BLANK" as const, week_id: null }]),
    ...(p.nutrition.cell.value.trim() ? [] : [{ code: "NUTRITION_BLANK" as const, week_id: null }]),
  ];
}
/** 응답에 내지 않는 내부 값: 소방대피 칸이 마지막으로 복사한 후보의 item_id(서버는 이력의 `copied_from`). */
type Stored = PlayMonthlyPlan & { copied_from?: string };
const view = (p: PlayMonthlyPlan): PlayMonthlyPlan => {
  const copy = structuredClone(p) as Stored;
  delete copy.copied_from;
  return { ...copy, notices: notices(p) };
};

export const findPlayMonthly = (id: number) => {
  const p = read().playMonthlyPlans.find((x) => x.id === id);
  return p && view(p);
};
export const findPlayMonthlyFor = (classId: number, targetMonth: string) =>
  read().playMonthlyPlans.find((p) => p.class_id === classId && p.target_month === targetMonth);
export const listPlayMonthly = (classIds: number[]) =>
  read()
    .playMonthlyPlans.filter((p) => classIds.includes(p.class_id))
    .sort((a, b) => a.target_month.localeCompare(b.target_month) || a.id - b.id)
    .map(
      ({
        id,
        class_id,
        school_year,
        month,
        target_month,
        status,
        revision,
        created_at,
        confirmed_at,
      }) => ({
        id,
        class_id,
        school_year,
        month,
        target_month,
        status,
        revision,
        created_at,
        confirmed_at,
      }),
    );
export const removePlayMonthly = (id: number) =>
  commit((db) => {
    db.playMonthlyPlans = db.playMonthlyPlans.filter((p) => p.id !== id);
    delete db.playMonthlyAudit[id];
  });

/** 계획안의 모든 칸. 이 목록에 없는 item_id 는 404 다. */
export const playCells = (p: PlayMonthlyPlan): PlayMonthlyCell[] => [
  p.theme,
  p.rationale,
  ...[...p.together, ...p.free_play].flatMap((a) => [a.name, a.description]),
  ...p.habits.map((h) => h.cell),
  ...p.safety_candidates.map((c) => c.cell),
  p.health.cell,
  p.nutrition.cell,
  ...p.drill_candidates.map((d) => d.cell),
  ...p.teacher_inputs.map((t) => t.cell),
];
/**
 * 바뀌었으면 revision 을 올리고 `fn` 이 말한 이력을 남긴다. 같은 입력이면 그대로 두고 단건만 돌려준다
 * (서버: 200 · 무변경 · 이력 없음).
 */
const change = (
  id: number,
  fn: (p: PlayMonthlyPlan, log: (e: AuditInput) => void) => boolean,
  actor = ACTOR,
) =>
  commit((db) => {
    const p = db.playMonthlyPlans.find((x) => x.id === id)!;
    const events: AuditInput[] = [];
    if (fn(p, (e) => events.push({ actor, ...e }))) {
      p.revision++;
      record(db, id, ...events);
    }
    return view(p);
  });
/** 근거 · 생성 방식은 그대로다. 처음 쓰는 칸만 MANUAL 이 된다(교사 수정은 이력에만 남는다). */
export const editPlayMonthlyCell = (id: number, itemId: string, value: string) =>
  change(id, (p, log) => {
    const cell = playCells(p).find((c) => c.item_id === itemId)!;
    log({
      type: "TEACHER_EDITED",
      scope: "CELL",
      item_id: itemId,
      value_change: { before: cell.value, after: value },
    });
    cell.value = value;
    cell.generation ??= { method: "MANUAL", rule_id: null, rule_version: null };
    return true;
  });
const arranged = (scope: string, before: string[], after: string[]) => ({
  type: "ARRANGEMENT_CHANGED" as const,
  scope: "PLAN" as const,
  arrangement_change: { scope, before, after },
});
export const placePlayMonthlySafety = (id: number, weekId: string, candidate: string | null) =>
  change(id, (p, log) => {
    const week = p.safety_weeks.find((w) => w.week_id === weekId)!;
    const before = week.candidate_item_id;
    if (before === candidate) return false;
    week.candidate_item_id = candidate;
    log(arranged(weekId, before ? [before] : [], candidate ? [candidate] : []));
    return true;
  });
export const removePlayMonthlyActivity = (id: number, itemId: string) =>
  change(id, (p, log) => {
    for (const section of ["together", "free_play"] as const) {
      const rows = p[section];
      const at = rows.findIndex((a) => a.activity_id === itemId);
      if (at < 0) continue;
      const before = rows.map((a) => a.activity_id);
      rows.splice(at, 1);
      log(
        arranged(
          section,
          before,
          rows.map((a) => a.activity_id),
        ),
      );
    }
    return true;
  });
export const copyPlayMonthlyDrill = (id: number, itemId: string) =>
  change(id, (p, log) => {
    const from = p.drill_candidates.find((d) => d.cell.item_id === itemId)!.cell;
    const to = p.teacher_inputs.find((t) => t.key === TEACHER_KEYS[0])!.cell;
    const copied = {
      value: from.value,
      evidence: from.evidence,
      generation: { method: "RULE_ONLY", rule_id: DRILL_COPY, rule_version: p.format_version },
    };
    const sameOf = (c: Omit<PlayMonthlyCell, "item_id">, source?: string) =>
      JSON.stringify([c.value, c.evidence, c.generation, source]);
    // 서버처럼 값 · 근거 · 방식에 복사 원본 후보까지 같아야 같은 복사다 — 문장이 같은 다른 후보는 새 복사다.
    if (sameOf(to, (p as Stored).copied_from) === sameOf(copied, itemId)) return false;
    log({
      type: "CANDIDATE_COPIED",
      scope: "CELL",
      item_id: to.item_id,
      value_change: { before: to.value, after: copied.value },
      // 복사한 칸이 이미 쓰인 적이 있을 때만 온다.
      generation_change: to.generation ? { before: to.generation, after: copied.generation } : null,
      copied_from: itemId,
    });
    (p as Stored).copied_from = itemId;
    Object.assign(to, structuredClone(copied));
    return true;
  });

/** 서버 Core `confirm_problems` 의 위치 키. 비어 있으면 확정할 수 있다. */
export function playConfirmProblems(p: PlayMonthlyPlan): string[] {
  const blank = (c: PlayMonthlyCell) => !c.value.trim();
  return [
    ...(blank(p.theme) ? ["theme"] : []),
    ...(blank(p.rationale) ? ["rationale"] : []),
    ...(["together", "free_play"] as const).flatMap((section) => [
      ...(p[section].length ? [] : [section]),
      ...p[section].flatMap((a) => [
        ...(blank(a.name) ? [section + "." + a.activity_id] : []),
        ...(a.content_ids.length >= 1 && a.content_ids.length <= 3
          ? []
          : [section + "." + a.activity_id + ".content_ids"]),
      ]),
    ]),
  ];
}
/** 확정. 이미 확정이면(동시에 온 두 번째 확정) 저장된 그대로 돌려주고 아무것도 바꾸지 않는다. */
export const confirmPlayMonthly = (id: number) =>
  commit((db) => {
    const p = db.playMonthlyPlans.find((x) => x.id === id)!;
    if (p.status !== "CONFIRMED") {
      p.status = "CONFIRMED";
      p.confirmed_at = new Date().toISOString();
      p.revision++;
      record(db, id, { type: "CONFIRMED", scope: "PLAN", actor: ACTOR });
    }
    return view(p);
  });
