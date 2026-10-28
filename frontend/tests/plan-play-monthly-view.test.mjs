// 놀이 중심 월간 읽기 화면 (/plans/monthly/play/[id]) — MSW 고정 데이터로 문서 용지와 안내를 확인한다.
import assert from "node:assert/strict";
import { test } from "node:test";
import { createRequire } from "node:module";
import { readFileSync, existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { registerHooks } from "node:module";
registerHooks({
  resolve(spec, ctx, next) {
    if (spec.startsWith(".") && ctx.parentURL) {
      const u = new URL(spec + ".ts", ctx.parentURL);
      if (existsSync(fileURLToPath(u))) return { url: u.href, shortCircuit: true };
    }
    return next(spec, ctx);
  },
});
const { resetTestData } = await import("../msw/data/store.ts");
const queueModule = await import("../lib/plan-generator/playMonthlyQueue.ts");
const { addPlayMonthly, findPlayMonthly } = await import("../msw/data/play-monthly.ts");

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

class StubApiError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}
const calls = [];
let getResult;
let classesResult = async () => ({ items: [{ id: 7, name: "해님반" }] });
const sheetStub = (props) => jsx("sheet", props);
const editorStub = (props) => jsx("editor", props);
const saved = [];
let saveState = { status: "idle", canUndo: false, canRedo: false };
const saveStub = () => ({
  ...saveState,
  editCell: (...a) => saved.push(["edit", ...a]),
  undo: () => saved.push(["undo"]),
  redo: () => saved.push(["redo"]),
  retry: () => saved.push(["retry"]),
  whenIdle: () => saved.push(["idle"]),
  freeze: () => saved.push(["freeze"]),
  unfreeze: () => saved.push(["unfreeze"]),
});
const barStub = (props) => jsx("confirmbar", props);
const historyStub = (props) => jsx("history", props);
function load() {
  const h = harness();
  const mod = compile("../components/plan-generator/PlayMonthlyView.tsx", {
    react: h.react,
    "@/components/app/AppHeader": esModule(() => null),
    "@/components/workspace/Workspace.module.css": esModule(css),
    "@/lib/api/client": { ApiError: StubApiError },
    "@/lib/api/auth": { getMe: async () => ({ center_id: 1 }) },
    "@/lib/api/classes": { getClasses: () => classesResult() },
    "@/lib/api/playMonthly": { getPlayMonthly: (id) => (calls.push(id), getResult()) },
    "@/lib/hooks/use-play-monthly-save": { usePlayMonthlySave: saveStub },
    "@/lib/plan-generator/playMonthlyQueue": queueModule,
    "./PlayCellEditor": esModule(editorStub),
    "./PlayMonthlySheet": esModule(sheetStub),
    "./PlayMonthlyConfirmBar": esModule(barStub),
    "./PlayMonthlyHistory": esModule(historyStub),
    "./playProjectPagination": {},
    "./PlayMonthlyView.module.css": esModule(css),
  });
  return { ...mod, h };
}
const fixture = (confirmed = false, edit = (p) => p) => {
  resetTestData();
  const plan = addPlayMonthly(7, confirmed);
  return edit(findPlayMonthly(plan.id));
};
async function open(id, result) {
  calls.length = 0;
  getResult = result;
  const { default: View, h } = load();
  return { tree: await h.settle(View, { id }), View, h };
}

// ---- 읽기 화면 (View) ----
test("계획안을 읽어 반 이름과 함께 문서 용지에 넘기고 초안 배지를 보인다", async () => {
  const plan = fixture();
  const { View, h } = await open(plan.id, async () => plan);
  assert.deepEqual(calls, [plan.id]);
  const tree = await h.settle(View, { id: plan.id });
  const sheet = all(tree).find((n) => n.type === "sheet");
  assert.equal(sheet.props.className, "해님반");
  assert.equal(sheet.props.plan.id, plan.id);
  assert.deepEqual(sheet.props.zoom, { mode: "fit", percent: 100 });
  assert.equal(withText(tree, "span", "초안").length, 1);
  assert.equal(withText(tree, "span", "확정됨").length, 0);
});

