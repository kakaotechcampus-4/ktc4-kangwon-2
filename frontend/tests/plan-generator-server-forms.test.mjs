/**
 * 계획안 생성 화면의 기관 양식은 서버가 원본이다 (docs/api-spec.md §4 · §8).
 *
 * 브라우저 저장소(`workspace.templates`)를 보지 않고, 고른 양식은 `form_id` 로만 나간다.
 */
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
const plansApi = await import("../lib/api/plans.ts");
const formsApi = await import("../lib/api/forms.ts");
const onboarding = await import("../lib/api/onboarding.ts");
const session = await import("../lib/auth/request-session.ts");
const settingsLib = await import("../lib/onboarding/settings.ts");
const onboardingTypes = await import("../lib/onboarding/types.ts");
const planTypes = await import("../lib/plan-generator/types.ts");
const planDate = await import("../lib/plan-generator/date.ts");
const workspacePlans = await import("../lib/workspace/plans.ts");
const workspaceModel = await import("../lib/workspace/model.ts");
const { fixtureAccount, fixtureKey, fixtureSession } = await import("./auth-fixture.mjs");

const SOURCE = readFileSync(
  new URL("../components/plan-generator/PlanGeneratorPage.tsx", import.meta.url),
  "utf8",
).replace(/\r\n/g, "\n");

