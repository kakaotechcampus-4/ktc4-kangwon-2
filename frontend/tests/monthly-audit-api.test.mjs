// 월간계획안 변경 이력 클라이언트와 MSW 목업 (docs/api-spec.md §9-5, BE-2 4aaa678).
// 이력은 목업의 생성 · 편집 · 재생성 · 확정을 실제로 불러 쌓는다 — 테스트가 이벤트를 지어내지
// 않는다(같은 시각 정렬 검사 하나만 저장된 시각을 맞춰 둔다). 실제 서버 · LLM 을 부르지 않는다.
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
const { addMonthly } = await import("../msw/data/monthly-plans.ts");
const { addReadyProfile, approveTemplateForTest } =
  await import("../msw/data/template-profiles.ts");
const { createCenter } = await import("../lib/api/centers.ts");
const { createClass } = await import("../lib/api/classes.ts");
const { createAnnualPlan, confirmAnnualPlan } = await import("../lib/api/plans.ts");
const {
  createMonthlyPlan,
  getMonthlyPlan,
  editMonthlyCell,
  regenerateMonthlyCell,
  confirmMonthlyPlan,
  getMonthlyPlanAudit,
} = await import("../lib/api/monthly.ts");
const {
  createTemplateProfile,
  putCenterDefaultProfile,
  putClassProfileOverride,
  getClassTemplateProfile,
} = await import("../lib/api/templateProfiles.ts");
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
  delete globalThis.window;
});

