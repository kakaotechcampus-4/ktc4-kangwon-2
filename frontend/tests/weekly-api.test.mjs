// 주간계획안 API 클라이언트와 MSW 목업 계약 (docs/weekly-plan-contract.md §13).
// 월간과 다른 네 가지만 집중해서 본다 — Gate · 한 Section 한 칸 · 교사 입력 칸 · 토요일.
import { test, before, after, beforeEach, afterEach } from "node:test";
import assert from "node:assert/strict";
import { createRequire, registerHooks } from "node:module";
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
const { setupServer } = await import("msw/node");
const { handlers } = await import("../msw/handlers.ts");
const { resetTestData } = await import("../msw/data/store.ts");
const { putCenterSettings } = await import("../msw/data/centers.ts");
const { approveTemplateForTest } = await import("../msw/data/template-profiles.ts");
const { createTemplateProfile } = await import("../lib/api/templateProfiles.ts");
const { createCenter } = await import("../lib/api/centers.ts");
const { createClass } = await import("../lib/api/classes.ts");
const { createAnnualPlan, confirmAnnualPlan } = await import("../lib/api/plans.ts");
const { createMonthlyPlan, confirmMonthlyPlan, getMonthlyPlan } =
  await import("../lib/api/monthly.ts");
const weekly = await import("../lib/api/weekly.ts");
const { ApiError } = await import("../lib/api/client.ts");
const { SECTION_LABELS, sectionName } = await import("../lib/weekly/section-labels.ts");
const { readFileSync } = await import("node:fs");
const { fileURLToPath: toPath } = await import("node:url");

const ROUTER = toPath(
  new URL("../../backend/app/features/plans/weekly_router.py", import.meta.url),
);
const SCHEMAS = toPath(
  new URL("../../backend/app/features/plans/weekly_schemas.py", import.meta.url),
);

const BASE = {
  template_id: "ssuksak.monthly-template-a",
  template_version: "monthly-template-a-v0.2.1",
};
const PROFILE_INPUT = {
  base_template_ref: BASE,
  selected_optional_keys: ["focus", "goals"],
  display_labels: {
    theme: "주제",
    week_axis: "주",
    outdoor_play: "바깥놀이",
    safety_education: "안전교육",
    focus: "소주제",
    goals: "목표",
  },
  focus_variant: "SUBTHEME",
};

const server = setupServer(...handlers);
let mswFetch;
before(() => {
  server.listen({ onUnhandledRequest: "error" });
  mswFetch = globalThis.fetch;
});
after(() => server.close());
beforeEach(() => {
  resetTestData();
  globalThis.fetch = (url, options) => {
    const u = new URL(url, "http://localhost");
    u.searchParams.set("mockDelay", "0");
    return mswFetch(u.href, options);
  };
});
afterEach(() => {
  globalThis.fetch = mswFetch;
  delete globalThis.window;
});

const rejects = (promise, status, code) =>
  assert.rejects(promise, (e) => {
    assert.ok(e instanceof ApiError);
    assert.equal(e.status, status);
    assert.equal(e.body.error.code, code);
    return true;
  });
const cellOf = (plan, key) => plan.sections.find((s) => s.section_key === key).cells[0];

/** 반 · 연간 확정까지. 월간은 테스트마다 확정할지 말지를 고른다 (G3 를 보기 위해). */
async function classWithMonthly({ confirm = true, saturday = false } = {}) {
  const center = await createCenter({
    name: "검증 원",
    director_name: "원장",
    region_sido: "충청북도",
    region_sigungu: "충주시",
  });
  if (saturday) putCenterSettings(center.id, { weekly_saturday_enabled: true });
  const klass = await createClass(center.id, {
    name: "반",
    teacher_name: "교사",
    age_min: 3,
    age_max: 5,
    child_count: null,
  });
  const annual = await createAnnualPlan({
    class_id: klass.id,
    form_id: null,
    format: "MONTHLY_THEME",
  });
  await confirmAnnualPlan(annual.id);
  approveTemplateForTest(BASE);
  const ref = (await createTemplateProfile(center.id, PROFILE_INPUT)).profile_ref;
  let monthly = await createMonthlyPlan({ class_id: klass.id, month: 3, profile_ref: ref });
  if (confirm) monthly = await confirmMonthlyPlan(monthly.id, monthly.revision);
  return { center, klass, monthly: await getMonthlyPlan(monthly.id) };
}

