import assert from "node:assert/strict";
import { test } from "node:test";
import { registerHooks } from "node:module";
import { fixtureAccount, fixtureKey, fixtureEmail } from "./auth-fixture.mjs";
import { existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
registerHooks({
  // 상대 경로와 @/ 별칭에 .ts 를 붙여 본다. 목록을 손으로 관리하면 import 를 하나 더할
  // 때마다 여기도 고쳐야 하고, 빠뜨리면 「모듈을 찾을 수 없다」로 끝난다.
  resolve(spec, ctx, next) {
    const base = spec.startsWith("@/")
      ? new URL(`../${spec.slice(2)}.ts`, import.meta.url)
      : spec.startsWith(".") && ctx.parentURL
        ? new URL(spec + ".ts", ctx.parentURL)
        : null;
    if (base && existsSync(fileURLToPath(base))) return { url: base.href, shortCircuit: true };
    return next(spec, ctx);
  },
});
const { hasDemoSession, startDemoSession, endDemoSession, accountStorageKey } =
  await import("../lib/auth/demo-session.ts");

test("demo login survives reads and logout removes only the session", () => {
  const saved = new Map([["saessak.classSettings", "saved settings"]]);
  const session = new Map();
  globalThis.window = {
    localStorage: { getItem: (key) => saved.get(key) ?? null },
    sessionStorage: {
      getItem: (key) => session.get(key) ?? null,
      setItem: (key, value) => session.set(key, value),
      removeItem: (key) => session.delete(key),
    },
  };
  assert.equal(hasDemoSession(), false);
  saved.set(fixtureKey, fixtureAccount);
  session.set("saessak.accountEmail", fixtureEmail);
  assert.equal(startDemoSession(), true);
  assert.equal(hasDemoSession(), true);
  assert.equal(hasDemoSession(), true);
  assert.equal(endDemoSession(), true);
  assert.equal(hasDemoSession(), false);
  assert.equal(window.localStorage.getItem("saessak.classSettings"), "saved settings");
  delete globalThis.window;
});

test("active-only, missing, malformed and removed accounts cannot use shared storage", () => {
  const session = new Map();
  const saved = new Map([["saessak.classSettings", "private legacy data"]]);
  globalThis.window = {
    localStorage: { getItem: (key) => saved.get(key) ?? null },
    sessionStorage: {
      getItem: (key) => session.get(key) ?? null,
      setItem: (key, v) => session.set(key, v),
      removeItem: (key) => session.delete(key),
    },
  };
  for (const email of [null, "", "unknown@example.com", fixtureEmail]) {
    session.set("saessak.demoSession", "active");
    if (email !== null) session.set("saessak.accountEmail", email);
    saved.set(fixtureKey, "{");
    assert.equal(hasDemoSession(), false);
    assert.equal(session.has("saessak.demoSession"), false);
    assert.throws(() => accountStorageKey("saessak.classSettings"), /로그인/);
  }
  delete globalThis.window;
});

test("blocked storage and server rendering do not report a successful session", () => {
  globalThis.window = {
    get sessionStorage() {
      throw new Error("denied");
    },
  };
  assert.equal(hasDemoSession(), false);
  assert.equal(startDemoSession(), false);
  assert.equal(endDemoSession(), false);
  delete globalThis.window;
  assert.equal(hasDemoSession(), false);
  assert.equal(startDemoSession(), false);
  assert.equal(endDemoSession(), false);
});
