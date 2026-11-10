/**
 * 보육일지 하루 화면의 규칙들 (lib/workspace/journal-day.ts).
 * 계획안에서 후보 고르기 · 관찰에서 이름 빼기 · 날씨 칩 · 깐 줄 안내.
 */
import assert from "node:assert/strict";
import { test } from "node:test";

const day = await import("../lib/workspace/journal-day.ts");

const plan = {
  operating_days: ["MON", "TUE", "WED", "THU", "FRI"],
  week_period: { label: "", start_date: "2026-11-09", end_date: "2026-11-13" },
  display_end_date: "2026-11-13",
  sections: [
    {
      section_key: "group_activity",
      label: "대·소집단 활동",
      visible: true,
      order: 1,
      repeat_by: "DAY",
      cells: [
        { item_id: "a1", value: "낙엽 모자이크", day: "MON" },
        { item_id: "a2", value: "솔방울 굴리기\n가을 소리 찾기", day: "TUE" },
      ],
    },
    {
      section_key: "special_program",
      label: "특별활동",
      visible: true,
      order: 2,
      repeat_by: "DAY",
      cells: [{ item_id: "s1", value: "체육", day: "MON" }],
    },
    {
      section_key: "indoor_play",
      label: "실내 자유놀이",
      visible: true,
      order: 3,
      repeat_by: "NONE",
      cells: [
        { item_id: "i1", value: "쌓기: 낙엽 길 만들기", day: null },
        { item_id: "i2", value: "", day: null },
      ],
    },
    { section_key: "hidden", label: "숨김", visible: false, order: 4, cells: [{ value: "x" }] },
  ],
};

test("계획안 중 그날이 든 주를 고른다 — 표시 마지막 날까지", () => {
  const other = { ...plan, week_period: { ...plan.week_period, start_date: "2026-11-02" } };
  other.display_end_date = "2026-11-06";
  assert.equal(day.planOfDay([other, plan], "2026-11-10"), plan);
  assert.equal(day.planOfDay([other, plan], "2026-11-15"), null);
});

test("요일 칸이 있는 「활동」 · 「특별활동」 줄에만 그날 후보가 뜬다", () => {
  const monday = day.dayPlan(plan, "2026-11-09");
  assert.deepEqual(day.planCandidates("활동", monday), ["낙엽 모자이크"]);
  assert.deepEqual(day.planCandidates("특별활동(체육)", monday), ["체육"]);
  assert.deepEqual(day.planCandidates("오전 실내놀이", monday), []);
  assert.deepEqual(day.planCandidates("바깥놀이(대체)", monday), []);
  // 한 칸에 두 줄이면 후보도 둘이다.
  assert.deepEqual(day.planCandidates("활동", day.dayPlan(plan, "2026-11-10")), [
    "솔방울 굴리기",
    "가을 소리 찾기",
  ]);
});

test("「계획 보기」는 그날 칸과 주 전체 칸을 묶음별로 준다 — 숨긴 칸 · 빈 칸은 뺀다", () => {
  const monday = day.dayPlan(plan, "2026-11-09");
  assert.deepEqual(monday.all, [
    { label: "대·소집단 활동", values: ["낙엽 모자이크"] },
    { label: "특별활동", values: ["체육"] },
    { label: "실내 자유놀이", values: ["쌓기: 낙엽 길 만들기"] },
  ]);
});

test("관찰은 상황의 첫 말이 일과 이름과 겹칠 때 그 줄에 뜬다", () => {
  assert.equal(day.contextMatches("실내놀이, 쌓기", "오전 실내놀이"), true);
  assert.equal(day.contextMatches("오전 실내놀이", "오전 실내놀이"), true);
  assert.equal(day.contextMatches("바깥놀이", "바깥놀이(대체)"), true);
  assert.equal(day.contextMatches("점심", "오전 실내놀이"), false);
  assert.equal(day.contextMatches("", "오전 실내놀이"), false);
});

test("관찰 글에서 반 아이 이름을 ○○ 로 빼고, 외자 부르는 이름은 못 가린 낱말로 짚는다", () => {
  const names = ["김가람", "이나래", "박솔"];
  assert.deepEqual(day.withoutNames("가람이가 나래에게 같이 만들자고 함", names), {
    text: "○○가 ○○에게 같이 만들자고 함",
    suspects: [],
  });
  assert.deepEqual(day.withoutNames("김가람이 블록을 쌓음", names), {
    text: "○○ 블록을 쌓음",
    suspects: [],
  });
  // 외자(솔)는 글자 하나라 지우면 문장이 망가진다. 지우지 않고 노랗게 짚는다.
  assert.deepEqual(day.withoutNames("솔이가 웃었다", names), {
    text: "솔이가 웃었다",
    suspects: ["솔이"],
  });
});

test("비 · 눈 · 미세먼지 날만 특이사항 칩이 하나 뜬다 — 눈이면 「눈으로」", () => {
  const w = (sky, dust, hint) => ({ date: "", sky, dust, source: "auto", indoor_hint: hint });
  assert.equal(day.indoorNote(w("비", "보통", "rain")), "비로 실내 대체놀이");
  assert.equal(day.indoorNote(w("눈", null, "rain")), "눈으로 실내 대체놀이");
  assert.equal(day.indoorNote(w("비나 눈", null, "rain")), "비나 눈으로 실내 대체놀이");
  assert.equal(day.indoorNote(w("맑음", "나쁨", "dust")), "미세먼지로 실내 대체놀이");
  assert.equal(day.indoorNote(w("맑음", "보통", null)), null);
  assert.equal(day.indoorNote(null), null);
});

test("바깥놀이 줄에는 대체 칩이 뜨고, 이미 「(대체)」면 안 뜬다", () => {
  assert.equal(day.needsOutdoorSwap("바깥놀이", "rain"), true);
  assert.equal(day.needsOutdoorSwap("바깥놀이(대체)", "rain"), false);
  assert.equal(day.needsOutdoorSwap("바깥놀이", null), false);
  assert.equal(day.needsOutdoorSwap("오전 실내놀이", "dust"), false);
});

test("깐 줄 안내 — 기본 일과표인지, 어느 날 일과인지", () => {
  assert.equal(
    day.presetNote({ source: "template", from_date: null, rows: [] }),
    "반 기본 일과표로 깔았어요",
  );
  assert.equal(
    day.presetNote({ source: "last_week", from_date: "2026-11-03", rows: [] }),
    "11월 3일 (화) 일과로 깔았어요",
  );
  assert.equal(day.presetNote(null), "");
});

test("넣는 글은 줄을 바꿔 덧붙인다", () => {
  assert.equal(day.appendLine("", "낙엽 모자이크"), "낙엽 모자이크");
  assert.equal(day.appendLine("블록을 쌓았다.", "낙엽 모자이크"), "블록을 쌓았다.\n낙엽 모자이크");
});
