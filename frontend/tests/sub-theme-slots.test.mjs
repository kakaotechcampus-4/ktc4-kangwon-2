// 월별 주제형 주차별 소주제 칸(계약 I-A · 화면 #3): 이동 · 삭제 · 저장 값 · 개수 어긋남 · 문서 줄 수.
import { test } from "node:test";
import assert from "node:assert/strict";
const { moveSlot, removeSlot, setSlot, cleanSlots, slotMismatch, slotRows } =
  await import("../lib/plan-generator/subThemeSlots.ts");

test("move swaps neighbours and keeps the ends", () => {
  const list = ["a", "b", "c"];
  assert.deepEqual(moveSlot(list, 0, 1), ["b", "a", "c"]);
  assert.deepEqual(moveSlot(list, 2, -1), ["a", "c", "b"]);
  assert.equal(moveSlot(list, 0, -1), list);
  assert.equal(moveSlot(list, 2, 1), list);
  assert.deepEqual(list, ["a", "b", "c"]);
});

test("remove, set and the saved value drop blanks after trimming", () => {
  assert.deepEqual(removeSlot(["a", "b", "c"], 1), ["a", "c"]);
  assert.deepEqual(setSlot(["a", ""], 1, "b"), ["a", "b"]);
  assert.deepEqual(cleanSlots([" a ", "", "  ", "b"]), ["a", "b"]);
});

test("mismatch counts only filled slots; rows show missing and extra slots", () => {
  assert.equal(slotMismatch(["a", "b", "c", "d"], 4), false);
  assert.equal(slotMismatch(["a", "b", "c", " "], 4), true);
  assert.equal(slotMismatch(["a", "b", "c", "d", "e"], 4), true);
  assert.equal(slotRows(["a"], 4), 4);
  assert.equal(slotRows(["a", "b", "c", "d", "e"], 4), 5);
  assert.equal(slotRows([], 0), 1);
});
