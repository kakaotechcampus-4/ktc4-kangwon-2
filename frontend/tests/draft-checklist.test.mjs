// 「이어서 하기」 메모지 체크 줄 — AI 후보로 채우는 줄만, 다 채웠으면 체크.
import assert from "node:assert/strict";
import { test } from "node:test";

const { annualChecklist, monthlyChecklist, playMonthlyChecklist, weeklyChecklist } =
  await import("../lib/plan-generator/draftChecklist.ts");

test("월별 주제형 연간은 체크 줄이 없고, 놀이 중심형은 구간마다 5개를 골랐는지 본다", () => {
  assert.deepEqual(annualChecklist({ format: "MONTHLY_THEME", months: [] }), []);
  const periods = [
    { label: "3월~5월", selected: ["a", "b", "c", "d", "e"] },
    { label: "6월~8월", selected: ["a"] },
  ];
  assert.deepEqual(annualChecklist({ format: "PLAY_PROJECT", periods }), [
    { label: "3월~5월", done: true },
    { label: "6월~8월", done: false },
  ]);
});

test("월간: 후보가 있을 때만 안전교육 · 소방대피 줄", () => {
  const plan = {
    safety_candidates: [{ cell: { item_id: "s1", value: "불조심" } }],
    safety_weeks: [{ display_value: "불조심" }, { display_value: " " }],
    drill_candidates: [{ cell: { item_id: "d", value: "" } }],
    sections: [{ section_key: "drill", cells: [{ value: "화재 대피" }] }],
  };
  assert.deepEqual(monthlyChecklist(plan), [
    { label: "안전교육", done: false },
    { label: "소방대피", done: true },
  ]);
  assert.deepEqual(monthlyChecklist({ ...plan, safety_candidates: [], drill_candidates: [] }), []);
});

test("놀이 월간: 둔 후보 문장이 비면 안 채운 것 · 고를 수만큼 골랐는지", () => {
  const plan = {
    safety_candidates: [{ cell: { item_id: "c1", value: "물놀이 안전" } }],
    safety_weeks: [{ candidate_item_id: "c1" }, { candidate_item_id: "c1" }],
    teacher_inputs: [{ key: "fire_disaster_drill", cell: { value: "" } }],
    drill_candidates: [{}],
    activity_pick: 2,
    together: [{}, {}],
    free_play: [{}],
  };
  assert.deepEqual(playMonthlyChecklist(plan), [
    { label: "안전교육", done: true },
    { label: "소방대피", done: false },
    { label: "함께 활동", done: true },
    { label: "자유놀이", done: false },
  ]);
  const old = { ...plan, safety_weeks: [], drill_candidates: [], activity_pick: null };
  assert.deepEqual(playMonthlyChecklist(old), []);
});

test("주간: 후보 있는 대·소집단 · 후보형 실내놀이 — 선생님 입력 칸은 세지 않는다", () => {
  const plan = {
    activity_grids: [{}],
    activity_candidates: [{ section_key: "group_activity" }],
    indoor_play_selection: true,
    sections: [
      {
        visible: true,
        section_key: "group_activity",
        cells: [{ value: "동시" }, { value: "", teacher_input: true }],
      },
      { visible: true, section_key: "indoor_play", cells: [{ value: "" }] },
    ],
  };
  assert.deepEqual(weeklyChecklist(plan), [
    { label: "대·소집단", done: true },
    { label: "실내놀이", done: false },
  ]);
  assert.deepEqual(weeklyChecklist({ sections: [] }), []);
});
