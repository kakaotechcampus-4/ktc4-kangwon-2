// 놀이 중심 월간 ⑥ 확정 바 · 변경 이력 패널 — props 만 받는 두 컴포넌트가 약속대로 움직이는지.
import assert from "node:assert/strict";
import { test } from "node:test";
import { createRequire } from "node:module";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
process.env.TZ = "Asia/Seoul"; // 시각이 UTC 로 오고 화면이 현지로 바꾸는지 보려면 UTC 가 아닌 시간대여야 한다.

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

// 한 번 그릴 때마다 훅 칸을 순서대로 다시 읽는 대역. effect 는 deps 가 바뀔 때만 돈다.
function harness() {
  const slots = [];
  let index = 0;
  let pending = [];
  const cleanups = [];
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
    pending.forEach((fn) => {
      const cleanup = fn();
      if (typeof cleanup === "function") cleanups.push(cleanup);
    });
    return tree;
  };
  return {
    unmount: () => cleanups.splice(0).forEach((fn) => fn()),
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
  constructor(status, code, fields = []) {
    super(code + " 문구");
    this.status = status;
    this.body = { error: { code, fields } };
  }
}
const tick = () => new Promise((done) => setTimeout(done, 0));
const plan = { id: 5, status: "DRAFT", revision: 3 };

function bar(over = {}) {
  const log = [];
  const h = harness();
  globalThis.document = { activeElement: { blur: () => log.push("blur") } };
  const props = {
    plan,
    whenIdle: async () => (log.push("idle"), { saved: true, revision: 7 }),
    freeze: () => log.push("freeze"),
    unfreeze: () => log.push("unfreeze"),
    onConfirmed: (p) => log.push(["confirmed", p]),
    onConflict: () => log.push("conflict"),
    ...over,
  };
  const mod = compile("../components/plan-generator/PlayMonthlyConfirmBar.tsx", {
    react: h.react,
    "@/components/workspace/Workspace.module.css": esModule(css),
    "@/lib/api/client": { ApiError: StubApiError },
    "@/lib/api/playMonthly": {
      confirmPlayMonthly: async (id, rev) => {
        log.push(["confirm", id, rev]);
        if (over.confirm) return over.confirm();
        return { id, status: "CONFIRMED", revision: rev + 1 };
      },
    },
    "@/lib/api/plans": {
      isSaveConflict: (e) => ["STALE_WRITE", "ALREADY_CONFIRMED"].includes(e?.body?.error?.code),
    },
  });
  const render = () => h.render(mod.default, props);
  const click = async () => {
    withText(render(), "button", "확정하기")[0].props.onClick();
    await tick();
    return render();
  };
  return { log, render, click, mod, h };
}

test("confirm bar: blur, freeze, wait for the queue, then confirm with the revision it reports", async () => {
  const b = bar();
  const first = b.render();
  assert.equal(withText(first, "span", "확정하면 고칠 수 없어요").length, 1);
  await b.click();
  assert.deepEqual(b.log, [
    "blur",
    "freeze",
    "idle",
    ["confirm", 5, 7], // plan.revision 은 3 이지만 큐가 끝난 뒤의 7 로 보낸다
    ["confirmed", { id: 5, status: "CONFIRMED", revision: 8 }],
    // 확정되면 큐를 다시 열지 않는다 — 열린 입력창의 마지막 저장이 확정본을 덮지 못하게.
  ]);
});

test("confirm bar: a save rejected while waiting says it was put back, not 'save again'", async () => {
  const b = bar({ whenIdle: async () => ({ saved: false, revision: 7, rejected: true }) });
  const after = await b.click();
  assert.equal(
    text(all(after).find((n) => n.props?.role === "alert")),
    "저장하지 못한 곳을 원래대로 되돌렸어요. 확인한 뒤 다시 확정해 주세요.",
  );
  assert.equal(b.log.at(-1), "unfreeze");
});

test("confirm bar: a failed save means no confirm, a Korean message, and unfreeze", async () => {
  const b = bar({ whenIdle: async () => ({ saved: false, revision: 7 }) });
  const after = await b.click();
  assert.equal(
    b.log.some((x) => x[0] === "confirm"),
    false,
  );
  assert.equal(
    text(all(after).find((n) => n.props?.role === "alert")),
    "저장하지 못했어요. 다시 저장한 뒤 확정해 주세요.",
  );
  assert.equal(b.log.at(-1), "unfreeze");
});

test("confirm bar: 422 lists what is lacking by counting the fields", async () => {
  const fields = [
    "theme",
    "together.item_a",
    "together.item_b",
    "together.item_a.content_ids",
    "free_play.item_c.content_ids",
    "mystery",
  ];
  const b = bar({
    confirm: () => Promise.reject(new StubApiError(422, "VALIDATION_FAILED", fields)),
  });
  const after = await b.click();
  assert.equal(
    text(all(after).find((n) => n.props?.role === "alert")),
    "확정하려면 채워야 할 곳이 있어요: 놀이 주제 · 이름 없는 함께 하는 활동 2개 · 누리과정 연결을 1~3개로 맞춰야 하는 행 2개",
  );
  assert.equal(b.log.at(-1), "unfreeze");
});

