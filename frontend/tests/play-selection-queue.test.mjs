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
  const rejected = [];
  let conflicts = 0;
  const gates = [];
  const control = { fail: null, reload: null };
  const queue = createSaveQueue({
    revision,
    selections: sel(),
    send: (selections, expected) => {
      sent.push({ selections, expected });
      return new Promise((resolve, reject) =>
        gates.push(() => {
          if (control.fail) return reject(control.fail);
          resolve({ revision: expected + 1 });
        }),
      );
    },
    sendCell: (itemId, value, expected) => {
      sent.push({ cell: { itemId, value }, expected });
      return new Promise((resolve, reject) =>
        gates.push(() => {
          if (control.fail) return reject(control.fail);
          resolve({ revision: expected + 1 });
        }),
      );
    },
    isConflict: (error) => error === stale,
    isRejected: (error) => error?.status >= 400 && error?.status < 500,
    onRejected: (rejection) => rejected.push(rejection),
    onStatus: (status) => statuses.push(status),
    onConflict: () => (conflicts++, control.reload ?? Promise.resolve()),
  });
  return { queue, sent, statuses, rejected, control, gates, conflicts: () => conflicts };
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

test("after a conflict the queue takes nothing more and never says everything is saved", async () => {
  const t = setup();
  t.control.fail = stale;
  t.queue.enqueue(sel("x"));
  t.gates[0]();
  await tick();
  assert.equal(t.conflicts(), 1);
  t.queue.enqueue(sel("y"));
  t.queue.enqueueCell("item_a", "A", "B");
  t.queue.retry();
  assert.equal(t.sent.length, 1);
  assert.equal(await t.queue.whenIdle(), false);
});

