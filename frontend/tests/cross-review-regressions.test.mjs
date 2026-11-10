import assert from "node:assert/strict";
import { test } from "node:test";
import { createRequire } from "node:module";
import { readFileSync } from "node:fs";
const require = createRequire(import.meta.url);
const jsx = (type, props) => ({ type, props });
const runtime = { jsx, jsxs: jsx, Fragment: "fragment" };
const settle = () => new Promise((done) => setImmediate(done));
const walk = (node) => {
  if (Array.isArray(node)) return node.flatMap(walk);
  if (node == null || typeof node === "boolean") return [];
  return typeof node === "object" ? [node, ...walk(node.props?.children)] : [node];
};
const text = (node) =>
  walk(node)
    .filter((n) => typeof n === "string")
    .join(" ");
function harness(path, imports, extra = "") {
  const slots = [],
    pending = [];
  let cursor = 0;
  const react = {
    useState(initial) {
      const n = cursor++;
      if (!(n in slots)) slots[n] = typeof initial === "function" ? initial() : initial;
      return [
        slots[n],
        (next) => {
          slots[n] = typeof next === "function" ? next(slots[n]) : next;
        },
      ];
    },
    useEffect(fn, deps) {
      const n = cursor++,
        previous = slots[n];
      if (!previous || deps.some((d, i) => d !== previous.deps[i])) {
        previous?.cleanup?.();
        slots[n] = { deps };
        pending.push(() => {
          slots[n].cleanup = fn();
        });
      }
    },
    useMemo: (fn) => fn(),
    useCallback(fn, deps) {
      const n = cursor++,
        previous = slots[n];
      if (!previous || deps.some((d, i) => d !== previous.deps[i])) slots[n] = { fn, deps };
      return slots[n].fn;
    },
    useRef(value) {
      const n = cursor++;
      return slots[n] ?? (slots[n] = { current: value });
    },
  };
  function compile(path, extra = "") {
    const code = require("next/dist/compiled/babel/core").transformSync(
      readFileSync(new URL(path, import.meta.url), "utf8") + extra,
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
    const modules = { react, "react/jsx-runtime": runtime, ...imports };
    const cjs = { exports: {} };
    new Function("require", "module", "exports", code)(
      (id) => {
        if (id === "./use-journal-editor")
          return compile("../components/workspace/use-journal-editor.ts");
        if (id === "@/lib/hooks/use-unsaved-warning") return { useUnsavedWarning() {} };
        assert.ok(id in modules, id);
        return modules[id];
      },
      cjs,
      cjs.exports,
    );
    return cjs.exports;
  }
  const exports = compile(path, extra);
  return {
    exports,
    render(fn = exports.default, props = {}) {
      cursor = 0;
      const tree = fn(props);
      pending.splice(0).forEach((f) => f());
      return tree;
    },
  };
}

test("#373: 미저장 일지 이동 취소·저장 중 이동 차단·저장 후 이동을 구분한다", () => {
  const before = globalThis.window;
  let accepted = false,
    asks = 0;
  globalThis.window = {
    confirm() {
      asks++;
      return accepted;
    },
  };
  try {
    const h = harness("../components/workspace/use-journal-editor.ts", {});
    const read = (scope = "class-a|2026-03-02", busy = false) =>
      h.render(() => h.exports.useJournalEditor(scope, busy));
    let state = read();
    state.open("doc-a");
    state = read();
    state.onEditStateChange({ dirty: true, pending: false });
    state = read();
    assert.equal(state.leave(), false);
    assert.equal(read().openId, "doc-a");
    state.onEditStateChange({ dirty: true, pending: true });
    state = read();
    assert.equal(state.leave(), false);
    assert.equal(asks, 1, "저장 중이면 버리기 확인도 열지 않는다");
    assert.equal(read("class-a|2026-03-02", true).leave(), false);
    state.onEditStateChange({ dirty: false, pending: false });
    state = read();
    assert.equal(state.leave(), true);
    assert.equal(read().openId, "");
    state.open("doc-b");
    state = read();
    state.onEditStateChange({ dirty: true, pending: false });
    state = read();
    accepted = true;
    assert.equal(state.close(), true);
    assert.equal(read().openId, "");
    state.open("doc-c");
    state = read();
    state.onEditStateChange({ dirty: true, pending: true });
    state = read();
    state.dismiss();
    assert.equal(read().openId, "", "삭제 완료는 저장 잠금과 관계없이 닫는다");
  } finally {
    globalThis.window = before;
  }
});

test("#392: 아이·기간·근거는 생성 완료까지 잠기고 올바른 문서를 연다", async () => {
  let resolve, sent;
  const response = new Promise((done) => {
    resolve = done;
  });
  const classes = [
    {
      id: "class-a",
      children: [
        { id: "a", name: "fixture-A" },
        { id: "b", name: "fixture-B" },
      ],
    },
  ];
  const h = harness("../components/workspace/ObservationJournalPage.tsx", {
    "next/link": { __esModule: true, default: "link" },
    "@/lib/workspace/model": { today: () => "2026-03-02", validDate: () => true },
    "@/lib/api/records": {
      listRecords: async () => [
        {
          id: "source-a",
          childId: "a",
          classId: "class-a",
          date: "2026-03-02",
          domain: "fixture",
          fact: "fixture",
        },
      ],
    },
    "@/lib/api/documents": {
      listDocuments: async () => [],
      createDocument: (input) => {
        sent = input;
        return response;
      },
    },
    "@/lib/api/onboarding": { classServerId: () => 1 },
    "@/lib/hooks/use-client-state": {
      useClientState: (_read, fallback) => [fallback === "" ? "class-a" : fallback],
    },
    "@/lib/onboarding/settings": {
      chosenClassFor: () => classes[0],
      loadClassSettings: () => ({}),
    },
    "@/lib/workspace/child-mark": { markFor: () => ({}), weekStart: (d) => d },
    "@/components/app/ChildPicker": { ChildNote: "child-note" },
    "@/components/app/Posty": { Posty: "posty" },
    "./WorkspaceUI": {
      WorkspacePage: "workspace",
      Empty: "empty",
      Message: "message",
      useClasses: () => classes,
      ws: {},
    },
    "./ObservationJournalEditor": { __esModule: true, default: "journal" },
    "@/lib/hooks/use-observation-domains": { useObservationDomains: () => [] },
    "./use-server-document": { useServerDocument: () => ({}) },
    "./RecordsPage": { openPicker() {} },
    "./ObservationClassDrafts": { __esModule: true, default: "class-drafts" },
    "./ObservationJournal.module.css": { __esModule: true, default: {} },
  });
  let tree = h.render();
  await settle();
  tree = h.render();
  h.render();
  const pick = (tree, name) =>
    walk(tree).find((n) => n?.type === "button" && text(n).includes(name));
  pick(tree, "fixture-A").props.onClick();
  tree = h.render();
  const making = pick(tree, "초안 만들기").props.onClick();
  tree = h.render();
  assert.equal(sent.childId, "a");
  assert.equal(pick(tree, "fixture-B").props.disabled, true);
  for (const input of walk(tree).filter((n) => n?.type === "input"))
    assert.equal(input.props.disabled, true);
  resolve({ id: "doc-for-a" });
  await making;
  tree = h.render();
  const editor = walk(tree).find(
    (n) => typeof n?.type === "function" && n.type.name === "JournalEditor",
  );
  assert.equal(editor.props.id, "doc-for-a");
});

test("#416: 검색 실패는 빈 결과와 구분하고 같은 조건으로 재시도한다", async () => {
  const before = globalThis.window,
    timers = [];
  globalThis.window = {
    setTimeout: (fn) => {
      timers.push(fn);
      return 1;
    },
    clearTimeout() {},
  };
  try {
    const settings = {
      orgName: "",
      directorName: "",
      regionProvince: "fixture-province",
      regionDistrict: "fixture-district",
    };
    const parts = Object.fromEntries(
      [
        "AnsweredList",
        "Cascade",
        "CtaButton",
        "ErrorLine",
        "FieldHint",
        "FieldLabel",
        "LineField",
        "LoadingLine",
        "PickButton",
        "Question",
      ].map((k) => [k, k]),
    );
    const calls = [];
    let failing = true;
    const h = harness("../components/onboarding/CenterFlow.tsx", {
      "next/navigation": { useRouter: () => ({ push() {} }) },
      "./OnboardingLayout": { __esModule: true, default: "layout" },
      "./RegionSheet": { __esModule: true, default: "regions" },
      "./FlowParts": { ...parts, onEnter() {} },
      "./useOnboardingData": {
        useOnboardingData: () => ({ settings, ready: true, edit() {}, error: "", setError() {} }),
      },
      "@/lib/onboarding/settings": { saveClassSettings() {} },
      "@/lib/onboarding/regions": { districtsFor: () => ["fixture-district"] },
      "@/lib/api/onboarding": { chooseCenter() {} },
      "@/lib/api/centers": {
        searchDaycares: async (...args) => {
          calls.push(args);
          if (failing) throw new Error("network unavailable");
          return [];
        },
      },
    });
    let tree = h.render();
    tree.props.footer.props.onNext();
    h.render();
    timers.splice(0).forEach((fn) => fn());
    await settle();
    tree = h.render();
    const cascade = walk(tree).find((n) => n?.type === "Cascade");
    const find = cascade.props.fields.find(
      (n) => typeof n?.type === "function" && n.type.name === "FindField",
    );
    const field = find.type(find.props);
    assert.match(text(field), /불러오지 못했어요/);
    assert.ok(!walk(field).some((n) => n?.type?.name === "NoDaycare"));
    failing = false;
    walk(field)
      .find((n) => n?.type === "CtaButton")
      .props.onClick();
    h.render();
    timers.splice(0).forEach((fn) => fn());
    await settle();
    tree = h.render();
    const next = walk(tree)
      .find((n) => n?.type === "Cascade")
      .props.fields.find((n) => n?.type?.name === "FindField");
    assert.equal(next.props.failed, false);
    const none = walk(next.type(next.props)).find((n) => n?.type?.name === "NoDaycare");
    assert.match(text(none.type(none.props)), /찾은 어린이집이 없어요/);
    assert.deepEqual(calls, [
      ["fixture-province", "fixture-district", ""],
      ["fixture-province", "fixture-district", ""],
    ]);
  } finally {
    globalThis.window = before;
  }
});

test("#373: 타반 놀이 월간을 전용 조회·내려받기로 읽기 전용 표시한다", async () => {
  const calls = [];
  const list = (kind, result) => async () => {
    calls.push(kind);
    return result;
  };
  const h = harness(
    "../components/workspace/ClassAccessPanels.tsx",
    {
      "@/lib/api/client": { errorCode: () => null },
      "@/lib/api/auth": { getMe() {} },
      "@/lib/api/classes": { getClasses() {}, isMyClass() {} },
      "@/lib/api/class-access": {
        classAccessMessage() {},
        decideRequest() {},
        getArchiveSummary() {},
        listReceivedRequests() {},
        requestClassAccess() {},
      },
      "@/lib/api/documents": {
        listDocuments: list("documents", []),
        downloadDocumentHwpx() {},
        getDocument() {},
        isStaleWrite() {},
      },
      "@/lib/api/plans": {
        listAnnualPlans: list("annual", { items: [] }),
        downloadAnnualHwpx() {},
      },
      "@/lib/api/monthly": {
        listMonthlyPlans: list("monthly-v1", { items: [] }),
        downloadMonthlyHwpx() {},
      },
      "@/lib/api/weekly": {
        listWeeklyPlans: list("weekly", { items: [] }),
        downloadWeeklyHwpx() {},
      },
      "@/lib/api/playMonthly": {
        listPlayMonthly: list("monthly-v2", {
          items: [
            { id: 42, target_month: "2026-03", status: "CONFIRMED", created_at: "2026-03-01" },
          ],
        }),
        downloadPlayMonthlyHwpx: async (id) => calls.push(`download-v2:${id}`),
      },
      "@/lib/workspace/document-archive": { monthLabel: (s) => s, weekIdLabel: (s) => s },
      "@/lib/workspace/model": { DOCUMENT_KINDS: {}, localDate: (s) => s },
      "@/components/app/icons": { Icon: "icon" },
      "@/components/app/Posty": { Posty: "posty" },
      "./WorkspaceUI": { Message: "message", ws: {} },
      "./DocumentArchivePreview": {
        __esModule: true,
        default: "doc-preview",
        PlanArchivePreview: "plan-preview",
      },
    },
    "\nexport { ApprovedList };\n",
  );
  const props = { room: { id: 9, name: "fixture-room" }, onLost() {} };
  h.render(h.exports.ApprovedList, props);
  await settle();
  const tree = h.render(h.exports.ApprovedList, props);
  assert.deepEqual(calls, ["documents", "annual", "monthly-v1", "weekly", "monthly-v2"]);
  const buttons = walk(tree).filter((n) => n?.type === "button");
  buttons.find((n) => text(n) === "보기").props.onClick();
  const opened = h.render(h.exports.ApprovedList, props);
  const preview = walk(opened).find((n) => n?.type === "plan-preview");
  assert.equal(preview.props.target.play, true);
  assert.equal(preview.props.target.href, "");
  assert.equal(preview.props.target.id, 42);
  assert.equal(preview.props.onDeleted, undefined);
  await buttons.find((n) => text(n).includes("hwp")).props.onClick();
  assert.equal(calls.at(-1), "download-v2:42");
});

test("#373: 날짜·주 변경 즉시 이전 일지와 근거를 숨긴다", async () => {
  const doc = {
    id: "journal-first-period",
    start: "2026-03-02",
    end: "2026-03-02",
    status: "draft",
  };
  const common = {
    "@/lib/api/documents": {
      listDocuments: async ({ kind }) =>
        kind === "dailyLog" ? [doc] : [{ ...doc, end: "2026-03-08" }],
      createDocument() {},
    },
    "@/lib/api/onboarding": { classServerId: () => 1 },
    "@/lib/onboarding/settings": { loadClassSettings: () => null },
    "@/components/app/Posty": { Posty: "posty" },
    "./WorkspaceUI": { Message: "message", ws: {} },
    "./DocumentEditor": { __esModule: true, default: "editor" },
    "./use-server-document": { useServerDocument() {} },
  };
  const daily = harness("../components/workspace/DailyJournalCard.tsx", common);
  const firstDay = { classId: 1, date: "2026-03-02" };
  daily.render(daily.exports.useDailyJournal, firstDay);
  await settle();
  let state = daily.render(daily.exports.useDailyJournal, firstDay);
  state.open(doc.id);
  daily.render(daily.exports.useDailyJournal, firstDay);
  const nextDay = { classId: 1, date: "2026-03-03" };
  state = daily.render(daily.exports.useDailyJournal, nextDay);
  assert.equal(state.openId, "");
  assert.equal(state.doc, undefined);
  await settle();
  state = daily.render(daily.exports.useDailyJournal, nextDay);
  assert.equal(state.doc, null);
  assert.equal(state.openId, "");

  const weekly = harness("../components/workspace/WeeklyJournalCard.tsx", {
    ...common,
    "next/link": { __esModule: true, default: "link" },
    "@/lib/api/routines": { routineLocalId: (id) => `routine:${id}` },
    "@/lib/workspace/routines-route": { routinesPath: () => "/routines" },
    "./DailyJournalCard": { journalMood: () => ({}) },
  });
  const firstWeek = {
    classId: "class-a",
    weekStart: "2026-03-02",
    weekEnd: "2026-03-08",
    routines: [],
  };
  weekly.render(weekly.exports.useWeeklyJournal, firstWeek);
  await settle();
  state = weekly.render(weekly.exports.useWeeklyJournal, firstWeek);
  state.open(doc.id);
  weekly.render(weekly.exports.useWeeklyJournal, firstWeek);
  const nextWeek = { ...firstWeek, weekStart: "2026-03-09", weekEnd: "2026-03-15" };
  state = weekly.render(weekly.exports.useWeeklyJournal, nextWeek);
  assert.equal(state.openId, "");
  assert.equal(state.doc, undefined);
  assert.deepEqual(state.weekDailies, []);
  await settle();
  state = weekly.render(weekly.exports.useWeeklyJournal, nextWeek);
  assert.equal(state.doc, null);
  assert.equal(state.openId, "");
});
