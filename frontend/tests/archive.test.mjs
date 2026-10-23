/** 문서 보관함(S-J5) 정렬 — 일지와 계획안을 합친 뒤 다시 정렬한다 (FR-701). */
import { test } from "node:test";
import assert from "node:assert/strict";

const { byArchiveOrder } = await import("../lib/workspace/archive.ts");

const doc = (serverId, createdAt) => ({ source: "document", serverId, createdAt });
const plan = (serverId, createdAt) => ({ source: "plan", serverId, createdAt });
const order = (items) => [...items].sort(byArchiveOrder).map((i) => `${i.source}:${i.serverId}`);

test("계획안 묶음이 일지 묶음 아래에 통째로 붙지 않고 섞여서 최신순이다", () => {
  assert.deepEqual(
    order([
      doc(1, "2026-10-01T00:00:00Z"),
      doc(2, "2026-10-03T00:00:00Z"),
      plan(1, "2026-10-02T00:00:00Z"),
      plan(2, "2026-10-04T00:00:00Z"),
    ]),
    ["plan:2", "document:2", "plan:1", "document:1"],
  );
});

test("같은 시각이면 일지가 먼저다 — 계획안 id 가 더 커도", () => {
  assert.deepEqual(order([plan(99, "2026-10-02T00:00:00Z"), doc(1, "2026-10-02T00:00:00Z")]), [
    "document:1",
    "plan:99",
  ]);
});

test("같은 시각 같은 종류끼리만 id 내림차순이다", () => {
  assert.deepEqual(
    order([
      doc(3, "2026-10-02T00:00:00Z"),
      plan(4, "2026-10-02T00:00:00Z"),
      doc(7, "2026-10-02T00:00:00Z"),
      plan(9, "2026-10-02T00:00:00Z"),
    ]),
    ["document:7", "document:3", "plan:9", "plan:4"],
  );
});

test("시각은 글자가 아니라 시간으로 비교한다 — Z 와 +09:00 이 섞여도", () => {
  // 글자로 비교하면 "2026-10-02T08..." 이 "2026-10-02T00..." 보다 뒤라 계획안이 위로 간다.
  // 실제로는 계획안 08:00+09:00 이 전날 23:00Z 라, 00:30Z 인 일지가 더 최신이다.
  assert.deepEqual(order([plan(1, "2026-10-02T08:00:00+09:00"), doc(1, "2026-10-02T00:30:00Z")]), [
    "document:1",
    "plan:1",
  ]);
});

test("같은 시각이면 서버 번호가 없는 브라우저 증빙이 서버 일지 뒤다", () => {
  assert.deepEqual(order([doc(null, "2026-10-02T00:00:00Z"), doc(3, "2026-10-02T00:00:00Z")]), [
    "document:3",
    "document:null",
  ]);
});
