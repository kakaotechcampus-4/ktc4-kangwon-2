// 월간 양식 설정 관리 API 클라이언트와 MSW 목업 계약 (docs/api-spec.md §9-4, BE-1 f418031).
// 실제 서버를 부르지 않는다. 목업은 한 흐름에서 돌아 DB 수준 동시성은 보여 주지 못한다 —
// 그것은 BE-1 의 PostgreSQL 테스트가 본다. 여기서는 순서 · 승인 게이트 · CAS 규칙 · 상태 연결을 본다.
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
const { addReadyProfile, approveTemplateForTest } =
  await import("../msw/data/template-profiles.ts");
const { createCenter } = await import("../lib/api/centers.ts");
const { createClass } = await import("../lib/api/classes.ts");
const { createAnnualPlan, confirmAnnualPlan } = await import("../lib/api/plans.ts");
const { createMonthlyPlan, getMonthlyPlan } = await import("../lib/api/monthly.ts");
const {
  getClassTemplateProfile,
  listReadyTemplateProfiles,
  listMonthlyTemplates,
  createTemplateProfile,
  getCenterDefaultProfile,
  putCenterDefaultProfile,
  getClassProfileOverride,
  putClassProfileOverride,
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

const TEMPLATE_ID = "ssuksak.monthly-template-a";
const PLAIN = { template_id: TEMPLATE_ID, template_version: "monthly-template-a-v0.1.1" };
const FOCUS = { template_id: TEMPLATE_ID, template_version: "monthly-template-a-v0.2.1" };
const LABELS = {
  theme: "생활주제",
  week_axis: "주",
  outdoor_play: "바깥놀이",
  safety_education: "안전교육",
  focus: "소주제",
  goals: "목표",
  basic_habit: "기본생활",
};
const labels = (...optional) =>
  Object.fromEntries(
    ["theme", "week_axis", "outdoor_play", "safety_education", ...optional].map((k) => [
      k,
      LABELS[k],
    ]),
  );
const INPUT = {
  base_template_ref: FOCUS,
  selected_optional_keys: ["focus", "goals"],
  display_labels: labels("focus", "goals"),
  focus_variant: "SUBTHEME",
};
const EMPTY = { profile_ref: null, changed_by: null, changed_at: null };

const rejects = (promise, status, code, fields) =>
  assert.rejects(promise, (e) => {
    assert.ok(e instanceof ApiError);
    assert.equal(e.status, status);
    assert.equal(e.body.error.code, code);
    assert.deepEqual(e.body.error.fields, fields);
    return true;
  });

async function world() {
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
  const otherClass = await createClass(other.id, {
    name: "달빛반",
    teacher_name: "교사",
    age_min: 5,
    age_max: 5,
    child_count: null,
  });
  return { center: center.id, other: other.id, klass: klass.id, otherClass: otherClass.id };
}
async function twoReady(w) {
  approveTemplateForTest(FOCUS);
  approveTemplateForTest(PLAIN);
  const p1 = (await createTemplateProfile(w.center, INPUT)).profile_ref;
  const p2 = (
    await createTemplateProfile(w.center, {
      base_template_ref: PLAIN,
      selected_optional_keys: ["goals"],
      display_labels: labels("goals"),
      focus_variant: null,
    })
  ).profile_ref;
  return { p1, p2 };
}

// ── 클라이언트 요청 모양 ──────────────────────────────────────────────────

test("methods, path ids, bodies keep explicit nulls, bearer token, no retry", async () => {
  const session = new Map([["saessak.authToken", "T0KEN"]]);
  const storage = {
    getItem: (k) => session.get(k) ?? null,
    setItem: (k, v) => session.set(k, v),
    removeItem: (k) => session.delete(k),
  };
  globalThis.window = { sessionStorage: storage, localStorage: storage };
  const calls = [];
  let status = 200;
  globalThis.fetch = async (url, options = {}) => {
    const headers = new Headers(options.headers);
    calls.push({
      url: String(url),
      method: options.method ?? "GET",
      raw: options.body,
      auth: headers.get("Authorization"),
      type: headers.get("Content-Type"),
    });
    const body =
      status === 200 ? "{}" : '{"error":{"code":"GENERATION_FAILED","message":"x","fields":[]}}';
    return new Response(body, { status, headers: { "Content-Type": "application/json" } });
  };
  const ref = { profile_id: "tprofile_1", profile_version: "v1" };
  await listMonthlyTemplates();
  await createTemplateProfile(4, INPUT);
  await getCenterDefaultProfile(4);
  await putCenterDefaultProfile(4, { profile_ref: ref, expected_profile_ref: null });
  await putCenterDefaultProfile(4, { profile_ref: null, expected_profile_ref: ref });
  await getClassProfileOverride(7);
  await putClassProfileOverride(7, { profile_ref: ref, expected_profile_ref: null });
  assert.deepEqual(
    calls.map((c) => [c.method, c.url, c.raw === undefined ? undefined : JSON.parse(c.raw)]),
    [
      ["GET", "/api/monthly-templates", undefined],
      ["POST", "/api/centers/4/template-profiles", INPUT],
      ["GET", "/api/centers/4/template-profile-default", undefined],
      [
        "PUT",
        "/api/centers/4/template-profile-default",
        { profile_ref: ref, expected_profile_ref: null },
      ],
      [
        "PUT",
        "/api/centers/4/template-profile-default",
        { profile_ref: null, expected_profile_ref: ref },
      ],
      ["GET", "/api/classes/7/template-profile-override", undefined],
      [
        "PUT",
        "/api/classes/7/template-profile-override",
        { profile_ref: ref, expected_profile_ref: null },
      ],
    ],
  );
  // null 은 빠뜨리지 않고 그대로 보낸다 — 서버는 키가 없으면 422 다.
  assert.ok(calls[3].raw.includes('"expected_profile_ref":null'));
  assert.ok(calls[4].raw.includes('"profile_ref":null'));
  assert.ok(calls.every((c) => c.auth === "Bearer T0KEN"));
  assert.ok(calls.every((c) => (c.raw ? c.type === "application/json" : c.type === null)));
  // 시작은 멱등이 아니라 실패해도 다시 보내지 않는다.
  status = 500;
  calls.length = 0;
  await rejects(createTemplateProfile(4, INPUT), 500, "GENERATION_FAILED", []);
  assert.equal(calls.length, 1);
});

// ── 기반 Template 목록 · 승인 게이트 ────────────────────────────────────────

test("templates list shows both as pending; only the test fixture opens one", async () => {
  await world();
  const { items } = await listMonthlyTemplates();
  assert.deepEqual(
    items.map((t) => [t.template_ref.template_version, t.approved]),
    [
      ["monthly-template-a-v0.1.1", false],
      ["monthly-template-a-v0.2.1", false],
    ],
  );
  const by = (sel) =>
    items[0].sections
      .filter((s) => s.selection === sel)
      .map((s) => s.section_key)
      .sort();
  assert.deepEqual(by("REQUIRED"), ["outdoor_play", "safety_education", "theme", "week_axis"]);
  assert.deepEqual(by("OPTIONAL"), ["basic_habit", "focus", "goals"]);
  assert.deepEqual(by("INSTITUTION_INPUT"), ["drill", "event_schedule"]);
  assert.deepEqual(by("NOT_SUPPORTED"), [
    "emergency_response",
    "indoor_alternative",
    "special_program",
  ]);
  assert.equal(items[0].sections.find((s) => s.section_key === "basic_habit").label, "habits");
  assert.deepEqual(items[0].focus_variants, ["SUBTHEME", "EXPECTED_PLAY", "WEEKLY_THEME"]);

  approveTemplateForTest(FOCUS);
  const after = (await listMonthlyTemplates()).items;
  assert.deepEqual(
    after.map((t) => t.approved),
    [false, true],
  );
});

test("unapproved template → 409 GATE_BLOCKED and nothing stored; fixture → 201 READY", async () => {
  const w = await world();
  await rejects(createTemplateProfile(w.center, INPUT), 409, "GATE_BLOCKED", ["base_template_ref"]);
  assert.equal(read().profiles.length, 0);

  approveTemplateForTest(FOCUS);
  // 승인은 Template 마다다 — 하나를 열어도 다른 것은 그대로 막힌다.
  await rejects(
    createTemplateProfile(w.center, { ...INPUT, base_template_ref: PLAIN }),
    409,
    "GATE_BLOCKED",
    ["base_template_ref"],
  );
  const created = await createTemplateProfile(w.center, INPUT);
  assert.equal(created.status, "READY");
  assert.equal(created.profile_ref.profile_version, "v1");
  assert.deepEqual(created.base_template_ref, FOCUS);
  assert.deepEqual(created.selected_optional_keys, ["focus", "goals"]);
  assert.deepEqual(
    created.sections.map((s) => [s.section_key, s.label]),
    Object.entries(labels("focus", "goals")).sort(
      (a, b) =>
        ["theme", "week_axis", "outdoor_play", "safety_education", "focus", "goals"].indexOf(a[0]) -
        ["theme", "week_axis", "outdoor_play", "safety_education", "focus", "goals"].indexOf(b[0]),
    ),
  );
  assert.deepEqual((await listReadyTemplateProfiles(w.center)).items, [created]);
  // 만들기만 한다 — 원 기본 · 해석은 그대로다.
  assert.deepEqual(await getCenterDefaultProfile(w.center), EMPTY);
  assert.equal((await getClassTemplateProfile(w.klass)).source, "SELECTION_REQUIRED");
  // 멱등이 아니다.
  const again = await createTemplateProfile(w.center, INPUT);
  assert.notEqual(again.profile_ref.profile_id, created.profile_ref.profile_id);
});

test("start input validation mirrors the server (422, nothing stored)", async () => {
  const w = await world();
  approveTemplateForTest(FOCUS);
  const cases = [
    [{ selected_optional_keys: ["focus", "unknown"] }, ["selected_optional_keys"]],
    [{ selected_optional_keys: ["focus", "theme"] }, ["selected_optional_keys"]],
    [{ selected_optional_keys: ["focus", "focus"] }, ["selected_optional_keys"]],
    [{ selected_optional_keys: ["focus", "habits"] }, ["selected_optional_keys"]],
    [{ selected_optional_keys: ["focus", "event_schedule"] }, ["selected_optional_keys"]],
    [{ selected_optional_keys: ["focus", "drill"] }, ["selected_optional_keys"]],
    [{ display_labels: { event_schedule: "행사" } }, ["display_labels.event_schedule"]],
    [{ display_labels: { basic_habit: "기본생활" } }, ["display_labels.basic_habit"]],
    [{ display_labels: { ...labels("focus", "goals"), focus: "  " } }, ["display_labels.focus"]],
    [{ display_labels: labels("focus") }, ["display_labels.goals"]],
    [
      { display_labels: { focus: "소주제", goals: "목표" } },
      [
        "display_labels.outdoor_play",
        "display_labels.safety_education",
        "display_labels.theme",
        "display_labels.week_axis",
      ],
    ],
    [{ focus_variant: null }, ["focus_variant"]],
    [{ focus_variant: "NEUTRAL" }, ["focus_variant"]],
    [
      {
        selected_optional_keys: ["goals"],
        display_labels: labels("goals"),
        focus_variant: "SUBTHEME",
      },
      ["focus_variant"],
    ],
    [
      { base_template_ref: { template_id: "", template_version: "x" } },
      ["base_template_ref.template_id"],
    ],
  ];
  for (const [overrides, fields] of cases)
    await rejects(
      createTemplateProfile(w.center, { ...INPUT, ...overrides }),
      422,
      "VALIDATION_FAILED",
      fields,
    );
  await rejects(
    createTemplateProfile(w.center, {
      ...INPUT,
      base_template_ref: { ...FOCUS, template_version: "monthly-template-a-v9.9.9" },
    }),
    404,
    "NOT_FOUND",
    ["base_template_ref"],
  );
  await rejects(createTemplateProfile(w.other, INPUT), 404, "NOT_FOUND", ["center_id"]);
  assert.equal(read().profiles.length, 0);
});

// ── CAS ────────────────────────────────────────────────────────────────────

test("center default: set, stale 409 keeps data, move, clear, invalid clear, not-READY 404", async () => {
  const w = await world();
  const { p1, p2 } = await twoReady(w);
  assert.deepEqual(await getCenterDefaultProfile(w.center), EMPTY);

  const first = await putCenterDefaultProfile(w.center, {
    profile_ref: p1,
    expected_profile_ref: null,
  });
  assert.deepEqual(first.profile_ref, p1);
  assert.equal(first.changed_by, 1);
  assert.ok(first.changed_at);
  assert.deepEqual(await getCenterDefaultProfile(w.center), first);

  const before = structuredClone(read().defaultPointers);
  await rejects(
    putCenterDefaultProfile(w.center, { profile_ref: p2, expected_profile_ref: null }),
    409,
    "STALE_WRITE",
    ["expected_profile_ref"],
  );
  await rejects(
    putCenterDefaultProfile(w.center, { profile_ref: null, expected_profile_ref: p2 }),
    409,
    "STALE_WRITE",
    ["expected_profile_ref"],
  );
  await rejects(
    putCenterDefaultProfile(w.center, { profile_ref: null, expected_profile_ref: null }),
    422,
    "VALIDATION_FAILED",
    ["expected_profile_ref"],
  );
  assert.deepEqual(read().defaultPointers, before);

  const moved = await putCenterDefaultProfile(w.center, {
    profile_ref: p2,
    expected_profile_ref: p1,
  });
  assert.deepEqual(moved.profile_ref, p2);
  assert.deepEqual(
    await putCenterDefaultProfile(w.center, { profile_ref: null, expected_profile_ref: p2 }),
    EMPTY,
  );
  assert.deepEqual(await getCenterDefaultProfile(w.center), EMPTY);

  // DRAFT · ARCHIVED · 남의 원 READY 는 가리킬 수 없다(없는 것과 같다).
  const theirs = addReadyProfile(w.other, INPUT).profile_ref;
  commit((db) => {
    db.profiles.push(
      {
        center_id: w.center,
        status: "DRAFT",
        profile: {
          ...db.profiles[0].profile,
          profile_ref: { profile_id: "draft", profile_version: "v2" },
        },
      },
      {
        center_id: w.center,
        status: "ARCHIVED",
        profile: {
          ...db.profiles[0].profile,
          profile_ref: { profile_id: "old", profile_version: "v1" },
        },
      },
    );
  });
  for (const target of [
    theirs,
    { profile_id: "draft", profile_version: "v2" },
    { profile_id: "old", profile_version: "v1" },
  ])
    await rejects(
      putCenterDefaultProfile(w.center, { profile_ref: target, expected_profile_ref: null }),
      404,
      "NOT_FOUND",
      ["profile_ref"],
    );
  assert.deepEqual(read().defaultPointers, {});
  // 남의 원 경로 · 입력 모양.
  await rejects(getCenterDefaultProfile(w.other), 404, "NOT_FOUND", ["center_id"]);
  await rejects(
    putCenterDefaultProfile(w.other, { profile_ref: theirs, expected_profile_ref: null }),
    404,
    "NOT_FOUND",
    ["center_id"],
  );
  const r = await fetch("http://localhost/api/centers/" + w.center + "/template-profile-default", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ profile_ref: p1 }),
  });
  assert.equal(r.status, 422);
  assert.deepEqual((await r.json()).error.fields, ["expected_profile_ref"]);
});

