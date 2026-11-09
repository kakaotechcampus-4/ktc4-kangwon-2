/** 관찰 기록 상황 칸을 그날 일과로 채우는 규칙 (lib/workspace/record-context.ts). */
import { test } from "node:test";
import assert from "node:assert/strict";

const ctx = await import("../lib/workspace/record-context.ts");

const DAY = [
  { name: "등원", start: "09:00", end: "" },
  { name: "실내놀이", start: "10:00", end: "11:30" },
  { name: "점심", start: "11:30", end: "" },
  { name: "바깥놀이", start: "14:00", end: "" },
];

test("지금 시각이 든 일과 — 끝이 없으면 다음 일과까지, 마지막이면 고르지 않는다", () => {
  assert.equal(ctx.slotAt(DAY, "08:59"), null);
  assert.equal(ctx.slotAt(DAY, "09:30").name, "등원");
  assert.equal(ctx.slotAt(DAY, "11:29").name, "실내놀이");
  assert.equal(ctx.slotAt(DAY, "11:30").name, "점심");
  assert.equal(ctx.slotAt(DAY, "15:00"), null);
  assert.equal(ctx.slotAt([{ name: "자유", start: "", end: "" }], "10:00"), null);
});

test("흥미 영역은 실내 놀이만 묻고, 넣는 말은 「실내놀이, 쌓기」처럼 50자 안이다", () => {
  assert.equal(ctx.isIndoorPlay("실내놀이"), true);
  assert.equal(ctx.isIndoorPlay("오전 자유놀이"), true);
  assert.equal(ctx.isIndoorPlay("바깥놀이"), false);
  assert.equal(ctx.isIndoorPlay("점심"), false);
  assert.equal(ctx.contextFor("실내놀이", "쌓기"), "실내놀이, 쌓기");
  assert.equal(ctx.contextFor("가".repeat(60)).length, 50);
  assert.equal(ctx.PLACES.join(" "), "쌓기 역할 미술 수조작 언어 과학 음률");
});

test("상황 칸 글에서 고른 일과와 영역을 읽는다. 손으로 고친 글은 아무것도 아니다", () => {
  assert.deepEqual(ctx.pickedSlot(DAY, "실내놀이, 쌓기"), { slot: DAY[1], place: "쌓기" });
  assert.deepEqual(ctx.pickedSlot(DAY, "점심"), { slot: DAY[2], place: "" });
  assert.equal(ctx.pickedSlot(DAY, "실내놀이, 블록 영역 구석"), null);
  assert.equal(ctx.pickedSlot(DAY, ""), null);
});
