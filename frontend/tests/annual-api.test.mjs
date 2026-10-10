// 연간계획안 클라이언트와 MSW 목업이 서버 계약(docs/api-spec.md §4 ~ §7, backend 0d255a9)과 같은지.
// 실제 서버 · LLM 을 부르지 않는다. 문구 · id 는 목업 고정값이라 모양과 규칙만 본다.
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
const { resetTestData, read } = await import("../msw/data/store.ts");
const { createCenter } = await import("../lib/api/centers.ts");
const { createClass } = await import("../lib/api/classes.ts");
const { createAnnualPlan, listAnnualPlans, getAnnualPlan, putAnnualMonth, confirmAnnualPlan } =
  await import("../lib/api/plans.ts");
const { ApiError } = await import("../lib/api/client.ts");

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
});

const rejects = (promise, status, code, fields) =>
  assert.rejects(promise, (e) => {
    assert.ok(e instanceof ApiError);
    assert.equal(e.status, status);
    assert.equal(e.body.error.code, code);
    assert.deepEqual(e.body.error.fields, fields);
    return true;
  });
async function newClass() {
  const center = await createCenter({
    name: "검증 원",
    director_name: "원장",
    region_sido: "충청북도",
    region_sigungu: "충주시",
  });
  return createClass(center.id, {
    name: "반",
    teacher_name: "교사",
    age_min: 3,
    age_max: 4,
    child_count: null,
  });
}
const MONTH_KEYS = [
  "evidence",
  "generation",
  "month",
  "safety_education",
  "safety_education_state",
  "sub_themes",
  "theme",
];

test("create · get return the server shape (§4)", async () => {
  const klass = await newClass();
  const plan = await createAnnualPlan({ class_id: klass.id, form_id: null });
  assert.deepEqual(Object.keys(plan).sort(), [
    "checked_rules",
    "checks",
    "class_id",
    "id",
    "months",
    "school_year",
    "status",
  ]);
  assert.equal(plan.status, "DRAFT");
  assert.equal(plan.school_year, klass.school_year);
  assert.deepEqual(
    plan.months.map((m) => m.month),
    [3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 1, 2],
  );
  for (const m of plan.months) {
    assert.deepEqual(Object.keys(m).sort(), MONTH_KEYS);
    assert.ok(m.theme.trim());
    assert.deepEqual(m.sub_themes, []);
    assert.deepEqual(m.safety_education, []);
    assert.equal(m.safety_education_state, "SOURCE_REQUIRED");
    assert.equal(m.evidence.length, 1);
    assert.equal(m.evidence[0].source_type, "THEME_REFERENCE");
    assert.equal(m.evidence[0].effective_date, null);
    assert.equal(m.generation.method, "RULE_LLM");
    assert.ok(m.generation.rule_id && m.generation.rule_version);
  }
  // 빈 checks 를 「통과」로 읽지 않도록 무엇을 봤는지가 따로 온다. P0 는 6구분 × (주기 · 시수).
  assert.deepEqual(plan.checked_rules, ["legal_hours"]);
  assert.equal(plan.checks.length, 12);
  for (const c of plan.checks)
    assert.deepEqual(
      { ...c, detail: typeof c.detail },
      {
        rule: "legal_hours",
        severity: "UNVERIFIED",
        detail: "string",
        month: null,
      },
    );
  // 단건 응답에는 시각이 없다 — 저장소에만 있다.
  assert.deepEqual(await getAnnualPlan(plan.id), plan);
  assert.ok(read().plans[0].created_at);
});

test("one annual plan per class: 409 ALREADY_EXISTS · nothing added", async () => {
  const klass = await newClass();
  await createAnnualPlan({ class_id: klass.id, form_id: null });
  await rejects(createAnnualPlan({ class_id: klass.id, form_id: null }), 409, "ALREADY_EXISTS", [
    "class_id",
  ]);
  await rejects(createAnnualPlan({ class_id: 999, form_id: null }), 404, "NOT_FOUND", ["class_id"]);
  assert.equal(read().plans.length, 1);
});

