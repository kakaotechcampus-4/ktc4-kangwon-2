// 연간 변경 이력 클라이언트와 MSW 목업. 모양은 develop 서버의 `AuditEventOut`(다섯 키)과 같다.
// 연간 선택 월 재생성은 넣지 않는다(PROV-Y-A). 실제 서버 · LLM · DB 를 부르지 않는다.
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
const { createAnnualPlan, putAnnualMonth, confirmAnnualPlan, getAnnualPlanAudit } = plans;

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
const KEYS = ["actor", "month", "occurred_at", "system_actor", "type"];
const SCHOOL_YEAR = [3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 1, 2];
const snapshot = () => structuredClone({ plans: read().plans, audit: read().annualAudit });

test("client: GET audit without a body", async () => {
  const plan = await newPlan();
  calls = [];
  await getAnnualPlanAudit(plan.id);
  assert.deepEqual(calls, [
    { path: `/api/plans/annual/${plan.id}/audit`, method: "GET", body: undefined },
  ]);
  assert.equal(typeof plans.regenerateAnnualMonth, "undefined");
});

test("audit: CREATED · TEACHER_EDITED · CONFIRMED with the server's five keys", async () => {
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
      { ...e, month: null },
      {
        type: "CREATED",
        occurred_at: items[0].occurred_at,
        month: null,
        actor: null,
        system_actor: "yearly_application",
      },
    );
  }
  await putAnnualMonth(plan.id, 10, { theme: "교사가 쓴 10월 주제", sub_themes: [] });
  const confirmed = await confirmAnnualPlan(plan.id);
  items = (await getAnnualPlanAudit(plan.id)).items;
  assert.equal(items.length, 15);
  const [edited, done] = items.slice(13);
  assert.deepEqual(edited, {
    type: "TEACHER_EDITED",
    occurred_at: edited.occurred_at,
    month: 10,
    actor: "user_1",
    system_actor: null,
  });
  assert.deepEqual(done, {
    type: "CONFIRMED",
    occurred_at: confirmed.confirmed_at,
    month: null,
    actor: "user_1",
    system_actor: null,
  });
  for (const e of items) assert.deepEqual(Object.keys(e).sort(), KEYS);
  // 시간순.
  const times = items.map((e) => Date.parse(e.occurred_at));
  assert.deepEqual(
    times,
    [...times].sort((a, b) => a - b),
  );
});

test("teacher edit keeps generation · records even when unchanged · no sub_themes in history", async () => {
  const plan = await newPlan();
  const march = plan.months[0];
  const saved = await putAnnualMonth(plan.id, 3, { theme: march.theme, sub_themes: ["놀이"] });
  assert.deepEqual(saved.generation, march.generation);
  const last = (await getAnnualPlanAudit(plan.id)).items.at(-1);
  assert.equal(last.type, "TEACHER_EDITED");
  assert.equal(last.month, 3);
  assert.ok(!JSON.stringify(last).includes("놀이"));
  assert.ok(!JSON.stringify(last).includes(march.theme));
});

test("refused PUT after confirm adds no audit event", async () => {
  const plan = await newPlan();
  await confirmAnnualPlan(plan.id);
  const before = snapshot();
  await rejects(
    putAnnualMonth(plan.id, 3, { theme: "확정 뒤 수정", sub_themes: [] }),
    409,
    "ALREADY_CONFIRMED",
    [],
  );
  assert.deepEqual(snapshot(), before);
});

test("401 · 404 [id]: unauthenticated, unknown plan, not an annual plan", async () => {
  const plan = await newPlan();
  commit((db) => db.monthlyPlans.push({ id: 500 }));
  const before = snapshot();
  mockQuery = { mockError: "UNAUTHENTICATED" };
  await rejects(getAnnualPlanAudit(plan.id), 401, "UNAUTHENTICATED", []);
  mockQuery = {};
  await rejects(getAnnualPlanAudit(999), 404, "NOT_FOUND", ["id"]);
  await rejects(getAnnualPlanAudit(500), 404, "NOT_FOUND", ["id"]);
  assert.deepEqual(snapshot(), before);
});

test("old mock data saved before FE-Y1: kept as is, empty audit", async () => {
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
    // 지우거나 고쳐 쓰지 않았다.
    assert.deepEqual(JSON.parse(values.get(key)), old);
  } finally {
    for (const k of ["window", "localStorage", "sessionStorage"]) delete globalThis[k];
  }
});