test("서버에 있는 경로만 쓰고, 아직 없는 경로는 알고 쓴다", () => {
  const router = readFileSync(ROUTER, "utf8");
  // 서버가 지금 내는 경로. 이게 바뀌면 여기가 먼저 깨진다.
  assert.ok(router.includes('@router.post("", response_model=WeeklyPlanOut'));
  assert.ok(router.includes('@router.get("", response_model=WeeklyPlanListOut'));
  assert.ok(router.includes('@router.get("/{plan_id}"'));
  assert.ok(router.includes('@router.delete("/{plan_id}"'));
  // W5b 로 생긴 것. 화면의 「준비 중」 안내는 걷었다.
  assert.ok(router.includes('"/{plan_id}/cells/{item_id}"'), "칸 편집");
  assert.ok(router.includes('"/{plan_id}/cells/{item_id}/regenerate"'), "칸 재생성");
  assert.ok(router.includes('"/{plan_id}/confirm"'), "확정");
});

test("month 는 달력 달 1~12 다 — YYYY-MM 을 보내면 422 다", () => {
  const router = readFileSync(ROUTER, "utf8");
  assert.ok(router.includes("month: int | None = None"));
  assert.ok(router.includes("not 1 <= month <= 12"));
});

test("응답 칸 이름이 화면이 읽는 것과 같다", () => {
  const schemas = readFileSync(SCHEMAS, "utf8");
  for (const field of [
    "week_id",
    "target_month",
    "week_period",
    "operating_days",
    "display_end_date",
    "parent_snapshots",
    "generation",
  ])
    assert.ok(schemas.includes(field + ":"), field);
  // 교사 입력 칸 표시는 서버가 준다 (W5b). 화면은 generation 으로 추론하지 않는다.
  assert.ok(schemas.includes("teacher_input:"), "teacher_input");
});

test("클라이언트는 아홉 가지를 낸다 — 이력 · 한글 파일 포함", () => {
  assert.deepEqual(Object.keys(weekly).sort(), [
    "confirmWeeklyPlan",
    "createWeeklyPlan",
    "deleteWeeklyPlan",
    "downloadWeeklyHwpx",
    "editWeeklyCell",
    "getWeeklyPlan",
    "getWeeklyPlanAudit",
    "listWeeklyPlans",
    "regenerateWeeklyCell",
  ]);
});

test("G3 — 월간이 확정되기 전에는 주간을 만들 수 없다", async () => {
  const { klass, monthly } = await classWithMonthly({ confirm: false });
  await rejects(
    weekly.createWeeklyPlan({ class_id: klass.id, week_id: monthly.weeks[0].week_id }),
    409,
    "GATE_BLOCKED",
  );
});

test("G4 — 월간에 없는 주 주소는 거절한다. 주차를 주간이 다시 세지 않는다", async () => {
  const { klass } = await classWithMonthly();
  await rejects(
    weekly.createWeeklyPlan({ class_id: klass.id, week_id: "2026-03-W9" }),
    422,
    "VALIDATION_FAILED",
  );
});

test("G5 — 같은 반 같은 주는 한 번만 만든다", async () => {
  const { klass, monthly } = await classWithMonthly();
  const weekId = monthly.weeks[0].week_id;
  await weekly.createWeeklyPlan({ class_id: klass.id, week_id: weekId });
  await rejects(
    weekly.createWeeklyPlan({ class_id: klass.id, week_id: weekId }),
    409,
    "ALREADY_EXISTS",
  );
});

test("Section 마다 칸이 하나다 — 주차 열이 없다", async () => {
  const { klass, monthly } = await classWithMonthly();
  const plan = await weekly.createWeeklyPlan({
    class_id: klass.id,
    week_id: monthly.weeks[0].week_id,
  });
  assert.equal(plan.sections.length, 12);
  for (const section of plan.sections) assert.equal(section.cells.length, 1);
  // 주간 칸에는 week_id 가 없다. 계획안 자체가 한 주다.
  assert.ok(plan.sections.every((s) => !("week_id" in s.cells[0])));
});

