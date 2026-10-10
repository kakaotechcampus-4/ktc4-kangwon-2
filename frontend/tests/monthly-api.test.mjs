// 월간계획안 · 양식 설정 API 클라이언트와 MSW 목업 계약 (docs/api-spec.md §9-1 ~ §9-3).
// 실제 서버 · LLM 을 부르지 않는다. 목업은 서버의 revision · 확정 · 소유 규칙을 그대로 따른다.
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
const { addMonthly } = await import("../msw/data/monthly-plans.ts");
const { addReadyProfile, approveTemplateForTest } =
  await import("../msw/data/template-profiles.ts");
const { createCenter } = await import("../lib/api/centers.ts");
const { createClass } = await import("../lib/api/classes.ts");
const { createAnnualPlan, getAnnualPlan, putAnnualMonth, confirmAnnualPlan } =
  await import("../lib/api/plans.ts");
const monthly = await import("../lib/api/monthly.ts");
const profiles = await import("../lib/api/templateProfiles.ts");
const { ApiError } = await import("../lib/api/client.ts");
const {
  createMonthlyPlan,
  getMonthlyPlan,
  listMonthlyPlans,
  editMonthlyCell,
  regenerateMonthlyCell,
  confirmMonthlyPlan,
} = monthly;
const {
  getClassTemplateProfile,
  listReadyTemplateProfiles,
  createTemplateProfile,
  putCenterDefaultProfile,
} = profiles;
// 기반 Template 은 승인 대기다 — 테스트만 승인 Fixture 로 열고 관리 API 로 READY 를 만든다.
const FOCUS = {
  template_id: "ssuksak.monthly-template-a",
  template_version: "monthly-template-a-v0.2.1",
};
const PROFILE_INPUT = {
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
async function readyRef(centerId) {
  approveTemplateForTest(FOCUS);
  return (await createTemplateProfile(centerId, PROFILE_INPUT)).profile_ref;
}

const server = setupServer(...handlers);
// listen() 이 바꿔 끼운 fetch. 클라이언트의 상대 경로를 절대 주소로 바꾸고,
// 목업의 연출용 지연(생성 1.2초)은 끈다 — 계약 검사에는 필요 없다.
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

/** 오류는 ApiError 그대로 — status · code · fields 를 바꾸지 않는다. */
const rejects = (promise, status, code, fields) =>
  assert.rejects(promise, (e) => {
    assert.ok(e instanceof ApiError);
    assert.equal(e.status, status);
    assert.equal(e.body.error.code, code);
    if (fields) assert.deepEqual(e.body.error.fields, fields);
    assert.equal(e.message, e.body.error.message);
    return true;
  });
const cells = (plan) => plan.sections.flatMap((s) => s.cells);
const cellOf = (plan, key) => plan.sections.find((s) => s.section_key === key).cells[0];

async function confirmedClass() {
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
    age_max: 5,
    child_count: null,
  });
  const annual = await createAnnualPlan({ class_id: klass.id, form_id: null });
  await confirmAnnualPlan(annual.id);
  return { center, klass, annual, ref: await readyRef(center.id) };
}

test("client exports 15 functions: 7 monthly + 2 profile read + 6 profile management", () => {
  assert.deepEqual(Object.keys(monthly).sort(), [
    "confirmMonthlyPlan",
    "createMonthlyPlan",
    "editMonthlyCell",
    "getMonthlyPlan",
    "getMonthlyPlanAudit",
    "listMonthlyPlans",
    "regenerateMonthlyCell",
  ]);
  assert.deepEqual(Object.keys(profiles).sort(), [
    "createTemplateProfile",
    "getCenterDefaultProfile",
    "getClassProfileOverride",
    "getClassTemplateProfile",
    "listMonthlyTemplates",
    "listReadyTemplateProfiles",
    "putCenterDefaultProfile",
    "putClassProfileOverride",
  ]);
});

