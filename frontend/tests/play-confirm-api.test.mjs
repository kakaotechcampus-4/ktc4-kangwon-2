// 놀이 프로젝트형 확정 · 이력(POST confirm · GET audit)과 MSW 목업이 실제 서버 응답과 같은지.
// 기준: 서버를 실제로 찍은 응답(2026-10-28, play_confirm_responses) — 상태 · code · message · fields 를 그대로 옮겼다.
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
const { createCenter } = await import("../lib/api/centers.ts");
const { createClass } = await import("../lib/api/classes.ts");
const {
  createAnnualPlan,
  getAnnualPlan,
  getAnnualPlanAudit,
  savePlaySelection,
  editPlayCell,
  confirmPlayProject,
  confirmAnnualPlan,
} = await import("../lib/api/plans.ts");
const { ApiError, apiRequest } = await import("../lib/api/client.ts");

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

const rejects = (promise, status, code, message, fields) =>
  assert.rejects(promise, (e) => {
    assert.ok(e instanceof ApiError);
    assert.equal(e.status, status);
    assert.equal(e.body.error.code, code);
    assert.equal(e.body.error.message, message);
    assert.deepEqual(e.body.error.fields, fields);
    return true;
  });
const INVALID = "입력값을 확인해주세요.";
const STALE = "그 사이 다른 화면에서 계획안이 바뀌었습니다. 새로 불러온 뒤 다시 해주세요.";
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
async function newPlay() {
  return createAnnualPlan({
    class_id: (await newClass()).id,
    form_id: null,
    format: "PLAY_PROJECT",
  });
}
const post = (id, data) =>
  apiRequest("/api/plans/annual/" + id + "/confirm", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
const pick = (plan, counts) =>
  Object.fromEntries(
    plan.periods.map((p, i) => [
      p.period_key,
      p.candidates.slice(0, counts[i]).map((c) => c.row_key),
    ]),
  );
/** 네 구간을 counts 개씩 고른 계획안 (revision 이 그만큼 오른다). */
const picked = async (counts = [5, 5, 5, 5]) => {
  const plan = await newPlay();
  return savePlaySelection(plan.id, pick(plan, counts), plan.revision);
};

test("confirming returns the whole plan CONFIRMED at revision + 1", async () => {
  const plan = await picked();
  const done = await confirmPlayProject(plan.id, plan.revision);
  assert.equal(done.status, "CONFIRMED");
  assert.equal(done.revision, plan.revision + 1);
  assert.equal(done.format, "PLAY_PROJECT");
  assert.deepEqual(
    done.periods.map((p) => p.selected.length),
    [5, 5, 5, 5],
  );
  assert.deepEqual(await getAnnualPlan(plan.id), done);
});

test("confirming again is 200 with the same plan — without a body, and with an old revision", async () => {
  const plan = await picked();
  const done = await confirmPlayProject(plan.id, plan.revision);
  assert.deepEqual(await confirmAnnualPlan(plan.id), done);
  assert.deepEqual(await confirmPlayProject(plan.id, 1), done);
  assert.deepEqual(await confirmPlayProject(plan.id, plan.revision), done);
  const events = (await getAnnualPlanAudit(plan.id)).items;
  assert.equal(events.filter((e) => e.type === "CONFIRMED").length, 1);
});

test("a draft confirmed without a body is 422 on expected_revision", async () => {
  const plan = await picked();
  await rejects(confirmAnnualPlan(plan.id), 422, "VALIDATION_FAILED", INVALID, [
    "expected_revision",
  ]);
});

test("an old revision is 409 STALE_WRITE and nothing is confirmed", async () => {
  const plan = await picked();
  await rejects(confirmPlayProject(plan.id, plan.revision - 1), 409, "STALE_WRITE", STALE, [
    "expected_revision",
  ]);
  assert.equal((await getAnnualPlan(plan.id)).status, "DRAFT");
});

test("short periods are 422 with the period keys in period order, no prefix", async () => {
  const plan = await picked([5, 5, 3, 0]);
  await rejects(confirmPlayProject(plan.id, plan.revision), 422, "VALIDATION_FAILED", INVALID, [
    "m09_m11",
    "m12_m02",
  ]);
  assert.equal((await getAnnualPlan(plan.id)).status, "DRAFT");
});

test("a missing plan is 404", async () => {
  await rejects(confirmPlayProject(999, 1), 404, "NOT_FOUND", "계획안을 찾을 수 없습니다.", ["id"]);
});

test("after confirming, selecting or editing a cell is 409 ALREADY_CONFIRMED", async () => {
  const plan = await picked();
  const done = await confirmPlayProject(plan.id, plan.revision);
  const message = "확정된 계획안은 수정할 수 없습니다.";
  await rejects(
    savePlaySelection(plan.id, pick(done, [5, 5, 5, 5]), done.revision),
    409,
    "ALREADY_CONFIRMED",
    message,
    [],
  );
  await rejects(
    editPlayCell(
      plan.id,
      done.periods[0].candidates[0].play_name.item_id,
      "확정 뒤",
      done.revision,
    ),
    409,
    "ALREADY_CONFIRMED",
    message,
    [],
  );
});

test("the audit lists eight keys per event in time order, with CANDIDATES_SELECTED and CONFIRMED", async () => {
  const plan = await newPlay();
  const first = await savePlaySelection(plan.id, pick(plan, [5, 5, 3, 0]), plan.revision);
  const second = await savePlaySelection(plan.id, pick(plan, [5, 5, 5, 5]), first.revision);
  const edited = await editPlayCell(
    plan.id,
    second.periods[0].candidates[0].play_name.item_id,
    "고친 놀이",
    second.revision,
  );
  await confirmPlayProject(plan.id, edited.revision);
  const { items } = await getAnnualPlanAudit(plan.id);
  const keys = [
    "actor",
    "item_id",
    "month",
    "occurred_at",
    "selection_change",
    "system_actor",
    "type",
    "value_change",
  ];
  assert.ok(items.every((e) => JSON.stringify(Object.keys(e).sort()) === JSON.stringify(keys)));
  assert.ok(items.every((e) => e.month === null));
  const times = items.map((e) => Date.parse(e.occurred_at));
  assert.deepEqual(
    [...times].sort((a, b) => a - b),
    times,
  );
  assert.deepEqual(items[0], {
    type: "CREATED",
    occurred_at: items[0].occurred_at,
    month: null,
    actor: null,
    system_actor: "play_project_application",
    value_change: null,
    item_id: null,
    selection_change: null,
  });
  assert.equal(items.filter((e) => e.type === "CREATED").length, 161);
  const selected = items.filter((e) => e.type === "CANDIDATES_SELECTED");
  assert.deepEqual(
    selected.map((e) => [
      e.selection_change.period_key,
      e.selection_change.before.length,
      e.selection_change.after.length,
    ]),
    [
      ["m03_m05", 0, 5],
      ["m06_m08", 0, 5],
      ["m09_m11", 0, 3],
      ["m09_m11", 3, 5],
      ["m12_m02", 0, 5],
    ],
  );
  assert.ok(selected.every((e) => /^user_\d+$/.test(e.actor) && e.system_actor === null));
  const teacher = items.find((e) => e.type === "TEACHER_EDITED");
  assert.equal(teacher.item_id, second.periods[0].candidates[0].play_name.item_id);
  assert.equal(teacher.value_change.after, "고친 놀이");
  const confirmed = items.at(-1);
  assert.equal(confirmed.type, "CONFIRMED");
  assert.match(confirmed.actor, /^user_\d+$/);
});

test("the audit of a missing plan is 404", async () => {
  await rejects(getAnnualPlanAudit(999), 404, "NOT_FOUND", "계획안을 찾을 수 없습니다.", ["id"]);
});

test("two confirms sent at once confirm once: one CONFIRMED event and one revision bump", async () => {
  const plan = await picked();
  const [a, b] = await Promise.all([
    confirmPlayProject(plan.id, plan.revision),
    confirmPlayProject(plan.id, plan.revision),
  ]);
  assert.deepEqual(a, b);
  assert.equal(a.revision, plan.revision + 1);
  const { items } = await getAnnualPlanAudit(plan.id);
  assert.equal(items.filter((e) => e.type === "CONFIRMED").length, 1);
});

test("a given expected_revision that is not an integer >= 1 is 422 first, even on a confirmed plan", async () => {
  const plan = await picked();
  for (const wrong of ["4", true, 0, 3.5, -1])
    await rejects(post(plan.id, { expected_revision: wrong }), 422, "VALIDATION_FAILED", INVALID, [
      "expected_revision",
    ]);
  await confirmPlayProject(plan.id, plan.revision);
  for (const wrong of ["4", true, 0, 3.5])
    await rejects(post(plan.id, { expected_revision: wrong }), 422, "VALIDATION_FAILED", INVALID, [
      "expected_revision",
    ]);
  // 값이 없거나 null 이면 확정본은 200 이다.
  assert.equal((await post(plan.id, {})).status, "CONFIRMED");
  assert.equal((await post(plan.id, { expected_revision: null })).status, "CONFIRMED");
});