const FOCUS = {
  template_id: "ssuksak.monthly-template-a",
  template_version: "monthly-template-a-v0.2.1",
};
const INPUT = {
  base_template_ref: FOCUS,
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
const KEYS = [
  "type",
  "occurred_at",
  "scope",
  "item_id",
  "section_key",
  "week_id",
  "actor",
  "system_actor",
  "value_change",
  "generation_change",
];
const ACTOR = "user_1"; // 목업 계정 id (서버는 user_{users.id})

const rejects = (promise, status, code, fields) =>
  assert.rejects(promise, (e) => {
    assert.ok(e instanceof ApiError);
    assert.equal(e.status, status);
    assert.equal(e.body.error.code, code);
    assert.deepEqual(e.body.error.fields, fields);
    return true;
  });
const cellOf = (plan, key, index = 0) =>
  plan.sections.find((s) => s.section_key === key).cells[index];
const located = (plan) =>
  plan.sections.flatMap((s) => s.cells.map((c) => [c.item_id, s.section_key, c.week_id]));
const types = (items) => items.map((i) => [i.type, i.scope]);

/** 내 원(첫 원)의 반 · 확정된 연간 · READY Profile, 그리고 남의 원 월간 하나. */
async function world({ confirm = true } = {}) {
  const center = await createCenter({
    name: "가원",
    director_name: "원장",
    region_sido: "강원특별자치도",
    region_sigungu: "춘천시",
  });
  const other = await createCenter({
    name: "나원",
    director_name: "원장",
    region_sido: "강원특별자치도",
    region_sigungu: "원주시",
  });
  const klass = await createClass(center.id, {
    name: "햇살반",
    teacher_name: "교사",
    age_min: 3,
    age_max: 4,
    child_count: null,
  });
  const theirClass = await createClass(other.id, {
    name: "달빛반",
    teacher_name: "교사",
    age_min: 5,
    age_max: 5,
    child_count: null,
  });
  const annual = await createAnnualPlan({ class_id: klass.id, form_id: null });
  if (confirm) await confirmAnnualPlan(annual.id);
  const theirAnnual = await createAnnualPlan({ class_id: theirClass.id, form_id: null });
  await confirmAnnualPlan(theirAnnual.id);
  approveTemplateForTest(FOCUS);
  const ref = (await createTemplateProfile(center.id, INPUT)).profile_ref;
  const theirs = addMonthly(theirClass, theirAnnual, 9, addReadyProfile(other.id, INPUT));
  return { center: center.id, klass: klass.id, annual: annual.id, ref, theirs };
}
async function monthly(w) {
  return createMonthlyPlan({ class_id: w.klass, month: 9, profile_ref: w.ref });
}
const audit = async (id, itemId) => (await getMonthlyPlanAudit(id, itemId)).items;

// ── A. 클라이언트 ──────────────────────────────────────────────────────────

test("client: GET, query only when item_id is given (encoded), bearer, ApiError", async () => {
  const session = new Map([["saessak.authToken", "T0KEN"]]);
  const storage = {
    getItem: (k) => session.get(k) ?? null,
    setItem: (k, v) => session.set(k, v),
    removeItem: (k) => session.delete(k),
  };
  globalThis.window = { sessionStorage: storage, localStorage: storage };
  const calls = [];
  let reply = () =>
    new Response('{"items":[]}', { headers: { "Content-Type": "application/json" } });
  globalThis.fetch = async (url, options = {}) => {
    calls.push({
      url: String(url),
      method: options.method ?? "GET",
      body: options.body,
      auth: new Headers(options.headers).get("Authorization"),
    });
    return reply();
  };
  assert.deepEqual(await getMonthlyPlanAudit(7), { items: [] });
  await getMonthlyPlanAudit(7, "item/a b");
  await getMonthlyPlanAudit(7, "");
  assert.deepEqual(
    calls.map((c) => [c.method, c.url, c.body]),
    [
      ["GET", "/api/plans/monthly/7/audit", undefined],
      ["GET", "/api/plans/monthly/7/audit?item_id=item%2Fa%20b", undefined],
      // 빈 문자열은 서버처럼 「그런 칸 없음」(404) 이 되도록 그대로 보낸다.
      ["GET", "/api/plans/monthly/7/audit?item_id=", undefined],
    ],
  );
  assert.ok(calls.every((c) => c.auth === "Bearer T0KEN"));
  for (const [status, code, fields] of [
    [401, "UNAUTHENTICATED", []],
    [404, "NOT_FOUND", ["item_id"]],
  ]) {
    reply = () =>
      new Response(JSON.stringify({ error: { code, message: "x", fields } }), {
        status,
        headers: { "Content-Type": "application/json" },
      });
    await rejects(getMonthlyPlanAudit(7, "x"), status, code, fields);
  }
});

// ── B. 생성 ───────────────────────────────────────────────────────────────

test("create records one PLAN CREATED and one CREATED per cell; failed creates record nothing", async () => {
  const w = await world({ confirm: false });
  const before = structuredClone(read().monthlyAudit);
  const body = { class_id: w.klass, month: 9, profile_ref: w.ref };
  await rejects(createMonthlyPlan(body), 409, "GATE_BLOCKED", ["class_id"]);
  await confirmAnnualPlan(w.annual);
  const approved = read().approvedTemplates;
  commit((db) => {
    db.approvedTemplates = []; // 생성 직전 승인 재검사가 막는 경우
  });
  await rejects(createMonthlyPlan(body), 422, "VALIDATION_FAILED", ["profile_ref"]);
  assert.deepEqual(read().monthlyAudit, before);
  commit((db) => {
    db.approvedTemplates = approved;
  });

  const plan = await monthly(w);
  const items = await audit(plan.id);
  assert.ok(items.every((i) => JSON.stringify(Object.keys(i)) === JSON.stringify(KEYS)));
  assert.deepEqual(items[0], {
    type: "CREATED",
    occurred_at: items[0].occurred_at,
    scope: "PLAN",
    item_id: null,
    section_key: null,
    week_id: null,
    actor: null,
    system_actor: "monthly_application",
    value_change: null,
    generation_change: null,
  });
  const cells = items.slice(1);
  assert.deepEqual(
    cells.map((i) => [i.item_id, i.section_key, i.week_id]),
    located(plan),
  );
  assert.ok(cells.every((i) => i.type === "CREATED" && i.system_actor === "monthly_application"));
  assert.equal(items[0].occurred_at, plan.created_at);
  assert.ok(!Number.isNaN(Date.parse(items[0].occurred_at)) && items[0].occurred_at.endsWith("Z"));
  assert.deepEqual(await audit(plan.id), items);
});

// ── C. 교사 수정 ───────────────────────────────────────────────────────────

test("edit records TEACHER_EDITED on that cell only; rejected edits record nothing", async () => {
  const w = await world();
  const plan = await monthly(w);
  const target = cellOf(plan, "focus", 1);
  const start = await audit(plan.id);

  await rejects(
    editMonthlyCell(plan.id, target.item_id, target.value, 1),
    422,
    "VALIDATION_FAILED",
    ["value"],
  );
  await rejects(editMonthlyCell(plan.id, target.item_id, "x", 2), 409, "STALE_WRITE", [
    "expected_revision",
  ]);
  await rejects(editMonthlyCell(plan.id, "item_none", "x", 1), 404, "NOT_FOUND", ["item_id"]);
  await rejects(
    editMonthlyCell(w.theirs.id, cellOf(w.theirs, "focus").item_id, "x", 1),
    404,
    "NOT_FOUND",
    ["id"],
  );
  assert.deepEqual(await audit(plan.id), start);

  await editMonthlyCell(plan.id, target.item_id, "교사가 고친 소주제", 1);
  const items = await audit(plan.id);
  assert.deepEqual(items.slice(0, start.length), start);
  const [edited] = items.slice(start.length);
  assert.deepEqual(edited, {
    type: "TEACHER_EDITED",
    occurred_at: edited.occurred_at,
    scope: "CELL",
    item_id: target.item_id,
    section_key: "focus",
    week_id: target.week_id,
    actor: ACTOR,
    system_actor: null,
    value_change: { before: target.value, after: "교사가 고친 소주제" },
    generation_change: null,
  });
  assert.equal(items.length, start.length + 1);
});

// ── D. 재생성 ─────────────────────────────────────────────────────────────

test("regenerate records value and generation before/after; failures record nothing", async () => {
  const w = await world();
  const plan = await monthly(w);
  const target = cellOf(plan, "focus");
  const start = await audit(plan.id);

  const r = await fetch(
    "http://localhost/api/plans/monthly/" +
      plan.id +
      "/cells/" +
      target.item_id +
      "/regenerate?mockError=GENERATION_FAILED",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ expected_revision: 1 }),
    },
  );
  assert.equal(r.status, 500);
  await rejects(regenerateMonthlyCell(plan.id, target.item_id, 2), 409, "STALE_WRITE", [
    "expected_revision",
  ]);
  await rejects(
    regenerateMonthlyCell(plan.id, cellOf(plan, "theme").item_id, 1),
    422,
    "VALIDATION_FAILED",
    ["item_id"],
  );
  assert.deepEqual(await audit(plan.id), start);

  const changed = await regenerateMonthlyCell(plan.id, target.item_id, 1);
  const now = changed.sections.flatMap((s) => s.cells).find((c) => c.item_id === target.item_id);
  const regenerated = (await audit(plan.id)).filter((i) => i.type === "REGENERATED");
  assert.deepEqual(regenerated, [
    {
      type: "REGENERATED",
      occurred_at: regenerated[0].occurred_at,
      scope: "CELL",
      item_id: target.item_id,
      section_key: "focus",
      week_id: target.week_id,
      actor: ACTOR,
      system_actor: null,
      value_change: { before: target.value, after: now.value },
      generation_change: { before: target.generation, after: now.generation },
    },
  ]);
  assert.notDeepEqual(target.generation, now.generation);
});