test("methods, URLs, query, encoded item_id, bodies and bearer token", async () => {
  const session = new Map([["saessak.authToken", "T0KEN"]]);
  const storage = {
    getItem: (k) => session.get(k) ?? null,
    setItem: (k, v) => session.set(k, v),
    removeItem: (k) => session.delete(k),
  };
  globalThis.window = { sessionStorage: storage, localStorage: storage };
  const calls = [];
  globalThis.fetch = async (url, options = {}) => {
    const headers = new Headers(options.headers);
    calls.push({
      url: String(url),
      method: options.method ?? "GET",
      body: options.body ? JSON.parse(options.body) : undefined,
      auth: headers.get("Authorization"),
      type: headers.get("Content-Type"),
    });
    return new Response("{}", { headers: { "Content-Type": "application/json" } });
  };
  const ref = { profile_id: "tprofile_1", profile_version: "v1" };
  await createMonthlyPlan({ class_id: 3, month: 9, profile_ref: ref });
  await getMonthlyPlan(7);
  await listMonthlyPlans();
  await listMonthlyPlans(3);
  await editMonthlyCell(7, "item/a b", "가을 놀이", 4);
  await regenerateMonthlyCell(7, "item/a b", 4);
  await confirmMonthlyPlan(7, 4);
  await getClassTemplateProfile(3);
  await listReadyTemplateProfiles(1);
  const cell = "/api/plans/monthly/7/cells/item%2Fa%20b";
  assert.deepEqual(
    calls.map((c) => [c.method, c.url, c.body]),
    [
      ["POST", "/api/plans/monthly", { class_id: 3, month: 9, profile_ref: ref }],
      ["GET", "/api/plans/monthly/7", undefined],
      ["GET", "/api/plans/monthly", undefined],
      ["GET", "/api/plans/monthly?class_id=3", undefined],
      ["PUT", cell, { value: "가을 놀이", expected_revision: 4 }],
      ["POST", cell + "/regenerate", { expected_revision: 4 }],
      ["POST", "/api/plans/monthly/7/confirm", { expected_revision: 4 }],
      ["GET", "/api/classes/3/template-profile", undefined],
      ["GET", "/api/centers/1/template-profiles", undefined],
    ],
  );
  assert.ok(calls.every((c) => c.auth === "Bearer T0KEN"));
  assert.ok(calls.every((c) => (c.body ? c.type === "application/json" : c.type === null)));
});

test("create returns the full DTO: dynamic weeks, empty safety cells, no audit fields", async () => {
  const { klass, annual, ref } = await confirmedClass();
  const plan = await createMonthlyPlan({ class_id: klass.id, month: 9, profile_ref: ref });
  assert.equal(plan.status, "DRAFT");
  assert.equal(plan.revision, 1);
  assert.equal(plan.target_month, klass.school_year + "-09");
  assert.deepEqual(plan.profile_ref, ref);
  assert.equal(plan.parent.annual_plan_id, annual.id);
  assert.equal(
    plan.parent.theme,
    (await getAnnualPlan(annual.id)).months.find((m) => m.month === 9).theme,
  );
  assert.equal(plan.confirmed_at, null);
  for (const s of plan.sections) {
    const expected = s.repeat_by === "WEEK" ? plan.weeks.length : s.repeat_by === "NONE" ? 1 : 0;
    assert.equal(s.cells.length, expected, s.section_key);
  }
  assert.equal(plan.sections.find((s) => s.role === "AXIS").repeat_by, null);
  const safety = plan.sections.find((s) => s.section_key === "safety_education").cells;
  assert.ok(safety.every((c) => c.value === "" && c.state === "EMPTY_UNRESOLVED"));
  assert.equal(plan.constraints[0].verification, "NOT_VERIFIED_SOURCE_REQUIRED");
  for (const c of cells(plan)) {
    assert.deepEqual(Object.keys(c).sort(), [
      "evidence",
      "generation",
      "item_id",
      "state",
      "value",
      "week_id",
    ]);
  }
  // 1~2월은 다음 해 — 주 개수는 달력이 정한다.
  const feb = await createMonthlyPlan({ class_id: klass.id, month: 2, profile_ref: ref });
  assert.equal(feb.target_month, klass.school_year + 1 + "-02");
  assert.ok(feb.weeks.every((w, i) => w.week_id === feb.target_month + "-W" + (i + 1)));
  assert.deepEqual(await getMonthlyPlan(plan.id), plan);
  // 목록은 요약만, 대상 달 오름차순.
  const { items } = await listMonthlyPlans(klass.id);
  assert.deepEqual(
    items.map((p) => p.id),
    [plan.id, feb.id],
  );
  assert.equal(items[0].sections, undefined);
  assert.deepEqual((await listMonthlyPlans()).items, items);
});

