import assert from "node:assert/strict";
import { test } from "node:test";
import { createRequire } from "node:module";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const jsx = (type, props, key) => ({ type, props, key });
const runtime = { jsx, jsxs: jsx, Fragment: "fragment" };
const esModule = (value) => ({ __esModule: true, default: value });
function compile(path, modules, document) {
  const source = readFileSync(new URL(path, import.meta.url), "utf8");
  const code = require("next/dist/compiled/babel/core").transformSync(source, {
    filename: fileURLToPath(new URL(path, import.meta.url)),
    babelrc: false,
    configFile: false,
    presets: [
      [require("next/dist/compiled/babel/preset-env"), { targets: { node: "current" } }],
      [require("next/dist/compiled/babel/preset-react"), { runtime: "automatic" }],
      require("next/dist/compiled/babel/preset-typescript"),
    ],
  }).code;
  const compiled = { exports: {} };
  new Function("require", "module", "exports", "document", code)(
    (name) => {
      if (name === "react/jsx-runtime") return runtime;
      assert.ok(name in modules, "unhandled import: " + name);
      return modules[name];
    },
    compiled,
    compiled.exports,
    document,
  );
  return compiled.exports;
}
function resolve(node) {
  if (Array.isArray(node)) return node.map(resolve);
  if (!node || typeof node !== "object") return node;
  if (typeof node.type === "function") return resolve(node.type(node.props));
  return { ...node, props: { ...node.props, children: resolve(node.props.children) } };
}
function all(node) {
  if (Array.isArray(node)) return node.flatMap(all);
  if (!node || typeof node !== "object") return [];
  return [node, ...all(node.props?.children)];
}
function text(node) {
  if (Array.isArray(node)) return node.map(text).join("");
  if (node && typeof node === "object") return text(node.props?.children);
  return typeof node === "string" || typeof node === "number" ? String(node) : "";
}
function plan() {
  const cell = (value) => ({ value, evidence: [], generation: { method: "RULE_LLM" } });
  return {
    id: 41,
    class_id: 8,
    school_year: 2026,
    status: "DRAFT",
    format: "PLAY_PROJECT",
    format_version: "play-project-layout-v0.2.0",
    periods: ["3월~5월", "6월~8월", "9월~11월", "12월~2월"].map((label, period) => ({
      period_key: "period" + period,
      label,
      months: [],
      candidates: Array.from({ length: 10 }, (_, i) => ({
        row_key: "cand" + i,
        play_name: cell("놀이 " + i),
        materials: cell("종이 상자"),
        support_direction: cell("관심을 따라 돕습니다."),
        learning: cell("배움 한 줄\n배움 두 줄"),
      })),
    })),
  };
}
const css = Object.fromEntries(
  ["page", "badge", "notice", "stack", "card", "eyebrow", "primary"].map((key) => [key, key]),
);
const resultStyles = new Proxy({}, { get: (_target, key) => String(key) });
const resultTabs = {
  steps: "steps",
  reached: "reached",
  tabs: "tabs",
  wrappingTabs: "wrappingTabs",
  activeTab: "active",
};
function resultRenderer(planValue, initial = []) {
  const state = [...initial];
  const focused = [];
  const tabListRef = { current: null };
  let cursor = 0;
  const useState = (value) => {
    const index = cursor++;
    if (!(index in state)) state[index] = typeof value === "function" ? value() : value;
    return [
      state[index],
      (next) => (state[index] = typeof next === "function" ? next(state[index]) : next),
    ];
  };
  const { default: Result } = compile(
    "../components/plan-generator/PlayProjectResult.tsx",
    {
      react: { useState, useRef: () => tabListRef, useEffect: () => {} },
      "@/components/workspace/Workspace.module.css": esModule(css),
      "./GenerationFlow.module.css": esModule(resultTabs),
      "./PlayProjectResult.module.css": esModule(resultStyles),
    },
    { getElementById: (id) => ({ focus: () => focused.push(id) }) },
  );
  const render = () => {
    cursor = 0;
    return resolve(jsx(Result, { plan: planValue }));
  };
  return { render, state, focused };
}
function playResult() {
  return compile("../components/plan-generator/PlayProjectResult.tsx", {
    react: {
      useState: (value) => [typeof value === "function" ? value() : value, () => {}],
      useRef: (value) => ({ current: value }),
      useEffect: () => {},
    },
    "@/components/workspace/Workspace.module.css": esModule(css),
    "./GenerationFlow.module.css": esModule(resultTabs),
    "./PlayProjectResult.module.css": esModule(resultStyles),
  });
}

