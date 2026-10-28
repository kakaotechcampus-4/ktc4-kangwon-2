// 놀이 중심 월간 API 클라이언트와 MSW 목업이 실제 서버 응답과 같은지.
// 기준: 서버를 실제로 찍은 응답(2026-10-28, play_monthly_responses) — 상태 · code · message · fields · 키를 옮겼다.
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
const { addPlayMonthly } = await import("../msw/data/play-monthly.ts");
const { createCenter } = await import("../lib/api/centers.ts");
const { createClass } = await import("../lib/api/classes.ts");
const { createAnnualPlan, savePlaySelection, confirmPlayProject } =
  await import("../lib/api/plans.ts");
const pm = await import("../lib/api/playMonthly.ts");
const { getMonthlyPlan, listMonthlyPlans } = await import("../lib/api/monthly.ts");
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
const LEGACY = "기존 월간계획안은 /api/plans/monthly 경로로 다룹니다.";
const PLAY_ROUTE = "놀이 중심 월간계획안은 /api/plans/monthly/play 경로로 다룹니다.";
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

test("single response has the captured key set, in every nested cell too", async () => {
  const { id } = await seeded();
  const plan = await pm.getPlayMonthly(id);
  assert.deepEqual(
    Object.keys(plan).sort(),
    [
      "confirmed_at",
      "class_id",
      "created_at",
      "drill_candidates",
      "format",
      "format_version",
      "free_play",
      "habits",
      "health",
      "id",
      "month",
      "notices",
      "nutrition",
      "parent",
      "rationale",
      "revision",
      "safety_candidates",
      "safety_weeks",
      "school_year",
      "status",
      "target_ages",
      "target_month",
      "teacher_inputs",
      "theme",
      "together",
      "weeks",
    ].sort(),
  );
  assert.deepEqual(Object.keys(plan.theme).sort(), ["evidence", "generation", "item_id", "value"]);
  assert.deepEqual(Object.keys(plan.together[0]).sort(), [
    "activity_id",
    "content_ids",
    "description",
    "name",
    "parent_item_id",
  ]);
  assert.deepEqual(Object.keys(plan.parent).sort(), [
    "annual_plan_id",
    "confirmed_at",
    "layout_version",
    "period_key",
    "plays",
  ]);
  assert.deepEqual(Object.keys(plan.parent.plays[0]).sort(), [
    "emphasized",
    "materials",
    "play_name",
    "play_name_item_id",
    "row_key",
    "support_direction",
  ]);
  assert.deepEqual(Object.keys(plan.weeks[0]).sort(), [
    "active",
    "end_date",
    "label",
    "start_date",
    "week_id",
  ]);
  assert.deepEqual(Object.keys(plan.safety_candidates[0]).sort(), [
    "category_id",
    "cell",
    "kind",
    "topic_group",
  ]);
  assert.deepEqual(Object.keys(plan.drill_candidates[0]).sort(), ["cell", "label", "topic_id"]);
  assert.deepEqual(Object.keys(plan.habits[0]).sort(), ["cell", "entry_id", "week_id"]);
  assert.deepEqual(Object.keys(plan.health).sort(), ["cell", "entry_id"]);
  assert.deepEqual(Object.keys(plan.teacher_inputs[0]).sort(), ["cell", "key"]);
  assert.deepEqual(Object.keys(plan.notices[0]).sort(), ["code", "week_id"]);
  assert.equal(plan.format, "PLAY_MONTHLY");
  assert.equal(plan.target_month, "2026-11");
  assert.deepEqual(
    [
      plan.together.length,
      plan.free_play.length,
      plan.habits.length,
      plan.safety_candidates.length,
      plan.drill_candidates.length,
      plan.parent.plays.length,
    ],
    [5, 5, 4, 8, 5, 5],
  );
  assert.deepEqual(
    plan.teacher_inputs.map((t) => t.key),
    [
      "fire_disaster_drill",
      "specialized_timetable",
      "special_activity_timetable",
      "class_notice",
      "class_birthdays",
      "home_connection",
    ],
  );
  // 한 번도 쓰지 않은 교사 입력 칸: 근거 없음 · generation null.
  assert.deepEqual(plan.teacher_inputs[0].cell.evidence, []);
  assert.equal(plan.teacher_inputs[0].cell.generation, null);
  assert.deepEqual(
    plan.notices.map((n) => n.code),
    Array(4).fill("SAFETY_UNPLACED"),
  );
  assert.deepEqual(
    plan.notices.map((n) => n.week_id),
    ["2026-11-W1", "2026-11-W2", "2026-11-W3", "2026-11-W4"],
  );
});

