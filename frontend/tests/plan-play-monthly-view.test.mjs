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
      if (name.endsWith("/PlanMemo")) return { PlanMemoNote: () => null };
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
  if (typeof node.type === "function") {
    const out = resolve(node.type(node.props));
    return node.key !== undefined && out && typeof out === "object" && !Array.isArray(out)
      ? { ...out, key: node.key }
      : out;
  }
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
let conflict;
let refuse = false; // 큐가 받지 않는 상황(확정 중 · 409 로 멈춤)
let saveArgs = [];
const saveStub = (...args) => {
  saveArgs = args;
  const [plan, onPlan, onConflict] = args;
  conflict = onConflict;
  return {
    ...saveState,
    placeSafety: (...a) => (
      saved.push(["safety", ...a]),
      onPlan(queueModule.withSafety(plan, a[0], a[1]))
    ),
    copyDrill: (...a) => (saved.push(["copy", ...a]), !refuse),
    removeActivity: (id) => (
      saved.push(["remove", id]),
      onPlan(queueModule.withoutActivity(plan, id))
    ),
    editCell: (...a) => (saved.push(["edit", ...a]), !refuse),
    undo: () => (saved.push(["undo"]), !refuse),
    redo: () => (saved.push(["redo"]), !refuse),
    retry: () => saved.push(["retry"]),
    whenIdle: () => saved.push(["idle"]),
    freeze: () => saved.push(["freeze"]),
    unfreeze: () => saved.push(["unfreeze"]),
  };
};
const barStub = (props) => jsx("confirmbar", props);
// 다듬기 틀 대역 — 머리 · 패널 · 문서를 한 나무에 늘어놓아 글자 · 단추를 그대로 찾는다.
const frameModule = {
  __esModule: true,
  default: (p) =>
    jsx("frame", {
      ...p,
      children: [p.lead, p.status, p.actions, p.notice, p.aside, p.docLabel, p.docHint, p.children],
    }),
  AsideStrip: (p) => jsx("strip", p),
  BUTTON: css,
  tabClass: () => "tab",
  UNCONFIRM: "unconfirm",
  POPOVER: "popover",
  BigView: (p) => jsx("bigview", p),
  useSheetZoom: () => ({ percent: 100, tools: null }),
  // 편집 바 되돌리기 대역 — 글자 단추로 그려 이름으로 찾는다.
  UndoRedo: (p) =>
    jsx("span", {
      children: [
        jsx("button", {
          disabled: !!p.disabled || !p.canUndo,
          onClick: p.onUndo,
          children: "되돌리기",
        }),
        p.onRedo &&
          jsx("button", {
            disabled: !!p.disabled || !p.canRedo,
            onClick: p.onRedo,
            children: "다시 하기",
          }),
      ],
    }),
  // 확정 후 틀 대역 — 문서 쪽 · 다음 단계 · 확정 풀기를 한 나무에.
  PlanDone: (p) =>
    jsx("done", {
      ...p,
      children: [
        p.title,
        ...p.pages,
        jsx("a", { href: p.next.href, children: p.next.label }),
        p.unconfirm,
      ],
    }),
};
const shellModule = { useCompactShell: () => {} };
const linkStub = esModule((p) => jsx("a", p));
function load() {
  const h = harness();
  const mod = compile("../components/plan-generator/PlayMonthlyView.tsx", {
    react: h.react,
    "@/components/app/AppHeader": esModule(() => null),
    "@/components/workspace/Workspace.module.css": esModule(css),
    "@/lib/api/client": { ApiError: StubApiError },
    "@/lib/api/auth": { getMe: async () => ({ center_id: 1 }) },
    "@/lib/api/classes": { getClasses: () => classesResult() },
    "@/lib/api/playMonthly": {
      getPlayMonthly: (id) => (calls.push(id), getResult()),
      unconfirmPlayMonthly: (...a) => (calls.push(["unconfirm", ...a]), getResult()),
    },
    "@/lib/hooks/use-play-monthly-save": { usePlayMonthlySave: saveStub },
    "@/lib/plan-generator/playMonthlyQueue": queueModule,
    "./PlayCellEditor": esModule(editorStub),
    "./PlayMonthlySheet": {
      __esModule: true,
      default: sheetStub,
      safetyCellId: (weekId) => "safety:" + weekId,
    },
    "./PlayMonthlySafetyPanel": esModule((props) => jsx("safety", props)),
    "./PlayMonthlyDrillPanel": esModule((props) => jsx("drill", props)),
    "./PlayMonthlyRowRemove": esModule((props) => jsx("remove", props)),
    "./PlayMonthlyConfirmBar": esModule(barStub),
    "./UnconfirmButton": esModule((props) => jsx("unconfirm", props)),
    "./AnnualFrame": frameModule,
    "next/link": linkStub,
    "@/components/app/compact-shell": shellModule,
  });
  return { ...mod, h };
}
const fixture = (confirmed = false, edit = (p) => p) => {
  resetTestData();
  const plan = addPlayMonthly(7, confirmed);
  return edit(findPlayMonthly(plan.id));
};
// 문서 칸 고르기 · 패널 탭 누르기.
const pick = (tree, id) =>
  all(tree)
    .find((n) => n.type === "sheet")
    .props.onSelect(id);
const tabTo = (tree, name) =>
  all(tree)
    .find((n) => n.props?.role === "tab" && text(n) === name)
    .props.onClick();
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
  // 초안 표시는 「작성 중」 없이 저장 상태만(11-03 하민).
  assert.doesNotMatch(text(tree), /작성 중|확정됨/);
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

test("확정본이면 Ⓜ4 — 다음 달 월간으로 가고, 한글 내보내기 · 확정 · 이력 · 되돌리기 단추는 없다", async () => {
  const plan = fixture(true);
  const { tree } = await open(plan.id, async () => plan);
  assert.match(text(tree), new RegExp(`${plan.month}월 월간계획안을 확정했어요`));
  const done = all(tree).find((n) => n.type === "done");
  assert.equal(done.props.download, undefined); // 놀이 월간 hwpx 서버 경로가 아직 없다.
  assert.deepEqual(done.props.next, {
    href: "/plans/monthly",
    label: `${(plan.month % 12) + 1}월 월간 만들기 →`,
    hint: "놀이 중심형은 주간 없이 다음 달로 가요",
  });
  assert.equal(all(tree).find((n) => n.type === "sheet").props.onSelect, undefined);
  assert.deepEqual(
    all(tree).filter((n) => n.type === "button"),
    [],
  );
});

test("확정본의 [확정 취소]는 그 revision 으로 풀고 응답을 넘긴다 · 상위가 바뀌면 한 줄 안내", async () => {
  const done = fixture(true);
  const { View, h, tree } = await open(done.id, async () => ({ ...done, parent_changed: true }));
  assert.equal(withText(tree, "span", "상위 계획안이 바뀌었어요").length, 1);
  const button = all(tree).find((n) => n.type === "unconfirm");
  const draft = { ...done, status: "DRAFT", confirmed_at: null, revision: done.revision + 1 };
  getResult = async () => draft;
  button.props.onDone(await button.props.run());
  assert.deepEqual(calls.at(-1), ["unconfirm", done.id, done.revision]);
  // 이 대역은 key 로 다시 마운트하지 않으므로 초안 화면은 브라우저 확인 몫이다 — 여기서는 다시 그리기가 터지지 않는지만 본다.
  assert.ok(h.render(View, { id: done.id }));
});

