/**
 * 화면 4상태 공용 처리 (components/workspace/WorkspaceViewState.tsx).
 *
 * 컴포넌트는 hook 을 쓰지 않아서, 실제 소스를 babel 로 옮긴 뒤 함수로 직접 부른다.
 * React 와 CSS module 은 스텁이다 — 여기서 보는 것은 "어떤 상태에 무엇을 그리나" 다.
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { createRequire, registerHooks } from "node:module";
import { existsSync, readFileSync } from "node:fs";
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

const { ApiError, invalidFields } = await import("../lib/api/client.ts");
const require = createRequire(import.meta.url);
const read = (path) => readFileSync(new URL(path, import.meta.url), "utf8").replace(/\r\n/g, "\n");

const compiled = require("next/dist/compiled/babel/core").transformSync(
  read("../components/workspace/WorkspaceViewState.tsx"),
  {
    filename: "WorkspaceViewState.tsx",
    babelrc: false,
    configFile: false,
    presets: [
      [require("next/dist/compiled/babel/preset-env"), { targets: { node: "current" } }],
      [require("next/dist/compiled/babel/preset-react"), { runtime: "automatic" }],
      require("next/dist/compiled/babel/preset-typescript"),
    ],
  },
).code;

const jsx = (type, props) => ({ type, props });
const modules = {
  "react/jsx-runtime": { jsx, jsxs: jsx, Fragment: "fragment" },
  // Message 는 실제 공용 컴포넌트다. 여기서는 "무엇이 그려졌나" 만 보면 된다.
  "./WorkspaceUI": { Message: "message", ws: { loading: "loading", fieldError: "fieldError" } },
};
const module_ = { exports: {} };
new Function("require", "module", "exports", compiled)(
  (name) => {
    assert.ok(name in modules, `unhandled import: ${name}`);
    return modules[name];
  },
  module_,
  module_.exports,
);
const { WorkspaceViewState, FieldError, fieldErrorProps, fieldErrorId } = module_.exports;

/** 렌더 결과를 평평하게 편다. 문자열과 노드가 섞여 나온다. */
function flatten(node) {
  if (node === null || node === undefined || node === false || node === true) return [];
  if (Array.isArray(node)) return node.flatMap(flatten);
  if (typeof node === "object") return [node, ...flatten(node.props?.children)];
  return [node];
}
const texts = (node) => flatten(node).filter((part) => typeof part === "string");
const nodes = (node) => flatten(node).filter((part) => typeof part === "object");

const SUCCESS = jsx("ok", { children: "성공 본문" });
const EMPTY = jsx("empty", { children: "비었음 본문" });
const view = (over) =>
  WorkspaceViewState({ status: "ready", loading: "불러오고 있어요.", children: SUCCESS, ...over });

test("loading 은 aria-busy 와 화면이 준 문구를 보여주고 본문을 그리지 않는다", () => {
  const tree = view({ status: "loading", empty: EMPTY });
  assert.equal(tree.props["aria-busy"], "true");
  assert.ok(texts(tree).includes("불러오고 있어요."));
  assert.equal(nodes(tree).includes(SUCCESS), false);
  assert.equal(nodes(tree).includes(EMPTY), false);
});

test("error 는 서버 문구를 그대로 alert 로 넘긴다", () => {
  const tree = view({ status: "error", error: "요청을 처리하지 못했어요.", empty: EMPTY });
  assert.equal(tree.type, "message");
  assert.equal(tree.props.error, true);
  assert.equal(tree.props.children, "요청을 처리하지 못했어요.");
  assert.equal(nodes(tree).includes(SUCCESS), false);
});

test("empty 는 화면이 준 그대로 그리고 본문을 대신한다", () => {
  const tree = view({ empty: EMPTY });
  assert.ok(nodes(tree).includes(EMPTY));
  assert.equal(nodes(tree).includes(SUCCESS), false);
});

test("success 는 children 을 그린다. empty 가 false 면 비어 있지 않다", () => {
  for (const empty of [false, undefined]) {
    const tree = view({ empty });
    assert.ok(nodes(tree).includes(SUCCESS), String(empty));
  }
});

