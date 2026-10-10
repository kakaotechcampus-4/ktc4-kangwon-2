// 연간 선택 월 재생성 · 변경 이력 클라이언트와 MSW 목업 (docs/api-spec.md §7-1, 잠정 재생성 계약은
// docs/provisional-policy-decisions.md 부록 · backend 0d255a9). 실제 서버 · LLM · DB 를 부르지 않는다.
// 저장 충돌 · 503 · 500 은 목업의 mockError 로 만든 응답이다 — 동시성 자체는 backend PostgreSQL 테스트가 본다.
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
const { resetTestData, read, commit } = await import("../msw/data/store.ts");
const { resetScenarioFailures } = await import("../msw/scenarios.ts");
const { createCenter } = await import("../lib/api/centers.ts");
const { createClass } = await import("../lib/api/classes.ts");
const plans = await import("../lib/api/plans.ts");
const { ApiError } = await import("../lib/api/client.ts");
const {
  createAnnualPlan,
  getAnnualPlan,
  putAnnualMonth,
  confirmAnnualPlan,
  regenerateAnnualMonth,
  getAnnualPlanAudit,
} = plans;

const server = setupServer(...handlers);
let mswFetch, calls, mockQuery;
before(() => {
  server.listen({ onUnhandledRequest: "error" });
  mswFetch = globalThis.fetch;
});
after(() => server.close());
beforeEach(() => {
  resetTestData();
  calls = [];
  mockQuery = {};
  globalThis.fetch = (url, options = {}) => {
    const u = new URL(url, "http://localhost");
    u.searchParams.set("mockDelay", "0");
    for (const [k, v] of Object.entries(mockQuery)) u.searchParams.set(k, v);
    calls.push({ path: u.pathname, method: options.method ?? "GET", body: options.body });
    return mswFetch(u.href, options);
  };
});
afterEach(() => {
  globalThis.fetch = mswFetch;
  resetScenarioFailures();
});

const rejects = (promise, status, code, fields) =>
  assert.rejects(promise, (e) => {
    assert.ok(e instanceof ApiError);
    assert.equal(e.status, status);
    assert.equal(e.body.error.code, code);
    assert.deepEqual(e.body.error.fields, fields);
    return true;
  });
async function newPlan() {
  const center = await createCenter({
    name: "검증 원",
    director_name: "원장",
    region_sido: "충청북도",
    region_sigungu: "충주시",
  });
  const klass = await createClass(center.id, {
    name: "반",
    teacher_name: "교사",
    age_min: 3,
    age_max: 4,
    child_count: null,
  });
  return createAnnualPlan({ class_id: klass.id, form_id: null });
}
const KEYS = [
  "actor",
  "generation_change",
  "month",
  "occurred_at",
  "system_actor",
  "type",
  "value_change",
];
const SCHOOL_YEAR = [3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 1, 2];
const snapshot = () => structuredClone({ plans: read().plans, audit: read().annualAudit });

test("client: POST without a body to the regenerate path · GET audit", async () => {
  const plan = await newPlan();
  calls = [];
  const month = await regenerateAnnualMonth(plan.id, 5);
  await getAnnualPlanAudit(plan.id);
  assert.deepEqual(calls, [
    { path: `/api/plans/annual/${plan.id}/months/5/regenerate`, method: "POST", body: undefined },
    { path: `/api/plans/annual/${plan.id}/audit`, method: "GET", body: undefined },
  ]);
  // 응답은 PUT 과 같은 그 달 객체(MonthOut)다.
  assert.deepEqual(Object.keys(month).sort(), Object.keys(plan.months[2]).sort());
  assert.equal(month.month, 5);
});

test("regenerate changes only that month and GET shows the same result", async () => {
  const plan = await newPlan();
  const before = plan.months.find((m) => m.month === 5);
  const month = await regenerateAnnualMonth(plan.id, 5);
  assert.ok(month.theme.trim());
  // 서버 Core 처럼 지금 주제와 다른 후보 — 근거 id 가 바뀐다. 생성 방식은 같은 rule 이다.
  assert.equal(month.evidence.length, 1);
  assert.equal(month.evidence[0].source_type, "THEME_REFERENCE");
  assert.notEqual(month.evidence[0].source_id, before.evidence[0].source_id);
  assert.deepEqual(month.generation, before.generation);
  assert.deepEqual(month.sub_themes, []);
  assert.equal(month.source_type, undefined);
  const reloaded = await getAnnualPlan(plan.id);
  assert.deepEqual(
    reloaded.months.find((m) => m.month === 5),
    month,
  );
  assert.deepEqual(
    reloaded.months.filter((m) => m.month !== 5),
    plan.months.filter((m) => m.month !== 5),
  );
  assert.equal(reloaded.status, "DRAFT");
  assert.deepEqual(reloaded.checks, plan.checks);
});