test("반 이름 조회가 끝나지 않아도 문서는 먼저 보이고, 나중에 오면 채워진다", async () => {
  const plan = fixture();
  let arrive;
  classesResult = () => new Promise((done) => (arrive = done));
  const { View, h } = await open(plan.id, async () => plan);
  const props = { id: plan.id };
  const sheetOf = (tree) => all(tree).find((n) => n.type === "sheet");
  try {
    assert.equal(sheetOf(h.render(View, props)).props.plan.id, plan.id);
    assert.equal(sheetOf(h.render(View, props)).props.className, "");
    arrive({ items: [{ id: 7, name: "해님반" }] });
    await new Promise((done) => setTimeout(done, 0));
    assert.equal(sheetOf(h.render(View, props)).props.className, "해님반");
  } finally {
    classesResult = async () => ({ items: [{ id: 7, name: "해님반" }] });
  }
  // 실패하면 반 이름 칸만 빈다.
  classesResult = async () => Promise.reject(new Error("x"));
  const failed = await open(plan.id, async () => plan);
  assert.equal(sheetOf(await failed.h.settle(failed.View, props)).props.className, "");
  classesResult = async () => ({ items: [{ id: 7, name: "해님반" }] });
});

test("확정본이면 「확정됨」 배지가 있고 확정 · 이력 · 인쇄 · 되돌리기 단추는 없다", async () => {
  const plan = fixture(true);
  const { tree } = await open(plan.id, async () => plan);
  assert.equal(withText(tree, "span", "확정됨").length, 1);
  assert.deepEqual(
    all(tree).filter((n) => n.type === "button"),
    [],
  );
});

test("확정 바와 이력은 초안 · 확정본 모두 계획안 id 로 달고, 저장 훅의 함수를 그대로 넘긴다", async () => {
  const plan = fixture();
  const { tree } = await open(plan.id, async () => plan);
  const bar = all(tree).find((n) => n.type === "confirmbar");
  assert.equal(bar.props.plan.id, plan.id);
  saved.length = 0;
  for (const name of ["whenIdle", "freeze", "unfreeze"]) bar.props[name]();
  assert.deepEqual(saved.splice(0), [["idle"], ["freeze"], ["unfreeze"]]);
  assert.equal(all(tree).find((n) => n.type === "history").props.id, plan.id);
  const done = fixture(true);
  const confirmed = await open(done.id, async () => done);
  assert.equal(all(confirmed.tree).find((n) => n.type === "history").props.id, done.id);
});

test("확정 응답을 받으면 확정본 화면 — 칸 편집 패널 · 저장 표시 · 되돌리기 없이 「확정됨」 배지", async () => {
  const plan = fixture();
  const { View, h, tree } = await open(plan.id, async () => plan);
  assert.equal(withText(tree, "h2", "칸 편집").length, 1);
  assert.equal(typeof all(tree).find((n) => n.type === "sheet").props.onSelect, "function");
  all(tree)
    .find((n) => n.type === "confirmbar")
    .props.onConfirmed({ ...plan, status: "CONFIRMED", revision: plan.revision + 1 });
  const after = h.render(View, { id: plan.id });
  assert.equal(withText(after, "span", "확정됨").length, 1);
  assert.equal(withText(after, "h2", "칸 편집").length, 0);
  assert.equal(all(after).find((n) => n.type === "sheet").props.onSelect, undefined);
  assert.equal(all(after).filter((n) => n.type === "button").length, 0);
  // 확정 바의 마무리(unfreeze)가 뒤따라도 화면은 그대로 확정본이다.
  all(after)
    .find((n) => n.type === "confirmbar")
    .props.unfreeze();
  assert.equal(withText(h.render(View, { id: plan.id }), "span", "확정됨").length, 1);
  saved.length = 0;
});

