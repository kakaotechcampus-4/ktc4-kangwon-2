/**
 * 관찰 기록 · 관찰일지 화면. 실제 TSX 를 React 흉내 위에서 돌려 이벤트와 state 를 본다
 * (documents-server.test.mjs 의 편집기 시험과 같은 방식). 브라우저 E2E 는 아니다.
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { createRequire, registerHooks } from "node:module";
import { existsSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

registerHooks({
  resolve(spec, ctx, next) {
    if (spec.startsWith("@/")) {
      const u = new URL("../" + spec.slice(2) + ".ts", import.meta.url);
      if (existsSync(fileURLToPath(u))) return { url: u.href, shortCircuit: true };
    }
    if (spec.startsWith(".") && ctx.parentURL) {
      const u = new URL(spec + ".ts", ctx.parentURL);
      if (existsSync(fileURLToPath(u))) return { url: u.href, shortCircuit: true };
    }
    return next(spec, ctx);
  },
});

const { invalidFields } = await import("../lib/api/client.ts");

const require = createRequire(import.meta.url);
const jsx = (type, props, key) => ({ type, props, key });
const runtime = { jsx, jsxs: jsx, Fragment: "fragment" };
function compile(path, modules) {
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
  const out = { exports: {} };
  new Function("require", "module", "exports", code)(
    (name) => {
      assert.ok(name in modules, `unhandled import: ${name}`);
      return modules[name];
    },
    out,
    out.exports,
  );
  return out.exports;
}

const all = (node) => {
  if (Array.isArray(node)) return node.flatMap(all);
  if (node === null || node === undefined || typeof node === "boolean") return [];
  return typeof node === "object" ? [node, ...all(node.props?.children)] : [node];
};
const textOf = (node) =>
  all(node)
    .filter((part) => typeof part === "string" || typeof part === "number")
    .join("");

/** React 흉내 — hook 자리를 컴포넌트 경로 + key 로 나누고, 함수 컴포넌트를 펼친다. */
function host() {
  const boxes = new Map();
  const effects = new Map();
  const queue = [];
  let scope = "";
  const box = () => {
    if (!boxes.has(scope)) boxes.set(scope, { slots: [], cursor: 0 });
    return boxes.get(scope);
  };
  const useState = (initial) => {
    const b = box();
    const i = b.cursor++;
    if (!(i in b.slots)) b.slots[i] = typeof initial === "function" ? initial() : initial;
    return [
      b.slots[i],
      (next) => (b.slots[i] = typeof next === "function" ? next(b.slots[i]) : next),
    ];
  };
  const useEffect = (fn, deps) => {
    const key = `${scope}#${box().cursor++}`;
    const prev = effects.get(key);
    if (prev && deps && deps.every((d, i) => Object.is(d, prev.deps[i]))) return;
    const next = { deps };
    effects.set(key, next);
    queue.push(() => {
      prev?.cleanup?.();
      next.cleanup = fn();
    });
  };
  const react = {
    useState,
    useEffect,
    useMemo: (fn) => fn(),
    useRef: (current) => useState(() => ({ current }))[0],
  };
  const resolve = (node, path) => {
    if (Array.isArray(node)) return node.map((n) => resolve(n, path));
    if (!node || typeof node !== "object") return node;
    if (typeof node.type === "function") {
      const outer = scope;
      scope = `${path}/${node.type.name}#${node.key ?? ""}`;
      box().cursor = 0;
      const out = node.type(node.props);
      const id = scope;
      scope = outer;
      return resolve(out, id);
    }
    return { ...node, props: { ...node.props, children: resolve(node.props?.children, path) } };
  };
  return {
    react,
    mount(Page, props = {}) {
      let tree;
      const render = () => {
        scope = "";
        box().cursor = 0;
        tree = resolve(Page(props), "");
      };
      const nodes = () => all(tree).filter((n) => typeof n === "object");
      const button = (label) =>
        nodes().find((n) => n.type === "button" && textOf(n.props.children) === label);
      render();
      return {
        render,
        nodes,
        button,
        text: () => textOf(tree),
        async flush() {
          for (let i = 0; i < 4; i++) {
            render();
            queue.splice(0).forEach((fn) => fn());
            await new Promise((r) => setImmediate(r));
          }
          render();
        },
        async press(label) {
          const found = button(label);
          assert.ok(found, `button: ${label}`);
          await found.props.onClick({ preventDefault() {} });
          render();
        },
        type(node, value) {
          node.props.onChange({ target: { value } });
          render();
        },
      };
    },
  };
}

const TODAY = "2026-11-09";
const DOMAINS = ["신체운동·건강", "의사소통", "사회관계", "예술경험", "자연탐구"];
const ROOMS = [
  {
    id: "class-a",
    name: "햇살반",
    children: [
      { id: "kid-1", name: "김하늘" },
      { id: "kid-2", name: "박서아" },
    ],
  },
  { id: "class-b", name: "별빛반", children: [{ id: "kid-9", name: "이달" }] },
];
const RECORD = {
  id: "observation:1",
  classId: "class-a",
  childId: "kid-2",
  childName: "박서아",
  date: "2026-11-02",
  domain: "자연탐구",
  context: "바깥놀이",
  fact: "개미를 오래 보았다.",
};
const common = (react) => ({
  "react/jsx-runtime": runtime,
  react,
  "next/link": { __esModule: true, default: "link" },
  "@/lib/workspace/model": { today: () => TODAY, validDate: (v) => /^\d{4}-\d{2}-\d{2}$/.test(v) },
  "@/lib/hooks/use-client-state": { useClientState: (read) => react.useState(read) },
  "@/lib/hooks/use-observation-domains": { useObservationDomains: () => DOMAINS },
  "@/lib/onboarding/settings": {
    chosenClassFor: () => ({ id: "class-a" }),
    loadClassSettings: () => ({}),
  },
  "@/components/app/Posty": { Posty: "posty" },
  "@/components/app/ChildPicker": { ChildNote: "child-note" },
  "@/components/app/icons": { Icon: "icon" },
  "@/lib/workspace/domain-look": { DOMAIN_LOOK: {} },
});
function browser(t, search = "") {
  globalThis.window = {
    location: { search },
    scrollTo() {},
    history: { pushState() {}, back() {} },
    addEventListener() {},
    removeEventListener() {},
  };
  globalThis.document = { addEventListener() {}, removeEventListener() {} };
  t.after(() => {
    delete globalThis.window;
    delete globalThis.document;
  });
}

