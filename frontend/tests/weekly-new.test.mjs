// 주간 만들기(Ⓦ1)의 처음 고를 달 · 주, 월간에서 이어받는 것, 주간 용지의 줄 순서, 다듬기(Ⓦ3) 칸 출처.
import assert from "node:assert/strict";
import { test } from "node:test";
import { createRequire } from "node:module";
import { readFileSync } from "node:fs";

const require = createRequire(import.meta.url);
function load(path, modules) {
  const code = require("next/dist/compiled/babel/core").transformSync(
    readFileSync(new URL(path, import.meta.url), "utf8"),
    {
      filename: path,
      babelrc: false,
      configFile: false,
      presets: [
        [require("next/dist/compiled/babel/preset-env"), { targets: { node: "current" } }],
        [require("next/dist/compiled/babel/preset-react"), { runtime: "automatic" }],
        require("next/dist/compiled/babel/preset-typescript"),
      ],
    },
  ).code;
  const m = { exports: {} };
  new Function("require", "module", "exports", code)((n) => modules[n] ?? require(n), m, m.exports);
  return m.exports;
}
const React = require("react");
const { renderToStaticMarkup } = require("react-dom/server");
const stub = () => null;
const weeklyLabels = load("../lib/weekly/section-labels.ts", {});
const monthlyLabels = load("../lib/monthly/section-labels.ts", {});
const Paper = ({ title, children }) => React.createElement("article", { title }, children);
const sheet = load("../components/workspace/WeeklySheet.tsx", {
  react: React,
  "@/lib/weekly/section-labels": weeklyLabels,
  "@/components/plan-generator/PlayMonthlySheet": {
    Cell: ({ id, value }) => React.createElement("span", { "data-cell": id }, value),
    HEAD: "",
    LINE: "",
    Paper,
    TEACHER_HINT: "",
    period: () => "기간",
  },
});
const MONTH_ORDER = [3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 1, 2];
const { firstWeeklyMonth, firstOpenWeek, inheritWeek } = load(
  "../components/workspace/WeeklyNew.tsx",
  {
    react: React,
    "next/link": { __esModule: true, default: stub },
    "@/lib/api/client": { ApiError: class {} },
    "@/lib/api/monthly": {},
    "@/lib/api/plans": {},
    "@/lib/api/weekly": {},
    "@/lib/api/onboarding": {},
    "@/lib/monthly/play-entry": {},
    "@/lib/monthly/section-labels": monthlyLabels,
    "@/lib/onboarding/settings": {},
    "@/lib/onboarding/types": { MONTH_ORDER },
    "@/lib/hooks/use-client-state": {},
    "@/components/plan-ui/GenerationRing": { __esModule: true, default: stub },
    "@/components/plan-generator/PlanMemo": { PlanMemoField: stub, memoError: stub },
    "@/components/app/compact-shell": {},
    "./WorkspaceUI": {},
    "./WeeklySheet": sheet,
  },
);

test("처음 고를 달: 주소의 달 → 확정한 이번 달 → 마지막 확정 달 → 이번 달", () => {
  const done = { 9: { status: "CONFIRMED" }, 10: { status: "CONFIRMED" }, 11: { status: "DRAFT" } };
  assert.equal(firstWeeklyMonth(11, done, 4), 4);
  assert.equal(firstWeeklyMonth(10, done, 0), 10);
  assert.equal(firstWeeklyMonth(11, done, null), 10);
  assert.equal(firstWeeklyMonth(11, {}, null), 11);
});

test("처음 고를 주: 계획안이 없는 첫 주, 다 있으면 첫 주", () => {
  const weeks = [{ week_id: "W1" }, { week_id: "W2" }];
  assert.equal(firstOpenWeek(weeks, [{ week_id: "W1" }]), "W2");
  assert.equal(firstOpenWeek(weeks, [{ week_id: "W1" }, { week_id: "W2" }]), "W1");
  assert.equal(firstOpenWeek([], []), undefined);
});

