import assert from "node:assert/strict";
import { test } from "node:test";
import { registerHooks } from "node:module";
import { existsSync } from "node:fs";
import { fileURLToPath } from "node:url";

registerHooks({
  resolve(spec, ctx, next) {
    const url = spec.startsWith("@/")
      ? new URL("../" + spec.slice(2) + ".ts", import.meta.url)
      : spec.startsWith(".") && ctx.parentURL
        ? new URL(spec + ".ts", ctx.parentURL)
        : null;
    if (url && existsSync(fileURLToPath(url))) return { url: url.href, shortCircuit: true };
    return next(spec, ctx);
  },
});
const { stubAuthFetch } = await import("./auth-fixture.mjs");
const auth = await import("../lib/auth/local-account.ts");
const session = await import("../lib/auth/demo-session.ts");
const settings = await import("../lib/onboarding/settings.ts");
const onboarding = await import("../lib/api/onboarding.ts");
const { API_STORAGE_CONTEXT } = await import("../lib/api/storage-context.ts");
const { EMPTY_CLASS_SETTINGS, createEmptyClassroom } = await import("../lib/onboarding/types.ts");

const EMAIL = "legacy@example.com";
const BASE = "saessak.classSettings";
const SCOPED = BASE + ":" + encodeURIComponent(EMAIL);
const LINKS = "saessak.apiLinks.v1:" + API_STORAGE_CONTEXT + ":" + encodeURIComponent(EMAIL);
const children = [
  { id: "child-local-1", name: "박서준", code: "민준" },
  { id: "child-local-2", name: "김하윤", code: "예준" },
  { id: "child-local-3", name: "이태겸", code: "도준" },
];
const legacy = {
  ...EMPTY_CLASS_SETTINGS,
  orgName: "테스트 어린이집",
  directorName: "테스트 원장",
  regionProvince: "강원특별자치도",
  regionDistrict: "춘천시",
  primaryClassId: "class-local-1",
  classes: [
    {
      ...createEmptyClassroom("class-local-1"),
      className: "햇살반",
      teacherName: "교사",
      selectedAges: [4],
      currentChildCount: 3,
      guardianConsent: true,
      children,
    },
  ],
};
const links = JSON.stringify({
  center: { id: 7, signature: "center" },
  classes: { "class-local-1": { id: 8, signature: "class" } },
  children: { "child-local-1": 11, "child-local-2": 12, "child-local-3": 13 },
});

function setup(t) {
  const values = new Map(),
    tab = new Map();
  const storage = (map) => ({
    get length() {
      return map.size;
    },
    key: (index) => [...map.keys()][index] ?? null,
    getItem: (key) => map.get(key) ?? null,
    setItem: (key, value) => map.set(key, String(value)),
    removeItem: (key) => map.delete(key),
  });
  const previous = { window: globalThis.window, localStorage: globalThis.localStorage };
  globalThis.localStorage = storage(values);
  globalThis.window = Object.assign(new EventTarget(), {
    localStorage,
    sessionStorage: storage(tab),
    location: { search: "" },
  });
  const restore = stubAuthFetch().seed(EMAIL, "test-password-123");
  t.after(() => {
    restore();
    globalThis.window = previous.window;
    globalThis.localStorage = previous.localStorage;
  });
  values.set("saessak.demoAccount", JSON.stringify({ name: "교사", email: EMAIL }));
  values.set(LINKS, links);
  return { values, tab };
}
async function login() {
  await auth.verifyAccount(EMAIL, "test-password-123");
  // Assert cleanup before any screen, loadClassSettings(), or UI session starts.
}
function assertPrivate(values, tab) {
  const dump = JSON.stringify([...values, ...tab]);
  for (const child of children)
    for (const value of [child.name, child.code]) assert.equal(dump.includes(value), false, value);
}
function assertSettings(raw, expected = legacy) {
  const saved = JSON.parse(raw);
  assert.equal(saved.orgName, expected.orgName);
  assert.equal(saved.directorName, expected.directorName);
  assert.equal(saved.regionProvince, expected.regionProvince);
  assert.equal(saved.regionDistrict, expected.regionDistrict);
  assert.equal(saved.primaryClassId, expected.primaryClassId);
  const classroom = { ...expected.classes[0] };
  delete classroom.children;
  assert.deepEqual(saved.classes[0], { ...classroom, childIds: children.map((c) => c.id) });
  assert.deepEqual(saved.characterMessages, expected.characterMessages);
}

