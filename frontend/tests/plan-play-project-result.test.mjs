// 놀이 중심형 연간 ④ · ⑤ (PlayProjectResult) — 순수 도우미와 고르기 · 칸 편집 · 확정 흐름만 본다.
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
      if (name === "./PlanMemo") return { PlanMemoNote: () => null };
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
const sheetHelpers = compile("../components/plan-generator/playProjectPagination.ts", {});
const { default: Sheet } = compile("../components/plan-generator/PlayProjectSheet.tsx", {
  "./playProjectPagination": sheetHelpers,
  "./rowDrag": compile("../components/plan-generator/rowDrag.ts", {
    "@/lib/appZoom": { appZoom: () => 1 },
  }),
  "./PlayMonthlySheet": { HATCH: "hatch" },
});
// 입력창 대역 — 화면이 넘긴 값과 콜백만 본다. 입력창 규칙은 play-cell-editor.test.mjs 가 다룬다.
const editorStub = { props: null };
const CellEditor = (props) => ((editorStub.props = props), jsx("cell-editor", props));
// 저장 훅 대역 — 화면이 무엇을 저장하라고 넘겼는지만 본다. 큐 규칙은 따로 시험한다.
const saveStub = { calls: [], cells: [], idle: { saved: true, revision: 9 }, log: [] };
const confirmStub = { calls: [], next: null };
class StubApiError extends Error {
  constructor(status, fields) {
    super("서버 문구");
    this.status = status;
    this.body = { error: { fields } };
  }
}
const plansStub = {
  confirmPlayProject: async (id, revision) => {
    saveStub.log.push("confirm");
    confirmStub.calls.push({ id, revision });
    if (confirmStub.next instanceof Error) throw confirmStub.next;
    return confirmStub.next;
  },
  isSaveConflict: (error) => error?.status === 409,
  errorFields: (error) => error?.body?.error?.fields ?? [],
  downloadAnnualHwpx: async () => {},
};
const frameModules = {
  "next/link": esModule((props) => jsx("a", props)),
  "@/components/workspace/WorkspaceUI": { Tape: () => null },
  "@/lib/api/plans": plansStub,
  "@/lib/hooks/use-hwpx-download": { useHwpxDownload: () => ({ exporting: false }) },
  "./playProjectPagination": sheetHelpers,
};

// 훅을 부른 순서대로 칸에 담는 대역. effect 는 시험이 부르지 않는다.
function renderer(planValue, props = {}) {
  const slots = [];
  let index = 0;
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
    useEffect() {},
    useMemo: (compute) => compute(),
  };
  const { default: Frame, ...frameRest } = compile("../components/plan-generator/AnnualFrame.tsx", {
    react,
    ...frameModules,
  });
  const { default: Result } = compile(
    "../components/plan-generator/PlayProjectResult.tsx",
    {
      react,
      "next/link": esModule((props) => jsx("a", props)),
      "@/components/workspace/Workspace.module.css": esModule(new Proxy({}, { get: (_, k) => k })),
      "./GenerationFlow.module.css": esModule(new Proxy({}, { get: (_, k) => k })),
      "./PlayProjectResult.module.css": esModule(new Proxy({}, { get: (_, k) => k })),
      "./PlayProjectPicking": esModule((p) => jsx("picking", p)),
      "@/components/plan-ui/PlayPickBoard": { MemoMark: () => jsx("memo-mark", {}) },
      "./PlayProjectSheet": esModule(Sheet),
      "./PlayCellEditor": esModule(CellEditor),
      "./PlayMonthlyConfirm": esModule((p) => jsx("confirm-dialog", p)),
      "./AnnualFrame": { __esModule: true, default: Frame, ...frameRest },
      "@/lib/plan-generator/playEditHistory": compile(
        "../lib/plan-generator/playEditHistory.ts",
        {},
      ),
      "@/lib/api/client": { ApiError: StubApiError },
      "@/lib/api/plans": plansStub,
      "@/lib/hooks/use-play-selection-save": {
        usePlaySelectionSave: () => ({
          status: "idle",
          save: (selections) => saveStub.calls.push(selections),
          saveCell: (itemId, value, base) => saveStub.cells.push({ itemId, value, base }),
          retry: () => {},
          whenIdle: async () => (saveStub.log.push("whenIdle"), saveStub.idle),
        }),
      },
      "./playProjectPagination": sheetHelpers,
    },
    { activeElement: null, getElementById: () => null },
    () => {},
  );
  return () => {
    index = 0;
    return resolve(jsx(Result, { plan: planValue, onConflict: async () => {}, ...props }));
  };
}
const FULL = ["cand0", "cand1", "cand2", "cand3", "cand4"];
function fullPlan() {
  const p = plan();
  for (const period of p.periods) period.selected = [...FULL];
  return p;
}
const button = (tree, name) =>
  all(tree).find(
    (n) => n.type === "button" && (text(n) === name || n.props["aria-label"] === name),
  );