test("audit: CREATED · TEACHER_EDITED · REGENERATED · CONFIRMED with the server null contract", async () => {
  const plan = await newPlan();
  let { items } = await getAnnualPlanAudit(plan.id);
  // 생성: 계획안 1건 + 달마다 1건, 같은 시각 — 계획안 다음 3월 ~ 익년 2월.
  assert.equal(items.length, 13);
  assert.deepEqual(
    items.map((e) => e.month),
    [null, ...SCHOOL_YEAR],
  );
  for (const e of items) {
    assert.deepEqual(Object.keys(e).sort(), KEYS);
    assert.deepEqual(
      { ...e, occurred_at: items[0].occurred_at, month: null },
      {
        type: "CREATED",
        occurred_at: items[0].occurred_at,
        month: null,
        actor: null,
        system_actor: "yearly_application",
        value_change: null,
        generation_change: null,
      },
    );
  }
  const original = plan.months.find((m) => m.month === 10);
  await putAnnualMonth(plan.id, 10, { theme: "교사가 쓴 10월 주제", sub_themes: [] });
  const regenerated = await regenerateAnnualMonth(plan.id, 10);
  const confirmed = await confirmAnnualPlan(plan.id);
  items = (await getAnnualPlanAudit(plan.id)).items;
  assert.deepEqual(
    items.slice(13).map((e) => [e.type, e.month]),
    [
      ["TEACHER_EDITED", 10],
      ["REGENERATED", 10],
      ["CONFIRMED", null],
    ],
  );
  const [edited, again, done] = items.slice(13);
  assert.deepEqual(edited, {
    ...edited,
    actor: "user_1",
    system_actor: null,
    value_change: { before: original.theme, after: "교사가 쓴 10월 주제" },
    generation_change: null,
  });
  // 교사가 고친 주제도 바뀌고(PROV-Y-B, 잠정) 고친 문구는 before 에 남는다.
  assert.deepEqual(again, {
    ...again,
    actor: "user_1",
    system_actor: null,
    value_change: { before: "교사가 쓴 10월 주제", after: regenerated.theme },
    generation_change: { before: original.generation, after: regenerated.generation },
  });
  assert.deepEqual(done, {
    ...done,
    actor: "user_1",
    system_actor: null,
    value_change: null,
    generation_change: null,
  });
  assert.equal(done.occurred_at, confirmed.confirmed_at);
  // 시간순.
  const times = items.map((e) => Date.parse(e.occurred_at));
  assert.deepEqual(
    times,
    [...times].sort((a, b) => a - b),
  );
  // 재확정: 같은 응답, 이벤트 없음.
  assert.deepEqual(await confirmAnnualPlan(plan.id), confirmed);
  assert.deepEqual((await getAnnualPlanAudit(plan.id)).items, items);
});

test("teacher edit keeps generation · records the theme even when unchanged · no sub_themes history", async () => {
  const plan = await newPlan();
  const march = plan.months[0];
  const saved = await putAnnualMonth(plan.id, 3, { theme: march.theme, sub_themes: ["놀이"] });
  assert.deepEqual(saved.generation, march.generation);
  const last = (await getAnnualPlanAudit(plan.id)).items.at(-1);
  assert.deepEqual(last.value_change, { before: march.theme, after: march.theme });
  assert.ok(!JSON.stringify(last).includes("놀이"));
});

test("sub_themes: meaningful → 422 [sub_themes] · blank-only counts as none", async () => {
  const plan = await newPlan();
  await putAnnualMonth(plan.id, 4, { theme: "4월", sub_themes: ["  ", "봄 꽃"] });
  let before = snapshot();
  await rejects(regenerateAnnualMonth(plan.id, 4), 422, "VALIDATION_FAILED", ["sub_themes"]);
  assert.deepEqual(snapshot(), before);
  await putAnnualMonth(plan.id, 6, { theme: "6월", sub_themes: ["", "   "] });
  const month = await regenerateAnnualMonth(plan.id, 6);
  // 서버처럼 읽은 소주제 그대로 돌려준다.
  assert.deepEqual(month.sub_themes, ["", "   "]);
  before = snapshot();
  assert.equal(before.audit[plan.id].at(-1).type, "REGENERATED");
});