for (const mode of ["unscoped", "scoped", "both"]) {
  test("legacy privacy: login sanitizes " + mode + " name/code before screen access", async (t) => {
    const { values, tab } = setup(t);
    if (mode !== "scoped") values.set(BASE, JSON.stringify(legacy));
    const scoped = { ...legacy, orgName: "현재 계정 어린이집" };
    if (mode !== "unscoped") values.set(SCOPED, JSON.stringify(scoped));
    await login();
    assertPrivate(values, tab);
    if (mode !== "scoped") assertSettings(values.get(BASE));
    assertSettings(values.get(SCOPED), mode === "unscoped" ? legacy : scoped);
    assert.equal(values.get(LINKS), links);
  });
}

test("legacy privacy: single-class schema retains organization, class and child IDs", async (t) => {
  const { values, tab } = setup(t);
  values.set(
    BASE,
    JSON.stringify({
      orgName: legacy.orgName,
      className: "햇살반",
      ageGroup: "4",
      children,
    }),
  );
  await login();
  assertPrivate(values, tab);
  for (const key of [BASE, SCOPED]) {
    const saved = JSON.parse(values.get(key));
    assert.equal(saved.orgName, legacy.orgName);
    assert.equal(saved.classes[0].className, "햇살반");
    assert.equal(saved.classes[0].ageGroup, "4");
    assert.deepEqual(
      saved.classes[0].childIds,
      children.map((c) => c.id),
    );
  }
  assert.equal(values.get(LINKS), links);
});

test("legacy privacy: another account keeps every non-sensitive field and ID", async (t) => {
  const { values, tab } = setup(t);
  const other = BASE + ":other%40example.com";
  const otherSettings = {
    ...legacy,
    orgName: "다른 계정",
    serverId: 42,
    customSetting: { enabled: true },
    classes: [{ ...legacy.classes[0], childIds: ["existing-id"], serverId: 43 }],
  };
  const otherRaw = JSON.stringify(otherSettings);
  values.set(other, otherRaw);
  values.set(BASE, JSON.stringify(legacy));
  await login();
  const expected = structuredClone(otherSettings);
  delete expected.classes[0].children;
  assert.deepEqual(JSON.parse(values.get(other)), expected);
  assertPrivate(values, tab);
  assert.equal(values.get(LINKS), links);
});

for (const mode of ["unscoped", "scoped", "other"]) {
  test(
    "legacy privacy: malformed " + mode + " is removed, including migrated copies",
    async (t) => {
      const { values, tab } = setup(t);
      const key = mode === "unscoped" ? BASE : mode === "scoped" ? SCOPED : BASE + ":other";
      values.set(key, '{"classes":[{"children":[{"name":"박서준","code":"민준"');
      await login();
      assert.equal(values.has(key), false);
      assert.equal(values.has(SCOPED), false);
      assertPrivate(values, tab);
    },
  );
}

for (const raw of [
  "",
  "null",
  "[]",
  '[{"name":"박서준","code":"민준"}]',
  '"박서준 민준"',
  "42",
  "true",
]) {
  test("legacy privacy: non-record value is removed: " + JSON.stringify(raw), async (t) => {
    const { values, tab } = setup(t);
    values.set(BASE, raw);
    await login();
    assert.equal(values.has(BASE), false);
    assert.equal(values.has(SCOPED), false);
    assertPrivate(values, tab);
  });
}

test("legacy privacy: all account keys are sanitized without touching unrelated keys", async (t) => {
  const { values, tab } = setup(t);
  const unrelated = new Map([
    [BASE + "Backup", "untouched"],
    ["saessak.apiLinks.v1:other", links],
    ["saessak.workspace.v1:other", '{"version":1}'],
    ["saessak.demoAccount:other", '{"email":"other@example.com"}'],
  ]);
  for (const entry of unrelated) values.set(...entry);
  values.set(BASE + ":broken-first", "{");
  for (const suffix of ["a", "b", "c"]) {
    values.set(BASE + ":" + suffix, JSON.stringify(legacy));
  }
  values.set(
    BASE + ":old-flat",
    JSON.stringify({ orgName: "옛 원", className: "옛 반", children }),
  );
  await login();
  assert.equal(values.has(BASE + ":broken-first"), false);
  for (const suffix of ["a", "b", "c"]) assertSettings(values.get(BASE + ":" + suffix));
  assert.deepEqual(JSON.parse(values.get(BASE + ":old-flat")), {
    orgName: "옛 원",
    className: "옛 반",
    childIds: children.map((child) => child.id),
  });
  for (const [key, value] of unrelated) assert.equal(values.get(key), value);
  assertPrivate(values, tab);
});

