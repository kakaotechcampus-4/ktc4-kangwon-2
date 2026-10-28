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
  if (typeof node.type === "function") {
    if (node.type === CellEditor) editorStub.key = node.key;
    return resolve(node.type(node.props));
  }
  return { ...node, props: { ...node.props, children: resolve(node.props.children) } };
}
function all(node) {
  if (Array.isArray(node)) return node.flatMap(all);
  if (!node || typeof node !== "object" || node.props?.["aria-hidden"] || node.props?.hidden)
    return [];
  return [node, ...all(node.props?.children)];
}
function text(node) {
  if (Array.isArray(node)) return node.map(text).join("");
  if (node && typeof node === "object")
    return node.props?.["aria-hidden"] || node.props?.hidden ? "" : text(node.props?.children);
  return typeof node === "string" || typeof node === "number" ? String(node) : "";
}
function plan() {
  let serial = 0;
  const cell = (value) => ({
    item_id: "item_" + serial++,
    value,
    evidence: [],
    generation: { method: "RULE_LLM" },
  });
  return {
    id: 41,
    revision: 3,
    class_id: 8,
    school_year: 2026,
    status: "DRAFT",
    format: "PLAY_PROJECT",
    format_version: "play-project-layout-v0.2.0",
    periods: ["3월~5월", "6월~8월", "9월~11월", "12월~2월"].map((label, period) => ({
      period_key: "period" + period,
      label,
      months: [],
      selected: [],
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
const sheetHelpers = compile("../components/plan-generator/playProjectPagination.ts", {});
const { default: Sheet, windowScrollDelta } = compile(
  "../components/plan-generator/PlayProjectSheet.tsx",
  {
    react: {
      useState: (value) => [typeof value === "function" ? value() : value, () => {}],
      useRef: (value) => ({ current: value }),
      useEffect: () => {},
      useMemo: (compute) => compute(),
    },
    "./playProjectPagination": sheetHelpers,
    "./PlayProjectResult.module.css": esModule(resultStyles),
  },
);
const { default: Picking } = compile("../components/plan-generator/PlayProjectPicking.tsx", {
  react: { useRef: (value) => ({ current: value }), useEffect: () => {} },
  "@/components/workspace/Workspace.module.css": esModule(css),
  "./PlayProjectResult.module.css": esModule(resultStyles),
  "./playProjectPagination": sheetHelpers,
});
// 저장 훅 대역 — 화면이 무엇을 저장하라고 넘겼는지와 저장 표시만 본다. 큐 규칙은 따로 시험한다.
const saveStub = {
  calls: [],
  cells: [],
  retries: 0,
  status: "idle",
  conflict: null,
  rejected: null,
  drafting: false,
  // whenIdle 의 다음 답과 불린 순서 — 확정이 큐를 기다린 뒤 그 revision 으로 보내는지 본다.
  idle: { saved: true, revision: 3 },
  gate: null,
  queue: null, // 있으면 whenIdle 이 이 진짜 큐를 부른다
  log: [],
};
// 확정 API 대역 — 무엇을 어떤 revision 으로 보냈는지, 다음에 무엇이 오는지.
const confirmStub = { calls: [], next: null };
// 한글 파일 내려받기 훅 대역 — 누른 id · 진행 중 · 안내 문구를 시험이 정한다.
const hwpxStub = { exporting: false, ran: [], message: "" };
class StubApiError extends Error {
  constructor(status, fields) {
    super("서버 문구");
    this.status = status;
    this.body = { error: { fields } };
  }
}
// 입력창 대역 — 화면이 넘긴 값과 콜백만 본다. 입력창 규칙은 play-cell-editor.test.mjs 가 다룬다.
const editorStub = { props: null };
const CellEditor = (props) => (
  (editorStub.props = props),
  [
    jsx("label", { htmlFor: props.id, children: props.label }),
    jsx("textarea", { id: props.id, value: props.value }),
  ]
);
const sheetModules = {
  "@/lib/hooks/use-play-selection-save": {
    usePlaySelectionSave: (
      _id,
      _revision,
      onConflict,
      _onSaved,
      onRejected,
      _selections,
      drafting,
    ) => {
      saveStub.conflict = onConflict;
      saveStub.rejected = onRejected;
      saveStub.drafting = drafting;
      return {
        status: saveStub.status,
        save: (selections) => saveStub.calls.push(selections),
        saveCell: (itemId, value, base) => saveStub.cells.push({ itemId, value, base }),
        retry: () => saveStub.retries++,
        whenIdle: () => {
          saveStub.log.push("whenIdle");
          if (saveStub.queue) return saveStub.queue.whenIdle();
          return saveStub.gate
            ? saveStub.gate.then(() => saveStub.idle)
            : Promise.resolve(saveStub.idle);
        },
      };
    },
  },
  "@/lib/api/client": { ApiError: StubApiError },
  "@/lib/hooks/use-hwpx-download": {
    useHwpxDownload: (onMessage) => ({
      exporting: hwpxStub.exporting,
      download: async (fetchFile) => {
        try {
          await fetchFile();
        } catch (e) {
          onMessage(e.message);
        }
      },
    }),
  },
  "@/lib/api/plans": {
    downloadAnnualHwpx: async (id) => {
      hwpxStub.ran.push(id);
      if (hwpxStub.message) throw new Error(hwpxStub.message);
    },
    confirmPlayProject: async (id, revision) => {
      saveStub.log.push("confirm");
      confirmStub.calls.push({ id, revision });
      const next = confirmStub.next;
      if (next instanceof Error) throw next;
      return next;
    },
    isSaveConflict: (error) => error?.status === 409,
  },
  "@/lib/plan-generator/playEditHistory": compile("../lib/plan-generator/playEditHistory.ts", {}),
  "./PlayCellEditor": esModule(CellEditor),
  "./playProjectPagination": sheetHelpers,
  "./PlayProjectSheet": esModule(Sheet),
  "./PlayProjectPicking": esModule(Picking),
};
const pickToggles = (nodes) =>
  nodes.filter((node) => /^「.*」 선택(하기|됨)$/.test(node.props?.["aria-label"] ?? ""));
const tables = (nodes) => nodes.filter((node) => node.type === "table");
function resultRenderer(planValue, initial = [], desktop = false, extraProps = {}) {
  // ② 를 짧은 상태로 시작하는 테스트는 숨은 「선택한 놀이」 패널이 아니라 보이는 쪽을 쓴다.
  const state =
    initial.length === 4 && initial[1] === 1
      ? [...initial, { mode: "fit", percent: 100 }, null, "picked"]
      : [...initial];
  const focused = [];
  const focusOptions = [];
  const scrolls = [];
  const frames = [];
  let effects = [];
  const tabListRef = { current: null };
  const boxes = [];
  let boxCursor = 0;
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
      react: {
        useState,
        useRef: (value) =>
          value === null ? tabListRef : (boxes[boxCursor++] ??= { current: value }),
        useEffect: (effect) => effects.push(effect),
        useSyncExternalStore: (_subscribe, get) => get(),
        useMemo: (compute) => compute(),
      },
      "@/components/workspace/Workspace.module.css": esModule(css),
      "./GenerationFlow.module.css": esModule(resultTabs),
      "./PlayProjectResult.module.css": esModule(resultStyles),
      ...sheetModules,
    },
    {
      activeElement: { blur: () => saveStub.log.push("blur") },
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
    { scrollTo: (options) => scrolls.push(options), matchMedia: () => ({ matches: desktop }) },
  );
  const render = () => {
    cursor = 0;
    boxCursor = 0;
    effects = [];
    tree = resolve(jsx(Result, { plan: planValue, ...extraProps }));
    return tree;
  };
  return {
    render,
    // 마지막 렌더의 효과를 모두 돌리고 정리 함수들을 돌려준다(화면이 내려갈 때 부르는 것).
    mount: () => effects.map((effect) => effect()).filter((c) => typeof c === "function"),
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
      useSyncExternalStore: (_subscribe, get) => get(),
      useMemo: (compute) => compute(),
    },
    "@/components/workspace/Workspace.module.css": esModule(css),
    "./GenerationFlow.module.css": esModule(resultTabs),
    "./PlayProjectResult.module.css": esModule(resultStyles),
    ...sheetModules,
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
  assert.match(rendered, /확정하면 한글 파일로 내려받을 수 있어요\./);
  assert.equal(
    nodes.some((node) => node.type === "button" && /한글 파일로 내려받기/.test(text(node))),
    false,
  );
  assert.doesNotMatch(rendered, /아직 확정 · 내려받기를 할 수 없어요/);
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
  assert.equal(pickToggles(nodes).length, 10);
  assert.equal(nodes.filter((node) => node.type === "input").length, 0);
  assert.equal(text(nodes.find((node) => node.type === "h2")), "놀이 0");
  // 카드는 요약만 보인다: 놀이명 · 지원 방향 앞부분 · 지원매체. 배움은 자세히 보기 안에 있다.
  assert.ok(text(cards[0]).includes("지원매체 종이 상자"));
  assert.ok(text(cards[0]).includes("관심을 따라 돕습니다."));
  assert.equal(text(cards[0]).includes("배움 한 줄"), false);
  assert.equal(text(pickToggles(nodes)[2]), "+ 선택하기");
  assert.equal(
    nodes
      .filter((node) => node.type === "button")
      .some((node) => /수정|확정|내려받기|저장/.test(text(node))),
    false,
  );
  assert.doesNotMatch(rendered, /아직 저장되지 않아요|새로고침하면 처음부터/);
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
  const table = tables(nodes);
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
    nodes
      .filter((node) => node.type === "tbody")
      .flatMap((body) => all(body).filter((node) => node.type === "tr"));
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
    nodes.find((node) => node.props?.["aria-label"] === "「놀이 3」 선택됨").props["aria-pressed"],
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
    text(availableNodes().find((node) => node.props?.role === "status" && text(node))),
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
    availableNodes().some((node) => node.props?.role === "status" && text(node)),
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
  const toggle = nodes.find((node) => node.props?.["aria-label"] === "「놀이 1」 선택하기");
  assert.equal(toggle.props["aria-pressed"], false);
  toggle.props.onClick();
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
    text(nodes.find((node) => node.props?.role === "status" && text(node))),
    "9월~11월이 3개, 12월~2월이 0개예요. 확정하려면 구간마다 5개가 필요해요.",
  );
  const table = tables(nodes);
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
  assert.equal(all(table).filter((node) => node.props?.scope === "col").length, 10);
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
  assert.equal(text(tables(nodes)), text(table));
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
  assert.equal(nodes.filter((node) => node.props?.role === "status" && text(node)).length, 0);
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
  [state[10], state[11], state[12], state[13], state[14], state[15]] = [
    {},
    { saved: {}, history: { undo: [], redo: [] }, epochs: {} },
    "",
    false,
    "",
    [],
  ];
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
        useSyncExternalStore: (_subscribe, get) => get(),
        useMemo: (compute) => compute(),
      },
      "@/components/workspace/Workspace.module.css": esModule(css),
      "./GenerationFlow.module.css": esModule(resultTabs),
      "./PlayProjectResult.module.css": esModule(resultStyles),
      ...sheetModules,
    },
    { querySelector: (selector) => (assert.equal(selector, 'aside[aria-label="주 메뉴"]'), nav) },
  );
  Result({ plan: plan() });
  const cleanup = effects[1](); // [0] 은 화면이 떠 있는지 적는 효과
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

test("all four full periods show only the floating arrangement button and the draft button in step two", () => {
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
  assert.equal(
    nodes
      .filter((node) => node.props?.className?.includes("floatingNext"))
      .map(text)
      .join(),
    "전체 초안 보기로 →",
  );
});

test("step two shows a floating draft button only when all four periods are full", () => {
  const full = ["cand0", "cand1", "cand2", "cand3", "cand4"];
  const picks = Object.fromEntries(plan().periods.map((period) => [period.period_key, full]));
  const find = (view) =>
    all(view.render()).filter((node) => node.props?.className?.includes("floatingNext"));
  const view = resultRenderer(plan(), [0, 1, picks, null]);
  const floating = find(view);
  assert.equal(floating.length, 1);
  assert.equal(text(floating[0]), "전체 초안 보기로 →");
  floating[0].props.onClick();
  view.flushFrames();
  assert.ok(
    all(view.render()).some(
      (node) => node.type === "button" && text(node) === "← 배치하고 다듬기로",
    ),
  );
  assert.equal(find(view).length, 0);
  assert.deepEqual(view.scrolls, [{ top: 0 }]);
  const short = { ...picks, period3: full.slice(0, 4) };
  assert.equal(find(resultRenderer(plan(), [0, 1, short, null])).length, 0);
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
  for (const toggle of pickToggles(nodes).slice(0, 5)) {
    toggle.props.onClick();
    nodes = all(view.render());
  }
  let toggles = pickToggles(nodes);
  assert.equal(toggles.filter((node) => node.props["aria-pressed"]).length, 5);
  assert.equal(toggles.filter((node) => node.props.disabled).length, 5);
  assert.deepEqual(toggles.slice(0, 5).map(text), Array(5).fill("✓ 선택됨"));
  assert.ok(
    nodes.some((node) => text(node).includes("5개를 모두 골랐어요. 바꾸려면 하나를 빼 주세요.")),
  );
  assert.ok(nodes.some((node) => node.props?.role === "tab" && text(node) === "3월~5월 · 5/5"));
  toggles.find((node) => node.props["aria-pressed"]).props.onClick();
  nodes = all(view.render());
  toggles = pickToggles(nodes);
  assert.equal(toggles.filter((node) => node.props["aria-pressed"]).length, 4);
  assert.equal(toggles.filter((node) => node.props.disabled).length, 0);
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
  assert.equal(textarea.props.readOnly, undefined);
  assert.equal(textarea.props.id, "play-project-selected-cell");
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
  assert.ok(!nodes.some((node) => text(node).includes("아직 수정 기능은 제공하지 않아요")));
  assert.ok(!nodes.some((node) => text(node).includes("아직 저장되지 않아요")));
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
  pickToggles(nodes)[2].props.onClick();
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

const fit = { mode: "fit", percent: 100 };
const FULL_STATE = (picks, step, tab = "edit", detail = null, cell = null) => [
  0,
  step,
  picks,
  cell,
  fit,
  null,
  tab,
  detail,
  "",
  null,
];
const draggableRows = (nodes) => all(tables(nodes)).filter((node) => node.props?.draggable);
const dragEvent = () => ({
  dataTransfer: { setData() {}, effectAllowed: "" },
  preventDefault() {},
});

test("pick buttons toggle with aria-pressed and the side list fills from the top with empty slots", () => {
  const view = resultRenderer(plan());
  let nodes = all(view.render());
  const panel = () => nodes.find((node) => node.props?.["aria-label"] === "고른 놀이");
  const slots = () =>
    all(panel()).filter((node) => node.type === "li" && node.props.className === "slot");
  assert.equal(slots().length, 5);
  assert.ok(slots().every((slot) => text(slot).includes("우리 반의 놀이를 골라 주세요")));
  pickToggles(nodes)[3].props.onClick();
  pickToggles(nodes)[1].props.onClick();
  nodes = all(view.render());
  assert.deepEqual(
    pickToggles(nodes).map((node) => node.props["aria-pressed"]),
    [false, true, false, true, false, false, false, false, false, false],
  );
  assert.equal(text(pickToggles(nodes)[1]), "✓ 선택됨");
  assert.equal(text(panel().props.children[0]), "고른 놀이 2/5");
  assert.deepEqual(slots().map(text), [
    "1놀이 3×",
    "2놀이 1×",
    "3우리 반의 놀이를 골라 주세요",
    "4우리 반의 놀이를 골라 주세요",
    "5우리 반의 놀이를 골라 주세요",
  ]);
  assert.ok(nodes.some((node) => node.type === "strong" && text(node) === "2"));
  assert.ok(text(nodes.find((node) => node.props?.className === "total")).includes("/20개 선택"));
  assert.ok(
    text(all(panel()).find((node) => node.props?.["aria-label"] === "구간별 진행")).includes(
      "3월~5월2/5",
    ),
  );
  all(panel())
    .find((node) => node.props?.["aria-label"] === "놀이 3 빼기")
    .props.onClick();
  nodes = all(view.render());
  assert.deepEqual(view.state[2].period0, ["cand1"]);
  assert.equal(text(slots()[0]), "1놀이 1×");
  assert.equal(text(nodes.find((node) => node.props?.className === "total")), "전체 1/20개 선택");
  const arrange = all(panel()).find((node) => text(node) === "배치하고 다듬기로");
  assert.equal(arrange.props.disabled, undefined);
  arrange.props.onClick();
  assert.equal(view.state[1], 1);
});

test("the detail dialog shows read-only fields and toggles the pick without closing", () => {
  const view = resultRenderer(plan(), FULL_STATE({ period0: ["cand1"] }, 0));
  let nodes = all(view.render());
  assert.equal(
    nodes.some((node) => node.type === "dialog"),
    false,
  );
  nodes.find((node) => node.props?.["aria-label"] === "놀이 3 자세히 살펴보기").props.onClick();
  assert.equal(view.state[7], "cand3");
  nodes = all(view.render());
  const dialog = nodes.find((node) => node.type === "dialog");
  assert.equal(dialog.props["aria-labelledby"], "play-project-detail-title");
  const inside = all(dialog);
  for (const label of ["지원매체", "내용 및 지원 방향 예상하기", "놀이를 통한 배움", "배움 한 줄"])
    assert.ok(text(dialog).includes(label), label);
  assert.equal(
    inside.some((node) => node.type === "textarea" || node.type === "input"),
    false,
  );
  const toggle = inside.find((node) => node.props?.["aria-label"] === "「놀이 3」 선택하기");
  assert.equal(toggle.props["aria-pressed"], false);
  toggle.props.onClick();
  nodes = all(view.render());
  assert.deepEqual(view.state[2].period0, ["cand1", "cand3"]);
  assert.equal(view.state[7], "cand3");
  assert.equal(
    all(nodes.find((node) => node.type === "dialog")).find(
      (n) => n.props?.["aria-label"] === "「놀이 3」 선택됨",
    ).props["aria-pressed"],
    true,
  );
  // 닫기 · 배경 클릭은 dialog.close() 만 부른다. 상태는 네이티브 close 이벤트(Esc 도 같다)가 푼다.
  const open = nodes.find((node) => node.type === "dialog");
  let closed = 0;
  open.props.ref.current = { close: () => closed++ };
  all(open)
    .find((node) => text(node) === "닫기")
    .props.onClick();
  open.props.onClick({ target: "inner", currentTarget: "outer" });
  assert.equal(closed, 1);
  open.props.onClick({ target: "outer", currentTarget: "outer" });
  assert.equal(closed, 2);
  assert.equal(view.state[7], "cand3");
  open.props.onClose();
  assert.equal(view.state[7], null);
});

test("the detail dialog cannot add a sixth pick but can still remove one", () => {
  const five = ["cand0", "cand1", "cand2", "cand4", "cand5"];
  const view = resultRenderer(plan(), FULL_STATE({ period0: five }, 0, "edit", "cand3"));
  let nodes = all(view.render());
  const label = (name) => (node) => node.props?.["aria-label"] === name;
  assert.equal(
    all(nodes.find((n) => n.type === "dialog")).find(label("「놀이 3」 선택하기")).props.disabled,
    true,
  );
  view.state[7] = "cand0";
  nodes = all(view.render());
  const toggle = all(nodes.find((n) => n.type === "dialog")).find(label("「놀이 0」 선택됨"));
  assert.equal(toggle.props.disabled, false);
  toggle.props.onClick();
  assert.deepEqual(view.state[2].period0, ["cand1", "cand2", "cand4", "cand5"]);
});

test("step two has two left tabs and a document cell press switches to the edit tab", () => {
  const view = resultRenderer(
    plan(),
    FULL_STATE({ period0: ["cand0", "cand1"] }, 1, "picked"),
    true,
  );
  let nodes = all(view.render());
  const leftTabs = () =>
    all(nodes.find((node) => node.props?.["aria-label"] === "왼쪽 패널")).filter(
      (node) => node.props?.role === "tab",
    );
  assert.deepEqual(leftTabs().map(text), ["내용 편집", "선택한 놀이 2"]);
  assert.deepEqual(
    leftTabs().map((tab) => tab.props["aria-selected"]),
    [false, true],
  );
  // 안 보이는 패널(hidden)은 하네스가 건너뛴다 — 보이는 패널은 선택된 탭의 것 하나뿐이다.
  const visiblePanels = () =>
    nodes.filter(
      (node) => node.props?.role === "tabpanel" && node.props["aria-labelledby"].includes("-left-"),
    );
  const selectedTab = () => leftTabs().find((tab) => tab.props["aria-selected"]);
  assert.equal(visiblePanels().length, 1);
  assert.equal(visiblePanels()[0].props.id, selectedTab().props["aria-controls"]);
  assert.equal(visiblePanels()[0].props["aria-labelledby"], selectedTab().props.id);
  leftTabs()[0].props.onClick();
  nodes = all(view.render());
  assert.equal(visiblePanels().length, 1);
  assert.equal(visiblePanels()[0].props["aria-labelledby"], leftTabs()[0].props.id);
  leftTabs()[1].props.onClick();
  nodes = all(view.render());
  nodes.find((node) => node.props?.["aria-label"] === "놀이 1 지원매체").props.onClick();
  assert.equal(view.state[6], "edit");
  nodes = all(view.render());
  assert.equal(visiblePanels()[0].props["aria-labelledby"], leftTabs()[0].props.id);
  // 넓은 화면에서 목록의 놀이명 버튼은 탭을 바꾸지 않는다.
  leftTabs()[1].props.onClick();
  nodes = all(view.render());
  nodes.find((node) => node.props?.className?.includes("playButton")).props.onClick();
  assert.equal(view.state[6], "picked");
});

test("placePlayPick moves to a slot, shifts the rest, and ignores same slot or unknown keys", () => {
  const { placePlayPick } = playResult();
  const picks = ["a", "b", "c", "d"];
  assert.deepEqual(placePlayPick(picks, "d", 0), ["d", "a", "b", "c"]);
  assert.deepEqual(placePlayPick(picks, "a", 2), ["b", "c", "a", "d"]);
  assert.deepEqual(placePlayPick(picks, "a", 3), ["b", "c", "d", "a"]);
  assert.equal(placePlayPick(picks, "b", 1), picks);
  assert.equal(placePlayPick(picks, "zzz", 0), picks);
  assert.deepEqual(placePlayPick(picks, "a", 99), ["b", "c", "d", "a"]);
  assert.deepEqual(placePlayPick(picks, "d", -5), ["d", "a", "b", "c"]);
  assert.deepEqual(picks, ["a", "b", "c", "d"]);
});

const DESKTOP = true;
const picksOf = (view, key) => view.state[2][key];

test("dragging a document row onto another row of the same period reorders and announces it", () => {
  const view = resultRenderer(
    plan(),
    FULL_STATE({ period0: ["cand0", "cand1", "cand2"], period1: ["cand4"] }, 1),
    DESKTOP,
  );
  let nodes = all(view.render());
  const rows = () => draggableRows(nodes);
  assert.equal(rows().length, 4);
  rows()[0].props.onDragStart(dragEvent());
  nodes = all(view.render());
  assert.ok(rows()[0].props.className.includes("dragging"));
  rows()[1].props.onDragOver(dragEvent());
  nodes = all(view.render());
  assert.ok(rows()[1].props.className.includes("dropOver"));
  rows()[2].props.onDragOver(dragEvent());
  nodes = all(view.render());
  assert.equal(rows()[1].props.className, undefined);
  assert.ok(rows()[2].props.className.includes("dropOver"));
  rows()[2].props.onDrop(dragEvent());
  nodes = all(view.render());
  assert.deepEqual(picksOf(view, "period0"), ["cand1", "cand2", "cand0"]);
  assert.deepEqual(picksOf(view, "period1"), ["cand4"]);
  assert.equal(view.state[9], null);
  const status = nodes.filter((node) => node.props?.role === "status" && text(node));
  assert.deepEqual(status.map(text), ["「놀이 0」을(를) 3번째로 옮겼어요"]);
  // 옮긴 놀이의 첫 칸으로 포커스를 보낸다(고른 칸이 없으므로).
  view.flushFrames();
  assert.deepEqual(view.focused, ["play-project-cell-period0-cand0-play_name"]);
});

test("a document drop focuses the same field when that play's cell is selected", () => {
  const view = resultRenderer(
    plan(),
    FULL_STATE({ period0: ["cand0", "cand1"] }, 1, "edit", null, {
      periodKey: "period0",
      rowKey: "cand0",
      field: "materials",
    }),
    DESKTOP,
  );
  let nodes = all(view.render());
  draggableRows(nodes)[0].props.onDragStart(dragEvent());
  nodes = all(view.render());
  draggableRows(nodes)[1].props.onDrop(dragEvent());
  all(view.render());
  view.flushFrames();
  assert.deepEqual(view.focused, ["play-project-cell-period0-cand0-materials"]);
});

test("the dragged row never shows a drop marker on its own slot", () => {
  const view = resultRenderer(plan(), FULL_STATE({ period0: ["cand0", "cand1"] }, 1), DESKTOP);
  let nodes = all(view.render());
  draggableRows(nodes)[0].props.onDragStart(dragEvent());
  nodes = all(view.render());
  draggableRows(nodes)[0].props.onDragOver(dragEvent());
  nodes = all(view.render());
  assert.ok(draggableRows(nodes)[0].props.className.includes("dragging"));
  assert.equal(draggableRows(nodes)[0].props.className.includes("dropOver"), false);
});

test("dragging over another period clears the drop marker and blocks the drop", () => {
  const view = resultRenderer(
    plan(),
    FULL_STATE({ period0: ["cand0", "cand1"], period1: ["cand4", "cand0"] }, 1),
    DESKTOP,
  );
  let nodes = all(view.render());
  const before = JSON.stringify(view.state[2]);
  draggableRows(nodes)[0].props.onDragStart(dragEvent());
  nodes = all(view.render());
  draggableRows(nodes)[1].props.onDragOver(dragEvent());
  nodes = all(view.render());
  assert.ok(draggableRows(nodes)[1].props.className.includes("dropOver"));
  let prevented = false;
  draggableRows(nodes)[2].props.onDragOver({
    ...dragEvent(),
    preventDefault: () => (prevented = true),
  });
  assert.equal(prevented, false);
  nodes = all(view.render());
  assert.equal(draggableRows(nodes)[1].props.className, undefined);
  draggableRows(nodes)[2].props.onDrop(dragEvent());
  assert.equal(JSON.stringify(view.state[2]), before);
  assert.equal(view.state[8], "");
  assert.equal(view.state[0], 0);
  nodes = all(view.render());
  draggableRows(nodes)[1].props.onDragStart(dragEvent());
  nodes = all(view.render());
  draggableRows(nodes)[1].props.onDrop(dragEvent());
  assert.equal(JSON.stringify(view.state[2]), before);
  assert.equal(view.state[8], "");
});

test("reordering a non-active period in the document makes that period active", () => {
  const view = resultRenderer(
    plan(),
    FULL_STATE({ period0: ["cand0"], period1: ["cand4", "cand5", "cand6"] }, 1),
    DESKTOP,
  );
  let nodes = all(view.render());
  draggableRows(nodes)[1].props.onDragStart(dragEvent());
  nodes = all(view.render());
  draggableRows(nodes)[3].props.onDrop(dragEvent());
  assert.equal(view.state[0], 1);
  assert.deepEqual(picksOf(view, "period1"), ["cand5", "cand6", "cand4"]);
  nodes = all(view.render());
  assert.ok(
    nodes.some(
      (node) =>
        node.props?.role === "tab" &&
        node.props["aria-selected"] &&
        text(node).startsWith("6월~8월"),
    ),
  );
});

test("list rows drag onto document rows and focus the moved row's list button", () => {
  const view = resultRenderer(
    plan(),
    FULL_STATE({ period0: ["cand0", "cand1", "cand2"] }, 1, "picked"),
    DESKTOP,
  );
  let nodes = all(view.render());
  const listRows = () =>
    nodes.filter((node) => node.props?.draggable && node.props.className?.includes("pickedRow"));
  assert.equal(listRows().length, 3);
  listRows()[2].props.onDragStart(dragEvent());
  nodes = all(view.render());
  draggableRows(nodes)[0].props.onDrop(dragEvent());
  nodes = all(view.render());
  view.flushFrames();
  assert.deepEqual(picksOf(view, "period0"), ["cand2", "cand0", "cand1"]);
  const moved = nodes.find((node) => node.props?.className?.includes("playButton"));
  assert.equal(text(moved), "놀이 2");
  assert.equal(view.focused.at(-1), moved.props.id);
  nodes.find((node) => node.props?.["aria-label"] === "2번째 놀이 위로").props.onClick();
  nodes = all(view.render());
  assert.deepEqual(picksOf(view, "period0"), ["cand0", "cand2", "cand1"]);
  assert.equal(view.state[8], "「놀이 0」을(를) 1번째로 옮겼어요");
  assert.ok(nodes.some((node) => node.props?.role === "status" && text(node) === view.state[8]));
});

test("narrow screens turn dragging off, keep the arrows, and a list name press opens the edit tab", () => {
  const view = resultRenderer(
    plan(),
    FULL_STATE({ period0: ["cand0", "cand1"] }, 1, "picked"),
    false,
  );
  let nodes = all(view.render());
  assert.equal(draggableRows(nodes).length, 0);
  assert.equal(nodes.filter((node) => node.props?.draggable).length, 0);
  assert.ok(nodes.some((node) => node.props?.["aria-label"] === "1번째 놀이 아래로"));
  nodes.find((node) => node.props?.className?.includes("playButton")).props.onClick();
  assert.equal(view.state[6], "edit");
});

test("wide screens keep the picked tab when a list name is pressed", () => {
  const view = resultRenderer(
    plan(),
    FULL_STATE({ period0: ["cand0", "cand1"] }, 1, "picked"),
    DESKTOP,
  );
  all(view.render())
    .find((node) => node.props?.className?.includes("playButton"))
    .props.onClick();
  assert.equal(view.state[6], "picked");
});

test("pure helpers for focus targets, tab keys, and names", () => {
  const { removeFocusSlot, leftTabTarget, dropFocusField } = playResult();
  assert.equal(removeFocusSlot(3, 0), 0);
  assert.equal(removeFocusSlot(3, 1), 1);
  assert.equal(removeFocusSlot(3, 2), null);
  assert.equal(removeFocusSlot(1, 0), null);
  assert.equal(leftTabTarget("ArrowRight", "edit"), "picked");
  assert.equal(leftTabTarget("ArrowRight", "picked"), "edit");
  assert.equal(leftTabTarget("ArrowLeft", "edit"), "picked");
  assert.equal(leftTabTarget("Home", "picked"), "edit");
  assert.equal(leftTabTarget("End", "edit"), "picked");
  assert.equal(leftTabTarget("Enter", "edit"), null);
  assert.equal(dropFocusField("list", "a", null), null);
  assert.equal(dropFocusField("doc", "a", null), "play_name");
  assert.equal(dropFocusField("doc", "a", { rowKey: "b", field: "learning" }), "play_name");
  assert.equal(dropFocusField("doc", "a", { rowKey: "a", field: "learning" }), "learning");
  assert.equal(sheetHelpers.eulReul("솔방울 길"), "을");
  assert.equal(sheetHelpers.eulReul("나무 놀이터"), "를");
  assert.equal(sheetHelpers.eulReul("놀이 0"), "을(를)");
  assert.equal(
    sheetHelpers.cellButtonId("p0", "c1", "materials"),
    "play-project-cell-p0-c1-materials",
  );
});

test("left tablist is a roving tabindex and arrow, Home, End keys activate and focus a tab", () => {
  const view = resultRenderer(plan(), FULL_STATE({ period0: ["cand0"] }, 1, "edit"), DESKTOP);
  let nodes = all(view.render());
  const list = () => nodes.find((node) => node.props?.["aria-label"] === "왼쪽 패널");
  const tabs = () => all(list()).filter((node) => node.props?.role === "tab");
  assert.deepEqual(
    tabs().map((tab) => tab.props.tabIndex),
    [0, -1],
  );
  const key = (name) => {
    let prevented = false;
    list().props.onKeyDown({ key: name, preventDefault: () => (prevented = true) });
    return prevented;
  };
  assert.equal(key("ArrowRight"), true);
  assert.equal(view.state[6], "picked");
  nodes = all(view.render());
  assert.deepEqual(
    tabs().map((tab) => tab.props.tabIndex),
    [-1, 0],
  );
  assert.equal(view.focused.at(-1), tabs()[1].props.id);
  key("Home");
  assert.equal(view.state[6], "edit");
  nodes = all(view.render());
  assert.equal(view.focused.at(-1), tabs()[0].props.id);
  key("End");
  assert.equal(view.state[6], "picked");
  assert.equal(key("a"), false);
  assert.equal(view.state[6], "picked");
});

test("removing from the side list focuses the next slot's x, or the panel heading at the end", () => {
  const view = resultRenderer(plan(), FULL_STATE({ period0: ["cand0", "cand1", "cand2"] }, 0));
  let nodes = all(view.render());
  const panel = () => nodes.find((node) => node.props?.["aria-label"] === "고른 놀이");
  const remove = (name) =>
    all(panel()).find((node) => node.props?.["aria-label"] === `${name} 빼기`);
  remove("놀이 0").props.onClick();
  nodes = all(view.render());
  view.flushFrames();
  assert.equal(view.focused.at(-1), remove("놀이 1").props.id);
  assert.ok(view.focused.at(-1).endsWith("-remove-0"));
  remove("놀이 2").props.onClick();
  nodes = all(view.render());
  view.flushFrames();
  const heading = all(panel()).find((node) => node.type === "h2");
  assert.equal(heading.props.tabIndex, -1);
  assert.equal(view.focused.at(-1), heading.props.id);
  assert.ok(heading.props.id.endsWith("-heading"));
});

test("changing the period closes the detail dialog and clears the drag and notice", () => {
  const view = resultRenderer(plan(), FULL_STATE({ period0: ["cand0"] }, 0, "edit", "cand3"));
  view.state[8] = "안내";
  view.state[9] = { periodKey: "period0", rowKey: "cand0", from: "doc", over: 0 };
  all(view.render())
    .find((node) => node.props?.role === "tab" && text(node).startsWith("6월~8월"))
    .props.onClick();
  assert.equal(view.state[7], null);
  assert.equal(view.state[8], "");
  assert.equal(view.state[9], null);
});

test("selecting a cell or switching a left tab clears the move notice", () => {
  const view = resultRenderer(plan(), FULL_STATE({ period0: ["cand0"] }, 1, "picked"), DESKTOP);
  view.state[8] = "안내";
  all(view.render())
    .find((node) => node.props?.["aria-label"] === "놀이 0 지원매체")
    .props.onClick();
  assert.equal(view.state[8], "");
  view.state[8] = "안내";
  const tab = all(view.render()).find(
    (node) => node.props?.role === "tab" && text(node) === "선택한 놀이 1",
  );
  tab.props.onClick();
  assert.equal(view.state[8], "");
});

test("pick button names contain the visible words and the play name", () => {
  const view = resultRenderer(plan(), FULL_STATE({ period0: ["cand1"] }, 0));
  const toggles = pickToggles(all(view.render()));
  const visible = (node) => text(node).replace(/^[+✓] /, "");
  assert.ok(toggles.every((node) => node.props["aria-label"].includes(visible(node))));
  assert.equal(toggles[0].props["aria-label"], "「놀이 0」 선택하기");
  assert.equal(toggles[1].props["aria-label"], "「놀이 1」 선택됨");
});

test("PlayProjectResult does not use browser storage", () => {
  for (const file of [
    "PlayProjectResult.tsx",
    "PlayProjectSheet.tsx",
    "PlayProjectPicking.tsx",
    "playProjectPagination.ts",
  ]) {
    const source = readFileSync(
      new URL("../components/plan-generator/" + file, import.meta.url),
      "utf8",
    );
    assert.doesNotMatch(source, /localStorage|sessionStorage|indexedDB/i, file);
  }
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
    react: {
      useState: stateHook,
      useRef: (value) => ({ current: value }),
      useEffect: (effect) => effects.push(effect),
    },
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
    "./PlayProjectResult": esModule(({ plan: loaded, onConfirmed }) =>
      jsx("play-project-result", { id: loaded.id, status: loaded.status, onConfirmed }),
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
  // 확정이 끝나면 응답 계획안으로 바꿔 다시 그린다.
  const shown = nodes.find((node) => node.type === "play-project-result");
  assert.equal(shown.props.status, "DRAFT");
  shown.props.onConfirmed({ ...pp, status: "CONFIRMED", revision: pp.revision + 1 });
  assert.equal(
    all(render()).find((node) => node.type === "play-project-result").props.status,
    "CONFIRMED",
  );
});

// ── 확정 (ADR-044 §2 · §4) ──
const FULL = ["cand0", "cand1", "cand2", "cand3", "cand4"];
const fullPicks = { period0: FULL, period1: FULL, period2: FULL, period3: FULL };
const confirmButton = (nodes) =>
  nodes.find((node) => node.type === "button" && /^확정/.test(text(node)));
function confirmView(picks = fullPicks, props = {}) {
  const confirmed = [];
  const conflicts = [];
  const view = resultRenderer(plan(), [0, 2, picks], false, {
    onConfirmed: (next) => confirmed.push(next),
    onConflict: async () => conflicts.push(1),
    ...props,
  });
  return { view, confirmed, conflicts };
}
function resetConfirm(next = { id: 41, status: "CONFIRMED", revision: 10 }) {
  saveStub.idle = { saved: true, revision: 9 };
  saveStub.gate = null;
  saveStub.log = [];
  confirmStub.calls = [];
  confirmStub.next = next;
}

test("③ confirm button is on only when all four periods have five, and always says it cannot be undone", () => {
  resetConfirm();
  const full = all(confirmView().view.render());
  assert.equal(confirmButton(full).props.disabled, false);
  assert.equal(text(confirmButton(full)), "확정하기");
  assert.ok(full.some((node) => text(node) === "확정하면 고칠 수 없어요"));
  const short = all(confirmView({ ...fullPicks, period3: ["cand0"] }).view.render());
  assert.equal(confirmButton(short).props.disabled, true);
  // 이유는 지금의 부족 안내 한 줄이 말한다.
  assert.ok(
    short.some((node) => text(node) === "12월~2월이 1개예요. 확정하려면 구간마다 5개가 필요해요."),
  );
  assert.ok(short.some((node) => text(node) === "확정하면 고칠 수 없어요"));
});

test("confirming blurs the input, waits for the queue, then confirms with the revision the queue gives", async () => {
  const done = { id: 41, status: "CONFIRMED", revision: 10 };
  resetConfirm(done);
  let release;
  saveStub.gate = new Promise((resolve) => (release = resolve));
  const { view, confirmed } = confirmView();
  const first = confirmButton(all(view.render())).props.onClick();
  confirmButton(all(view.render())).props.onClick(); // 더블클릭 — ref 잠금으로 무시
  await new Promise((resolve) => setImmediate(resolve));
  assert.deepEqual(saveStub.log, ["blur", "whenIdle"]); // 큐가 끝나기 전에는 확정하지 않는다
  const waiting = all(view.render());
  assert.equal(text(confirmButton(waiting)), "확정하는 중…");
  assert.equal(confirmButton(waiting).props.disabled, true);
  release();
  await first;
  assert.deepEqual(saveStub.log, ["blur", "whenIdle", "confirm"]);
  assert.deepEqual(confirmStub.calls, [{ id: 41, revision: 9 }]);
  assert.deepEqual(confirmed, [done]);
  // 끝나면 다시 누를 수 있는 상태로 돌아온다.
  assert.equal(text(confirmButton(all(view.render()))), "확정하기");
});

test("a queue that did not save everything stops the confirm with a plain message", async () => {
  resetConfirm();
  saveStub.idle = { saved: false, revision: 9 };
  const { view, confirmed } = confirmView();
  await confirmButton(all(view.render())).props.onClick();
  assert.deepEqual(confirmStub.calls, []);
  assert.deepEqual(confirmed, []);
  const alert = all(view.render()).find((node) => node.props?.role === "alert");
  assert.equal(text(alert), "저장하지 못했어요. 다시 저장한 뒤 확정해 주세요.");
});

test("a 422 names the short periods by label and highlights their tabs", async () => {
  resetConfirm(new StubApiError(422, ["period2", "period3"]));
  const { view, confirmed } = confirmView();
  await confirmButton(all(view.render())).props.onClick();
  const nodes = all(view.render());
  assert.equal(
    text(nodes.find((node) => node.props?.role === "alert")),
    "9월~11월 · 12월~2월 구간이 5개가 안 돼요. 모두 5개를 골라 주세요.",
  );
  const tabs = nodes.filter((node) => node.props?.role === "tab");
  assert.deepEqual(
    tabs.map((tab) => tab.props.className?.includes("lack") ?? false),
    [false, false, true, true],
  );
  assert.deepEqual(confirmed, []);
});

test("a 409 reloads through onConflict without an error line; another failure shows the server's words", async () => {
  resetConfirm(new StubApiError(409, ["expected_revision"]));
  const stale = confirmView();
  await confirmButton(all(stale.view.render())).props.onClick();
  assert.equal(stale.conflicts.length, 1);
  assert.equal(
    all(stale.view.render()).some((node) => node.props?.role === "alert"),
    false,
  );
  resetConfirm(new StubApiError(500, []));
  const other = confirmView();
  await confirmButton(all(other.view.render())).props.onClick();
  assert.equal(other.conflicts.length, 0);
  assert.equal(
    text(all(other.view.render()).find((node) => node.props?.role === "alert")),
    "서버 문구",
  );
});

test("a confirmed plan opens as the read-only ③ table only, even when first opened", () => {
  const confirmedPlan = plan();
  confirmedPlan.status = "CONFIRMED";
  confirmedPlan.periods.forEach((item) => (item.selected = FULL));
  const view = resultRenderer(confirmedPlan, [], false, { onConfirmed: () => {} });
  const nodes = all(view.render());
  const rendered = text(nodes);
  assert.equal(text(nodes.find((node) => node.props?.className === "badge")), "확정됨");
  assert.match(rendered, /확정했어요\. 확정한 계획안은 고치거나 지울 수 없어요\./);
  assert.doesNotMatch(rendered, /곧 열려요/);
  assert.ok(tables(nodes).length > 0);
  assert.equal(all(tables(nodes)).filter((node) => node.type === "button").length, 0);
  // ① ② · 되돌리기 · 다시 하기 · 확정 · 배치로 돌아가기 · 단계 표시가 모두 없다.
  assert.equal(pickToggles(nodes).length, 0);
  assert.equal(nodes.filter((node) => node.props?.className === "stepButton").length, 0);
  assert.equal(
    nodes.some((node) => node.props?.["aria-label"] === "고른 놀이와 선택한 칸"),
    false,
  );
  const labels = nodes.filter((node) => node.type === "button").map(text);
  assert.equal(
    labels.some((label) => /되돌리기|다시 하기|확정하기|배치하고 다듬기|다시 저장/.test(label)),
    false,
  );
  assert.equal(nodes.filter((node) => node.props?.role === "tab").length, 4);
});

test("paginatePlaySheet starts each template group on a titled page", () => {
  const rows = sheetHelpers.buildPlayProjectPreviewRows(plan(), { period0: ["cand0", "cand1"] });
  const groups = [rows.slice(0, 3), rows.slice(3)].map((group) =>
    group.map((row) => ({ ...row, height: 20, labelHeight: 10 })),
  );
  const pages = sheetHelpers.paginatePlaySheet(groups, {
    contentHeight: 100,
    titleHeight: 10,
    headerHeight: 10,
  });
  assert.equal(pages.length, 2);
  assert.deepEqual(
    pages.map((page) => [page.group, page.title]),
    [
      [0, true],
      [1, true],
    ],
  );
  assert.deepEqual(
    pages.map((page) => page.rows.map((row) => row.key)),
    groups.map((group) => group.map((row) => row.key)),
  );
});

test("paginatePlaySheet repeats the period label on a continuation and preserves row order", () => {
  const rows = sheetHelpers.buildPlayProjectPreviewRows(plan(), {
    period0: ["cand0", "cand1", "cand2"],
    period1: ["cand3"],
  });
  const groups = [rows.slice(0, 4), rows.slice(4)].map((group) =>
    group.map((row) => ({ ...row, height: 30, labelHeight: 10 })),
  );
  const pages = sheetHelpers.paginatePlaySheet(groups, {
    contentHeight: 100,
    titleHeight: 10,
    headerHeight: 10,
  });
  assert.deepEqual(
    pages.map((page) => [page.group, page.title]),
    [
      [0, true],
      [0, false],
      [1, true],
    ],
  );
  assert.deepEqual(
    pages.flatMap((page) => page.rows.map((row) => row.key)),
    rows.map((row) => row.key),
  );
  assert.equal(pages[0].rows[0].rowSpan, 2);
  const continuation = pages[1].rows[0];
  assert.equal(continuation.rowSpan, 1);
  assert.equal(continuation.period.label, "3월~5월");
  assert.equal(pages[1].rows[1].rowSpan, 1);
});

test("paginatePlaySheet leaves an oversize row alone without an empty page", () => {
  const rows = sheetHelpers.buildPlayProjectPreviewRows(plan(), { period0: ["cand0", "cand1"] });
  const pages = sheetHelpers.paginatePlaySheet(
    [
      [
        { ...rows[0], height: 200 },
        { ...rows[1], height: 20 },
      ],
    ],
    { contentHeight: 100, titleHeight: 10, headerHeight: 10 },
  );
  assert.deepEqual(
    pages.map((page) => [page.title, page.rows.length]),
    [
      [true, 1],
      [false, 1],
    ],
  );
  assert.equal(pages[0].rows[0].key, rows[0].key);
});

test("zoom steps round fit, move ten percent, and clamp manual zoom to 50–150", () => {
  const { stepPlaySheetZoom: zoom } = sheetHelpers;
  assert.equal(zoom(100, 1), 110);
  assert.equal(zoom(100, -1), 90);
  assert.equal(zoom(72, 1), 80);
  assert.equal(zoom(72, -1), 60);
  assert.equal(zoom(150, 1), 150);
  assert.equal(zoom(50, -1), 50);
  assert.equal(zoom(32, 1), 50);
  assert.equal(zoom(32, -1), 50);
});

test("both sheet steps expose page navigation and share manual zoom then return to fit", () => {
  const view = resultRenderer(plan(), [0, 1, { period0: ["cand0"] }, null]);
  let nodes = all(view.render());
  const button = (label) =>
    nodes.find(
      (node) =>
        node.type === "button" && (node.props["aria-label"] === label || text(node) === label),
    );
  for (const label of ["1쪽", "2쪽", "축소", "확대", "맞춤"]) assert.ok(button(label), label);
  button("확대").props.onClick();
  nodes = all(view.render());
  assert.ok(text(nodes).includes("110%"));
  button("③ 전체 초안 보기").props.onClick();
  nodes = all(view.render());
  assert.ok(text(nodes).includes("110%"));
  for (const label of ["1쪽", "2쪽", "축소", "확대", "맞춤"]) assert.ok(button(label), label);
  assert.equal(all(tables(nodes)).filter((node) => node.type === "button").length, 0);
  button("맞춤").props.onClick();
  nodes = all(view.render());
  assert.ok(text(nodes).includes("맞춤 100%"));
});

test("period tabs clear selection even for the current period and request its first row in both sheet steps", () => {
  const view = resultRenderer(plan(), [
    0,
    1,
    { period0: ["cand0"] },
    { periodKey: "period0", rowKey: "cand0", field: "play_name" },
  ]);
  for (const step of [1, 2]) {
    view.state[1] = step;
    view.state[3] = { periodKey: "period0", rowKey: "cand0", field: "play_name" };
    const tab = all(view.render()).find((node) => node.props?.role === "tab");
    tab.props.onClick();
    assert.equal(view.state[3], null);
    assert.equal(view.state[5].periodKey, "period0");
    assert.equal(view.state[5].request, step);
  }
});

test("reordering measured sheets retains continuation positions and refreshes text before measuring again", () => {
  const pp = plan();
  const picks = { period0: ["cand0", "cand1", "cand2"] };
  const rows = sheetHelpers
    .buildPlayProjectPreviewRows(pp, picks)
    .map((row) => ({ ...row, height: 30 }));
  const groups = [rows.slice(0, 4), rows.slice(4)];
  const dimensions = { contentHeight: 100, titleHeight: 10, headerHeight: 10 };
  const measured = {
    groups,
    dimensions,
    pages: sheetHelpers.paginatePlaySheet(groups, dimensions),
  };
  let cursor = 0;
  let zoom;
  const { default: MeasuredSheet } = compile("../components/plan-generator/PlayProjectSheet.tsx", {
    react: {
      useState: () => [[measured, 32][cursor++], () => {}],
      useRef: () => ({ current: null }),
      useEffect: () => {},
      useMemo: (compute) => compute(),
    },
    "./playProjectPagination": sheetHelpers,
    "./PlayProjectResult.module.css": esModule(resultStyles),
  });
  const render = (picks) => {
    cursor = 0;
    return all(
      resolve(
        jsx(MeasuredSheet, {
          plan: pp,
          picks,
          interactive: true,
          selectedCell: null,
          onSelectCell: () => {},
          zoom: { mode: "fit", percent: 100 },
          onZoomChange: (next) => (zoom = next),
          scrollPeriod: null,
        }),
      ),
    );
  };
  const before = render(picks);
  const after = render({ period0: ["cand2", "cand1", "cand0"] });
  assert.equal(before.filter((node) => node.props?.["data-page"] !== undefined).length, 3);
  assert.equal(after.filter((node) => node.props?.["data-page"] !== undefined).length, 3);
  assert.deepEqual(
    tables(after).map((table) =>
      all(table)
        .filter((node) => node.type === "tr")
        .map((row) => row.key),
    ),
    tables(before).map((table) =>
      all(table)
        .filter((node) => node.type === "tr")
        .map((row) => row.key),
    ),
  );
  assert.deepEqual(
    after.filter((node) => node.props?.["aria-label"]?.endsWith(" 놀이명")).map(text),
    ["놀이 2", "놀이 1", "놀이 0"],
  );
  assert.equal(after.find((node) => node.props?.className === "sheetPages").props.style.zoom, 0.32);
  assert.ok(text(after).includes("맞춤 32%"));
  after.find((node) => node.props?.["aria-label"] === "확대").props.onClick();
  assert.deepEqual(zoom, { mode: "manual", percent: 50 });
});

test("page and period navigation scroll to the requested target once", () => {
  const effects = [];
  const effectDeps = [];
  const frames = [];
  const scrolls = [];
  const windowScrolls = [];
  let targetTop = 800;
  let boxTop = 700;
  let measuredTarget;
  const row = { dataset: { period: "period3" } };
  const other = { dataset: { period: "period0" } };
  const cell = { dataset: { period: "period3", rowKey: "cand0", cell: "play_name" } };
  const pages = [{}, {}];
  for (const target of [row, other, cell, ...pages]) {
    target.getBoundingClientRect = () => {
      measuredTarget = target;
      return { top: targetTop, bottom: targetTop + 20, left: 0, right: 100 };
    };
  }
  const viewport = {
    querySelectorAll: (selector) =>
      selector === "tbody tr" ? [other, row] : selector === "[data-cell]" ? [cell] : pages,
    getBoundingClientRect: () => ({ top: boxTop, bottom: boxTop + 300, left: 0, right: 300 }),
    scrollBy: (delta) => {
      scrolls.push(delta);
      targetTop -= delta.top;
    },
  };
  const refs = [{ current: viewport }, { current: null }, { current: null }];
  let refIndex = 0;
  let effectIndex = 0;
  let memo;
  let memoDeps;
  let renderedPages;
  const planValue = plan();
  const picks = {};
  const { default: ScrollSheet } = compile(
    "../components/plan-generator/PlayProjectSheet.tsx",
    {
      react: {
        useState: (initial) => [typeof initial === "function" ? initial() : initial, () => {}],
        useRef: () => refs[refIndex++],
        useMemo: (compute, deps) => {
          if (!memoDeps || deps.some((value, i) => !Object.is(value, memoDeps[i]))) {
            memo = compute();
            memoDeps = deps;
          }
          return memo;
        },
        useEffect: (effect, deps) => {
          const index = effectIndex++;
          if (
            !effectDeps[index] ||
            deps.some((value, i) => !Object.is(value, effectDeps[index][i]))
          ) {
            effects[index] = effect;
            effectDeps[index] = deps;
          }
        },
      },
      "./playProjectPagination": {
        ...sheetHelpers,
        paginatePlaySheet: (...args) => (renderedPages ??= sheetHelpers.paginatePlaySheet(...args)),
      },
      "./PlayProjectResult.module.css": esModule(resultStyles),
    },
    undefined,
    (callback) => frames.push(callback),
    {
      matchMedia: () => ({ matches: true }),
      innerHeight: 600,
      scrollBy: (delta) => windowScrolls.push(delta),
    },
  );
  const render = (request) => {
    refIndex = 0;
    effectIndex = 0;
    effects.length = 0;
    return all(
      resolve(
        jsx(ScrollSheet, {
          plan: planValue,
          picks,
          interactive: true,
          selectedCell: null,
          onSelectCell: () => {},
          zoom: { mode: "fit", percent: 100 },
          onZoomChange: () => {},
          scrollPeriod: request,
        }),
      ),
    );
  };
  let nodes = render(null);
  nodes.find((node) => node.type === "button" && text(node) === "2쪽").props.onClick();
  assert.equal(measuredTarget, pages[1]);
  assert.deepEqual(scrolls.pop(), { top: 100, left: 0 });
  assert.deepEqual(windowScrolls.pop(), { top: 120 });

  boxTop = 300;
  targetTop = 400;
  nodes.find((node) => node.type === "button" && text(node) === "1쪽").props.onClick();
  assert.equal(measuredTarget, pages[0]);
  assert.equal(windowScrolls.length, 0);

  boxTop = 700;
  targetTop = 800;
  const request = { periodKey: "period3", request: 1 };
  nodes = render(request);
  effects[2]();
  frames.shift()();
  assert.equal(measuredTarget, row);
  assert.deepEqual(scrolls.pop(), { top: 100, left: 0 });
  assert.deepEqual(windowScrolls.pop(), { top: 120 });
  renderedPages = undefined;
  render(request); // Remeasure and changed pages must not repeat the request.
  effects[2]();
  assert.equal(frames.length, 0);
  render(null); // A step change clears the request.
  effects[2]();
  assert.equal(frames.length, 0);

  targetTop = 800;
  nodes = render({ periodKey: "period3", request: 2 });
  effects[2]();
  nodes.find((node) => node.type === "button" && text(node) === "2쪽").props.onClick();
  assert.equal(measuredTarget, pages[1]);
  scrolls.length = 0;
  frames.shift()();
  assert.equal(scrolls.length, 0);

  targetTop = 800;
  render({ periodKey: "period3", request: 3, cell: { rowKey: "cand0", field: "play_name" } });
  effects[2]();
  frames.shift()();
  assert.equal(measuredTarget, cell);
  assert.deepEqual(scrolls.pop(), { top: 0, left: 0 });
  assert.deepEqual(windowScrolls.pop(), { top: 220 });
});

test("window adjustment requires up to 80 pixels of the target to be visible", () => {
  assert.equal(windowScrollDelta({ top: 100, bottom: 180 }, 900), 0);
  assert.equal(windowScrollDelta({ top: -10, bottom: 40 }, 900), -10);
  assert.equal(windowScrollDelta({ top: 899, bottom: 999 }, 900), 79);
  assert.equal(windowScrollDelta({ top: 900, bottom: 950 }, 800), 150);
  assert.equal(windowScrollDelta({ top: 880, bottom: 900 }, 900), 0);
});

test("phone play and field selection do not request a sheet scroll", () => {
  const view = resultRenderer(plan(), [0, 1, { period0: ["cand0"] }, null]);
  let nodes = all(view.render());
  nodes.find((node) => node.type === "button" && text(node) === "놀이 0").props.onClick();
  assert.equal(view.state[5], null);
  nodes = all(view.render());
  nodes.find((node) => node.type === "button" && text(node) === "지원매체").props.onClick();
  assert.equal(view.state[5], null);
  assert.equal(view.state[3].field, "materials");
});

test("desktop play selection requests its cell and a step change clears it", () => {
  const view = resultRenderer(plan(), [0, 1, { period0: ["cand0"] }, null], true);
  const nodes = all(view.render());
  nodes.find((node) => node.type === "button" && text(node) === "놀이 0").props.onClick();
  assert.deepEqual(view.state[5].cell, { rowKey: "cand0", field: "play_name" });
  all(view.render())
    .find((node) => node.type === "button" && text(node) === "③ 전체 초안 보기")
    .props.onClick();
  assert.equal(view.state[5], null);
});

test("removing and readding a selected play cancels its pending scroll request", () => {
  const view = resultRenderer(plan(), [0, 1, { period0: ["cand0"] }, null], true);
  let nodes = all(view.render());
  nodes.find((node) => node.type === "button" && text(node) === "놀이 0").props.onClick();
  assert.equal(view.state[5].cell.rowKey, "cand0");
  nodes = all(view.render());
  nodes.find((node) => node.props?.["aria-label"] === "놀이 0 빼기").props.onClick();
  assert.equal(view.state[5], null);
  nodes = all(view.render());
  nodes.find((node) => node.props?.["aria-label"] === "놀이 0 넣기").props.onClick();
  assert.equal(view.state[5], null);
});

test("desktop selected oversized cells use nearest scrolling", () => {
  const effects = [];
  const frames = [];
  const scrolls = [];
  let rect = { top: 50, bottom: 500, left: 0, right: 200 };
  const cell = {
    dataset: { period: "period0", rowKey: "cand0", cell: "support_direction" },
    getBoundingClientRect: () => rect,
  };
  const viewport = {
    querySelectorAll: () => [cell],
    getBoundingClientRect: () => ({ top: 100, bottom: 400, left: 0, right: 300 }),
    scrollBy: (delta) => scrolls.push(delta),
  };
  const refs = [{ current: viewport }, { current: null }, { current: null }];
  let cursor = 0;
  const { default: ScrollSheet } = compile(
    "../components/plan-generator/PlayProjectSheet.tsx",
    {
      react: {
        useState: (initial) => [typeof initial === "function" ? initial() : initial, () => {}],
        useRef: () => refs[cursor++],
        useMemo: (compute) => compute(),
        useEffect: (effect) => effects.push(effect),
      },
      "./playProjectPagination": sheetHelpers,
      "./PlayProjectResult.module.css": esModule(resultStyles),
    },
    undefined,
    (callback) => frames.push(callback),
    { matchMedia: () => ({ matches: true }), innerHeight: 1000, scrollBy: () => {} },
  );
  for (const [index, nextRect, expected] of [
    [0, rect, 0],
    [1, { top: 50, bottom: 350, left: 0, right: 200 }, -50],
    [2, { top: 150, bottom: 550, left: 0, right: 200 }, 50],
  ]) {
    rect = nextRect;
    cursor = 0;
    effects.length = 0;
    ScrollSheet({
      plan: plan(),
      picks: { period0: ["cand0"] },
      interactive: true,
      selectedCell: null,
      onSelectCell: () => {},
      zoom: { mode: "fit", percent: 100 },
      onZoomChange: () => {},
      scrollPeriod: {
        periodKey: "period0",
        request: index,
        cell: { rowKey: "cand0", field: "support_direction" },
      },
    });
    effects[2]();
    frames.shift()();
    assert.deepEqual(scrolls.pop(), { top: expected, left: 0 });
  }
});

const statusText = (nodes) => text(nodes.find((node) => node.props?.role === "status"));
test("picks start from the server's selected lists, so a reload keeps them", () => {
  const saved = plan();
  saved.periods[0].selected = ["cand4", "cand1"];
  const nodes = all(resultRenderer(saved).render());
  const tabs = nodes.filter((node) => node.props?.role === "tab").map(text);
  assert.deepEqual(tabs, ["3월~5월 · 2/5", "6월~8월 · 0/5", "9월~11월 · 0/5", "12월~2월 · 0/5"]);
});

test("every picking change goes through one save call with all four periods", () => {
  saveStub.calls.length = 0;
  const view = resultRenderer(plan());
  pickToggles(all(view.render()))[2].props.onClick();
  assert.deepEqual(saveStub.calls.pop(), {
    period0: ["cand2"],
    period1: [],
    period2: [],
    period3: [],
  });
  pickToggles(all(view.render()))[0].props.onClick();
  assert.deepEqual(saveStub.calls.pop().period0, ["cand2", "cand0"]);
  all(view.render())
    .find((node) => node.props?.["aria-label"] === "놀이 2 빼기")
    .props.onClick();
  assert.deepEqual(saveStub.calls.pop().period0, ["cand0"]);
  assert.equal(saveStub.calls.length, 0);
});

test("a pick that changes nothing (sixth play) is not saved", () => {
  saveStub.calls.length = 0;
  const full = plan();
  full.periods[0].selected = ["cand0", "cand1", "cand2", "cand3", "cand4"];
  const view = resultRenderer(full);
  const sixth = pickToggles(all(view.render())).find((node) =>
    node.props["aria-label"].includes("「놀이 5」"),
  );
  assert.ok(sixth);
  sixth.props.onClick();
  assert.equal(saveStub.calls.length, 0);
});

test("save status shows in a status line with a retry button only on failure", () => {
  const { default: Result } = playResult();
  const render = (status) => {
    saveStub.status = status;
    return all(resolve(jsx(Result, { plan: plan(), onConflict: () => {} })));
  };
  try {
    assert.equal(statusText(render("idle")), "");
    assert.equal(statusText(render("saving")), "저장 중…");
    assert.equal(statusText(render("saved")), "저장됨");
    assert.equal(
      render("saved").some((node) => node.type === "button" && text(node) === "다시 저장"),
      false,
    );
    const failed = render("failed");
    assert.equal(statusText(failed), "저장하지 못했어요");
    const retries = saveStub.retries;
    failed.find((node) => node.type === "button" && text(node) === "다시 저장").props.onClick();
    assert.equal(saveStub.retries, retries + 1);
  } finally {
    saveStub.status = "idle";
  }
});

test("the reloaded-after-conflict notice shows up as a status message", () => {
  const { default: Result } = playResult();
  const message = "다른 곳에서 바뀌었어요. 최신 내용을 다시 불러왔어요.";
  const nodes = all(resolve(jsx(Result, { plan: plan(), notice: message })));
  assert.ok(nodes.some((node) => node.props?.role === "status" && text(node) === message));
});

test("AnnualResult reloads the plan on a save conflict and keeps the notice", async () => {
  const first = plan();
  const fresh = { ...plan(), revision: 9 };
  fresh.periods[0].selected = ["cand7"];
  let served = first;
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
    react: {
      useState: stateHook,
      useRef: (value) => ({ current: value }),
      useEffect: (effect) => effects.push(effect),
    },
    "next/navigation": { useRouter: () => ({ push: () => {} }) },
    "@/components/app/AppHeader": esModule(() => jsx("app-header", {})),
    "@/lib/api/plans": { getAnnualPlan: async () => served },
    "@/lib/plan-generator/context": { loadAnnualContext: () => undefined },
    "./GenerationFlow": esModule(() => jsx("generation-flow", {})),
    "./PlayProjectResult": esModule(() => jsx("play-project-result", {})),
  });
  const render = () => {
    cursor = 0;
    return all(Result({ id: first.id }));
  };
  const shown = () => render().find((node) => node.props?.onConflict);
  render();
  effects[0]();
  await new Promise((resolve) => setImmediate(resolve));
  const before = shown();
  assert.equal(before.props.notice, undefined);
  served = fresh;
  before.props.onConflict();
  await new Promise((resolve) => setImmediate(resolve));
  const after = shown();
  assert.equal(after.props.plan.revision, 9);
  assert.deepEqual(after.props.plan.periods[0].selected, ["cand7"]);
  assert.equal(after.props.notice, "다른 곳에서 바뀌었어요. 최신 내용을 다시 불러왔어요.");
  assert.notEqual(after.key, before.key);
});

test("every way of changing picks saves all four periods as the full body", () => {
  const full = (period0, period1 = []) => ({ period0, period1, period2: [], period3: [] });
  const start = { period0: ["cand0", "cand1", "cand2"], period1: ["cand4"] };
  const after = (step, tab, desktop, act) => {
    saveStub.calls.length = 0;
    const view = resultRenderer(plan(), FULL_STATE({ ...start }, step, tab), desktop);
    act(all(view.render()), view);
    assert.equal(saveStub.calls.length, 1);
    return saveStub.calls[0];
  };
  const byLabel = (nodes, label) => nodes.find((node) => node.props?.["aria-label"] === label);
  // ① 선택 · 해제(× 와 같은 흐름)
  assert.deepEqual(
    after(0, "edit", false, (nodes) => byLabel(nodes, "「놀이 5」 선택하기").props.onClick()),
    full(["cand0", "cand1", "cand2", "cand5"], ["cand4"]),
  );
  assert.deepEqual(
    after(0, "edit", false, (nodes) => byLabel(nodes, "「놀이 1」 선택됨").props.onClick()),
    full(["cand0", "cand2"], ["cand4"]),
  );
  // ① 오른쪽 목록의 ×
  assert.deepEqual(
    after(0, "edit", false, (nodes) => byLabel(nodes, "놀이 0 빼기").props.onClick()),
    full(["cand1", "cand2"], ["cand4"]),
  );
  // ② ↑ ↓ · 빼기 · 넣기
  assert.deepEqual(
    after(1, "picked", false, (nodes) => byLabel(nodes, "1번째 놀이 아래로").props.onClick()),
    full(["cand1", "cand0", "cand2"], ["cand4"]),
  );
  assert.deepEqual(
    after(1, "picked", false, (nodes) => byLabel(nodes, "놀이 2 빼기").props.onClick()),
    full(["cand0", "cand1"], ["cand4"]),
  );
  assert.deepEqual(
    after(1, "picked", false, (nodes) => byLabel(nodes, "놀이 7 넣기").props.onClick()),
    full(["cand0", "cand1", "cand2", "cand7"], ["cand4"]),
  );
  // ② 끌어놓기: 문서 행 → 다른 문서 행
  assert.deepEqual(
    after(1, "edit", DESKTOP, (nodes, view) => {
      draggableRows(nodes)[0].props.onDragStart(dragEvent());
      draggableRows(all(view.render()))[2].props.onDrop(dragEvent());
    }),
    full(["cand1", "cand2", "cand0"], ["cand4"]),
  );
});

test("two picks changed before a re-render both survive (latest value, not the render's)", () => {
  saveStub.calls.length = 0;
  const view = resultRenderer(plan());
  const nodes = all(view.render());
  pickToggles(nodes)[3].props.onClick();
  pickToggles(nodes)[1].props.onClick();
  assert.deepEqual(saveStub.calls.at(-1).period0, ["cand3", "cand1"]);
});

test("the stale notice is dismissed when the next pick is made", () => {
  const { default: Result } = playResult();
  let dismissed = 0;
  const nodes = all(
    resolve(
      jsx(Result, { plan: plan(), onDismissNotice: () => dismissed++, onConflict: () => {} }),
    ),
  );
  pickToggles(nodes)[0].props.onClick();
  assert.equal(dismissed, 1);
});

test("overlapping conflict reloads keep only the last request's plan, and picking dismisses the notice", async () => {
  const first = plan();
  const answers = [];
  const state = [];
  const refs = [];
  const effects = [];
  let cursor = 0;
  let refCursor = 0;
  let calls = 0;
  const stateHook = (initial) => {
    const index = cursor++;
    if (!(index in state)) state[index] = typeof initial === "function" ? initial() : initial;
    return [
      state[index],
      (value) => (state[index] = typeof value === "function" ? value(state[index]) : value),
    ];
  };
  const { default: Result } = compile("../components/plan-generator/AnnualResult.tsx", {
    react: {
      useState: stateHook,
      useRef: (value) => (refs[refCursor] ??= { current: value }) && refs[refCursor++],
      useEffect: (effect) => effects.push(effect),
    },
    "next/navigation": { useRouter: () => ({ push: () => {} }) },
    "@/components/app/AppHeader": esModule(() => jsx("app-header", {})),
    "@/lib/api/plans": {
      getAnnualPlan: () =>
        calls++ === 0 ? Promise.resolve(first) : new Promise((resolve) => answers.push(resolve)),
    },
    "@/lib/plan-generator/context": { loadAnnualContext: () => undefined },
    "./GenerationFlow": esModule(() => jsx("generation-flow", {})),
    "./PlayProjectResult": esModule(() => jsx("play-project-result", {})),
  });
  const render = () => {
    cursor = 0;
    refCursor = 0;
    return all(Result({ id: first.id }));
  };
  const shown = () => render().find((node) => node.props?.onConflict);
  render();
  effects[0]();
  await new Promise((resolve) => setImmediate(resolve));
  const screen = shown();
  const older = screen.props.onConflict();
  const newer = screen.props.onConflict();
  answers[1]({ ...plan(), revision: 8 });
  await newer;
  answers[0]({ ...plan(), revision: 5 }); // 늦게 온 옛 응답
  await older;
  assert.equal(shown().props.plan.revision, 8);
  assert.ok(shown().props.notice);
  shown().props.onDismissNotice();
  assert.equal(shown().props.notice, undefined);
});

// ── 칸 편집 · 되돌리기 (ADR-044 §2) ──
const editing = (field = "play_name", tab = "edit") => {
  const served = plan();
  const cell = served.periods[0].candidates[2][field];
  const view = resultRenderer(
    served,
    FULL_STATE({ period0: ["cand2"] }, 1, tab, null, {
      periodKey: "period0",
      rowKey: "cand2",
      field,
    }),
  );
  saveStub.calls.length = 0;
  saveStub.cells.length = 0;
  view.render();
  return { view, cell };
};
const historyButton = (nodes, name) =>
  nodes.find((node) => node.type === "button" && text(node).trim().endsWith(name));

test("the edit tab shows an editor for the picked play's name, materials, and support direction", () => {
  for (const [field, value] of [
    ["play_name", "놀이 2"],
    ["materials", "종이 상자"],
    ["support_direction", "관심을 따라 돕습니다."],
  ]) {
    const { view, cell } = editing(field);
    const nodes = all(view.render());
    assert.equal(editorStub.props.id, "play-project-selected-cell");
    assert.equal(editorStub.props.value, value);
    assert.equal(editorStub.props.label, fieldLabel(field));
    assert.ok(cell.item_id);
    assert.ok(!nodes.some((node) => text(node).includes("아직 수정 기능은 제공하지 않아요")));
  }
});
const fieldLabel = (field) =>
  ({ play_name: "놀이명", materials: "지원매체", support_direction: "지원 방향" })[field];

test("the learning tab stays read-only with the curriculum note", () => {
  const { view } = editing("learning");
  editorStub.props = null;
  const nodes = all(view.render());
  assert.equal(editorStub.props, null);
  const area = nodes.find((node) => node.type === "textarea");
  assert.equal(area.props.readOnly, true);
  assert.equal(area.props.value, "배움 한 줄\n배움 두 줄");
  assert.ok(nodes.some((node) => text(node) === "배움은 누리과정 원문이라 고칠 수 없어요."));
});

test("saving a cell sends it once with the last saved value, and the document shows it", () => {
  const { view, cell } = editing();
  editorStub.props.onSave("새 놀이 이름");
  assert.deepEqual(saveStub.cells, [
    { itemId: cell.item_id, value: "새 놀이 이름", base: "놀이 2" },
  ]);
  const nodes = all(view.render());
  assert.equal(editorStub.props.value, "새 놀이 이름");
  assert.ok(text(nodes).includes("새 놀이 이름"));
  // 같은 값은 보내지 않는다 — 서버는 같은 값을 422 로 거절한다.
  editorStub.props.onSave("새 놀이 이름");
  assert.equal(saveStub.cells.length, 1);
  // 다음 저장의 base 는 방금 저장한 값이다.
  editorStub.props.onSave("또 고침");
  assert.equal(saveStub.cells[1].base, "새 놀이 이름");
});

test("typing shows in the document at once, and a revert brings the saved text back", () => {
  const { view } = editing();
  editorStub.props.onDraft("입력 중인 글");
  assert.ok(text(view.render()).includes("입력 중인 글"));
  assert.equal(saveStub.cells.length, 0);
  editorStub.props.onRevert();
  const after = text(view.render());
  assert.ok(!after.includes("입력 중인 글"));
  assert.ok(after.includes("놀이 2"));
});

test("undo and redo buttons start disabled, and undo re-saves the old value with the same cell call", () => {
  const { view, cell } = editing();
  let nodes = all(view.render());
  assert.equal(historyButton(nodes, "되돌리기").props.disabled, true);
  assert.equal(historyButton(nodes, "다시 하기").props.disabled, true);
  editorStub.props.onSave("새 놀이 이름");
  nodes = all(view.render());
  assert.equal(historyButton(nodes, "되돌리기").props.disabled, false);
  historyButton(nodes, "되돌리기").props.onClick();
  assert.deepEqual(saveStub.cells.at(-1), {
    itemId: cell.item_id,
    value: "놀이 2",
    base: "새 놀이 이름",
  });
  nodes = all(view.render());
  assert.ok(text(nodes).includes("되돌렸어요"));
  assert.equal(editorStub.props.value, "놀이 2");
  assert.equal(historyButton(nodes, "되돌리기").props.disabled, true);
  historyButton(nodes, "다시 하기").props.onClick();
  assert.equal(saveStub.cells.at(-1).value, "새 놀이 이름");
  assert.ok(text(all(view.render())).includes("다시 했어요"));
});

test("a new change empties redo, and picks and cell edits undo from one list", () => {
  const { view, cell } = editing("play_name", "picked");
  editorStub.props.onSave("새 놀이 이름");
  // 고르기를 하나 더 한다 — 같은 목록의 두 번째 걸음이다.
  all(view.render())
    .find((node) => node.props?.["aria-label"] === "새 놀이 이름 빼기")
    .props.onClick();
  assert.deepEqual(saveStub.calls.pop().period0, []);
  let nodes = all(view.render());
  historyButton(nodes, "되돌리기").props.onClick(); // 빼기를 되돌린다
  assert.deepEqual(saveStub.calls.pop().period0, ["cand2"]);
  assert.equal(saveStub.cells.length, 1);
  nodes = all(view.render());
  assert.equal(historyButton(nodes, "다시 하기").props.disabled, false);
  historyButton(nodes, "되돌리기").props.onClick(); // 칸 글을 되돌린다
  assert.equal(saveStub.calls.length, 0);
  assert.equal(saveStub.cells.at(-1).itemId, cell.item_id);
  assert.equal(saveStub.cells.at(-1).value, "놀이 2");
  // 새 변경이 오면 다시 하기가 비워진다.
  // (이 시점의 입력창은 이미 새 번호로 바뀌었다 — 옛 props 의 글은 버려진다.)
  nodes = all(view.render());
  nodes.find((node) => node.props?.["aria-label"] === "놀이 3 넣기").props.onClick();
  nodes = all(view.render());
  assert.equal(historyButton(nodes, "다시 하기").props.disabled, true);
});

test("undo or redo of a cell gives the editor a new key, so it never keeps the old text", () => {
  const { view } = editing();
  editorStub.props.onSave("새 놀이 이름");
  view.render();
  const before = editorStub.key;
  historyButton(all(view.render()), "되돌리기").props.onClick();
  view.render();
  const undone = editorStub.key;
  assert.notEqual(undone, before);
  historyButton(all(view.render()), "다시 하기").props.onClick();
  view.render();
  assert.notEqual(editorStub.key, undone);
  // 저장만으로는 키가 바뀌지 않는다 — 입력 중 포커스를 잃지 않는다.
  const stable = editorStub.key;
  editorStub.props.onSave("계속 입력");
  view.render();
  assert.equal(editorStub.key, stable);
});

test("saving the trimmed server value again sends nothing", () => {
  const { view } = editing();
  editorStub.props.onSave("놀이 2");
  assert.equal(saveStub.cells.length, 0);
  assert.equal(historyButton(all(view.render()), "되돌리기").props.disabled, true);
});

test("a rejected cell goes back to the confirmed value with a status notice and an empty history", () => {
  const { view, cell } = editing();
  editorStub.props.onSave("새 놀이 이름");
  view.render();
  saveStub.rejected({ kind: "cell", itemId: cell.item_id, value: "놀이 2" });
  const nodes = all(view.render());
  assert.equal(editorStub.props.value, "놀이 2");
  assert.ok(
    nodes.some(
      (node) =>
        node.props?.role === "status" && text(node) === "저장하지 못한 칸은 원래대로 되돌렸어요.",
    ),
  );
  assert.equal(historyButton(nodes, "되돌리기").props.disabled, true);
});

test("a rejected pick save puts the confirmed picks back", () => {
  const { view } = editing();
  saveStub.rejected({
    kind: "picks",
    selections: { period0: [], period1: [], period2: [], period3: [] },
  });
  const nodes = all(view.render());
  assert.ok(text(nodes).includes("저장하지 못한 고르기는 원래대로 되돌렸어요."));
  assert.equal(nodes.filter((node) => node.props?.role === "tab").map(text)[0], "3월~5월 · 0/5");
});

test("the same announcement twice in a row changes its text so it is read again", () => {
  const { view } = editing();
  editorStub.props.onSave("A");
  editorStub.props.onSave("B");
  const notices = [];
  for (const name of ["되돌리기", "되돌리기"]) {
    historyButton(all(view.render()), name).props.onClick();
    notices.push(statusTexts(all(view.render())).find((line) => line.startsWith("되돌렸어요")));
  }
  assert.notEqual(notices[0], notices[1]);
});
const statusTexts = (nodes) => nodes.filter((node) => node.props?.role === "status").map(text);

test("typing keeps the leave-page warning on until the draft is saved or put back", () => {
  const { view } = editing();
  editorStub.props.onDraft("입력 중");
  view.render();
  assert.equal(saveStub.drafting, true);
  editorStub.props.onRevert();
  view.render();
  assert.equal(saveStub.drafting, false);
});

test("a rejection reopens only that cell's editor, and its old editor can no longer save", () => {
  const { view, cell } = editing("materials");
  view.render();
  const stable = editorStub.key;
  const old = editorStub.props;
  const other = plan().periods[0].candidates[2].play_name.item_id;
  saveStub.rejected({ kind: "cell", itemId: other, value: "놀이 2" });
  view.render();
  assert.equal(editorStub.key, stable);
  saveStub.rejected({ kind: "cell", itemId: cell.item_id, value: "종이 상자" });
  view.render();
  assert.notEqual(editorStub.key, stable);
  old.onSave("옛 입력창의 글"); // 사라지는 입력창의 저장은 버려진다
  assert.equal(saveStub.cells.length, 0);
});

test("while confirming, the step buttons, undo and redo and the confirm button are all off", () => {
  resetConfirm();
  const { view } = confirmView();
  view.state[13] = true; // confirming
  const nodes = all(view.render());
  const steps = nodes.filter((node) => node.props?.className === "stepButton");
  assert.equal(steps.length, 3);
  assert.ok(steps.every((node) => node.props.disabled === true));
  const labels = ["되돌리기", "다시 하기"];
  const history = nodes.filter(
    (node) => node.type === "button" && labels.some((l) => text(node).includes(l)),
  );
  assert.equal(history.length, 2);
  assert.ok(history.every((node) => node.props.disabled === true));
  assert.equal(confirmButton(nodes).props.disabled, true);
  // 아닐 때는 단계 버튼이 켜져 있다.
  const idle = all(confirmView().view.render());
  assert.ok(
    idle.filter((n) => n.props?.className === "stepButton").every((n) => !n.props.disabled),
  );
});

test("a save the server rejects while the confirm waits stops the confirm (real queue)", async () => {
  resetConfirm();
  const { createSaveQueue } = compile("../lib/plan-generator/playSelectionQueue.ts", {});
  const sends = [];
  const rejected = [];
  saveStub.queue = createSaveQueue({
    revision: 3,
    selections: {},
    send: async () => ({ revision: 4 }),
    sendCell: (itemId) =>
      new Promise((_resolve, reject) => sends.push(() => reject({ status: 422, itemId }))),
    isConflict: () => false,
    isRejected: (error) => error?.status === 422,
    onStatus: () => {},
    onRejected: (r) => rejected.push(r),
    onConflict: async () => {},
  });
  try {
    saveStub.queue.enqueueCell("item_x", "새 글", "옛 글"); // 입력 중이던 글 — blur 가 넣은 것과 같다
    const { view, confirmed } = confirmView();
    const click = confirmButton(all(view.render())).props.onClick();
    await new Promise((resolve) => setImmediate(resolve));
    assert.equal(confirmStub.calls.length, 0); // PUT 이 끝나기 전에는 confirm 이 없다
    sends[0](); // 서버가 422 로 거절
    await click;
    assert.equal(rejected.length, 1);
    assert.deepEqual(confirmStub.calls, []);
    assert.deepEqual(confirmed, []);
    assert.equal(
      text(all(view.render()).find((node) => node.props?.role === "alert")),
      "저장하지 못했어요. 다시 저장한 뒤 확정해 주세요.",
    );
  } finally {
    saveStub.queue = null;
  }
});

test("a screen that went down while waiting sends no confirm and calls nothing back", async () => {
  resetConfirm();
  let release;
  saveStub.gate = new Promise((resolve) => (release = resolve));
  const { view, confirmed, conflicts } = confirmView();
  const nodes = all(view.render());
  const cleanups = view.mount();
  const click = confirmButton(nodes).props.onClick();
  await new Promise((resolve) => setImmediate(resolve));
  cleanups.forEach((cleanup) => cleanup()); // 언마운트
  release();
  await click;
  assert.deepEqual(confirmStub.calls, []);
  assert.deepEqual(confirmed, []);
  assert.deepEqual(conflicts, []);
});

test("a confirm response that arrives after the screen went down is not handed on", async () => {
  resetConfirm();
  const { view, confirmed } = confirmView();
  const cleanups = (view.render(), view.mount());
  const click = confirmButton(all(view.render())).props.onClick();
  cleanups.forEach((cleanup) => cleanup()); // whenIdle 이 끝나기 전에 내려간다
  await click;
  assert.deepEqual(confirmed, []);
});

const exportButton = (nodes) =>
  nodes.find(
    (node) => node.type === "button" && /한글 파일로 내려받기|내려받는 중/.test(text(node)),
  );
function confirmedView() {
  const confirmedPlan = plan();
  confirmedPlan.status = "CONFIRMED";
  confirmedPlan.periods.forEach((item) => (item.selected = FULL));
  hwpxStub.ran = [];
  hwpxStub.message = "";
  hwpxStub.exporting = false;
  return resultRenderer(confirmedPlan, [], false, { onConfirmed: () => {} });
}

test("a confirmed plan has a download button that fetches that plan's hwpx", async () => {
  const view = confirmedView();
  const button = exportButton(all(view.render()));
  assert.equal(text(button), "한글 파일로 내려받기");
  assert.notEqual(button.props.disabled, true);
  await button.props.onClick();
  assert.deepEqual(hwpxStub.ran, [plan().id]);
});

test("while downloading the button is off and says 내려받는 중…", () => {
  const view = confirmedView();
  hwpxStub.exporting = true;
  const button = exportButton(all(view.render()));
  assert.equal(text(button), "내려받는 중…");
  assert.equal(button.props.disabled, true);
});

test("a failed download shows the server's words", async () => {
  const view = confirmedView();
  hwpxStub.message = "놀이 프로젝트형 연간계획안은 확정한 뒤 내려받을 수 있습니다.";
  await exportButton(all(view.render())).props.onClick();
  assert.match(text(view.render()), /확정한 뒤 내려받을 수 있습니다\./);
});