test("create gates: no annual, unconfirmed annual, duplicate month, unknown profile", async () => {
  const center = await createCenter({
    name: "원",
    director_name: "원장",
    region_sido: "충청북도",
    region_sigungu: "충주시",
  });
  const klass = await createClass(center.id, {
    name: "반",
    teacher_name: "교사",
    age_min: 4,
    age_max: 4,
    child_count: null,
  });
  const ref = await readyRef(center.id);
  const input = { class_id: klass.id, month: 9, profile_ref: ref };
  await rejects(createMonthlyPlan(input), 409, "GATE_BLOCKED", ["class_id"]);
  const annual = await createAnnualPlan({ class_id: klass.id, form_id: null });
  await rejects(createMonthlyPlan(input), 409, "GATE_BLOCKED", ["class_id"]);
  await confirmAnnualPlan(annual.id);
  await rejects(
    createMonthlyPlan({ ...input, profile_ref: { ...ref, profile_version: "v9" } }),
    404,
    "NOT_FOUND",
    ["profile_ref"],
  );
  await rejects(createMonthlyPlan({ ...input, month: 13 }), 422, "VALIDATION_FAILED", ["month"]);
  assert.equal(read().monthlyPlans.length, 0);
  await createMonthlyPlan(input);
  await rejects(createMonthlyPlan(input), 409, "ALREADY_EXISTS", ["class_id", "month"]);
  await rejects(getMonthlyPlan(999), 404, "NOT_FOUND", ["id"]);
});

test("edit: matching revision +1 and only the target cell changes", async () => {
  const { klass, ref } = await confirmedClass();
  const plan = await createMonthlyPlan({ class_id: klass.id, month: 9, profile_ref: ref });
  const target = cellOf(plan, "goals");
  const edited = await editMonthlyCell(plan.id, target.item_id, "교사가 고친 목표", 1);
  assert.equal(edited.revision, 2);
  const after = cellOf(edited, "goals");
  assert.equal(after.value, "교사가 고친 목표");
  assert.equal(after.item_id, target.item_id);
  assert.deepEqual(after.evidence, target.evidence);
  assert.deepEqual(after.generation, target.generation);
  const others = (p) => cells(p).filter((c) => c.item_id !== target.item_id);
  assert.deepEqual(others(edited), others(plan));
  // 같은 값 · 없는 칸 · 오래된 revision 은 저장하지 않는다.
  await rejects(
    editMonthlyCell(plan.id, target.item_id, "교사가 고친 목표", 2),
    422,
    "VALIDATION_FAILED",
    ["value"],
  );
  await rejects(editMonthlyCell(plan.id, "item_none", "x", 2), 404, "NOT_FOUND", ["item_id"]);
  await rejects(editMonthlyCell(plan.id, target.item_id, "x", 1), 409, "STALE_WRITE", [
    "expected_revision",
  ]);
  assert.deepEqual(await getMonthlyPlan(plan.id), edited);
  // 안전교육 칸도 고칠 수 있고, 비우면 다시 「근거 필요」다.
  const safety = cellOf(edited, "safety_education");
  const filled = await editMonthlyCell(plan.id, safety.item_id, "교통안전", 2);
  assert.equal(cellOf(filled, "safety_education").state, "FILLED");
  const cleared = await editMonthlyCell(plan.id, safety.item_id, "", 3);
  assert.equal(cellOf(cleared, "safety_education").state, "EMPTY_UNRESOLVED");
});