test("list is summaries only, filtered by class, and the legacy monthly list leaves it out", async () => {
  const { klass, plan } = await seeded();
  const { items } = await pm.listPlayMonthly(klass.id);
  assert.deepEqual(Object.keys(items[0]).sort(), [
    "class_id",
    "confirmed_at",
    "created_at",
    "id",
    "month",
    "revision",
    "school_year",
    "status",
    "target_month",
  ]);
  assert.equal(items[0].id, plan.id);
  assert.deepEqual((await pm.listPlayMonthly()).items.length, 1);
  assert.deepEqual(await listMonthlyPlans(klass.id), { items: [] });
  await rejects(pm.listPlayMonthly(999999), 404, "NOT_FOUND", "반을 찾을 수 없습니다.", [
    "class_id",
  ]);
});

test("editing a cell: trimmed value, revision + 1, evidence kept, whole plan returned", async () => {
  const { id, rev, plan } = await seeded();
  const done = await pm.editPlayMonthlyCell(
    id,
    plan.theme.item_id,
    "  가을 숲으로 놀러 가요  ",
    rev,
  );
  assert.equal(done.revision, rev + 1);
  assert.equal(done.theme.value, "가을 숲으로 놀러 가요");
  assert.deepEqual(done.theme.evidence, plan.theme.evidence);
  assert.deepEqual(done.theme.generation, plan.theme.generation);
  assert.deepEqual(await pm.getPlayMonthly(id), done);
  // 처음 쓰는 교사 입력 칸은 MANUAL 이 된다.
  const input = plan.teacher_inputs[3].cell.item_id;
  const written = await pm.editPlayMonthlyCell(id, input, "알림", done.revision);
  assert.equal(written.teacher_inputs[3].cell.generation.method, "MANUAL");
  assert.deepEqual(written.teacher_inputs[3].cell.evidence, []);
});

test("the same value is 422 on value and the revision stays; so is blank to blank", async () => {
  const { id, rev, plan } = await seeded();
  const same = plan.theme.value;
  await rejects(
    pm.editPlayMonthlyCell(id, plan.theme.item_id, same, rev),
    422,
    "VALIDATION_FAILED",
    INVALID,
    ["value"],
  );
  await rejects(
    pm.editPlayMonthlyCell(id, plan.theme.item_id, " " + same + " ", rev),
    422,
    "VALIDATION_FAILED",
    INVALID,
    ["value"],
  );
  const input = plan.teacher_inputs[3].cell.item_id; // 빈 칸
  await rejects(pm.editPlayMonthlyCell(id, input, "   ", rev), 422, "VALIDATION_FAILED", INVALID, [
    "value",
  ]);
  assert.equal((await pm.getPlayMonthly(id)).revision, rev);
});

test("whitespace-only value clears a filled cell (200, empty) and adds the blank notice", async () => {
  const { id, rev, plan } = await seeded();
  const done = await pm.editPlayMonthlyCell(id, plan.health.cell.item_id, "  ", rev);
  assert.equal(done.health.cell.value, "");
  assert.equal(done.revision, rev + 1);
  assert.deepEqual(done.notices.at(-1), { code: "HEALTH_BLANK", week_id: null });
  const habit = await pm.editPlayMonthlyCell(id, plan.habits[1].cell.item_id, "", done.revision);
  assert.ok(habit.notices.some((n) => n.code === "HABIT_BLANK" && n.week_id === "2026-11-W2"));
});