test("확정 바는 계획안 id 로 달고 저장 훅의 함수를 그대로 넘긴다 · 변경 이력 버튼은 없다", async () => {
  const plan = fixture();
  const { tree } = await open(plan.id, async () => plan);
  const bar = all(tree).find((n) => n.type === "confirmbar");
  assert.equal(bar.props.plan.id, plan.id);
  saved.length = 0;
  for (const name of ["whenIdle", "freeze", "unfreeze"]) bar.props[name]();
  assert.deepEqual(saved.splice(0), [["idle"], ["freeze"], ["unfreeze"]]);
  // 변경 이력은 서버에만 남고 화면에는 없다(screen-spec S11 · 놀이 월간).
  assert.equal(withText(tree, "button", "변경 이력").length, 0);
});

test("확정 응답을 받으면 확정 후 화면 — 칸 편집 패널 · 저장 표시 · 되돌리기 없이", async () => {
  const plan = fixture();
  const { View, h, tree } = await open(plan.id, async () => plan);
  assert.equal(withText(tree, "button", "칸 편집").length, 1);
  assert.equal(typeof all(tree).find((n) => n.type === "sheet").props.onSelect, "function");
  const bar = all(tree).find((n) => n.type === "confirmbar");
  bar.props.onConfirmed({ ...plan, status: "CONFIRMED", revision: plan.revision + 1 });
  const after = h.render(View, { id: plan.id });
  assert.match(text(after), /월간계획안을 확정했어요/);
  assert.equal(withText(after, "button", "칸 편집").length, 0);
  assert.equal(all(after).find((n) => n.type === "sheet").props.onSelect, undefined);
  assert.equal(all(after).filter((n) => n.type === "button").length, 0);
  // 확정 바의 마무리(unfreeze)가 뒤따라도 화면은 그대로 확정본이다.
  bar.props.unfreeze();
  assert.match(text(h.render(View, { id: plan.id })), /월간계획안을 확정했어요/);
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

test("놀이 행을 고르면 이어진 연간 놀이를 보이고 누리과정 연결 ID 칩은 없다", async () => {
  // 대역 계획안은 행과 연간 놀이를 잇지 않아 첫 행을 둘째 놀이에 잇는다.
  const plan = fixture(
    false,
    (p) => ((p.together[0].parent_item_id = p.parent.plays[1].play_name_item_id), p),
  );
  const { View, h, tree } = await open(plan.id, async () => plan);
  const row = plan.together[0];
  const parent = plan.parent.plays.find((p) => p.play_name_item_id === row.parent_item_id);
  pick(tree, row.name.item_id);
  const after = h.render(View, { id: plan.id });
  assert.ok(text(after).includes(`연간 놀이 ‘${parent.play_name}’에서 이어졌어요`));
  assert.ok(!text(after).includes("누리과정 연결"));
});

const node = (tree, type) => all(tree).filter((n) => n.type === type);

const drillCell = (plan) => plan.teacher_inputs.find((t) => t.key === "fire_disaster_drill").cell;

test("안전교육 칸은 그 주 후보 패널, 소방대피 칸은 훈련 패널, 놀이 행은 행 빼기를 훅에 잇는다", async () => {
  const plan = fixture();
  const { tree, View, h } = await open(plan.id, async () => plan);
  const props = { id: plan.id };
  saved.length = 0;
  assert.equal(node(tree, "safety").length, 0, "칸을 고르기 전에는 패널이 없다");
  const weekId = plan.safety_weeks[0].week_id;
  const cand = plan.safety_candidates[0].cell.item_id;
  pick(tree, "safety:" + weekId);
  const [safety] = node(h.render(View, props), "safety");
  assert.equal(safety.props.weekId, weekId);
  assert.equal(safety.props.disabled, false);
  safety.props.onPlace(weekId, cand);
  safety.props.onPlace(weekId, null);
  pick(h.render(View, props), drillCell(plan).item_id);
  node(h.render(View, props), "drill")[0].props.onCopy(cand);
  assert.deepEqual(saved, [
    ["safety", weekId, cand],
    ["safety", weekId, null],
    ["copy", cand],
  ]);
  // 두면 화면 계획안에 입혀진다.
  pick(h.render(View, props), "safety:" + weekId);
  node(h.render(View, props), "safety")[0].props.onPlace(weekId, cand);
  assert.equal(
    node(h.render(View, props), "safety")[0].props.plan.safety_weeks[0].candidate_item_id,
    cand,
  );
  // 행을 고르면 그 행 빼기 하나, 구역 이름이 붙는다.
  const free = plan.free_play.at(-1);
  pick(h.render(View, props), free.name.item_id);
  assert.equal(node(h.render(View, props), "remove")[0].props.section, "자유놀이");
  const row = plan.together[0];
  pick(h.render(View, props), row.name.item_id);
  const [remove] = node(h.render(View, props), "remove");
  assert.equal(remove.props.section, "함께 하는 활동");
  assert.equal(remove.props.isLastInSection, false);
  remove.props.onRemove(row.activity_id);
  const gone = h.render(View, props);
  assert.ok(
    all(gone)
      .find((n) => n.type === "sheet")
      .props.plan.together.every((r) => r !== row),
  );
  assert.deepEqual(saved.at(-1), ["remove", row.activity_id]);
  saved.length = 0;
});

test("구역에 행이 하나 남으면 마지막 행으로 알린다", async () => {
  const plan = fixture(false, (p) => ((p.together = p.together.slice(0, 1)), p));
  const { tree, View, h } = await open(plan.id, async () => plan);
  pick(tree, plan.together[0].name.item_id);
  assert.equal(node(h.render(View, { id: plan.id }), "remove")[0].props.isLastInSection, true);
  pick(tree, plan.free_play[0].name.item_id);
  assert.equal(node(h.render(View, { id: plan.id }), "remove")[0].props.isLastInSection, false);
});

test("확정본에는 안전 · 훈련 패널과 행 빼기가 없다", async () => {
  const plan = fixture(true);
  const { tree } = await open(plan.id, async () => plan);
  for (const t of ["safety", "drill", "remove"]) assert.equal(node(tree, t).length, 0, t);
});

// 훈련 패널(AI 후보)과 행 빼기(칸 편집)가 지금 잠겼는지.
const lockFlags = (View, h, plan) => {
  const props = { id: plan.id };
  pick(h.render(View, props), drillCell(plan).item_id);
  const drill = node(h.render(View, props), "drill")[0].props.disabled;
  pick(h.render(View, props), plan.together[0].name.item_id);
  return [drill, node(h.render(View, props), "remove")[0].props.disabled];
};

test("저장이 409 로 멈추면 패널 · 행 빼기를 잠근다", async () => {
  const plan = fixture();
  const { View, h } = await open(plan.id, async () => plan);
  assert.deepEqual(lockFlags(View, h, plan), [false, false]);
  conflict();
  assert.deepEqual(lockFlags(View, h, plan), [true, true]);
});

test("확정을 진행하는 동안(freeze 뒤) 패널 · 행 빼기를 잠그고, 끝나면(unfreeze) 푼다", async () => {
  const plan = fixture();
  const { tree, View, h } = await open(plan.id, async () => plan);
  node(tree, "confirmbar")[0].props.freeze();
  assert.deepEqual(lockFlags(View, h, plan), [true, true]);
  node(h.render(View, { id: plan.id }), "confirmbar")[0].props.unfreeze();
  assert.deepEqual(lockFlags(View, h, plan), [false, false]);
  saved.length = 0;
});

test("강조한 놀이에서 이어진 행을 고르면 「이번 달에 더 집중해요」가 붙는다", async () => {
  const plan = fixture(false, (p) => {
    p.parent.plays[1].emphasized = true;
    p.together[2].parent_item_id = p.parent.plays[1].play_name_item_id;
    return p;
  });
  const { tree, View, h } = await open(plan.id, async () => plan);
  const row = [...plan.together, ...plan.free_play].find(
    (r) => r.parent_item_id === plan.parent.plays[1].play_name_item_id,
  );
  pick(tree, row.name.item_id);
  assert.match(text(h.render(View, { id: plan.id })), /이번 달에 더 집중해요/);
});

test("notices 가 있어도 「확인할 것」 배지는 없다", async () => {
  const plan = fixture();
  assert.ok(plan.notices.length > 0);
  const { tree } = await open(plan.id, async () => plan);
  assert.equal(withText(tree, "button", "확인할 것").length, 0);
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
function sheetOf(plan, more = {}) {
  const h = harness();
  const { default: Sheet } = compile("../components/plan-generator/PlayMonthlySheet.tsx", {
    react: { ...h.react, useEffect: () => {} },
  });
  return h.render(Sheet, { plan, className: "해님반", ...more });
}
const rowsOf = (tree, tag, th) =>
  all(tree).filter((n) => n.type === "tr" && withText(n, "th", th).length);

test("칸의 빈 곳(td)을 눌러도 그 칸 하나의 글을 고른다", () => {
  const paper = all(sheetOf(fixture(), { onSelect: () => {} })).find((n) => n.type === "article");
  let clicks = 0;
  const cell = { click: () => clicks++ };
  const td = (cells, area) => ({
    tagName: "TD",
    dataset: area ? { area } : {},
    querySelectorAll: () => cells,
  });
  paper.props.onClick({ target: td([cell]) });
  paper.props.onClick({ target: td([cell, cell]) }); // 칸이 여럿이면 모른다
  paper.props.onClick({ target: td([cell], "x") }); // 주간 area 가 받는다
  paper.props.onClick({ target: { tagName: "SPAN", dataset: {} } });
  assert.equal(clicks, 1);
});

test("머리표 — 주제 · 기간 · 만 나이 · 반 이름 · 주제 선정 이유", () => {
  const plan = fixture();
  const t = text(sheetOf(plan));
  assert.match(t, /11월 놀이계획안/);
  assert.match(t, /예상 기간\d{4}\.\d{2}\.\d{2} ~ \d{4}\.\d{2}\.\d{2}/);
  for (const part of ["놀이 주제봄 길을 걸어요", "만 4·5세 해님반", "주제선정이유봄에는 바깥에서"])
    assert.ok(t.includes(part), part);
});

test("놀이 방향 — 함께 5행 · 가운데 주제 · 자유놀이 5행", () => {
  const tree = sheetOf(fixture());
  const [together, free] = all(tree).filter((n) => n.type === "ol");
  assert.equal(all(together).filter((n) => n.type === "li").length, 5);
  assert.equal(all(free).filter((n) => n.type === "li").length, 5);
  assert.match(text(together), /①함께 놀이 1/);
  assert.match(text(free), /^-/);
  assert.equal(text(all(tree).find((n) => n.props?.rowSpan === 2)), "봄 길을 걸어요");
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
  const hn = text(rowsOf(tree, "tr", "건강·영양교육")[0]);
  assert.ok(hn.includes("[건강]합성 건강 1") && hn.includes("[영양]합성 영양 1"));
});

test("특성화 · 특별활동 시간표는 글 칸 하나씩이고, 빈 교사 입력 칸은 빈 칸으로 그린다", () => {
  const plan = fixture(false, (p) => {
    p.teacher_inputs.find((i) => i.key === "specialized_timetable").cell.value = "월 인성교육";
    return p;
  });
  const tree = sheetOf(plan);
  const t = text(tree);
  assert.ok(t.includes("[ 특성화 시간표 ]") && t.includes("[ 특별활동 시간표 ]"));
  const cells = all(tree)
    .filter((n) => n.props?.["data-cell"])
    .map(text);
  assert.ok(cells.includes("월 인성교육"));
  assert.equal(all(tree).filter((n) => n.type === "td" && /시간표/.test(text(n))).length, 0);
  for (const label of ["우리반 생일", "가정연계"])
    assert.equal(text(all(rowsOf(tree, "tr", label)[0]).find((n) => n.type === "td")), "");
  // 안내사항은 내려받기에 나오지 않아(2026-10-28) 문서 화면에도 없다.
  assert.equal(rowsOf(tree, "tr", "안내사항").length, 0);
});

test("칸은 글자일 뿐 버튼 · 입력창이 아니고 data-cell 자리를 남긴다", () => {
  const tree = sheetOf(fixture());
  assert.equal(all(tree).filter((n) => ["input", "textarea"].includes(n.type)).length, 0);
  assert.equal(all(tree).filter((n) => n.type === "button" && !n.props["aria-label"]).length, 0);
  assert.ok(
    all(tree)
      .filter((n) => n.props?.["data-cell"])
      .every((n) => /^(item_|safety:)/.test(n.props["data-cell"])),
  );
  assert.doesNotMatch(text(tree), /RULE_LLM|CURRICULUM/, "출처는 문서에 섞지 않는다");
});

test("확대 도구는 없고 용지는 줄이기만 한다(처음 배율 1)", () => {
  const tree = sheetOf(fixture());
  assert.equal(all(tree).filter((n) => n.type === "button").length, 0);
  assert.equal(all(tree).find((n) => n.props?.style?.zoom).props.style.zoom, 1);
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
  // 큰 제목은 행 이름 대신 문서 순서 「첫 번째 칸」.
  const shown = text(h.render(View, { id: plan.id }));
  assert.match(shown, /첫 번째 칸/);
  assert.doesNotMatch(shown, /①/);
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
    assert.match(text(tree), /저장하지 못했어요/);
    withText(tree, "button", "다시 저장")[0].props.onClick();
    const undo = withText(tree, "button", "되돌리기")[0];
    assert.equal(undo.props.disabled, false);
    assert.equal(withText(tree, "button", "다시 하기")[0].props.disabled, true);
    undo.props.onClick();
    assert.deepEqual(saved.splice(0), [["retry"], ["undo"]]);
    assert.doesNotMatch(text(h.render(View, { id: plan.id })), /되돌렸어요/);
    const confirmed = fixture(true);
    const done = await open(confirmed.id, async () => confirmed);
    assert.doesNotMatch(text(done.tree), /저장하지 못했어요/);
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
  });
  const tree = h.render(Sheet, {
    plan,
    className: "",
    selected: plan.theme.item_id,
    onSelect: (id) => picked.push(id),
  });
  const cells = all(tree).filter((n) => n.props?.["data-cell"]);
  const theme = cells.find((n) => n.props["data-cell"] === plan.theme.item_id);
  assert.equal(theme.props.role, "button");
  assert.equal(theme.props["aria-pressed"], true);
  assert.equal(cells.filter((n) => n.props["aria-pressed"] === true).length, 1);
  theme.props.onClick();
  theme.props.onKeyDown({ key: "Enter", preventDefault() {} });
  assert.deepEqual(picked, [plan.theme.item_id, plan.theme.item_id]);
});

test("거절된 칸만 입력창을 다시 열고, 옛 입력창이 사라지며 보내는 글은 버린다 · 입력 중이면 떠날 때 경고 조건", async () => {
  const plan = fixture();
  const { View, h } = await open(plan.id, async () => plan);
  const props = { id: plan.id };
  all(h.render(View, props))
    .find((n) => n.type === "sheet")
    .props.onSelect(plan.theme.item_id);
  const first = all(h.render(View, props)).find((n) => n.type === "editor");
  assert.equal(saveArgs[4], false);
  first.props.onDraft("쓰는 중");
  h.render(View, props);
  assert.equal(saveArgs[4], true);
  saveArgs[3](plan.theme.item_id); // 422 로 그 칸이 되돌아갔다
  const second = all(h.render(View, props)).find((n) => n.type === "editor");
  assert.notEqual(second.key, first.key);
  assert.equal(saveArgs[4], false);
  first.props.onSave("옛 입력창의 글"); // 옛 입력창 cleanup
  assert.deepEqual(saved, []);
  second.props.onSave("새 글");
  assert.deepEqual(saved.pop(), ["edit", plan.theme.item_id, "새 글"]);
  // 다른 칸의 입력창은 다시 열리지 않는다.
  saveArgs[3]("다른 칸");
  assert.equal(all(h.render(View, props)).find((n) => n.type === "editor").key, second.key);
});

async function openDrillEditor() {
  const plan = fixture();
  const { View, h } = await open(plan.id, async () => plan);
  const props = { id: plan.id };
  all(h.render(View, props))
    .find((n) => n.type === "sheet")
    .props.onSelect(drillCell(plan).item_id);
  tabTo(h.render(View, props), "칸 편집");
  const editor = () => all(h.render(View, props)).find((n) => n.type === "editor");
  const drill = () => {
    tabTo(h.render(View, props), "AI 후보");
    const panel = node(h.render(View, props), "drill")[0];
    tabTo(h.render(View, props), "칸 편집");
    return panel;
  };
  return { plan, View, h, props, editor, drill };
}

test("열린 소방대피 입력창에서 훈련을 복사하면 입력창이 다시 열리고 옛 글은 버려진다", async () => {
  const { plan, h, View, props, editor, drill } = await openDrillEditor();
  const first = editor();
  first.props.onDraft("쓰는 중");
  h.render(View, props);
  const candidate = plan.drill_candidates[0].cell.item_id;
  saved.length = 0;
  drill().props.onCopy(candidate);
  const second = editor();
  assert.notEqual(second.key, first.key); // 입력창이 새로 열린다(복사된 글을 보인다)
  assert.equal(
    all(h.render(View, props)).find((n) => n.type === "sheet").props.plan.teacher_inputs[0].cell
      .value,
    drillCell(plan).value,
    "입력 중이던 글은 문서에서 치워졌다",
  );
  first.props.onSave("옛 글"); // 옛 입력창이 사라지며 보내는 글
  assert.deepEqual(saved, [["copy", candidate]]);
});

test("큐가 복사를 받지 않으면 열린 입력창을 그대로 둔다", async () => {
  const { plan, editor, drill } = await openDrillEditor();
  const first = editor();
  refuse = true;
  try {
    drill().props.onCopy(plan.drill_candidates[0].cell.item_id);
  } finally {
    refuse = false;
  }
  assert.equal(editor().key, first.key);
});

test("확정하는 동안 되돌리기 · 다시 하기는 잠기고 입력창은 읽기 전용이다", async () => {
  saveState = { status: "idle", canUndo: true, canRedo: true };
  try {
    const { View, h, props, editor } = await openDrillEditor();
    const buttons = () =>
      ["되돌리기", "다시 하기"].map((l) => withText(h.render(View, props), "button", l)[0]);
    assert.ok(buttons().every((b) => b.props.disabled === false));
    assert.equal(editor().props.readOnly, false);
    node(h.render(View, props), "confirmbar")[0].props.freeze();
    assert.ok(buttons().every((b) => b.props.disabled === true));
    assert.equal(editor().props.readOnly, true);
    node(h.render(View, props), "confirmbar")[0].props.unfreeze();
    assert.ok(buttons().every((b) => b.props.disabled === false));
    assert.equal(editor().props.readOnly, false);
    saved.length = 0;
  } finally {
    saveState = { status: "idle", canUndo: false, canRedo: false };
  }
});

test("큐가 되돌리기를 거절하면 입력 중 글이 남고, 되돌려도 「되돌렸어요」 문구는 없다", async () => {
  saveState = { status: "idle", canUndo: true, canRedo: true };
  try {
    const { plan, View, h, props, editor } = await openDrillEditor();
    editor().props.onDraft("쓰는 중");
    refuse = true;
    withText(h.render(View, props), "button", "되돌리기")[0].props.onClick();
    withText(h.render(View, props), "button", "다시 하기")[0].props.onClick();
    refuse = false;
    const tree = h.render(View, props);
    assert.doesNotMatch(text(tree), /되돌렸어요|다시 했어요/);
    assert.equal(
      all(tree).find((n) => n.type === "sheet").props.plan.teacher_inputs[0].cell.value,
      "쓰는 중",
    );
    assert.notEqual(drillCell(plan).value, "쓰는 중");
    withText(tree, "button", "되돌리기")[0].props.onClick();
    assert.doesNotMatch(text(h.render(View, props)), /되돌렸어요/);
    saved.length = 0;
  } finally {
    refuse = false;
    saveState = { status: "idle", canUndo: false, canRedo: false };
  }
});

test("큐가 칸 저장을 받지 않으면 입력 중 글을 지우지 않는다", async () => {
  const { plan, h, View, props, editor } = await openDrillEditor();
  editor().props.onDraft("확정 중에 쓴 글");
  refuse = true;
  try {
    editor().props.onSave("확정 중에 쓴 글");
  } finally {
    refuse = false;
  }
  const sheet = all(h.render(View, props)).find((n) => n.type === "sheet");
  assert.equal(sheet.props.plan.teacher_inputs[0].cell.value, "확정 중에 쓴 글");
  assert.notEqual(drillCell(plan).value, "확정 중에 쓴 글");
  saved.length = 0;
});

test("거절 안내 — 칸이면 「칸」, 안전 배치 · 삭제 · 복사면 「변경」, 확정 바의 409 도 저장을 멈춘다", async () => {
  const plan = fixture();
  const { View, h } = await open(plan.id, async () => plan);
  const props = { id: plan.id };
  h.render(View, props);
  saveArgs[3](null, "cell");
  assert.match(text(h.render(View, props)), /저장하지 못한 칸은 원래대로/);
  saveArgs[3](null, "safety");
  assert.match(text(h.render(View, props)), /저장하지 못한 변경은 원래대로/);
  assert.doesNotMatch(text(h.render(View, props)), /저장하지 못한 칸은/);
  node(h.render(View, props), "confirmbar")[0].props.onConflict();
  pick(h.render(View, props), drillCell(plan).item_id);
  assert.ok(node(h.render(View, props), "drill")[0].props.disabled);
});

// ---- 월간 v1 편집 화면 (MonthlyPlanEditor) — 같은 배치, 저장 줄 경계 ----
function openV1Editor(findings = [], setup = (p) => p) {
  globalThis.document = { activeElement: null };
  const listeners = [];
  globalThis.window = {
    addEventListener: (type) => listeners.push(type),
    removeEventListener: (type) => listeners.splice(listeners.indexOf(type), 1),
  };
  const h = harness();
  let n = 0;
  const cell = { item_id: "c1", week_id: "W1", value: "A", state: "FILLED", evidence: [] };
  let server = setup({
    id: 1,
    revision: 1,
    status: "DRAFT",
    month: 9,
    target_month: "2026-09",
    parent: { theme: "" },
    generation_mode: "LLM_PLANNER",
    verification: { findings },
    weeks: [{ week_id: "W1", active: true, label: "1주" }],
    sections: [
      {
        section_key: "outdoor_play",
        label: "",
        role: "CONTENT",
        visible: true,
        order: 1,
        repeat_by: "WEEK",
        cells: [cell],
      },
    ],
    safety_candidates: [],
    safety_weeks: [],
    drill_candidates: [],
    notices: [],
  });
  const sent = [];
  const edits = [];
  const placed = [];
  const copied = [];
  const waits = [];
  const displayOf = (candidates, itemId) => {
    const value = candidates.find((c) => c.cell.item_id === itemId)?.cell.value ?? "";
    return value ? `[교통안전] - ${value}` : "";
  };
  // 서버처럼 같은 값은 거절하고(monthly_cell_value_unchanged), 응답은 시험이 풀 때까지 붙잡는다.
  const edit = async (id, itemId, value, rev) => {
    sent.push(value);
    edits.push([id, itemId, value, rev]);
    await new Promise((ok, fail) => waits.push({ ok, fail }));
    const prev = [
      ...server.sections.flatMap((s) => s.cells),
      ...server.safety_candidates.map((c) => c.cell),
    ].find((c) => c.item_id === itemId)?.value;
    if (value === prev) throw new StubApiError(422, "unchanged");
    const safety_candidates = server.safety_candidates.map((c) =>
      c.cell.item_id === itemId ? { ...c, cell: { ...c.cell, value } } : c,
    );
    server = {
      ...server,
      revision: server.revision + 1,
      sections: server.sections.map((s) => ({
        ...s,
        cells: s.cells.map((c) => (c.item_id === itemId ? { ...c, value } : c)),
      })),
      safety_candidates,
      safety_weeks: server.safety_weeks.map((w) =>
        w.candidate_item_id === itemId
          ? { ...w, display_value: displayOf(safety_candidates, itemId) }
          : w,
      ),
    };
    return server;
  };
  let place = async (id, weekId, candidateItemId, rev) => {
    placed.push([id, weekId, candidateItemId, rev]);
    server = {
      ...server,
      revision: server.revision + 1,
      safety_weeks: server.safety_weeks.map((w) =>
        w.week_id === weekId
          ? {
              ...w,
              candidate_item_id: candidateItemId,
              display_value: displayOf(server.safety_candidates, candidateItemId),
            }
          : w,
      ),
    };
    return server;
  };
  let audit = async () => ({ items: [] });
  const Confirm = compile("../components/plan-generator/PlayMonthlyConfirm.tsx", {
    react: h.react,
    "./PlayMonthlyStructure.module.css": esModule(css),
  }).default;
  const DrillPanel = compile("../components/plan-generator/PlayMonthlyDrillPanel.tsx", {
    react: h.react,
    "./PlayMonthlyStructure.module.css": esModule(css),
    "./PlayMonthlyConfirm": esModule(Confirm),
    "./PlayMonthlySafetyPanel": { CARD: "card", PUT: "put" },
  }).default;
  const { default: View } = compile("../components/workspace/MonthlyPlanEditor.tsx", {
    // 의존성 목록이 없는 effect 는 실제 React 처럼 매번 돈다.
    react: { ...h.react, useEffect: (fn, deps) => h.react.useEffect(fn, deps ?? [n++]) },
    "@/lib/api/client": { ApiError: StubApiError },
    "./Workspace.module.css": esModule(css),
    "@/lib/api/monthly": {
      editMonthlyCell: edit,
      placeMonthlySafety: (...a) => place(...a),
      copyMonthlyDrill: async (id, itemId, revision) => {
        copied.push([id, itemId, revision]);
        const value = server.drill_candidates.find((c) => c.cell.item_id === itemId).cell.value;
        server = {
          ...server,
          revision: server.revision + 1,
          sections: server.sections.map((s) =>
            s.section_key === "drill" ? { ...s, cells: s.cells.map((c) => ({ ...c, value })) } : s,
          ),
        };
        return server;
      },
      confirmMonthlyPlan: async () => server,
      regenerateMonthlyCell: async () => server,
      getMonthlyPlanAudit: (...a) => audit(...a),
      downloadMonthlyHwpx: () => {},
    },
    "@/lib/api/plans": { isSaveConflict: (e) => e.status === 409 },
    "@/lib/monthly/section-labels": { sectionName: (key) => key },
    "@/lib/hooks/use-hwpx-download": { useHwpxDownload: () => ({ exporting: false }) },
    "@/components/plan-generator/PlayCellEditor": esModule((p) => {
      const clear = () => {
        globalThis.document.activeElement = null;
      };
      return jsx("editor", {
        ...p,
        onDraft: (v) => {
          p.onDraft(v);
          globalThis.document.activeElement = {
            blur: () => {
              clear();
              p.onSave(v.trim());
            },
          };
        },
        onSave: (v) => {
          clear();
          p.onSave(v);
        },
        onRevert: () => {
          clear();
          p.onRevert();
        },
      });
    }),
    "@/components/plan-generator/PlayMonthlySafetyPanel": esModule((props) => jsx("safety", props)),
    "@/components/plan-generator/PlayMonthlyDrillPanel": esModule(DrillPanel),
    "@/components/plan-generator/UnconfirmButton": esModule((props) => jsx("unconfirm", props)),
    "@/components/plan-generator/PlayMonthlySheet": {
      Cell: (props) => jsx("cell", props),
      Paper: (props) => jsx("paper", props),
      Band: (props) => jsx("div", props),
      WeekHead: ({ week }) => jsx("th", { children: week.label }),
      LINE: "line",
      HEAD: "head",
      hu: (n) => n,
      period: () => "",
      safetyCellId: (weekId) => "safety:" + weekId,
    },
    "@/components/plan-generator/PlayMonthlyConfirm": esModule((p) => jsx("ask", p)),
    "@/components/plan-generator/AnnualFrame": frameModule,
    "@/components/app/compact-shell": shellModule,
    "./WorkspaceUI": { ws: css },
  });
  const props = {
    plan: server,
    className: "해님반",
    onBack: () => {},
    onPlan: (next) => (props.plan = next),
    onConflict: () => {},
    onDelete: () => {},
    flushRef: { current: null },
  };
  const render = () => h.render(View, props);
  all(render())
    .find((x) => x.type === "cell")
    .props.onSelect("c1");
  return {
    sent,
    edits,
    placed,
    copied,
    setPlace: (fn) => (place = fn),
    setAudit: (fn) => (audit = fn),
    waits,
    listeners,
    props,
    render,
    editor: () => all(render()).find((x) => x.type === "editor").props,
    // 문서 칸을 고른다(안전교육 칸은 「AI 후보」 탭이 먼저 열린다).
    pick: (id) =>
      all(render())
        .find((x) => x.type === "cell" && x.props.id === id)
        .props.onSelect(id),
    tab: (name) => tabTo(render(), name),
    // 그 주 안전교육 칸을 골라 후보 패널을 연다.
    panel: (weekId) => {
      all(render())
        .find((x) => x.type === "cell" && x.props.id === "safety:" + weekId)
        .props.onSelect("safety:" + weekId);
      return node(render(), "safety")[0].props;
    },
    stored: () => server.sections[0].cells[0].value,
    tick: () => new Promise((done) => setTimeout(done, 0)),
  };
}

test("v1 — 안전교육 검증 안내는 영어 서버 문구 대신 한국어로 보인다", () => {
  const finding = (code) => ({ code, section_key: "safety_education", message: "English " + code });
  const tree = openV1Editor([
    finding("SAFETY_ANNUAL_HOURS_NOT_VERIFIED"),
    finding("SAFETY_OFFICIAL_GROUNDING_MISSING"),
    finding("SAFETY_SUPPLEMENTAL_GROUNDING_INVALID"),
  ]).render();
  assert.doesNotMatch(text(tree), /English/);
  assert.match(text(tree), /연간 법정 시간은 자동으로 확인하지 못했어요/);
  assert.match(text(tree), /공식 교육 내용 근거/);
  assert.match(text(tree), /생활안전 칸의 참고 근거/);
});

test("v1 — 저장 중에 원래 값으로 되돌리면 그 값도 보내고, 같은 글을 두 번 넘기면 한 번만 보낸다", async () => {
  const back = openV1Editor();
  back.editor().onDraft("B");
  back.editor().onSave("B");
  await back.tick();
  back.editor().onDraft("A");
  back.editor().onSave("A"); // B 응답 전
  back.waits.shift().ok();
  await back.tick();
  back.waits.shift().ok();
  await back.tick();
  assert.deepEqual(back.sent, ["B", "A"]);
  assert.equal(back.stored(), "A");
  assert.match(text(back.render()), /저장됨/);

  const twice = openV1Editor();
  twice.editor().onSave("B"); // 1초 뒤 저장
  await twice.tick();
  twice.editor().onSave("B"); // 같은 글로 떠남
  twice.waits.shift().ok();
  await twice.tick();
  await twice.tick();
  assert.deepEqual(twice.sent, ["B"]);
  assert.doesNotMatch(text(twice.render()), /저장하지 못했어요/);
});

test("v1 — 반 · 월 이동은 기다리는 동안 입력을 잠그고, 늦게 붙은 저장까지 기다려 실패하면 옮기지 않는다", async () => {
  const view = openV1Editor();
  view.editor().onDraft("B");
  view.editor().onSave("B");
  await view.tick();
  const moving = view.props.flushRef.current(); // B 응답 전에 다른 월을 고름
  assert.equal(view.editor().readOnly, true); // 기다리는 동안 새 글을 못 쓴다
  assert.equal(await view.props.flushRef.current(), false); // 겹친 이동은 받지 않는다
  view.editor().onDraft("C");
  view.editor().onSave("C"); // 잠그기 전에 이미 출발한 저장
  view.waits.shift().ok(); // B 성공
  await view.tick();
  view.waits.shift().fail(new Error("offline")); // C 실패
  assert.equal(await moving, false);
  const tree = view.render();
  assert.match(text(tree), /저장하지 못한 칸이 있어요/);
  assert.equal(view.editor().readOnly, false);
  assert.equal(view.editor().value, "C"); // 되돌리지 않았다
  assert.equal(all(tree).find((x) => x.type === "cell").props.value, "C");
  assert.ok(view.listeners.includes("beforeunload"));
  withText(tree, "button", "다시 저장")[0].props.onClick();
  await view.tick();
  view.waits.shift().ok();
  assert.equal(await view.props.flushRef.current(), true);
  assert.equal(view.stored(), "C");
});

const withV1Candidates = (plan) => ({
  ...plan,
  weeks: [
    { week_id: "W1", active: true, label: "1주" },
    { week_id: "W2", active: true, label: "2주" },
  ],
  sections: [
    {
      ...plan.sections[0],
      cells: [
        plan.sections[0].cells[0],
        { item_id: "c2", week_id: "W2", value: "B", state: "FILLED", evidence: [] },
      ],
    },
    {
      section_key: "safety_education",
      label: "안전교육",
      role: "CONTENT",
      visible: true,
      order: 2,
      repeat_by: "WEEK",
      cells: [
        { item_id: "s_w1", week_id: "W1", value: "", state: "EMPTY_UNRESOLVED", evidence: [] },
        { item_id: "s_w2", week_id: "W2", value: "", state: "EMPTY_UNRESOLVED", evidence: [] },
      ],
    },
  ],
  safety_candidates: [
    {
      kind: "STATUTORY",
      category_id: "traffic",
      topic_group: null,
      cell: {
        item_id: "cand_1",
        week_id: null,
        value: "횡단보도 건너기",
        state: "FILLED",
        evidence: [],
      },
    },
  ],
  safety_weeks: [
    {
      week_id: "W1",
      candidate_item_id: "cand_1",
      display_value: "[교통안전] - 횡단보도 건너기",
    },
    { week_id: "W2", candidate_item_id: null, display_value: "" },
  ],
  notices: [{ code: "SAFETY_UNPLACED", week_id: "W2" }],
});

const withV1Drill = (plan, value = "") => ({
  ...plan,
  sections: [
    ...plan.sections,
    {
      section_key: "drill",
      label: "소방대피/재난대비",
      role: "CONTENT",
      visible: true,
      order: 2,
      repeat_by: "NONE",
      cells: [{ item_id: "drill_cell", week_id: null, value, state: "FILLED", evidence: [] }],
    },
  ],
  drill_candidates: [
    { topic_id: "fire", label: "화재", cell: { item_id: "drill_candidate", value: "대피해요" } },
  ],
});

// 훈련 후보의 「넣기」 단추들. 훈련 칸을 고르면 「AI 후보」 탭에 뜬다(놀이 월간과 같다).
const drillButtons = (tree) =>
  all(tree).filter((n) => n.type === "button" && n.props["data-act"] === "copy");

test("v1 — 훈련 칸을 고르면 「AI 후보」에 훈련 후보가 보이고, 후보가 없거나 확정본이면 없다", () => {
  const view = openV1Editor([], withV1Drill);
  assert.equal(drillButtons(view.render()).length, 0, "훈련 칸을 고르기 전에는 패널이 없다");
  view.pick("drill_cell");
  const tree = view.render();
  assert.equal(withText(tree, "h2", "넣을 문구 고르기").length, 1);
  assert.equal(drillButtons(tree)[0].props["aria-label"], "소방대피/재난대비 칸에 넣기: 화재");
  view.props.plan = { ...view.props.plan, drill_candidates: [] };
  view.pick("drill_cell");
  view.tab("AI 후보");
  assert.equal(drillButtons(view.render()).length, 0);
  view.props.plan = { ...withV1Drill(view.props.plan), status: "CONFIRMED" };
  assert.equal(drillButtons(view.render()).length, 0);
});

test("v1 — 훈련 칸이 비었으면 확인 없이 후보를 복사하고 응답으로 계획안을 바꾼다", async () => {
  const view = openV1Editor([], withV1Drill);
  view.pick("drill_cell");
  drillButtons(view.render())[0].props.onClick();
  await view.tick();
  assert.deepEqual(view.copied, [[1, "drill_candidate", 1]]);
  assert.equal(
    view.props.plan.sections.find((s) => s.section_key === "drill").cells[0].value,
    "대피해요",
  );
  assert.match(text(view.render()), /훈련 후보를 넣었어요/);
});

test("v1 — 훈련 칸에 글이 있어도 묻지 않고 바로 복사한다", async () => {
  const view = openV1Editor([], (plan) => withV1Drill(plan, "기존 글"));
  view.pick("drill_cell");
  drillButtons(view.render())[0].props.onClick();
  await view.tick();
  assert.deepEqual(view.copied, [[1, "drill_candidate", 1]]);
});

test("v1 — 저장 응답 전 훈련 칸에 쓴 글이 있으면 저장이 끝난 revision 으로 복사한다", async () => {
  const view = openV1Editor([], withV1Drill);
  view.pick("drill_cell");
  view.tab("칸 편집");
  view.editor().onDraft("저장 전 글");
  view.editor().onSave("저장 전 글");
  await view.tick();
  assert.deepEqual(view.edits, [[1, "drill_cell", "저장 전 글", 1]]);
  view.tab("AI 후보");
  drillButtons(view.render())[0].props.onClick();
  await view.tick();
  assert.deepEqual(view.copied, []);
  view.waits.shift().ok();
  await view.tick();
  assert.deepEqual(view.copied, [[1, "drill_candidate", 2]]);
  assert.equal(
    view.props.plan.sections.find((s) => s.section_key === "drill").cells[0].value,
    "대피해요",
  );
});

test("v1 — 공백을 다듬어 저장한 뒤 훈련 후보를 넣으면 옛 입력이 남거나 다시 저장되지 않는다", async () => {
  const view = openV1Editor([], withV1Drill);
  view.pick("drill_cell");
  view.tab("칸 편집");
  const first = node(view.render(), "editor")[0];
  view.editor().onDraft(" 저장 전 글 ");
  view.tab("AI 후보");
  drillButtons(view.render())[0].props.onClick();
  await view.tick();
  assert.deepEqual(view.edits, [[1, "drill_cell", "저장 전 글", 1]]);
  assert.deepEqual(view.copied, []);
  view.waits.shift().ok();
  await view.tick();
  assert.deepEqual(view.copied, [[1, "drill_candidate", 2]]);

  view.tab("칸 편집");
  const tree = view.render();
  assert.equal(node(tree, "cell").find((c) => c.props.id === "drill_cell").props.value, "대피해요");
  assert.notEqual(node(tree, "editor")[0].key, first.key);
  assert.equal(view.editor().value, "대피해요");
  view.editor().onSave(view.editor().value); // 수정 없이 입력창을 떠난다(blur).
  await view.tick();
  assert.deepEqual(view.edits, [[1, "drill_cell", "저장 전 글", 1]]);
});

test("v1 — 후보가 없는 계획은 패널과 안내가 없고 안전교육 줄이 주별 칸을 보이며 고를 수 있다", () => {
  const view = openV1Editor([], (plan) => ({
    ...plan,
    sections: [
      ...plan.sections,
      {
        section_key: "safety_education",
        label: "안전교육",
        role: "CONTENT",
        visible: true,
        order: 2,
        repeat_by: "WEEK",
        cells: [
          {
            item_id: "s_w1",
            week_id: "W1",
            value: "교통안전 약속",
            state: "FILLED",
            evidence: [],
          },
        ],
      },
    ],
    notices: [{ code: "SAFETY_UNPLACED", week_id: "W1" }],
  }));
  const tree = view.render();
  assert.equal(node(tree, "safety").length, 0);
  assert.doesNotMatch(text(tree), /안전교육 1주 미배치/);
  const [safetyRow] = rowsOf(tree, "tr", "safety_education");
  const [safetyCell] = node(safetyRow, "cell");
  assert.equal(safetyCell.props.id, "s_w1");
  assert.equal(safetyCell.props.value, "교통안전 약속");
  safetyCell.props.onSelect("s_w1");
  assert.equal(view.editor().label, "1주 · safety_education");
  assert.equal(view.editor().value, "교통안전 약속");
});

test("v1 — 후보가 있는 계획은 패널 · 안내를 보이고(확정본은 숨김) 안전 줄에 둔 후보의 display_value 만 그리며 빈 주별 안전 칸 때문에 「빈 칸 있음」이 뜨지 않는다", () => {
  const view = openV1Editor([], withV1Candidates);
  const tree = view.render();
  assert.equal(node(tree, "safety").length, 0, "안전교육 칸을 고르기 전에는 패널이 없다");
  assert.equal(withText(tree, "button", "확인할 것").length, 0);
  assert.equal(withText(tree, "span", "빈 칸 있음").length, 0);
  const [safetyRow] = rowsOf(tree, "tr", "safety_education");
  assert.deepEqual(
    node(safetyRow, "cell").map((c) => [c.props.id, c.props.value]),
    [
      ["safety:W1", "[교통안전] - 횡단보도 건너기"],
      ["safety:W2", ""],
    ],
  );
  const ids = node(tree, "cell").map((c) => c.props.id);
  assert.ok(!ids.includes("s_w1") && !ids.includes("s_w2"));
  node(safetyRow, "cell")[1].props.onSelect("safety:W2"); // 미배치 주의 안전교육 칸 · 그 주 후보 패널
  assert.equal(node(view.render(), "safety")[0].props.weekId, "W2");

  view.props.plan = { ...view.props.plan, status: "CONFIRMED" };
  const confirmed = view.render();
  assert.equal(node(confirmed, "safety").length, 0);
  const [confirmedCell] = node(rowsOf(confirmed, "tr", "safety_education")[0], "cell");
  assert.equal(confirmedCell.props.value, "[교통안전] - 횡단보도 건너기");
  assert.equal(confirmedCell.props.onSelect, undefined);
  // Ⓜ4 — 월별 주제형은 한글 내보내기 · 주간 만들기로 간다.
  const done = node(confirmed, "done")[0];
  assert.equal(typeof done.props.download, "function");
  assert.equal(done.props.next.href, "/plans/weekly");
  assert.equal(done.props.next.label, "주간계획안 만들기 →");
});

test("v1 — 후보 두기는 placeMonthlySafety(id, weekId, 후보 id, 현재 revision) 를 부르고 응답을 onPlan 으로 넘기며 409 면 onConflict", async () => {
  const view = openV1Editor([], withV1Candidates);
  let conflicts = 0;
  view.props.onConflict = () => conflicts++;
  await view.panel("W2").onPlace("W2", "cand_1");
  assert.deepEqual(view.placed, [[1, "W2", "cand_1", 1]]);
  assert.equal(view.props.plan.revision, 2);
  assert.equal(view.props.plan.safety_weeks[1].candidate_item_id, "cand_1");
  assert.match(text(view.render()), /안전교육을 두었어요/);

  view.setPlace(async () => {
    throw new StubApiError(409, "conflict");
  });
  await view.panel("W2").onPlace("W2", null);
  assert.equal(conflicts, 1);
});

test("v1 — 안전 줄 칸을 누르면 편집기 라벨이 「안전교육 후보 · n주」이고 editMonthlyCell 로 저장하며 그 주를 비우면 편집기가 닫힌다", async () => {
  const view = openV1Editor([], withV1Candidates);
  await view.panel("W2").onPlace("W2", "cand_1");
  view.tab("칸 편집");
  const opened = view.render();
  assert.equal(view.editor().label, "안전교육 후보 · 2주");
  assert.equal(view.editor().value, "횡단보도 건너기");
  assert.equal(withText(opened, "button", "AI로 이 칸 다시 만들기").length, 0);
  assert.equal(withText(opened, "p", "이 문장을 둔 다른 주도 같이 바뀌어요.").length, 1);

  view.editor().onSave("손을 들고 건너요");
  await view.tick();
  view.waits.shift().ok();
  await view.tick();
  assert.deepEqual(view.edits, [[1, "cand_1", "손을 들고 건너요", 2]]);

  view.tab("AI 후보");
  await node(view.render(), "safety")[0].props.onPlace("W2", null);
  view.tab("칸 편집");
  assert.equal(node(view.render(), "editor").length, 0);
  assert.match(text(view.render()), /「AI 후보」에서 이 주에 안전교육을 넣으면/);
});

test("v1 — 열린 입력창에 저장되지 않은 글이 있을 때 후보를 두면 칸 저장이 먼저 끝나고 그 응답 revision 으로 두며, 칸 저장이 실패하면 두지 않는다", async () => {
  const view = openV1Editor([], withV1Candidates);
  view.editor().onDraft("바깥놀이 수정");
  const placing = view.panel("W2").onPlace("W2", "cand_1");
  await view.tick();
  assert.deepEqual(view.edits, [[1, "c1", "바깥놀이 수정", 1]]);
  assert.deepEqual(view.placed, []);
  view.waits.shift().ok();
  await placing;
  assert.deepEqual(view.placed, [[1, "W2", "cand_1", 2]]);
  assert.equal(view.props.plan.revision, 3);

  view.pick("c1");
  view.editor().onDraft("실패할 수정");
  const failed = view.panel("W2").onPlace("W2", null);
  await view.tick();
  assert.equal(view.edits.length, 2);
  view.waits.shift().fail(new Error("offline"));
  await failed;
  assert.equal(view.placed.length, 1);
  assert.equal(view.props.plan.safety_weeks[1].candidate_item_id, "cand_1");
  assert.match(text(view.render()), /저장하지 못한 칸이 있어요/);
});

test('v1 — 빈 후보(display_value "")도 칸을 그려 눌러 편집기를 열고, 입력 중 글은 안전 줄에 섞이지 않으며, 저장 응답으로 같은 후보를 둔 모든 주의 display_value 가 같이 바뀐다', async () => {
  const view = openV1Editor([], (plan) => {
    const next = withV1Candidates(plan);
    next.safety_candidates[0].cell.value = "";
    next.safety_weeks = [
      { week_id: "W1", candidate_item_id: "cand_1", display_value: "" },
      { week_id: "W2", candidate_item_id: "cand_1", display_value: "" },
    ];
    return next;
  });
  const safetyCells = () => node(rowsOf(view.render(), "tr", "safety_education")[0], "cell");
  assert.deepEqual(
    safetyCells().map((c) => [c.props.id, c.props.value]),
    [
      ["safety:W1", ""],
      ["safety:W2", ""],
    ],
  );
  safetyCells()[0].props.onSelect("safety:W1");
  view.tab("칸 편집");
  assert.equal(view.editor().label, "안전교육 후보 · 1주");
  assert.equal(view.editor().value, "");

  view.editor().onDraft("손을 들고 건너요");
  assert.equal(view.editor().value, "손을 들고 건너요");
  assert.deepEqual(
    safetyCells().map((c) => c.props.value),
    ["", ""],
  );

  view.editor().onSave("손을 들고 건너요");
  await view.tick();
  assert.deepEqual(
    safetyCells().map((c) => c.props.value),
    ["", ""],
  );
  view.waits.shift().ok();
  await view.tick();
  assert.deepEqual(
    safetyCells().map((c) => c.props.value),
    ["[교통안전] - 손을 들고 건너요", "[교통안전] - 손을 들고 건너요"],
  );

  view.editor().onDraft("뛰지 않아요");
  assert.deepEqual(
    safetyCells().map((c) => c.props.value),
    ["[교통안전] - 손을 들고 건너요", "[교통안전] - 손을 들고 건너요"],
  );
});

test("v1 — 확정은 페이지 안 확인을 거친 뒤에만 보낸다 · 칸 다시 만들기 · 지우기는 없다", async () => {
  const view = openV1Editor([], withV1Candidates);
  const asks = () => node(view.render(), "ask");
  assert.equal(withText(view.render(), "button", "AI로 이 칸 다시 만들기").length, 0);
  assert.equal(withText(view.render(), "button", "지우고 다시 만들기").length, 0);
  withText(view.render(), "button", "확정하기")[0].props.onClick();
  const [ask] = asks();
  assert.match(
    ask.props.message,
    /이 내용으로 주간계획안을 만들게 돼요\. 확인할 것 1개가 남았어요\.$/,
  );
  assert.equal(ask.props.no, "더 다듬기");
  ask.props.onYes();
  await view.tick();
  assert.match(text(view.render()), /확정했어요/);
});
