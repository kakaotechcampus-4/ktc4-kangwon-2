// 놀이 월간 저장 큐: 한 줄 순서 · 칸 합치기 · 같은 값 안 보냄 · 422 · 409 · 실패 붙잡기 · whenIdle · freeze · 되돌리기 목록.
import { test } from "node:test";
import assert from "node:assert/strict";
const q = await import("../lib/plan-generator/playMonthlyQueue.ts");

const tick = () => new Promise((resolve) => setImmediate(resolve));
const err = (status) => Object.assign(new Error("x"), { status });
function setup(server = {}) {
  const sent = [];
  const gates = [];
  const log = { statuses: [], rejected: [], drained: 0, conflicts: 0 };
  const queue = q.createPlayMonthlyQueue({
    revision: 1,
    serverValue: (id) => server[id],
    send: (job, expected) => {
      sent.push({ job, expected });
      return new Promise((resolve, reject) =>
        gates.push((fail) => {
          if (fail) return reject(fail);
          if (job.kind === "cell") server[job.itemId] = job.value;
          resolve({ revision: expected + 1 });
        }),
      );
    },
    isConflict: (e) => e?.status === 409,
    isRejected: (e) => e?.status === 422,
    onStatus: (s) => log.statuses.push(s),
    onRejected: (j) => log.rejected.push(j),
    onDrained: () => log.drained++,
    onConflict: () => log.conflicts++,
  });
  const done = async (i = gates.length - 1, fail) => (gates[i](fail), tick());
  return { queue, sent, gates, log, done, server };
}
const cell = (itemId, value) => ({ kind: "cell", itemId, value });

test("one request at a time, in order, passing each response revision on", async () => {
  const t = setup();
  t.queue.enqueue(cell("a", "1"));
  t.queue.enqueue({ kind: "safety", weekId: "w1", candidateItemId: "s" });
  t.queue.enqueue({ kind: "copy", itemId: "d" });
  assert.equal(t.sent.length, 1);
  await t.done(0);
  await t.done(1);
  await t.done(2);
  assert.deepEqual(
    t.sent.map((s) => [s.job.kind, s.expected]),
    [
      ["cell", 1],
      ["safety", 2],
      ["copy", 3],
    ],
  );
  assert.deepEqual(t.log.statuses, ["saving", "saving", "saving", "saved"]);
  assert.equal(t.log.drained, 1);
});

test("queued edits of one cell merge into the latest, in-flight one is not touched", async () => {
  const t = setup();
  t.queue.enqueue(cell("a", "1"));
  t.queue.enqueue(cell("a", "2"));
  t.queue.enqueue(cell("a", "3"));
  t.queue.enqueue(cell("b", "x"));
  await t.done(0);
  await t.done(1);
  await t.done(2);
  assert.deepEqual(
    t.sent.map((s) => s.job.value),
    ["1", "3", "x"],
  );
});

test("a cell edit after another kind of job is not merged before it", async () => {
  const t = setup();
  t.queue.enqueue({ kind: "safety", weekId: "w", candidateItemId: null });
  t.queue.enqueue(cell("d", "old"));
  t.queue.enqueue({ kind: "copy", itemId: "d" });
  t.queue.enqueue(cell("d", "new"));
  await t.done(0);
  await t.done(1);
  await t.done(2);
  await t.done(3);
  assert.deepEqual(
    t.sent.map((s) => s.job.kind + (s.job.value ?? "")),
    ["safety", "cellold", "copy", "cellnew"],
  );
});

test("a value equal to the server's is not sent, blank to blank included", async () => {
  const t = setup({ a: "서버", b: "" });
  t.queue.enqueue(cell("a", "서버"));
  t.queue.enqueue(cell("b", ""));
  await tick();
  assert.equal(t.sent.length, 0);
  assert.equal(t.queue.enqueue(cell("b", "채움")), true);
  await t.done(0);
  t.queue.enqueue(cell("b", ""));
  await tick();
  assert.equal(t.sent.length, 2);
});

test("a rejected (422) job is dropped alone, the line goes on, and whenIdle says saved:false", async () => {
  const t = setup();
  t.queue.enqueue(cell("a", "1"));
  t.queue.enqueue(cell("b", "2"));
  const idle = t.queue.whenIdle();
  await t.done(0, err(422));
  assert.deepEqual(t.log.rejected, [cell("a", "1")]);
  assert.equal(t.sent.length, 2);
  assert.equal(t.sent[1].expected, 1);
  await t.done(1);
  assert.deepEqual(await idle, { saved: false, revision: 2 });
  assert.deepEqual(await t.queue.whenIdle(), { saved: true, revision: 2 });
});

