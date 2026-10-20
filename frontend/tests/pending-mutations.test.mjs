import assert from "node:assert/strict";
import { test } from "node:test";
import { createMutationBarrier } from "../lib/api/pending-mutations.ts";

const settle = () => new Promise((resolve) => setImmediate(resolve));
function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((yes, no) => {
    resolve = yes;
    reject = no;
  });
  return { promise, resolve, reject };
}

test("track returns the original result; readers wait for completion without retaining a result", async () => {
  const barrier = createMutationBarrier();
  const work = deferred();
  assert.equal(barrier.track("A", work.promise), work.promise);
  const waiting = barrier.wait("A");
  const response = { name: "saved", execution: "server value" };
  work.resolve(response);
  assert.equal(await work.promise, response);
  assert.equal(await waiting, undefined);
});

test("three writes finishing 3 → 2 → 1 all remain behind the same scope barrier", async () => {
  const barrier = createMutationBarrier();
  const writes = [deferred(), deferred(), deferred()];
  writes.forEach((work) => barrier.track("A", work.promise));
  let ready = false;
  const waiting = barrier.wait("A").then(() => (ready = true));
  writes[2].resolve();
  await settle();
  assert.equal(ready, false);
  writes[1].resolve();
  await settle();
  assert.equal(ready, false);
  writes[0].resolve();
  await waiting;
  assert.equal(ready, true);
});

test("a different semantic scope does not wait for another class or date", async () => {
  const barrier = createMutationBarrier();
  const work = deferred();
  barrier.track("3|2026-10-06", work.promise);
  await barrier.wait("4|2026-10-06");
  await barrier.wait("3|2026-10-07");
  work.resolve();
  await barrier.wait("3|2026-10-06");
});

test("wait also follows a write registered after it started waiting", async () => {
  const barrier = createMutationBarrier();
  const first = deferred();
  const second = deferred();
  barrier.track("A", first.promise);
  let ready = false;
  const waiting = barrier.wait("A").then(() => (ready = true));
  barrier.track("A", second.promise);
  first.resolve();
  await settle();
  assert.equal(ready, false, "old completion cannot remove or skip the newer chain");
  second.resolve();
  await waiting;
});

test("a rejected write does not poison the next reader or a later write", async () => {
  const barrier = createMutationBarrier();
  const failed = deferred();
  barrier.track("A", failed.promise);
  const failure = assert.rejects(failed.promise, /not saved/);
  failed.reject(new Error("not saved"));
  await failure;
  await barrier.wait("A");
  const later = deferred();
  barrier.track("A", later.promise);
  let ready = false;
  const waiting = barrier.wait("A").then(() => (ready = true));
  await settle();
  assert.equal(ready, false);
  later.resolve("saved");
  await waiting;
});

test("settled chains are removed, while an older completion never removes a newer chain", async (t) => {
  const removed = [];
  const original = Map.prototype.delete;
  t.mock.method(Map.prototype, "delete", function (scope) {
    if (scope === "cleanup") removed.push(scope);
    return original.call(this, scope);
  });
  const barrier = createMutationBarrier();
  const first = deferred();
  const second = deferred();
  barrier.track("cleanup", first.promise);
  barrier.track("cleanup", second.promise);
  first.resolve();
  await settle();
  assert.deepEqual(removed, [], "first chain must leave the second registered");
  second.resolve();
  await barrier.wait("cleanup");
  assert.deepEqual(removed, ["cleanup"]);
  await barrier.wait("cleanup");
  assert.deepEqual(removed, ["cleanup"], "no settled entry remains to clean again");
});