// ── E. 확정 ───────────────────────────────────────────────────────────────

test("first confirm records PLAN CONFIRMED; re-confirm (policy B) records nothing", async () => {
  const w = await world();
  const plan = await monthly(w);
  const confirmed = await confirmMonthlyPlan(plan.id, 1);
  const items = await audit(plan.id);
  const last = items[items.length - 1];
  assert.deepEqual(
    [last.type, last.scope, last.actor, last.system_actor, last.item_id],
    ["CONFIRMED", "PLAN", ACTOR, null, null],
  );
  assert.equal(last.occurred_at, confirmed.confirmed_at);

  for (const stale of [1, 2, 9])
    assert.deepEqual(await confirmMonthlyPlan(plan.id, stale), confirmed);
  assert.deepEqual(await audit(plan.id), items);
  assert.equal((await getMonthlyPlan(plan.id)).revision, confirmed.revision);
  await rejects(
    editMonthlyCell(plan.id, cellOf(plan, "goals").item_id, "x", 2),
    409,
    "ALREADY_CONFIRMED",
    [],
  );
  await rejects(
    regenerateMonthlyCell(plan.id, cellOf(plan, "goals").item_id, 2),
    409,
    "ALREADY_CONFIRMED",
    [],
  );
  assert.deepEqual(await audit(plan.id), items);
});

