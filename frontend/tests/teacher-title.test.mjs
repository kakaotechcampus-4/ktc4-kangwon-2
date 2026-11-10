// 이름 뒤 호칭은 한 번만 붙는다. 온보딩에서 「김하늘 교사」를 그대로 넣거나 이름 칸에
// 「멘토선생님」을 적으면 「멘토선생님 선생님」이 됐다(점검 H-E1, 시안 7).
import { test } from "node:test";
import assert from "node:assert/strict";

const { teacherTitle } = await import("../lib/greeting.ts");

test("이름 뒤에 선생님을 한 번 붙인다", () => {
  assert.equal(teacherTitle("김하늘"), "김하늘 선생님");
});

test("이름이 선생님 · 교사 · 쌤으로 끝나면 떼고 한 번만 붙인다", () => {
  // 이미 「선생님」으로 끝나면 적은 그대로 둔다(시안 7: 「멘토선생님」).
  assert.equal(teacherTitle("멘토선생님"), "멘토선생님");
  assert.equal(teacherTitle("김하늘 교사"), "김하늘 선생님");
  assert.equal(teacherTitle("하늘쌤"), "하늘 선생님");
  assert.equal(teacherTitle("김하늘 선생님 "), "김하늘 선생님");
});

test("이름이 없거나 호칭뿐이면 선생님", () => {
  assert.equal(teacherTitle(""), "선생님");
  assert.equal(teacherTitle(null), "선생님");
  assert.equal(teacherTitle("교사"), "선생님");
  assert.equal(teacherTitle("선생님"), "선생님");
});
