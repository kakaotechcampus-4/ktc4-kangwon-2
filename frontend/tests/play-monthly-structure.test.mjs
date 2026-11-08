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
      if (name === "./PlanMemo") return { PlanMemoNote: () => null };
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
  mods["./PlayMonthlySafetyPanel"] = compile(dir + "PlayMonthlySafetyPanel.tsx", mods);
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

test("안전교육: 넣은 후보는 후보 목록에서 숨고, 남은 후보는 모두 [+ 넣기]", () => {
  const { C, h } = load("PlayMonthlySafetyPanel.tsx");
  let tree = h.render(C, { plan: plan(), weekId: "w2", onPlace() {}, disabled: false });
  const ids = (t) => all(t).flatMap((n) => n.props?.["data-candidate"] ?? []);
  // s2 는 1주 · 3주에 넣었다 — 후보 8개 중 7개만 남는다.
  assert.deepEqual(ids(tree), ["s1", "s3", "s4", "s5", "s6", "s7", "s8"]);
  assert.ok(text(tree).includes("2주 안전교육 후보"));
  assert.equal(all(tree).filter(act("place")).length, 7);
  tree = h.render(C, { plan: plan(), weekId: "w1", onPlace() {}, disabled: false });
  assert.ok(!text(tree).includes("넣었어요"));
  assert.ok(!ids(tree).includes("s2"));
});

test("안전교육: [넣기]는 고른 주에 그 후보를, [빼기]는 null 을 넘기고, disabled 면 모든 버튼이 꺼진다", () => {
  const { C, h } = load("PlayMonthlySafetyPanel.tsx");
  const calls = [];
  const onPlace = (...a) => calls.push(a);
  click(
    h.render(C, { plan: plan(), weekId: "w2", onPlace, disabled: false }),
    (n) => act("place")(n) && n.props["aria-label"].endsWith("법정 3"),
  );
  click(
    h.render(C, { plan: plan(), weekId: "w1", onPlace, disabled: false }),
    (n) => act("unplace")(n) && n.props["aria-label"].startsWith("1주"),
  );
  // 넣은 안전교육(놀이 고르기의 「고른 놀이」처럼): 주마다 한 칸, 넣은 주는 [영역] · ✕ 로 뺀다.
  const placed = h.render(C, {
    plan: plan({
      safety_candidates: [
        { kind: "STATUTORY", category_id: "traffic_safety", cell: cell("s2", "건너요") },
      ],
    }),
    weekId: "w2",
    onPlace,
    disabled: false,
  });
  const list = all(placed).find((n) => n.props?.["aria-label"] === "넣은 안전교육");
  assert.equal(all(list).filter((n) => n.type === "li").length, 3);
  assert.ok(text(list).includes("[교통안전]건너요"));
  assert.equal(all(list).filter(act("unplace")).length, 2);
  click(placed, (n) => act("unplace")(n) && n.props["aria-label"].startsWith("3주"));
  assert.deepEqual(calls, [
    ["w2", "s3"],
    ["w1", null],
    ["w3", null],
  ]);
  const tree = h.render(C, { plan: plan(), weekId: "w1", onPlace() {}, disabled: true });
  assert.ok(
    all(tree)
      .filter((n) => n.type === "button")
      .every((n) => n.props.disabled),
  );
});

test("소방대피: 쓴 글이 있어도 묻지 않고 바로 복사한다", () => {
  const { C, h } = load("PlayMonthlyDrillPanel.tsx");
  const calls = [];
  const tree = h.render(C, {
    candidates: plan().drill_candidates,
    current: "쓴 글",
    onCopy: (id) => calls.push(id),
    disabled: false,
  });
  click(tree, (n) => n.props["data-candidate"] === "d1");
  assert.deepEqual(calls, ["d1"]);
  assert.ok(!text(tree).includes("바꿀까요"));
});