test("revision body is strict: string and boolean are rejected", async () => {
  const { klass, ref } = await confirmedClass();
  const plan = await createMonthlyPlan({ class_id: klass.id, month: 9, profile_ref: ref });
  const item = cellOf(plan, "goals").item_id;
  for (const bad of ["1", true, 0]) {
    await rejects(regenerateMonthlyCell(plan.id, item, bad), 422, "VALIDATION_FAILED", [
      "expected_revision",
    ]);
    await rejects(confirmMonthlyPlan(plan.id, bad), 422, "VALIDATION_FAILED", [
      "expected_revision",
    ]);
  }
  assert.equal((await getMonthlyPlan(plan.id)).revision, 1);
});

test("regenerate: allowed sections only, revision checked, other cells untouched", async () => {
  const { klass, ref } = await confirmedClass();
  const plan = await createMonthlyPlan({ class_id: klass.id, month: 9, profile_ref: ref });
  const focus = plan.sections.find((s) => s.section_key === "focus").cells[1];
  const regenerated = await regenerateMonthlyCell(plan.id, focus.item_id, 1);
  assert.equal(regenerated.revision, 2);
  const after = cells(regenerated).find((c) => c.item_id === focus.item_id);
  assert.notEqual(after.value, focus.value);
  assert.equal(after.week_id, focus.week_id);
  assert.equal(after.generation.method, "RULE_LLM");
  const others = (p) => cells(p).filter((c) => c.item_id !== focus.item_id);
  assert.deepEqual(others(regenerated), others(plan));
  for (const key of ["theme", "safety_education"])
    await rejects(
      regenerateMonthlyCell(plan.id, cellOf(plan, key).item_id, 2),
      422,
      "VALIDATION_FAILED",
      ["item_id"],
    );
  await rejects(regenerateMonthlyCell(plan.id, focus.item_id, 1), 409, "STALE_WRITE", [
    "expected_revision",
  ]);
  // 503 · 500 은 저장 전에 돌아온다 — 칸 · revision 이 그대로다.
  for (const [code, status] of [
    ["LLM_BUDGET_EXCEEDED", 503],
    ["DEPENDENCY_UNAVAILABLE", 503],
    ["GENERATION_FAILED", 500],
  ]) {
    const r = await mswFetch(
      "http://localhost/api/plans/monthly/" +
        plan.id +
        "/cells/" +
        focus.item_id +
        "/regenerate?mockError=" +
        code +
        "&mockDelay=0",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ expected_revision: 2 }),
      },
    );
    assert.equal(r.status, status);
    assert.deepEqual(await r.json(), {
      error: { code, message: "개발용 실패 상황입니다.", fields: [] },
    });
  }
  assert.deepEqual(await getMonthlyPlan(plan.id), regenerated);
});

test("confirm policy B: match → +1, stale → 409, already confirmed → 200 unchanged", async () => {
  const { klass, ref } = await confirmedClass();
  const plan = await createMonthlyPlan({ class_id: klass.id, month: 9, profile_ref: ref });
  await rejects(confirmMonthlyPlan(plan.id, 2), 409, "STALE_WRITE", ["expected_revision"]);
  assert.equal((await getMonthlyPlan(plan.id)).status, "DRAFT");
  // 안전교육이 「근거 필요」로 남아 있어도 확정된다.
  const confirmed = await confirmMonthlyPlan(plan.id, 1);
  assert.equal(confirmed.status, "CONFIRMED");
  assert.equal(confirmed.revision, 2);
  assert.ok(confirmed.confirmed_at);
  for (const stale of [1, 2, 99])
    assert.deepEqual(await confirmMonthlyPlan(plan.id, stale), confirmed);
  // 확정 뒤 편집 · 재생성은 revision 이 맞아도 막힌다.
  const item = cellOf(plan, "goals").item_id;
  await rejects(editMonthlyCell(plan.id, item, "금지", 2), 409, "ALREADY_CONFIRMED", []);
  await rejects(regenerateMonthlyCell(plan.id, item, 2), 409, "ALREADY_CONFIRMED", []);
  assert.deepEqual(await getMonthlyPlan(plan.id), confirmed);
});

