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
const { createMonthlyPlan, confirmMonthlyPlan, getMonthlyPlan } =
  await import("../lib/api/monthly.ts");
const weekly = await import("../lib/api/weekly.ts");
const { ApiError } = await import("../lib/api/client.ts");
const { SECTION_LABELS, sectionName } = await import("../lib/weekly/section-labels.ts");

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
const sectionOf = (plan, key) => plan.sections.find((s) => s.section_key === key);

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
  const annual = await createAnnualPlan({ class_id: klass.id, form_id: null });
  await confirmAnnualPlan(annual.id);
  approveTemplateForTest(BASE);
  const ref = (await createTemplateProfile(center.id, PROFILE_INPUT)).profile_ref;
  let monthly = await createMonthlyPlan({ class_id: klass.id, month: 3, profile_ref: ref });
  if (confirm) monthly = await confirmMonthlyPlan(monthly.id, monthly.revision);
  return { center, klass, monthly: await getMonthlyPlan(monthly.id) };
}

test("클라이언트는 일곱 가지를 낸다 — 월간의 audit 은 아직 없다", () => {
  assert.deepEqual(Object.keys(weekly).sort(), [
    "confirmWeeklyPlan",
    "createWeeklyPlan",
    "deleteWeeklyPlan",
    "editWeeklyCell",
    "getWeeklyPlan",
    "listWeeklyPlans",
    "regenerateWeeklyCell",
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

test("G4 — 월간에 없는 주 주소는 거절한다. 주차를 주간이 다시 세지 않는다", async () => {
  const { klass } = await classWithMonthly();
  await rejects(
    weekly.createWeeklyPlan({ class_id: klass.id, week_id: "2026-03-W9" }),
    422,
    "VALIDATION_FAILED",
  );
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
  for (const key of ["family_link", "event_schedule", "special_program"]) {
    assert.equal(sectionOf(plan, key).teacher_input, true, key);
    assert.equal(cellOf(plan, key).value, "", key);
    assert.equal(cellOf(plan, key).generation, null, key);
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
  // WeekPeriod 는 월간 것 그대로고, 늘어나는 것은 표시 기간뿐이다 (§3-2).
  const monthEnd = monthly.weeks[0].end_date;
  assert.notEqual(plan.week_period.end_date, monthEnd);
});

test("확정하면 고칠 수 없고 지울 수도 없다 — 확정 취소가 없다", async () => {
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
  await rejects(weekly.deleteWeeklyPlan(plan.id), 409, "GATE_BLOCKED");
});

test("칸 이름표는 열두 칸을 모두 덮고, 월간의 옛 키(habits)는 쓰지 않는다", () => {
  assert.equal(Object.keys(SECTION_LABELS).length, 12);
  assert.ok(!("habits" in SECTION_LABELS));
  assert.equal(SECTION_LABELS.basic_habit, "기본생활습관");
  // 모르는 키는 지어내지 않는다 — 서버가 준 이름을 그대로 쓴다.
  assert.equal(sectionName("unknown_key", "서버 이름"), "서버 이름");
  assert.equal(sectionName("unknown_key"), "unknown_key");
});