test("409 clears everything, stops the queue and reports once", async () => {
  const t = setup();
  t.queue.enqueue(cell("a", "1"));
  t.queue.enqueue(cell("b", "2"));
  const idle = t.queue.whenIdle();
  await t.done(0, err(409));
  assert.equal(t.log.conflicts, 1);
  assert.equal(t.sent.length, 1);
  assert.deepEqual(await idle, { saved: false, revision: 1 });
  assert.equal(t.queue.enqueue(cell("c", "3")), false);
  assert.deepEqual(await t.queue.whenIdle(), { saved: false, revision: 1 });
});

test("a network failure holds the job at the front until retry, and a newer edit replaces it", async () => {
  const t = setup();
  t.queue.enqueue(cell("a", "1"));
  await t.done(0, err(500));
  assert.equal(t.log.statuses.at(-1), "failed");
  t.queue.enqueue(cell("a", "2"));
  await tick();
  assert.equal(t.sent.length, 2);
  assert.equal(t.sent[1].job.value, "2");
  await t.done(1);
  assert.equal(t.log.statuses.at(-1), "saved");
});

test("whenIdle waits for the line and answers the last revision", async () => {
  const t = setup();
  assert.deepEqual(await t.queue.whenIdle(), { saved: true, revision: 1 });
  t.queue.enqueue(cell("a", "1"));
  const idle = t.queue.whenIdle();
  await t.done(0);
  assert.deepEqual(await idle, { saved: true, revision: 2 });
  t.queue.enqueue(cell("b", "1"));
  await t.done(1, err(500));
  assert.deepEqual(await t.queue.whenIdle(), { saved: false, revision: 2 });
});

test("freeze refuses new jobs until unfreeze", async () => {
  const t = setup();
  t.queue.freeze();
  assert.equal(t.queue.enqueue(cell("a", "1")), false);
  assert.equal(t.sent.length, 0);
  t.queue.unfreeze();
  assert.equal(t.queue.enqueue(cell("a", "1")), true);
});

test("removing a row drops its queued cell edits but not the one in flight", async () => {
  const t = setup();
  t.queue.enqueue(cell("n", "1"));
  t.queue.enqueue(cell("d", "2"));
  t.queue.enqueue(cell("other", "3"));
  t.queue.enqueue({ kind: "remove", itemId: "n", cellIds: ["n", "d"] });
  await t.done(0);
  await t.done(1);
  await t.done(2);
  assert.deepEqual(
    t.sent.map((s) => s.job.kind + (s.job.itemId ?? "")),
    ["celln", "cellother", "removen"],
  );
});

test("history: 30 steps, new step clears redo, undo and redo walk the same steps", () => {
  let h = q.EMPTY_HISTORY;
  for (let i = 0; i < 35; i++)
    h = q.pushStep(h, { kind: "cell", itemId: "a", before: "" + i, after: "" + (i + 1) });
  assert.equal(h.undo.length, 30);
  const u = q.moveStep(h, "undo");
  assert.equal(u.step.after, "35");
  assert.equal(u.history.redo.length, 1);
  const r = q.moveStep(u.history, "redo");
  assert.deepEqual(r.history, h);
  assert.deepEqual(
    q.pushStep(u.history, { kind: "safety", weekId: "w", before: null, after: "s" }).redo,
    [],
  );
  assert.equal(q.moveStep(q.EMPTY_HISTORY, "undo"), null);
});

test("pure plan helpers: overlayCells, cellValue, safety, row removal", () => {
  const plan = {
    theme: { item_id: "t", value: "주제" },
    together: [
      {
        activity_id: "n",
        name: { item_id: "n", value: "행" },
        description: { item_id: "d", value: "설명" },
      },
    ],
    free_play: [],
    safety_weeks: [{ week_id: "w1", candidate_item_id: null }],
  };
  const next = q.overlayCells(plan, { d: "새 설명" });
  assert.equal(q.cellValue(next, "d"), "새 설명");
  assert.equal(q.cellValue(plan, "d"), "설명");
  assert.equal(q.overlayCells(plan, {}), plan);
  assert.equal(q.cellValue(plan, "없음"), undefined);
  assert.equal(q.safetyOf(q.withSafety(plan, "w1", "s"), "w1"), "s");
  assert.equal(q.withoutActivity(plan, "n").together.length, 0);
});