test("PlayProjectResult shows notices, accessible period tabs, and ten complete candidates", () => {
  const { default: Result } = playResult();
  const tree = resolve(jsx(Result, { plan: plan() }));
  const nodes = all(tree);
  const rendered = text(tree);
  assert.match(rendered, /놀이 프로젝트형은 아직 확정 · 내려받기를 할 수 없어요\./);
  assert.match(rendered, /이 반은 월간 · 주간계획안을 만들 수 없어요\./);
  const tabs = nodes.filter((node) => node.props?.role === "tab");
  assert.deepEqual(tabs.map(text), [
    "3월~5월 · 0/5",
    "6월~8월 · 0/5",
    "9월~11월 · 0/5",
    "12월~2월 · 0/5",
  ]);
  assert.equal(tabs.filter((tab) => tab.props["aria-selected"]).length, 1);
  const panel = nodes.find((node) => node.props?.role === "tabpanel");
  assert.equal(panel.props.tabIndex, 0);
  assert.equal(panel.props["aria-labelledby"], tabs[0].props.id);
  assert.ok(tabs.every((tab) => tab.props["aria-controls"] === panel.props.id));
  const cards = nodes.filter((node) => node.type === "article");
  assert.equal(cards.length, 10);
  const checkboxes = nodes.filter((node) => node.type === "input");
  assert.equal(checkboxes.length, 10);
  assert.equal(checkboxes[2].props["aria-label"], "후보 3 고르기");
  assert.equal(text(nodes.find((node) => node.type === "h2")), "놀이 0");
  for (const label of ["지원매체", "내용 및 지원 방향 예상하기", "놀이를 통한 배움", "배움 한 줄"])
    assert.ok(text(cards[0]).includes(label));
  assert.equal(
    nodes
      .filter((node) => node.type === "button")
      .some((node) => /수정|확정|내려받기|저장/.test(text(node))),
    false,
  );
  assert.match(
    rendered,
    /고른 놀이는 아직 저장되지 않아요\. 새로고침하면 처음부터 다시 골라야 해요\./,
  );
});

test("pick helper enforces five picks in pick order and preview rows preserve that order", () => {
  const { togglePlayPick, buildPlayProjectPreviewRows } = playResult();
  const selected = ["cand3", "cand1", "cand8", "cand2", "cand9"];
  assert.deepEqual(togglePlayPick([], "cand3"), ["cand3"]);
  assert.deepEqual(togglePlayPick(selected, "cand4"), selected);
  assert.deepEqual(togglePlayPick(selected, "cand1"), ["cand3", "cand8", "cand2", "cand9"]);
  const rows = buildPlayProjectPreviewRows(plan(), { period0: ["cand3", "cand1"] });
  assert.deepEqual(
    rows.slice(0, 2).map((row) => row.candidate.play_name.value),
    ["놀이 3", "놀이 1"],
  );
  assert.equal(rows[0].rowSpan, 2);
  assert.equal(rows[1].rowSpan, undefined);
  assert.equal(rows[2].period.label, "6월~8월");
  assert.equal(rows[2].rowSpan, 1);
  assert.equal(rows[2].candidate, null);
});

test("floating next clears the bottom nav and leaves the left sidebar to CSS", () => {
  const { floatingNextBottom } = playResult();
  assert.equal(floatingNextBottom({ top: 795, height: 105 }), 117);
  assert.equal(floatingNextBottom({ top: 0, height: 900 }), null);
});

test("floating next observes nav size, updates its bottom, and disconnects", (t) => {
  const effects = [];
  const state = [0, 0, { period0: ["cand0", "cand1", "cand2", "cand3", "cand4"] }, null];
  const button = { style: {} };
  const nav = { getBoundingClientRect: () => ({ top: 795, height: 105 }) };
  const observer = { observe: t.mock.fn(), disconnect: t.mock.fn() };
  let cursor = 0;
  let resize;
  const original = globalThis.ResizeObserver;
  t.after(() => {
    if (original === undefined) delete globalThis.ResizeObserver;
    else globalThis.ResizeObserver = original;
  });
  globalThis.ResizeObserver = function (callback) {
    resize = callback;
    return observer;
  };
  const { default: Result } = compile(
    "../components/plan-generator/PlayProjectResult.tsx",
    {
      react: {
        useState: () => [state[cursor++], () => {}],
        useRef: () => ({ current: button }),
        useEffect: (effect) => effects.push(effect),
      },
      "@/components/workspace/Workspace.module.css": esModule(css),
      "./GenerationFlow.module.css": esModule(resultTabs),
      "./PlayProjectResult.module.css": esModule(resultStyles),
    },
    { querySelector: (selector) => (assert.equal(selector, 'aside[aria-label="주 메뉴"]'), nav) },
  );
  Result({ plan: plan() });
  const cleanup = effects[0]();
  assert.equal(button.style.bottom, "117px");
  assert.deepEqual(
    observer.observe.mock.calls.map((call) => call.arguments),
    [[nav]],
  );
  nav.getBoundingClientRect = () => ({ top: 0, height: 900 });
  resize();
  assert.equal(button.style.bottom, "");
  cleanup();
  assert.equal(observer.disconnect.mock.callCount(), 1);
});

