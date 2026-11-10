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
  "@/components/plan-generator/PlayMonthlySafetyPanel": { DROP: "" },
  "@/components/plan-generator/PlayMonthlySheet": {
    Cell: ({ id, value, strong }) =>
      React.createElement("span", { "data-cell": id, "data-strong": strong || undefined }, value),
    HEAD: "",
    LINE: "",
    hu: (n) => n,
    Paper,
    TEACHER_HINT: "",
    period: () => "기간",
  },
});
const MONTH_ORDER = [3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 1, 2];
const WEEKLY_NEW = {
  react: React,
  "next/link": { __esModule: true, default: stub },
  "@/lib/api/client": { ApiError: class {} },
  "@/lib/api/conflict": {},
  "@/lib/api/monthly": {},
  "@/lib/api/plans": {},
  "@/lib/api/weekly": {},
  "@/lib/api/trends": {},
  "@/lib/api/generationRuns": { newRunId: () => "run-1" },
  "@/lib/api/onboarding": {},
  "@/lib/monthly/play-entry": {},
  "@/lib/monthly/section-labels": monthlyLabels,
  "@/lib/onboarding/settings": {},
  "@/lib/onboarding/types": { MONTH_ORDER, planClassLine: (c) => c.className },
  "@/lib/hooks/use-client-state": {},
  "@/components/plan-ui/GenerationRing": {
    __esModule: true,
    default: stub,
    ringFinished: async () => {},
  },
  "@/components/plan-generator/PlanMemo": { PlanMemoField: stub, memoError: stub },
  "@/components/app/compact-shell": {},
  "./WorkspaceUI": {},
  "@/components/plan-generator/AnnualFrame": { BACK_BUTTON: "back", BACK_ICON: null },
  "./WeeklySheet": sheet,
};
const { firstWeeklyMonth, firstOpenWeek, inheritWeek } = load(
  "../components/workspace/WeeklyNew.tsx",
  WEEKLY_NEW,
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
      sec("safety_education", "WEEK", [{ week_id: "W1", value: "" }], 3),
    ],
    safety_weeks: [{ week_id: "W1", display_value: "[교통안전] 횡단보도를 건너요" }],
  };
  assert.deepEqual(inheritWeek(monthly, "W1"), {
    theme: "가을",
    rows: [
      { name: monthlyLabels.sectionName("outdoor_play"), value: "모래놀이" },
      {
        name: monthlyLabels.sectionName("safety_education"),
        value: "[교통안전] 횡단보도를 건너요",
      },
    ],
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
        "@/lib/monthly/findings",
        "@/components/plan-generator/PlayCellEditor",
        "@/components/plan-generator/PlayMonthlyConfirm",
        "@/components/plan-ui/DraftSave",
        "@/components/plan-generator/UnconfirmButton",
        "@/components/plan-generator/PlayMonthlySafetyPanel",
        "@/components/plan-generator/AnnualFrame",
        "@/components/plan-generator/PlayMonthlySheet",
        "@/components/plan-generator/PlanMemo",
        "@/components/app/compact-shell",
        "./WeeklySheet",
        "./WeeklyGroupActivityPanel",
        "./WeeklyIndoorPlayPanel",
        "./Workspace.module.css",
        "./useCellHistory",
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

test("주간 용지: 칸 둘레의 빈 곳을 눌러도 그 칸을 고른다 — 글 위 클릭은 칸이 받는다", () => {
  const cell = (item_id, day = null) => ({ item_id, value: "x", day, teacher_input: false });
  const sections = sheet.BLANK_SECTIONS.map((s) =>
    s.section_key === "theme"
      ? { ...s, cells: [cell("theme")] }
      : s.section_key === "group_activity"
        ? { ...s, cells: [cell("mon", "MON"), cell("tue", "TUE")] }
        : s,
  );
  const picked = [];
  const tree = sheet.default({
    title: "",
    sub: "",
    start: "",
    end: "",
    days: ["MON", "TUE"],
    sections,
    grids: [
      { cell_id: "mon", children: [] },
      {
        split_id: "s",
        axis: "VERTICAL",
        children: [
          { cell_id: "tue", children: [] },
          { cell_id: "tue2", children: [] },
        ],
      },
    ],
    at: { selected: null, onSelect: (id) => picked.push(id) },
  });
  const all = (n) =>
    Array.isArray(n)
      ? n.flatMap(all)
      : n && typeof n === "object"
        ? [n, ...all(n.props?.children)]
        : [];
  const areas = all(tree).filter((n) => n.props?.["data-area"]);
  for (const n of areas) {
    const self = {};
    n.props.onClick({ target: self, currentTarget: self });
    n.props.onClick({ target: {}, currentTarget: self }); // 안쪽 글 클릭은 넘긴다
  }
  assert.deepEqual(picked.sort(), ["mon", "theme", "tue", "tue2"]);
});

test("주간 용지: 활동 후보를 대·소집단활동 칸에 놓으면 그 칸(나눈 칸은 그 조각)에 넣고, 안전교육은 [주제]를 굵게 한 줄에", () => {
  const cell = (item_id, day = null, value = "x") => ({
    item_id,
    value,
    day,
    teacher_input: false,
  });
  const sections = sheet.BLANK_SECTIONS.map((s) =>
    s.section_key === "group_activity"
      ? {
          ...s,
          cells: [cell("mon", "MON", "[게임] 짝 찾기"), cell("tue", "TUE"), cell("tue2", "TUE")],
        }
      : s.section_key === "safety_education"
        ? { ...s, cells: [cell("safe", null, "[교통안전] - 신호등을 봐요")] }
        : s,
  );
  const put = [];
  const props = {
    title: "",
    sub: "",
    start: "",
    end: "",
    days: ["MON", "TUE"],
    sections,
    at: { selected: null },
    onPut: (cellId, id) => put.push([cellId, id]),
  };
  const all = (n) =>
    Array.isArray(n)
      ? n.flatMap(all)
      : n && typeof n === "object"
        ? [n, ...all(n.props?.children)]
        : [];
  const tds = all(sheet.default(props)).filter((n) => n.props?.onDrop);
  assert.equal(tds.length, 2); // 대·소집단활동 요일 칸만 받는다
  const drop = (td, data, hit) =>
    td.props.onDrop({
      preventDefault() {},
      currentTarget: { dataset: {} },
      target: { closest: () => hit },
      dataTransfer: { getData: () => data },
    });
  drop(tds[0], "weekly-activity:c1", null); // 칸 하나뿐인 날 — 빈 곳에 놓아도 그 칸
  drop(tds[1], "weekly-activity:c2", { dataset: { cell: "tue2" } }); // 나눈 날 — 놓은 조각
  drop(tds[1], "weekly-activity:c3", null); // 나눈 날 빈 곳 — 넣지 않는다
  drop(tds[0], "safety-candidate:s1", null); // 다른 끌기는 받지 않는다
  assert.deepEqual(put, [
    ["mon", "c1"],
    ["tue2", "c2"],
  ]);
  const html = renderToStaticMarkup(React.createElement(sheet.default, props));
  // 안전교육은 「[주제] 문장」 한 줄, 넣은 활동은 가운데에 「[종류]」 밑에 이름(PM 2026-11-06).
  assert.match(html, /data-cell="safe" data-strong="true">\[교통안전\] 신호등을 봐요/);
  assert.match(html, /text-center"><div><span data-cell="mon">\[게임\]\n짝 찾기/);
  const still = all(sheet.default({ ...props, onPut: undefined })).filter((n) => n.props?.onDrop);
  assert.equal(still.length, 0); // 확정 · 저장 중에는 받지 않는다
});

/** 화면 함수를 hook 칸 · 의존 값이 바뀌면 다시 도는 effect 로 그린다. 함수 컴포넌트는 펼치지 않는다. */
function fakeReact() {
  const slots = [];
  const effects = [];
  let cursor = 0;
  const state = (initial) => {
    const i = cursor++;
    slots[i] ??= [
      typeof initial === "function" ? initial() : initial,
      (next) => (slots[i][0] = typeof next === "function" ? next(slots[i][0]) : next),
    ];
    return [slots[i][0], slots[i][1]];
  };
  const useEffect = (fn, deps) => {
    const i = cursor++;
    const prev = effects[i];
    if (prev && deps.every((d, k) => Object.is(d, prev.deps[k]))) return;
    prev?.cleanup?.();
    effects[i] = { deps, cleanup: fn() };
  };
  const jsx = (type, props, key) => ({ type, props, key });
  return {
    react: { useState: state, useRef: (v) => state(() => ({ current: v }))[0], useEffect },
    runtime: { jsx, jsxs: jsx, Fragment: "fragment" },
    render: (fn) => ((cursor = 0), fn()),
    cleanup: () => effects.forEach((e) => e?.cleanup?.()),
  };
}
const nodes = (n) =>
  Array.isArray(n)
    ? n.flatMap(nodes)
    : n && typeof n === "object"
      ? [n, ...nodes(n.props?.children)]
      : [];
const drain = async () => {
  for (let i = 0; i < 20; i++) await new Promise((r) => setImmediate(r));
};

test("만들기: 생성 POST 의 X-Generation-Run-Id 와 링의 runId 가 같은 값이다", async (t) => {
  const fake = fakeReact();
  const sent = [];
  const apiRequest = (path, init) => {
    sent.push({ path, init });
    return new Promise(() => {}); // 만드는 중에 멈춰 둔다 — 링이 떠 있다
  };
  const runs = load("../lib/api/generationRuns.ts", { "./client": { apiRequest } });
  const weeklyApi = load("../lib/api/weekly.ts", {
    "./client": { apiRequest },
    "./export": {},
    "./generationRuns": runs,
  });
  const week = { week_id: "W1", label: "11월 1주", active: true, start_date: "", end_date: "" };
  const classes = [{ id: "c1", className: "햇살반" }];
  const { default: WeeklyNew } = load("../components/workspace/WeeklyNew.tsx", {
    ...WEEKLY_NEW,
    react: fake.react,
    "react/jsx-runtime": fake.runtime,
    "@/lib/api/generationRuns": { ...runs, newRunId: () => "run-1" },
    "@/lib/api/weekly": { ...weeklyApi, listWeeklyPlans: async () => ({ items: [] }) },
    "@/lib/api/monthly": {
      listMonthlyPlans: async () => ({ items: [{ id: 5, month: 11, status: "CONFIRMED" }] }),
      getMonthlyPlan: async () => ({ weeks: [week], sections: [] }),
    },
    "@/lib/api/plans": { listAnnualPlans: async () => ({ items: [] }) },
    "@/lib/api/onboarding": { syncClass: async () => 31 },
    "@/lib/api/trends": { topicMemo: () => "" },
    "@/lib/monthly/play-entry": { isPlayAnnual: () => false },
    "@/lib/onboarding/settings": { loadClassSettings: () => ({}), chosenClassFor: () => null },
    "@/lib/hooks/use-client-state": { useClientState: (_read, fallback) => [fallback, stub] },
    "@/components/plan-ui/GenerationRing": { __esModule: true, default: "generation-ring" },
    "@/components/app/compact-shell": { useCompactShell: stub },
    "./WorkspaceUI": { Tape: stub, useClasses: () => classes },
  });
  globalThis.window = { location: { search: "?month=11" } };
  t.after(() => {
    fake.cleanup();
    delete globalThis.window;
  });
  const render = () => nodes(fake.render(() => WeeklyNew({ onOpen: stub })));
  render();
  await drain(); // 반 · 월간 목록
  render();
  await drain(); // 고른 달의 월간 · 주간 목록
  const label = "11월 1주 주간계획안 만들기";
  render()
    .find((n) => n.type === "button" && n.props.children === label)
    .props.onClick();
  await drain();

  const post = sent.find((s) => s.path === "/api/plans/weekly" && s.init.method === "POST");
  assert.equal(new Headers(post.init.headers).get("X-Generation-Run-Id"), "run-1");
  assert.equal(render().find((n) => n.type === "generation-ring").props.runId, "run-1");
});
