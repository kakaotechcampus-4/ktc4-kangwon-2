/**
 * 연간계획안 만들기 화면 (/plans/annual/new?format=…).
 *
 * 방식은 쿼리로 오고, 월별 주제형은 `form_id: null`(기본 양식), 놀이 중심형은 `form_id` 를 보내지 않는다.
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
const apiClient = await import("../lib/api/client.ts");
const onboarding = await import("../lib/api/onboarding.ts");
const session = await import("../lib/auth/request-session.ts");
const settingsLib = await import("../lib/onboarding/settings.ts");
const onboardingTypes = await import("../lib/onboarding/types.ts");
const workspaceModel = await import("../lib/workspace/model.ts");
const { fixtureAccount, fixtureKey, fixtureSession } = await import("./auth-fixture.mjs");

const SOURCE = readFileSync(
  new URL("../components/plan-generator/PlanGeneratorPage.tsx", import.meta.url),
  "utf8",
).replace(/\r\n/g, "\n");

const jsx = (type, props, key) => ({ type, props, key });
const runtime = { jsx, jsxs: jsx, Fragment: "fragment" };
const settle = () => new Promise((resolve) => setImmediate(resolve));
/** onClick 은 `void generate()` 라 기다릴 수 없다 — fetch 가 몇 번 오갈 때까지 돌린다. */
const drain = async () => {
  for (let i = 0; i < 20; i++) await settle();
};
const json = (body, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
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
function page(t, { format = "MONTHLY_THEME", hold = null, conflict = false } = {}) {
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
    location: { search: "" },
    scrollTo: () => {},
  });
  assert.equal(settingsLib.saveClassSettings(SETTINGS), true);

  const calls = [];
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (path, options = {}) => {
    const method = options.method ?? "GET";
    calls.push({
      path: String(path),
      method,
      body: options.body ? JSON.parse(options.body) : null,
      runId: new Headers(options.headers).get("X-Generation-Run-Id"),
    });
    if (String(path) === "/api/centers" && method === "POST") return json({ id: 7 });
    if (String(path) === "/api/centers/7/classes" && method === "POST") return json({ id: 31 });
    if (String(path) === "/api/plans/annual" && method === "POST") {
      if (hold) await hold;
      if (conflict)
        return json(
          {
            error: {
              code: "ALREADY_EXISTS",
              message: "이 반의 연간계획안이 이미 있습니다.",
              fields: ["class_id"],
            },
          },
          409,
        );
      const { format } = JSON.parse(options.body);
      return json({ id: 99, class_id: 31, school_year: 2026, status: "DRAFT", format }, 201);
    }
    throw new Error("unexpected request: " + method + " " + path);
  };
  const replaced = [];
  const compact = [];

  const slots = [],
    setters = [],
    effects = [];
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
      useEffect: (fn) => {
        const index = cursor++;
        effects[index] ??= { cleanup: fn() };
      },
    },
    "react/jsx-runtime": runtime,
    "next/navigation": { useRouter: () => ({ replace: (to) => replaced.push(to) }) },
    "next/image": { __esModule: true, default: "img" },
    "next/link": { __esModule: true, default: "a" },
    // 409 ALREADY_EXISTS 를 가르려면 ApiError 로 instanceof 를 해야 한다.
    "@/lib/api/client": apiClient,
    "@/lib/api/plans": plansApi,
    "@/lib/api/onboarding": onboarding,
    "@/lib/api/generationRuns": { newRunId: () => "run-1" },
    "@/lib/auth/request-session": session,
    "@/lib/workspace/model": workspaceModel,
    "@/lib/workspace/document-archive": { schoolYearOf: () => 2026 },
    "@/lib/hooks/use-client-state": { useClientState: (read) => [read()] },
    "@/lib/plan-generator/context": {
      classAnnualContext: () => ({}),
      saveAnnualContext: () => {},
    },
    "@/lib/onboarding/settings": settingsLib,
    "@/lib/onboarding/types": onboardingTypes,
    "@/components/plan-ui/GenerationRing": {
      __esModule: true,
      default: "generation-ring",
      ringFinished: async () => {},
    },
    "./PlanMemo": { PlanMemoField: () => null, memoError: () => null },
    "./AnnualFrame": { BACK_BUTTON: "back", BACK_ICON: null },
    "@/components/app/compact-shell": { useCompactShell: (on) => compact.push(on) },
    "@/components/workspace/WorkspaceUI": { Tape: () => null },
    "@/components/app/Tour": { SlideTour: () => null },
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
    tree = resolve(Page({ format }));
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
    compact: () => compact.at(-1),
    text: () => content(tree),
    node: (type) => all(tree).find((n) => n.type === type),
    button: (label) => all(tree).find((n) => n.type === "button" && content(n) === label),
    created: () =>
      calls.find(({ path, method }) => path === "/api/plans/annual" && method === "POST"),
  };
}

test("월별 주제형은 기본 양식(form_id: null)으로 만들고 다듬기 화면으로 간다", async (t) => {
  const p = page(t);
  assert.match(p.text(), /햇살반/);
  p.button("연간계획안 만들기").props.onClick();
  await drain();
  assert.deepEqual(p.created().body, { class_id: 31, format: "MONTHLY_THEME", form_id: null });
  assert.deepEqual(p.replaced, ["/plans/annual/99"]);
});

test("놀이 중심형은 form_id 를 보내지 않고, 만드는 동안 원형 진행 화면을 보여 준다", async (t) => {
  let release;
  const p = page(t, {
    format: "PLAY_PROJECT",
    hold: new Promise((r) => {
      release = r;
    }),
  });
  p.button("연간계획안 만들기").props.onClick();
  await drain();
  p.render();
  const ring = p.node("generation-ring");
  assert.ok(ring);
  assert.equal(p.compact(), true, "만드는 동안은 사이드바를 접는다");
  // 진행률은 서버가 주지 않는다 — 넘기지 않으면 고리가 스스로 돈다.
  assert.equal(ring.props.progress, undefined);
  assert.deepEqual(ring.props.steps, [
    ["generate", "놀이 떠올리기"],
    ["check", "겹치는 놀이 살펴보기"],
    ["save", "문서로 정리하기"],
  ]);
  assert.equal(ring.props.done, false);
  // POST 헤더와 링이 같은 id 를 쓴다 — 링이 이 id 로 서버 단계를 묻는다.
  assert.equal(p.created().runId, "run-1");
  assert.equal(ring.props.runId, "run-1");
  release();
  await drain();
  assert.deepEqual(p.created().body, { class_id: 31, format: "PLAY_PROJECT" });
  assert.deepEqual(p.replaced, ["/plans/annual/99"]);
});

test("반에 연간이 이미 있으면(409) 지우지 않고 「새로 만들기」를 물어본다", async (t) => {
  const p = page(t, { conflict: true });
  p.button("연간계획안 만들기").props.onClick();
  await drain();
  p.render();
  assert.match(p.text(), /이 반의 연간계획안이 이미 있습니다/);
  assert.ok(p.button("새로 만들기"));
  assert.ok(p.button("그대로 두기"));
  assert.equal(p.calls.filter(({ method }) => method === "DELETE").length, 0);
  assert.deepEqual(p.replaced, []);
});

test("방식 없이 들어오면 만들지 않고 첫 화면으로 보낸다", (t) => {
  const p = page(t, { format: null });
  assert.equal(p.button("연간계획안 만들기"), undefined);
  assert.equal(p.node("a").props.href, "/plans");
});
