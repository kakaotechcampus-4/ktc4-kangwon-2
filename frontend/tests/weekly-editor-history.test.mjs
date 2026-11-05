import assert from "node:assert/strict";
import { test } from "node:test";
import { createRequire } from "node:module";
import { readFileSync } from "node:fs";
const require = createRequire(import.meta.url);
const jsx = (type, props, key) => ({ type, props, key });
const all = (n) =>
  Array.isArray(n)
    ? n.flatMap(all)
    : n && typeof n === "object"
      ? [n, ...all(n.props?.children)]
      : [];
const content = (n) =>
  Array.isArray(n)
    ? n.map(content).join("")
    : n && typeof n === "object"
      ? content(n.props?.children)
      : typeof n === "string"
        ? n
        : "";
const resolve = (n) =>
  Array.isArray(n)
    ? n.map(resolve)
    : n && typeof n === "object"
      ? typeof n.type === "function"
        ? resolve(n.type(n.props))
        : { ...n, props: { ...n.props, children: resolve(n.props?.children) } }
      : n;
const tick = () => new Promise((r) => setTimeout(r, 0));
const es = (fn) => ({ __esModule: true, default: fn });
function compile(path, modules) {
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
  new Function("require", "module", "exports", code)(
    (name) => {
      if (name === "react/jsx-runtime") return { jsx, jsxs: jsx, Fragment: "fragment" };
      assert.ok(name in modules, name);
      return modules[name];
    },
    m,
    m.exports,
  );
  return m.exports;
}
test("removing an edited indoor play drops its undo steps, so confirm still goes through", async () => {
  let cursor = 0,
    effects = [],
    slots = [];
  const react = {
    useState(init) {
      const k = cursor++;
      if (!(k in slots)) slots[k] = typeof init === "function" ? init() : init;
      return [slots[k], (v) => (slots[k] = typeof v === "function" ? v(slots[k]) : v)];
    },
    useRef(init) {
      const k = cursor++;
      return (slots[k] ??= { current: init });
    },
    useEffect(fn) {
      effects.push(fn);
    },
  };
  const cell = (id, value) => ({
    item_id: id,
    value,
    day: null,
    teacher_input: false,
    generation: null,
  });
  let plan = {
    id: 1,
    revision: 1,
    status: "DRAFT",
    target_month: "2026-03",
    week_period: { label: "1주", start_date: "2026-03-02" },
    display_end_date: "2026-03-06",
    operating_days: ["MON", "TUE", "WED", "THU", "FRI"],
    indoor_play_selection: true,
    activity_grids: [],
    activity_candidates: [
      {
        section_key: "indoor_play",
        activity_type: "쌓기",
        name: "A",
        description: "블록으로 탑을 쌓아요.",
        cell: cell("k1", "A: 블록으로 탑을 쌓아요."),
      },
    ],
    // 서버 문구(영어)는 띄우지 않는다 — AI 칸마다 오는 같은 안내는 한 줄, 직접 쓴 바깥놀이 안내는 뺀다.
    verification: {
      findings: [
        { code: "WEEKLY_FACT_SCOPE_NOT_VERIFIED", message: "Dates, weekdays" },
        { code: "WEEKLY_FACT_SCOPE_NOT_VERIFIED", message: "Dates, weekdays" },
        { code: "ACTIVITY_FREE_TEXT_AGE_NOT_VERIFIED", message: "Free-text outdoor play" },
        { code: "WEEKLY_SAFETY_PARENT_CITATION_INVALID", message: "Safety citation" },
      ],
    },
    sections: [
      {
        section_key: "theme",
        label: "주제",
        visible: true,
        repeat_by: "NONE",
        cells: [cell("theme", "주제")],
      },
      {
        section_key: "indoor_play",
        label: "자유놀이",
        visible: true,
        repeat_by: "NONE",
        cells: [cell("i1", "[쌓기] - A"), cell("i2", "다른 놀이")],
      },
    ],
  };
  const edits = [];
  let confirms = 0;
  const api = {
    getWeeklyPlanAudit: async () => ({ items: [] }),
    editWeeklyCell: async (id, itemId, value) => {
      edits.push([itemId, value]);
      if (!plan.sections.flatMap((s) => s.cells).some((c) => c.item_id === itemId))
        throw { status: 404 };
      plan = {
        ...plan,
        revision: plan.revision + 1,
        sections: plan.sections.map((s) => ({
          ...s,
          cells: s.cells.map((c) => (c.item_id === itemId ? { ...c, value } : c)),
        })),
      };
      return plan;
    },
    removeWeeklyIndoorPlay: async (id, itemId) =>
      (plan = {
        ...plan,
        revision: plan.revision + 1,
        sections: plan.sections.map((s) => ({
          ...s,
          cells: s.cells.filter((c) => c.item_id !== itemId),
        })),
      }),
    confirmWeeklyPlan: async () => {
      confirms++;
      return { ...plan, status: "CONFIRMED" };
    },
  };
  const frame = {
    __esModule: true,
    default: (p) =>
      jsx("frame", { children: [p.aside, p.docHint, p.actions, p.notice, p.children] }),
    useSheetZoom: () => ({ percent: 100 }),
    UndoRedo: (p) => jsx("history", p),
    BigView: () => null,
    PlanDone: () => null,
    BUTTON: {},
    tabClass: () => "",
    BACK_BUTTON: "",
    BACK_ICON: null,
  };
  const mods = {
    react,
    "@/lib/api/client": { ApiError: class extends Error {} },
    "@/lib/api/plans": { isSaveConflict: (e) => e.status === 409 },
    "@/lib/api/weekly": api,
    "@/lib/weekly/section-labels": { DAY_NAMES: {}, sectionName: (k) => k },
    "@/lib/monthly/findings": compile("../lib/monthly/findings.ts", {}),
    "@/components/plan-generator/PlayCellEditor": es((p) => jsx("editor", p)),
    "@/components/plan-generator/PlayMonthlyConfirm": {
      ...es((p) => jsx("ask", p)),
      BLANK_LEAD: "",
      BlankRows: () => null,
      PanelOverview: () => null,
    },
    "@/components/plan-generator/UnconfirmButton": es(() => null),
    "@/components/plan-generator/PlayMonthlySafetyPanel": {},
    "@/components/plan-generator/AnnualFrame": frame,
    "@/components/plan-generator/PlayMonthlySheet": { PAPER_WIDTH: 853 },
    "@/components/app/compact-shell": { useCompactShell() {} },
    "./useCellHistory": compile("../components/workspace/useCellHistory.ts", { react }),
    "./WeeklySheet": es((p) => jsx("sheet", p)),
    "./WeeklyIndoorPlayPanel": es((p) => jsx("indoor", p)),
    "./Workspace.module.css": es({}),
    "@/components/plan-generator/PlanMemo": { PlanMemoNote: () => null },
  };
  const C = compile("../components/workspace/WeeklyEditor.tsx", mods).default;
  const render = () => {
    cursor = 0;
    effects = [];
    const tree = resolve(
      C({ plan, onPlan: (p) => (plan = p), onConflict() {}, onBack() {}, className: "" }),
    );
    effects.forEach((fn) => fn());
    return tree;
  };
  globalThis.window = { addEventListener() {}, removeEventListener() {} };
  globalThis.document = { activeElement: null };
  const notes = all(render())
    .filter((n) => n.type === "li")
    .map(content);
  assert.equal(notes.length, 1);
  assert.match(notes[0], /안전교육 칸이 월간계획안의 안전교육과/); // 사실 범위 · 직접 쓴 바깥놀이 안내는 띄우지 않는다
  all(render())
    .find((n) => n.type === "sheet")
    .props.at.onSelect("i1");
  all(render())
    .find((n) => n.type === "button" && content(n) === "칸 편집")
    .props.onClick();
  // 넣은 후보의 설명은 「칸 편집」에서 읽기만 한다(ADR-054 · 후보 목록에서는 숨긴다).
  assert.ok(all(render()).some((n) => n.type === "p" && content(n) === "블록으로 탑을 쌓아요."));
  all(render())
    .find((n) => n.type === "editor")
    .props.onSave("B");
  await tick();
  all(render())
    .find((n) => n.type === "button" && content(n) === "AI 후보")
    .props.onClick();
  all(render())
    .find((n) => n.type === "indoor")
    .props.onRemove("i1");
  await tick();
  assert.equal(
    plan.sections[1].cells.some((c) => c.item_id === "i1"),
    false,
  );
  // 빼도 「AI 후보」 화면 그대로 — 옆 줄을 고른다.
  assert.equal(all(render()).find((n) => n.type === "indoor").props.selected, "i2");
  // 뺀 칸의 걸음은 지워져 되돌릴 것이 없고, 없는 칸에 저장을 보내지 않는다.
  assert.equal(all(render()).find((n) => n.type === "history").props.canUndo, false);
  all(render())
    .find((n) => n.type === "button" && content(n) === "확정하기")
    .props.onClick();
  all(render())
    .find((n) => n.type === "ask")
    .props.onYes();
  await tick();
  await tick();
  assert.deepEqual(edits, [["i1", "B"]]);
  assert.equal(confirms, 1);
});