test("확정 바의 409 는 기존 다시 불러오기 — 최신 계획안으로 바꾸고 안내한다", async () => {
  const plan = fixture();
  const fresh = { ...plan, revision: plan.revision + 5 };
  const { View, h, tree } = await open(plan.id, async () => plan);
  getResult = async () => fresh;
  all(tree)
    .find((n) => n.type === "confirmbar")
    .props.onConflict();
  await new Promise((done) => setTimeout(done, 0));
  const after = h.render(View, { id: plan.id });
  assert.match(text(after), /다른 곳에서 바뀌었어요/);
  assert.equal(calls.length, 2, "다시 불러왔다");
});

test("연간에서 고른 놀이 5개와 놀이 행의 누리과정 연결 ID 칩을 읽기 전용으로 보인다", async () => {
  const plan = fixture();
  const { tree } = await open(plan.id, async () => plan);
  const side = withClass(tree, "side")[0];
  assert.equal(all(side).filter((n) => n.type === "strong").length, 5, "부모 놀이 5개");
  assert.match(text(side), /m09_m11 놀이 9/);
  assert.match(text(side), /지원매체 · 종이 상자/);
  const chips = all(side)
    .filter((n) => n.props?.className === "chip")
    .map(text);
  // 함께 5행은 둘씩(t.1 · t.2), 자유놀이 5행은 하나씩.
  assert.equal(chips.length, 15);
  assert.deepEqual(chips.slice(0, 2), ["t.1", "t.2"]);
  assert.equal(all(side).filter((n) => ["button", "input", "textarea"].includes(n.type)).length, 0);
});

test("강조한 놀이에는 표시가 붙는다", async () => {
  const plan = fixture(false, (p) => ((p.parent.plays[1].emphasized = true), p));
  const { tree } = await open(plan.id, async () => plan);
  assert.equal(withClass(tree, "mark").length, 1);
});

test("notices 를 한 줄로 요약한다 — 안전교육 4주 미배치 · 건강 빈 칸", async () => {
  const plan = fixture(false, (p) => {
    p.health.cell.value = "";
    p.notices.push({ code: "HEALTH_BLANK", week_id: null });
    return p;
  });
  const { tree } = await open(plan.id, async () => plan);
  assert.match(text(tree), /빈 곳 · 안전교육 4주 미배치 · 건강 빈 칸 \(확정을 막지 않아요\)/);
  const { noticeSummary } = load();
  assert.equal(noticeSummary([]), "");
  assert.equal(
    noticeSummary([
      { code: "HABIT_BLANK", week_id: "w1" },
      { code: "NUTRITION_BLANK", week_id: null },
      { code: "SAFETY_BLANK", week_id: "w2" },
    ]),
    "안전교육 1주 빈 칸 · 기본생활습관 1주 빈 칸 · 영양 빈 칸",
  );
});

test("빈 곳이 없으면 요약 줄이 없다", async () => {
  const plan = fixture(false, (p) => {
    p.safety_weeks.forEach((w, i) => (w.candidate_item_id = p.safety_candidates[i].cell.item_id));
    return { ...p, notices: [] };
  });
  const { tree } = await open(plan.id, async () => plan);
  assert.equal(withText(tree, "span", "빈 곳").length, 0);
});

test("404 · 409 · 그 밖 오류는 서버 문구로 안내하고 다시 불러오기를 준다", async () => {
  for (const [status, message] of [
    [404, "월간계획안을 찾을 수 없습니다."],
    [409, "기존 월간계획안은 /api/plans/monthly 경로로 다룹니다."],
    [500, "서버가 응답하지 못했어요."],
  ]) {
    const { tree } = await open(3, async () => Promise.reject(new StubApiError(status, message)));
    assert.equal(text(withText(tree, "p", message)[0]), message);
    assert.equal(withText(tree, "button", "다시 불러오기").length, 1);
  }
  const { tree } = await open(3, async () => Promise.reject(new Error("net")));
  assert.match(text(tree), /계획안을 불러오지 못했어요/);
});