test("601 characters and non-string values are 422 on value; 600 is fine; a stale revision is 409", async () => {
  const { id, rev, plan } = await seeded();
  const item = plan.theme.item_id;
  await rejects(
    pm.editPlayMonthlyCell(id, item, "가".repeat(601), rev),
    422,
    "VALIDATION_FAILED",
    INVALID,
    ["value"],
  );
  const raw = (data) =>
    apiRequest("/api/plans/monthly/play/" + id + "/cells/" + item, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
  await rejects(raw({ value: 5, expected_revision: rev }), 422, "VALIDATION_FAILED", INVALID, [
    "value",
  ]);
  await rejects(raw({ value: "x", expected_revision: "1" }), 422, "VALIDATION_FAILED", INVALID, [
    "expected_revision",
  ]);
  await rejects(raw({ value: "x", expected_revision: true }), 422, "VALIDATION_FAILED", INVALID, [
    "expected_revision",
  ]);
  const ok = await pm.editPlayMonthlyCell(id, item, "가".repeat(600), rev);
  assert.equal(ok.theme.value.length, 600);
  await rejects(pm.editPlayMonthlyCell(id, item, "다른 주제", rev), 409, "STALE_WRITE", STALE, [
    "expected_revision",
  ]);
});

test("unknown cell is 404 on item_id", async () => {
  const { id, rev } = await seeded();
  await rejects(
    pm.editPlayMonthlyCell(id, "item_nope", "x", rev),
    404,
    "NOT_FOUND",
    "그 칸을 찾을 수 없습니다.",
    ["item_id"],
  );
});

test("safety: place, same input is 200 and untouched, clear with null, notices follow", async () => {
  const { id, rev, plan } = await seeded();
  const cand = plan.safety_candidates[0].cell.item_id;
  const week = "2026-11-W1";
  const placed = await pm.placePlayMonthlySafety(id, week, cand, rev);
  assert.equal(placed.revision, rev + 1);
  assert.equal(placed.safety_weeks[0].candidate_item_id, cand);
  assert.deepEqual(
    placed.notices.map((n) => n.week_id),
    ["2026-11-W2", "2026-11-W3", "2026-11-W4"],
  );
  const same = await pm.placePlayMonthlySafety(id, week, cand, placed.revision);
  assert.deepEqual(same, placed); // 무변경 — revision 도 그대로
  assert.equal((await pm.getPlayMonthly(id)).revision, placed.revision);
  // 놓은 후보의 글을 비우면 안 둔 주처럼 안내한다(SAFETY_BLANK).
  const blank = await pm.editPlayMonthlyCell(id, cand, "", placed.revision);
  assert.deepEqual(blank.notices[0], { code: "SAFETY_BLANK", week_id: week });
  const cleared = await pm.placePlayMonthlySafety(id, week, null, blank.revision);
  assert.equal(cleared.safety_weeks[0].candidate_item_id, null);
  assert.equal(cleared.revision, blank.revision + 1);
});

test("safety: key required, unknown week 404, unknown or blank candidate 422", async () => {
  const { id, rev, plan } = await seeded();
  const put = (week, data) =>
    apiRequest("/api/plans/monthly/play/" + id + "/safety-weeks/" + week, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
  await rejects(put("2026-11-W1", { expected_revision: rev }), 422, "VALIDATION_FAILED", INVALID, [
    "candidate_item_id",
  ]);
  await rejects(
    put("2026-11-W9", { candidate_item_id: null, expected_revision: rev }),
    404,
    "NOT_FOUND",
    "그 주를 찾을 수 없습니다.",
    ["week_id"],
  );
  await rejects(
    put("week-1", { candidate_item_id: null, expected_revision: rev }),
    422,
    "VALIDATION_FAILED",
    INVALID,
    ["week_id"],
  );
  await rejects(
    pm.placePlayMonthlySafety(id, "2026-11-W1", "item_nope", rev),
    422,
    "VALIDATION_FAILED",
    INVALID,
    ["candidate_item_id"],
  );
  await rejects(
    pm.placePlayMonthlySafety(id, "2026-11-W1", " ", rev),
    422,
    "VALIDATION_FAILED",
    INVALID,
    ["candidate_item_id"],
  );
  // 후보 id 가 아닌 칸(주제)도 안전 후보가 아니다.
  await rejects(
    pm.placePlayMonthlySafety(id, "2026-11-W1", plan.theme.item_id, rev),
    422,
    "VALIDATION_FAILED",
    INVALID,
    ["candidate_item_id"],
  );
});

test("drill copy fills the fire drill input as RULE_ONLY, the same copy is untouched", async () => {
  const { id, rev, plan } = await seeded();
  const drill = plan.drill_candidates[0].cell;
  const done = await pm.copyPlayMonthlyDrill(id, drill.item_id, rev);
  const cell = done.teacher_inputs[0].cell;
  assert.equal(done.revision, rev + 1);
  assert.equal(cell.value, drill.value);
  assert.deepEqual(cell.evidence, drill.evidence);
  assert.deepEqual(cell.generation, {
    method: "RULE_ONLY",
    rule_id: "play_monthly.drill_copy",
    rule_version: "play-monthly-layout-v0.1.0",
  });
  assert.equal(cell.item_id, plan.teacher_inputs[0].cell.item_id);
  const same = await pm.copyPlayMonthlyDrill(id, drill.item_id, done.revision);
  assert.deepEqual(same, done);
  const other = await pm.copyPlayMonthlyDrill(
    id,
    plan.drill_candidates[1].cell.item_id,
    done.revision,
  );
  assert.equal(other.revision, done.revision + 1);
  await rejects(
    pm.copyPlayMonthlyDrill(id, "item_nope", other.revision),
    404,
    "NOT_FOUND",
    "그 훈련 후보를 찾을 수 없습니다.",
    ["item_id"],
  );
});

test("copying a different candidate with the same sentence is a new copy (revision + 1)", async () => {
  const { id, rev, plan } = await seeded();
  const [a, b] = plan.drill_candidates;
  const first = await pm.copyPlayMonthlyDrill(id, a.cell.item_id, rev);
  const edited = await pm.editPlayMonthlyCell(id, b.cell.item_id, a.cell.value, first.revision);
  const second = await pm.copyPlayMonthlyDrill(id, b.cell.item_id, edited.revision);
  assert.deepEqual([first.revision, edited.revision, second.revision], [rev + 1, rev + 2, rev + 3]);
  assert.equal(second.teacher_inputs[0].cell.value, a.cell.value);
  assert.equal("copied_from" in second, false);
  const again = await pm.copyPlayMonthlyDrill(id, b.cell.item_id, second.revision);
  assert.equal(again.revision, second.revision);
});

test("legacy monthly creation is 409 ALREADY_EXISTS when a play monthly holds that month", async () => {
  const { klass } = await seeded(); // 11월 놀이 월간
  const year = klass.school_year;
  assert.equal(year, 2026);
  await rejects(
    apiRequest("/api/plans/monthly", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        class_id: klass.id,
        month: 11,
        profile_ref: { profile_id: "p", profile_version: "v" },
      }),
    }),
    409,
    "ALREADY_EXISTS",
    "이 반의 그 달 월간계획안이 이미 있습니다.",
    ["class_id", "month"],
  );
});