// ── F. item_id 고르기 ──────────────────────────────────────────────────────

test("item_id filter: that cell + PLAN CONFIRMED only, never PLAN CREATED; unknown → 404", async () => {
  const w = await world();
  const plan = await monthly(w);
  const target = cellOf(plan, "focus", 0);
  const other = cellOf(plan, "focus", 1);
  await editMonthlyCell(plan.id, target.item_id, "첫 주", 1);
  await editMonthlyCell(plan.id, other.item_id, "둘째 주", 2);

  const draft = await audit(plan.id, target.item_id);
  assert.deepEqual(types(draft), [
    ["CREATED", "CELL"],
    ["TEACHER_EDITED", "CELL"],
  ]);
  assert.ok(draft.every((i) => i.item_id === target.item_id));

  await confirmMonthlyPlan(plan.id, 3);
  const confirmed = await audit(plan.id, target.item_id);
  assert.deepEqual(confirmed.slice(0, 2), draft);
  assert.deepEqual(types(confirmed.slice(2)), [["CONFIRMED", "PLAN"]]);

  await rejects(getMonthlyPlanAudit(plan.id, "item_none"), 404, "NOT_FOUND", ["item_id"]);
  await rejects(getMonthlyPlanAudit(plan.id, ""), 404, "NOT_FOUND", ["item_id"]);
  await rejects(getMonthlyPlanAudit(plan.id, cellOf(w.theirs, "focus").item_id), 404, "NOT_FOUND", [
    "item_id",
  ]);
});

// ── G. 순서 ───────────────────────────────────────────────────────────────

test("order: time ascending; on ties PLAN first, cells in plan order, stored order in a cell", async () => {
  const w = await world();
  const plan = await monthly(w);
  const focus = cellOf(plan, "focus");
  await editMonthlyCell(plan.id, focus.item_id, "고친 값", 1);
  await regenerateMonthlyCell(plan.id, focus.item_id, 2);
  await confirmMonthlyPlan(plan.id, 3);

  const items = await audit(plan.id);
  const times = items.map((i) => Date.parse(i.occurred_at));
  assert.deepEqual(
    times,
    [...times].sort((a, b) => a - b),
  );
  assert.deepEqual(types(items.slice(-3)), [
    ["TEACHER_EDITED", "CELL"],
    ["REGENERATED", "CELL"],
    ["CONFIRMED", "PLAN"],
  ]);

  // 같은 시각이면: 계획안 이벤트(저장 순서) → 칸(계획안 순서) → 한 칸 안은 저장 순서.
  commit((db) => {
    const a = db.monthlyAudit[plan.id];
    for (const e of [a.plan, ...Object.values(a.cells)].flat())
      e.occurred_at = "2026-10-10T00:00:00.000Z";
  });
  const tied = await audit(plan.id);
  assert.deepEqual(types(tied.slice(0, 2)), [
    ["CREATED", "PLAN"],
    ["CONFIRMED", "PLAN"],
  ]);
  const cellOrder = [...new Set(tied.slice(2).map((i) => i.item_id))];
  assert.deepEqual(
    cellOrder,
    located(plan).map(([id]) => id),
  );
  assert.deepEqual(
    tied.filter((i) => i.item_id === focus.item_id).map((i) => i.type),
    ["CREATED", "TEACHER_EDITED", "REGENERATED"],
  );
  assert.deepEqual(await audit(plan.id), tied);
});