test("a conflict releases whenIdle waiters with false, even if the reload itself fails", async () => {
  const t = setup();
  t.control.reload = Promise.reject(new Error("reload failed"));
  t.control.reload.catch(() => {});
  t.control.fail = stale;
  t.queue.enqueue(sel("x"));
  const waiting = t.queue.whenIdle();
  t.gates[0]();
  assert.equal(await waiting, false);
  assert.equal(t.statuses.at(-1), "idle");
  // 큐는 풀려 있다 — 다시 불러오기가 실패해도 영영 바쁘지 않다.
  assert.equal(await t.queue.whenIdle(), false);
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

test("a waiting pick goes before waiting cell edits, and the revision chain carries over", async () => {
  const t = setup(4);
  t.queue.enqueue(sel("x")); // 보내는 중
  t.queue.enqueueCell("item_a", "새 이름", "옛 이름");
  t.queue.enqueue(sel("x", "y"));
  t.queue.enqueue(sel("x", "y", "z")); // 기다리는 고르기는 합쳐진다
  assert.equal(t.sent.length, 1);
  t.gates[0]();
  await tick();
  assert.deepEqual(t.sent[1], { selections: sel("x", "y", "z"), expected: 5 });
  t.gates[1]();
  await tick();
  assert.deepEqual(t.sent[2], { cell: { itemId: "item_a", value: "새 이름" }, expected: 6 });
  t.gates[2]();
  await tick();
  assert.equal(t.sent.length, 3);
  assert.deepEqual(t.statuses, ["saving", "saving", "saving", "saved"]);
});

test("waiting cell edits merge per item_id, and returning to the first value sends nothing", async () => {
  const t = setup();
  t.queue.enqueue(sel("x")); // 보내는 중
  t.queue.enqueueCell("item_a", "A1", "A0");
  t.queue.enqueueCell("item_b", "B1", "B0");
  t.queue.enqueueCell("item_a", "A2", "A1");
  t.queue.enqueueCell("item_b", "B0", "B1"); // 처음 값으로 돌아왔다
  t.gates[0]();
  await tick();
  assert.deepEqual(t.sent[1], { cell: { itemId: "item_a", value: "A2" }, expected: 2 });
  t.gates[1]();
  await tick();
  assert.equal(t.sent.length, 2);
});

test("a failed cell edit is kept for retry, and a newer edit of the same cell replaces it", async () => {
  const t = setup();
  t.control.fail = new Error("network");
  t.queue.enqueueCell("item_a", "A1", "A0");
  t.gates[0]();
  await tick();
  assert.equal(t.statuses.at(-1), "failed");
  t.control.fail = null;
  t.queue.enqueueCell("item_a", "A2", "A0");
  assert.deepEqual(t.sent[1], { cell: { itemId: "item_a", value: "A2" }, expected: 1 });
});

test("a conflict drops waiting cell edits too", async () => {
  const t = setup();
  t.control.fail = stale;
  t.queue.enqueueCell("item_a", "A1", "A0");
  t.queue.enqueueCell("item_b", "B1", "B0");
  t.gates[0]();
  await tick();
  t.queue.retry();
  assert.equal(t.sent.length, 1);
});

test("whenIdle resolves true once everything is saved, false when stopped, and at once when idle", async () => {
  const t = setup();
  assert.equal(await t.queue.whenIdle(), true);
  t.queue.enqueue(sel("x"));
  t.queue.enqueueCell("item_a", "A1", "A0");
  let result;
  const waiting = t.queue.whenIdle().then((value) => (result = value));
  t.gates[0]();
  await tick();
  assert.equal(result, undefined); // 칸이 아직 남았다
  t.gates[1]();
  await waiting;
  assert.equal(result, true);
  t.control.fail = new Error("network");
  t.queue.enqueueCell("item_a", "A2", "A1");
  const stopped = t.queue.whenIdle();
  t.gates[2]();
  assert.equal(await stopped, false);
  assert.equal(await t.queue.whenIdle(), false);
});

test("a screen that went down sends nothing more", async () => {
  const t = setup();
  t.queue.setActive(false);
  t.queue.enqueueCell("item_a", "A1", "A0");
  t.queue.enqueue(sel("x"));
  assert.equal(t.sent.length, 0);
});

// ── 거절(409 가 아닌 4xx) · 서버가 확인한 값 · 고르기 먼저 ──
const tick0 = () => new Promise((resolve) => setTimeout(resolve, 0));
/** 서버 흉내 — 칸 편집은 그 후보(X)가 골라져 있어야 받고, 같은 값은 422 로 거절한다. */
function world({ cells = { item_a: "S0" }, selected = [], revision = 1 } = {}) {
  const sent = [];
  const statuses = [];
  const rejected = [];
  const gates = [];
  const server = { cells: { ...cells }, selected: new Set(selected) };
  const control = { netDown: false };
  let rev = revision;
  const hold = (work) =>
    new Promise((resolve, reject) =>
      gates.push(() => {
        if (control.netDown) return reject(new Error("network"));
        if (control.failWith) return reject(control.failWith);
        try {
          resolve(work());
        } catch (error) {
          reject(error);
        }
      }),
    );
  const queue = createSaveQueue({
    revision,
    selections: { p: [...selected] },
    send: (selections) => {
      sent.push("picks " + selections.p.join("+"));
      return hold(() => {
        if (control.rejectPicks) throw { status: 422 };
        server.selected = new Set(selections.p);
        return { revision: ++rev };
      });
    },
    sendCell: (itemId, value) => {
      sent.push("cell " + itemId + "=" + value);
      return hold(() => {
        if (itemId === "cell_X" && !server.selected.has("X")) throw { status: 422 };
        if (server.cells[itemId] === value) throw { status: 422 };
        server.cells[itemId] = value;
        return { revision: ++rev };
      });
    },
    isConflict: () => false,
    isRejected: (error) => error?.status === 422,
    onStatus: (status) => statuses.push(status),
    onRejected: (rejection) => rejected.push(rejection),
    onConflict: async () => {},
  });
  return { queue, sent, statuses, rejected, gates, server, control };
}
const pickP = (...list) => ({ p: list });
const flush = async (w, count = 6) => {
  for (let n = 0; n < count; n++) {
    w.gates.splice(0).forEach((open) => open());
    await tick0();
  }
};

test("a failed in-flight cell does not leave a later value without a confirmed base (F1)", async () => {
  const w = world();
  w.queue.enqueueCell("item_a", "A", "S0"); // 보내는 중
  w.queue.enqueueCell("item_a", "B", "A"); // 기다림
  w.control.netDown = true;
  w.gates.shift()();
  await tick0();
  w.control.netDown = false;
  w.queue.enqueueCell("item_a", "A", "B"); // 사용자가 되돌렸다
  w.queue.retry();
  await flush(w);
  assert.equal(w.server.cells.item_a, "A");
  assert.equal(await w.queue.whenIdle(), true);
});

test("a cell that went back to the confirmed value is skipped, and later picks still go (F2)", async () => {
  const w = world();
  w.queue.enqueueCell("item_a", "A", "S0");
  w.queue.enqueueCell("item_a", "S0", "A");
  w.control.netDown = true;
  w.gates.shift()();
  await tick0();
  w.control.netDown = false;
  w.queue.enqueue(pickP("X", "Y"));
  await flush(w);
  assert.deepEqual(w.sent, ["cell item_a=A", "picks X+Y"]);
  assert.equal(w.statuses.at(-1), "saved");
  assert.ok(w.server.selected.has("Y"));
  assert.deepEqual(w.rejected, []);
});

test("a failed cell reverted to the confirmed value clears the failure and settles whenIdle (S)", async () => {
  const w = world();
  w.control.netDown = true;
  w.queue.enqueueCell("item_a", "A", "S0");
  w.gates.shift()();
  await tick0();
  assert.equal(w.statuses.at(-1), "failed");
  assert.equal(await w.queue.whenIdle(), false);
  w.control.netDown = false;
  w.queue.enqueueCell("item_a", "S0", "A");
  w.queue.retry();
  await tick0();
  assert.equal(w.statuses.at(-1), "saved");
  assert.equal(w.sent.length, 1);
  assert.equal(await w.queue.whenIdle(), true);
});

test("pick, edit, unpick while one request flies: the cell is rejected, dropped, and the line goes on (a)", async () => {
  const w = world({ cells: { cell_X: "x0" } });
  w.queue.enqueue(pickP("Z")); // 보내는 중
  w.queue.enqueue(pickP("Z", "X"));
  w.queue.enqueueCell("cell_X", "x1", "x0");
  w.queue.enqueue(pickP("Z")); // 도로 뺀다
  await flush(w);
  w.queue.enqueue(pickP("Z", "W"));
  await flush(w);
  assert.deepEqual(w.rejected, [{ kind: "cell", itemId: "cell_X", value: "x0" }]);
  assert.deepEqual(w.sent, ["picks Z", "picks Z", "cell cell_X=x1", "picks Z+W"]);
  assert.equal(w.statuses.at(-1), "saved");
  assert.equal(w.server.cells.cell_X, "x0");
});

test("offline pick X, edit X, pick Y: after the network is back the pick goes first and nothing is rejected", async () => {
  const w = world({ cells: { cell_X: "x0" }, selected: ["Z"] });
  w.control.netDown = true;
  w.queue.enqueue(pickP("Z", "X"));
  await flush(w, 1);
  w.queue.enqueueCell("cell_X", "x1", "x0");
  w.queue.enqueue(pickP("Z", "X", "Y"));
  w.control.netDown = false;
  w.queue.retry();
  await flush(w);
  w.queue.enqueue(pickP("Z", "X", "Y", "W"));
  await flush(w);
  assert.deepEqual(w.rejected, []);
  assert.equal(w.server.cells.cell_X, "x1");
  assert.equal(w.statuses.at(-1), "saved");
  assert.deepEqual([...w.server.selected], ["Z", "X", "Y", "W"]);
});

test("four quick undos: the merged pick goes first, the cell is rejected and reverts to what the server has", async () => {
  const w = world({ cells: { cell_X: "edited" }, selected: ["Z", "Y"], revision: 5 });
  w.queue.enqueue(pickP("Z")); // 보내는 중
  w.queue.enqueue(pickP("Z", "X"));
  w.queue.enqueueCell("cell_X", "orig", "edited");
  w.queue.enqueue(pickP("Z"));
  await flush(w);
  assert.deepEqual(w.rejected, [{ kind: "cell", itemId: "cell_X", value: "edited" }]);
  assert.equal(w.statuses.at(-1), "saved");
  assert.equal(await w.queue.whenIdle(), true);
});

test("a rejected pick save reverts to the last confirmed picks, drops piled picks, and goes on", async () => {
  const w = world({ selected: ["Z"] });
  w.queue.enqueue(pickP("Z", "Y")); // 서버가 받는다
  await flush(w);
  w.control.rejectPicks = true;
  w.queue.enqueue(pickP("Z", "Y", "V")); // 거절될 것
  w.queue.enqueue(pickP("Z", "Y", "V", "U")); // 그 위에 쌓인 것
  await flush(w);
  assert.deepEqual(w.rejected, [{ kind: "picks", selections: pickP("Z", "Y") }]);
  assert.deepEqual(w.sent, ["picks Z+Y", "picks Z+Y+V"]);
  assert.equal(w.statuses.at(-1), "saved");
});

test("a rejected cell leaves nothing behind, so whenIdle resolves true", async () => {
  const w = world();
  w.queue.enqueueCell("cell_X", "x1", "x0"); // 거절될 것
  const waiting = w.queue.whenIdle();
  await flush(w);
  assert.equal(await waiting, true);
});

test("a cell rejected while a newer value waits drops both, sends nothing more, and whenIdle is true", async () => {
  const w = world({ cells: { cell_X: "x0" } });
  w.queue.enqueueCell("cell_X", "v1", "x0"); // 보내는 중 (X 가 안 골라져 422)
  w.queue.enqueueCell("cell_X", "v2", "x0");
  await flush(w);
  assert.deepEqual(w.sent, ["cell cell_X=v1"]);
  assert.deepEqual(w.rejected, [{ kind: "cell", itemId: "cell_X", value: "x0" }]);
  assert.equal(w.statuses.at(-1), "saved");
  assert.equal(await w.queue.whenIdle(), true);
});

test("only a 422 is thrown away; 401, 403, 404, 408, 429 and 5xx stay held for retry", async () => {
  for (const status of [401, 403, 404, 408, 429, 500, 503]) {
    const w = world();
    w.control.failWith = { status };
    w.queue.enqueueCell("item_a", "A", "S0");
    await flush(w, 2);
    assert.deepEqual(w.rejected, [], String(status));
    assert.equal(w.statuses.at(-1), "failed", String(status));
    assert.equal(await w.queue.whenIdle(), false);
    w.control.failWith = null;
    w.queue.retry();
    await flush(w, 2);
    assert.equal(w.server.cells.item_a, "A");
    assert.equal(w.statuses.at(-1), "saved");
  }
});
