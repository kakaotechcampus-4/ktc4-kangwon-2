// usePlayMonthlySave: 화면에 바로 입히기 · 되돌리기(칸 글 · 안전 배치만) · 행 삭제 · 복사 뒤 목록 비움 · 422 되돌림.
import { test } from "node:test";
import assert from "node:assert/strict";
import { createRequire, registerHooks } from "node:module";
import { readFileSync, existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
registerHooks({
  resolve(spec, ctx, next) {
    if (spec.startsWith(".") && ctx.parentURL) {
      const u = new URL(spec + ".ts", ctx.parentURL);
      if (existsSync(fileURLToPath(u))) return { url: u.href, shortCircuit: true };
    }
    return next(spec, ctx);
  },
});
const queueModule = await import("../lib/plan-generator/playMonthlyQueue.ts");
const require = createRequire(import.meta.url);

const file = fileURLToPath(new URL("../lib/hooks/use-play-monthly-save.ts", import.meta.url));
const code = require("next/dist/compiled/babel/core").transformSync(readFileSync(file, "utf8"), {
  filename: file,
  babelrc: false,
  configFile: false,
  presets: [
    [require("next/dist/compiled/babel/preset-env"), { targets: { node: "current" } }],
    require("next/dist/compiled/babel/preset-typescript"),
  ],
}).code;

const base = () => ({
  id: 9,
  revision: 1,
  theme: { item_id: "t", value: "주제" },
  together: [
    {
      activity_id: "n",
      name: { item_id: "n", value: "행" },
      description: { item_id: "d", value: "설" },
    },
  ],
  free_play: [],
  safety_weeks: [{ week_id: "w1", candidate_item_id: null }],
});
const listeners = new Set();
globalThis.window = {
  addEventListener: (_, fn) => listeners.add(fn),
  removeEventListener: (_, fn) => listeners.delete(fn),
};
const tick = () => new Promise((r) => setTimeout(r, 0));

function mount({ fail = null } = {}) {
  let server = base();
  const sent = [];
  const slots = [];
  let cursor = 0;
  let effects = [];
  const react = {
    useState(init) {
      const k = cursor++;
      if (!(k in slots)) slots[k] = typeof init === "function" ? init() : init;
      return [slots[k], (v) => void (slots[k] = typeof v === "function" ? v(slots[k]) : v)];
    },
    useRef(init) {
      const k = cursor++;
      return (slots[k] ??= { current: init });
    },
    useEffect: (fn) => effects.push(fn),
  };
  const bump = (plan) => (server = { ...plan, revision: plan.revision + 1 });
  const api = {
    editPlayMonthlyCell: async (id, itemId, value, rev) => {
      sent.push(["cell", itemId, value, rev]);
      if (fail) throw fail;
      return bump(queueModule.overlayCells(server, { [itemId]: value }));
    },
    placePlayMonthlySafety: async (id, weekId, cand, rev) => {
      sent.push(["safety", weekId, cand, rev]);
      return bump(queueModule.withSafety(server, weekId, cand));
    },
    removePlayMonthlyActivity: async (id, itemId, rev) => {
      sent.push(["remove", itemId, rev]);
      return bump(queueModule.withoutActivity(server, itemId));
    },
    copyPlayMonthlyDrill: async (id, itemId, rev) => {
      sent.push(["copy", itemId, rev]);
      return bump(server);
    },
  };
  const modules = {
    react,
    "@/lib/api/playMonthly": api,
    "@/lib/api/plans": {
      isSaveConflict: (e) => e?.status === 409,
      isRejectedSave: (e) => e?.status === 422,
    },
    "@/lib/plan-generator/playMonthlyQueue": queueModule,
  };
  const compiled = { exports: {} };
  new Function("require", "module", "exports", code)((n) => modules[n], compiled, compiled.exports);
  const shown = { plan: base(), rejected: 0 };
  let hook;
  const render = () => {
    cursor = 0;
    effects = [];
    hook = compiled.exports.usePlayMonthlySave(
      shown.plan,
      (p) => (shown.plan = p),
      () => {},
      () => shown.rejected++,
    );
    effects.forEach((fn) => fn());
    return hook;
  };
  render();
  return { shown, sent, render, get: () => hook };
}

test("edit shows at once, sends, and undo/redo walk cell and safety steps", async () => {
  const m = mount();
  m.get().editCell("t", "새 주제");
  m.get().placeSafety("w1", "s1");
  assert.equal(m.shown.plan.theme.value, "새 주제");
  assert.equal(m.shown.plan.safety_weeks[0].candidate_item_id, "s1");
  await tick();
  assert.equal(m.render().canUndo, true);
  m.get().undo(); // 안전 배치 되돌리기
  assert.equal(m.shown.plan.safety_weeks[0].candidate_item_id, null);
  m.render().undo(); // 칸 글 되돌리기
  assert.equal(m.shown.plan.theme.value, "주제");
  await tick();
  assert.equal(m.render().canUndo, false);
  assert.equal(m.get().canRedo, true);
  m.get().redo();
  assert.equal(m.shown.plan.theme.value, "새 주제");
  await tick();
  assert.deepEqual(
    m.sent.map((s) => s.slice(0, 3)),
    [
      ["cell", "t", "새 주제"],
      ["safety", "w1", "s1"],
      ["safety", "w1", null],
      ["cell", "t", "주제"],
      ["cell", "t", "새 주제"],
    ],
  );
  assert.deepEqual(
    m.sent.map((s) => s.at(-1)),
    [1, 2, 3, 4, 5],
  );
});

test("same value as shown is not a step; blank is a value", async () => {
  const m = mount();
  m.get().editCell("t", "주제");
  m.get().editCell("t", "");
  assert.equal(m.shown.plan.theme.value, "");
  await tick();
  assert.deepEqual(
    m.sent.map((s) => s[2]),
    [""],
  );
  assert.equal(m.render().canUndo, true);
});

test("row removal and drill copy are not undoable and empty the undo list", async () => {
  const m = mount();
  m.get().editCell("t", "A");
  await tick();
  assert.equal(m.render().canUndo, true);
  m.get().removeActivity("n");
  assert.equal(m.shown.plan.together.length, 0);
  await tick();
  assert.equal(m.render().canUndo, false);
  m.get().editCell("t", "B");
  await tick();
  assert.equal(m.render().canUndo, true);
  m.get().copyDrill("x");
  await tick();
  assert.equal(m.render().canUndo, false);
  assert.equal(m.get().canRedo, false);
});

test("a 422 puts the server value back, clears history and reports", async () => {
  const m = mount({ fail: { status: 422 } });
  m.get().editCell("t", "거절");
  assert.equal(m.shown.plan.theme.value, "거절");
  await tick();
  assert.equal(m.shown.plan.theme.value, "주제");
  assert.equal(m.shown.rejected, 1);
  assert.equal(m.render().canUndo, false);
  assert.deepEqual(await m.get().whenIdle(), { saved: true, revision: 1 });
});

test("freeze refuses new work and unfreeze accepts it again", async () => {
  const m = mount();
  m.get().freeze();
  m.get().editCell("t", "X");
  assert.equal(m.shown.plan.theme.value, "주제");
  assert.equal(m.render().canUndo, false);
  m.get().unfreeze();
  m.get().editCell("t", "X");
  assert.equal(m.shown.plan.theme.value, "X");
  assert.deepEqual(await m.get().whenIdle(), { saved: true, revision: 2 });
});