// ── H. 원 단위 격리 ───────────────────────────────────────────────────────

test("isolation: other center, missing, annual id → 404 [id] before item_id; 401 via scenario", async () => {
  const w = await world();
  const plan = await monthly(w);
  const theirItem = cellOf(w.theirs, "focus").item_id;
  assert.ok((await audit(plan.id)).length > 0);
  await rejects(getMonthlyPlanAudit(w.theirs.id), 404, "NOT_FOUND", ["id"]);
  await rejects(getMonthlyPlanAudit(w.theirs.id, theirItem), 404, "NOT_FOUND", ["id"]);
  await rejects(getMonthlyPlanAudit(w.theirs.id, "item_none"), 404, "NOT_FOUND", ["id"]);
  await rejects(getMonthlyPlanAudit(999999), 404, "NOT_FOUND", ["id"]);
  await rejects(getMonthlyPlanAudit(w.annual), 404, "NOT_FOUND", ["id"]);
  // 목업은 토큰을 검증하지 않는다(handlers.ts 관례). 401 은 기존 시나리오 도구로 재현한다.
  const r = await fetch(
    "http://localhost/api/plans/monthly/" + plan.id + "/audit?mockError=UNAUTHENTICATED",
  );
  assert.equal(r.status, 401);
  assert.equal((await r.json()).error.code, "UNAUTHENTICATED");
});

// ── I. 조회는 저장소를 바꾸지 않는다 ───────────────────────────────────────

test("audit GET (full and filtered) leaves the whole mock store unchanged", async () => {
  const w = await world();
  const plan = await monthly(w);
  const focus = cellOf(plan, "focus");
  await editMonthlyCell(plan.id, focus.item_id, "고친 값", 1);
  await confirmMonthlyPlan(plan.id, 2);
  const snapshot = JSON.stringify(read());
  for (let i = 0; i < 3; i++) {
    await audit(plan.id);
    await audit(plan.id, focus.item_id);
  }
  await rejects(getMonthlyPlanAudit(plan.id, "item_none"), 404, "NOT_FOUND", ["item_id"]);
  assert.equal(JSON.stringify(read()), snapshot);
});

// ── J. 기존 흐름과 같은 저장소 ─────────────────────────────────────────────

test("profile → default → override → annual gate → create → edit → regenerate → confirm", async () => {
  const w = await world({ confirm: false });
  await putCenterDefaultProfile(w.center, { profile_ref: w.ref, expected_profile_ref: null });
  const second = (await createTemplateProfile(w.center, INPUT)).profile_ref;
  await putClassProfileOverride(w.klass, { profile_ref: second, expected_profile_ref: null });
  const resolved = await getClassTemplateProfile(w.klass);
  assert.equal(resolved.source, "CLASSROOM_OVERRIDE");
  const body = { class_id: w.klass, month: 10, profile_ref: resolved.profile_ref };
  await rejects(createMonthlyPlan(body), 409, "GATE_BLOCKED", ["class_id"]);
  await confirmAnnualPlan(w.annual);
  const plan = await createMonthlyPlan(body);
  assert.deepEqual(plan.profile_ref, second);
  const focus = cellOf(plan, "focus");
  const edited = await editMonthlyCell(plan.id, focus.item_id, "고친 값", 1);
  const regenerated = await regenerateMonthlyCell(plan.id, focus.item_id, edited.revision);
  const confirmed = await confirmMonthlyPlan(plan.id, regenerated.revision);
  assert.equal(confirmed.revision, 4);
  assert.deepEqual(types((await audit(plan.id)).filter((i) => i.type !== "CREATED")), [
    ["TEACHER_EDITED", "CELL"],
    ["REGENERATED", "CELL"],
    ["CONFIRMED", "PLAN"],
  ]);
});