const selectedTab = (tree, label) =>
  all(tree).find(
    (n) => n.props?.role === "tab" && n.props["aria-selected"] && text(n).startsWith(label),
  );

test("helpers: five picks in order, moves, removal focus, and the left tab keys", () => {
  const { togglePlayPick, placePlayPick, removeFocusSlot, leftTabTarget } = compile(
    "../components/plan-generator/PlayProjectResult.tsx",
    new Proxy({}, { has: () => true, get: () => ({}) }),
  );
  const five = ["cand3", "cand1", "cand8", "cand2", "cand9"];
  assert.deepEqual(togglePlayPick([], "cand3"), ["cand3"]);
  assert.deepEqual(togglePlayPick(five, "cand4"), five);
  assert.deepEqual(togglePlayPick(five, "cand1"), ["cand3", "cand8", "cand2", "cand9"]);
  // 끌어놓기: 끈 놀이가 놓은 줄의 자리로 간다. 고르지 않은 놀이 · 같은 줄은 그대로.
  assert.deepEqual(placePlayPick(FULL, "cand1", "cand3"), [
    "cand0",
    "cand2",
    "cand3",
    "cand1",
    "cand4",
  ]);
  assert.deepEqual(placePlayPick(FULL, "cand3", "cand0"), [
    "cand3",
    "cand0",
    "cand1",
    "cand2",
    "cand4",
  ]);
  // 다른 후보를 끌어 놓으면 다 찼을 때는 그 줄과 바뀌고, 자리가 남으면 그 줄 앞에 들어간다.
  assert.deepEqual(placePlayPick(FULL, "cand9", "cand1"), [
    "cand0",
    "cand9",
    "cand2",
    "cand3",
    "cand4",
  ]);
  assert.deepEqual(placePlayPick(["cand0", "cand1"], "cand9", "cand1"), [
    "cand0",
    "cand9",
    "cand1",
  ]);
  assert.equal(placePlayPick(FULL, "cand9", "cand8"), FULL);
  assert.equal(placePlayPick(FULL, "cand2", "cand2"), FULL);
  assert.equal(removeFocusSlot(3, 1), 1);
  assert.equal(removeFocusSlot(3, 2), null);
  assert.equal(leftTabTarget("ArrowRight", "picked"), "edit");
  assert.equal(leftTabTarget("Home", "edit"), "picked");
  assert.equal(leftTabTarget("End", "picked"), "edit");
  assert.equal(leftTabTarget("Enter", "edit"), null);
});

test("a short plan opens ④ picking; arranging opens ⑤ with AI 후보 · 칸 편집 tabs", () => {
  const render = renderer(plan());
  const picking = all(render()).find((n) => n.type === "picking");
  picking.props.onArrange();
  const tree = render();
  assert.ok(selectedTab(tree, "AI 후보"));
  assert.ok(all(tree).some((n) => n.props?.role === "tab" && text(n) === "칸 편집"));
  assert.match(text(tree), /3월~5월 0\/5/);
});

test("⑤: a document cell opens 칸 편집 and the editor saves that cell; 빼기 saves four periods", () => {
  saveStub.calls = [];
  saveStub.cells = [];
  const p = fullPlan();
  const render = renderer(p);
  button(render(), "놀이 1 지원매체").props.onClick();
  let tree = render();
  assert.ok(selectedTab(tree, "칸 편집"));
  const cell = p.periods[0].candidates[1].materials;
  assert.equal(editorStub.props.value, cell.value);
  editorStub.props.onSave("나뭇잎");
  assert.deepEqual(saveStub.cells, [{ itemId: cell.item_id, value: "나뭇잎", base: cell.value }]);
  assert.match(text(render()), /나뭇잎/, "문서에 바로 보인다");
  all(render())
    .find((n) => n.props?.role === "tab" && text(n) === "AI 후보")
    .props.onClick();
  button(render(), "놀이 0 빼기").props.onClick();
  assert.deepEqual(Object.keys(saveStub.calls.at(-1)), [
    "period0",
    "period1",
    "period2",
    "period3",
  ]);
  assert.deepEqual(saveStub.calls.at(-1).period0, ["cand1", "cand2", "cand3", "cand4"]);
  const pages = (tree) =>
    all(tree)
      .filter((n) => n.type === "article")
      .map((n) => n.props["aria-label"]);
  assert.deepEqual(pages(render()), ["3월~5월"], "편집은 구간마다 한 쪽");
  button(render(), "⤢ 크게 보기").props.onClick();
  // 편집 문서는 그대로 두고, 따로 뜨는 창에 원래 문서처럼 두 구간씩 한 쪽(창은 문서 머리줄에 있어 나무에서 앞).
  assert.deepEqual(pages(render()).sort(), ["3월~5월", "3월~5월 · 6월~8월"]);
  button(render(), "2쪽").props.onClick();
  assert.deepEqual(pages(render()).sort(), ["3월~5월", "9월~11월 · 12월~2월"], "쪽을 골라 본다");
  all(render())
    .find((n) => n.type === "dialog")
    .props.onClose();
  assert.deepEqual(pages(render()), ["3월~5월"], "닫으면 창 안 문서도 내린다");
});