test("confirmed plan → 409 ALREADY_CONFIRMED · nothing changes", async () => {
  const plan = await newPlan();
  await confirmAnnualPlan(plan.id);
  const before = snapshot();
  await rejects(regenerateAnnualMonth(plan.id, 3), 409, "ALREADY_CONFIRMED", []);
  assert.deepEqual(snapshot(), before);
});

test("mocked failures (STALE_WRITE · 503 · 500 · 401) leave plan and audit unchanged", async () => {
  const plan = await newPlan();
  const before = snapshot();
  for (const [code, status] of [
    ["STALE_WRITE", 409],
    ["DEPENDENCY_UNAVAILABLE", 503],
    ["LLM_BUDGET_EXCEEDED", 503],
    ["GENERATION_FAILED", 500],
    ["UNAUTHENTICATED", 401],
  ]) {
    mockQuery = { mockError: code };
    await rejects(regenerateAnnualMonth(plan.id, 3), status, code, []);
    assert.deepEqual(snapshot(), before);
  }
  mockQuery = { mockError: "UNAUTHENTICATED" };
  await rejects(getAnnualPlanAudit(plan.id), 401, "UNAUTHENTICATED", []);
  // 실패 한 번 뒤 다시 누르면 된다(mockFailures 는 그 횟수만 실패시킨다). 자동 재시도는 없다.
  mockQuery = { mockError: "GENERATION_FAILED", mockFailures: "1" };
  await rejects(regenerateAnnualMonth(plan.id, 3), 500, "GENERATION_FAILED", []);
  assert.equal(calls.filter((c) => c.path.endsWith("/regenerate")).length, 6);
  assert.equal((await regenerateAnnualMonth(plan.id, 3)).month, 3);
});

test("404 fields: unknown plan [id] · not an annual plan [id] · unknown month [month]", async () => {
  const plan = await newPlan();
  commit((db) => db.monthlyPlans.push({ id: 500 }));
  const before = snapshot();
  await rejects(regenerateAnnualMonth(999, 3), 404, "NOT_FOUND", ["id"]);
  await rejects(regenerateAnnualMonth(500, 3), 404, "NOT_FOUND", ["id"]);
  await rejects(regenerateAnnualMonth(plan.id, 13), 404, "NOT_FOUND", ["month"]);
  await rejects(getAnnualPlanAudit(999), 404, "NOT_FOUND", ["id"]);
  await rejects(getAnnualPlanAudit(500), 404, "NOT_FOUND", ["id"]);
  assert.deepEqual(snapshot(), before);
});

test("old mock data saved before FE-Y1: kept as is, empty audit, regenerate refused", async () => {
  // 브라우저 저장소 경로로 읽는다 — 옛 저장본에는 annualAudit 키도, 근거 · 생성 방식도 없다.
  const values = new Map();
  const shim = {
    getItem: (k) => values.get(k) ?? null,
    setItem: (k, v) => values.set(k, String(v)),
    removeItem: (k) => values.delete(k),
  };
  Object.assign(globalThis, {
    window: { localStorage: shim, sessionStorage: shim, location: { search: "" } },
    localStorage: shim,
    sessionStorage: shim,
  });
  const old = {
    next: 78,
    centers: [],
    classes: [],
    children: [],
    plans: [
      {
        id: 77,
        class_id: 1,
        school_year: 2026,
        status: "DRAFT",
        months: SCHOOL_YEAR.map((month) => ({
          month,
          theme: "옛 주제",
          sub_themes: [],
          source_type: "TEMPLATE",
          citation: { label: "옛 자료", url: null },
        })),
      },
    ],
  };
  const key = "saessak.mswSS.v1:anonymous";
  values.set(key, JSON.stringify(old));
  try {
    assert.deepEqual(read().annualAudit, {});
    assert.deepEqual(await getAnnualPlanAudit(77), { items: [] });
    await rejects(regenerateAnnualMonth(77, 3), 422, "VALIDATION_FAILED", ["id"]);
    // 지우거나 고쳐 쓰지 않았다.
    assert.deepEqual(JSON.parse(values.get(key)), old);
  } finally {
    for (const k of ["window", "localStorage", "sessionStorage"]) delete globalThis[k];
  }
});
