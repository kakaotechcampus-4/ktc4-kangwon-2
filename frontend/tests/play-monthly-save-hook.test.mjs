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
const timetable = await import("../lib/plan-generator/playMonthlyTimetable.ts");
// 서버처럼 겹치지 않는 32자 id.
let nextId = 0;
const newId = () => "item_" + String(++nextId).padStart(32, "0");
const leafOf = (value = "") => timetable.leaf({ item_id: newId(), value });
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
  teacher_inputs: [{ key: "fire_disaster_drill", cell: { item_id: "f", value: "옛 글" } }],
  drill_candidates: [{ topic_id: "d1", label: "화재", cell: { item_id: "x", value: "후보 글" } }],
  special_activity: [leafOf("가"), leafOf(), leafOf(), leafOf(), leafOf()],
  special_activity_size: { column_widths: [20, 20, 20, 20, 20], height_mm: 24 },
});
const listeners = new Set();
globalThis.window = {
  addEventListener: (_, fn) => listeners.add(fn),
  removeEventListener: (_, fn) => listeners.delete(fn),
};
const tick = () => new Promise((r) => setTimeout(r, 0));

function mount({ fail = null, hold = false, drafting = false, failCopy = null } = {}) {
  const gates = [];
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
  const gate = async () => {
    if (!hold) return;
    const error = await new Promise((resolve) => gates.push(resolve));
    if (error) throw error;
  };
  const api = {
    editPlayMonthlyCell: async (id, itemId, value, rev) => {
      sent.push(["cell", itemId, value, rev]);
      await gate();
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
    splitPlayMonthlyCell: async (id, itemId, axis, rev) => {
      sent.push(["split", itemId, axis, rev]);
      const added = { item_id: newId(), value: "" },
        splitId = newId();
      return bump({
        ...server,
        special_activity: server.special_activity.map((d) =>
          timetable.splitLeaf(d, itemId, axis, splitId, added),
        ),
      });
    },
    removePlayMonthlyCell: async (id, itemId, rev) => {
      sent.push(["removeCell", itemId, rev]);
      return bump(queueModule.withoutTimetableCell(server, itemId));
    },
    resizePlayMonthlySplit: async (id, splitId, ratio, rev) => {
      sent.push(["ratio", splitId, ratio, rev]);
      return bump(queueModule.withTimetableRatio(server, splitId, ratio));
    },
    copyPlayMonthlyDrill: async (id, itemId, rev) => {
      sent.push(["copy", itemId, rev]);
      if (failCopy) throw failCopy;
      return bump(queueModule.overlayCells(server, { f: "후보 글" }));
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
    "@/lib/plan-generator/playMonthlyTimetable": timetable,
  };
  const compiled = { exports: {} };
  new Function("require", "module", "exports", code)((n) => modules[n], compiled, compiled.exports);
  const shown = { plan: structuredClone(server), rejected: [], kinds: [] };
  let hook;
  const render = () => {
    cursor = 0;
    effects = [];
    hook = compiled.exports.usePlayMonthlySave(
      shown.plan,
      (p) => (shown.plan = p),
      () => {},
      (itemId, kind) => (shown.rejected.push(itemId), shown.kinds.push(kind)),
      drafting,
    );
    effects.forEach((fn) => fn());
    return hook;
  };
  render();
  return { shown, sent, render, get: () => hook, gates };
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

test("timetable split · remove · ratio undo and redo through the server's new ids", async () => {
  const m = mount();
  const monday = () => m.shown.plan.special_activity[0];
  const a = monday().cell.item_id;
  m.get().splitCell(a, "VERTICAL");
  assert.equal(m.render().structuring, true); // 응답 전에는 잠근다
  await tick();
  assert.equal(m.render().structuring, false);
  const b1 = monday().children[1].cell.item_id;
  m.get().editCell(b1, "나");
  await tick();
  m.render().undo(); // 새 칸 글
  m.render().undo(); // 나누기 = 새 칸 빼기
  await tick();
  assert.equal(monday().cell.item_id, a);
  m.render().redo(); // 다시 나누기 — 새 id 가 생긴다
  await tick();
  const b2 = monday().children[1].cell.item_id;
  assert.notEqual(b2, b1);
  m.render().redo(); // 새 칸 글 — 옛 id 가 새 id 로 바뀌어 있다
  await tick();
  assert.equal(monday().children[1].cell.value, "나");
  const s2 = monday().split_id;
  m.render().resizeSplit(s2, 70);
  m.get().removeCell(a); // 위 칸(글 「가」)을 뺀다 — 형제가 칸 하나라 되돌릴 수 있다
  assert.equal(monday().cell.item_id, b2);
  await tick();
  m.render().undo(); // 되살리기: 형제를 나누고 글 · 비율을 되돌린다
  await tick();
  const [top, bottom] = monday().children.map((c) => c.cell);
  assert.deepEqual([top.item_id, top.value, bottom.value, monday().ratio], [b2, "가", "나", 70]);
  m.render().undo(); // 비율 — 경계 id 도 새 것으로 바뀌어 있다
  await tick();
  assert.equal(monday().ratio, 50);
  assert.deepEqual(
    m.sent.slice(-6).map((s) => s.slice(0, 3)),
    [
      ["removeCell", a, m.sent.at(-6)[2]],
      ["split", b2, "VERTICAL"],
      ["cell", b2, "가"],
      ["cell", bottom.item_id, "나"],
      ["ratio", monday().split_id, 70],
      ["ratio", monday().split_id, 50],
    ],
  );
  assert.deepEqual(
    m.sent.map((s) => s.at(-1)),
    m.sent.map((_, i) => i + 1),
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
  assert.deepEqual(m.shown.rejected, ["t"]);
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

test("a 422 on one cell leaves another pending cell's value and the undo base intact", async () => {
  const m = mount({ hold: true });
  m.get().editCell("t", "A1"); // 보내는 중(곧 거절)
  m.get().editCell("n", "B1"); // 대기
  m.gates[0]({ status: 422 });
  await tick();
  assert.equal(m.shown.plan.theme.value, "주제"); // 거절된 칸만 되돌아간다
  assert.equal(m.shown.plan.together[0].name.value, "B1"); // 대기 중인 칸은 그대로
  assert.deepEqual(m.shown.rejected, ["t"]);
  m.gates[1](); // B1 저장
  await tick();
  assert.equal(m.shown.plan.together[0].name.value, "B1");
  m.render().editCell("n", "B2");
  m.gates[2]();
  await tick();
  m.render().undo();
  m.gates[3]();
  await tick();
  assert.deepEqual(
    m.sent.map((s) => s.slice(1, 3)),
    [
      ["t", "A1"],
      ["n", "B1"],
      ["n", "B2"],
      ["n", "B1"],
    ],
  );
  assert.equal(m.shown.plan.together[0].name.value, "B1");
});

test("typed-but-unsaved text (drafting) turns on the leave warning even when the queue is idle", () => {
  listeners.clear();
  mount();
  assert.equal(listeners.size, 0);
  mount({ drafting: true });
  assert.equal(listeners.size, 1);
});

test("drill copy shows the candidate text at once and says the queue took it", async () => {
  const m = mount();
  assert.equal(m.get().copyDrill("x"), true);
  assert.equal(m.shown.plan.teacher_inputs[0].cell.value, "후보 글");
  await tick();
  assert.deepEqual(m.sent.at(-1).slice(0, 2), ["copy", "x"]);
});

test("a rejected drill copy puts the old text back and names the pasted-into cell", async () => {
  const m = mount({ failCopy: { status: 422 } });
  m.get().copyDrill("x");
  await tick();
  assert.equal(m.shown.plan.teacher_inputs[0].cell.value, "옛 글");
  assert.deepEqual(m.shown.rejected, ["f"]);
  assert.deepEqual(m.shown.kinds, ["copy"]);
});

test("while frozen editCell, copyDrill, undo and redo all say the queue refused", async () => {
  const m = mount();
  m.get().editCell("t", "A");
  await tick();
  m.render().undo();
  await tick();
  m.render().freeze();
  assert.equal(m.get().editCell("t", "B"), false);
  assert.equal(m.get().copyDrill("x"), false);
  assert.equal(m.get().redo(), false);
  assert.equal(m.shown.plan.theme.value, "주제"); // 다시 하기를 받지 않았으니 화면이 그대로다
  assert.equal(m.get().canRedo, true); // 걸음도 소비되지 않았다
  m.get().unfreeze();
  assert.equal(m.get().undo(), false); // 되돌릴 걸음이 없다
  assert.equal(m.get().redo(), true);
});