test("잘못된 주소는 요청 없이 안내하고, 읽는 동안에는 상태 문구를 보인다", async () => {
  const bad = await open(Number("abc"), async () => assert.fail("호출하면 안 된다"));
  assert.match(text(bad.tree), /올바른 계획안 주소가 아닙니다/);
  assert.equal(calls.length, 0);
  const { default: View, h } = load();
  getResult = () => new Promise(() => {});
  const tree = h.render(View, { id: 5 });
  assert.match(text(tree), /계획안을 불러오고 있어요/);
});

test("브라우저 저장소를 쓰지 않는다", () => {
  for (const file of ["PlayMonthlyView.tsx", "PlayMonthlySheet.tsx"])
    assert.doesNotMatch(
      readFileSync(new URL("../components/plan-generator/" + file, import.meta.url), "utf8"),
      /localStorage|sessionStorage|indexedDB/,
    );
});

// ---- 문서 용지 (Sheet) ----
function sheetOf(plan, zoom = { mode: "manual", percent: 100 }, onZoomChange = () => {}) {
  const h = harness();
  const { default: Sheet } = compile("../components/plan-generator/PlayMonthlySheet.tsx", {
    react: { ...h.react, useEffect: () => {} },
    "@/lib/api/types": {},
    "./playProjectPagination": {
      stepPlaySheetZoom: (cur, d) =>
        Math.max(50, Math.min(150, Math.round(cur / 10) * 10 + d * 10)),
    },
    "./PlayProjectResult.module.css": esModule(css),
    "./PlayMonthlyView.module.css": esModule(css),
  });
  return h.render(Sheet, { plan, className: "해님반", zoom, onZoomChange });
}
const rowsOf = (tree, tag, th) =>
  all(tree).filter((n) => n.type === "tr" && withText(n, "th", th).length);

test("머리표 — 주제 · 기간 · 만 나이 · 반 이름 · 주제 선정 이유", () => {
  const plan = fixture();
  const t = text(sheetOf(plan));
  assert.match(t, /2026년 11월 놀이계획안/);
  for (const part of ["놀이 주제봄 길을 걸어요", "예상 기간2026년 11월", "만 4·5세해님반"])
    assert.ok(t.includes(part), part);
  assert.ok(t.includes("주제선정이유봄에는 바깥에서"));
});

test("놀이 방향 — 함께 5행 · 가운데 주제 · 자유놀이 5행", () => {
  const tree = sheetOf(fixture());
  const [together, , free] = withClass(tree, "board")[0].props.children;
  assert.equal(all(together).filter((n) => n.type === "li").length, 5);
  assert.equal(all(free).filter((n) => n.type === "li").length, 5);
  assert.match(text(withClass(tree, "center")[0]), /우리의 놀이봄 길을 걸어요/);
  assert.match(text(together), /함께 놀이 1/);
});

test("주별 표 — 열은 응답 weeks 4개와 날짜, 습관 칸, 안전교육은 둔 주만 글이 있다", () => {
  const plan = fixture(false, (p) => {
    p.safety_weeks[1].candidate_item_id = p.safety_candidates[0].cell.item_id;
    return p;
  });
  const tree = sheetOf(plan);
  const head = all(tree).find((n) => n.type === "thead");
  const cols = all(head).filter((n) => n.type === "th");
  assert.equal(cols.length, 5);
  assert.match(text(cols[1]), /11월 1주11\.02 ~ 11\.06/);
  const [habit] = rowsOf(tree, "tr", "기본생활습관");
  assert.deepEqual(
    all(habit)
      .filter((n) => n.type === "td")
      .map(text),
    ["합성 습관 1", "합성 습관 2", "합성 습관 3", "합성 습관 4"],
  );
  const safety = all(rowsOf(tree, "tr", "안전교육")[0]).filter((n) => n.type === "td");
  assert.deepEqual(safety.map(text), ["", "성폭력 예방 약속을 함께 알아보아요", "", ""]);
});

test("소방대피/재난대비는 가로로 합치고, 건강 · 영양 칸이 있다", () => {
  const tree = sheetOf(fixture());
  const drill = all(rowsOf(tree, "tr", "소방대피")[0]).find((n) => n.type === "td");
  assert.equal(drill.props.colSpan, 4);
  assert.equal(text(drill), "");
  const hn = text(rowsOf(tree, "tr", "건강‧영양교육")[0]);
  assert.ok(hn.includes("[건강] 합성 건강 1") && hn.includes("[영양] 합성 영양 1"));
});

