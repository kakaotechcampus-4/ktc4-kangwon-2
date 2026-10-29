// 아이 표식은 **아이가 들어오고 나가도 안 바뀌어야** 한다. 교사가 외운 자리가
// 그때마다 무너지면 표식을 다는 뜻이 없다. 날짜 계산은 UTC+9 에서 하루 밀리기 쉬워
// 그 자리도 같이 잡는다.
import { test } from "node:test";
import assert from "node:assert/strict";
import { registerHooks } from "node:module";
import { existsSync } from "node:fs";
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
const mark = await import("../lib/workspace/child-mark.ts");

test("같은 id 면 늘 같은 표식", () => {
  const a = mark.markFor("child-7");
  const b = mark.markFor("child-7");
  assert.deepEqual(a, b);
});

test("표식은 목록 순서가 아니라 id 를 따른다", () => {
  // 가나다 순서가 밀려도(앞에 아이가 끼어들어도) 각 아이의 표식은 그대로다.
  const before = ["김하늘", "박하준", "이보람"];
  const after = ["강태윤", "김하늘", "박하준", "이보람"];
  for (const id of before) {
    assert.deepEqual(mark.markFor(id), mark.markFor(after[after.indexOf(id)]));
  }
});

test("도형·색이 범위 안이고 한쪽으로 쏠리지 않는다", () => {
  const shapes = new Set();
  const tones = new Set();
  for (let i = 0; i < 40; i += 1) {
    const m = mark.markFor(`c${i}`);
    assert.ok(m.shape >= 0 && m.shape < mark.MARK_SHAPES, `shape ${m.shape}`);
    assert.ok(m.tone >= 0 && m.tone < mark.MARK_TONES, `tone ${m.tone}`);
    shapes.add(m.shape);
    tones.add(m.tone);
  }
  // 마흔 명이면 여섯 도형·세 색이 모두 한 번씩은 나와야 쓸모가 있다.
  assert.equal(shapes.size, mark.MARK_SHAPES);
  assert.equal(tones.size, mark.MARK_TONES);
});

test("주는 월요일에 시작한다", () => {
  // 2026-10-30 은 금요일. 그 주 월요일은 10-26.
  assert.equal(mark.weekStart("2026-10-30"), "2026-10-26");
  assert.equal(mark.weekStart("2026-10-26"), "2026-10-26");
  // 일요일은 아직 지난 주다.
  assert.equal(mark.weekStart("2026-11-01"), "2026-10-26");
  assert.equal(mark.weekStart("2026-11-02"), "2026-11-02");
});

test("달이 바뀌어도 날 수가 맞다", () => {
  assert.equal(mark.daysBetween("2026-10-30", "2026-10-30"), 0);
  assert.equal(mark.daysBetween("2026-10-29", "2026-10-30"), 1);
  assert.equal(mark.daysBetween("2026-09-30", "2026-10-30"), 30);
  // 윤년 2월.
  assert.equal(mark.daysBetween("2028-02-28", "2028-03-01"), 2);
});

test("이번 주 횟수는 월요일부터, 마지막 기록은 가장 최근 것", () => {
  const rows = [
    { childId: "a", date: "2026-10-26" }, // 이번 주 월
    { childId: "a", date: "2026-10-28" }, // 이번 주 수
    { childId: "a", date: "2026-10-23" }, // 지난 주
    { childId: "b", date: "2026-10-30" }, // 다른 아이
  ];
  const a = mark.tallyFor(rows, "a", "2026-10-30");
  assert.equal(a.week, 2);
  assert.equal(a.days, 2);
  assert.equal(mark.tallyLabel(a), "2일 전 · 2번");

  const b = mark.tallyFor(rows, "b", "2026-10-30");
  assert.equal(b.week, 1);
  assert.equal(b.days, 0);
  assert.equal(mark.tallyLabel(b), "오늘 · 1번");
});

test("기록이 없는 아이는 가장 급하게 본다", () => {
  const none = mark.tallyFor([], "c", "2026-10-30");
  assert.equal(none.days, null);
  assert.equal(none.week, 0);
  assert.equal(mark.tallyLabel(none), "아직 없어요");
  assert.ok(mark.isStale(none));
});

test("한 주 넘게 비면 눈에 띄게 한다", () => {
  const rows = [{ childId: "a", date: "2026-10-23" }];
  assert.ok(!mark.isStale(mark.tallyFor(rows, "a", "2026-10-29"))); // 6일 전
  assert.ok(mark.isStale(mark.tallyFor(rows, "a", "2026-10-30"))); // 7일 전
});
