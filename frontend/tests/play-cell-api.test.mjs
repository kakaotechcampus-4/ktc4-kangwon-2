// 칸 편집 API(PUT /api/plans/annual/{id}/cells/{item_id})와 MSW 목업이 실제 서버 응답과 같은지.
// 기준: 서버 칸 편집을 실제로 찍은 응답(2026-10-28, play_save_responses.json) — 상태 · code · message · fields 를 그대로 옮겼다.
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
const { createAnnualPlan, getAnnualPlan, savePlaySelection, editPlayCell, isRejectedSave } =
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

/** 새 계획안에서 첫 구간 후보 1 · 2 를 고른다. 칸은 후보 1(고름) · 3(안 고름) 것을 쓴다. */
async function picked() {
  const plan = await newPlay();
  const saved = await savePlaySelection(plan.id, { ...none(), m03_m05: ["cand1", "cand2"] }, 1);
  const [cand1, , cand3] = saved.periods[0].candidates;
  return { id: plan.id, revision: saved.revision, cand1, cand3 };
}

test("editing a picked play's cell returns the whole plan at revision + 1 with the trimmed value", async () => {
  const p = await picked();
  const saved = await editPlayCell(
    p.id,
    p.cand1.play_name.item_id,
    "  캡처 놀이 이름  ",
    p.revision,
  );
  assert.equal(saved.revision, p.revision + 1);
  assert.equal(saved.periods[0].candidates[0].play_name.value, "캡처 놀이 이름");
  assert.equal(saved.periods.length, 4);
  assert.deepEqual(saved.periods[0].selected, ["cand1", "cand2"]);
  assert.deepEqual(await getAnnualPlan(p.id), saved);
  for (const field of ["materials", "support_direction"]) {
    const next = await editPlayCell(p.id, p.cand1[field].item_id, "고침", saved.revision);
    assert.equal(next.revision, saved.revision + 1);
    assert.equal(next.periods[0].candidates[0][field].value, "고침");
    saved.revision = next.revision;
  }
});

test("the same value is 422 VALIDATION_FAILED on value, and the revision stays", async () => {
  const p = await picked();
  const same = p.cand1.play_name.value;
  await rejects(
    editPlayCell(p.id, p.cand1.play_name.item_id, same, p.revision),
    422,
    "VALIDATION_FAILED",
    INVALID,
    ["value"],
  );
  await rejects(
    editPlayCell(p.id, p.cand1.play_name.item_id, " " + same + " ", p.revision),
    422,
    "VALIDATION_FAILED",
    INVALID,
    ["value"],
  );
  assert.equal((await getAnnualPlan(p.id)).revision, p.revision);
});

test("blank, whitespace-only, and 601-character values are 422 on value; 600 is fine", async () => {
  const p = await picked();
  const id = p.cand1.play_name.item_id;
  for (const value of ["", "   ", "가".repeat(601)])
    await rejects(editPlayCell(p.id, id, value, p.revision), 422, "VALIDATION_FAILED", INVALID, [
      "value",
    ]);
  const ok = await editPlayCell(p.id, id, "가".repeat(600), p.revision);
  assert.equal(ok.periods[0].candidates[0].play_name.value.length, 600);
});

test("a bad revision is 422 on expected_revision before anything else is looked at", async () => {
  const p = await picked();
  const id = p.cand1.play_name.item_id;
  for (const revision of [0, -1, 1.5, "3", true])
    await rejects(editPlayCell(p.id, id, "바꿈", revision), 422, "VALIDATION_FAILED", INVALID, [
      "expected_revision",
    ]);
});

test("a learning cell, an unpicked play's cell, and an unknown item are 422 on item_id", async () => {
  const p = await picked();
  for (const itemId of [p.cand1.learning.item_id, p.cand3.play_name.item_id, "item_does_not_exist"])
    await rejects(
      editPlayCell(p.id, itemId, "바꿈", p.revision),
      422,
      "VALIDATION_FAILED",
      INVALID,
      ["item_id"],
    );
  assert.equal((await getAnnualPlan(p.id)).revision, p.revision);
});

test("an old revision is 409 STALE_WRITE and nothing is saved", async () => {
  const p = await picked();
  await editPlayCell(p.id, p.cand1.play_name.item_id, "첫 고침", p.revision);
  await rejects(
    editPlayCell(p.id, p.cand1.play_name.item_id, "다른 이름", p.revision),
    409,
    "STALE_WRITE",
    STALE,
    ["expected_revision"],
  );
  assert.equal((await getAnnualPlan(p.id)).periods[0].candidates[0].play_name.value, "첫 고침");
});

test("a missing plan is 404 and a monthly-theme plan is 409 GATE_BLOCKED", async () => {
  await rejects(
    editPlayCell(99999, "item_x", "바꿈", 1),
    404,
    "NOT_FOUND",
    "계획안을 찾을 수 없습니다.",
    ["id"],
  );
  const center = await newClass();
  const monthly = await createAnnualPlan({
    class_id: center.id,
    form_id: null,
    format: "MONTHLY_THEME",
  });
  await rejects(
    editPlayCell(monthly.id, "item_x", "바꿈", 1),
    409,
    "GATE_BLOCKED",
    "월별 주제형은 월별 칸 수정으로 고칩니다.",
    [],
  );
});

test("an old saved plan without a revision key is read as revision 1 and can be edited", async () => {
  const p = await picked();
  commit((db) => {
    const plan = db.plans.find((x) => x.id === p.id);
    delete plan.revision;
  });
  const saved = await editPlayCell(p.id, p.cand1.play_name.item_id, "옛 저장본 고침", 1);
  assert.equal(saved.revision, 2);
});

test("a confirmed plan is 409 ALREADY_CONFIRMED", async () => {
  const p = await picked();
  commit((db) => {
    db.plans.find((x) => x.id === p.id).status = "CONFIRMED";
  });
  await rejects(
    editPlayCell(p.id, p.cand1.play_name.item_id, "바꿈", p.revision),
    409,
    "ALREADY_CONFIRMED",
    "확정된 계획안은 수정할 수 없습니다.",
    [],
  );
});

test("the 600-character limit counts code points, so 600 emoji are fine and 601 are not", async () => {
  const p = await picked();
  const id = p.cand1.play_name.item_id;
  await rejects(
    editPlayCell(p.id, id, "😀".repeat(601), p.revision),
    422,
    "VALIDATION_FAILED",
    INVALID,
    ["value"],
  );
  const ok = await editPlayCell(p.id, id, "😀".repeat(600), p.revision);
  assert.equal([...ok.periods[0].candidates[0].play_name.value].length, 600);
});

test("only a 422 ApiError counts as a rejected save", () => {
  const error = (status) =>
    new ApiError(status, { error: { code: "X", message: "m", fields: [] } });
  assert.equal(isRejectedSave(error(422)), true);
  for (const status of [400, 401, 403, 404, 408, 409, 429, 500, 503])
    assert.equal(isRejectedSave(error(status)), false, String(status));
  assert.equal(isRejectedSave(new Error("network")), false);
});
