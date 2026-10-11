import assert from "node:assert/strict";
import { test } from "node:test";
import { createRequire, registerHooks } from "node:module";
import { existsSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

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

const require = createRequire(import.meta.url);
const api = await import("../lib/api/centers.ts");
const auth = await import("../lib/api/auth.ts");
const session = await import("../lib/auth/request-session.ts");
const local = await import("../lib/onboarding/settings.ts");
const { EMPTY_CLASS_SETTINGS, MONTH_ORDER, DEFAULT_CHARACTER_MESSAGES } =
  await import("../lib/onboarding/types.ts");
const { fixtureAccount, fixtureKey, fixtureSession } = await import("./auth-fixture.mjs");
const jsx = (type, props) => ({ type, props });
const compile = (path, modules) => {
  const code = require("next/dist/compiled/babel/core").transformSync(
    readFileSync(new URL(path, import.meta.url), "utf8"),
    {
      filename: path,
      babelrc: false,
      configFile: false,
      presets: [
        [require("next/dist/compiled/babel/preset-env"), { targets: { node: "current" } }],
        [require("next/dist/compiled/babel/preset-react"), { runtime: "automatic" }],
        require("next/dist/compiled/babel/preset-typescript"),
      ],
    },
  ).code;
  const compiledModule = { exports: {} };
  new Function("require", "module", "exports", code)(
    (name) => {
      assert.ok(name in modules, name);
      return modules[name];
    },
    compiledModule,
    compiledModule.exports,
  );
  return compiledModule.exports;
};
const runtime = { jsx, jsxs: jsx, Fragment: "fragment" };
const { WorkspaceViewState } = compile("../components/workspace/WorkspaceViewState.tsx", {
  "react/jsx-runtime": runtime,
  "./WorkspaceUI": { Message: "message", ws: {} },
});
const all = (node) => {
  if (Array.isArray(node)) return node.flatMap(all);
  if (node === null || node === undefined || typeof node === "boolean") return [];
  return typeof node === "object" ? [node, ...all(node.props.children)] : [node];
};
const settle = () => new Promise((resolve) => setImmediate(resolve));
const response = (body, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
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
  const confirms = [];
  let allowed = true;
  globalThis.window = Object.assign(new EventTarget(), {
    localStorage,
    sessionStorage,
    location: { search: "" },
    confirm: (text) => {
      confirms.push(text);
      return allowed;
    },
  });
  const original = globalThis.fetch;
  t.after(() => {
    globalThis.fetch = original;
    delete globalThis.window;
    delete globalThis.localStorage;
    delete globalThis.sessionStorage;
  });
  return {
    confirms,
    allowConfirm: (value) => {
      allowed = value;
    },
  };
}

// 실제 SettingsPage의 effect와 이벤트를 실행하고 실제 API/로컬 저장 함수를 사용한다.
function page(t, { centerId = 42, failGet = false, greetings = serverGreetings() } = {}) {
  const stub = browser(t);
  const originalSettings = {
    ...EMPTY_CLASS_SETTINGS,
    orgName: "로컬 원 이름",
    directorName: "로컬 원장",
    characterEducationEnabled: true,
    characterMessages: Object.fromEntries(MONTH_ORDER.map((m) => [m, "이전 로컬 인사"])),
  };
  assert.equal(local.saveClassSettings(originalSettings), true);
  const calls = [];
  let failPut = false;
  globalThis.fetch = async (path, options = {}) => {
    const method = options.method ?? "GET";
    calls.push({ path, method, options });
    assert.equal(options.headers.get("Authorization"), "Bearer mock.fixture%40example.com");
    if (path === "/api/auth/me") return response({ id: 1, center_id: centerId });
    assert.equal(path, `/api/centers/${centerId}/greetings`);
    if ((method === "GET" && failGet) || (method === "PUT" && failPut))
      return response(
        { error: { code: "DEPENDENCY_UNAVAILABLE", message: "서버 오류", fields: [] } },
        503,
      );
    if (method === "PUT") {
      const body = JSON.parse(options.body);
      greetings = body.enabled ? body : { ...greetings, enabled: false };
    }
    return response(greetings);
  };
  const slots = [],
    setters = [],
    effects = [],
    pending = [];
  let cursor = 0,
    tree;
  const state = (initial) => {
    const index = cursor++;
    if (!(index in slots)) {
      slots[index] = typeof initial === "function" ? initial() : initial;
      setters[index] = (next) => {
        slots[index] = typeof next === "function" ? next(slots[index]) : next;
      };
    }
    return [slots[index], setters[index]];
  };
  const Page = compile("../components/auth/SettingsPage.tsx", {
    "react/jsx-runtime": runtime,
    react: {
      useState: state,
      useEffect: (fn, deps) => {
        const index = cursor++;
        if (!effects[index] || deps.some((dep, i) => !Object.is(dep, effects[index].deps[i]))) {
          effects[index]?.cleanup?.();
          effects[index] = { deps };
          pending.push(() => {
            effects[index].cleanup = fn();
          });
        }
      },
    },
    "next/link": { default: "link" },
    "@/lib/hooks/use-client-state": {
      useClientState: (read) => state(read),
      useHydrated: () => true,
    },
    "@/lib/onboarding/settings": local,
    "@/lib/onboarding/types": { EMPTY_CLASS_SETTINGS, MONTH_ORDER },
    "@/lib/api/auth": auth,
    "@/lib/api/centers": api,
    "@/lib/auth/request-session": session,
    "@/components/onboarding/OnboardingPage": { StepCharacterMessages: "character-step" },
    "@/components/workspace/WorkspaceUI": { Message: "message", WorkspacePage: "page", ws: {} },
    "@/components/workspace/WorkspaceViewState": { WorkspaceViewState },
  }).default;
  const resolve = (node) => {
    if (Array.isArray(node)) return node.map(resolve);
    if (!node || typeof node !== "object") return node;
    if (typeof node.type === "function") return resolve(node.type(node.props));
    return { ...node, props: { ...node.props, children: resolve(node.props.children) } };
  };
  const render = () => {
    cursor = 0;
    tree = resolve(Page());
  };
  const flush = async () => {
    render();
    pending.splice(0).forEach((fn) => fn());
    await settle();
    render();
  };
  t.after(() => effects.forEach((effect) => effect?.cleanup?.()));
  render();
  return {
    ...stub,
    calls,
    render,
    flush,
    step: () => all(tree).find((node) => node.type === "character-step"),
    text: () =>
      all(tree)
        .filter((node) => typeof node === "string")
        .join(""),
    fieldset: () => all(tree).find((node) => node.type === "fieldset"),
    retry: () =>
      all(tree).find((node) => node.type === "button" && node.props.children === "다시 시도"),
    failGet: (value) => {
      failGet = value;
    },
    failPut: (value) => {
      failPut = value;
    },
  };
}

test("기본 설정과 enabled가 없는 기존 로컬 설정은 off다", (t) => {
  browser(t);
  assert.equal(EMPTY_CLASS_SETTINGS.characterEducationEnabled, false);
  const legacy = { ...EMPTY_CLASS_SETTINGS };
  delete legacy.characterEducationEnabled;
  localStorage.setItem("saessak.classSettings:fixture%40example.com", JSON.stringify(legacy));
  assert.equal(local.loadClassSettings().characterEducationEnabled, false);
});

test("설정 GET 완료까지 편집을 막고 로컬 성품인사보다 서버 값을 기준으로 쓴다", async (t) => {
  const p = page(t);
  assert.equal(p.step(), undefined);
  assert.match(p.text(), /불러오고 있어요/);
  await p.flush();
  assert.deepEqual(
    p.calls.map(({ path }) => path),
    ["/api/auth/me", "/api/centers/42/greetings"],
  );
  assert.equal(p.step().props.settings.characterEducationEnabled, false);
  assert.equal(p.step().props.settings.characterMessages[3], "서버 3월 인사");
  assert.equal(p.step().props.settings.orgName, "로컬 원 이름");
});

test("설정 PUT은 12개월을 보내고 서버 성공값만 로컬에 반영하며 다른 설정을 유지한다", async (t) => {
  const p = page(t);
  await p.flush();
  const changed = { ...p.step().props.settings.characterMessages, 3: "수정한 3월 인사" };
  p.step().props.onChange({ characterEducationEnabled: true, characterMessages: changed });
  p.render();
  // 저장 대기 중 다른 화면에서 바뀐 설정도 덮어쓰지 않는다.
  local.saveClassSettings({
    ...local.loadClassSettings(),
    directorName: "다른 화면에서 수정한 원장",
  });
  const saved = p.step().props.onFinish();
  p.render();
  assert.equal(p.fieldset().props.disabled, true);
  await saved;
  p.render();
  const put = p.calls.find(({ method }) => method === "PUT");
  assert.deepEqual(JSON.parse(put.options.body), {
    enabled: true,
    items: MONTH_ORDER.map((month) => ({ month, text: changed[month] })),
  });
  const stored = local.loadClassSettings();
  assert.equal(stored.characterEducationEnabled, true);
  assert.equal(stored.characterMessages[3], changed[3]);
  assert.equal(stored.orgName, "로컬 원 이름");
  assert.equal(stored.directorName, "다른 화면에서 수정한 원장");
  assert.match(p.text(), /설정을 저장했어요/);
  assert.equal(p.fieldset().props.disabled, false);
  assert.deepEqual(p.confirms, []);
});

test("off PUT은 서버에서 보존한 문구를 화면과 로컬에 반영한다", async (t) => {
  const p = page(t, { greetings: serverGreetings(true) });
  await p.flush();
  p.step().props.onChange({
    characterEducationEnabled: false,
    characterMessages: {
      ...p.step().props.settings.characterMessages,
      3: "off 요청에서 무시할 문구",
    },
  });
  p.render();
  await p.step().props.onFinish();
  p.render();
  assert.equal(p.step().props.settings.characterMessages[3], "서버 3월 인사");
  assert.equal(local.loadClassSettings().characterMessages[3], "서버 3월 인사");
  assert.equal(local.loadClassSettings().characterEducationEnabled, false);
  // 문구를 고친 채 껐으므로 저장 전에 한 번 물었고, 계속을 골라 그대로 저장됐다.
  assert.equal(p.confirms.length, 1);
});

test("문구를 고친 채 성품교육을 끄면 저장 전에 묻고, 취소하면 서버를 부르지 않는다", async (t) => {
  const p = page(t, { greetings: serverGreetings(true) });
  await p.flush();
  p.allowConfirm(false);
  p.step().props.onChange({
    characterEducationEnabled: false,
    characterMessages: { ...p.step().props.settings.characterMessages, 3: "지키고 싶은 3월 인사" },
  });
  p.render();
  await p.step().props.onFinish();
  p.render();
  assert.deepEqual(p.confirms, [
    "성품교육을 사용하지 않으면 수정한 월별 문구는 저장되지 않아요. 계속 저장할까요?",
  ]);
  assert.equal(
    p.calls.some(({ method }) => method === "PUT"),
    false,
  );
  assert.equal(p.step().props.settings.characterMessages[3], "지키고 싶은 3월 인사");
  assert.equal(p.step().props.settings.characterEducationEnabled, false);
  assert.equal(local.loadClassSettings().characterMessages[3], "이전 로컬 인사");
  assert.equal(p.fieldset().props.disabled, false);
  assert.equal(p.text().includes("저장했어요"), false);
});

test("문구를 고치지 않고 성품교육만 끄면 묻지 않고 바로 저장한다", async (t) => {
  const p = page(t, { greetings: serverGreetings(true) });
  await p.flush();
  p.step().props.onChange({ characterEducationEnabled: false });
  p.render();
  await p.step().props.onFinish();
  p.render();
  assert.deepEqual(p.confirms, []);
  const put = p.calls.find(({ method }) => method === "PUT");
  assert.equal(JSON.parse(put.options.body).enabled, false);
  assert.equal(local.loadClassSettings().characterEducationEnabled, false);
  assert.match(p.text(), /설정을 저장했어요/);
});

test("고친 문구를 되돌려 서버 값과 같아지면 끌 때 묻지 않는다", async (t) => {
  const p = page(t, { greetings: serverGreetings(true) });
  await p.flush();
  const original = p.step().props.settings.characterMessages;
  p.step().props.onChange({ characterMessages: { ...original, 3: "잠깐 고친 3월 인사" } });
  p.render();
  p.step().props.onChange({
    characterEducationEnabled: false,
    characterMessages: { ...original, 3: "서버 3월 인사" },
  });
  p.render();
  await p.step().props.onFinish();
  p.render();
  assert.deepEqual(p.confirms, []);
  assert.match(p.text(), /설정을 저장했어요/);
});

test("PUT 실패는 입력을 보존하고 오류를 표시하며 같은 값으로 재시도한다", async (t) => {
  const p = page(t);
  await p.flush();
  p.step().props.onChange({
    characterEducationEnabled: true,
    characterMessages: { ...p.step().props.settings.characterMessages, 3: "보존할 입력값" },
  });
  p.render();
  p.failPut(true);
  await p.step().props.onFinish();
  p.render();
  assert.match(p.text(), /서버 오류/);
  assert.equal(p.step().props.settings.characterMessages[3], "보존할 입력값");
  assert.equal(local.loadClassSettings().characterMessages[3], "이전 로컬 인사");
  assert.equal(p.fieldset().props.disabled, false);
  p.failPut(false);
  await p.step().props.onFinish();
  p.render();
  assert.equal(local.loadClassSettings().characterMessages[3], "보존할 입력값");
  assert.equal(p.text().includes("서버 오류"), false);
  assert.deepEqual(p.confirms, []);
});

test("GET 실패는 로컬 값을 기준으로 저장하지 않고 재조회할 수 있다", async (t) => {
  const p = page(t, { failGet: true });
  await p.flush();
  assert.equal(p.step(), undefined);
  assert.match(p.text(), /서버 오류/);
  p.failGet(false);
  p.retry().props.onClick();
  await p.flush();
  assert.equal(p.step().props.settings.characterEducationEnabled, false);
  assert.equal(
    p.calls.some(({ method }) => method === "PUT"),
    false,
  );
});

test("등록된 원이 없으면 greetings를 호출하거나 원을 새로 만들지 않는다", async (t) => {
  const p = page(t, { centerId: null });
  await p.flush();
  assert.equal(p.step(), undefined);
  assert.match(p.text(), /원 정보를 먼저 등록/);
  assert.deepEqual(
    p.calls.map(({ path }) => path),
    ["/api/auth/me"],
  );
});

test("다른 로그인 세션으로 바뀐 뒤 늦게 온 PUT 결과는 새 계정에 저장하지 않는다", async (t) => {
  const p = page(t);
  await p.flush();
  p.step().props.onChange({ characterEducationEnabled: true });
  p.render();
  let release;
  const original = globalThis.fetch;
  globalThis.fetch = async (path, options) => {
    const result = await original(path, options);
    if (options.method === "PUT")
      await new Promise((resolve) => {
        release = resolve;
      });
    return result;
  };
  const saving = p.step().props.onFinish();
  await settle();
  sessionStorage.setItem("saessak.accountEmail", "other@example.com");
  release();
  await saving;
  assert.equal(localStorage.getItem("saessak.classSettings:other%40example.com"), null);
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