test("row delete takes the revision from the query and drops the row; a bad query is 422", async () => {
  const { id, rev, plan } = await seeded();
  const row = plan.free_play[4].activity_id;
  const done = await pm.removePlayMonthlyActivity(id, row, rev);
  assert.equal(done.revision, rev + 1);
  assert.equal(done.free_play.length, 4);
  assert.equal(done.together.length, 5);
  assert.deepEqual(calls.at(-1), {
    method: "DELETE",
    url: "/api/plans/monthly/play/" + id + "/activities/" + row + "?expected_revision=" + rev,
    body: undefined,
  });
  await rejects(
    pm.removePlayMonthlyActivity(id, row, done.revision),
    404,
    "NOT_FOUND",
    "그 행을 찾을 수 없습니다.",
    ["item_id"],
  );
  const bare = (query) =>
    apiRequest(
      "/api/plans/monthly/play/" + id + "/activities/" + plan.together[0].activity_id + query,
      { method: "DELETE" },
    );
  for (const query of [
    "",
    "?expected_revision=0",
    "?expected_revision=abc",
    "?expected_revision=3.5",
  ])
    await rejects(bare(query), 422, "VALIDATION_FAILED", INVALID, ["expected_revision"]);
  await rejects(
    pm.removePlayMonthlyActivity(id, plan.together[0].activity_id, rev),
    409,
    "STALE_WRITE",
    STALE,
    ["expected_revision"],
  );
  assert.equal((await pm.getPlayMonthly(id)).together.length, 5);
});

test("missing and foreign ids are 404, a non-integer id is 422 on plan_id", async () => {
  await seeded();
  await rejects(pm.getPlayMonthly(999999), 404, "NOT_FOUND", NOT_FOUND, ["id"]);
  await rejects(pm.editPlayMonthlyCell(999999, "item_x", "x", 1), 404, "NOT_FOUND", NOT_FOUND, [
    "id",
  ]);
  await rejects(apiRequest("/api/plans/monthly/play/abc"), 422, "VALIDATION_FAILED", INVALID, [
    "plan_id",
  ]);
});