test("list gives stored created_at · confirmed_at, newest first", async () => {
  const a = await createAnnualPlan({ class_id: (await newClass()).id, form_id: null });
  const b = await createAnnualPlan({ class_id: (await newClass()).id, form_id: null });
  const confirmed = await confirmAnnualPlan(a.id);
  const { items } = await listAnnualPlans();
  assert.deepEqual(
    items.map((p) => p.id),
    [b.id, a.id],
  );
  const stored = read().plans;
  for (const item of items) {
    const row = stored.find((p) => p.id === item.id);
    assert.equal(item.created_at, row.created_at);
    assert.equal(item.confirmed_at, row.confirmed_at);
  }
  assert.equal(items[1].confirmed_at, confirmed.confirmed_at);
  assert.equal(items[0].confirmed_at, null);
  // 같은 목록을 두 번 불러도 시각이 바뀌지 않는다.
  assert.deepEqual((await listAnnualPlans()).items, items);
  assert.deepEqual((await listAnnualPlans(a.class_id)).items, [items[1]]);
  await rejects(listAnnualPlans(999), 404, "NOT_FOUND", ["class_id"]);
});

test("PUT replaces theme · sub_themes and keeps evidence · generation (§6)", async () => {
  const plan = await createAnnualPlan({ class_id: (await newClass()).id, form_id: null });
  const before = plan.months.find((m) => m.month === 4);
  const saved = await putAnnualMonth(plan.id, 4, { theme: "고친 주제", sub_themes: ["놀이"] });
  assert.deepEqual(saved, { ...before, theme: "고친 주제", sub_themes: ["놀이"] });
  assert.equal(saved.source_type, undefined);
  const reloaded = await getAnnualPlan(plan.id);
  assert.deepEqual(
    reloaded.months.find((m) => m.month === 4),
    saved,
  );
  // 다른 달은 그대로다.
  assert.deepEqual(
    reloaded.months.filter((m) => m.month !== 4),
    plan.months.filter((m) => m.month !== 4),
  );
});

test("PUT errors follow the server order and fields", async () => {
  const plan = await createAnnualPlan({ class_id: (await newClass()).id, form_id: null });
  const snapshot = structuredClone(read().plans);
  await rejects(putAnnualMonth(plan.id, 3, { theme: "x" }), 422, "VALIDATION_FAILED", [
    "sub_themes",
  ]);
  await rejects(
    putAnnualMonth(plan.id, 3, { theme: "", sub_themes: [] }),
    422,
    "VALIDATION_FAILED",
    ["theme"],
  );
  await rejects(
    putAnnualMonth(plan.id, 3, { theme: "x", sub_themes: [], extra: 1 }),
    422,
    "VALIDATION_FAILED",
    ["extra"],
  );
  // 공백만 있는 주제는 Core 가 거절한다 — fields 없음.
  await rejects(
    putAnnualMonth(plan.id, 3, { theme: "   ", sub_themes: [] }),
    422,
    "VALIDATION_FAILED",
    [],
  );
  await rejects(putAnnualMonth(999, 3, { theme: "x", sub_themes: [] }), 404, "NOT_FOUND", ["id"]);
  await rejects(putAnnualMonth(plan.id, 13, { theme: "x", sub_themes: [] }), 404, "NOT_FOUND", [
    "month",
  ]);
  assert.deepEqual(read().plans, snapshot);
});

test("confirm: 200 · idempotent re-call · confirmed PUT is 409 ALREADY_CONFIRMED (§6 · §7)", async () => {
  const plan = await createAnnualPlan({ class_id: (await newClass()).id, form_id: null });
  // 서버는 빈 소주제로 확정을 막지 않는다 — 생성 직후(소주제 []) 바로 확정된다.
  const first = await confirmAnnualPlan(plan.id);
  assert.deepEqual(Object.keys(first).sort(), ["confirmed_at", "id", "status"]);
  assert.equal(first.status, "CONFIRMED");
  const snapshot = structuredClone(read());
  assert.deepEqual(await confirmAnnualPlan(plan.id), first);
  assert.deepEqual(read(), snapshot);
  assert.equal((await getAnnualPlan(plan.id)).status, "CONFIRMED");
  await rejects(
    putAnnualMonth(plan.id, 3, { theme: "금지", sub_themes: [] }),
    409,
    "ALREADY_CONFIRMED",
    [],
  );
  assert.deepEqual(read(), snapshot);
  await rejects(confirmAnnualPlan(999), 404, "NOT_FOUND", ["id"]);
});
