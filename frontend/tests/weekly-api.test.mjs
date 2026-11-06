// 주간계획안 API 클라이언트와 MSW 목업 계약 (docs/weekly-plan-contract.md §13).
// 월간과 다른 네 가지만 집중해서 본다 — Gate · 한 Section 한 칸 · 교사 입력 칸 · 토요일.
import { test, before, after, beforeEach, afterEach } from "node:test";
import assert from "node:assert/strict";
import { registerHooks } from "node:module";
import { existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
registerHooks({
  resolve(spec, ctx, next) {
    if (spec.startsWith(".") && ctx.parentURL) {
      const u = new URL(spec + ".ts", ctx.parentURL);
      if (existsSync(fileURLToPath(u))) return { url: u.href, shortCircuit: true };
    }
    return next(spec, ctx);
  },
});
const { setupServer } = await import("msw/node");
const { handlers } = await import("../msw/handlers.ts");
const { resetTestData } = await import("../msw/data/store.ts");
const { putCenterSettings } = await import("../msw/data/centers.ts");
const { approveTemplateForTest } = await import("../msw/data/template-profiles.ts");
const { createTemplateProfile } = await import("../lib/api/templateProfiles.ts");
const { createCenter } = await import("../lib/api/centers.ts");
const { createClass } = await import("../lib/api/classes.ts");
const { createAnnualPlan, confirmAnnualPlan } = await import("../lib/api/plans.ts");
const {
  createMonthlyPlan,
  confirmMonthlyPlan,
  getMonthlyPlan,
  placeMonthlySafety,
  deleteMonthlyPlan,
} = await import("../lib/api/monthly.ts");
const weekly = await import("../lib/api/weekly.ts");
const { ApiError } = await import("../lib/api/client.ts");
const { SECTION_LABELS, sectionName } = await import("../lib/weekly/section-labels.ts");
const { readFileSync } = await import("node:fs");
const { fileURLToPath: toPath } = await import("node:url");

const ROUTER = toPath(
  new URL("../../backend/app/features/plans/weekly_router.py", import.meta.url),
);
const SCHEMAS = toPath(
  new URL("../../backend/app/features/plans/weekly_schemas.py", import.meta.url),
);

const BASE = {
  template_id: "ssuksak.monthly-template-a",
  template_version: "monthly-template-a-v0.2.1",
};
const PROFILE_INPUT = {
  base_template_ref: BASE,
  selected_optional_keys: ["focus", "goals"],
  display_labels: {
    theme: "주제",
    week_axis: "주",
    outdoor_play: "바깥놀이",
    safety_education: "안전교육",
    focus: "소주제",
    goals: "목표",
  },
  focus_variant: "SUBTHEME",
};

const server = setupServer(...handlers);
let mswFetch;
before(() => {
  server.listen({ onUnhandledRequest: "error" });
  mswFetch = globalThis.fetch;
});
after(() => server.close());
beforeEach(() => {
  resetTestData();
  globalThis.fetch = (url, options) => {
    const u = new URL(url, "http://localhost");
    u.searchParams.set("mockDelay", "0");
    return mswFetch(u.href, options);
  };
});
afterEach(() => {
  globalThis.fetch = mswFetch;
  delete globalThis.window;
});

const rejects = (promise, status, code) =>
  assert.rejects(promise, (e) => {
    assert.ok(e instanceof ApiError);
    assert.equal(e.status, status);
    assert.equal(e.body.error.code, code);
    return true;
  });
const cellOf = (plan, key) => plan.sections.find((s) => s.section_key === key).cells[0];

/** 반 · 연간 확정까지. 월간은 테스트마다 확정할지 말지를 고른다 (G3 를 보기 위해). */
async function classWithMonthly({ confirm = true, saturday = false } = {}) {
  const center = await createCenter({
    name: "검증 원",
    director_name: "원장",
    region_sido: "충청북도",
    region_sigungu: "충주시",
  });
  if (saturday) putCenterSettings(center.id, { weekly_saturday_enabled: true });
  const klass = await createClass(center.id, {
    name: "반",
    teacher_name: "교사",
    age_min: 3,
    age_max: 5,
    child_count: null,
  });
  const annual = await createAnnualPlan({
    class_id: klass.id,
    form_id: null,
    format: "MONTHLY_THEME",
  });
  await confirmAnnualPlan(annual.id);
  approveTemplateForTest(BASE);
  const ref = (await createTemplateProfile(center.id, PROFILE_INPUT)).profile_ref;
  let monthly = await createMonthlyPlan({ class_id: klass.id, month: 3, profile_ref: ref });
  if (confirm) monthly = await confirmMonthlyPlan(monthly.id, monthly.revision);
  return { center, klass, monthly: await getMonthlyPlan(monthly.id) };
}

test("서버에 있는 경로만 쓰고, 아직 없는 경로는 알고 쓴다", () => {
  const router = readFileSync(ROUTER, "utf8");
  // 서버가 지금 내는 경로. 이게 바뀌면 여기가 먼저 깨진다.
  assert.ok(router.includes('@router.post("", response_model=WeeklyPlanOut'));
  assert.ok(router.includes('@router.get("", response_model=WeeklyPlanListOut'));
  assert.ok(router.includes('@router.get("/{plan_id}"'));
  assert.ok(router.includes('@router.delete("/{plan_id}"'));
  // W5b 로 생긴 것. 화면의 「준비 중」 안내는 걷었다.
  assert.ok(router.includes('"/{plan_id}/cells/{item_id}"'), "칸 편집");
  assert.ok(router.includes('"/{plan_id}/cells/{item_id}/regenerate"'), "칸 재생성");
  assert.ok(router.includes('"/{plan_id}/confirm"'), "확정");
});

test("month 는 달력 달 1~12 다 — YYYY-MM 을 보내면 422 다", () => {
  const router = readFileSync(ROUTER, "utf8");
  assert.ok(router.includes("month: int | None = None"));
  assert.ok(router.includes("not 1 <= month <= 12"));
});

test("응답 칸 이름이 화면이 읽는 것과 같다", () => {
  const schemas = readFileSync(SCHEMAS, "utf8");
  for (const field of [
    "week_id",
    "target_month",
    "week_period",
    "operating_days",
    "display_end_date",
    "parent_snapshots",
    "generation",
  ])
    assert.ok(schemas.includes(field + ":"), field);
  // 교사 입력 칸 표시는 서버가 준다 (W5b). 화면은 generation 으로 추론하지 않는다.
  assert.ok(schemas.includes("teacher_input:"), "teacher_input");
});

test("클라이언트는 후보 복사와 칸 분할·삭제 · 확정 취소까지 낸다", () => {
  assert.deepEqual(Object.keys(weekly).sort(), [
    "addWeeklyIndoorPlay",
    "confirmWeeklyPlan",
    "copyWeeklyActivity",
    "createWeeklyPlan",
    "deleteWeeklyPlan",
    "downloadWeeklyHwpx",
    "editWeeklyCell",
    "getWeeklyPlan",
    "getWeeklyPlanAudit",
    "listWeeklyPlans",
    "orderWeeklyIndoorPlays",
    "regenerateWeeklyCell",
    "removeWeeklyActivityCell",
    "removeWeeklyIndoorPlay",
    "splitWeeklyActivityCell",
    "unconfirmWeeklyPlan",
  ]);
});

test("G3 — 월간이 확정되기 전에는 주간을 만들 수 없다", async () => {
  const { klass, monthly } = await classWithMonthly({ confirm: false });
  await rejects(
    weekly.createWeeklyPlan({ class_id: klass.id, week_id: monthly.weeks[0].week_id }),
    409,
    "GATE_BLOCKED",
  );
});

test("후보형 주간 — 빈 요일 칸에 유형별 후보를 넣고 나눈 칸을 다시 조회한다", async () => {
  const { klass, monthly } = await classWithMonthly();
  let plan = await weekly.createWeeklyPlan({
    class_id: klass.id,
    week_id: monthly.weeks[0].week_id,
    activity_candidates: true,
  });
  assert.equal(plan.activity_candidates.length, 10);
  const group = (p) => p.sections.find((section) => section.section_key === "group_activity").cells;
  assert.ok(group(plan).every((cell) => !cell.value));
  const itemId = group(plan)[0].item_id;
  const candidate = plan.activity_candidates[0];
  plan = await weekly.copyWeeklyActivity(plan.id, itemId, candidate.cell.item_id, plan.revision);
  assert.equal(group(plan)[0].value, `[${candidate.activity_type}] ${candidate.name}`);
  const revision = plan.revision;
  plan = await weekly.copyWeeklyActivity(plan.id, itemId, candidate.cell.item_id, revision);
  assert.equal(plan.revision, revision);
  plan = await weekly.splitWeeklyActivityCell(plan.id, itemId, "VERTICAL", plan.revision);
  const added = group(plan)[1].item_id;
  assert.equal(group(plan)[0].item_id, itemId);
  assert.equal(group(plan)[1].value, "");
  assert.equal((await weekly.getWeeklyPlan(plan.id)).activity_grids[0].children.length, 2);
  await rejects(weekly.removeWeeklyActivityCell(plan.id, added, 0), 422, "VALIDATION_FAILED");
  plan = await weekly.removeWeeklyActivityCell(plan.id, added, plan.revision);
  assert.equal(plan.activity_grids[0].cell_id, itemId);
});

test("G4 — 월간에 없는 주 주소는 거절한다. 주차를 주간이 다시 세지 않는다", async () => {
  const { klass } = await classWithMonthly();
  await rejects(
    weekly.createWeeklyPlan({ class_id: klass.id, week_id: "2026-03-W9" }),
    422,
    "VALIDATION_FAILED",
  );
});

test("자유놀이 후보는 여러 개를 넣고 고치고 순서를 바꾼 뒤 마지막까지 뺄 수 있다", async () => {
  const { klass, monthly } = await classWithMonthly();
  let plan = await weekly.createWeeklyPlan({
    class_id: klass.id,
    week_id: monthly.weeks[0].week_id,
    indoor_play_candidates: true,
  });
  const rows = (p) => p.sections.find((s) => s.section_key === "indoor_play").cells;
  const candidates = plan.activity_candidates.filter((c) => c.section_key === "indoor_play");
  assert.equal(plan.indoor_play_selection, true);
  assert.equal(rows(plan)[0].value, "");
  plan = await weekly.addWeeklyIndoorPlay(plan.id, candidates[0].cell.item_id, plan.revision);
  const first = rows(plan)[0].item_id;
  assert.equal(rows(plan)[0].value, `[${candidates[0].activity_type}] ${candidates[0].name}`);
  plan = await weekly.addWeeklyIndoorPlay(plan.id, candidates[1].cell.item_id, plan.revision);
  plan = await weekly.editWeeklyCell(plan.id, first, "고친 자유놀이", plan.revision);
  const revision = plan.revision;
  plan = await weekly.addWeeklyIndoorPlay(plan.id, candidates[0].cell.item_id, plan.revision);
  assert.equal(plan.revision, revision);
  assert.equal(rows(plan)[0].value, "고친 자유놀이");
  const ids = rows(plan)
    .map((cell) => cell.item_id)
    .reverse();
  plan = await weekly.orderWeeklyIndoorPlays(plan.id, ids, plan.revision);
  assert.deepEqual(
    rows(plan).map((cell) => cell.item_id),
    ids,
  );
  await rejects(
    weekly.orderWeeklyIndoorPlays(plan.id, [first, first], plan.revision),
    422,
    "VALIDATION_FAILED",
  );
  const group = plan.activity_candidates.find((c) => c.section_key !== "indoor_play");
  await rejects(
    weekly.addWeeklyIndoorPlay(plan.id, group.cell.item_id, plan.revision),
    422,
    "VALIDATION_FAILED",
  );
  await rejects(
    weekly.regenerateWeeklyCell(plan.id, first, plan.revision),
    422,
    "VALIDATION_FAILED",
  );
  for (const id of ids) plan = await weekly.removeWeeklyIndoorPlay(plan.id, id, plan.revision);
  assert.equal(rows(plan).length, 1);
  assert.equal(rows(plan)[0].value, "");
  assert.deepEqual(rows(await weekly.getWeeklyPlan(plan.id)), rows(plan));
});

test("자유놀이 패널은 종류별 후보와 선택 목록을 구분하고 저장 대기·확정 상태에서 잠긴다", async () => {
  const { createRequire } = await import("node:module");
  const require = createRequire(import.meta.url);
  const source = readFileSync(
    new URL("../components/workspace/WeeklyIndoorPlayPanel.tsx", import.meta.url),
    "utf8",
  );
  const code = require("next/dist/compiled/babel/core").transformSync(source, {
    filename: "WeeklyIndoorPlayPanel.tsx",
    babelrc: false,
    configFile: false,
    presets: [
      [require("next/dist/compiled/babel/preset-env"), { targets: { node: "current" } }],
      [require("next/dist/compiled/babel/preset-react"), { runtime: "automatic" }],
      require("next/dist/compiled/babel/preset-typescript"),
    ],
  }).code;
  const jsx = (type, props) => ({ type, props });
  const panelModule = { exports: {} };
  new Function("require", "module", "exports", code)(
    (name) =>
      name === "react/jsx-runtime"
        ? { jsx, jsxs: jsx }
        : // 그 밖의 모듈은 class 문자열 (SMALL 은 이름, BUTTON.quiet 는 「quiet」) · 끌기 받는 곳.
          {
            SMALL: "small",
            DROP: "",
            GRIP: null,
            dropTo: (fn, prefix) => ({
              drop: (data) => data.startsWith(prefix) && fn(data.slice(prefix.length)),
            }),
            BUTTON: new Proxy({}, { get: (_, key) => String(key) }),
          },
    panelModule,
    panelModule.exports,
  );
  const Panel = panelModule.exports.default;
  const selected = [
    { item_id: "one", value: "[역할놀이] 가게 놀이" },
    { item_id: "two", value: "[쌓기놀이] - 길 만들기" },
  ];
  const plan = {
    status: "DRAFT",
    indoor_play_selection: true,
    sections: [{ section_key: "indoor_play", cells: selected }],
    activity_candidates: [
      {
        section_key: "indoor_play",
        activity_type: "역할놀이",
        name: "가게 놀이",
        cell: { item_id: "candidate", value: "가게 놀이: 말을 주고받습니다." },
      },
      {
        section_key: "group_activity",
        activity_type: "음률",
        name: "집단 활동",
        cell: { item_id: "group", value: "숨길 집단 후보" },
      },
    ],
  };
  const calls = [];
  const props = {
    plan,
    disabled: false,
    onAdd: (id) => calls.push(id),
    onOrder: (ids) => calls.push(ids),
    onRemove: (id) => calls.push(id),
  };
  const all = (node) =>
    Array.isArray(node)
      ? node.flatMap(all)
      : node && typeof node === "object"
        ? [node, ...all(node.props?.children)]
        : [];
  const text = (node) =>
    Array.isArray(node)
      ? node.map(text).join("")
      : node && typeof node === "object"
        ? text(node.props?.children)
        : typeof node === "string"
          ? node
          : "";
  const tree = Panel(props);
  assert.equal(text(tree).includes("숨길 집단 후보"), false);
  const buttons = all(tree).filter((n) => n.type === "button");
  const byLabel = (label) => buttons.find((n) => n.props["aria-label"] === label);
  // 넣은 후보는 서버가 옮겨 쓴 「[종류] 이름」(옛 「[종류] - 이름」도)으로 알아보고 후보 목록에서 뺀다(PM 2026-11-06). 빼면 다시 보인다.
  assert.equal(byLabel("이번 주 놀이에 넣기: 가게 놀이"), undefined);
  const without = all(
    Panel({
      ...props,
      plan: { ...plan, sections: [{ section_key: "indoor_play", cells: selected.slice(1) }] },
    }),
  );
  const put = without.find((n) => n.props?.["aria-label"] === "이번 주 놀이에 넣기: 가게 놀이");
  assert.equal(text(put), "+ 넣기");
  put.props.onClick();
  byLabel("1번 놀이 빼기").props.onClick();
  // 점선 빈칸의 「+」 — 빈 줄이 없으면 직접 쓸 칸을 더한다.
  byLabel("직접 쓸 놀이 더하기").props.onClick();
  // 「+」로 더한 빈 줄도 목록에 보이고, 누르면 「칸 편집」으로 연다.
  const blankRow = { item_id: "new", value: "" };
  all(
    Panel({
      ...props,
      onWrite: (id) => calls.push("write:" + id),
      plan: { ...plan, sections: [{ section_key: "indoor_play", cells: [...selected, blankRow] }] },
    }),
  )
    .find((n) => n.props?.["aria-label"] === "3번 놀이 직접 쓰기")
    .props.onClick();
  // 끌기 — 후보는 넣은 목록에, 넣은 줄은 다른 줄 자리로 · 후보 쪽에 놓으면 뺀다.
  const drops = all(Panel(props)).filter((n) => n.props?.drop);
  drops[0].props.drop("weekly-indoor:candidate");
  drops[1].props.drop("weekly-indoor-row:two"); // 「one」 줄에 「two」를 놓는다
  assert.deepEqual(calls, ["candidate", "one", null, "write:new", "candidate", ["two", "one"]]);
  assert.ok(
    all(Panel({ ...props, disabled: true }))
      .filter((n) => n.type === "button")
      .every((n) => n.props.disabled),
  );
  assert.equal(Panel({ ...props, plan: { ...plan, status: "CONFIRMED" } }), null);
  assert.equal(Panel({ ...props, plan: { ...plan, indoor_play_selection: false } }), null);
});

test("G5 — 같은 반 같은 주는 한 번만 만든다", async () => {
  const { klass, monthly } = await classWithMonthly();
  const weekId = monthly.weeks[0].week_id;
  await weekly.createWeeklyPlan({ class_id: klass.id, week_id: weekId });
  await rejects(
    weekly.createWeeklyPlan({ class_id: klass.id, week_id: weekId }),
    409,
    "ALREADY_EXISTS",
  );
});

test("안전교육은 월간에서 그 주에 놓은 후보를 복사한다 — 안 놓은 주는 빈칸", async () => {
  const { klass, monthly: draft } = await classWithMonthly({ confirm: false });
  const [w1, w2] = draft.weeks;
  const source = draft.safety_candidates[0].cell;
  let monthly = await placeMonthlySafety(draft.id, w1.week_id, source.item_id, draft.revision);
  monthly = await confirmMonthlyPlan(monthly.id, monthly.revision);
  const safety = (plan) => plan.sections.find((s) => s.section_key === "safety_education").cells[0];
  const copied = safety(await weekly.createWeeklyPlan({ class_id: klass.id, week_id: w1.week_id }));
  assert.equal(copied.value, monthly.safety_weeks[0].display_value);
  assert.equal(copied.state, "FILLED");
  assert.equal(copied.generation.method, "RULE_ONLY");
  assert.equal(copied.generation.rule_id, "weekly.safety.parent_placement");
  assert.deepEqual(copied.parent_snapshots, [
    { parent_item_id: source.item_id, snapshot_value: source.value },
  ]);
  const blank = safety(await weekly.createWeeklyPlan({ class_id: klass.id, week_id: w2.week_id }));
  assert.equal(blank.value, "");
  assert.equal(blank.state, "EMPTY_UNRESOLVED");
});

test("Section 마다 칸이 하나다 — 주차 열이 없다", async () => {
  const { klass, monthly } = await classWithMonthly();
  const plan = await weekly.createWeeklyPlan({
    class_id: klass.id,
    week_id: monthly.weeks[0].week_id,
  });
  assert.equal(plan.sections.length, 12);
  for (const section of plan.sections) assert.equal(section.cells.length, 1);
  // 주간 칸에는 week_id 가 없다. 계획안 자체가 한 주다.
  assert.ok(plan.sections.every((s) => !("week_id" in s.cells[0])));
});

test("교사 입력 칸 셋은 만들지 않는다 — generation 이 null 이고 다시 만들 수 없다", async () => {
  const { klass, monthly } = await classWithMonthly();
  const plan = await weekly.createWeeklyPlan({
    class_id: klass.id,
    week_id: monthly.weeks[0].week_id,
  });
  // 응답에 teacher_input 같은 칸이 없다. 만든 적이 없으면 generation 이 null 이다 (§10-2).
  for (const key of ["family_link", "event_schedule", "special_program"]) {
    assert.equal(cellOf(plan, key).value, "", key);
    assert.equal(cellOf(plan, key).generation, null, key);
  }
  // 생성한 칸은 반드시 generation 을 들고 온다 — 둘이 섞이면 화면이 못 가른다.
  for (const key of ["theme", "goals", "outdoor_play"]) {
    assert.ok(cellOf(plan, key).generation, key);
  }
  await rejects(
    weekly.regenerateWeeklyCell(plan.id, cellOf(plan, "family_link").item_id, plan.revision),
    422,
    "VALIDATION_FAILED",
  );
});

test("교사가 처음 쓰면 그때 MANUAL 이 된다", async () => {
  const { klass, monthly } = await classWithMonthly();
  const plan = await weekly.createWeeklyPlan({
    class_id: klass.id,
    week_id: monthly.weeks[0].week_id,
  });
  const item = cellOf(plan, "family_link").item_id;
  const next = await weekly.editWeeklyCell(plan.id, item, "금요일 알림장", plan.revision);
  const cell = next.sections.flatMap((s) => s.cells).find((c) => c.item_id === item);
  assert.equal(cell.value, "금요일 알림장");
  assert.equal(cell.generation.method, "MANUAL");
});

test("놀이 주제를 비우면 확정할 수 없다", async () => {
  const { klass, monthly } = await classWithMonthly();
  let plan = await weekly.createWeeklyPlan({
    class_id: klass.id,
    week_id: monthly.weeks[0].week_id,
  });
  plan = await weekly.editWeeklyCell(plan.id, cellOf(plan, "theme").item_id, "", plan.revision);
  await rejects(weekly.confirmWeeklyPlan(plan.id, plan.revision), 422, "VALIDATION_FAILED");
});

test("토요일을 켜면 표시 기간이 하루 늘고 요일이 여섯이다", async () => {
  const { klass, monthly } = await classWithMonthly({ saturday: true });
  const plan = await weekly.createWeeklyPlan({
    class_id: klass.id,
    week_id: monthly.weeks[0].week_id,
  });
  assert.equal(plan.operating_days.length, 6);
  assert.equal(plan.operating_days.at(-1), "SAT");
  // **WeekPeriod 는 늘 금요일이다.** 늘어나는 것은 표시 기간(display_end_date)뿐이다 (§3-2).
  assert.equal(plan.week_period.end_date, monthly.weeks[0].end_date);
  assert.notEqual(plan.display_end_date, plan.week_period.end_date);
});

test("확정하면 고칠 수 없고, 지우는 것은 된다(ADR-064) · 주간이 딸린 월간은 409 IN_USE", async () => {
  const { klass, monthly } = await classWithMonthly();
  let plan = await weekly.createWeeklyPlan({
    class_id: klass.id,
    week_id: monthly.weeks[0].week_id,
  });
  plan = await weekly.confirmWeeklyPlan(plan.id, plan.revision);
  assert.equal(plan.status, "CONFIRMED");
  await rejects(
    weekly.editWeeklyCell(plan.id, cellOf(plan, "goals").item_id, "바뀐 값", plan.revision),
    409,
    "ALREADY_CONFIRMED",
  );
  await rejects(deleteMonthlyPlan(monthly.id), 409, "IN_USE");
  await weekly.deleteWeeklyPlan(plan.id);
  await deleteMonthlyPlan(monthly.id);
});

test("칸 이름표는 열두 칸을 모두 덮고, 월간의 옛 키(habits)는 쓰지 않는다", () => {
  assert.equal(Object.keys(SECTION_LABELS).length, 12);
  assert.ok(!("habits" in SECTION_LABELS));
  assert.equal(SECTION_LABELS.basic_habit, "기본생활습관");
  // 모르는 키는 지어내지 않는다 — 서버가 준 이름을 그대로 쓴다.
  assert.equal(sectionName("unknown_key", "서버 이름"), "서버 이름");
  assert.equal(sectionName("unknown_key"), "unknown_key");
});

test("서버 경로가 아직 없으면 「준비 중」으로 읽는다 — 「잠시 후 다시」가 아니다", async () => {
  // 우리가 낸 404 는 공통 봉투를 달고 온다. 아예 없는 경로는 FastAPI 기본 {"detail": ...} 다.
  const enveloped = new ApiError(404, {
    error: { code: "NOT_FOUND", message: "없어요", fields: [] },
  });
  const missingRoute = new ApiError(404, { detail: "Not Found" });
  const notBuiltYet = (e) =>
    e instanceof ApiError &&
    e.status === 404 &&
    !(typeof e.body === "object" && e.body !== null && "error" in e.body);
  assert.equal(notBuiltYet(enveloped), false);
  assert.equal(notBuiltYet(missingRoute), true);
});