test("a legacy monthly id is 409 on the play route, and a play id is 409 on the legacy routes", async () => {
  const { id } = await seeded();
  await rejects(getMonthlyPlan(id), 409, "GATE_BLOCKED", PLAY_ROUTE, []);
  await rejects(
    apiRequest("/api/plans/monthly/" + id + "/audit"),
    409,
    "GATE_BLOCKED",
    PLAY_ROUTE,
    [],
  );
  await rejects(
    apiRequest("/api/plans/monthly/" + id + "/cells/item_x", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ value: "x", expected_revision: 1 }),
    }),
    409,
    "GATE_BLOCKED",
    PLAY_ROUTE,
    [],
  );
  await rejects(
    apiRequest("/api/plans/monthly/" + id + "/confirm", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ expected_revision: 1 }),
    }),
    409,
    "GATE_BLOCKED",
    PLAY_ROUTE,
    [],
  );
  await rejects(getMonthlyPlan(999999), 404, "NOT_FOUND", NOT_FOUND, ["id"]);
});

test("a legacy monthly id is 409 on every play route", async () => {
  const { klass, rev } = await seeded();
  const legacy = commit(
    (db) => db.monthlyPlans.push({ id: db.next++, class_id: klass.id }) && db.next - 1,
  );
  await rejects(pm.getPlayMonthly(legacy), 409, "GATE_BLOCKED", LEGACY, []);
  await rejects(pm.deletePlayMonthly(legacy), 409, "GATE_BLOCKED", LEGACY, []);
  await rejects(
    pm.editPlayMonthlyCell(legacy, "item_x", "x", rev),
    409,
    "GATE_BLOCKED",
    LEGACY,
    [],
  );
  await rejects(
    pm.removePlayMonthlyActivity(legacy, "item_x", rev),
    409,
    "GATE_BLOCKED",
    LEGACY,
    [],
  );
});

test("the literal play path is never taken as a legacy id", async () => {
  await seeded();
  const { items } = await apiRequest("/api/plans/monthly/play");
  assert.equal(items.length, 1); // 놀이 월간 목록이다 — 기존 월간 단건이 아니다
  assert.deepEqual(Object.keys(items[0]).includes("profile_ref"), false);
});

test("a confirmed plan is 409 ALREADY_CONFIRMED on every change, and cannot be deleted", async () => {
  const { id, rev, plan } = await seeded(true);
  const confirmed = (p) =>
    rejects(p, 409, "ALREADY_CONFIRMED", "확정된 계획안은 수정할 수 없습니다.", []);
  await confirmed(pm.editPlayMonthlyCell(id, plan.theme.item_id, "다른", rev));
  await confirmed(pm.placePlayMonthlySafety(id, "2026-11-W1", null, rev));
  await confirmed(pm.copyPlayMonthlyDrill(id, plan.drill_candidates[0].cell.item_id, rev));
  await confirmed(pm.removePlayMonthlyActivity(id, plan.together[0].activity_id, rev));
  await rejects(
    pm.deletePlayMonthly(id),
    409,
    "GATE_BLOCKED",
    "확정된 계획안은 지울 수 없습니다.",
    [],
  );
  assert.equal((await pm.getPlayMonthly(id)).status, "CONFIRMED");
  assert.equal((await pm.listPlayMonthly()).items[0].confirmed_at !== null, true);
});

test("a draft is deleted with 204 and then it is 404", async () => {
  const { id } = await seeded();
  assert.equal(await pm.deletePlayMonthly(id), undefined);
  await rejects(pm.getPlayMonthly(id), 404, "NOT_FOUND", NOT_FOUND, ["id"]);
  assert.deepEqual((await pm.listPlayMonthly()).items, []);
});