test("phone period tabs use two grid columns in the 767px media block", () => {
  const source = readFileSync(
    new URL("../components/plan-generator/GenerationFlow.module.css", import.meta.url),
    "utf8",
  );
  const mobile = source.split("@media (max-width: 767px) {")[1].split("@media")[0];
  const wrapping = mobile.match(/\.wrappingTabs\s*\{([^}]+)\}/)[1];
  assert.match(wrapping, /display:\s*grid\s*;/);
  assert.match(wrapping, /grid-template-columns:\s*repeat\(2,\s*minmax\(0,\s*1fr\)\)\s*;/);
});

test("next period helper skips full periods and wraps in period order", () => {
  const { nextPlayProjectPeriod } = playResult();
  const full = ["cand0", "cand1", "cand2", "cand3", "cand4"];
  const picks = { period0: full, period2: full };
  assert.equal(nextPlayProjectPeriod(plan(), picks, 2), 3);
  assert.equal(nextPlayProjectPeriod(plan(), picks, 3), 1);
  picks.period3 = full;
  assert.equal(nextPlayProjectPeriod(plan(), picks, 2), 1);
  picks.period1 = full;
  assert.equal(nextPlayProjectPeriod(plan(), picks, 2), null);
});

test("a full active period shows one floating next button that switches tabs and scrolls up", () => {
  const full = ["cand0", "cand1", "cand2", "cand3", "cand4"];
  const view = resultRenderer(plan(), [0, 0, { period0: full }, null]);
  let nodes = all(view.render());
  let floating = nodes.filter((node) => node.props?.className?.includes("floatingNext"));
  assert.equal(floating.length, 1);
  assert.equal(floating[0].type, "button");
  assert.equal(text(floating[0]), "다음: 6월~8월 고르기 →");
  assert.ok(floating[0].props.className.includes("primary"));
  assert.ok(
    nodes
      .find((node) => node.props?.role === "tabpanel")
      .props.className.includes("panelWithFloating"),
  );
  floating[0].props.onClick();
  nodes = all(view.render());
  assert.equal(text(nodes.find((node) => node.props?.["aria-selected"])), "6월~8월 · 0/5");
  assert.equal(nodes.filter((node) => node.props?.className?.includes("floatingNext")).length, 0);
  nodes
    .find((node) => node.props?.role === "tab" && text(node) === "3월~5월 · 5/5")
    .props.onClick();
  nodes = all(view.render());
  let scrolled;
  nodes.find((node) => node.props?.role === "tablist").props.ref.current = {
    scrollIntoView: (options) => {
      scrolled = options;
    },
  };
  floating = nodes.filter((node) => node.props?.className?.includes("floatingNext"));
  floating[0].props.onClick();
  assert.deepEqual(scrolled, { block: "start" });
});

test("floating next focuses the newly active period tab", () => {
  const full = ["cand0", "cand1", "cand2", "cand3", "cand4"];
  const view = resultRenderer(plan(), [0, 0, { period0: full }, null]);
  const nodes = all(view.render());
  nodes.find((node) => node.props?.className?.includes("floatingNext")).props.onClick();
  const activeTab = all(view.render()).find((node) => node.props?.["aria-selected"]);
  assert.equal(text(activeTab), "6월~8월 · 0/5");
  assert.deepEqual(view.focused, [activeTab.props.id]);
});