test("소방대피: 넣은 후보는 안전교육처럼 위 상자로 올라가 [−]로 빼고, 후보 목록에서는 숨는다", () => {
  const { C, h } = load("PlayMonthlyDrillPanel.tsx");
  const candidates = plan().drill_candidates.map((d) =>
    d.cell.item_id === "d2" ? { ...d, cell: { ...d.cell, value: "숨어요" } } : d,
  );
  let cleared = 0;
  const tree = h.render(C, {
    candidates,
    current: "숨어요",
    onCopy() {},
    onClear: () => cleared++,
    disabled: false,
  });
  assert.deepEqual(
    all(tree)
      .filter(act("copy"))
      .map((n) => n.props["data-candidate"]),
    ["d1"],
  );
  click(tree, act("clear"));
  assert.equal(cleared, 1);
  assert.ok(text(tree).includes("숨어요"));
});

test("소방대피: 빈 후보와 disabled 는 버튼이 꺼진다", () => {
  const { C, h } = load("PlayMonthlyDrillPanel.tsx");
  let tree = h.render(C, {
    candidates: plan().drill_candidates,
    current: "",
    onCopy() {},
    disabled: false,
  });
  const off = (t) =>
    all(t)
      .filter(act("copy"))
      .map((n) => n.props.disabled);
  assert.deepEqual(off(tree), [false, true]);
  tree = h.render(C, {
    candidates: plan().drill_candidates,
    current: "",
    onCopy() {},
    disabled: true,
  });
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

test("확인 상자: 연 채 disabled 가 되면 상자가 닫히고 콜백은 0건이다", () => {
  for (const [file, props, opener] of [
    [
      "PlayMonthlyRowRemove.tsx",
      { activity: row, section: "자유놀이", onRemove: () => calls.push(1), isLastInSection: false },
      act("remove"),
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
  assert.equal(typeof buttons[0].props.ref, "object"); // 안정된 ref — 인라인 함수면 다시 그릴 때마다 포커스를 가져간다
  const box = all(tree).find((n) => n.props?.role === "group");
  box.props.onKeyDown({ key: "Enter" });
  assert.deepEqual(calls, []);
  box.props.onKeyDown({ key: "Escape" });
  assert.deepEqual(calls, ["no"]);
  assert.ok(all(h.render(C, { ...props, disabled: true })).find(act("yes")).props.disabled);
});

test("확인 상자: 열릴 때 한 번만 아니요로 포커스를 옮기고, 닫히면 연 버튼으로 돌린다", () => {
  const log = [];
  let ref;
  let effect;
  const react = {
    useRef: () => (ref ??= { current: { focus: () => log.push("no") } }),
    // 마운트 때 한 번만 도는 효과 하나(deps []). cleanup 은 닫힐 때 부른다.
    useEffect: (fn, deps) => {
      assert.deepEqual(deps, []);
      effect ??= fn();
    },
  };
  const C = compile(dir + "PlayMonthlyConfirm.tsx", {
    react,
    "./PlayMonthlyStructure.module.css": esModule(css),
  }).default;
  globalThis.document = { activeElement: { focus: () => log.push("opener") } };
  const props = { message: "m", yes: "예", onYes() {}, onNo() {} };
  C(props);
  C(props);
  C({ ...props, disabled: true }); // 다시 그려도 포커스를 다시 가져가지 않는다
  assert.deepEqual(log, ["no"]);
  effect(); // 닫힘
  assert.deepEqual(log, ["no", "opener"]);
});

test("복사 · 비우기 버튼 이름에 후보명 · 주 이름이 들어가고 빈 후보에 이름이 있다", () => {
  const s = load("PlayMonthlySafetyPanel.tsx");
  const p = plan();
  p.safety_candidates[0].cell.value = " ";
  const tree = s.h.render(s.C, { plan: p, weekId: "w1", onPlace() {}, disabled: false });
  const labels = (t, a) =>
    all(t)
      .filter(act(a))
      .map((n) => n.props["aria-label"]);
  assert.deepEqual(labels(tree, "unplace"), ["1주에서 빼기: 법정 2", "3주에서 빼기: 법정 2"]);
  assert.equal(labels(tree, "place")[0], "1주에 넣기: 법정 빈 후보");
  const d = load("PlayMonthlyDrillPanel.tsx");
  assert.deepEqual(
    labels(
      d.h.render(d.C, {
        candidates: plan().drill_candidates,
        current: "",
        onCopy() {},
        disabled: false,
      }),
      "copy",
    ),
    ["소방대피/재난대비 칸에 넣기: 화재", "소방대피/재난대비 칸에 넣기: 지진"],
  );
});