test("confirm asks first, waits for the queue, then confirms with its revision", async () => {
  saveStub.log = [];
  confirmStub.calls = [];
  confirmStub.next = { id: 41, status: "CONFIRMED" };
  const done = [];
  const render = renderer(fullPlan(), { onConfirmed: (next) => done.push(next) });
  button(render(), "확정하기").props.onClick();
  const dialog = all(render()).find((n) => n.type === "confirm-dialog");
  assert.equal(
    dialog.props.message,
    "확정하면 고칠 수 없어요. 고치려면 문서 보관함에서 「수정하기」를 눌러요.\n이 내용으로 월간계획안을 만들게 돼요.",
  );
  assert.equal(dialog.props.no, "더 다듬기");
  await dialog.props.onYes();
  assert.deepEqual(saveStub.log, ["whenIdle", "confirm"]);
  assert.deepEqual(confirmStub.calls, [{ id: 41, revision: 9 }]);
  assert.deepEqual(done, [confirmStub.next]);
});

test("확정 전 빈 곳 — 5개를 다 고르지 않은 기간은 흔들리는 알림에서 그 기간 AI 후보로 보낸다", () => {
  const p = fullPlan();
  p.periods[1].selected = FULL.slice(0, 2);
  const render = renderer(p);
  all(render())
    .find((n) => n.type === "picking")
    .props.onArrange();
  button(render(), "확정하기").props.onClick();
  const ask = all(render()).find((n) => n.type === "confirm-dialog");
  assert.equal(ask.props.shake, true);
  assert.equal(ask.props.yes, undefined);
  assert.match(ask.props.message, /아직 고르지 않은 놀이가 남아있어요/);
  ask.props.onNo();
  const tree = render();
  assert.ok(selectedTab(tree, "6월~8월"));
  assert.ok(selectedTab(tree, "AI 후보"));
});

test("a 422 goes to the first short period's AI 후보; a 409 hands over to onConflict", async () => {
  confirmStub.next = new StubApiError(422, ["period2", "period3"]);
  const render = renderer(fullPlan());
  button(render(), "확정하기").props.onClick();
  await all(render())
    .find((n) => n.type === "confirm-dialog")
    .props.onYes();
  const tree = render();
  assert.ok(selectedTab(tree, "9월~11월"));
  assert.ok(selectedTab(tree, "AI 후보"));
  assert.equal(
    text(all(tree).find((n) => n.props?.role === "alert")),
    "9월~11월 · 12월~2월 놀이를 5개 골라 주세요.",
  );
  const conflicts = [];
  confirmStub.next = new StubApiError(409, []);
  const again = renderer(fullPlan(), { onConflict: async () => conflicts.push(1) });
  button(again(), "확정하기").props.onClick();
  await all(again())
    .find((n) => n.type === "confirm-dialog")
    .props.onYes();
  assert.deepEqual(conflicts, [1]);
  assert.equal(
    all(again()).find((n) => n.props?.role === "alert"),
    undefined,
  );
});