test("ApiError 의 서버 message 가 그대로 error 로 전달된다", () => {
  const body = {
    error: { code: "VALIDATION_FAILED", message: "입력값을 확인해주세요.", fields: [] },
  };
  const error = new ApiError(422, body);
  assert.equal(error.message, "입력값을 확인해주세요.");
  // 화면은 이 문장을 다시 쓰지 않는다.
  assert.equal(view({ status: "error", error: error.message }).props.children, error.message);
});

const FIELDS = (fields) =>
  new ApiError(422, { error: { code: "VALIDATION_FAILED", message: "확인해주세요.", fields } });
const MAP = { class_id: "classId", fact: "fact", sources: "sources", source_ids: "sources" };

test("VALIDATION_FAILED 의 fields 만 화면 입력 이름으로 바꾼다", () => {
  assert.deepEqual(invalidFields(FIELDS(["class_id", "fact"]), MAP), ["classId", "fact"]);
  // 점 표기는 앞부분을 본다. 같은 묶음이 여러 번 와도 한 번만 남는다.
  assert.deepEqual(invalidFields(FIELDS(["sources.3", "sources.7", "source_ids"]), MAP), [
    "sources",
  ]);
  // 화면에 없는 칸은 버린다. 서버 이름을 그대로 보여주면 어디를 고칠지 모른다.
  assert.deepEqual(invalidFields(FIELDS(["school_year"]), MAP), []);
});

test("VALIDATION_FAILED 가 아니거나 모양이 다르면 아무 칸도 짚지 않는다", () => {
  const other = new ApiError(409, {
    error: { code: "STALE_WRITE", message: "", fields: ["fact"] },
  });
  assert.deepEqual(invalidFields(other, MAP), []);
  assert.deepEqual(invalidFields(FIELDS("fact"), MAP), []);
  assert.deepEqual(invalidFields(FIELDS([1, null, "fact"]), MAP), ["fact"]);
  assert.deepEqual(invalidFields(new ApiError(422, "그냥 문자열"), MAP), []);
  assert.deepEqual(invalidFields(new Error("네트워크"), MAP), []);
});

test("짚힌 칸만 alert 와 aria 연결을 받는다", () => {
  const marker = FieldError({ name: "fact", invalid: ["fact"] });
  assert.equal(marker.props.role, "alert");
  assert.equal(marker.props.id, fieldErrorId("fact"));
  assert.equal(fieldErrorProps("fact", ["fact"])["aria-describedby"], marker.props.id);
  assert.equal(fieldErrorProps("fact", ["fact"])["aria-invalid"], true);

  assert.equal(FieldError({ name: "fact", invalid: ["context"] }), null);
  const clean = fieldErrorProps("fact", ["context"]);
  assert.equal(clean["aria-invalid"], undefined);
  assert.equal(clean["aria-describedby"], undefined);
});

// 화면은 JSX 라 이 환경에서 렌더할 수 없다. 아래는 소스로 확인한다.
const records = () => read("../components/workspace/RecordsPage.tsx");
const documents = () => read("../components/workspace/DocumentsPage.tsx");
const between = (source, from, to) => {
  const start = source.indexOf(from);
  assert.ok(start > -1, from);
  const end = source.indexOf(to, start);
  assert.ok(end > start, to);
  return source.slice(start, end);
};

test("관찰 기록 빈 상태 제목은 계약 문구 그대로다", () => {
  assert.ok(records().includes('<Empty title="아직 남긴 기록이 없어요">'));
});

test("두 화면이 로딩·빈 상태·오류를 직접 분기하지 않는다", () => {
  for (const [name, source] of [
    ["RecordsPage", records()],
    ["DocumentsPage", documents()],
  ]) {
    assert.ok(source.includes("<WorkspaceViewState"), name);
    assert.equal(source.includes('aria-busy="true"'), false, `${name}: 로딩 분기가 남아 있다`);
    assert.equal(source.includes("ws.loading"), false, `${name}: 로딩 분기가 남아 있다`);
  }
});

test("저장이 실패해도 관찰 기록 입력값을 지우지 않는다", () => {
  const submit = between(records(), "async function submit(", "async function remove(");
  const caught = between(submit, "} catch (e) {", "} finally {");
  for (const setter of [
    "setFact(",
    "setContext(",
    "setClassId(",
    "setChildId(",
    "setDate(",
    "setDomain(",
    "setEditId(",
  ])
    assert.equal(caught.includes(setter), false, setter);
  // 성공했을 때만 비운다.
  assert.ok(submit.includes('setFact("")'));
});

