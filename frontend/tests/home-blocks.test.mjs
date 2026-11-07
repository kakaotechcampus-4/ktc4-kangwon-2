// 첫 화면 쪽지의 날짜 셈. 주말 건너뛰기와 지난주 구간을 여기서 잡는다 —
// 틀리면 교사에게 「비어 있는 날」이 엉뚱한 날짜로 뜨고, 눈으로는 알아채기 어렵다.
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
const home = await import("../lib/workspace/home-blocks.ts");

// 2026-11-03 은 화요일이다. 아래 시험은 전부 이 주를 쓴다.
const TUE = "2026-11-03";

test("날짜 옮기기는 UTC 로 센다 — 달을 넘어도 하루 밀리지 않는다", () => {
  assert.equal(home.shiftDays(TUE, -1), "2026-11-02");
  assert.equal(home.shiftDays("2026-11-01", -1), "2026-10-31");
  assert.equal(home.shiftDays("2026-03-01", -1), "2026-02-28");
});

test("비어 있는 날은 제일 가까운 지난 평일을 집는다", () => {
  // 월요일(11-02)만 적혔다. 어제가 비지 않았으니 그 앞 금요일(10-30)이 비어 있다.
  assert.equal(home.emptyDay(["2026-11-02"], "2026-10-19", TUE), "2026-10-30");
});

test("비어 있는 날은 주말을 세지 않는다", () => {
  // 수요일에서 보면 화·월은 적혀 있고, 그 앞은 일·토다 — 금요일(10-30)로 건너뛴다.
  const dates = ["2026-11-02", "2026-11-03"];
  assert.equal(home.emptyDay(dates, "2026-10-19", "2026-11-04"), "2026-10-30");
});

test("쓰기 시작한 날보다 앞은 비어 있는 날이 아니다", () => {
  // 어제 처음 적었다. 그 앞은 빠뜨린 것이 아니라 쓰기 전이다.
  assert.equal(home.emptyDay(["2026-11-02"], "2026-11-02", TUE), null);
  // 한 번도 적은 적이 없으면 들추지 않는다.
  assert.equal(home.emptyDay([], "", TUE), null);
});

test("일과를 한 번도 안 적은 반에도 비어 있는 날이 보인다", () => {
  // 관찰은 2주째 적고 있는데 일과가 없는 교사 — 정작 이 쪽지가 필요한 사람이다.
  assert.equal(home.emptyDay([], "2026-10-19", TUE), "2026-11-02");
});

test("처음 적은 날은 일과와 관찰을 함께 본다", () => {
  assert.equal(home.firstWrittenDay(["2026-11-02"], ["2026-10-19"]), "2026-10-19");
  assert.equal(home.firstWrittenDay([], []), "");
});

test("지난주는 지난주 월요일부터 일요일까지다", () => {
  const rows = [
    { date: "2026-10-26", domain: "자연탐구" }, // 지난주 월
    { date: "2026-11-01", domain: "사회관계" }, // 지난주 일
    { date: "2026-10-25", domain: "신체운동" }, // 그 앞 주 일요일 — 아니다
    { date: "2026-11-02", domain: "의사소통" }, // 이번 주 월 — 아니다
  ];
  const look = home.lastWeekLook(rows, TUE);
  assert.equal(look.from, "2026-10-26");
  assert.equal(look.to, "2026-11-01");
  assert.equal(look.count, 2);
});

test("지난주에 제일 많았던 영역을 고르고, 같은 수면 이름 순으로 정한다", () => {
  const twice = [
    { date: "2026-10-26", domain: "자연탐구" },
    { date: "2026-10-27", domain: "자연탐구" },
    { date: "2026-10-28", domain: "사회관계" },
  ];
  assert.deepEqual(
    [home.lastWeekLook(twice, TUE).domain, home.lastWeekLook(twice, TUE).domainCount],
    ["자연탐구", 2],
  );
  // 하나씩이면 이름 순으로 앞선 것. 새로고침마다 바뀌면 교사가 숫자를 못 믿는다.
  const tied = [
    { date: "2026-10-26", domain: "자연탐구" },
    { date: "2026-10-27", domain: "사회관계" },
  ];
  assert.equal(home.lastWeekLook(tied, TUE).domain, "사회관계");
  assert.equal(home.lastWeekLook(tied, TUE).domainCount, 1);
});

test("지난주에 기록이 없으면 쪽지를 만들지 않는다", () => {
  assert.equal(home.lastWeekLook([{ date: TUE, domain: "자연탐구" }], TUE), null);
  assert.equal(home.lastWeekLook([], TUE), null);
});