test("all four full periods show only the floating arrangement button and none in step two", () => {
  const full = ["cand0", "cand1", "cand2", "cand3", "cand4"];
  const picks = Object.fromEntries(plan().periods.map((period) => [period.period_key, full]));
  const view = resultRenderer(plan(), [2, 0, picks, null]);
  let nodes = all(view.render());
  const floating = nodes.filter((node) => node.props?.className?.includes("floatingNext"));
  assert.equal(floating.length, 1);
  assert.equal(floating[0].type, "button");
  assert.equal(text(floating[0]), "배치하고 다듬기로 →");
  assert.equal(
    nodes.some((node) => node.type === "button" && text(node).startsWith("다음:")),
    false,
  );
  floating[0].props.onClick();
  nodes = all(view.render());
  assert.ok(nodes.some((node) => node.type === "table"));
  assert.deepEqual(view.focused, [nodes.find((node) => node.props?.role === "tabpanel").props.id]);
  assert.equal(nodes.filter((node) => node.props?.className?.includes("floatingNext")).length, 0);
  assert.ok(
    !nodes
      .find((node) => node.props?.role === "tabpanel")
      .props.className.includes("panelWithFloating"),
  );
});

test("an active period with fewer than five picks has no floating button or extra padding", () => {
  const view = resultRenderer(plan(), [
    0,
    0,
    { period0: ["cand0", "cand1", "cand2", "cand3"] },
    null,
  ]);
  const nodes = all(view.render());
  assert.equal(nodes.filter((node) => node.props?.className?.includes("floatingNext")).length, 0);
  assert.ok(
    !nodes
      .find((node) => node.props?.role === "tabpanel")
      .props.className.includes("panelWithFloating"),
  );
});

test("five picks disable the remaining candidates and unpicking opens a slot", () => {
  const view = resultRenderer(plan());
  let nodes = all(view.render());
  for (const checkbox of nodes.filter((node) => node.type === "input").slice(0, 5)) {
    checkbox.props.onChange();
    nodes = all(view.render());
  }
  let checkboxes = nodes.filter((node) => node.type === "input");
  assert.equal(checkboxes.filter((node) => node.props.checked).length, 5);
  assert.equal(checkboxes.filter((node) => node.props.disabled).length, 5);
  assert.ok(
    nodes.some((node) => text(node).includes("5개를 모두 골랐어요. 바꾸려면 하나를 빼 주세요.")),
  );
  assert.ok(nodes.some((node) => node.props?.role === "tab" && text(node) === "3월~5월 · 5/5"));
  checkboxes.find((node) => node.props.checked).props.onChange();
  nodes = all(view.render());
  checkboxes = nodes.filter((node) => node.type === "input");
  assert.equal(checkboxes.filter((node) => node.props.checked).length, 4);
  assert.equal(checkboxes.filter((node) => node.props.disabled).length, 0);
  assert.equal(
    nodes.some((node) => text(node).includes("5개를 모두 골랐어요.")),
    false,
  );
});

test("selected preview cells sync the read-only viewer, field chips, highlight, and unsaved notice", () => {
  const view = resultRenderer(plan(), [0, 0, { period0: ["cand2"] }, null]);
  let nodes = all(view.render());
  nodes
    .find((node) => node.type === "button" && text(node) === "② 배치하고 다듬기")
    .props.onClick();
  nodes = all(view.render());
  const playNameCell = nodes.find(
    (node) => node.type === "button" && node.props["aria-label"] === "놀이 2 놀이명",
  );
  playNameCell.props.onClick();
  nodes = all(view.render());
  let textarea = nodes.find((node) => node.type === "textarea");
  assert.equal(textarea.props.value, "놀이 2");
  assert.equal(textarea.props.readOnly, true);
  assert.equal(textarea.props.disabled, undefined);
  assert.ok(
    nodes.some((node) => node.type === "label" && node.props.htmlFor === textarea.props.id),
  );
  const highlighted = nodes.filter((node) => node.props?.className?.includes("selectedCell"));
  assert.equal(highlighted.length, 1);
  assert.equal(highlighted[0].type, "td");
  assert.equal(highlighted[0].props.children.type, "button");
  assert.equal(highlighted[0].props.children.props["aria-pressed"], true);
  assert.equal(highlighted[0].props.children.props["aria-label"], "놀이 2 놀이명");
  assert.ok(!highlighted[0].props.children.props.className.includes("selectedCell"));
  assert.ok(nodes.some((node) => text(node) === "아직 수정 기능은 제공하지 않아요."));
  assert.ok(nodes.some((node) => text(node).includes("고른 놀이는 아직 저장되지 않아요.")));
  nodes.find((node) => node.type === "button" && text(node) === "지원매체").props.onClick();
  nodes = all(view.render());
  textarea = nodes.find((node) => node.type === "textarea");
  assert.equal(textarea.props.value, "종이 상자");
  assert.ok(
    nodes.some(
      (node) =>
        node.type === "td" &&
        node.props.children.props["aria-label"] === "놀이 2 지원매체" &&
        node.props.children.props["aria-pressed"] &&
        node.props.className.includes("selectedCell"),
    ),
  );
});

