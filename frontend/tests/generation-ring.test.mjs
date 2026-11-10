/**
 * 생성 중 링 — 시간으로 차지 않고 서버 단계(docs/api-spec.md §9-8)로만 찬다.
 * ① `watchStage`(조회 사슬) ② 링이 단계를 받아 그리는 것.
 */
import assert from "node:assert/strict";
import { test, mock } from "node:test";
import { createRequire } from "node:module";
import { readFileSync } from "node:fs";

const require = createRequire(import.meta.url);
function load(path, modules) {
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
  const m = { exports: {} };
  new Function("require", "module", "exports", code)((n) => modules[n] ?? require(n), m, m.exports);
  return m.exports;
}
const settle = () => new Promise((resolve) => setImmediate(resolve));
const flush = async () => {
  for (let i = 0; i < 5; i++) await settle();
};
const fail = (status) => Object.assign(new Error("조회 실패 " + status), { status });

/** 가짜 `apiRequest` — 부른 횟수와 신호를 적고, 정해 둔 답을 차례로 준다. */
function watcher(replies) {
  const calls = [];
  const api = load("../lib/api/generationRuns.ts", {
    "./client": {
      apiRequest: async (path, options) => {
        calls.push({ path, signal: options?.signal });
        const next = replies[calls.length - 1];
        if (next instanceof Error) throw next;
        return next;
      },
    },
  });
  return { calls, watchStage: api.watchStage, api };
}

test("헤더 도우미: id 가 있을 때만 붙고, 없으면 아무것도 붙이지 않는다", () => {
  const { api } = watcher([]);
  assert.equal(api.RUN_HEADER, "X-Generation-Run-Id");
  assert.deepEqual(api.runHeaders("abc"), { "X-Generation-Run-Id": "abc" });
  assert.deepEqual(api.runHeaders(undefined), {});
  assert.match(api.newRunId(), /^[0-9a-f-]{36}$/);
});

test("watchStage: 404 · 500 은 삼키고 단계만 전하며, 끝나면 더 묻지 않는다", async (t) => {
  mock.timers.enable({ apis: ["setTimeout"] });
  t.after(() => mock.timers.reset());
  const { calls, watchStage } = watcher([
    fail(404),
    { status: "RUNNING", stage: "generate" },
    fail(500),
    { status: "RUNNING", stage: "check" },
    { status: "SUCCEEDED", stage: "save" },
  ]);
  const stages = [];
  const finished = watchStage("run-1", (s) => stages.push(s), new AbortController().signal);
  for (let i = 0; i < 5; i++) {
    mock.timers.tick(2000);
    await flush();
  }
  await finished;
  assert.deepEqual(stages, ["generate", "check", "save"]);
  assert.equal(calls.length, 5);
  assert.equal(calls[0].path, "/api/generation-runs/run-1");
  mock.timers.tick(10000);
  await flush();
  assert.equal(calls.length, 5, "끝난 뒤로는 묻지 않는다");
});

test("watchStage: 끊으면 그 뒤 조회도 콜백도 없다", async (t) => {
  mock.timers.enable({ apis: ["setTimeout"] });
  t.after(() => mock.timers.reset());
  const { calls, watchStage } = watcher(Array(9).fill({ status: "RUNNING", stage: "generate" }));
  const stages = [];
  const ctl = new AbortController();
  const finished = watchStage("run-2", (s) => stages.push(s), ctl.signal);
  mock.timers.tick(2000);
  await flush();
  assert.equal(calls.length, 1);
  assert.deepEqual(stages, ["generate"]);
  ctl.abort();
  mock.timers.tick(2000);
  await flush();
  await finished;
  assert.equal(calls.length, 1);
  assert.deepEqual(stages, ["generate"]);

  // 첫 기다림 도중에 끊어도 한 번도 묻지 않는다.
  const early = watcher([{ status: "RUNNING", stage: "generate" }]);
  const ctl2 = new AbortController();
  const waiting = early.watchStage("run-3", (s) => stages.push(s), ctl2.signal);
  ctl2.abort();
  mock.timers.tick(2000);
  await flush();
  await waiting;
  assert.equal(early.calls.length, 0);
});

// ---- 링 그리기 -------------------------------------------------------------------------------

const R = 120;
const C = 2 * Math.PI * R;
const FOUR = [
  ["prepare", "6월 놀이 이어받기"],
  ["generate", "함께 할 활동 정하기"],
  ["check", "살펴보고 다듬기"],
  ["save", "문서로 정리하기"],
];