test("create passes the gates and then is 503 without saving anything", async () => {
  const klass = await newClass();
  const create = (month = 12) =>
    pm.createPlayMonthly({ class_id: klass.id, month, emphasized_row_keys: [] });
  const gate = (message) => rejects(create(), 409, "GATE_BLOCKED", message, ["class_id"]);
  await gate("연간계획안을 먼저 만들어 확정해주세요.");
  const annual = await createAnnualPlan({
    class_id: klass.id,
    form_id: null,
    format: "PLAY_PROJECT",
  });
  await gate("연간계획안을 먼저 확정해주세요.");
  const pick = Object.fromEntries(
    annual.periods.map((p) => [p.period_key, p.candidates.slice(0, 5).map((c) => c.row_key)]),
  );
  const saved = await savePlaySelection(annual.id, pick, annual.revision);
  await confirmPlayProject(annual.id, saved.revision);
  await rejects(
    create(),
    503,
    "DEPENDENCY_UNAVAILABLE",
    "지금은 이 반의 놀이 중심 월간계획안을 만들 수 없습니다. 관리자에게 문의해 주세요.",
    [],
  );
  assert.deepEqual((await pm.listPlayMonthly(klass.id)).items, []);
  await rejects(
    pm.createPlayMonthly({ class_id: klass.id, month: 13, emphasized_row_keys: [] }),
    422,
    "VALIDATION_FAILED",
    INVALID,
    ["month"],
  );
  await rejects(
    pm.createPlayMonthly({ class_id: klass.id, month: 12, emphasized_row_keys: ["a", "a"] }),
    422,
    "VALIDATION_FAILED",
    INVALID,
    ["emphasized_row_keys"],
  );
  await rejects(
    pm.createPlayMonthly({ class_id: 999999, month: 12, emphasized_row_keys: [] }),
    404,
    "NOT_FOUND",
    "반을 찾을 수 없습니다.",
    ["class_id"],
  );
});

test("create is 409 ALREADY_EXISTS when that month already has a plan, before the annual gate", async () => {
  const { klass } = await seeded(); // 연간은 없다 — 이미 있음이 먼저다
  await rejects(
    pm.createPlayMonthly({ class_id: klass.id, month: 11, emphasized_row_keys: [] }),
    409,
    "ALREADY_EXISTS",
    "이 반의 그 달 월간계획안이 이미 있습니다.",
    ["class_id", "month"],
  );
});

test("legacy monthly creation on a play-project annual says to use the play monthly", async () => {
  const klass = await newClass();
  await createAnnualPlan({ class_id: klass.id, form_id: null, format: "PLAY_PROJECT" });
  await rejects(
    apiRequest("/api/plans/monthly", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        class_id: klass.id,
        month: 3,
        profile_ref: { profile_id: "p", profile_version: "v" },
      }),
    }),
    409,
    "GATE_BLOCKED",
    "놀이 프로젝트형 연간계획안으로는 기존 월간계획안을 만들 수 없습니다. 놀이 중심 월간계획안으로 만들어 주세요.",
    ["class_id"],
  );
});

test("client sends the right method, path and body", async () => {
  const { id, rev, plan } = await seeded();
  const sent = async (call, method, path, body) => {
    calls.length = 0;
    await call().catch(() => {});
    assert.equal(calls[0].method, method);
    assert.equal(calls[0].url, "/api/plans/monthly/play" + path);
    assert.deepEqual(calls[0].body && JSON.parse(calls[0].body), body);
  };
  const item = plan.theme.item_id;
  await sent(() => pm.listPlayMonthly(7), "GET", "?class_id=7", undefined);
  await sent(() => pm.getPlayMonthly(id), "GET", "/" + id, undefined);
  await sent(() => pm.deletePlayMonthly(id), "DELETE", "/" + id, undefined);
  await sent(
    () => pm.createPlayMonthly({ class_id: 7, month: 12, emphasized_row_keys: ["cand1"] }),
    "POST",
    "",
    { class_id: 7, month: 12, emphasized_row_keys: ["cand1"] },
  );
  await sent(
    () => pm.editPlayMonthlyCell(id, item, "글", rev),
    "PUT",
    "/" + id + "/cells/" + item,
    { value: "글", expected_revision: rev },
  );
  await sent(
    () => pm.placePlayMonthlySafety(id, "2026-11-W2", null, rev),
    "PUT",
    "/" + id + "/safety-weeks/2026-11-W2",
    { candidate_item_id: null, expected_revision: rev },
  );
  await sent(
    () => pm.copyPlayMonthlyDrill(id, item, rev),
    "POST",
    "/" + id + "/drill-candidates/" + item + "/copy",
    { expected_revision: rev },
  );
  await sent(
    () => pm.removePlayMonthlyActivity(id, item, rev),
    "DELETE",
    "/" + id + "/activities/" + item + "?expected_revision=" + rev,
    undefined,
  );
});