test("특성화 · 특별활동 시간표는 글 칸 하나씩이고, 빈 교사 입력 칸은 빈 칸으로 그린다", () => {
  const plan = fixture(false, (p) => {
    p.teacher_inputs.find((i) => i.key === "specialized_timetable").cell.value = "월 인성교육";
    return p;
  });
  const tree = sheetOf(plan);
  const bars = withClass(tree, "bar").map(text);
  assert.ok(bars.includes("[ 특성화 시간표 ]") && bars.includes("[ 특별활동 시간표 ]"));
  const timetables = all(tree)
    .filter((n) => n.type === "div" && !n.props.className && /시간표/.test(text(n)))
    .map((div) => all(div).filter((n) => n.type === "td").length);
  assert.deepEqual(timetables, [1, 1]);
  const cells = withClass(tree, "cell").map(text);
  assert.ok(cells.includes("월 인성교육"));
  for (const label of ["안내사항", "우리반 생일", "가정연계"])
    assert.equal(text(all(rowsOf(tree, "tr", label)[0]).find((n) => n.type === "td")), "");
});

test("칸은 글자일 뿐 버튼 · 입력창이 아니고 data-cell 자리를 남긴다", () => {
  const tree = sheetOf(fixture());
  assert.equal(all(tree).filter((n) => ["input", "textarea"].includes(n.type)).length, 0);
  assert.equal(all(tree).filter((n) => n.type === "button" && !n.props["aria-label"]).length, 0);
  assert.ok(withClass(tree, "cell").every((n) => n.props["data-cell"]?.startsWith("item_")));
  assert.doesNotMatch(text(tree), /RULE_LLM|CURRICULUM/, "출처는 문서에 섞지 않는다");
});

test("확대 · 축소 · 맞춤 단추 — 10% 단위, 50~150%, 맞춤은 mode 만 바꾼다", () => {
  const seen = [];
  const press = (label, zoom) =>
    all(sheetOf(fixture(), zoom, (z) => seen.push(z)))
      .find((n) => n.type === "button" && n.props["aria-label"] === label)
      .props.onClick();
  press("확대", { mode: "manual", percent: 100 });
  press("축소", { mode: "manual", percent: 100 });
  press("확대", { mode: "manual", percent: 150 });
  press("축소", { mode: "manual", percent: 50 });
  press("맞춤", { mode: "manual", percent: 120 });
  assert.deepEqual(seen, [
    { mode: "manual", percent: 110 },
    { mode: "manual", percent: 90 },
    { mode: "manual", percent: 150 },
    { mode: "manual", percent: 50 },
    { mode: "fit", percent: 120 },
  ]);
  const pages = all(sheetOf(fixture(), { mode: "manual", percent: 80 })).find(
    (n) => n.props?.style?.zoom,
  );
  assert.equal(pages.props.style.zoom, 0.8);
});

// ---- 칸 편집 (④) ----
test("문서의 칸을 누르면 그 칸이 강조되고 옆 패널에 빈 값을 허용하는 입력창이 뜬다", async () => {
  const plan = fixture();
  const { View, h } = await open(plan.id, async () => plan);
  const props = { id: plan.id };
  const sheet = () => all(h.render(View, props)).find((n) => n.type === "sheet");
  assert.equal(sheet().props.selected, null);
  assert.match(text(h.render(View, props)), /문서의 칸을 누르면/);
  sheet().props.onSelect(plan.theme.item_id);
  const tree = h.render(View, props);
  assert.equal(all(tree).find((n) => n.type === "sheet").props.selected, plan.theme.item_id);
  const editor = all(tree).filter((n) => n.type === "editor");
  assert.equal(editor.length, 1);
  assert.equal(editor[0].props.label, "놀이 주제");
  assert.equal(editor[0].props.value, plan.theme.value);
  assert.equal(editor[0].props.allowBlank, true);
  editor[0].props.onSave("");
  assert.deepEqual(saved.pop(), ["edit", plan.theme.item_id, ""]);
});