// ── 관찰 기록 (RecordsPage) ────────────────────────────────────────────────

function recordsPage(t) {
  browser(t);
  const app = host();
  const warned = [];
  const Page = compile("../components/workspace/RecordsPage.tsx", {
    ...common(app.react),
    "@/lib/hooks/use-unsaved-warning": { useUnsavedWarning: (on) => warned.push(on) },
    "@/lib/api/client": { isUnauthenticated: () => false, invalidFields },
    "@/lib/api/records": {
      listRecords: async () => [RECORD],
      addRecord: async () => ({}),
      editRecord: async () => ({}),
      removeRecord: async () => {},
    },
    "@/lib/workspace/child-mark": { markFor: () => 0 },
    "./WorkspaceUI": {
      WorkspacePage: "page",
      Empty: "empty",
      Message: "message",
      useClasses: () => ROOMS,
      ws: {},
    },
    "./WorkspaceViewState": {
      WorkspaceViewState: "view-state",
      FieldError: "field-error",
      fieldErrorProps: () => ({}),
    },
  }).default;
  const view = app.mount(Page);
  const fact = () => view.nodes().find((n) => n.props["aria-label"] === "본 대로 적기");
  const date = () => view.nodes().find((n) => n.props["aria-label"] === "날짜");
  const pickedDomain = () =>
    view.nodes().find((n) => n.props["aria-pressed"] === true && DOMAINS.includes(textOf(n)));
  /** 쌓인 기록 카드를 펼친다. */
  const open = () => {
    view
      .nodes()
      .find((n) => n.props["aria-expanded"] !== undefined && textOf(n).includes(RECORD.fact))
      .props.onClick();
    view.render();
  };
  const links = () => view.nodes().filter((n) => n.type === "link");
  return { ...view, warned, fact, date, pickedDomain, open, links };
}

test("F1 「그만두기」는 고치기 전 날짜 · 영역 · 아이로 되돌린다", async (t) => {
  const view = recordsPage(t);
  await view.flush();
  view.type(view.date(), "2026-11-05");
  await view.press("의사소통");
  await view.press("김하늘");
  view.open();
  await view.press("고치기");
  assert.equal(view.date().props.value, RECORD.date);
  assert.equal(textOf(view.pickedDomain()), RECORD.domain);

  await view.press("그만두기");
  assert.equal(view.date().props.value, "2026-11-05");
  assert.equal(textOf(view.pickedDomain()), "의사소통");
  assert.match(view.text(), /하늘이가/);
  assert.equal(view.fact().props.value, "");
});

test("F2 적던 글이 있으면 고치기 전에 화면 안에서 묻고, 버리기로 해야 덮는다", async (t) => {
  const view = recordsPage(t);
  await view.flush();
  view.type(view.fact(), "적던 새 글");
  view.open();
  // window.confirm 은 없다 — 부르면 여기서 터진다.
  await view.press("고치기");
  assert.equal(view.fact().props.value, "적던 새 글");
  assert.ok(view.button("버리고 고치기"));

  await view.press("계속 쓰기");
  assert.equal(view.button("버리고 고치기"), undefined);
  assert.equal(view.fact().props.value, "적던 새 글");

  await view.press("고치기");
  await view.press("버리고 고치기");
  assert.equal(view.fact().props.value, RECORD.fact);
});

test("F3 적던 글이 있으면 떠날 때 경고하고, 관찰일지 길도 먼저 묻는다", async (t) => {
  const view = recordsPage(t);
  await view.flush();
  assert.equal(view.warned.at(-1), false);
  const journal = () => view.links().find((n) => textOf(n).includes("관찰일지 만들기"));
  let stopped = false;
  journal().props.onClick({ preventDefault: () => (stopped = true) });
  assert.equal(stopped, false, "적은 게 없으면 그냥 간다");

  view.type(view.fact(), "적던 새 글");
  assert.equal(view.warned.at(-1), true);
  journal().props.onClick({ preventDefault: () => (stopped = true) });
  view.render();
  assert.equal(stopped, true);
  assert.ok(view.links().some((n) => textOf(n) === "버리고 나가기"));
});

test("F11 관찰일지로 가는 길이 반을 들고 간다", async (t) => {
  const view = recordsPage(t);
  await view.flush();
  await view.press("김하늘");
  const head = view.links().find((n) => textOf(n).includes("관찰일지 만들기"));
  assert.equal(head.props.href, "/records/journal?child=kid-1&class=class-a");
  view.open();
  const card = view.links().find((n) => textOf(n) === "이 기록으로 일지 만들기");
  assert.equal(card.props.href, "/records/journal?record=observation%3A1&class=class-a");
});
