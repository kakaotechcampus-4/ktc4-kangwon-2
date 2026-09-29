import { test } from "node:test";
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
const { createClass, getClasses } = await import("../lib/api/classes.ts");
const { createChild, getChildren, deleteChild } = await import("../lib/api/children.ts");
const { createAnnualPlan, getAnnualPlan, patchAnnualMonth, confirmAnnualPlan } =
  await import("../lib/api/plans.ts");
const { ApiError } = await import("../lib/api/client.ts");
const server = setupServer(...handlers);
test("P0 clients use real URLs: center, mixed class, children, annual, patch, confirm", async () => {
  resetTestData();
  server.listen({ onUnhandledRequest: "error" });
  const patched = globalThis.fetch;
  globalThis.fetch = (url, options) => patched(new URL(url, "http://localhost").href, options);
  try {
    const center = await createCenter({
      name: "검증 원",
      director_name: "원장",
      region_sido: "충청북도",
      region_sigungu: "충주시",
    });
    assert.equal(center.id, 1);
    assert.ok(center.created_at);
    const klass = await createClass(center.id, {
      name: "반",
      teacher_name: "교사",
      age_min: 3,
      age_max: 5,
      child_count: null,
    });
    assert.equal(klass.age_min, 3);
    assert.equal(klass.age_max, 5);
    // 목록 봉투는 { items } 하나다 — count 를 따로 주지 않는다 (§2-1).
    assert.deepEqual(await getChildren(klass.id), { items: [] });
    const child = await createChild(klass.id, { name: "검증아동" });
    assert.equal(child.class_id, klass.id);
    assert.notEqual(child.code, child.name);
    assert.equal((await getChildren(klass.id)).items.length, 1);
    assert.equal(await deleteChild(child.id), undefined);
    const plan = await createAnnualPlan({
      class_id: klass.id,
      school_year: 2026,
      source: "FROM_SCRATCH",
      upload_id: null,
    });
    assert.deepEqual(
      plan.months.map((m) => m.month),
      [3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 1, 2],
    );
    assert.deepEqual(await getAnnualPlan(plan.id), plan);
    const month = await patchAnnualMonth(plan.id, 3, { theme: "수정", sub_themes: ["놀이"] });
    assert.equal(month.source_type, "TEACHER");
    assert.equal(month.month, 3);
    assert.equal(month.months, undefined);
    assert.equal((await confirmAnnualPlan(plan.id)).status, "CONFIRMED");
    await assert.rejects(
      patchAnnualMonth(plan.id, 3, { theme: "금지", sub_themes: [] }),
      (e) => e instanceof ApiError && e.status === 409,
    );
    await assert.rejects(
      getAnnualPlan(999),
      (e) => e.status === 404 && e.body.error.code === "NOT_FOUND",
    );
  } finally {
    globalThis.fetch = patched;
    server.close();
  }
});
test("mock failure scenarios preserve data, validate bodies, and report empty confirm month", async () => {
  resetTestData();
  server.listen({ onUnhandledRequest: "error" });
  const request = (path, body, method = "POST") =>
    fetch("http://localhost/api/" + path, {
      method,
      headers: { "Content-Type": "application/json" },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    });
  try {
    let r = await request("centers", { name: "" });
    assert.equal(r.status, 422);
    assert.equal(read().centers.length, 0);
    const center = await (
      await request("centers", {
        name: "원",
        director_name: "교사",
        region_sido: "충청북도",
        region_sigungu: "충주시",
      })
    ).json();
    // 연령은 범위 두 값이고 3~5 안이며 age_min <= age_max 다 (§2).
    r = await request("centers/" + center.id + "/classes", {
      name: "반",
      teacher_name: "교사",
      age_min: 5,
      age_max: 3,
    });
    assert.equal(r.status, 422);
    r = await request("centers/" + center.id + "/classes", { name: "반", teacher_name: "교사" });
    assert.equal(r.status, 422);
    r = await request("centers/" + center.id + "/classes", {
      name: "반",
      teacher_name: "교사",
      age_min: 2,
      age_max: 3,
    });
    assert.equal(r.status, 422);
    const klass = await (
      await request("centers/" + center.id + "/classes", {
        name: "반",
        teacher_name: "교사",
        age_min: 3,
        age_max: 4,
      })
    ).json();
    r = await request("classes/" + klass.id + "/children?mockError=VALIDATION_FAILED", {
      name: "유지",
    });
    assert.equal(r.status, 422);
    assert.equal(read().children.length, 0);
    r = await request("centers/" + center.id + "/classes?mockEmpty=true", undefined, "GET");
    assert.deepEqual(await r.json(), { items: [] });
    const input = {
      class_id: klass.id,
      school_year: 2026,
      source: "FROM_SCRATCH",
      upload_id: null,
    };
    for (const [code, status] of [
      ["NO_ACTIVITIES", 503],
      ["GENERATION_FAILED", 500],
    ]) {
      r = await request("plans/annual?mockDelay=0&mockError=" + code, input);
      assert.equal(r.status, status);
      assert.equal(read().plans.length, 0);
    }
    const plan = await (await request("plans/annual?mockDelay=0", input)).json();
    r = await request(
      "plans/annual/" + plan.id + "/months/3?mockError=GENERATION_FAILED",
      { theme: "失敗", sub_themes: [] },
      "PATCH",
    );
    assert.equal(r.status, 500);
    assert.deepEqual(read().plans[0].months, plan.months);
    await request("plans/annual/" + plan.id + "/months/4", { theme: "", sub_themes: [] }, "PATCH");
    r = await request("plans/annual/" + plan.id + "/confirm");
    assert.equal(r.status, 422);
    assert.deepEqual((await r.json()).error.fields, ["months.4"]);
    assert.equal(read().plans[0].status, "DRAFT");
    r = await request(
      "centers/" + center.id + "/plan-config",
      { uses_monthly: true, weekly_location: "SEPARATE_WEEKLY", safety_edu_hours: 44 },
      "PUT",
    );
    assert.equal(r.status, 204);
  } finally {
    server.close();
  }
});