test("교사 입력 칸 셋은 만들지 않는다 — generation 이 null 이고 다시 만들 수 없다", async () => {
  const { klass, monthly } = await classWithMonthly();
  const plan = await weekly.createWeeklyPlan({
    class_id: klass.id,
    week_id: monthly.weeks[0].week_id,
  });
  // 응답에 teacher_input 같은 칸이 없다. 만든 적이 없으면 generation 이 null 이다 (§10-2).
  for (const key of ["family_link", "event_schedule", "special_program"]) {
    assert.equal(cellOf(plan, key).value, "", key);
    assert.equal(cellOf(plan, key).generation, null, key);
  }
  // 생성한 칸은 반드시 generation 을 들고 온다 — 둘이 섞이면 화면이 못 가른다.
  for (const key of ["theme", "goals", "outdoor_play"]) {
    assert.ok(cellOf(plan, key).generation, key);
  }
  await rejects(
    weekly.regenerateWeeklyCell(plan.id, cellOf(plan, "family_link").item_id, plan.revision),
    422,
    "VALIDATION_FAILED",
  );
});

test("교사가 처음 쓰면 그때 MANUAL 이 된다", async () => {
  const { klass, monthly } = await classWithMonthly();
  const plan = await weekly.createWeeklyPlan({
    class_id: klass.id,
    week_id: monthly.weeks[0].week_id,
  });
  const item = cellOf(plan, "family_link").item_id;
  const next = await weekly.editWeeklyCell(plan.id, item, "금요일 알림장", plan.revision);
  const cell = next.sections.flatMap((s) => s.cells).find((c) => c.item_id === item);
  assert.equal(cell.value, "금요일 알림장");
  assert.equal(cell.generation.method, "MANUAL");
});

test("놀이 주제를 비우면 확정할 수 없다", async () => {
  const { klass, monthly } = await classWithMonthly();
  let plan = await weekly.createWeeklyPlan({
    class_id: klass.id,
    week_id: monthly.weeks[0].week_id,
  });
  plan = await weekly.editWeeklyCell(plan.id, cellOf(plan, "theme").item_id, "", plan.revision);
  await rejects(weekly.confirmWeeklyPlan(plan.id, plan.revision), 422, "VALIDATION_FAILED");
});

test("토요일을 켜면 표시 기간이 하루 늘고 요일이 여섯이다", async () => {
  const { klass, monthly } = await classWithMonthly({ saturday: true });
  const plan = await weekly.createWeeklyPlan({
    class_id: klass.id,
    week_id: monthly.weeks[0].week_id,
  });
  assert.equal(plan.operating_days.length, 6);
  assert.equal(plan.operating_days.at(-1), "SAT");
  // **WeekPeriod 는 늘 금요일이다.** 늘어나는 것은 표시 기간(display_end_date)뿐이다 (§3-2).
  assert.equal(plan.week_period.end_date, monthly.weeks[0].end_date);
  assert.notEqual(plan.display_end_date, plan.week_period.end_date);
});

test("확정하면 고칠 수 없고 지울 수도 없다 — 확정 취소가 없다", async () => {
  const { klass, monthly } = await classWithMonthly();
  let plan = await weekly.createWeeklyPlan({
    class_id: klass.id,
    week_id: monthly.weeks[0].week_id,
  });
  plan = await weekly.confirmWeeklyPlan(plan.id, plan.revision);
  assert.equal(plan.status, "CONFIRMED");
  await rejects(
    weekly.editWeeklyCell(plan.id, cellOf(plan, "goals").item_id, "바뀐 값", plan.revision),
    409,
    "ALREADY_CONFIRMED",
  );
  await rejects(weekly.deleteWeeklyPlan(plan.id), 409, "GATE_BLOCKED");
});

test("칸 이름표는 열두 칸을 모두 덮고, 월간의 옛 키(habits)는 쓰지 않는다", () => {
  assert.equal(Object.keys(SECTION_LABELS).length, 12);
  assert.ok(!("habits" in SECTION_LABELS));
  assert.equal(SECTION_LABELS.basic_habit, "기본생활습관");
  // 모르는 키는 지어내지 않는다 — 서버가 준 이름을 그대로 쓴다.
  assert.equal(sectionName("unknown_key", "서버 이름"), "서버 이름");
  assert.equal(sectionName("unknown_key"), "unknown_key");
});

