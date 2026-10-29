// 고른 놀이 저장 API(PUT /api/plans/annual/{id}/selection)와 MSW 목업이 실제 서버 응답과 같은지.
// 기준: 서버 ② 를 실제로 찍은 응답(2026-10-28) — 상태 · code · message · fields 를 그대로 옮겼다.
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
const { createCenter } = await import("../lib/api/centers.ts");
const { createClass } = await import("../lib/api/classes.ts");
const { createAnnualPlan, getAnnualPlan, savePlaySelection, isSaveConflict } =
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

const KEYS = ["m03_m05", "m06_m08", "m09_m11", "m12_m02"];
const none = () => Object.fromEntries(KEYS.map((key) => [key, []]));
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

test("a new play plan starts at revision 1 with empty selections and item_ids shaped like the server's", async () => {
  const plan = await newPlay();
  assert.equal(plan.revision, 1);
  assert.deepEqual(
    plan.periods.map((p) => p.selected),
    [[], [], [], []],
  );
  const ids = plan.periods.flatMap((p) =>
    p.candidates.flatMap((c) =>
      [c.play_name, c.materials, c.support_direction, c.learning].map((cell) => cell.item_id),
    ),
  );
  assert.equal(ids.length, 160);
  assert.ok(ids.every((id) => /^item_[0-9a-f]{32}$/.test(id)));
  assert.equal(new Set(ids).size, 160);
});

test("saving a selection returns the whole plan at revision + 1, and a reload sees it", async () => {
  const plan = await newPlay();
  const saved = await savePlaySelection(
    plan.id,
    { ...none(), m03_m05: ["cand5", "cand1"] },
    plan.revision,
  );
  assert.equal(saved.revision, 2);
  assert.deepEqual(saved.periods[0].selected, ["cand5", "cand1"]);
  assert.equal(saved.periods.length, 4);
  assert.equal(saved.periods[0].candidates.length, 10);
  assert.deepEqual(await getAnnualPlan(plan.id), saved);
});

test("the same selection is 200 and keeps the revision", async () => {
  const plan = await newPlay();
  const selections = { ...none(), m03_m05: ["cand5", "cand1"] };
  await savePlaySelection(plan.id, selections, 1);
  const again = await savePlaySelection(plan.id, selections, 2);
  assert.equal(again.revision, 2);
});

test("an old revision is 409 STALE_WRITE and nothing is saved", async () => {
  const plan = await newPlay();
  await savePlaySelection(plan.id, { ...none(), m03_m05: ["cand5"] }, 1);
  await rejects(
    savePlaySelection(plan.id, { ...none(), m03_m05: ["cand5", "cand1"] }, 1),
    409,
    "STALE_WRITE",
    STALE,
    ["expected_revision"],
  );
  assert.deepEqual((await getAnnualPlan(plan.id)).periods[0].selected, ["cand5"]);
});

test("schema errors are 422 VALIDATION_FAILED naming selections.<period>", async () => {
  const plan = await newPlay();
  const bad = (selections, fields, revision = 1) =>
    rejects(
      savePlaySelection(plan.id, selections, revision),
      422,
      "VALIDATION_FAILED",
      INVALID,
      fields,
    );
  const missing = none();
  delete missing.m12_m02;
  await bad(missing, ["selections.m12_m02"]);
  await bad({ ...none(), unknown_period: [] }, ["selections.unknown_period"]);
  const six = ["cand1", "cand2", "cand3", "cand4", "cand5", "cand6"];
  await bad({ ...none(), m06_m08: six }, ["selections.m06_m08"]);
  await bad({ ...none(), m06_m08: ["cand1", "cand1"] }, ["selections.m06_m08"]);
  await bad(none(), ["expected_revision"], "1");
  await bad(none(), ["expected_revision"], 0);
});

test("a row_key that is not a candidate of that period is 422 on that period, after the revision check", async () => {
  const plan = await newPlay();
  await rejects(
    savePlaySelection(plan.id, { ...none(), m06_m08: ["cand99"] }, 1),
    422,
    "VALIDATION_FAILED",
    INVALID,
    ["selections.m06_m08"],
  );
  // 옛 revision 이면 row_key 를 보기 전에 409 다.
  await rejects(
    savePlaySelection(plan.id, { ...none(), m06_m08: ["cand99"] }, 7),
    409,
    "STALE_WRITE",
    STALE,
    ["expected_revision"],
  );
});

test("a monthly-theme plan is 409 GATE_BLOCKED, an unknown plan is 404", async () => {
  const monthly = await createAnnualPlan({
    class_id: (await newClass()).id,
    form_id: null,
    format: "MONTHLY_THEME",
  });
  await rejects(
    savePlaySelection(monthly.id, none(), 1),
    409,
    "GATE_BLOCKED",
    "월별 주제형은 월별 칸 수정으로 고칩니다.",
    [],
  );
  await rejects(savePlaySelection(999, none(), 1), 404, "NOT_FOUND", "계획안을 찾을 수 없습니다.", [
    "id",
  ]);
});

test("a confirmed plan is 409 ALREADY_CONFIRMED, checked before the revision", async () => {
  const plan = await newPlay();
  commit((db) => (db.plans.find((p) => p.id === plan.id).status = "CONFIRMED"));
  await rejects(
    savePlaySelection(plan.id, none(), 99),
    409,
    "ALREADY_CONFIRMED",
    "확정된 계획안은 수정할 수 없습니다.",
    [],
  );
});

test("only STALE_WRITE and ALREADY_CONFIRMED count as a save conflict", async () => {
  const plan = await newPlay();
  const caught = (promise) =>
    promise.then(
      () => null,
      (e) => e,
    );
  assert.equal(isSaveConflict(await caught(savePlaySelection(plan.id, none(), 9))), true);
  commit((db) => (db.plans.find((p) => p.id === plan.id).status = "CONFIRMED"));
  assert.equal(isSaveConflict(await caught(savePlaySelection(plan.id, none(), 1))), true);
  assert.equal(isSaveConflict(await caught(savePlaySelection(plan.id, {}, 1))), false);
  assert.equal(isSaveConflict(await caught(savePlaySelection(999, none(), 1))), false);
  assert.equal(isSaveConflict(new Error("network")), false);
});

test("a plan stored before revision and selected existed can be saved (read as revision 1)", async () => {
  const plan = await newPlay();
  commit((db) => {
    const stored = db.plans.find((p) => p.id === plan.id);
    delete stored.revision;
    stored.periods.forEach((period) => delete period.selected);
  });
  const old = await getAnnualPlan(plan.id);
  assert.equal(old.revision, 1);
  const saved = await savePlaySelection(plan.id, { ...none(), m03_m05: ["cand2"] }, 1);
  assert.equal(saved.revision, 2);
  assert.deepEqual(saved.periods[0].selected, ["cand2"]);
  // 같은 선택이면 revision 이 그대로다.
  assert.equal(
    (await savePlaySelection(plan.id, { ...none(), m03_m05: ["cand2"] }, 2)).revision,
    2,
  );
});