test("월간에서 이어받는 것: 생활주제 + 그 주의 빈칸 아닌 칸", () => {
  const sec = (section_key, repeat_by, cells, order) => ({
    section_key,
    label: null,
    role: "CONTENT",
    visible: true,
    order,
    repeat_by,
    cells,
  });
  const monthly = {
    sections: [
      sec(
        "outdoor_play",
        "WEEK",
        [
          { week_id: "W1", value: "모래놀이" },
          { week_id: "W2", value: "" },
        ],
        2,
      ),
      sec("theme", "NONE", [{ value: "가을" }], 0),
    ],
  };
  assert.deepEqual(inheritWeek(monthly, "W1"), {
    theme: "가을",
    rows: [{ name: monthlyLabels.sectionName("outdoor_play"), value: "모래놀이" }],
  });
  assert.deepEqual(inheritWeek(monthly, "W2").rows, []);
});

test("주간 용지: 양식 순서 · 띠 · 요일 줄, 모르는 칸은 맨 아래", () => {
  const extra = { ...sheet.BLANK_SECTIONS[0], section_key: "zzz_note", label: "메모", order: 0 };
  const sections = [extra, ...[...sheet.BLANK_SECTIONS].reverse()];
  const html = renderToStaticMarkup(
    React.createElement(sheet.default, {
      title: "1주 주간놀이계획안",
      sub: "햇살반",
      start: "2026-11-02",
      end: "2026-11-06",
      days: ["MON", "TUE", "WED", "THU", "FRI"],
      sections,
      at: { selected: null },
    }),
  );
  const heads = [...html.matchAll(/<th[^>]*>([^<]*)<\/th>/g)].map((m) => m[1].trim());
  const order = heads.filter((h) => !["월", "화", "수", "목", "금"].includes(h));
  assert.deepEqual(order, [
    "예상 기간",
    "놀이 주제",
    "소주제",
    "이번 주 목표",
    "[ 이번 주 놀이 ]",
    "실내자유놀이",
    "[ 대·소집단활동 ]",
    "요일",
    "활동",
    "바깥놀이",
    "실내 대체놀이",
    "기본생활습관",
    "안전교육",
    "[ 특별활동 시간표 ]",
    "요일",
    "활동",
    "행사",
    "가정 연계",
    "메모",
  ]);
});

test("다듬기 칸 출처: 교사 수정은 이력으로, 후보를 다시 넣으면 「후보에서 선택」", () => {
  const { originOf } = load("../components/workspace/WeeklyEditor.tsx", {
    react: React,
    ...Object.fromEntries(
      [
        "@/lib/api/client",
        "@/lib/api/plans",
        "@/lib/api/weekly",
        "@/components/plan-generator/PlayCellEditor",
        "@/components/plan-generator/PlayMonthlyConfirm",
        "@/components/plan-generator/UnconfirmButton",
        "@/components/plan-generator/PlayMonthlySafetyPanel",
        "@/components/plan-generator/AnnualFrame",
        "@/components/plan-generator/PlayMonthlySheet",
        "@/components/plan-generator/PlanMemo",
        "@/components/app/compact-shell",
        "./WeeklySheet",
        "./WeeklyIndoorPlayPanel",
      ].map((n) => [n, {}]),
    ),
    "@/lib/weekly/section-labels": weeklyLabels,
  });
  const cell = {
    item_id: "a",
    value: "x",
    teacher_input: false,
    generation: { method: "RULE_ONLY", rule_id: "weekly.activity_copy" },
  };
  assert.equal(originOf(cell, new Set()), "후보에서 선택");
  assert.equal(originOf(cell, new Set(["a"])), "교사 수정");
  assert.equal(originOf({ ...cell, generation: { method: "RULE_LLM" } }, new Set()), "AI 초안");
  assert.equal(originOf({ ...cell, teacher_input: true, value: " " }, new Set()), "");
  assert.equal(originOf({ ...cell, teacher_input: true }, new Set()), "직접 입력");
});