test("생성이 실패해도 문서 작성 조건과 근거 선택을 지우지 않는다", () => {
  const generate = between(documents(), "async function generate(", "const serverActions");
  const caught = between(generate, "} catch (e) {", "} finally {");
  for (const setter of [
    "setSelected(",
    "setClassId(",
    "setChildId(",
    "setStart(",
    "setEnd(",
    "setKind(",
    "setMode(",
  ])
    assert.equal(caught.includes(setter), false, setter);
  assert.ok(generate.includes("setSelected([])"));
});

test("짚을 수 있는 칸은 모두 서버 계약의 칸 이름에서 온다", () => {
  for (const [name, source] of [
    ["RecordsPage", records()],
    ["DocumentsPage", documents()],
  ]) {
    const map = between(source, "const FIELD_INPUT: Record<string, string> = {", "};");
    const inputs = new Set([...map.matchAll(/:\s*"([^"]+)"/g)].map((m) => m[1]));
    const marked = [...source.matchAll(/<FieldError name="([^"]+)"/g)].map((m) => m[1]);
    const linked = [...source.matchAll(/fieldErrorProps\("([^"]+)"/g)].map((m) => m[1]);
    assert.ok(marked.length > 0, name);
    assert.deepEqual(new Set(marked), new Set(linked), `${name}: 표시와 aria 연결이 어긋난다`);
    for (const field of marked) assert.ok(inputs.has(field), `${name}: ${field}`);
  }
});

// DocumentsPage의 실제 조회·재시도 이벤트와 공용 상태 분기를 함께 실행한다.
const workspaceModel = await import("../lib/workspace/model.ts");
const documentApi = await import("../lib/api/documents.ts");
const archive = await import("../lib/workspace/archive.ts");
const archiveNavigation = await import("../lib/workspace/document-archive.ts");
const { createSelection } = await import("../components/workspace/document-selection.ts");
const pageCode = require("next/dist/compiled/babel/core").transformSync(documents(), {
  filename: "DocumentsPage.tsx",
  babelrc: false,
  configFile: false,
  presets: [
    [require("next/dist/compiled/babel/preset-env"), { targets: { node: "current" } }],
    [require("next/dist/compiled/babel/preset-react"), { runtime: "automatic" }],
    require("next/dist/compiled/babel/preset-typescript"),
  ],
}).code;

const serverDocument = {
  id: "document:17",
  kind: "observation",
  title: "기존 서버 문서",
  status: "draft",
  classId: "class-1",
  className: "햇살반",
  childId: "",
  childName: "",
  start: "2026-09-01",
  end: "2026-09-30",
  createdAt: "2026-09-02T00:00:00Z",
  updatedAt: "t0",
  sourcesCount: 0,
  sources: [],
  sections: [],
  reviewNote: "기존 검토 메모",
};
const localDocuments = [
  { ...serverDocument, id: "import-uuid", title: "로컬 증빙", origin: "import" },
  { ...serverDocument, id: "plan-uuid", title: "로컬 계획안", kind: "annual", origin: "template" },
];
const LIST_FAILURE = "문서 목록을 다시 불러오지 못했어요.";
const PLAN_FAILURE = "계획안 서버 오류";
const annualPlan = {
  id: 5,
  class_id: 3,
  school_year: 2026,
  format: "MONTHLY_THEME",
  status: "CONFIRMED",
  created_at: "2026-09-10T00:00:00Z",
  confirmed_at: "2026-09-11T00:00:00Z",
};
const settle = () => new Promise((resolve) => setImmediate(resolve));

function documentsHarness({
  items = [],
  local = [],
  fail = false,
  plans = [],
  planFail = false,
  planPending = false,
  listPending = false,
} = {}) {
  // listPending 이면 일지 목록 응답을 releaseList() 를 부를 때까지 붙잡아 둔다.
  let releaseList;
  const listGate = listPending
    ? new Promise((resolve) => {
        releaseList = resolve;
      })
    : null;
  const slots = [],
    effects = [];
  let cursor = 0,
    mounted = false,
    selection,
    pickClass = () => {},
    tree;
  const state = (initial) => {
    const slot = cursor++;
    if (!(slot in slots)) slots[slot] = typeof initial === "function" ? initial() : initial;
    return [
      slots[slot],
      (next) => {
        slots[slot] = typeof next === "function" ? next(slots[slot]) : next;
      },
    ];
  };
  const pageModules = {
    react: {
      useState: state,
      useRef: (initial) => state(() => ({ current: initial }))[0],
      useMemo: (fn) => fn(),
      useEffect: (effect) => {
        if (!mounted) effects.push(effect);
      },
      useSyncExternalStore: (_subscribe, get) => get(),
    },
    "react/jsx-runtime": { jsx, jsxs: jsx, Fragment: "fragment" },
    "next/link": { default: "link", __esModule: true },
    "@/lib/workspace/model": workspaceModel,
    "@/lib/workspace/store": {
      useWorkspace: () => ({
        data: {
          documents: local,
          observations: [],
          templates: [],
          criteria: [],
        },
        error: "",
      }),
    },
    "@/lib/api/client": { isUnauthenticated: () => false, invalidFields },
    "@/lib/api/records": { listRecords: async () => [] },
    "@/lib/api/documents": {
      ...documentApi,
      listDocuments: async () => {
        if (listGate) await listGate;
        if (fail) throw new Error(LIST_FAILURE);
        return items;
      },
      getDocument: async () => serverDocument,
      updateDocument: async () => serverDocument,
    },
    // 일일 보육일지 근거(일과 기록). 이 테스트는 보관함 목록만 보므로 부르지 않는다.
    "@/lib/api/routines": { listDayRoutines: async () => [] },
    "@/lib/api/plans": {
      listAnnualPlans: async () => {
        if (planPending) return new Promise(() => {});
        if (planFail) throw new Error(PLAN_FAILURE);
        return { items: plans };
      },
    },
    "@/lib/workspace/archive": archive,
    "@/lib/api/onboarding": { classServerId: (id) => (id === "class-1" ? 3 : null) },
    "@/lib/hooks/use-client-state": { useClientState: (_read, fallback) => state(fallback) },
    "@/lib/workspace/routines-route": {
      routinesPath: () => "/routines",
      routinesScope: () => ({ date: "", classId: null }),
    },
    "@/lib/onboarding/settings": { chosenClassFor: () => null, loadClassSettings: () => null },
    "./DailyLogSources": { default: "daily-log-sources", __esModule: true },
    "./DocumentArchivePreview": { default: "preview", __esModule: true },
    "./DocumentEditor": { default: "editor", __esModule: true },
    // 보관함 탐색(반 → 종류 → 기간)은 자기 테스트가 따로 본다. 여기서는 목록과
    // 선택 문서 상세만 보므로, 넘겨받은 `detail` 만 그대로 그려 준다.
    "./DocumentArchiveView": {
      default: ({ header, documents, annual, onOpen, onPickClass, detail }) => {
        pickClass = onPickClass;
        return jsx("archive", {
          children: [
            header,
            ...documents.map((d) =>
              jsx("button", { children: d.title, onClick: () => onOpen(d.id) }),
            ),
            ...(annual ?? []).map((p) =>
              jsx("link", {
                children: `${p.school_year}학년도 연간 보육계획안`,
                href: `/plans/annual/${p.id}`,
              }),
            ),
            detail,
          ],
        });
      },
      __esModule: true,
    },
    "./document-selection": {
      createSelection: (...args) => {
        selection = createSelection(...args);
        return selection;
      },
    },
    "./WorkspaceUI": {
      WorkspacePage: "page",
      Empty: ({ title, children }) => jsx("empty", { children: [title, children] }),
      Message: ({ children, error }) => (children ? jsx("message", { children, error }) : null),
      useClasses: () => [{ id: "class-1", className: "햇살반", children: [] }],
      ws: {},
    },
    "./WorkspaceViewState": { WorkspaceViewState, FieldError, fieldErrorProps },
  };
  const pageModule = { exports: {} };
  new Function("require", "module", "exports", pageCode)(
    (name) => {
      assert.ok(name in pageModules, name);
      return pageModules[name];
    },
    pageModule,
    pageModule.exports,
  );
  const resolveViews = (node) => {
    if (Array.isArray(node)) return node.map(resolveViews);
    if (!node || typeof node !== "object") return node;
    if (typeof node.type === "function") return resolveViews(node.type(node.props));
    return { ...node, props: { ...node.props, children: resolveViews(node.props.children) } };
  };
  const render = () => {
    cursor = 0;
    tree = resolveViews(pageModule.exports.default());
    mounted = true;
  };
  const content = (node) => texts(node).join("");
  render();
  return {
    render,
    mount: async () => {
      effects.forEach((effect) => effect());
      await settle();
      render();
    },
    fail: (next) => {
      fail = next;
    },
    planFail: (next) => {
      planFail = next;
    },
    releaseList: async () => {
      releaseList();
      await settle();
      render();
    },
    pickClass: (id) => pickClass(id),
    links: () => nodes(tree).filter((node) => node.type === "link"),
    selection: () => selection,
    editor: () => nodes(tree).find((node) => node.type === "editor"),
    text: () => content(tree),
    button: (label) =>
      nodes(tree).find((node) => node.type === "button" && content(node).includes(label)),
    errors: () => nodes(tree).filter((node) => node.type === "message" && node.props.error),
  };
}

test("문서 목록 재조회 실패는 기존 목록·선택 문서·로컬 문서를 유지하고 재시도할 수 있다", async () => {
  const page = documentsHarness({ items: [serverDocument], local: localDocuments });
  // 로컬 증빙은 바로 있으니 일지를 기다리지 않고 먼저 그린다.
  assert.match(page.text(), /일지를 불러오고 있어요/);
  assert.ok(page.text().includes(localDocuments[0].title));
  await page.mount();
  page.button(serverDocument.title).props.onClick();
  await settle();
  page.render();
  const before = page.editor();
  assert.ok(before);
  page.fail(true);
  await before.props.server.save([], "기존 검토 메모");
  await settle();
  page.render();
  for (const doc of [serverDocument, localDocuments[0]]) assert.ok(page.text().includes(doc.title));
  assert.equal(page.editor().key, before.key);
  assert.strictEqual(page.editor().props.initial, before.props.initial);
  assert.equal(page.selection().get().active, serverDocument.id);
  assert.equal(page.errors().length, 1);
  assert.match(page.text(), new RegExp(LIST_FAILURE));
  page.fail(false);
  await page.button("다시 시도").props.onClick();
  page.render();
  assert.equal(page.errors().length, 0);
  assert.equal(page.editor().key, before.key);
});

test("서버 목록이 없어도 로컬 증빙은 오류와 함께 표시하고 선택할 수 있다", async () => {
  const page = documentsHarness({ local: localDocuments, fail: true });
  await page.mount();
  assert.ok(page.text().includes(localDocuments[0].title));
  // 브라우저에 남은 옛 계획안은 읽지 않는다 — 계획안은 서버 목록에서 온다.
  assert.equal(page.text().includes(localDocuments[1].title), false);
  page.button(localDocuments[0].title).props.onClick();
  page.render();
  const before = page.editor();
  assert.strictEqual(before.props.initial, localDocuments[0]);
  await page.button("다시 시도").props.onClick();
  page.render();
  assert.equal(page.editor().key, before.key);
});

test("목록이 비어도 이미 받은 선택 문서 상세가 있으면 조회 오류가 상세를 숨기지 않는다", async () => {
  const page = documentsHarness({ fail: true });
  page.selection().adopt(serverDocument);
  await page.mount();
  assert.strictEqual(page.editor().props.initial, serverDocument);
  assert.equal(page.errors().length, 1);
});

test("표시할 문서가 없는 조회 실패는 오류와 재시도를 띄우고, 성공하면 오류를 걷는다", async () => {
  const page = documentsHarness({ fail: true });
  await page.mount();
  assert.equal(page.editor(), undefined);
  assert.equal(page.errors().length, 1);
  page.fail(false);
  await page.button("다시 시도").props.onClick();
  page.render();
  assert.equal(page.errors().length, 0);
  assert.equal(page.button("다시 시도"), undefined);
});

// ── 보관함 형식 표시와 종류별 탐색을 함께 보존한다 (S-J5 · FR-701) ──
test("보관함은 놀이 프로젝트형 연간계획안의 둘째 줄에만 형식을 덧붙인다", () => {
  // PR의 반·종류별 보관함을 실제로 렌더한다. 평면 목록을 흉내 낸 스텁에 형식 표시를 복제하지 않는다.
  const code = require("next/dist/compiled/babel/core").transformSync(
    read("../components/workspace/DocumentArchiveView.tsx"),
    {
      filename: "DocumentArchiveView.tsx",
      babelrc: false,
      configFile: false,
      presets: [
        [require("next/dist/compiled/babel/preset-env"), { targets: { node: "current" } }],
        [require("next/dist/compiled/babel/preset-react"), { runtime: "automatic" }],
        require("next/dist/compiled/babel/preset-typescript"),
      ],
    },
  ).code;
  let hook = 0;
  const imports = {
    "react/jsx-runtime": { jsx, jsxs: jsx, Fragment: "fragment" },
    react: {
      useState: (initial) => [
        hook++ === 0 ? "annual" : typeof initial === "function" ? initial() : initial,
        () => {},
      ],
      useMemo: (fn) => fn(),
      useEffect() {},
      useRef: () => ({ current: null }),
    },
    "next/link": { __esModule: true, default: "link" },
    "@/components/app/icons": { Icon: "icon" },
    "@/lib/workspace/model": { ...workspaceModel, today: () => "2026-10-28" },
    "@/lib/workspace/document-archive": archiveNavigation,
    "@/lib/api/onboarding": { classServerId: () => 3 },
    "@/lib/onboarding/types": {},
    "@/lib/api/monthly": {},
    "@/lib/api/weekly": {},
    "./DocumentArchivePreview": { PlanArchivePreview: "plan-preview" },
    "./WorkspaceUI": { Message: "message", ws: {} },
    "./DocumentArchiveArt": new Proxy({}, { get: () => "art" }),
    "./DocumentArchive.module.css": {
      __esModule: true,
      default: new Proxy({}, { get: (_, name) => name }),
    },
  };
  const viewModule = { exports: {} };
  new Function("require", "module", "exports", code)(
    (name) => {
      assert.ok(name in imports, name);
      return imports[name];
    },
    viewModule,
    viewModule.exports,
  );
  const resolve = (node) => {
    if (Array.isArray(node)) return node.map(resolve);
    if (!node || typeof node !== "object") return node;
    if (typeof node.type === "function") return resolve(node.type(node.props));
    return { ...node, props: { ...node.props, children: resolve(node.props.children) } };
  };
  for (const format of ["MONTHLY_THEME", "PLAY_PROJECT"]) {
    hook = 0;
    const tree = resolve(
      viewModule.exports.default({
        classes: [{ id: "class-1", className: "햇살반", children: [] }],
        classId: "class-1",
        documents: [],
        annual: [{ ...annualPlan, format }],
        activeId: "",
        editingId: "",
        onBackToPreview() {},
        preview: null,
        onOpen() {},
        onPickClass() {},
        onCloseDetail() {},
        onCreate() {},
        header: null,
        detail: null,
      }),
    );
    const link = nodes(tree).find(
      (node) => node.type === "button" && node.props.className === "docCard",
    );
    assert.ok(link);
    const secondLine = nodes(link).find((node) => node.type === "small");
    assert.equal(
      texts(secondLine).join(""),
      "햇살반" + (format === "PLAY_PROJECT" ? " · 놀이 프로젝트형" : ""),
    );
    const title = nodes(link).find((node) => node.props.className === "docTitle");
    assert.equal(
      flatten(title)
        .filter((part) => typeof part === "string" || typeof part === "number")
        .join(""),
      "2026학년도 연간계획안",
    );
  }
});

test("계획 노트는 놀이 프로젝트형에만 상태 옆 둥근 배지를 보여준다", () => {
  const code = require("next/dist/compiled/babel/core").transformSync(
    read("../components/plan-generator/PlanNotebookPage.tsx"),
    {
      filename: "PlanNotebookPage.tsx",
      babelrc: false,
      configFile: false,
      presets: [
        [require("next/dist/compiled/babel/preset-env"), { targets: { node: "current" } }],
        [require("next/dist/compiled/babel/preset-react"), { runtime: "automatic" }],
        require("next/dist/compiled/babel/preset-typescript"),
      ],
    },
  ).code;
  const notebook = { exports: {} };
  const imports = {
    "react/jsx-runtime": { jsx, jsxs: jsx },
    "@/lib/workspace/model": workspaceModel,
  };
  new Function("require", "module", "exports", code + "\nexports.PlanCard = PlanCard;")(
    (name) => imports[name] ?? {},
    notebook,
    notebook.exports,
  );
  for (const format of ["MONTHLY_THEME", "PLAY_PROJECT"]) {
    const tree = notebook.exports.PlanCard({ plan: { ...annualPlan, format }, onReset() {} });
    const pills = nodes(tree).filter((node) => node.props.className?.includes("rounded-full"));
    assert.deepEqual(
      pills.map((node) => texts(node).join("")),
      format === "PLAY_PROJECT" ? ["확정", "놀이 프로젝트형"] : ["확정"],
    );
  }
});

// ── 보관함은 종류(연간 · 월간 · 주간 · 보육 · 관찰)로만 탐색한다 (S-J5 · FR-701) ──
test("일지와 연간계획안을 각자 보관함 뷰로 넘긴다", async () => {
  const page = documentsHarness({ items: [serverDocument], plans: [annualPlan] });
  await page.mount();
  // 둘은 다른 API 라 한 목록으로 합치지 않는다 — 종류 칸이 각자 받는다.
  assert.ok(page.text().includes(serverDocument.title));
  assert.ok(page.text().includes("2026학년도 연간 보육계획안"));
  const [link] = page.links().filter((node) => node.props.href?.startsWith("/plans/"));
  assert.equal(link.props.href, "/plans/annual/5");
  // 지워진 전체 목록(필터 · 검색)을 다시 띄우지 않는다.
  assert.equal(page.text().includes("전체 문서 목록"), false);
  assert.equal(page.button("확정"), undefined);
});

test("계획안 목록만 실패하면 일지는 그대로 보이고 계획안만 다시 시도한다", async () => {
  const page = documentsHarness({ items: [serverDocument], planFail: true });
  await page.mount();
  assert.ok(page.text().includes(serverDocument.title));
  assert.match(page.text(), new RegExp(PLAN_FAILURE));
  assert.ok(page.button("계획안 다시 시도"));
  page.planFail(false);
  await page.button("계획안 다시 시도").props.onClick();
  page.render();
  assert.equal(page.button("계획안 다시 시도"), undefined);
});

test("일지 목록만 실패해도 받은 계획안은 그린다", async () => {
  const page = documentsHarness({ fail: true, plans: [annualPlan] });
  await page.mount();
  assert.ok(page.text().includes("2026학년도 연간 보육계획안"));
  assert.match(page.text(), new RegExp(LIST_FAILURE));
  assert.ok(page.button("다시 시도"));
});

test("보관함에는 상단 문서 만들기 단추를 두지 않는다", async () => {
  // 만들기는 종류별 화면 안의 작성 단추로만 한다 — 반을 골라도 상단에 다시 뜨면 안 된다.
  const page = documentsHarness({ items: [serverDocument] });
  await page.mount();
  assert.equal(page.button("기록으로 문서 만들기"), undefined);
  page.pickClass("class-1");
  page.render();
  assert.equal(page.button("기록으로 문서 만들기"), undefined);
  assert.equal(page.text().includes("기록으로 문서 만들기"), false);
});

test("계획안 목록만 실패하고 일지가 없으면 「문서가 없다」고 하지 않는다", async () => {
  const page = documentsHarness({ planFail: true });
  await page.mount();
  assert.match(page.text(), new RegExp(PLAN_FAILURE));
  assert.equal(page.text().includes("보관된 문서가 없어요"), false);
});

test("계획안이 아직 오는 중이어도 「문서가 없다」고 하지 않는다", async () => {
  const page = documentsHarness({ planPending: true });
  await page.mount();
  assert.equal(page.text().includes("보관된 문서가 없어요"), false);
  assert.equal(page.errors().length, 0);
});

test("계획안을 먼저 받으면 일지가 오는 중이어도 계획안부터 그린다", async () => {
  const page = documentsHarness({
    items: [serverDocument],
    plans: [annualPlan],
    listPending: true,
  });
  await page.mount();
  // 받은 계획안을 「불러오는 중」 화면이 가리지 않는다.
  assert.ok(page.text().includes("2026학년도 연간 보육계획안"));
  assert.equal(page.text().includes("문서를 불러오고 있어요"), false);
  assert.match(page.text(), /일지를 불러오고 있어요/);
  assert.equal(page.text().includes(serverDocument.title), false);

  await page.releaseList();
  assert.ok(page.text().includes("2026학년도 연간 보육계획안"));
  assert.ok(page.text().includes(serverDocument.title));
  assert.equal(page.text().includes("일지를 불러오고 있어요"), false);
});
