import assert from "node:assert/strict";
import { test } from "node:test";
import { registerHooks } from "node:module";
import { existsSync } from "node:fs";
import { fileURLToPath } from "node:url";

// 설정 화면에서 성품인사 칸은 뺐다(2026-11-06). 서버 계약(api-spec)은 그대로라 목업이 계약을 따르는지만 본다.
registerHooks({
  resolve(spec, ctx, next) {
    const url = spec.startsWith("@/")
      ? new URL(`../${spec.slice(2)}.ts`, import.meta.url)
      : spec.startsWith(".") && ctx.parentURL
        ? new URL(spec + ".ts", ctx.parentURL)
        : null;
    if (url && existsSync(fileURLToPath(url))) return { url: url.href, shortCircuit: true };
    return next(spec, ctx);
  },
});

const api = await import("../lib/api/centers.ts");
const auth = await import("../lib/api/auth.ts");
const local = await import("../lib/onboarding/settings.ts");
const { EMPTY_CLASS_SETTINGS, MONTH_ORDER, DEFAULT_CHARACTER_MESSAGES } =
  await import("../lib/onboarding/types.ts");
const { fixtureAccount, fixtureKey, fixtureSession } = await import("./auth-fixture.mjs");
const serverGreetings = (enabled = false) => ({
  enabled,
  items: MONTH_ORDER.map((month) => ({ month, text: `서버 ${month}월 인사` })),
});

function browser(t) {
  const values = new Map([[fixtureKey, fixtureAccount]]);
  const storage = {
    get length() {
      return values.size;
    },
    key: (i) => [...values.keys()][i] ?? null,
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, value),
    removeItem: (key) => values.delete(key),
  };
  globalThis.localStorage = storage;
  globalThis.sessionStorage = fixtureSession();
  sessionStorage.setItem("saessak.authToken", "mock.fixture%40example.com");
  globalThis.window = Object.assign(new EventTarget(), {
    localStorage,
    sessionStorage,
    location: { search: "" },
  });
  const original = globalThis.fetch;
  t.after(() => {
    globalThis.fetch = original;
    delete globalThis.window;
    delete globalThis.localStorage;
    delete globalThis.sessionStorage;
  });
}

test("기본 설정과 enabled가 없는 기존 로컬 설정은 off다", (t) => {
  browser(t);
  assert.equal(EMPTY_CLASS_SETTINGS.characterEducationEnabled, false);
  const legacy = { ...EMPTY_CLASS_SETTINGS };
  delete legacy.characterEducationEnabled;
  localStorage.setItem("saessak.classSettings:fixture%40example.com", JSON.stringify(legacy));
  assert.equal(local.loadClassSettings().characterEducationEnabled, false);
});

test("MSW도 최초 off, 12개월 저장, off 문구 보존과 잘못된 월 거절 계약을 따른다", async (t) => {
  browser(t);
  const { setupServer } = await import("msw/node");
  const { handlers } = await import("../msw/handlers.ts");
  const { resetTestData } = await import("../msw/data/store.ts");
  resetTestData();
  const server = setupServer(...handlers);
  server.listen({ onUnhandledRequest: "error" });
  const mocked = globalThis.fetch;
  globalThis.fetch = (path, options) => mocked(new URL(path, "http://localhost"), options);
  t.after(() => {
    globalThis.fetch = mocked;
    server.close();
  });
  const center = await api.createCenter({
    name: "목업 원",
    director_name: "원장",
    region_sido: "세종",
    region_sigungu: "세종",
  });
  assert.equal((await auth.getCurrentUser()).center_id, center.id);
  assert.deepEqual(await api.getGreetings(center.id), {
    enabled: false,
    items: MONTH_ORDER.map((month) => ({ month, text: DEFAULT_CHARACTER_MESSAGES[month] })),
  });
  const body = serverGreetings(true);
  assert.deepEqual(await api.saveGreetings(center.id, body), body);
  assert.deepEqual(await api.getGreetings(center.id), body);
  const off = { enabled: false, items: body.items.map((item) => ({ ...item, text: "무시" })) };
  assert.deepEqual(await api.saveGreetings(center.id, off), { ...body, enabled: false });
  const bad = { ...body, items: body.items.map((item) => ({ ...item, month: 3 })) };
  await assert.rejects(api.saveGreetings(center.id, bad), (e) => e.status === 422);
  const { addCenter } = await import("../msw/data/centers.ts");
  const other = addCenter({
    name: "다른 원",
    director_name: "원장",
    region_sido: "세종",
    region_sigungu: "세종",
  });
  await assert.rejects(api.getGreetings(other.id), (e) => e.status === 404);
  await assert.rejects(api.saveGreetings(other.id, body), (e) => e.status === 404);
});