test("AnnualResult: a draft goes to PlayProjectResult, a confirmed one to ⑥ with two periods per page", async () => {
  const pp = fullPlan();
  const slots = [];
  const effects = [];
  const compact = [];
  let index = 0;
  const { default: Result } = compile("../components/plan-generator/AnnualResult.tsx", {
    "@/components/app/compact-shell": { useCompactShell: (on) => compact.push(on) },
    react: {
      useState(init) {
        const k = index++;
        if (!(k in slots)) slots[k] = typeof init === "function" ? init() : init;
        return [slots[k], (v) => void (slots[k] = typeof v === "function" ? v(slots[k]) : v)];
      },
      useRef: (value) => ({ current: value }),
      useEffect: (effect) => effects.push(effect),
    },
    "@/lib/api/plans": { getAnnualPlan: async () => pp },
    "@/lib/plan-generator/context": {
      loadAnnualContext: () => {
        throw new Error("PLAY_PROJECT should not read stored annual context");
      },
    },
    // 놀이형 문서 제목의 반 이름은 반 설정에서 계획안 class_id 로 찾는다.
    "@/lib/onboarding/settings": {
      loadClassSettings: () => ({ classes: [{ id: "local-1", className: "햇살반" }] }),
    },
    "@/lib/api/onboarding": { classServerId: (id) => (id === "local-1" ? pp.class_id : null) },
    "./AnnualFrame": { AnnualDone: (p) => jsx("done", p) },
    "./AnnualThemeSheet": esModule((p) => jsx("theme-sheet", p)),
    "./PlayProjectSheet": esModule((p) => jsx("play-sheet", p)),
    "./ThemeAnnualResult": esModule((p) => jsx("theme-result", p)),
    "./PlayProjectResult": {
      __esModule: true,
      default: (p) => jsx("play-result", p),
      picksFromPlan: (p) => Object.fromEntries(p.periods.map((x) => [x.period_key, x.selected])),
    },
  });
  const render = () => ((index = 0), resolve(jsx(Result, { id: pp.id })));
  render();
  effects[0]();
  await new Promise((done) => setImmediate(done));
  const shown = all(render()).find((n) => n.type === "play-result");
  assert.equal(compact.at(-1), true, "다듬기는 사이드바를 접는다");
  assert.equal(shown.props.className, "햇살반", "문서 제목에 붙일 반 이름");
  shown.props.onConfirmed({ ...pp, status: "CONFIRMED" });
  const done = all(render()).find((n) => n.type === "done");
  // 원래 문서 쪽 나눔: 봄·여름 / 가을·겨울.
  assert.deepEqual(
    done.props.pages.map((page) => [page.props.periods, page.props.perPage]),
    [
      [[0, 1], 2],
      [[2, 3], 2],
    ],
  );
  assert.equal(done.props.pages[0].props.className, "햇살반");
  assert.equal(compact.at(-1), false, "확정본은 펼친다");
  // 확정 취소는 없다(ADR-064) — 확정본 화면은 되돌리는 손잡이를 받지 않는다.
  assert.equal(done.props.onUnconfirmed, undefined);
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
  // ④ · ⑤ 계절 탭은 한 줄 모양(⑤ 문서 머리줄 것)을 같이 쓴다 — flex-wrap 이라 좁으면 다음 줄로 내려간다.
  const result = readFileSync(
    new URL("../components/plan-generator/PlayProjectResult.tsx", import.meta.url),
    "utf8",
  );
  const bars = [
    ...result.matchAll(
      /role="tablist"\s*\r?\n\s*aria-label="놀이 프로젝트 기간"\s*\r?\n\s*className="([^"]+)"/g,
    ),
  ].map((m) => m[1]);
  assert.equal(bars.length, 1);
  assert.match(bars[0], /\bflex-wrap\b/);
});

test("④ uses the same season tabs as ⑤; ⑤ drags 다른 후보 in and out; 크게 보기 has its own zoom", () => {
  saveStub.calls = [];
  const render = renderer(fullPlan(), {});
  const tabs = (tree) =>
    all(tree).filter(
      (n) => n.props?.role === "tablist" && n.props["aria-label"] === "놀이 프로젝트 기간",
    );
  const short = renderer(plan());
  assert.equal(tabs(short()).length, 1, "④ 에도 같은 탭 줄");
  // 다른 후보 「놀이 7」을 고른 놀이 2번째 줄(놀이 1)에 끌어 놓으면 그 줄과 바뀐다.
  const drag = (rowKey) => ({
    preventDefault() {},
    stopPropagation() {},
    currentTarget: { dataset: {} },
    dataTransfer: { getData: () => rowKey },
  });
  const pickedRow = all(render()).find(
    (n) => n.type === "li" && n.props.onDrop && text(n).startsWith("놀이 1종이 상자"),
  );
  pickedRow.props.onDrop(drag("cand7"));
  assert.deepEqual(saveStub.calls.at(-1).period0, ["cand0", "cand7", "cand2", "cand3", "cand4"]);
  // 고른 놀이를 「다른 후보」로 끌어 오면 뺀다.
  const rest = all(render()).find(
    (n) => n.type === "section" && n.props.onDrop && text(n).startsWith("다른 후보"),
  );
  rest.props.onDrop(drag("cand2"));
  assert.deepEqual(saveStub.calls.at(-1).period0, ["cand0", "cand7", "cand3", "cand4"]);
  const zoomIns = () => all(render()).filter((n) => n.props?.["aria-label"] === "문서 확대");
  assert.equal(zoomIns().length, 1);
  button(render(), "⤢ 크게 보기").props.onClick();
  assert.equal(zoomIns().length, 2, "읽기 전용 창에도 − · +");
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
