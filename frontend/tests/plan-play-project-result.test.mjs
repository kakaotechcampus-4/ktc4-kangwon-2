import assert from "node:assert/strict";
import { test } from "node:test";
import { createRequire } from "node:module";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const jsx = (type, props, key) => ({ type, props, key });
const runtime = { jsx, jsxs: jsx, Fragment: "fragment" };
const esModule = (value) => ({ __esModule: true, default: value });
function compile(path, modules, document, requestAnimationFrame, window) {
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
  new Function("require", "module", "exports", "document", "requestAnimationFrame", "window", code)(
    (name) => {
      if (name === "react/jsx-runtime") return runtime;
      assert.ok(name in modules, "unhandled import: " + name);
      return modules[name];
    },
    compiled,
    compiled.exports,
    document,
    requestAnimationFrame,
    window,
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
  const focusOptions = [];
  const scrolls = [];
  const frames = [];
  const tabListRef = { current: null };
  let tree;
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
    {
      getElementById: (id) => {
        const node = all(tree).find((node) => node.props?.id === id);
        return (
          node && {
            disabled: node.props.disabled,
            focus: (options) => (focused.push(id), focusOptions.push(options)),
          }
        );
      },
    },
    (callback) => frames.push(callback),
    { scrollTo: (options) => scrolls.push(options) },
  );
  const render = () => {
    cursor = 0;
    tree = resolve(jsx(Result, { plan: planValue }));
    return tree;
  };
  return {
    render,
    state,
    focused,
    focusOptions,
    scrolls,
    flushFrames: () => frames.splice(0).forEach((frame) => frame()),
  };
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
  assert.deepEqual(nodes.filter((node) => node.props?.className === "stepButton").map(text), [
    "① 놀이 고르기",
    "② 배치하고 다듬기",
    "③ 전체 초안 보기",
  ]);
  assert.match(rendered, /놀이 프로젝트형은 아직 확정 · 내려받기를 할 수 없어요\./);
  assert.match(rendered, /놀이 프로젝트형은 아직 월간 · 주간계획안으로 이어지지 않아요\./);
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

test("movePlayPick moves up/down, keeps ends and unknown keys, and leaves input unchanged", () => {
  const { movePlayPick } = playResult();
  const picks = ["cand0", "cand1", "cand2"];
  assert.deepEqual(movePlayPick(picks, "cand1", -1), ["cand1", "cand0", "cand2"]);
  assert.deepEqual(movePlayPick(picks, "cand1", 1), ["cand0", "cand2", "cand1"]);
  assert.deepEqual(movePlayPick(picks, "cand0", -1), picks);
  assert.deepEqual(movePlayPick(picks, "cand2", 1), picks);
  assert.deepEqual(movePlayPick(picks, "unknown", -1), picks);
  assert.deepEqual(picks, ["cand0", "cand1", "cand2"]);
});

test("arrangement controls move only active-period picks and request focus after render", () => {
  const view = resultRenderer(plan(), [
    0,
    1,
    { period0: ["cand0", "cand1", "cand2"], period1: ["cand4"] },
    null,
  ]);
  let nodes = all(view.render());
  const controls = () => nodes.filter((node) => node.type === "button" && node.props["aria-label"]);
  for (let n = 1; n <= 3; n++) {
    assert.ok(controls().some((node) => node.props["aria-label"] === `${n}번째 놀이 위로`));
    assert.ok(controls().some((node) => node.props["aria-label"] === `${n}번째 놀이 아래로`));
    assert.ok(controls().some((node) => node.props["aria-label"] === `놀이 ${n - 1} 빼기`));
  }
  assert.equal(
    controls().find((node) => node.props["aria-label"] === "1번째 놀이 위로").props.disabled,
    true,
  );
  assert.equal(
    controls().find((node) => node.props["aria-label"] === "3번째 놀이 아래로").props.disabled,
    true,
  );
  for (const label of [
    "1번째 놀이 아래로",
    "2번째 놀이 위로",
    "2번째 놀이 아래로",
    "3번째 놀이 위로",
  ]) {
    assert.equal(
      controls().find((node) => node.props["aria-label"] === label).props.disabled,
      false,
      label,
    );
  }
  controls()
    .find((node) => node.props["aria-label"] === "1번째 놀이 아래로")
    .props.onClick();
  assert.deepEqual(view.focused, []);
  nodes = all(view.render());
  view.flushFrames();
  assert.deepEqual(view.state[2], { period0: ["cand1", "cand0", "cand2"], period1: ["cand4"] });
  assert.deepEqual(
    nodes.filter((node) => node.props?.className?.includes("playButton")).map(text),
    ["놀이 1", "놀이 0", "놀이 2"],
  );
  const table = nodes.find((node) => node.type === "table");
  assert.deepEqual(
    all(table)
      .filter((node) => node.props?.["aria-label"]?.endsWith(" 놀이명"))
      .map(text),
    ["놀이 1", "놀이 0", "놀이 2", "놀이 4"],
  );
  assert.ok(view.focused.at(-1).endsWith("cand0-1"));
  controls()
    .find((node) => node.props["aria-label"] === "2번째 놀이 아래로")
    .props.onClick();
  nodes = all(view.render());
  view.flushFrames();
  assert.ok(view.focused.at(-1).endsWith("cand0"));
});

test("preview row keys stay in their period positions while reordered cell contents change", () => {
  const view = resultRenderer(plan(), [
    1,
    1,
    { period1: ["cand4", "cand1"] },
    { periodKey: "period1", rowKey: "cand4", field: "materials" },
  ]);
  let nodes = all(view.render());
  const rows = () =>
    all(nodes.find((node) => node.type === "tbody")).filter((node) => node.type === "tr");
  const keys = rows().map((row) => row.key);
  assert.deepEqual(keys, [
    "period0-empty",
    "period1-0",
    "period1-1",
    "period2-empty",
    "period3-empty",
  ]);
  const firstName = () =>
    text(all(rows()[1]).find((node) => node.props?.["aria-label"]?.endsWith(" 놀이명")));
  assert.equal(firstName(), "놀이 4");
  nodes.find((node) => node.props?.["aria-label"] === "1번째 놀이 아래로").props.onClick();
  nodes = all(view.render());
  assert.deepEqual(
    rows().map((row) => row.key),
    keys,
  );
  assert.equal(firstName(), "놀이 1");
  assert.ok(
    all(rows()[2]).some(
      (node) => node.props?.["aria-label"] === "놀이 4 지원매체" && node.props["aria-pressed"],
    ),
  );
  nodes.find((node) => text(node) === "③ 전체 초안 보기").props.onClick();
  nodes = all(view.render());
  assert.deepEqual(
    rows().map((row) => row.key),
    keys,
  );
  view.state[2].period0 = ["cand0"];
  nodes = all(view.render());
  assert.deepEqual(
    rows()
      .slice(1, 3)
      .map((row) => row.key),
    ["period1-0", "period1-1"],
  );
});

test("available plays keep candidate order and add appends, focuses, and checks the same pick", () => {
  const view = resultRenderer(plan(), [0, 1, { period0: ["cand1", "cand5"] }, null]);
  let nodes = all(view.render());
  const available = () => nodes.find((node) => node.props?.["aria-label"] === "넣을 수 있는 놀이");
  const availableRows = () =>
    all(available()).filter((node) => node.props?.className === "pickedRow");
  assert.equal(text(all(available()).find((node) => node.type === "h2")), "넣을 수 있는 놀이 8");
  assert.deepEqual(
    availableRows().map((row) =>
      text(all(row).find((node) => node.props?.className === "eyebrow")),
    ),
    ["후보 1", "후보 3", "후보 4", "후보 5", "후보 7", "후보 8", "후보 9", "후보 10"],
  );
  assert.deepEqual(
    availableRows().map((row) =>
      text(all(row).find((node) => node.type === "p" && !node.props.className)),
    ),
    ["놀이 0", "놀이 2", "놀이 3", "놀이 4", "놀이 6", "놀이 7", "놀이 8", "놀이 9"],
  );
  assert.deepEqual(
    all(available())
      .filter((node) => node.type === "button")
      .map((node) => node.props["aria-label"]),
    [
      "놀이 0 넣기",
      "놀이 2 넣기",
      "놀이 3 넣기",
      "놀이 4 넣기",
      "놀이 6 넣기",
      "놀이 7 넣기",
      "놀이 8 넣기",
      "놀이 9 넣기",
    ],
  );
  nodes.find((node) => node.props?.["aria-label"] === "놀이 3 넣기").props.onClick();
  assert.deepEqual(view.focused, []);
  nodes = all(view.render());
  view.flushFrames();
  assert.deepEqual(view.state[2].period0, ["cand1", "cand5", "cand3"]);
  const pickedNames = nodes.filter((node) => node.props?.className?.includes("playButton"));
  assert.deepEqual(pickedNames.map(text), ["놀이 1", "놀이 5", "놀이 3"]);
  assert.equal(view.focused.at(-1), pickedNames[2].props.id);
  assert.ok(nodes.some((node) => node.props?.role === "tab" && text(node) === "3월~5월 · 3/5"));
  nodes.find((node) => text(node) === "① 놀이 고르기").props.onClick();
  nodes = all(view.render());
  assert.equal(
    nodes.find((node) => node.props?.["aria-label"] === "후보 4 고르기").props.checked,
    true,
  );
  nodes.find((node) => text(node) === "② 배치하고 다듬기").props.onClick();
  nodes = all(view.render());
  nodes
    .find((node) => node.props?.role === "tab" && text(node) === "6월~8월 · 0/5")
    .props.onClick();
  nodes = all(view.render());
  assert.equal(all(available()).filter((node) => node.type === "button").length, 10);
});

test("available plays disable every add at five picks and reopen the removed candidate in order", () => {
  const view = resultRenderer(plan(), [
    0,
    1,
    { period0: ["cand0", "cand2", "cand4", "cand6", "cand8"] },
    null,
  ]);
  let nodes = all(view.render());
  const availableNodes = () =>
    all(nodes.find((node) => node.props?.["aria-label"] === "넣을 수 있는 놀이"));
  let buttons = availableNodes().filter((node) => node.type === "button");
  assert.equal(buttons.length, 5);
  assert.ok(buttons.every((node) => node.props.disabled === true));
  assert.equal(
    text(availableNodes().find((node) => node.props?.role === "status")),
    "5개를 모두 골랐어요. 바꾸려면 하나를 빼 주세요.",
  );
  nodes.find((node) => node.props?.["aria-label"] === "놀이 4 빼기").props.onClick();
  nodes = all(view.render());
  buttons = availableNodes().filter((node) => node.type === "button");
  assert.deepEqual(
    buttons.map((node) => node.props["aria-label"]),
    ["놀이 1 넣기", "놀이 3 넣기", "놀이 4 넣기", "놀이 5 넣기", "놀이 7 넣기", "놀이 9 넣기"],
  );
  assert.ok(buttons.every((node) => node.props.disabled === false));
  assert.equal(
    availableNodes().some((node) => node.props?.role === "status"),
    false,
  );
});

test("remove unpicks, clears selection/count, focuses heading, and re-picking appends", () => {
  const view = resultRenderer(plan(), [
    0,
    1,
    { period0: ["cand0", "cand1", "cand2"] },
    { periodKey: "period0", rowKey: "cand1", field: "play_name" },
  ]);
  let nodes = all(view.render());
  nodes.find((node) => node.props?.["aria-label"] === "놀이 1 빼기").props.onClick();
  nodes = all(view.render());
  view.flushFrames();
  const heading = nodes.find((node) => node.type === "h2" && text(node) === "고른 놀이 2");
  assert.equal(heading.props.tabIndex, -1);
  assert.equal(view.focused.at(-1), heading.props.id);
  assert.equal(
    nodes.some((node) => node.type === "textarea"),
    false,
  );
  assert.ok(nodes.some((node) => node.props?.role === "tab" && text(node) === "3월~5월 · 2/5"));
  nodes.find((node) => text(node) === "① 놀이 고르기").props.onClick();
  nodes = all(view.render());
  const checkbox = nodes.find((node) => node.props?.["aria-label"] === "후보 2 고르기");
  assert.equal(checkbox.props.checked, false);
  checkbox.props.onChange();
  assert.deepEqual(view.state[2].period0, ["cand0", "cand2", "cand1"]);
});

test("full draft shows only short periods, plain table, tabs, and arrangement return", () => {
  const full = ["cand0", "cand1", "cand2", "cand3", "cand4"];
  const view = resultRenderer(plan(), [
    0,
    2,
    { period0: full, period1: full, period2: ["cand0", "cand1", "cand2"] },
    { periodKey: "period0", rowKey: "cand0", field: "play_name" },
  ]);
  let nodes = all(view.render());
  assert.equal(
    text(nodes.find((node) => node.props?.role === "status")),
    "9월~11월이 3개, 12월~2월이 0개예요. 확정하려면 구간마다 5개가 필요해요.",
  );
  const table = nodes.find((node) => node.type === "table");
  assert.equal(all(table).filter((node) => node.type === "button").length, 0);
  assert.equal(
    nodes.some((node) => node.props?.className?.includes("selectedCell")),
    false,
  );
  assert.equal(
    nodes.some((node) => node.props?.["aria-label"] === "고른 놀이와 선택한 칸"),
    false,
  );
  assert.equal(
    nodes.some((node) => node.props?.["aria-label"] === "넣을 수 있는 놀이"),
    false,
  );
  assert.equal(
    nodes.some((node) => node.props?.className?.includes("floatingNext")),
    false,
  );
  assert.equal(all(table).filter((node) => node.props?.scope === "col").length, 5);
  assert.deepEqual(
    all(table)
      .filter((node) => node.props?.scope === "rowgroup")
      .map((node) => node.props.rowSpan),
    [5, 5, 3, 1],
  );
  assert.ok(text(table).includes("아직 고른 놀이가 없어요"));
  const firstCells = all(table)
    .filter((node) => node.type === "td")
    .slice(0, 2)
    .map(text);
  assert.deepEqual(firstCells, ["놀이 0", "종이 상자"]);
  assert.equal(nodes.filter((node) => node.props?.role === "tab").length, 4);
  nodes
    .find((node) => node.props?.role === "tab" && text(node) === "9월~11월 · 3/5")
    .props.onClick();
  nodes = all(view.render());
  assert.equal(text(nodes.find((node) => node.type === "table")), text(table));
  assert.equal(text(nodes.find((node) => node.props?.["aria-selected"])), "9월~11월 · 3/5");
  nodes
    .find((node) => node.type === "button" && text(node) === "← 배치하고 다듬기로")
    .props.onClick();
  view.flushFrames();
  assert.deepEqual(view.scrolls, [{ top: 0 }]);
  assert.ok(
    all(view.render()).some((node) => node.props?.["aria-label"] === "고른 놀이와 선택한 칸"),
  );
});

test("full draft arrangement wrapper can shrink around the scrolling preview", () => {
  const nodes = all(resultRenderer(plan(), [0, 2, { period0: ["cand0"] }, null]).render());
  const sheet = nodes.find((node) => node.props?.["aria-label"] === "연간놀이계획안 미리보기");
  const wrapper = nodes.find(
    (node) => node.type === "div" && node.props.children?.includes?.(sheet),
  );
  assert.equal(wrapper.props.className, "draftArrangement");
  const styles = readFileSync(
    new URL("../components/plan-generator/PlayProjectResult.module.css", import.meta.url),
    "utf8",
  );
  assert.match(styles, /\.draftArrangement\s*\{[^}]*\bmin-width:\s*0\s*;/);
});

test("available plays card is glass, and reduced transparency resets it", () => {
  const nodes = all(resultRenderer(plan(), [0, 1, {}, null]).render());
  const card = nodes.find((node) => node.props?.["aria-label"] === "넣을 수 있는 놀이");
  assert.ok(card.props.className.split(" ").includes("availableCard"));
  const styles = readFileSync(
    new URL("../components/plan-generator/PlayProjectResult.module.css", import.meta.url),
    "utf8",
  );
  assert.match(styles, /\.availableCard\s*\{[^}]*\bbackdrop-filter:\s*blur/);
  assert.match(
    styles,
    /prefers-reduced-transparency:\s*reduce\)\s*\{\s*\.availableCard\s*\{[^}]*\bbackdrop-filter:\s*none/,
  );
});

test("full draft omits the shortage line when all four periods have five picks", () => {
  const full = ["cand0", "cand1", "cand2", "cand3", "cand4"];
  const picks = Object.fromEntries(plan().periods.map((period) => [period.period_key, full]));
  const nodes = all(resultRenderer(plan(), [0, 2, picks, null]).render());
  assert.equal(nodes.filter((node) => node.props?.role === "status").length, 0);
  assert.equal(
    nodes.some((node) => text(node).includes("확정하려면 구간마다 5개가 필요해요.")),
    false,
  );
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
  assert.deepEqual(view.focusOptions, [{ preventScroll: true }]);
  assert.deepEqual(view.scrolls, []);
  view.flushFrames();
  assert.deepEqual(view.scrolls, [{ top: 0 }]);
  assert.equal(nodes.filter((node) => node.props?.className?.includes("floatingNext")).length, 0);
  assert.ok(
    !nodes
      .find((node) => node.props?.role === "tabpanel")
      .props.className.includes("panelWithFloating"),
  );
});

test("changing step scrolls to the top; clicking the current step does not", () => {
  const view = resultRenderer(plan());
  const stepButton = (label) =>
    all(view.render()).find((node) => node.type === "button" && text(node) === label);
  stepButton("① 놀이 고르기").props.onClick();
  view.flushFrames();
  assert.deepEqual(view.scrolls, []);
  stepButton("③ 전체 초안 보기").props.onClick();
  view.flushFrames();
  assert.deepEqual(view.scrolls, [{ top: 0 }]);
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