test("class override wins over the default, clears back to it, and is center-scoped", async () => {
  const w = await world();
  const { p1, p2 } = await twoReady(w);
  await putCenterDefaultProfile(w.center, { profile_ref: p1, expected_profile_ref: null });
  assert.deepEqual(await getClassProfileOverride(w.klass), EMPTY);

  const set = await putClassProfileOverride(w.klass, {
    profile_ref: p2,
    expected_profile_ref: null,
  });
  assert.deepEqual(set.profile_ref, p2);
  assert.deepEqual(await getClassProfileOverride(w.klass), set);
  assert.deepEqual(await getClassTemplateProfile(w.klass), {
    source: "CLASSROOM_OVERRIDE",
    profile_ref: p2,
    reason: null,
  });
  await rejects(
    putClassProfileOverride(w.klass, { profile_ref: p1, expected_profile_ref: null }),
    409,
    "STALE_WRITE",
    ["expected_profile_ref"],
  );
  assert.deepEqual((await getClassProfileOverride(w.klass)).profile_ref, p2);
  const changed = await putClassProfileOverride(w.klass, {
    profile_ref: p1,
    expected_profile_ref: p2,
  });
  assert.deepEqual(changed.profile_ref, p1);

  // 해제는 Profile 을 지우지 않는다 — 원 기본으로 돌아간다.
  await putClassProfileOverride(w.klass, { profile_ref: null, expected_profile_ref: p1 });
  assert.deepEqual(await getClassTemplateProfile(w.klass), {
    source: "INSTITUTION_DEFAULT",
    profile_ref: p1,
    reason: null,
  });
  assert.equal((await listReadyTemplateProfiles(w.center)).items.length, 2);
  await putCenterDefaultProfile(w.center, { profile_ref: null, expected_profile_ref: p1 });
  assert.deepEqual(await getClassTemplateProfile(w.klass), {
    source: "SELECTION_REQUIRED",
    profile_ref: null,
    reason: "NO_POINTER",
  });

  await rejects(getClassProfileOverride(w.otherClass), 404, "NOT_FOUND", ["class_id"]);
  await rejects(
    putClassProfileOverride(w.otherClass, { profile_ref: p1, expected_profile_ref: null }),
    404,
    "NOT_FOUND",
    ["class_id"],
  );
  const theirs = addReadyProfile(w.other, INPUT).profile_ref;
  await rejects(
    putClassProfileOverride(w.klass, { profile_ref: theirs, expected_profile_ref: null }),
    404,
    "NOT_FOUND",
    ["profile_ref"],
  );
  assert.deepEqual(read().overridePointers, {});
});