test("confirm bar: 409 hands over to onConflict and says nothing itself", async () => {
  for (const code of ["STALE_WRITE", "ALREADY_CONFIRMED"]) {
    const b = bar({ confirm: () => Promise.reject(new StubApiError(409, code)) });
    const after = await b.click();
    assert.equal(b.log.includes("conflict"), true);
    assert.equal(
      all(after).some((n) => n.props?.role === "alert"),
      false,
    );
    assert.equal(b.log.includes("unfreeze"), true);
  }
});

test("confirm bar: onConflict rejecting still says so and unfreezes", async () => {
  const b = bar({
    confirm: () => Promise.reject(new StubApiError(409, "STALE_WRITE")),
    onConflict: () => Promise.reject(new Error("net")),
  });
  const after = await b.click();
  assert.match(text(withText(after, "p", "최신 내용")[0]), /새로고침해 주세요/);
  assert.equal(b.log.at(-1), "unfreeze");
});

test("confirm bar: any other failure shows its message and unfreezes", async () => {
  const b = bar({ confirm: () => Promise.reject(new StubApiError(500, "SERVER")) });
  const after = await b.click();
  assert.equal(text(all(after).find((n) => n.props?.role === "alert")), "SERVER 문구");
  assert.equal(b.log.at(-1), "unfreeze");
});

test("confirm bar: a second click while confirming does nothing", async () => {
  let release;
  const b = bar({ whenIdle: () => new Promise((done) => (release = done)) });
  const button = () => withText(b.render(), "button", "확정")[0];
  button().props.onClick();
  button().props.onClick();
  assert.equal(button().props.disabled, true);
  assert.equal(b.log.filter((x) => x === "freeze").length, 1);
  release({ saved: true, revision: 3 });
  await tick();
  assert.equal(b.log.filter((x) => x[0] === "confirm").length, 1);
});

test("confirm bar: after unmount nothing is confirmed or reported", async () => {
  let release;
  const b = bar({ whenIdle: () => new Promise((done) => (release = done)) });
  b.render();
  b.click();
  b.h.unmount();
  release({ saved: true, revision: 3 });
  await tick();
  assert.equal(
    b.log.some((x) => x[0] === "confirm" || x[0] === "confirmed"),
    false,
  );
});

test("confirm bar: a confirmed plan shows no button", () => {
  const b = bar({ plan: { ...plan, status: "CONFIRMED" } });
  assert.equal(b.render(), null);
});

test("confirmShortages: counts rows, names the sections, skips unknown keys", () => {
  const { confirmShortages } = bar().mod;
  assert.equal(confirmShortages([]), "");
  assert.equal(confirmShortages(["mystery", "x.y.z"]), "");
  assert.equal(
    confirmShortages(["rationale", "together", "free_play", "free_play.i"]),
    "선정 이유 · 함께 하는 활동 행 · 자유놀이 행 · 이름 없는 자유놀이 1개",
  );
  // 같은 행이 이름 · 연결 둘 다 모자라도 연결은 행 수로 센다
  assert.equal(
    confirmShortages(["together.i.content_ids", "together.i.content_ids"]),
    "누리과정 연결을 1~3개로 맞춰야 하는 행 1개",
  );
});

const ev = (type, scope, more = {}) => ({
  type,
  occurred_at: "2026-10-28T08:41:45.000Z",
  scope,
  item_id: null,
  actor: "user_7",
  system_actor: null,
  value_change: null,
  generation_change: null,
  link_change: null,
  arrangement_change: null,
  copied_from: null,
  ...more,
});
function panel(events) {
  const mod = compile("../components/plan-generator/PlayMonthlyAuditPanel.tsx", {
    "@/components/workspace/Workspace.module.css": esModule(css),
  });
  return resolve(mod.default({ events }));
}