test("switching period clears a selected preview cell", () => {
  const view = resultRenderer(plan(), [0, 1, { period0: ["cand2"] }, null]);
  let nodes = all(view.render());
  nodes
    .find((node) => node.type === "button" && node.props["aria-label"] === "놀이 2 놀이명")
    .props.onClick();
  nodes = all(view.render());
  assert.ok(nodes.some((node) => node.type === "textarea"));
  nodes.find((node) => node.type === "button" && text(node) === "6월~8월 · 0/5").props.onClick();
  nodes = all(view.render());
  assert.equal(
    nodes.some((node) => node.type === "textarea"),
    false,
  );
  assert.ok(
    nodes.some((node) => text(node).includes("오른쪽 문서의 칸을 누르면 여기에서 볼 수 있어요.")),
  );
});

test("un-picking a play clears its selected preview cell", () => {
  const view = resultRenderer(plan(), [0, 0, { period0: ["cand2"] }, null]);
  let nodes = all(view.render());
  nodes
    .find((node) => node.type === "button" && text(node) === "② 배치하고 다듬기")
    .props.onClick();
  nodes = all(view.render());
  nodes
    .find((node) => node.type === "button" && node.props["aria-label"] === "놀이 2 놀이명")
    .props.onClick();
  nodes = all(view.render());
  assert.ok(nodes.some((node) => node.type === "textarea"));
  nodes.find((node) => node.type === "button" && text(node) === "① 놀이 고르기").props.onClick();
  nodes = all(view.render());
  nodes.filter((node) => node.type === "input")[2].props.onChange();
  nodes = all(view.render());
  nodes
    .find((node) => node.type === "button" && text(node) === "② 배치하고 다듬기")
    .props.onClick();
  nodes = all(view.render());
  assert.equal(
    nodes.some((node) => node.type === "textarea"),
    false,
  );
  assert.ok(
    nodes.some((node) => text(node).includes("오른쪽 문서의 칸을 누르면 여기에서 볼 수 있어요.")),
  );
});

test("PlayProjectResult does not use browser storage", () => {
  const source = readFileSync(
    new URL("../components/plan-generator/PlayProjectResult.tsx", import.meta.url),
    "utf8",
  );
  assert.doesNotMatch(source, /localStorage|sessionStorage|indexedDB/i);
});

test("AnnualResult routes a PLAY_PROJECT response to PlayProjectResult", async () => {
  const pp = plan();
  const state = [];
  const effects = [];
  let cursor = 0;
  const stateHook = (initial) => {
    const index = cursor++;
    if (!(index in state)) state[index] = typeof initial === "function" ? initial() : initial;
    return [
      state[index],
      (value) => (state[index] = typeof value === "function" ? value(state[index]) : value),
    ];
  };
  const { default: Result } = compile("../components/plan-generator/AnnualResult.tsx", {
    react: { useState: stateHook, useEffect: (effect) => effects.push(effect) },
    "next/navigation": { useRouter: () => ({ push: () => {} }) },
    "@/components/app/AppHeader": esModule(({ title, description }) =>
      jsx("app-header", { title, description }),
    ),
    "@/lib/api/plans": { getAnnualPlan: async () => pp },
    "@/lib/plan-generator/context": {
      loadAnnualContext: () => {
        throw new Error("PLAY_PROJECT should not read stored annual context");
      },
    },
    "./GenerationFlow": esModule(() => jsx("generation-flow", {})),
    "./PlayProjectResult": esModule(({ plan: loaded }) =>
      jsx("play-project-result", { id: loaded.id }),
    ),
  });
  const render = () => {
    cursor = 0;
    return resolve(jsx(Result, { id: pp.id }));
  };
  render();
  effects[0]();
  await new Promise((resolve) => setImmediate(resolve));
  const tree = render();
  const nodes = all(tree);
  assert.ok(
    nodes.some((node) => node.type === "play-project-result" && node.props.id === pp.id),
    nodes.map((node) => node.type).join(", "),
  );
  assert.equal(
    nodes.some((node) => node.type === "generation-flow"),
    false,
  );
  assert.ok(
    nodes.some(
      (node) => node.type === "app-header" && node.props.title === "연간계획안 · 놀이 프로젝트형",
    ),
  );
});