test("서버 경로가 아직 없으면 「준비 중」으로 읽는다 — 「잠시 후 다시」가 아니다", async () => {
  // 우리가 낸 404 는 공통 봉투를 달고 온다. 아예 없는 경로는 FastAPI 기본 {"detail": ...} 다.
  const enveloped = new ApiError(404, {
    error: { code: "NOT_FOUND", message: "없어요", fields: [] },
  });
  const missingRoute = new ApiError(404, { detail: "Not Found" });
  const notBuiltYet = (e) =>
    e instanceof ApiError &&
    e.status === 404 &&
    !(typeof e.body === "object" && e.body !== null && "error" in e.body);
  assert.equal(notBuiltYet(enveloped), false);
  assert.equal(notBuiltYet(missingRoute), true);
});

// ── 주간 화면 (진짜 컴포넌트) — 저장하지 않은 입력과 기다리는 응답을 지킨다 ──────────────

const W1 = "2026-09-W1";
const W2 = "2026-09-W2";
const pageCode = createRequire(import.meta.url)("next/dist/compiled/babel/core").transformSync(
  readFileSync(new URL("../components/workspace/WeeklyPlanPage.tsx", import.meta.url), "utf8"),
  {
    filename: "WeeklyPlanPage.tsx",
    babelrc: false,
    configFile: false,
    presets: ["preset-env", "preset-react", "preset-typescript"].map((name) => {
      const preset = createRequire(import.meta.url)(`next/dist/compiled/babel/${name}`);
      if (name === "preset-env") return [preset, { targets: { node: "current" } }];
      return name === "preset-react" ? [preset, { runtime: "automatic" }] : preset;
    }),
  },
).code;

/** 훅 자리가 고정인 화면 하나를 그리는 React 흉내. 서버는 `api` 로 갈아 끼운다. */
function weeklyPage(api) {
  const slots = [];
  let cursor = 0;
  let queued = [];
  let tree = null;
  const same = (a, b) => !!a && a.length === b.length && a.every((v, i) => Object.is(v, b[i]));
  const useState = (init) => {
    const i = cursor++;
    slots[i] ??= { v: typeof init === "function" ? init() : init };
    return [
      slots[i].v,
      (next) => (slots[i].v = typeof next === "function" ? next(slots[i].v) : next),
    ];
  };
  const memo = (fn, deps) => {
    const i = cursor++;
    if (!slots[i] || !same(slots[i].deps, deps)) slots[i] = { v: fn(), deps };
    return slots[i].v;
  };
  const useEffect = (fn, deps) => {
    const i = cursor++;
    if (slots[i] && same(slots[i].deps, deps)) return;
    const old = slots[i];
    slots[i] = { deps, cleanup: old?.cleanup };
    queued.push(() => {
      slots[i].cleanup?.();
      slots[i].cleanup = fn();
    });
  };
  const node = (type, props) => (typeof type === "function" ? type(props) : { type, props });
  const css = new Proxy({}, { get: (_, k) => String(k) });
  const modules = {
    react: { useState, useMemo: memo, useEffect, useCallback: (fn, deps) => memo(() => fn, deps) },
    "react/jsx-runtime": { jsx: node, jsxs: node, Fragment: "fragment" },
    "@/lib/api/client": { ApiError },
    "@/lib/api/monthly": {
      listMonthlyPlans: async () => ({ items: [{ id: 20, month: 9, status: "CONFIRMED" }] }),
      getMonthlyPlan: async () => ({
        id: 20,
        weeks: [W1, W2].map((week_id, i) => ({
          week_id,
          label: `${i + 1}주`,
          start_date: "2026-09-07",
          end_date: "2026-09-11",
          active: true,
        })),
      }),
    },
    "@/lib/api/onboarding": { classServerId: () => 1, syncClass: async () => 1 },
    "@/lib/api/weekly": { getWeeklyPlanAudit: async () => ({ items: [] }), ...api },
    "@/lib/hooks/use-hwpx-download": {
      useHwpxDownload: () => ({ exporting: false, download: async () => {} }),
    },
    "@/lib/onboarding/settings": {
      loadClassSettings: () => ({ classes: [{ id: "local", className: "반" }] }),
      primaryClassFor: (s) => s.classes[0],
    },
    "@/lib/hooks/use-client-state": { useClientState: (read) => useState(read) },
    "@/lib/workspace/document-archive": {
      archivePlanEntry: () => ({ id: 11, classId: 1, month: 9, weekId: W1 }),
    },
    "@/lib/weekly/section-labels": { DAY_NAMES: {}, sectionName: (key) => key },
    "./WorkspaceUI": {
      WorkspacePage: (p) => node("page", p),
      Empty: (p) => node("empty", p),
      Message: (p) => node("message", p),
    },
    "./WeeklyPlanPage.module.css": css,
  };
  const page = { exports: {} };
  new Function("require", "module", "exports", pageCode)(
    (name) => {
      assert.ok(name in modules, `unhandled import: ${name}`);
      return modules[name];
    },
    page,
    page.exports,
  );
  const all = (n) =>
    Array.isArray(n)
      ? n.flatMap(all)
      : n && typeof n === "object"
        ? [n, ...all(n.props?.children)]
        : [];
  const text = (n) =>
    Array.isArray(n)
      ? n.map(text).join("")
      : n && typeof n === "object"
        ? text(n.props?.children)
        : n == null || typeof n === "boolean"
          ? ""
          : String(n);
  const view = {
    async settle() {
      for (let i = 0; i < 12; i++) {
        cursor = 0;
        tree = page.exports.default();
        const run = queued;
        queued = [];
        run.forEach((fn) => fn());
        await new Promise(setImmediate);
      }
      cursor = 0;
      tree = page.exports.default();
    },
    all: () => all(tree),
    button: (label, scope = tree) =>
      all(scope).find((n) => n.type === "button" && text(n).startsWith(label)),
    card: (key) =>
      all(tree).find(
        (n) => n.type === "article" && all(n).some((h) => h.type === "h4" && text(h) === key),
      ),
    editor: () => all(tree).find((n) => n.type === "textarea"),
  };
  return view;
}