// ── 연간 → Profile → 월간 (같은 목업 상태) ───────────────────────────────────

test("profile set through the API drives monthly creation after the annual gate", async () => {
  const w = await world();
  const { p1, p2 } = await twoReady(w);
  await putCenterDefaultProfile(w.center, { profile_ref: p1, expected_profile_ref: null });
  const resolved = await getClassTemplateProfile(w.klass);
  assert.equal(resolved.source, "INSTITUTION_DEFAULT");

  const annual = await createAnnualPlan({ class_id: w.klass, form_id: null });
  const body = { class_id: w.klass, month: 9, profile_ref: resolved.profile_ref };
  await rejects(createMonthlyPlan(body), 409, "GATE_BLOCKED", ["class_id"]);
  await confirmAnnualPlan(annual.id);
  const september = await createMonthlyPlan(body);
  assert.deepEqual(september.profile_ref, p1);
  assert.deepEqual(september.base_template_ref, FOCUS);
  assert.ok(september.sections.some((s) => s.section_key === "focus"));

  // override 를 걸면 다음 달은 그 Profile 의 칸 모양이다. 이미 만든 계획안은 그대로다.
  await putClassProfileOverride(w.klass, { profile_ref: p2, expected_profile_ref: null });
  const next = (await getClassTemplateProfile(w.klass)).profile_ref;
  const october = await createMonthlyPlan({ ...body, month: 10, profile_ref: next });
  assert.deepEqual(october.profile_ref, p2);
  assert.deepEqual(october.base_template_ref, PLAIN);
  assert.deepEqual(
    october.sections.map((s) => s.section_key),
    ["theme", "week_axis", "outdoor_play", "safety_education", "goals"],
  );
  assert.deepEqual((await getMonthlyPlan(september.id)).profile_ref, p1);

  // 남의 원 Profile 로는 만들 수 없다.
  const theirs = addReadyProfile(w.other, INPUT).profile_ref;
  await rejects(createMonthlyPlan({ ...body, month: 11, profile_ref: theirs }), 404, "NOT_FOUND", [
    "profile_ref",
  ]);
});