test("create surfaces 503 / 500 envelopes without saving", async () => {
  const { klass, ref } = await confirmedClass();
  for (const [code, status] of [
    ["LLM_BUDGET_EXCEEDED", 503],
    ["DEPENDENCY_UNAVAILABLE", 503],
    ["GENERATION_FAILED", 500],
  ]) {
    const r = await mswFetch("http://localhost/api/plans/monthly?mockDelay=0&mockError=" + code, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ class_id: klass.id, month: 9, profile_ref: ref }),
    });
    assert.equal(r.status, status);
    assert.equal((await r.json()).error.code, code);
  }
  assert.equal(read().monthlyPlans.length, 0);
});

test("template profile: READY list, unassigned → SELECTION_REQUIRED, default pointer", async () => {
  const { center, klass, ref } = await confirmedClass();
  const { items } = await listReadyTemplateProfiles(center.id);
  assert.equal(items.length, 1);
  assert.equal(items[0].status, "READY");
  assert.ok(items[0].sections.some((s) => s.section_key === "safety_education"));
  assert.deepEqual(await getClassTemplateProfile(klass.id), {
    source: "SELECTION_REQUIRED",
    profile_ref: null,
    reason: "NO_POINTER",
  });
  await putCenterDefaultProfile(center.id, { profile_ref: ref, expected_profile_ref: null });
  assert.deepEqual(await getClassTemplateProfile(klass.id), {
    source: "INSTITUTION_DEFAULT",
    profile_ref: ref,
    reason: null,
  });
  await rejects(getClassTemplateProfile(999), 404, "NOT_FOUND", ["class_id"]);
});

test("another center's class, plan and profiles are not found", async () => {
  const mine = await confirmedClass();
  const other = await createCenter({
    name: "다른 원",
    director_name: "원장",
    region_sido: "강원특별자치도",
    region_sigungu: "춘천시",
  });
  const theirClass = await createClass(other.id, {
    name: "다른 반",
    teacher_name: "교사",
    age_min: 5,
    age_max: 5,
    child_count: null,
  });
  const theirAnnual = await createAnnualPlan({ class_id: theirClass.id, form_id: null });
  await confirmAnnualPlan(theirAnnual.id);
  const theirs = addMonthly(theirClass, theirAnnual, 9, addReadyProfile(other.id, PROFILE_INPUT));
  const item = cellOf(theirs, "goals").item_id;
  await rejects(getMonthlyPlan(theirs.id), 404, "NOT_FOUND", ["id"]);
  await rejects(editMonthlyCell(theirs.id, item, "x", 1), 404, "NOT_FOUND", ["id"]);
  await rejects(regenerateMonthlyCell(theirs.id, item, 1), 404, "NOT_FOUND", ["id"]);
  await rejects(confirmMonthlyPlan(theirs.id, 1), 404, "NOT_FOUND", ["id"]);
  await rejects(listMonthlyPlans(theirClass.id), 404, "NOT_FOUND", ["class_id"]);
  await rejects(
    createMonthlyPlan({ class_id: theirClass.id, month: 9, profile_ref: mine.ref }),
    404,
    "NOT_FOUND",
    ["class_id"],
  );
  await rejects(getClassTemplateProfile(theirClass.id), 404, "NOT_FOUND", ["class_id"]);
  await rejects(listReadyTemplateProfiles(other.id), 404, "NOT_FOUND", ["center_id"]);
  assert.deepEqual((await listMonthlyPlans()).items, []);
  assert.equal(read().monthlyPlans.find((p) => p.id === theirs.id).revision, 1);
});

test("annual API still behaves the same next to the monthly mocks", async () => {
  const { klass, annual } = await confirmedClass();
  const plan = await getAnnualPlan(annual.id);
  assert.equal(plan.status, "CONFIRMED");
  assert.equal(plan.class_id, klass.id);
  await rejects(
    putAnnualMonth(annual.id, 3, { theme: "금지", sub_themes: [] }),
    409,
    "ALREADY_CONFIRMED",
    [],
  );
  assert.equal(read().plans.length, 1);
});