const draftPlan = (week_id = W1) => ({
  id: 11,
  class_id: 1,
  school_year: 2026,
  week_id,
  status: "DRAFT",
  revision: 1,
  week_period: { start_date: "2026-09-07", end_date: "2026-09-11" },
  display_end_date: "2026-09-11",
  operating_days: ["MON"],
  parent: { theme: "" },
  verification: { findings: [] },
  sections: ["theme", "focus"].map((key) => ({
    section_key: key,
    label: key,
    visible: true,
    cells: [
      {
        item_id: `${key}-1`,
        value: "A",
        state: "FILLED",
        teacher_input: false,
        evidence: [],
        parent_snapshots: [],
        generation: { method: "RULE_LLM" },
      },
    ],
  })),
});

test("화면 — 저장이 실패하면 쓴 문장과 편집창을 그대로 두고, 저장하지 않은 채로는 확정·이동하지 않는다", async () => {
  let fail = true;
  const edits = [];
  const view = weeklyPage({
    listWeeklyPlans: async () => ({ items: [draftPlan()] }),
    getWeeklyPlan: async () => draftPlan(),
    editWeeklyCell: async (...args) => {
      edits.push(args);
      if (fail) throw new Error("저장 실패");
      return { ...draftPlan(), revision: 2 };
    },
  });
  await view.settle();
  view.button("고치기", view.card("focus")).props.onClick();
  await view.settle();
  view.editor().props.onChange({ target: { value: "B" } });
  await view.settle();

  // 열린 편집이 있으면 확정 · 지우기 · 다른 칸 · 주/월 이동을 시작하지 않는다 (WUI-A02).
  for (const label of ["확정하기", "초안 지우기", "1주", "2주"])
    assert.equal(view.button(label).props.disabled, true, label);
  assert.equal(view.button("고치기", view.card("theme")).props.disabled, true);
  assert.equal(view.all().find((n) => n.type === "select").props.disabled, true);

  await view.button("저장").props.onClick();
  await view.settle();
  assert.equal(edits.length, 1);
  assert.equal(view.editor()?.props.value, "B", "실패한 입력이 남아 있어야 한다 (WUI-A01)");

  fail = false;
  await view.button("저장").props.onClick();
  await view.settle();
  assert.equal(edits[1][2], "B");
  assert.equal(view.editor(), undefined, "성공한 뒤에만 닫는다");
  assert.equal(view.button("확정하기").props.disabled, false);
});

test("화면 — 만드는 응답을 기다리는 동안 다른 주로 옮기지 않는다", async () => {
  const view = weeklyPage({
    listWeeklyPlans: async () => ({ items: [] }),
    createWeeklyPlan: () => new Promise(() => {}),
  });
  await view.settle();
  view.button("이 주 계획안 만들기").props.onClick();
  await view.settle();
  assert.equal(
    view.button("2주").props.disabled,
    true,
    "늦은 1주 응답이 2주 화면에 붙는다 (WUI-A03)",
  );
});