const jsx = (type, props, key) => ({ type, props, key });
const runtime = { jsx, jsxs: jsx, Fragment: "fragment" };
const settle = () => new Promise((resolve) => setImmediate(resolve));
const json = (body, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
const form = (id, name) => ({
  id,
  center_id: 7,
  name,
  filename: name,
  tables: [],
  labels: [],
  label_map: {},
  created_at: "2026-10-01T00:00:00+09:00",
});

const SETTINGS = {
  ...onboardingTypes.EMPTY_CLASS_SETTINGS,
  orgName: "햇살 어린이집",
  directorName: "원장",
  regionProvince: "세종",
  regionDistrict: "세종",
  classes: [
    {
      ...onboardingTypes.EMPTY_CLASS_SETTINGS.classes[0],
      className: "햇살반",
      teacherName: "담임",
      currentChildCount: 12,
      selectedAges: [5],
    },
  ],
};

const code = require("next/dist/compiled/babel/core").transformSync(SOURCE, {
  filename: "PlanGeneratorPage.tsx",
  babelrc: false,
  configFile: false,
  presets: [
    [require("next/dist/compiled/babel/preset-env"), { targets: { node: "current" } }],
    [require("next/dist/compiled/babel/preset-react"), { runtime: "automatic" }],
    require("next/dist/compiled/babel/preset-typescript"),
  ],
}).code;

/** 실제 TSX 를 돌린다. API 는 진짜 모듈을 쓰고 fetch 만 스텁이다. */
function page(
  t,
  { forms = [], failForms = false, settings = SETTINGS, hold = null, search = "" } = {},
) {
  const values = new Map([[fixtureKey, fixtureAccount]]);
  const storage = {
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, value),
    removeItem: (key) => values.delete(key),
  };
  globalThis.localStorage = storage;
  globalThis.sessionStorage = fixtureSession();
  sessionStorage.setItem("saessak.authToken", "mock.fixture%40example.com");
  globalThis.window = Object.assign(new EventTarget(), {
    localStorage: storage,
    sessionStorage,
    location: { search },
    scrollTo: () => {},
  });
  if (settings) assert.equal(settingsLib.saveClassSettings(settings), true);

  const calls = [];
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (path, options = {}) => {
    const method = options.method ?? "GET";
    calls.push({
      path: String(path),
      method,
      body: options.body ? JSON.parse(options.body) : null,
    });
    if (String(path) === "/api/centers" && method === "POST") return json({ id: 7 });
    if (String(path) === "/api/centers/7/forms" && method === "GET") {
      if (hold) await hold;
      return failForms
        ? json({ error: { code: "DEPENDENCY_UNAVAILABLE", message: "서버 오류", fields: [] } }, 503)
        : json({ items: forms });
    }
    if (String(path) === "/api/centers/7/classes" && method === "POST") return json({ id: 31 });
    if (String(path) === "/api/plans/annual" && method === "POST")
      return json({ id: 99, class_id: 31, school_year: 2026, status: "DRAFT", months: [] }, 201);
    throw new Error("unexpected request: " + method + " " + path);
  };
  const replaced = [];

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
  const modules = {
    react: {
      useState: state,
      useRef: (initial) => state(() => ({ current: initial }))[0],
      useMemo: (fn) => fn(),
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
    "react/jsx-runtime": runtime,
    "next/navigation": { useRouter: () => ({ replace: (to) => replaced.push(to) }) },
    "@/lib/fonts": { fontClassName: "font" },
    "@/components/app/AppHeader": { default: "app-header" },
    "@/lib/api/plans": plansApi,
    "@/lib/api/forms": formsApi,
    "@/lib/api/onboarding": onboarding,
    "@/lib/auth/request-session": session,
    "./GenerationFlow": { default: "generation-flow" },
    "@/lib/workspace/ai-client": {
      requestAI: () => {
        throw new Error("Unexpected AI call");
      },
    },
    "@/lib/workspace/plans": workspacePlans,
    "@/lib/workspace/model": workspaceModel,
    "@/components/workspace/WorkspaceUI": { useAIStatus: () => false, ws: {} },
    "@/lib/plan-generator/types": planTypes,
    "@/lib/plan-generator/context": { saveAnnualContext: () => {} },
    "@/lib/onboarding/settings": settingsLib,
    "@/lib/onboarding/types": onboardingTypes,
    "@/lib/plan-generator/date": planDate,
  };
  const compiled = { exports: {} };
  new Function("require", "module", "exports", code)(
    (name) => {
      assert.ok(name in modules, "unhandled import: " + name);
      return modules[name];
    },
    compiled,
    compiled.exports,
  );
  const Page = compiled.exports.default;

  const resolve = (node) => {
    if (Array.isArray(node)) return node.map(resolve);
    if (!node || typeof node !== "object") return node;
    if (typeof node.type === "function") return resolve(node.type(node.props));
    return { ...node, props: { ...node.props, children: resolve(node.props.children) } };
  };
  const render = () => {
    cursor = 0;
    tree = resolve(Page({}));
  };
  const all = (node) => {
    if (Array.isArray(node)) return node.flatMap(all);
    if (!node || typeof node !== "object") return [];
    return [node, ...all(node.props?.children)];
  };
  const content = (node) => {
    if (Array.isArray(node)) return node.map(content).join("");
    if (node && typeof node === "object") return content(node.props?.children);
    return typeof node === "string" || typeof node === "number" ? String(node) : "";
  };
  t.after(() => {
    globalThis.fetch = originalFetch;
    effects.forEach((effect) => effect?.cleanup?.());
    delete globalThis.window;
    delete globalThis.localStorage;
    delete globalThis.sessionStorage;
  });
  render();
  return {
    calls,
    replaced,
    render,
    flush: async () => {
      render();
      pending.splice(0).forEach((fn) => fn());
      await settle();
      render();
    },
    unmount: () => effects.forEach((effect) => effect?.cleanup?.()),
    node: (type, match) => all(tree).find((n) => n.type === type && (!match || match(n))),
    options: () => {
      const select = all(tree).find(
        (n) => n.type === "select" && !n.props.id && Array.isArray(n.props.children),
      );
      return all(select.props.children)
        .filter((n) => n.type === "option")
        .map((n) => ({ value: n.props.value, label: content(n) }));
    },
    pick: (value) => {
      all(tree)
        .find((n) => n.type === "select" && !n.props.id)
        .props.onChange({ target: { value } });
    },
    text: () => content(tree),
    alert: () => all(tree).find((n) => n.type === "p" && n.props.role === "alert"),
    select: () => all(tree).find((n) => n.type === "select" && !n.props.id),
    generate: () =>
      all(tree).find((n) => n.type === "button" && n.props.children === "계획안 생성하기"),
    chooseAge: (value) => {
      all(tree)
        .find((n) => n.type === "select" && n.props.id === "age")
        .props.onChange({ target: { value } });
    },
    chooseType: (label) => {
      all(tree)
        .find(
          (n) =>
            n.type === "button" &&
            n.props["aria-pressed"] !== undefined &&
            content(n).startsWith(label),
        )
        .props.onClick();
    },
  };
}

test("계획안 생성 화면은 브라우저 저장소의 양식 목록을 보지 않는다", () => {
  for (const banned of ["useWorkspace", "workspace.templates", "storageError"])
    assert.equal(SOURCE.includes(banned), false, banned);
  // 서버 양식 등록 화면과 같은 원 식별 흐름을 쓴다.
  for (const used of ["loadClassSettings()", "syncCenter(", "getForms(", "form_id"])
    assert.ok(SOURCE.includes(used), used);
});

test("등록된 서버 양식이 선택 목록에 이름으로 나온다", async (t) => {
  const p = page(t, { forms: [form(4, "햇살 월간계획안"), form(9, "햇살 주간계획안")] });
  assert.deepEqual(p.options(), [{ value: "", label: "쓱싹요정 기본 양식" }]);
  await p.flush();
  assert.deepEqual(p.options(), [
    { value: "", label: "쓱싹요정 기본 양식" },
    { value: "4", label: "햇살 월간계획안" },
    { value: "9", label: "햇살 주간계획안" },
  ]);
  assert.deepEqual(
    p.calls.map(({ path }) => path),
    ["/api/centers", "/api/centers/7/forms"],
  );
});

test("등록된 양식이 없어도 기본 양식을 쓸 수 있다", async (t) => {
  const p = page(t, { forms: [] });
  await p.flush();
  assert.deepEqual(p.options(), [{ value: "", label: "쓱싹요정 기본 양식" }]);
  assert.equal(p.alert(), undefined);
});

test("양식 목록 조회가 실패해도 화면은 기본 양식으로 계속 쓸 수 있다", async (t) => {
  const p = page(t, { failForms: true });
  await p.flush();
  assert.deepEqual(p.options(), [{ value: "", label: "쓱싹요정 기본 양식" }]);
  assert.match(p.text(), /서버 오류/);
  // 입력 패널과 생성 버튼이 그대로 남는다 — 화면 전체가 막히지 않는다.
  assert.ok(p.node("select", (n) => n.props.id === "age"));
  assert.ok(p.node("button", (n) => n.props.children === "계획안 생성하기"));
});

test("고른 서버 양식은 form_id 로만 나가고 기본 양식은 null 이다", async (t) => {
  const p = page(t, { forms: [form(4, "햇살 월간계획안")] });
  await p.flush();
  p.chooseAge("5");
  p.chooseType("연간");
  p.render();
  p.pick("4");
  p.render();
  await p.generate().props.onClick();
  await settle();
  const created = p.calls.find(({ path }) => path === "/api/plans/annual");
  assert.deepEqual(created.body, { class_id: 31, form_id: 4 });
  assert.deepEqual(p.replaced, ["/plans/annual/99"]);
});

test("목록에 없는 양식 번호는 그대로 보내지 않고 기본 양식으로 본다", async (t) => {
  // 옛 로컬 양식 id 와, 숫자지만 우리 원 것이 아닌 번호 둘 다 본다.
  for (const stale of ["template-local-1", "999"]) {
    const p = page(t, { forms: [form(4, "햇살 월간계획안")] });
    await p.flush();
    p.chooseAge("5");
    p.chooseType("연간");
    p.render();
    p.pick(stale);
    p.render();
    await p.generate().props.onClick();
    await settle();
    assert.deepEqual(
      p.calls.find(({ path }) => path === "/api/plans/annual").body,
      { class_id: 31, form_id: null },
      stale,
    );
  }
});

test("응답이 오기 전에 계정이 바뀌면 다른 원 양식을 그리지 않는다", async (t) => {
  let release;
  const held = new Promise((resolve) => {
    release = resolve;
  });
  const p = page(t, { forms: [form(4, "다른 원 양식")], hold: held });
  const started = p.flush();
  await settle();
  // 양식 응답이 오기 전에 다른 계정으로 바뀐다.
  sessionStorage.setItem("saessak.accountEmail", "other@example.com");
  release();
  await started;
  for (let i = 0; i < 5; i++) await settle();
  p.render();
  assert.deepEqual(p.options(), [{ value: "", label: "쓱싹요정 기본 양식" }]);
  // 계정 전환은 오류가 아니다 — 새 계정 화면에 옛 오류를 아예 남기지 않는다.
  assert.equal(p.alert(), undefined);
});

test("화면을 떠난 뒤 도착한 응답은 state 를 건드리지 않는다", async (t) => {
  let release;
  const held = new Promise((resolve) => {
    release = resolve;
  });
  const p = page(t, { forms: [form(4, "햇살 월간계획안")], hold: held });
  const started = p.flush();
  await settle();
  // 응답이 오기 전에 화면을 떠난다.
  p.unmount();
  release();
  await started;
  for (let i = 0; i < 5; i++) await settle();
  p.render();
  assert.deepEqual(p.options(), [{ value: "", label: "쓱싹요정 기본 양식" }]);
});

// ── 양식은 연간계획안에만 붙는다 · 목록을 받기 전에는 보내지 않는다 ─────────
test("연간계획안을 고르지 않으면 기관 양식을 고를 수 없고 이유를 알려준다", async (t) => {
  const p = page(t, { forms: [form(4, "햇살 월간계획안")] });
  await p.flush();
  assert.equal(p.select().props.disabled, true);
  assert.match(p.text(), /기관 양식은 연간계획안에만 적용돼요/);
  // 월간만 골라도 열리지 않는다 — 붙일 계약이 있는 건 연간뿐이다.
  p.chooseType("월간");
  p.render();
  assert.equal(p.select().props.disabled, true);
});

test("연간계획안을 고르면 기관 양식을 고를 수 있다", async (t) => {
  const p = page(t, { forms: [form(4, "햇살 월간계획안")] });
  await p.flush();
  p.chooseType("연간");
  p.render();
  assert.equal(p.select().props.disabled, false);
  assert.match(p.text(), /연간계획안 생성에 적용돼요/);
});

test("양식 목록을 받기 전에는 URL 로 지정한 양식으로 생성하지 않는다", async (t) => {
  let release;
  const held = new Promise((resolve) => {
    release = resolve;
  });
  const p = page(t, { forms: [form(4, "햇살 월간계획안")], hold: held, search: "?template=4" });
  const started = p.flush();
  await settle();
  p.chooseAge("5");
  p.chooseType("연간");
  p.render();
  // 아직 4번이 우리 원 양식인지 모른다 — 기본 양식으로 조용히 바뀌면 안 된다.
  assert.equal(p.select().props.disabled, true);
  assert.equal(p.generate().props.disabled, true);
  assert.match(p.text(), /불러오고 있어요/);
  await p.generate().props.onClick();
  await settle();
  assert.equal(
    p.calls.some(({ path }) => path === "/api/plans/annual"),
    false,
  );
  release();
  await started;
  for (let i = 0; i < 5; i++) await settle();
  p.render();
  assert.equal(p.generate().props.disabled, false, "목록이 오면 다시 만들 수 있다");
});

test("목록이 도착하면 URL 로 지정한 양식 번호가 그대로 나간다", async (t) => {
  const p = page(t, { forms: [form(4, "햇살 월간계획안")], search: "?template=4" });
  await p.flush();
  assert.equal(p.select().props.value, "4");
  p.chooseAge("5");
  p.chooseType("연간");
  p.render();
  await p.generate().props.onClick();
  await settle();
  assert.deepEqual(p.calls.find(({ path }) => path === "/api/plans/annual").body, {
    class_id: 31,
    form_id: 4,
  });
});

test("목록을 받는 중이어도 기본 양식이면 생성을 막지 않는다", async (t) => {
  let release;
  const held = new Promise((resolve) => {
    release = resolve;
  });
  const p = page(t, { forms: [form(4, "햇살 월간계획안")], hold: held });
  const started = p.flush();
  await settle();
  p.chooseAge("5");
  p.chooseType("연간");
  p.render();
  assert.equal(p.generate().props.disabled, false);
  await p.generate().props.onClick();
  await settle();
  assert.deepEqual(p.calls.find(({ path }) => path === "/api/plans/annual").body, {
    class_id: 31,
    form_id: null,
  });
  release();
  await started;
});

test("월간·주간·일간만 고르면 기관 양식이 생성 요청에 실리지 않는다", async (t) => {
  const p = page(t, { forms: [form(4, "햇살 월간계획안")], search: "?template=4" });
  await p.flush();
  p.chooseAge("5");
  p.chooseType("월간");
  p.render();
  await p.generate().props.onClick();
  p.render();
  // 연간이 아니므로 서버 생성 자체가 없고, 고른 양식 번호도 어디에도 실리지 않는다.
  assert.deepEqual(
    p.calls.map(({ path }) => path),
    ["/api/centers", "/api/centers/7/forms"],
  );
  assert.equal(JSON.stringify(p.calls).includes("form_id"), false);
  // 로컬 초안 생성기에도 양식을 넘기지 않는다 — 변환 계약이 없다.
  assert.ok(SOURCE.includes("templatePlan(type, age, period, memo, undefined, request.ageLabel)"));
  assert.ok(SOURCE.includes("template: null,"));
});