/** 진짜 GenerationRing.tsx 를 돈다. React 는 칸 하나씩 흉내 내고 `watchStage` 는 받은 콜백을 밖으로 넘긴다. */
function ring(t, props) {
  const watched = [];
  const slots = [],
    effects = [];
  let cursor = 0,
    tree;
  const state = (initial) => {
    const index = cursor++;
    if (!(index in slots)) slots[index] = typeof initial === "function" ? initial() : initial;
    const set = (next) => {
      slots[index] = typeof next === "function" ? next(slots[index]) : next;
    };
    return [slots[index], set];
  };
  const jsx = (type, p, key) => ({ type, props: p, key });
  const { default: Ring } = load("../components/plan-ui/GenerationRing.tsx", {
    react: {
      useState: state,
      useEffect: (fn) => {
        const index = cursor++;
        effects[index] ??= { cleanup: fn() };
      },
    },
    "react/jsx-runtime": { jsx, jsxs: jsx, Fragment: "fragment" },
    "@/lib/api/generationRuns": {
      watchStage: (id, onStage, signal) => watched.push({ id, onStage, signal }),
    },
    "@/components/workspace/WorkspaceUI": { Tape: () => null },
  });
  const resolve = (node) => {
    if (Array.isArray(node)) return node.map(resolve);
    if (!node || typeof node !== "object") return node;
    if (typeof node.type === "function") return resolve(node.type(node.props));
    return { ...node, props: { ...node.props, children: resolve(node.props.children) } };
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
  const render = () => {
    cursor = 0;
    tree = resolve(Ring(props));
  };
  t.after(() => effects.forEach((e) => e?.cleanup?.()));
  render();
  return {
    watched,
    render,
    text: () => content(tree),
    steps: () => all(tree).filter((n) => n.type === "li"),
    ol: () => all(tree).find((n) => n.type === "ol"),
    filled: () => all(tree).find((n) => n.type === "circle" && n.props.strokeLinecap === "round"),
    pulse: () =>
      all(tree).find((n) => n.type === "circle" && /animate-pulse/.test(n.props.className)),
    stop: () => effects.forEach((e) => e?.cleanup?.()),
  };
}

const current = (r) => r.steps().findIndex((li) => li.props["aria-current"] === "step");
const finished = (r, upto) =>
  r.steps().every((li, i) => (i < upto ? /text-ink-soft/.test(li.props.className) : true));

test("링: 서버 단계까지 끝난 칸만큼 차고 지금 칸이 맥박친다 — 앞으로만 간다", (t) => {
  const r = ring(t, { steps: FOUR, runId: "run-1" });
  assert.equal(r.watched.length, 1);
  assert.equal(r.watched[0].id, "run-1");
  assert.equal(current(r), 0, "처음에는 첫 칸");
  assert.equal(r.filled().props.strokeDashoffset, C);

  r.watched[0].onStage("check");
  r.render();
  assert.equal(current(r), 2);
  assert.ok(finished(r, 2), "앞 두 칸은 끝난 색");
  assert.ok(Math.abs(r.filled().props.strokeDashoffset - C * 0.5) < 1e-9);
  const pulse = r.pulse();
  assert.ok(pulse, "지금 칸 맥박");
  assert.match(pulse.props.className, /motion-reduce:animate-none/);
  assert.ok(Math.abs(pulse.props.strokeDashoffset + C * 0.5) < 1e-9);
  assert.equal(pulse.props.strokeDasharray, `${C / 4} ${C}`);

  // 늦게 온 옛 응답 · 모르는 키는 되돌리지 못한다.
  r.watched[0].onStage("prepare");
  r.watched[0].onStage("zzz");
  r.render();
  assert.equal(current(r), 2);
});

test("링: 네 칸이면 줄을 바꿔 좁은 화면에서 넘치지 않는다", (t) => {
  const r = ring(t, { steps: FOUR, runId: "run-1" });
  assert.match(r.ol().props.className, /flex-wrap/);
  assert.equal(r.steps().length, 4);
});

test("링: done 이면 모두 끝났고 호가 가득 차며 맥박이 없다 — 조회도 하지 않는다", (t) => {
  const r = ring(t, { steps: FOUR, runId: "run-1", done: true });
  assert.equal(r.watched.length, 0);
  assert.equal(current(r), -1);
  assert.ok(finished(r, 4));
  assert.equal(r.filled().props.strokeDashoffset, 0);
  assert.equal(r.pulse(), undefined);
});

test("링: spin 이거나 runId 가 없으면 서버에 묻지 않는다", (t) => {
  const spin = ring(t, { steps: FOUR, runId: "run-1", spin: true });
  assert.equal(spin.watched.length, 0);
  assert.equal(current(spin), -1, "spin 은 강조하는 단계가 없다");
  assert.equal(spin.pulse(), undefined);

  const none = ring(t, { steps: FOUR });
  assert.equal(none.watched.length, 0);
  assert.equal(current(none), 0, "묻지 못하면 첫 단계에 머문다");
});

test("링: 내려가면 조회를 끊는다", (t) => {
  const r = ring(t, { steps: FOUR, runId: "run-1" });
  assert.equal(r.watched[0].signal.aborted, false);
  r.stop();
  assert.equal(r.watched[0].signal.aborted, true);
});

test("링: 퍼센트 · 초가 없고 localStorage 를 건드리지 않는다", (t) => {
  const original = Object.getOwnPropertyDescriptor(globalThis, "localStorage");
  Object.defineProperty(globalThis, "localStorage", {
    configurable: true,
    get() {
      throw new Error("링이 localStorage 를 건드렸다");
    },
  });
  t.after(() => {
    if (original) Object.defineProperty(globalThis, "localStorage", original);
    else delete globalThis.localStorage;
  });
  const r = ring(t, { steps: FOUR, runId: "run-1" });
  r.watched[0].onStage("generate");
  r.render();
  assert.doesNotMatch(r.text(), /%|\d+\s*초/);
  assert.match(r.text(), /2 함께 할 활동 정하기/);
});