test("audit panel: Korean kind per event, local time, before and after of an edit", () => {
  const lines = all(
    panel([
      ev("TEACHER_EDITED", "CELL", { item_id: "i", value_change: { before: "봄", after: "" } }),
      ev("ARRANGEMENT_CHANGED", "PLAN", {
        arrangement_change: { scope: "together", before: ["a"], after: ["a", "b"] },
      }),
      ev("ARRANGEMENT_CHANGED", "PLAN", {
        arrangement_change: { scope: "2026-11-W2", before: [], after: ["s"] },
      }),
      ev("CANDIDATE_COPIED", "CELL", {
        value_change: { before: "", after: "화재 대피" },
        copied_from: "d",
      }),
      ev("CONFIRMED", "PLAN"),
    ]),
  )
    .filter((n) => n.type === "li")
    .map(text);
  assert.equal(lines.length, 5);
  assert.match(lines[0], /고쳤어요 「봄」 → \(빈 칸\)/);
  assert.match(lines[1], /배치가 바뀌었어요 · 함께 하는 활동 1개 → 2개/);
  assert.match(lines[2], /배치가 바뀌었어요 · 2주 안전교육/);
  assert.match(lines[3], /훈련 후보를 복사했어요 \(빈 칸\) → 「화재 대피」/);
  assert.match(lines[4], /확정했어요/);
  // 08:41 UTC 는 한국에서 17:41 — 문자열을 자르면 08:41 이 보인다.
  assert.match(lines[0], /05:41/);
  assert.doesNotMatch(lines[0], /08:41/);
});

test("audit panel: a long text is shortened and an unknown type is skipped", () => {
  const lines = all(
    panel([
      ev("TEACHER_EDITED", "CELL", { value_change: { before: "가".repeat(40), after: "나" } }),
      ev("FROM_THE_FUTURE", "PLAN"),
    ]),
  )
    .filter((n) => n.type === "li")
    .map(text);
  assert.equal(lines.length, 1);
  assert.ok(lines[0].includes("「" + "가".repeat(30) + "…」"));
});

test("audit panel: the many CREATED cells fold into one line, a teacher-added one stays", () => {
  const created = (n, actor = null) =>
    ev("CREATED", "CELL", {
      item_id: "c" + n,
      actor,
      system_actor: actor ? null : "play_monthly_application",
    });
  const lines = all(
    panel([
      ev("CREATED", "PLAN", { actor: null, system_actor: "play_monthly_application" }),
      ...[1, 2, 3, 4].map((n) => created(n)),
      created(9, "user_7"),
      ev("CONFIRMED", "PLAN"),
    ]),
  )
    .filter((n) => n.type === "li")
    .map(text);
  assert.equal(lines.length, 4);
  assert.match(lines[0], /계획안을 만들었어요/);
  assert.match(lines[1], /처음 만들어진 칸 4개/);
  assert.match(lines[2], /칸을 만들었어요/);
  assert.match(lines[3], /확정했어요/);
});

test("audit panel: no events says so", () => {
  assert.match(text(panel([])), /아직 이력이 없어요/);
});

// ---- 변경 이력 보기 ----
function history(audit) {
  const h = harness();
  const calls = [];
  const mod = compile("../components/plan-generator/PlayMonthlyHistory.tsx", {
    react: h.react,
    "@/components/workspace/Workspace.module.css": esModule(css),
    "@/lib/api/playMonthly": {
      getPlayMonthlyAudit: (id, signal) => (calls.push([id, signal]), audit()),
    },
    "./PlayMonthlyAuditPanel": esModule((props) => jsx("panel", props)),
  });
  const render = () => h.render(mod.default, { id: 5 });
  const press = async (label) => {
    withText(render(), "button", label)[0].props.onClick();
    render();
    await tick();
    return render();
  };
  return { calls, h, render, press };
}

test("history: nothing is read until the button is pressed; pressing again folds it", async () => {
  const items = [ev("CONFIRMED", "PLAN")];
  const v = history(async () => ({ items }));
  assert.equal(v.calls.length, 0);
  assert.equal(
    all(v.render()).some((n) => n.type === "panel"),
    false,
  );
  const open = await v.press("변경 이력 보기");
  assert.deepEqual(v.calls[0][0], 5);
  assert.equal(all(open).find((n) => n.type === "panel").props.events, items);
  const folded = await v.press("변경 이력 접기");
  assert.equal(
    all(folded).some((n) => n.type === "panel"),
    false,
  );
  assert.equal(withText(folded, "button", "변경 이력 보기").length, 1);
});

test("history: says it is reading, and says so when reading fails", async () => {
  const reading = history(() => new Promise(() => {}));
  withText(reading.render(), "button", "변경 이력 보기")[0].props.onClick();
  assert.match(text(reading.render()), /변경 이력을 읽고 있어요/);
  const failing = history(() => Promise.reject(new Error("x")));
  const after = await failing.press("변경 이력 보기");
  assert.match(text(withText(after, "p", "불러오지")[0]), /변경 이력을 불러오지 못했어요/);
});

test("history: a late answer after unmount is ignored, and the request is aborted", async () => {
  let arrive;
  const v = history(() => new Promise((done) => (arrive = done)));
  withText(v.render(), "button", "변경 이력 보기")[0].props.onClick();
  v.render();
  const signal = v.calls[0][1];
  v.h.unmount();
  assert.equal(signal.aborted, true);
  arrive({ items: [ev("CONFIRMED", "PLAN")] });
  await tick();
  assert.equal(
    all(v.render()).some((n) => n.type === "panel"),
    false,
  );
});