test("놀이 행 이름을 누르면 문서에 없는 「설명」 입력창이 함께 뜬다", async () => {
  const plan = fixture();
  const { View, h } = await open(plan.id, async () => plan);
  const row = plan.together[0];
  all(h.render(View, { id: plan.id }))
    .find((n) => n.type === "sheet")
    .props.onSelect(row.name.item_id);
  const labels = all(h.render(View, { id: plan.id }))
    .filter((n) => n.type === "editor")
    .map((n) => n.props.label);
  assert.deepEqual(labels, ["놀이 행 이름", "놀이 행 설명"]);
});

test("입력 중 글은 문서에 바로 보인다", async () => {
  const plan = fixture();
  const { View, h } = await open(plan.id, async () => plan);
  const props = { id: plan.id };
  all(h.render(View, props))
    .find((n) => n.type === "sheet")
    .props.onSelect(plan.theme.item_id);
  all(h.render(View, props))
    .find((n) => n.type === "editor")
    .props.onDraft("쓰는 중");
  const sheet = all(h.render(View, props)).find((n) => n.type === "sheet");
  assert.equal(sheet.props.plan.theme.value, "쓰는 중");
});

test("저장 표시 · 다시 저장 · 되돌리기 단추는 초안에만 있고 확정본에는 없다", async () => {
  saveState = { status: "failed", canUndo: true, canRedo: false };
  try {
    const plan = fixture();
    const { tree, View, h } = await open(plan.id, async () => plan);
    assert.equal(withText(tree, "span", "저장하지 못했어요").length, 1);
    withText(tree, "button", "다시 저장")[0].props.onClick();
    const undo = withText(tree, "button", "되돌리기")[0];
    assert.equal(undo.props.disabled, false);
    assert.equal(withText(tree, "button", "다시 하기")[0].props.disabled, true);
    undo.props.onClick();
    assert.deepEqual(saved.splice(0), [["retry"], ["undo"]]);
    assert.match(text(h.render(View, { id: plan.id })), /되돌렸어요/);
    const confirmed = fixture(true);
    const done = await open(confirmed.id, async () => confirmed);
    assert.equal(withText(done.tree, "span", "저장하지 못했어요").length, 0);
    assert.equal(all(done.tree).filter((n) => n.type === "button").length, 0);
    assert.equal(all(done.tree).find((n) => n.type === "sheet").props.onSelect, undefined);
    assert.equal(all(done.tree).filter((n) => n.type === "editor").length, 0);
  } finally {
    saveState = { status: "idle", canUndo: false, canRedo: false };
  }
});

test("문서 용지 — onSelect 가 있으면 칸이 누르는 칸이 되고 고른 칸만 강조한다", () => {
  const plan = fixture();
  const picked = [];
  const h = harness();
  const { default: Sheet } = compile("../components/plan-generator/PlayMonthlySheet.tsx", {
    react: { ...h.react, useEffect: () => {} },
    "@/lib/api/types": {},
    "./playProjectPagination": { stepPlaySheetZoom: (c) => c },
    "./PlayProjectResult.module.css": esModule(css),
    "./PlayMonthlyView.module.css": esModule(css),
  });
  const tree = h.render(Sheet, {
    plan,
    className: "",
    zoom: { mode: "manual", percent: 100 },
    onZoomChange: () => {},
    selected: plan.theme.item_id,
    onSelect: (id) => picked.push(id),
  });
  const cells = all(tree).filter((n) => n.props?.["data-cell"]);
  const theme = cells.find((n) => n.props["data-cell"] === plan.theme.item_id);
  assert.equal(theme.props.role, "button");
  assert.match(theme.props.className, /selected/);
  assert.equal(cells.filter((n) => /selected/.test(n.props.className)).length, 1);
  theme.props.onClick();
  theme.props.onKeyDown({ key: "Enter", preventDefault() {} });
  assert.deepEqual(picked, [plan.theme.item_id, plan.theme.item_id]);
});
