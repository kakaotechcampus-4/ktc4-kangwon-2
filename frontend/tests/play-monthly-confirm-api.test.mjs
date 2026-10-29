// 놀이 중심 월간 확정 · 변경 이력(POST confirm · GET audit)과 MSW 목업이 실제 서버 응답과 같은지.
// 기준: 서버를 실제로 찍은 응답(2026-10-28, play_monthly_confirm_responses) — 상태 · code · message · fields · 키를 옮겼다.
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
const { resetTestData, commit } = await import("../msw/data/store.ts");
const { addPlayMonthly, confirmPlayMonthly } = await import("../msw/data/play-monthly.ts");
const { createCenter } = await import("../lib/api/centers.ts");
const { createClass } = await import("../lib/api/classes.ts");
const pm = await import("../lib/api/playMonthly.ts");
const { ApiError, apiRequest } = await import("../lib/api/client.ts");

const server = setupServer(...handlers);
let mswFetch, calls;
before(() => {
  server.listen({ onUnhandledRequest: "error" });
  mswFetch = globalThis.fetch;
});
after(() => server.close());
beforeEach(() => {
  resetTestData();
  calls = [];
  globalThis.fetch = (url, options) => {
    calls.push({ method: options?.method ?? "GET", url: String(url), body: options?.body });
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
const NOT_FOUND = "월간계획안을 찾을 수 없습니다.";

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
/** 반 하나와 그 반의 놀이 월간(초안 · 11월) 하나. */
async function seeded(confirmed = false) {
  const klass = await newClass();
  const plan = addPlayMonthly(klass.id, confirmed);
  return { klass, plan, id: plan.id, rev: plan.revision };
}

const KEYS = [
  "type",
  "occurred_at",
  "scope",
  "item_id",
  "actor",
  "system_actor",
  "value_change",
  "generation_change",
  "link_change",
  "arrangement_change",
  "copied_from",
];
const post = (id, body) =>
  apiRequest("/api/plans/monthly/play/" + id + "/confirm", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
const audit = async (id) => (await pm.getPlayMonthlyAudit(id)).items;
const cellCount = (plan) => new Set(JSON.stringify(plan).match(/item_[0-9a-f]{32}/g)).size;

test("confirm: draft without a body is 422, a stale revision is 409, neither changes anything", async () => {
  const { id, rev } = await seeded();
  await rejects(post(id), 422, "VALIDATION_FAILED", INVALID, ["expected_revision"]);
  await rejects(post(id, { expected_revision: "1" }), 422, "VALIDATION_FAILED", INVALID, [
    "expected_revision",
  ]);
  await rejects(post(id, { expected_revision: 0 }), 422, "VALIDATION_FAILED", INVALID, [
    "expected_revision",
  ]);
  await rejects(pm.confirmPlayMonthly(id, rev + 5), 409, "STALE_WRITE", STALE, [
    "expected_revision",
  ]);
  assert.equal((await pm.getPlayMonthly(id)).status, "DRAFT");
  assert.equal(
    (await audit(id)).some((e) => e.type === "CONFIRMED"),
    false,
  );
});

test("confirm: lacking places come as dotted keys in the Core order", async () => {
  const { id, plan } = await seeded();
  let cur = await pm.editPlayMonthlyCell(id, plan.theme.item_id, "", 1);
  const row = cur.together[0];
  cur = await pm.editPlayMonthlyCell(id, row.name.item_id, "", cur.revision);
  commit((db) => {
    const p = db.playMonthlyPlans.find((x) => x.id === id);
    p.free_play[0].content_ids = ["a", "b", "c", "d"];
    p.together[1].content_ids = [];
  });
  await rejects(pm.confirmPlayMonthly(id, cur.revision), 422, "VALIDATION_FAILED", INVALID, [
    "theme",
    "together." + row.activity_id,
    "together." + plan.together[1].activity_id + ".content_ids",
    "free_play." + plan.free_play[0].activity_id + ".content_ids",
  ]);
  const same = await pm.getPlayMonthly(id);
  assert.equal(same.revision, cur.revision);
  assert.equal(same.status, "DRAFT");
});

test("confirm: ok is 200 with revision + 1, the same keys as a read, and CONFIRMED in the audit", async () => {
  const { id, rev } = await seeded();
  const read = await pm.getPlayMonthly(id);
  const done = await pm.confirmPlayMonthly(id, rev);
  assert.deepEqual(Object.keys(done), Object.keys(read));
  assert.equal(done.status, "CONFIRMED");
  assert.equal(done.revision, rev + 1);
  assert.match(done.confirmed_at, /Z$/);
  const last = (await audit(id)).at(-1);
  assert.equal(last.type, "CONFIRMED");
  assert.equal(last.scope, "PLAN");
  assert.equal(last.actor, "user_1");
  assert.equal(last.system_actor, null);
  assert.deepEqual(Object.keys(last), KEYS);
});

test("confirm: an already confirmed plan answers 200 as stored, with any or no body", async () => {
  const { id, rev } = await seeded();
  const done = await pm.confirmPlayMonthly(id, rev);
  assert.deepEqual(await pm.confirmPlayMonthly(id, 1), done);
  assert.deepEqual(await post(id), done);
  // 본문이 있는데 정수 1 이상이 아니면 확정본이어도 422 다.
  await rejects(post(id, { expected_revision: "3" }), 422, "VALIDATION_FAILED", INVALID, [
    "expected_revision",
  ]);
  assert.equal((await audit(id)).filter((e) => e.type === "CONFIRMED").length, 1);
});

test("after confirming, edits are 409 ALREADY_CONFIRMED and delete is 409 GATE_BLOCKED", async () => {
  const { id, rev, plan } = await seeded();
  const done = await pm.confirmPlayMonthly(id, rev);
  await rejects(
    pm.editPlayMonthlyCell(id, plan.theme.item_id, "확정 뒤", done.revision),
    409,
    "ALREADY_CONFIRMED",
    "확정된 계획안은 수정할 수 없습니다.",
    [],
  );
  await rejects(
    pm.deletePlayMonthly(id),
    409,
    "GATE_BLOCKED",
    "확정된 계획안은 지울 수 없습니다.",
    [],
  );
});

test("two confirms at once: both 200, one revision step, one CONFIRMED event", async () => {
  const { id, rev } = await seeded();
  const [a, b] = await Promise.all([
    pm.confirmPlayMonthly(id, rev),
    pm.confirmPlayMonthly(id, rev),
  ]);
  assert.deepEqual(a, b);
  assert.equal(a.revision, rev + 1);
  assert.equal((await audit(id)).filter((e) => e.type === "CONFIRMED").length, 1);
  // 핸들러가 본문을 읽는 사이 다른 확정이 먼저 끝난 경우 — 저장 계층도 다시 바꾸지 않는다.
  assert.deepEqual(confirmPlayMonthly(id), a);
});

test("confirm and audit: missing plan is 404, a legacy monthly id is 409, a bad path id is 422", async () => {
  await newClass();
  await rejects(pm.confirmPlayMonthly(999, 1), 404, "NOT_FOUND", NOT_FOUND, ["id"]);
  await rejects(pm.getPlayMonthlyAudit(999), 404, "NOT_FOUND", NOT_FOUND, ["id"]);
  await rejects(post("abc", { expected_revision: 1 }), 422, "VALIDATION_FAILED", INVALID, [
    "plan_id",
  ]);
});

test("audit: a new plan has one PLAN and one CELL CREATED per cell, all keys, same time", async () => {
  const { id, plan } = await seeded();
  const items = await audit(id);
  assert.equal(items.length, 1 + cellCount(plan));
  assert.deepEqual(Object.keys(items[0]), KEYS);
  assert.deepEqual(
    [items[0].type, items[0].scope, items[0].item_id, items[0].actor, items[0].system_actor],
    ["CREATED", "PLAN", null, null, "play_monthly_application"],
  );
  assert.ok(items.slice(1).every((e) => e.scope === "CELL" && /^item_/.test(e.item_id)));
  assert.equal(new Set(items.map((e) => e.occurred_at)).size, 1);
});

test("audit: each change adds events in order; no-change and failed requests add none", async () => {
  const { id, plan } = await seeded();
  const before = (await audit(id)).length;
  const week = plan.weeks[0].week_id;
  const safe = plan.safety_candidates[0].cell.item_id;
  const drill = plan.drill_candidates[0].cell.item_id;
  const oldTheme = plan.theme.value;

  let cur = await pm.editPlayMonthlyCell(id, plan.theme.item_id, "새 주제", 1);
  cur = await pm.placePlayMonthlySafety(id, week, safe, cur.revision);
  const same = await pm.placePlayMonthlySafety(id, week, safe, cur.revision); // 무변경
  assert.equal(same.revision, cur.revision);
  cur = await pm.copyPlayMonthlyDrill(id, drill, cur.revision);
  await pm.copyPlayMonthlyDrill(id, drill, cur.revision); // 무변경
  const together = plan.together.map((a) => a.activity_id);
  cur = await pm.removePlayMonthlyActivity(id, together[0], cur.revision);
  await rejects(
    pm.editPlayMonthlyCell(id, plan.theme.item_id, "새 주제", cur.revision),
    422,
    "VALIDATION_FAILED",
    INVALID,
    ["value"],
  );
  await rejects(
    pm.editPlayMonthlyCell(id, plan.theme.item_id, "다른", 1),
    409,
    "STALE_WRITE",
    STALE,
    ["expected_revision"],
  );

  const added = (await audit(id)).slice(before);
  assert.deepEqual(
    added.map((e) => e.type),
    ["TEACHER_EDITED", "ARRANGEMENT_CHANGED", "CANDIDATE_COPIED", "ARRANGEMENT_CHANGED"],
  );
  assert.ok(added.every((e) => Object.keys(e).join() === KEYS.join() && e.actor === "user_1"));
  assert.deepEqual(added[0].value_change, { before: oldTheme, after: "새 주제" });
  assert.equal(added[0].item_id, plan.theme.item_id);
  assert.deepEqual(added[1].arrangement_change, { scope: week, before: [], after: [safe] });
  assert.equal(added[2].copied_from, drill);
  assert.equal(added[2].value_change.before, "");
  assert.equal(added[2].generation_change, null); // 처음 쓰는 칸
  assert.deepEqual(added[3].arrangement_change, {
    scope: "together",
    before: together,
    after: together.slice(1),
  });
  const times = added.map((e) => Date.parse(e.occurred_at));
  assert.deepEqual(
    times,
    [...times].sort((a, b) => a - b),
  );
});
