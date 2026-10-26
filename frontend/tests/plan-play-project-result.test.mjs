import assert from "node:assert/strict";
import { test } from "node:test";
import { createRequire } from "node:module";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const jsx = (type, props, key) => ({ type, props, key });
const runtime = { jsx, jsxs: jsx, Fragment: "fragment" };
const esModule = (value) => ({ __esModule: true, default: value });
function compile(path, modules) {
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
  new Function("require", "module", "exports", code)(
    (name) => {
      if (name === "react/jsx-runtime") return runtime;
      assert.ok(name in modules, "unhandled import: " + name);
      return modules[name];
    },
    compiled,
    compiled.exports,
  );
  return compiled.exports.default;
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
  ["page", "badge", "notice", "stack", "card", "eyebrow"].map((key) => [key, key]),
);

test("PlayProjectResult shows notices, accessible period tabs, and ten complete candidates", () => {
  const Result = compile("../components/plan-generator/PlayProjectResult.tsx", {
    react: { useState: (value) => [typeof value === "function" ? value() : value, () => {}] },
    "@/components/workspace/Workspace.module.css": esModule(css),
    "./GenerationFlow.module.css": esModule({
      tabs: "tabs",
      wrappingTabs: "wrappingTabs",
      activeTab: "active",
    }),
    "./PlayProjectResult.module.css": esModule({ meta: "meta", fields: "fields", panel: "panel" }),
  });
  const tree = resolve(jsx(Result, { plan: plan() }));
  const nodes = all(tree);
  const rendered = text(tree);
  assert.match(rendered, /놀이 프로젝트형은 아직 확정 · 내려받기를 할 수 없어요\./);
  assert.match(rendered, /이 반은 월간 · 주간계획안을 만들 수 없어요\./);
  const tabs = nodes.filter((node) => node.props?.role === "tab");
  assert.deepEqual(tabs.map(text), ["3월~5월", "6월~8월", "9월~11월", "12월~2월"]);
  assert.equal(tabs.filter((tab) => tab.props["aria-selected"]).length, 1);
  const panel = nodes.find((node) => node.props?.role === "tabpanel");
  assert.equal(panel.props.tabIndex, 0);
  assert.equal(panel.props["aria-labelledby"], tabs[0].props.id);
  assert.ok(tabs.every((tab) => tab.props["aria-controls"] === panel.props.id));
  const cards = nodes.filter((node) => node.type === "article");
  assert.equal(cards.length, 10);
  assert.equal(text(nodes.find((node) => node.type === "h2")), "놀이 0");
  for (const label of ["지원매체", "내용 및 지원 방향 예상하기", "놀이를 통한 배움", "배움 한 줄"])
    assert.ok(text(cards[0]).includes(label));
  assert.equal(
    nodes
      .filter((node) => node.type === "button")
      .some((node) => /수정|확정|내려받기|저장/.test(text(node))),
    false,
  );
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
  const Result = compile("../components/plan-generator/AnnualResult.tsx", {
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
