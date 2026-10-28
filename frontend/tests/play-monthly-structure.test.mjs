// 놀이 월간 구조 부품 3개(안전교육 · 소방대피 · 행 빼기) — props 만 받는 컴포넌트의 콜백 인자와 확인 상자.
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
  const file = fileURLToPath(new URL(path, import.meta.url));
  const code = require("next/dist/compiled/babel/core").transformSync(readFileSync(file, "utf8"), {
    filename: file,
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
  return compiled.exports;
}
const resolve = (node) => {
  if (Array.isArray(node)) return node.map(resolve);
  if (!node || typeof node !== "object") return node;
  if (typeof node.type === "function") return resolve(node.type(node.props));
  return { ...node, props: { ...node.props, children: resolve(node.props.children) } };
};
const all = (node) =>
  Array.isArray(node)
    ? node.flatMap(all)
    : !node || typeof node !== "object"
      ? []
      : [node, ...all(node.props?.children)];
const text = (node) =>
  Array.isArray(node)
    ? node.map(text).join("")
    : node && typeof node === "object"
      ? text(node.props?.children)
      : typeof node === "string" || typeof node === "number"
        ? String(node)
        : "";
const css = new Proxy({}, { get: (_, name) => String(name) });
const withText = (tree, tag, wanted) =>
  all(tree).filter((n) => n.type === tag && text(n).includes(wanted));
const withClass = (tree, name) => all(tree).filter((n) => n.props?.className?.includes?.(name));

// 한 번 그릴 때마다 훅 칸을 순서대로 다시 읽는 대역. effect 는 deps 가 바뀔 때만 돈다.
function harness() {
  const slots = [];
  let index = 0;
  let pending = [];
  const react = {
    useState(init) {
      const k = index++;
      if (!(k in slots)) slots[k] = typeof init === "function" ? init() : init;
      return [slots[k], (v) => void (slots[k] = typeof v === "function" ? v(slots[k]) : v)];
    },
    useRef(init) {
      const k = index++;
      return (slots[k] ??= { current: init });
    },
    useEffect(fn, deps) {
      const k = index++;
      const key = JSON.stringify(deps);
      if (slots[k] === key) return;
      pending.push(fn);
      slots[k] = key;
    },
  };
  const render = (component, props) => {
    index = 0;
    pending = [];
    const tree = resolve(component(props));
    pending.forEach((fn) => fn());
    return tree;
  };
  return {
    react,
    render,
    async settle(component, props) {
      render(component, props);
      await new Promise((done) => setTimeout(done, 0));
      return render(component, props);
    },
  };
}

const dir = "../components/plan-generator/";
const confirmMod = (h) =>
  compile(dir + "PlayMonthlyConfirm.tsx", {
    react: h.react,
    "./PlayMonthlyStructure.module.css": esModule(css),
  });
const load = (file) => {
  const h = harness();
  const mods = {
    react: h.react,
    "./PlayMonthlyStructure.module.css": esModule(css),
    "./PlayMonthlyConfirm": esModule(confirmMod(h).default),
  };
  return { C: compile(dir + file, mods).default, h };
};
const click = (tree, pred) =>
  all(tree)
    .find((n) => n.type === "button" && pred(n))
    .props.onClick();
const act = (name) => (n) => n.props["data-act"] === name;
const cell = (item_id, value) => ({ item_id, value, evidence: [], generation: null });
const plan = (over = {}) => ({
  id: 1,
  weeks: [1, 2, 3].map((n) => ({ week_id: "w" + n, label: n + "주" })),
  safety_candidates: [
    ...[1, 2, 3, 4, 5, 6].map((n) => ({ kind: "STATUTORY", cell: cell("s" + n, "법정 " + n) })),
    ...[7, 8].map((n) => ({ kind: "SUPPLEMENTAL", cell: cell("s" + n, "생활 " + n) })),
  ],
  safety_weeks: [
    { week_id: "w1", candidate_item_id: "s2" },
    { week_id: "w2", candidate_item_id: null },
    { week_id: "w3", candidate_item_id: "s2" },
  ],
  drill_candidates: [
    { topic_id: "a", label: "화재", cell: cell("d1", "대피해요") },
    { topic_id: "b", label: "지진", cell: cell("d2", "  ") },
  ],
  teacher_inputs: [{ key: "fire_disaster_drill", cell: cell("t1", "") }],
  ...over,
});

test("안전교육: 후보 8개와 주별 현재 배치를 보인다", () => {
  const { C, h } = load("PlayMonthlySafetyPanel.tsx");
  const tree = h.render(C, { plan: plan(), onPlace() {}, disabled: false });
  assert.equal(all(tree).filter((n) => n.props?.["data-candidate"]).length, 8);
  assert.equal(withClass(tree, "tag").filter((n) => text(n) === "법정").length, 6);
  assert.equal(withClass(tree, "tag").filter((n) => text(n) === "생활안전").length, 2);
  const w1 = all(tree).find((n) => n.props?.["data-week"] === "w1");
  assert.ok(text(w1).includes("법정 2"));
  const w2 = all(tree).find((n) => n.props?.["data-week"] === "w2");
  assert.ok(text(w2).includes("아직 안 뒀어요"));
  assert.equal(all(w2).filter(act("clear")).length, 0);
});

test("안전교육: 후보를 고르기 전엔 두기가 꺼져 있고, 고르면 주마다 같은 후보를 둘 수 있다", () => {
  const { C, h } = load("PlayMonthlySafetyPanel.tsx");
  const calls = [];
  const props = { plan: plan(), onPlace: (...a) => calls.push(a), disabled: false };
  let tree = h.render(C, props);
  assert.ok(
    all(tree)
      .filter(act("place"))
      .every((n) => n.props.disabled),
  );
  click(tree, (n) => n.props["data-candidate"] === "s3");
  tree = h.render(C, props);
  const place = all(tree).filter(act("place"));
  assert.ok(place.every((n) => !n.props.disabled));
  place[1].props.onClick();
  place[2].props.onClick();
  assert.deepEqual(calls, [
    ["w2", "s3"],
    ["w3", "s3"],
  ]);
});

test("안전교육: 비우기는 null 을 넘기고, disabled 면 모든 버튼이 꺼진다", () => {
  const { C, h } = load("PlayMonthlySafetyPanel.tsx");
  const calls = [];
  let tree = h.render(C, { plan: plan(), onPlace: (...a) => calls.push(a), disabled: false });
  click(tree, (n) => act("clear")(n) && text(n) === "비우기");
  assert.deepEqual(calls, [["w1", null]]);
  tree = h.render(C, { plan: plan(), onPlace() {}, disabled: true });
  assert.ok(
    all(tree)
      .filter((n) => n.type === "button")
      .every((n) => n.props.disabled),
  );
});

test("소방대피: 칸이 비었으면 확인 없이 바로 복사한다", () => {
  const { C, h } = load("PlayMonthlyDrillPanel.tsx");
  const calls = [];
  const tree = h.render(C, { plan: plan(), onCopy: (id) => calls.push(id), disabled: false });
  click(tree, (n) => n.props["data-candidate"] === "d1");
  assert.deepEqual(calls, ["d1"]);
  assert.equal(all(tree).filter((n) => n.props?.role === "group").length, 0);
});

test("소방대피: 쓴 글이 있으면 확인 상자를 거치고 아니요면 복사하지 않는다", () => {
  const { C, h } = load("PlayMonthlyDrillPanel.tsx");
  const calls = [];
  const p = plan({ teacher_inputs: [{ key: "fire_disaster_drill", cell: cell("t1", "내 글") }] });
  const props = { plan: p, onCopy: (id) => calls.push(id), disabled: false };
  click(h.render(C, props), (n) => n.props["data-candidate"] === "d1");
  assert.deepEqual(calls, []);
  let tree = h.render(C, props);
  assert.ok(text(tree).includes("지금 쓴 글을 이 후보로 바꿀까요?"));
  click(tree, (n) => n.props["data-act"] === "no");
  tree = h.render(C, props);
  assert.equal(all(tree).filter((n) => n.props?.role === "group").length, 0);
  assert.deepEqual(calls, []);
  click(tree, (n) => n.props["data-candidate"] === "d1");
  click(h.render(C, props), (n) => n.props["data-act"] === "yes");
  assert.deepEqual(calls, ["d1"]);
});

test("소방대피: 빈 후보와 disabled 는 버튼이 꺼진다", () => {
  const { C, h } = load("PlayMonthlyDrillPanel.tsx");
  let tree = h.render(C, { plan: plan(), onCopy() {}, disabled: false });
  const off = (t) =>
    all(t)
      .filter(act("copy"))
      .map((n) => n.props.disabled);
  assert.deepEqual(off(tree), [false, true]);
  tree = h.render(C, { plan: plan(), onCopy() {}, disabled: true });
  assert.deepEqual(off(tree), [true, true]);
});

const row = { activity_id: "r1", name: cell("r1", "모래놀이") };
test("행 빼기: 확인 상자를 거쳐야 콜백이 간다", () => {
  const { C, h } = load("PlayMonthlyRowRemove.tsx");
  const calls = [];
  const props = {
    activity: row,
    section: "자유놀이",
    onRemove: (id) => calls.push(id),
    disabled: false,
    isLastInSection: false,
  };
  click(h.render(C, props), act("remove"));
  let tree = h.render(C, props);
  assert.ok(text(tree).includes("이 행을 빼면 되돌릴 수 없어요. 뺄까요?"));
  assert.deepEqual(calls, []);
  click(tree, act("no"));
  assert.equal(all(h.render(C, props)).filter((n) => n.props?.role === "group").length, 0);
  click(h.render(C, props), act("remove"));
  click(h.render(C, props), act("yes"));
  assert.deepEqual(calls, ["r1"]);
});

test("행 빼기: 마지막 행이면 확정이 막힌다는 안내가 있고, disabled 면 꺼진다", () => {
  const { C, h } = load("PlayMonthlyRowRemove.tsx");
  const base = { activity: row, section: "자유놀이", onRemove() {}, disabled: false };
  assert.equal(
    withText(h.render(C, { ...base, isLastInSection: false }), "small", "확정").length,
    0,
  );
  assert.equal(
    withText(h.render(C, { ...base, isLastInSection: true }), "small", "확정할 수 없어요").length,
    1,
  );
  const tree = h.render(C, { ...base, isLastInSection: false, disabled: true });
  assert.ok(all(tree).find(act("remove")).props.disabled);
});

test("안전교육: 계획이 바뀌면 고른 후보를 버리고 두기가 꺼진다", () => {
  const { C, h } = load("PlayMonthlySafetyPanel.tsx");
  const calls = [];
  const onPlace = (...a) => calls.push(a);
  click(
    h.render(C, { plan: plan(), onPlace, disabled: false }),
    (n) => n.props["data-candidate"] === "s3",
  );
  const b = plan({
    id: 2,
    safety_candidates: [{ kind: "STATUTORY", cell: cell("x1", "다른 계획") }],
  });
  const tree = h.render(C, { plan: b, onPlace, disabled: false });
  assert.ok(
    all(tree)
      .filter(act("place"))
      .every((n) => n.props.disabled),
  );
  assert.equal(all(tree).filter((n) => n.props["aria-pressed"] === true).length, 0);
  assert.deepEqual(calls, []);
});

test("확인 상자: 연 채 disabled 가 되면 상자가 닫히고 콜백은 0건이다", () => {
  for (const [file, props, opener] of [
    [
      "PlayMonthlyRowRemove.tsx",
      { activity: row, section: "자유놀이", onRemove: () => calls.push(1), isLastInSection: false },
      act("remove"),
    ],
    [
      "PlayMonthlyDrillPanel.tsx",
      {
        plan: plan({ teacher_inputs: [{ key: "fire_disaster_drill", cell: cell("t1", "내 글") }] }),
        onCopy: () => calls.push(1),
      },
      (n) => n.props["data-candidate"] === "d1",
    ],
  ]) {
    const calls = [];
    const { C, h } = load(file);
    click(h.render(C, { ...props, disabled: false }), opener);
    assert.equal(
      all(h.render(C, { ...props, disabled: false })).filter((n) => n.props?.role === "group")
        .length,
      1,
    );
    h.render(C, { ...props, disabled: true }); // 렌더 중 setState — 진짜 React 는 바로 다시 그린다
    const tree = h.render(C, { ...props, disabled: true });
    assert.equal(all(tree).filter((n) => n.props?.role === "group").length, 0);
    assert.deepEqual(calls, []);
  }
});

test("확인 상자: 첫 버튼은 아니요이고 포커스를 받으며, Escape 는 아니요와 같다", () => {
  const h = harness();
  const C = compile(dir + "PlayMonthlyConfirm.tsx", {
    react: h.react,
    "./PlayMonthlyStructure.module.css": esModule(css),
  }).default;
  const calls = [];
  const props = {
    message: "m",
    yes: "예",
    disabled: false,
    onYes: () => calls.push("yes"),
    onNo: () => calls.push("no"),
  };
  const tree = h.render(C, props);
  const buttons = all(tree).filter((n) => n.type === "button");
  assert.equal(buttons[0].props["data-act"], "no");
  let focused = 0;
  buttons[0].props.ref({ focus: () => focused++ });
  assert.equal(focused, 1);
  const box = all(tree).find((n) => n.props?.role === "group");
  box.props.onKeyDown({ key: "Enter" });
  assert.deepEqual(calls, []);
  box.props.onKeyDown({ key: "Escape" });
  assert.deepEqual(calls, ["no"]);
  assert.ok(all(h.render(C, { ...props, disabled: true })).find(act("yes")).props.disabled);
});

test("복사 · 비우기 버튼 이름에 후보명 · 주 이름이 들어가고 빈 후보에 이름이 있다", () => {
  const s = load("PlayMonthlySafetyPanel.tsx");
  const p = plan();
  p.safety_candidates[0].cell.value = " ";
  const tree = s.h.render(s.C, { plan: p, onPlace() {}, disabled: false });
  const labels = (t, a) =>
    all(t)
      .filter(act(a))
      .map((n) => n.props["aria-label"]);
  assert.deepEqual(labels(tree, "clear"), ["1주 비우기: 법정 2", "3주 비우기: 법정 2"]);
  assert.equal(
    all(tree).find((n) => n.props["data-candidate"] === "s1").props["aria-label"],
    "법정 빈 후보",
  );
  const d = load("PlayMonthlyDrillPanel.tsx");
  assert.deepEqual(
    labels(d.h.render(d.C, { plan: plan(), onCopy() {}, disabled: false }), "copy"),
    ["소방대피/재난대비 칸에 넣기: 화재", "소방대피/재난대비 칸에 넣기: 지진"],
  );
});
