import { test } from "node:test";
import assert from "node:assert/strict";
const { stackByChild } = await import("../lib/workspace/record-stack.ts");

const rec = (id, childId, at) => ({ id, childId, createdAt: `2026-11-10T${at}:00+09:00` });
const ids = (piles) => piles.map((p) => p.map((r) => r.id));

test("같은 아이 기록은 한 벌, 가장 최근 장이 위이고 벌은 그 장 자리에 선다", () => {
  // 서버 순서(최근 것부터): 가람 10:40, 나래 10:30, 가람 10:20, 다온 10:10, 가람 09:00
  const day = [
    rec("g3", "garam", "10:40"),
    rec("n1", "narae", "10:30"),
    rec("g2", "garam", "10:20"),
    rec("d1", "daon", "10:10"),
    rec("g1", "garam", "09:00"),
  ];
  assert.deepEqual(ids(stackByChild(day)), [["g3", "g2", "g1"], ["n1"], ["d1"]]);
});

test("목록이 오래된 것부터 와도 벌은 그 아이 가장 최근 기록 자리에 선다", () => {
  const day = [
    rec("g1", "garam", "09:00"),
    rec("d1", "daon", "10:10"),
    rec("g2", "garam", "10:20"),
    rec("n1", "narae", "10:30"),
  ];
  // 가람 벌의 맨 위(g2)는 원래 셋째 자리 — 다온 다음, 나래 앞.
  assert.deepEqual(ids(stackByChild(day)), [["d1"], ["g2", "g1"], ["n1"]]);
});

test("거른 목록을 받으면 맞은 기록만 묶인다 — 한 장이면 벌이 아니다", () => {
  const day = [rec("g3", "garam", "10:40"), rec("n1", "narae", "10:30")];
  const piles = stackByChild(day);
  assert.deepEqual(ids(piles), [["g3"], ["n1"]]);
  assert.ok(piles.every((p) => p.length === 1));
});
