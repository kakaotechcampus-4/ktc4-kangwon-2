// 고른 놀이 저장 큐 규칙(ADR-044 §1): 하나씩 · revision 이어받기 · 쌓인 변경 합치기 · 실패 뒤 남김.
import { test } from "node:test";
import assert from "node:assert/strict";
const { createSaveQueue, hasUnsentSave } =
  await import("../lib/plan-generator/playSelectionQueue.ts");

const sel = (...first) => ({ a: first, b: [] });
const tick = () => new Promise((resolve) => setImmediate(resolve));
const stale = new Error("stale");
function setup(revision = 1) {
  const sent = [];
  const statuses = [];
  let conflicts = 0;
  const gates = [];
  const control = { fail: null, reload: null };
  const queue = createSaveQueue({
    revision,
    send: (selections, expected) => {
      sent.push({ selections, expected });
      return new Promise((resolve, reject) =>
        gates.push(() => {
          if (control.fail) return reject(control.fail);
          resolve({ revision: expected + 1 });
        }),
      );
    },
    isConflict: (error) => error === stale,
    onStatus: (status) => statuses.push(status),
    onConflict: () => (conflicts++, control.reload ?? Promise.resolve()),
  });
  return { queue, sent, statuses, control, gates, conflicts: () => conflicts };
}

test("only one request is in flight and changes made meanwhile merge into the latest one", async () => {
  const t = setup();
  t.queue.enqueue(sel("x"));
  t.queue.enqueue(sel("x", "y"));
  t.queue.enqueue(sel("x", "y", "z"));
  assert.equal(t.sent.length, 1);
  t.gates[0]();
  await tick();
  assert.equal(t.sent.length, 2);
  assert.deepEqual(t.sent[1].selections, sel("x", "y", "z"));
  t.gates[1]();
  await tick();
  assert.equal(t.sent.length, 2);
  assert.deepEqual(t.statuses, ["saving", "saving", "saved"]);
});

test("each request carries the revision the previous response returned", async () => {
  const t = setup(5);
  t.queue.enqueue(sel("x"));
  t.gates[0]();
  await tick();
  t.queue.enqueue(sel("y"));
  t.gates[1]();
  await tick();
  assert.deepEqual(
    t.sent.map((r) => r.expected),
    [5, 6],
  );
});

test("a failure keeps the unsent change and the next change or retry sends it again", async () => {
  const t = setup();
  t.control.fail = new Error("network");
  t.queue.enqueue(sel("x"));
  t.gates[0]();
  await tick();
  assert.deepEqual(t.statuses, ["saving", "failed"]);
  assert.equal(t.conflicts(), 0);
  t.control.fail = null;
  t.queue.retry();
  assert.deepEqual(t.sent[1], { selections: sel("x"), expected: 1 });
  t.gates[1]();
  await tick();
  assert.equal(t.statuses.at(-1), "saved");
  // 실패 뒤 새 변경이 오면 못 보낸 것이 아니라 최신 하나만 간다.
  t.control.fail = new Error("network");
  t.queue.enqueue(sel("y"));
  t.gates[2]();
  await tick();
  t.control.fail = null;
  t.queue.enqueue(sel("y", "z"));
  assert.deepEqual(t.sent[3].selections, sel("y", "z"));
  assert.equal(t.sent[3].expected, 2);
});

test("a change that piles up during a failing request wins over the failed one", async () => {
  const t = setup();
  t.control.fail = new Error("network");
  t.queue.enqueue(sel("x"));
  t.queue.enqueue(sel("x", "y"));
  t.gates[0]();
  await tick();
  t.control.fail = null;
  t.queue.retry();
  assert.deepEqual(t.sent[1].selections, sel("x", "y"));
});

test("a conflict drops the unsent change, shows reloading, and ends idle with nothing left to send", async () => {
  const t = setup();
  let finishReload;
  t.control.reload = new Promise((resolve) => (finishReload = resolve));
  t.control.fail = stale;
  t.queue.enqueue(sel("x"));
  t.queue.enqueue(sel("x", "y")); // 보내는 동안 쌓인 변경
  t.gates[0]();
  await tick();
  assert.equal(t.conflicts(), 1);
  assert.equal(t.statuses.at(-1), "reloading");
  assert.equal(hasUnsentSave("reloading"), false);
  t.queue.enqueue(sel("z")); // 다시 불러오는 동안의 변경도 버린다
  finishReload();
  await tick();
  assert.deepEqual(t.statuses, ["saving", "reloading", "idle"]);
  t.queue.retry();
  await tick();
  assert.equal(t.sent.length, 1);
});

test("two conflicts in a row are each signalled and neither leaves a pending change", async () => {
  const t = setup();
  t.control.fail = stale;
  t.queue.enqueue(sel("x"));
  t.gates[0]();
  await tick();
  t.queue.enqueue(sel("y"));
  t.gates[1]();
  await tick();
  assert.equal(t.conflicts(), 2);
  t.queue.retry();
  assert.equal(t.sent.length, 2);
});

test("only a sending or failed save warns before leaving the page", () => {
  for (const [status, warns] of [
    ["idle", false],
    ["saving", true],
    ["saved", false],
    ["failed", true],
    ["reloading", false],
  ])
    assert.equal(hasUnsentSave(status), warns, status);
});

test("a conflict that arrives after the screen went away does not reload again", async () => {
  const t = setup();
  t.control.fail = stale;
  t.queue.enqueue(sel("x"));
  t.queue.setActive(false);
  t.gates[0]();
  await tick();
  assert.equal(t.conflicts(), 0);
  assert.equal(t.statuses.at(-1), "idle");
});