for (const operation of ["setItem", "removeItem"]) {
  test(
    "legacy privacy: another account's " + operation + " failure prevents completed login",
    async (t) => {
      const { values, tab } = setup(t);
      values.set(BASE, JSON.stringify(legacy));
      const key = BASE + ":other";
      values.set(key, operation === "setItem" ? JSON.stringify(legacy) : "{");
      const original = localStorage[operation];
      localStorage[operation] = (target, ...args) => {
        if (target === key) throw new Error("cleanup blocked");
        return original(target, ...args);
      };
      await assert.rejects(login(), /cleanup blocked/);
      assert.equal(tab.has("saessak.accountEmail"), false);
    },
  );
}

test("legacy privacy: a failed storage cleanup does not complete login", async (t) => {
  const { values, tab } = setup(t);
  values.set(BASE, JSON.stringify(legacy));
  const write = localStorage.setItem;
  localStorage.setItem = (key, value) => {
    if (key === BASE) throw new Error("storage write blocked");
    write(key, value);
  };
  await assert.rejects(login(), /storage write blocked/);
  assert.equal(tab.has("saessak.accountEmail"), false);
});

test("legacy privacy: foreign legacy owner is never copied into the current account", async (t) => {
  const { values } = setup(t);
  values.set(
    "saessak.demoAccount",
    JSON.stringify({ name: "다른 교사", email: "other@example.com" }),
  );
  values.set(BASE, JSON.stringify(legacy));
  await login();
  assert.equal(values.has(SCOPED), false);
  assertSettings(values.get(BASE));
  for (const child of children) {
    assert.equal(values.get(BASE).includes(child.name), false);
    assert.equal(values.get(BASE).includes(child.code), false);
  }
});

test("legacy privacy: hydrate once, preserve links, and repeated save/load never persists names", async (t) => {
  const { values, tab } = setup(t);
  values.set(BASE, JSON.stringify(legacy));
  await login();
  assert.equal(session.startDemoSession(), true);
  const authFetch = globalThis.fetch,
    requests = [];
  globalThis.fetch = async (url) => {
    requests.push(String(url));
    assert.equal(String(url), "/api/classes/8/children");
    return Response.json({
      items: children.map((child, index) => ({
        id: 11 + index,
        class_id: 8,
        name: child.name,
        code: child.code,
        created_at: "2026-10-01T00:00:00Z",
      })),
    });
  };
  t.after(() => {
    globalThis.fetch = authFetch;
  });
  const loaded = settings.loadClassSettings();
  assert.deepEqual(loaded.classes[0].children, []);
  const hydrated = await onboarding.hydrateClassChildren(loaded);
  assert.deepEqual(hydrated[0].children, children);
  assert.equal(requests.length, 1);
  assert.equal(values.get(LINKS), links);
  assert.equal(onboarding.classServerId("class-local-1"), 8);
  assert.deepEqual(
    children.map((c) => onboarding.childServerId(c.id)),
    [11, 12, 13],
  );
  for (let i = 0; i < 2; i++) {
    assert.equal(settings.saveClassSettings({ ...loaded, classes: hydrated }), true);
    assert.deepEqual(
      settings.loadClassSettings().classes[0].childIds,
      children.map((c) => c.id),
    );
    assertPrivate(values, tab);
  }
});

for (const status of [200, 404]) {
  test(`account switch: late roster response ${status} cannot change the new account`, async (t) => {
    const { values, tab } = setup(t);
    values.set(BASE, JSON.stringify(legacy));
    await login();
    assert.equal(session.startDemoSession(), true);
    const authFetch = globalThis.fetch;
    let finish;
    globalThis.fetch = () =>
      new Promise((resolve) => {
        finish = resolve;
      });
    t.after(() => {
      globalThis.fetch = authFetch;
    });
    const pending = onboarding.hydrateClassChildren(settings.loadClassSettings());
    const other = "other@example.com";
    values.set(
      "saessak.demoAccount:" + encodeURIComponent(other),
      JSON.stringify({ name: "다른 교사", email: other }),
    );
    tab.set("saessak.accountEmail", other);
    const otherLinks = LINKS.replace(encodeURIComponent(EMAIL), encodeURIComponent(other));
    const originalLinks = JSON.stringify({ classes: {}, children: {} });
    values.set(otherLinks, originalLinks);
    finish(
      Response.json(
        status === 200
          ? { items: [{ id: 11, class_id: 8, name: children[0].name, code: children[0].code }] }
          : { error: { code: "NOT_FOUND", message: "not found" } },
        { status },
      ),
    );
    await assert.rejects(pending);
    assert.equal(values.get(LINKS), links);
    assert.equal(values.get(otherLinks), originalLinks);
    assertPrivate(values, tab);
  });
}