test("onboarding bridge deduplicates mounts, retains local IDs and isolates accounts", async () => {
  const { fixtureAccount, fixtureEmail, fixtureKey, fixtureSession } =
    await import("./auth-fixture.mjs");
  const values = new Map([[fixtureKey, fixtureAccount]]);
  const storage = {
    getItem: (k) => values.get(k) ?? null,
    setItem: (k, v) => values.set(k, v),
    removeItem: (k) => values.delete(k),
  };
  globalThis.localStorage = storage;
  globalThis.sessionStorage = fixtureSession();
  globalThis.window = { localStorage, sessionStorage, location: { search: "" } };
  const { syncClasses, syncClass, migrateChildren, loadServerChildren } =
    await import("../lib/api/onboarding.ts");
  const c = {
    id: "local-c",
    className: "반",
    ageGroup: "mixed",
    currentChildCount: 2,
    teacherName: "담임",
    guardianConsent: true,
    childrenSkipped: false,
    children: [{ id: "local-child", name: "기존 아동" }],
  };
  const settings = {
    orgName: "원",
    directorName: "원장",
    regionProvince: "시",
    regionDistrict: "구",
    classes: [c],
  };
  server.listen({ onUnhandledRequest: "error" });
  const patched = globalThis.fetch;
  globalThis.fetch = (url, options) => patched(new URL(url, "http://localhost").href, options);
  try {
    await Promise.all([syncClasses(settings), syncClasses(settings)]);
    assert.equal(read().centers.length, 1);
    assert.equal(read().classes.length, 1);
    await Promise.all([migrateChildren(c), migrateChildren(c)]);
    assert.equal(read().children.length, 1);
    const loaded = await loadServerChildren(c);
    assert.equal(loaded.children[0].id, "local-child");
    await syncClass(settings, { ...c, className: "변경 반" });
    await migrateChildren(c);
    assert.equal((await loadServerChildren(c)).children.length, 1);
    const other = "other@example.com";
    values.set(
      "saessak.demoAccount:" + encodeURIComponent(other),
      JSON.stringify({ ...JSON.parse(fixtureAccount), email: other }),
    );
    sessionStorage.setItem("saessak.accountEmail", other);
    await syncClasses(settings);
    assert.equal(read().centers.length, 1);
    assert.equal(read().children.length, 0);
    sessionStorage.setItem("saessak.accountEmail", fixtureEmail);
    assert.equal(read().children.length, 2);
  } finally {
    globalThis.fetch = patched;
    server.close();
    delete globalThis.window;
    delete globalThis.localStorage;
    delete globalThis.sessionStorage;
  }
});

test("age payload becomes age_min·age_max — the DB cannot store 「4세만 제외」", async () => {
  // docs/api-spec.md §2: 떨어진 조합은 범위로 채운다. classes 는 범위 컬럼이고
  // CHECK (age_min <= age_max) 가 걸려 있어 배열을 보내면 422 다.
  const { ageRangePayload } = await import("../lib/api/age-adapter.ts");
  for (const [ages, expected] of [
    [[3], { age_min: 3, age_max: 3 }],
    [[3, 4], { age_min: 3, age_max: 4 }],
    [[4, 5], { age_min: 4, age_max: 5 }],
    [[3, 5], { age_min: 3, age_max: 5 }],
    [[3, 4, 5], { age_min: 3, age_max: 5 }],
  ]) {
    const before = [...ages];
    assert.deepEqual(ageRangePayload({ selectedAges: ages }), expected);
    assert.deepEqual(ages, before); // 화면의 선택값 배열을 건드리지 않는다
  }
  assert.throws(() => ageRangePayload({ selectedAges: [] }));
  // 레거시 값도 같은 규칙으로 읽는다
  assert.deepEqual(ageRangePayload({ ageGroup: "mixed" }), { age_min: 3, age_max: 5 });
  assert.deepEqual(ageRangePayload({ ageGroup: "4" }), { age_min: 4, age_max: 4 });
});

test("보낼 때는 범위로 바뀌고, 라벨도 그 범위로 적는다", async () => {
  const { ageRangePayload } = await import("../lib/api/age-adapter.ts");
  const { ageSelectionLabel } = await import("../lib/onboarding/types.ts");
  resetTestData();
  server.listen({ onUnhandledRequest: "error" });
  const patched = globalThis.fetch;
  globalThis.fetch = (url, options) => patched(new URL(url, "http://localhost").href, options);
  try {
    const center = await createCenter({
      name: "연령 검증 원",
      director_name: "원장",
      region_sido: "충청북도",
      region_sigungu: "충주시",
    });
    for (const ages of [[3], [3, 4], [3, 5], [3, 4, 5]]) {
      const created = await createClass(center.id, {
        name: "반",
        teacher_name: "교사",
        ...ageRangePayload({ selectedAges: ages }),
        child_count: null,
      });
      assert.equal(created.age_min, Math.min(...ages));
      assert.equal(created.age_max, Math.max(...ages));
      const item = (await getClasses(center.id)).items.find((i) => i.id === created.id);
      assert.equal(item.age_min, Math.min(...ages));
      assert.equal(item.age_max, Math.max(...ages));
      assert.equal("selected_ages" in item, false);
      // 화면의 체크박스 상태는 선택값 그대로 남지만, 라벨은 저장된 범위로 적는다 —
      // 「만 3·5세반」으로 쓰면 교사가 본 것과 저장된 것이 달라진다 (docs/api-spec.md §2).
      const [low, high] = [Math.min(...ages), Math.max(...ages)];
      assert.equal(
        ageSelectionLabel(ages),
        low === high ? `만 ${low}세반` : `만 ${low}~${high}세반`,
      );
    }
  } finally {
    globalThis.fetch = patched;
    server.close();
  }
});

test("single-page annual retry keeps server data unchanged on first failure and persists retry", async () => {
  const { resetScenarioFailures } = await import("../msw/scenarios.ts");
  resetScenarioFailures();
  resetTestData();
  server.listen({ onUnhandledRequest: "error" });
  const request = (path, body, method = "POST") =>
    fetch("http://localhost/api/" + path, {
      method,
      headers: { "Content-Type": "application/json" },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    });
  try {
    const center = await (
      await request("centers", {
        name: "테스트 원",
        director_name: "원장",
        region_sido: "충청북도",
        region_sigungu: "충주시",
      })
    ).json();
    const klass = await (
      await request("centers/" + center.id + "/classes", {
        name: "반",
        teacher_name: "교사",
        age_min: 3,
        age_max: 3,
      })
    ).json();
    await request("classes/" + klass.id + "/children", { name: "테스트아동" });
    const before = structuredClone({ classes: read().classes, children: read().children });
    const plan = await (
      await request("plans/annual?mockDelay=0", {
        class_id: klass.id,
        school_year: 2026,
        source: "FROM_SCRATCH",
        upload_id: null,
      })
    ).json();
    assert.deepEqual({ classes: read().classes, children: read().children }, before);
    const url =
      "plans/annual/" +
      plan.id +
      "/months/3?mockDelay=0&mockError=GENERATION_FAILED&mockFailures=1";
    const change = { theme: "재시도한 제목", sub_themes: ["재시도 활동"] };
    assert.equal((await request(url, change, "PATCH")).status, 500);
    assert.deepEqual(read().plans[0].months, plan.months);
    const response = await request(url, change, "PATCH");
    assert.equal(response.status, 200);
    assert.equal((await response.json()).source_type, "TEACHER");
    const reloaded = await (await request("plans/annual/" + plan.id, undefined, "GET")).json();
    assert.equal(reloaded.months.find((m) => m.month === 3).theme, change.theme);
    assert.equal((await request("plans/annual/" + plan.id + "/confirm")).status, 200);
    const confirmed = await (await request("plans/annual/" + plan.id, undefined, "GET")).json();
    assert.equal(confirmed.status, "CONFIRMED");
  } finally {
    server.close();
    resetScenarioFailures();
  }
});
