/**
 * 일과 기록 (docs/api-spec.md §10-1 · ADR-025).
 *
 * 1. `lib/api/routines.ts` — 계약대로 묻고 보내나. fetch 와 브라우저 저장소는 스텁이다.
 * 2. `components/workspace/RoutinesPage.tsx` — 네 상태와 CRUD. 실패해도 적던 값을 지키나.
 */
import assert from "node:assert/strict";
import { test } from "node:test";
import { createRequire, registerHooks } from "node:module";
import { existsSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
const domainLook = await import("../lib/workspace/domain-look.ts");

registerHooks({
  resolve(spec, ctx, next) {
    const url = spec.startsWith("@/")
      ? new URL(`../${spec.slice(2)}.ts`, import.meta.url)
      : spec.startsWith(".") && ctx.parentURL
        ? new URL(spec + ".ts", ctx.parentURL)
        : null;
    if (url && existsSync(fileURLToPath(url))) return { url: url.href, shortCircuit: true };
    return next(spec, ctx);
  },
});

const routines = await import("../lib/api/routines.ts");
const { createMutationBarrier } = await import("../lib/api/pending-mutations.ts");
const { API_STORAGE_CONTEXT } = await import("../lib/api/storage-context.ts");
// **흉내 내지 않는다.** 주 반 판정 버그가 helper 를 mock 해서 숨어 있었다.
const classSettings = await import("../lib/onboarding/settings.ts");
const onboardingApi = await import("../lib/api/onboarding.ts");
const routinesRoute = await import("../lib/workspace/routines-route.ts");
const onboardingTypes = await import("../lib/onboarding/types.ts");
const childMark = await import("../lib/workspace/child-mark.ts");
const homeBlocks = await import("../lib/workspace/home-blocks.ts");
const recordContext = await import("../lib/workspace/record-context.ts");
const journalDay = await import("../lib/workspace/journal-day.ts");
const { EMPTY_CLASS_SETTINGS } = onboardingTypes;

const require = createRequire(import.meta.url);
const EMAIL = "fixture@example.com";
const TOKEN = "test-token";
const accountKey = `saessak.demoAccount:${encodeURIComponent(EMAIL)}`;
const linksKey = `saessak.apiLinks.v1:${API_STORAGE_CONTEXT}:${encodeURIComponent(EMAIL)}`;
const LINKS = JSON.stringify({
  classes: { "class-abc": { id: 3, signature: "" }, "class-star": { id: 7, signature: "" } },
  children: { "api-child-8": 8 },
});
/** 온보딩이 저장해 둔 반. 서버 반 3 · 7 과 짝이다 (위 LINKS). */
const CLASS_A = { ...EMPTY_CLASS_SETTINGS.classes[0], id: "class-abc", className: "햇살반" };
const CLASS_B = { ...EMPTY_CLASS_SETTINGS.classes[0], id: "class-star", className: "별빛반" };

const ROW = {
  id: 31,
  class_id: 3,
  class_name: "햇살반",
  date: "2026-10-06",
  position: 2,
  start: "09:20:00",
  end: "10:40:00",
  name: "오전 실내놀이",
  plan: "자동차 굴리기",
  execution: "블록 3개로 길을 만들었다.",
  created_at: "2026-10-06T10:31:00+09:00",
};

/**
 * 로그인한 브라우저. 반 설정은 **진짜 저장 경로**(`saveClassSettings`)로 넣는다 —
 * 읽는 쪽(`loadClassSettings` · `chosenClassFor`)도 진짜를 쓴다.
 */
function browser({ rooms, primaryClassId, search = "", confirm = true } = {}) {
  const values = new Map([
    [accountKey, JSON.stringify({ name: "선생님", email: EMAIL })],
    [linksKey, LINKS],
  ]);
  const local = {
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, value),
    removeItem: (key) => values.delete(key),
  };
  const session = new Map([
    ["saessak.demoSession", "active"],
    ["saessak.accountEmail", EMAIL],
    ["saessak.authToken", TOKEN],
  ]);
  const sessionStorage = {
    getItem: (key) => session.get(key) ?? null,
    setItem: (key, value) => session.set(key, value),
    removeItem: (key) => session.delete(key),
  };
  const confirms = [];
  globalThis.localStorage = local;
  globalThis.sessionStorage = sessionStorage;
  const location = { search };
  globalThis.window = {
    localStorage: local,
    sessionStorage,
    location,
    // S-J1 은 보고 있는 반 · 날짜를 주소에 적는다. 적힌 결과를 그대로 읽을 수 있어야 한다.
    history: {
      replaceState: (_state, _title, url) => {
        location.search = String(url).startsWith("?") ? String(url) : "";
      },
    },
    dispatchEvent: () => true,
    // 일과 화면은 창을 닫을 때(`pagehide`) 그 하루를 올린다.
    addEventListener: () => {},
    removeEventListener: () => {},
    confirm: (text) => {
      confirms.push(text);
      return confirm;
    },
  };
  // 시계 팝오버는 바깥 누르기 · Escape 를 document 에서 듣는다. 커서 옮기기도 여기로 온다.
  globalThis.document = {
    addEventListener: () => {},
    removeEventListener: () => {},
    getElementById: () => null,
  };
  if (rooms)
    classSettings.saveClassSettings({
      ...EMPTY_CLASS_SETTINGS,
      orgName: "기관",
      classes: rooms,
      primaryClassId: primaryClassId ?? "",
    });
  return confirms;
}

function serve(reply) {
  const calls = [];
  const original = globalThis.fetch;
  globalThis.fetch = async (url, options = {}) => {
    calls.push({
      url: String(url),
      method: options.method ?? "GET",
      body: options.body ? JSON.parse(options.body) : undefined,
    });
    return reply(calls.length);
  };
  return { calls, restore: () => (globalThis.fetch = original) };
}
const json = (body, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

// ── 1. API 계약 ────────────────────────────────────────────────────────────

test("하루치 조회는 class_id · from · to 를 붙인다", async () => {
  browser();
  const { calls, restore } = serve(() => json({ items: [ROW] }));
  try {
    const items = await routines.listRoutines({
      class_id: 3,
      from: "2026-10-06",
      to: "2026-10-06",
    });
    assert.equal(items.length, 1);
  } finally {
    restore();
  }
  assert.equal(calls[0].url, "/api/routines?class_id=3&from=2026-10-06&to=2026-10-06");
  assert.equal(calls[0].method, "GET");
});

test("S-J2 화면용 조회는 반을 서버 id 로 옮기고 시간을 한 줄로 만든다", async () => {
  browser();
  const { calls, restore } = serve(() =>
    json({
      items: [
        ROW,
        { ...ROW, id: 32, start: "11:00:00", end: null, execution: "" },
        { ...ROW, id: 33, start: null, end: null },
      ],
    }),
  );
  let items;
  try {
    items = await routines.listDayRoutines("class-abc", "2026-10-06");
  } finally {
    restore();
  }
  assert.equal(calls[0].url, "/api/routines?class_id=3&from=2026-10-06&to=2026-10-06");
  assert.deepEqual(items[0], {
    id: "routine:31",
    date: "2026-10-06",
    time: "09:20 ~ 10:40",
    name: "오전 실내놀이",
    execution: "블록 3개로 길을 만들었다.",
  });
  // 한쪽만 있거나 없는 시간도 서버 사실 줄과 같은 규칙으로 보인다.
  assert.equal(items[1].time, "11:00 ~");
  assert.equal(items[1].execution, "");
  assert.equal(items[2].time, "");
});

test("S-J2 화면용 조회는 반을 서버 id 로 못 옮기면 묻지 않는다", async () => {
  browser();
  const { calls, restore } = serve(() => json({ items: [] }));
  try {
    await assert.rejects(routines.listDayRoutines("class-unknown", "2026-10-06"));
  } finally {
    restore();
  }
  assert.equal(calls.length, 0);
});

test("빈 질의는 물음표를 붙이지 않는다", async () => {
  browser();
  const { calls, restore } = serve(() => json({ items: [] }));
  try {
    await routines.listRoutines();
  } finally {
    restore();
  }
  assert.equal(calls[0].url, "/api/routines");
});

test("생성은 class_id 를 함께 보내고, 수정은 보내지 않는다 — 보내면 422 다", async () => {
  browser();
  const input = {
    date: "2026-10-06",
    position: 2,
    start: "09:20",
    end: "10:40",
    name: "오전 실내놀이",
    plan: "자동차 굴리기",
    execution: "블록 3개로 길을 만들었다.",
  };
  const { calls, restore } = serve(() => json(ROW, 201));
  try {
    await routines.createRoutine(3, input);
    await routines.updateRoutine(31, { ...input, class_id: 99 });
  } finally {
    restore();
  }
  assert.equal(calls[0].method, "POST");
  assert.equal(calls[0].body.class_id, 3);

  assert.equal(calls[1].method, "PUT");
  assert.equal(calls[1].url, "/api/routines/31");
  assert.equal("class_id" in calls[1].body, false, "런타임의 추가 필드를 빼고 보낸다");
  assert.deepEqual(Object.keys(calls[1].body).sort(), [
    "date",
    "end",
    "execution",
    "name",
    "plan",
    "position",
    "start",
  ]);
});

test("삭제는 204 라 본문이 없다", async () => {
  browser();
  const { calls, restore } = serve(() => new Response(null, { status: 204 }));
  try {
    assert.equal(await routines.deleteRoutine(31), undefined);
  } finally {
    restore();
  }
  assert.equal(calls[0].method, "DELETE");
  assert.equal(calls[0].url, "/api/routines/31");
});

test("시간은 분까지만 쓰고, 빈 칸은 null 로 보낸다", () => {
  assert.equal(routines.routineTime("09:20:00"), "09:20");
  assert.equal(routines.routineTime(null), "");
  assert.equal(routines.routineTimeValue(""), null);
  assert.equal(routines.routineTimeValue("09:20"), "09:20");
});

test("화면 id 는 서버 id 와 섞이지 않는다", () => {
  assert.equal(routines.routineLocalId(31), "routine:31");
  assert.equal(routines.routineServerId("routine:31"), 31);
  for (const bad of ["observation:31", "routine:0", "routine:-1", "routine:x", "31", ""])
    assert.equal(routines.routineServerId(bad), null, bad);
});

test("근거 사본 한 줄은 서버의 fact_text 와 같은 모양이다", () => {
  assert.equal(
    routines.routineFactText(ROW),
    "[오전 실내놀이 09:20~10:40] 블록 3개로 길을 만들었다.",
  );
  assert.equal(
    routines.routineFactText({ ...ROW, start: null, end: null }),
    "[오전 실내놀이] 블록 3개로 길을 만들었다.",
  );
});

// ── 3. 화면 ────────────────────────────────────────────────────────────────

const OBSERVATION_DOMAINS = ["신체운동·건강", "의사소통", "사회관계", "예술경험", "자연탐구"];
const jsx = (type, props, key) => ({ type, props, key });
const runtime = { jsx, jsxs: jsx, Fragment: "fragment" };
const settle = () => new Promise((resolve) => setImmediate(resolve));
const compile = (path, modules) => {
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
  const compiled = { exports: {} };
  new Function("require", "module", "exports", code)(
    (name) => {
      assert.ok(name in modules, `unhandled import: ${name}`);
      return modules[name];
    },
    compiled,
    compiled.exports,
  );
  return compiled.exports;
};
const { WorkspaceViewState } = compile("../components/workspace/WorkspaceViewState.tsx", {
  "react/jsx-runtime": runtime,
  "./WorkspaceUI": { Message: "message", ws: {} },
});
const all = (node) => {
  if (Array.isArray(node)) return node.flatMap(all);
  if (node === null || node === undefined || typeof node === "boolean") return [];
  return typeof node === "object" ? [node, ...all(node.props?.children)] : [node];
};
/**
 * 중첩된 자리까지 내려가 글자만 모은다.
 *
 * 바로 아래 children 만 이으면 안 되는 자리가 있다 — 아이 타일은 이름이 안쪽 span 에
 * 있어서 `[object Object]` 가 나온다.
 */
const deepText = (node) =>
  all(node)
    .filter((part) => typeof part === "string" || typeof part === "number")
    .join("");

/**
 * React 흉내. hook 자리를 **컴포넌트 이름 + key** 로 나눠, 행 순서가 바뀌어도 각 행이
 * 자기 입력을 그대로 들고 간다. (같은 부모 아래 key 없는 동종 형제는 못 가른다.)
 */
function host() {
  const boxes = new Map();
  const effects = {};
  const pending = [];
  // 이번 그림에 실제로 나온 컴포넌트들. 안 나온 것은 unmount 로 보고 상태와 effect 를 버린다.
  let drawn = new Set();
  let scope = "";
  const box = () => {
    let found = boxes.get(scope);
    if (!found) boxes.set(scope, (found = { slots: [], setters: [], cursor: 0 }));
    return found;
  };
  const state = (initial) => {
    const self = box();
    const index = self.cursor++;
    if (!(index in self.slots)) {
      self.slots[index] = typeof initial === "function" ? initial() : initial;
      self.setters[index] = (next) => {
        self.slots[index] = typeof next === "function" ? next(self.slots[index]) : next;
      };
    }
    return [self.slots[index], self.setters[index]];
  };
  const effect = (fn, deps) => {
    const index = `${scope}#${box().cursor++}`;
    const prev = effects[index];
    if (!prev || !deps || deps.some((dep, i) => !Object.is(dep, prev.deps[i]))) {
      prev?.cleanup?.();
      effects[index] = { deps: deps ?? [] };
      pending.push(() => {
        // 큐에 넣은 뒤 그 줄이 사라졌을 수 있다 (날짜를 옮기면 줄이 통째로 바뀐다).
        // React 도 사라진 컴포넌트의 effect 는 돌리지 않는다.
        if (effects[index]) effects[index].cleanup = fn();
      });
    }
  };
  const react = {
    useState: state,
    useMemo: (fn) => fn(),
    // deps 가 그대로면 같은 함수를 돌려준다 — effect 가 매번 다시 돌지 않게.
    useCallback: (fn, deps) => {
      const [kept] = state(() => ({ fn, deps: deps ?? [] }));
      if (
        !deps ||
        deps.length !== kept.deps.length ||
        deps.some((d, i) => !Object.is(d, kept.deps[i]))
      ) {
        kept.fn = fn;
        kept.deps = deps ?? [];
      }
      return kept.fn;
    },
    useRef: (initial) => state(() => ({ current: initial }))[0],
    useSyncExternalStore: (_subscribe, get) => get(),
    useEffect: effect,
    useLayoutEffect: effect,
  };
  const resolve = (node, path = "") => {
    if (Array.isArray(node)) return node.map((child) => resolve(child, path));
    if (!node || typeof node !== "object") return node;
    if (typeof node.type === "function") {
      const id = `${path}/${node.type.name}#${node.key ?? ""}`;
      drawn.add(id);
      const outer = scope;
      scope = id;
      box().cursor = 0;
      const out = node.type(node.props);
      scope = outer;
      return resolve(out, id);
    }
    return { ...node, props: { ...node.props, children: resolve(node.props?.children, path) } };
  };
  return {
    react,
    state,
    cleanup: () => Object.values(effects).forEach((effect) => effect?.cleanup?.()),
    mount(Page) {
      let tree = null;
      const render = () => {
        scope = "";
        drawn = new Set([""]);
        box().cursor = 0;
        tree = resolve(Page());
        // React 처럼 사라진 컴포넌트는 상태를 들고 있지 않는다 — 다시 나오면 처음부터다.
        for (const id of [...boxes.keys()]) if (!drawn.has(id)) boxes.delete(id);
        for (const id of Object.keys(effects))
          if (!drawn.has(id.slice(0, id.lastIndexOf("#")))) {
            effects[id].cleanup?.();
            delete effects[id];
          }
      };
      render();
      return {
        render,
        tree: () => tree,
        async flush(times = 5) {
          for (let i = 0; i < times; i++) {
            render();
            pending.splice(0).forEach((fn) => fn());
            await settle();
          }
          render();
        },
      };
    },
  };
}

// A mock API module outlives its pages; separate mock servers keep unrelated tests isolated.
const routineMutationBarriers = new WeakMap();

const row = (over) => ({ ...ROW, ...over });
const TODAY = "2026-10-06";
const AUTOSAVE_MS = 800;
/** 한 시험에서 연 일과 화면 수. 마지막 화면이 내려간 뒤에 브라우저 흉내를 치운다. */
let openPages = 0;

/** 서버가 낸 409 STALE_WRITE 와 같은 모양. 화면은 `isStaleWrite` 로만 가른다. */
const staleWrite = () =>
  Object.assign(new Error("다른 화면에서 먼저 고쳤습니다."), { code: "STALE_WRITE" });

/**
 * 하루치 서버. **오간 요청을 전부 적어 둔다** — 「손대기 전에는 아무것도 안 보낸다」는
 * 보낸 게 없다는 것으로만 증명된다.
 *
 * 임시본(`PUT /api/routines/draft`)은 서버(`routines/drafts.py`)와 같은 규칙으로 흉내 낸다 —
 * 판 번호가 다르면 409, `promote` 면 손댄 줄만 일과 기록으로 만들고 · 바꾸고 · 지운다.
 * 올리는 규칙 자체는 서버 시험(`test_routine_drafts.py`)이 본다. 여기서 보는 것은 화면이
 * **무엇을 언제 보내나**다.
 */
function recorder({ rows = [], preset = null, drafts = [], weather = null } = {}) {
  const calls = [];
  const serverTime = (time) =>
    typeof time === "string" && time.length === 5 ? `${time}:00` : time;
  const stored = (routine) => ({
    ...routine,
    start: serverTime(routine.start),
    end: serverTime(routine.end),
  });
  let store = rows.map(stored);
  const saved = new Map(drafts.map((d) => [`${d.class_id}|${d.date}`, d]));
  let nextId = 900;
  const fails = new Set();
  const only = (op) => calls.filter((c) => c.op === op);
  const ofDay = (classId, date) =>
    store
      .filter((r) => r.date === date && r.class_id === classId)
      .map((r) => ({ ...r }))
      .sort(
        (a, b) =>
          a.position - b.position ||
          (a.start ?? "99").localeCompare(b.start ?? "99") ||
          a.id - b.id,
      );
  const filled = (r) =>
    (r.touched || r.id !== null) &&
    Boolean(r.start || r.end || r.name.trim() || r.plan.trim() || r.execution.trim());
  return {
    calls,
    only,
    rows: () => store,
    drafts: saved,
    /** 다음 요청 하나를 실패시킨다 — `"day"` · `"draft"`. */
    failNext: (op) => fails.add(op),
    api: {
      day: async (classId, date) => {
        calls.push({ op: "day", classId, date });
        if (fails.delete("day")) throw new Error("일과를 불러오지 못했어요.");
        const items = ofDay(classId, date);
        return {
          items,
          weather,
          draft: saved.get(`${classId}|${date}`) ?? null,
          preset: items.length ? null : preset,
        };
      },
      saveDraft: async (input, options) => {
        calls.push({ op: "draft", input, options });
        if (fails.delete("draft")) throw new Error("저장하지 못했어요");
        const key = `${input.class_id}|${input.date}`;
        const before = saved.get(key);
        if ((before?.revision ?? 0) !== input.expected_revision) throw staleWrite();
        const rows = input.rows.map((r) => ({ ...r }));
        let items = null;
        if (input.promote) {
          store = store.filter((r) => !input.removed.includes(r.id));
          rows.forEach((r, i) => {
            if (!filled(r)) return;
            const values = { ...r, date: input.date, class_id: input.class_id, position: i };
            delete values.touched;
            if (r.id !== null && store.some((s) => s.id === r.id)) {
              store = store.map((s) => (s.id === r.id ? stored({ ...s, ...values }) : s));
            } else {
              rows[i] = { ...r, id: (nextId += 1) };
              store = [...store, stored({ ...ROW, ...values, id: nextId })];
            }
          });
          items = ofDay(input.class_id, input.date);
        }
        const draft = {
          class_id: input.class_id,
          date: input.date,
          revision: (before?.revision ?? 0) + 1,
          rows,
          removed: input.promote ? [] : input.removed,
          promoted: input.promote,
          updated_at: "",
        };
        saved.set(key, draft);
        return {
          draft,
          items,
          review_impact: input.promote
            ? { affected_document_ids: [], newly_stale_document_ids: [] }
            : null,
        };
      },
      weather: async (choice) => {
        calls.push({ op: "weather", choice });
        return {
          date: choice.date,
          sky: choice.sky,
          dust: null,
          source: "teacher",
          indoor_hint: null,
        };
      },
      template: async (classId) => {
        calls.push({ op: "template", classId });
        return null;
      },
      saveTemplate: async (classId, rows) => {
        calls.push({ op: "saveTemplate", classId, rows });
        return { class_id: classId, rows };
      },
    },
  };
}

/**
 * 일과 기록 화면 하나. `api` 가 서버 노릇을 한다.
 *
 * **주 반 · 서버 반 번호 · canonical route 는 진짜 모듈을 쓴다.** 이 셋을 흉내 내면
 * 「주 반이 없으면 첫 반을 고른다」 같은 production 버그가 테스트를 그대로 통과한다.
 */
function page(
  t,
  api,
  {
    search = "",
    classes,
    rooms = [CLASS_A],
    primaryClassId = "class-abc",
    confirm = true,
    extras = { plan: null, observations: [] },
    yesterday = null,
  } = {},
) {
  const confirms = browser({ rooms, primaryClassId, search, confirm });
  const pushed = [];
  /** 「오늘 일지 만들기」가 넘긴 근거 목록. 화면을 떠나지 않으므로 `pushed` 로는 못 본다. */
  const journals = [];

  const app = host();
  let mutations = routineMutationBarriers.get(api);
  if (!mutations) {
    mutations = createMutationBarrier();
    routineMutationBarriers.set(api, mutations);
  }
  const css = {};
  // 시계 · 달력 · 날씨 · 줄 아래 칸은 **진짜로** 컴파일한다. 스텁으로 두면 시간 칸과 날짜 단추가
  // 트리에서 사라져, 「시간을 적었다」는 테스트가 아무것도 보지 못한 채 통과한다.
  const clock = compile("../components/workspace/RoutineClock.tsx", {
    "react/jsx-runtime": runtime,
    react: app.react,
    "./WorkspaceUI": { ws: {} },
  });
  const calendar = compile("../components/workspace/RoutineCalendar.tsx", {
    "react/jsx-runtime": runtime,
    "./WorkspaceUI": { ws: {} },
  });
  const weatherMark = compile("../components/workspace/RoutineWeather.tsx", {
    "react/jsx-runtime": runtime,
    react: app.react,
    "./RoutineDay.module.css": { __esModule: true, default: css },
  });
  const rowExtras = compile("../components/workspace/RoutineRowExtras.tsx", {
    "react/jsx-runtime": runtime,
    "./RoutineDay.module.css": { __esModule: true, default: css },
  });
  const Page = compile("../components/workspace/RoutinesPage.tsx", {
    "react/jsx-runtime": runtime,
    react: app.react,
    "./RoutineClock": clock,
    "./RoutineCalendar": calendar,
    "./RoutineWeather": weatherMark,
    "./RoutineRowExtras": rowExtras,
    "./use-day-extras": { useDayExtras: () => extras },
    "./RoutineDay.module.css": { __esModule: true, default: css },
    // 포스티는 제 파일에서 본다. 여기서 보는 것은 고칠 줄 목록이다.
    "@/components/app/Posty": { Posty: "posty" },
    "next/link": { default: "link" },
    "next/navigation": { useRouter: () => ({ push: (href) => pushed.push(href) }) },
    "@/lib/api/auth": { getMe: async () => ({ id: 1, center_id: 42 }) },
    "@/lib/api/classes": {
      isMyClass: (c) => c.my_access !== "NONE",
      getClasses: async () => ({ items: classes ?? [{ id: 3, name: "햇살반" }] }),
    },
    "@/lib/api/client": { isUnauthenticated: () => false },
    "@/lib/api/documents": { isStaleWrite: (e) => e?.code === "STALE_WRITE" },
    "@/lib/api/onboarding": onboardingApi,
    "@/lib/onboarding/settings": classSettings,
    "@/lib/workspace/routines-route": routinesRoute,
    "@/lib/workspace/journal-day": journalDay,
    "@/lib/hooks/use-client-state": { useClientState: (read) => app.state(read) },
    "@/lib/hooks/use-unsaved-warning": { useUnsavedWarning: () => {} },
    "@/lib/api/routines": {
      getRoutineDay: api.day,
      saveRoutineDraft: api.saveDraft,
      chooseRoutineWeather: api.weather,
      getRoutineTemplate: api.template,
      saveRoutineTemplate: api.saveTemplate,
      trackRoutineMutation: mutations.track,
      waitForRoutineScope: mutations.wait,
      // 달력 점은 적는 화면의 하루치 조회와 따로다. 섞으면 「하루만 읽는다」를 못 센다.
      listRoutineDates: async () => [],
      routineLocalId: routines.routineLocalId,
      routineTime: routines.routineTime,
      sortRoutinesByTime: routines.sortRoutinesByTime,
    },
    // 일지 칸 자체는 제 파일에서 본다. 여기서는 **근거로 무엇을 넘겼나**만 적어 둔다.
    "./DailyJournalCard": {
      __esModule: true,
      default: "daily-journal",
      DailyJournalEditor: "daily-journal-editor",
      useDailyJournal: () => ({
        doc: null,
        busy: false,
        error: "",
        yesterday,
        make: async (ids) => void journals.push(ids),
        off: true,
        leave: () => true,
      }),
    },
    "@/lib/workspace/model": {
      today: () => TODAY,
      validDate: (value) => /^\d{4}-\d{2}-\d{2}$/.test(value),
    },
    // 제목 옆 단추는 `action` 으로 간다. 글자 하나로 스텁을 두면 그 묶음이 트리에서
    // 빠져(`all()` 은 children 만 내려간다) 단추를 영영 못 찾는다.
    "./WorkspaceUI": {
      WorkspacePage: function WorkspacePage({ action, children }) {
        return jsx("page", { children: [action, children] });
      },
      Empty: "empty",
      JournalTabs: "journal-tabs",
      Message: "message",
      Notice: "notice",
      ws: {},
    },
    "./WorkspaceViewState": { WorkspaceViewState },
  }).default;

  const view = app.mount(Page);
  // 화면을 먼저 내리고(떠날 때 올리기까지 돈다) 마지막 화면이 내려간 뒤 브라우저를 치운다.
  openPages += 1;
  t.after(() => {
    app.cleanup();
    if (--openPages) return;
    delete globalThis.window;
    delete globalThis.document;
  });

  const find = (type) => all(view.tree()).filter((node) => node?.type === type);
  const labelled = (node) => String([node.props.children].flat().join(""));
  /** 글자가 「×」뿐인 단추는 aria-label 이 이름이다. */
  const named = (node) => labelled(node) + " " + (node.props["aria-label"] ?? "");
  return {
    confirms,
    pushed,
    journals,
    unmount: app.cleanup,
    flush: view.flush,
    render: view.render,
    /** 지금 주소창의 질의. 화면이 적어 둔 반 · 날짜가 여기 보여야 한다. */
    search: () => globalThis.window.location.search,
    dateInput: () => find("input").find((node) => node.props.type === "date"),
    /** 이름 칸들. 줄 순서 그대로다. */
    names: () => find("input").filter((node) => node.props.maxLength === 50),
    nameValues: () =>
      find("input")
        .filter((n) => n.props.maxLength === 50)
        .map((n) => n.props.value),
    /** 시작 · 종료 한 칸씩. 줄 순서대로 start, end, start, end … 로 나온다. */
    times: () => find("input").filter((node) => node.props.type === "time"),
    textareas: () => find("textarea"),
    /** 줄마다 「실제로 한 것」 하나. 「계획한 것」은 접힌 칸 안에 따로 있다. */
    dones: () => find("textarea").filter((n) => n.props["aria-label"] === "실제로 한 것"),
    checkboxes: () => find("input").filter((node) => node.props.type === "checkbox"),
    cards: () => find("article"),
    empties: () => find("empty").map((node) => node.props.title),
    loading: () => all(view.tree()).some((node) => node?.props?.["aria-busy"] === "true"),
    errors: () => find("message").map((node) => String(node.props.children ?? "")),
    text: () => deepText(view.tree()),
    /** 그 줄 안의 버튼. 줄마다 같은 이름의 버튼이 있어 전체에서 찾으면 첫 줄만 눌린다. */
    rowButton: (index, label) =>
      all(find("article")[index]).find(
        (node) => node?.type === "button" && named(node).includes(label),
      ),
    button: (label) =>
      find("button").find((node) => named(node).includes(label) && !node.props.disabled),
    type: (node, value) => node.props.onChange({ target: { value } }),
  };
}

const fill = (view, index, value) => view.type(view.names()[index], value);
/** 멈춘 뒤 자동 저장 시간이 지난다. */
const pause = async (t, view) => {
  await view.flush();
  t.mock.timers.tick(AUTOSAVE_MS);
  await view.flush();
};
const timers = (t) => t.mock.timers.enable({ apis: ["setTimeout"] });

// ── 주소 · 반 고르기 (S-J1 canonical route) ────────────────────────────────

test("주소의 날짜 · 반으로 하루 하나를 연다", async (t) => {
  const api = recorder();
  const view = page(t, api.api, {
    search: "?date=2026-10-02&class_id=7",
    classes: [
      { id: 3, name: "햇살반" },
      { id: 7, name: "별빛반" },
    ],
  });
  await view.flush();
  // 줄 · 날씨 · 임시본 · 깔 줄이 한 번에 온다 — 어제를 따로 읽지 않는다.
  assert.deepEqual(api.only("day").at(-1), { op: "day", classId: 7, date: "2026-10-02" });
  assert.equal(view.dateInput().props.value, "2026-10-02");
});

test("주소에 아무것도 없으면 오늘 · 주 반이다", async (t) => {
  const api = recorder();
  const view = page(t, api.api);
  await view.flush();
  assert.deepEqual(api.only("day").at(-1), { op: "day", classId: 3, date: TODAY });
});

test("주 반이 없으면 첫 반을 대신 고르지 않는다 — 고르라고 한다", async (t) => {
  const api = recorder();
  // 반은 둘인데 **교사가 주 반을 고른 적이 없다.** 진짜 settings 저장/읽기를 거친다.
  const view = page(t, api.api, {
    rooms: [CLASS_A, CLASS_B],
    primaryClassId: "",
    classes: [
      { id: 3, name: "햇살반" },
      { id: 7, name: "별빛반" },
    ],
  });
  await view.flush();
  assert.deepEqual(api.only("day"), [], "반을 모르면 묻지 않는다");
  assert.deepEqual(view.empties(), ["반을 골라주세요"]);
});

test("주소의 반 번호가 목록에 없으면 첫 반으로 조용히 바꾸지 않는다", async (t) => {
  const api = recorder();
  const view = page(t, api.api, { search: "?class_id=99" });
  await view.flush();
  assert.deepEqual(api.only("day"), []);
  assert.deepEqual(view.empties(), ["반을 골라주세요"]);
  assert.match(view.text(), /주소에 적힌 반을 찾을 수 없어요/);
});

// ── 하루를 깐다 (S-J1 · ADR-085) ──────────────────────────────────────────

test("그날도 깔 것도 없으면 표준 하루를 깐다 — 교사는 실제로 한 것만 적는다", async (t) => {
  const api = recorder();
  const view = page(t, api.api);
  await view.flush();
  assert.equal(view.names().length, 10);
  assert.equal(view.nameValues()[0], "등원 및 통합보육");
  assert.deepEqual(
    view
      .times()
      .slice(0, 2)
      .map((n) => n.props.value),
    ["07:30", "09:00"],
  );
  assert.equal(view.dones().length, 10, "줄마다 「실제로 한 것」 하나");
  assert.deepEqual(view.empties(), [], "하루를 깔았으니 「없어요」가 아니다");
});

test("이미 적은 줄이 있으면 그 줄만 편다", async (t) => {
  const api = recorder({ rows: [row({ id: 1 }), row({ id: 2, name: "바깥놀이" })] });
  const view = page(t, api.api);
  await view.flush();
  assert.deepEqual(view.nameValues(), ["오전 실내놀이", "바깥놀이"]);
});

test("서버가 정한 깔 줄을 시간순으로 깔고, 어디서 왔는지 한 줄로 말한다", async (t) => {
  const api = recorder({
    preset: {
      source: "last_week",
      from_date: "2026-09-29",
      rows: [
        { name: "특별활동(체육)", start: "10:40:00", end: "11:00:00" },
        { name: "등원", start: "07:30:00", end: "09:00:00" },
      ],
    },
  });
  const view = page(t, api.api);
  await view.flush();
  assert.deepEqual(view.nameValues(), ["등원", "특별활동(체육)"]);
  assert.match(view.text(), /9월 29일 \(화\) 일과로 깔았어요/);
  // 적은 글은 옮겨 오지 않는다 — 실제로 한 것은 비어 있다.
  assert.deepEqual(
    view.dones().map((n) => n.props.value),
    ["", ""],
  );
});

test("안 올라간 임시본이 있으면 그것을 편다 — 다른 기기에서 쓴 글도 이어서 쓴다", async (t) => {
  const api = recorder({
    rows: [row({ id: 1, execution: "올라간 글" })],
    drafts: [
      {
        class_id: 3,
        date: TODAY,
        revision: 4,
        rows: [
          {
            ...row({ id: 1 }),
            execution: "폰에서 고친 글",
            touched: true,
            reflected: false,
            activities: [],
          },
        ],
        removed: [],
        promoted: false,
        updated_at: "",
      },
    ],
  });
  const view = page(t, api.api);
  timers(t);
  await view.flush();
  assert.deepEqual(
    view.dones().map((n) => n.props.value),
    ["폰에서 고친 글"],
  );
  view.type(view.dones()[0], "PC 에서 이어 씀");
  await pause(t, view);
  assert.equal(api.only("draft")[0].input.expected_revision, 4, "판 번호를 이어받는다");
});

// ── 자동 저장 — 쓰는 대로 임시본에 (ADR-084) ───────────────────────────────

test("손대기 전에는 임시본도 일과 기록도 보내지 않는다 — 떠나도 그대로다", async (t) => {
  const api = recorder();
  const view = page(t, api.api);
  timers(t);
  await view.flush();
  await pause(t, view);
  view.type(view.dateInput(), "2026-10-07");
  await view.flush();
  view.unmount();
  await settle();
  assert.deepEqual(api.only("draft"), []);
});

test("쓰고 멈추면 임시본만 둔다 — 깔아 둔 줄은 손대지 않은 줄로 간다", async (t) => {
  const api = recorder();
  const view = page(t, api.api);
  timers(t);
  await view.flush();
  view.type(view.dones()[0], "엄마와 인사하고 들어왔어요.");
  await view.flush();
  assert.deepEqual(api.only("draft"), [], "멈추기 전에는 보내지 않는다");

  await pause(t, view);
  const [sent] = api.only("draft");
  assert.equal(sent.input.promote, false, "쓰는 동안은 근거로 올리지 않는다");
  assert.equal(sent.input.expected_revision, 0);
  assert.equal(sent.input.rows.length, 10);
  assert.deepEqual(
    [sent.input.rows[0].touched, sent.input.rows[0].execution, sent.input.rows[0].start],
    [true, "엄마와 인사하고 들어왔어요.", "07:30"],
  );
  assert.equal(sent.input.rows[1].touched, false);
  assert.equal(api.rows().length, 0, "일과 기록은 그대로다");
  assert.match(view.text(), /저장됨/);

  // 이어서 쓰면 앞 요청이 받은 판 번호를 따라간다.
  view.type(view.dones()[0], "엄마와 인사했어요.");
  await pause(t, view);
  assert.equal(api.only("draft")[1].input.expected_revision, 1);
});

test("임시본을 못 두면 「저장 못 했어요」와 다시 단추 — 누르면 다시 보낸다", async (t) => {
  const api = recorder();
  const view = page(t, api.api);
  timers(t);
  await view.flush();
  api.failNext("draft");
  view.type(view.dones()[0], "블록을 쌓았다.");
  await pause(t, view);
  assert.match(view.text(), /저장 못 했어요/);
  assert.equal(view.dones()[0].props.value, "블록을 쌓았다.", "적은 글자는 그대로다");

  view.button("다시 저장").props.onClick();
  await view.flush();
  assert.equal(api.only("draft").length, 2);
  assert.match(view.text(), /저장됨/);
});

test("다른 화면이 먼저 고쳤으면 덮지 않고, 다시 불러오면 그 글을 편다", async (t) => {
  const api = recorder();
  const view = page(t, api.api);
  timers(t);
  await view.flush();
  // 그 사이 다른 기기가 같은 날 임시본을 두었다.
  api.drafts.set(`3|${TODAY}`, {
    class_id: 3,
    date: TODAY,
    revision: 1,
    rows: [
      {
        ...row({ id: null }),
        name: "폰에서 쓴 줄",
        touched: true,
        reflected: false,
        activities: [],
      },
    ],
    removed: [],
    promoted: false,
    updated_at: "",
  });
  view.type(view.dones()[0], "옛 탭에서 친 글");
  await pause(t, view);
  assert.match(view.text(), /다른 화면에서 먼저 고쳤어요/);
  assert.equal(api.drafts.get(`3|${TODAY}`).rows[0].name, "폰에서 쓴 줄", "덮지 않았다");

  view.button("다시 불러오기").props.onClick();
  await view.flush();
  assert.deepEqual(view.nameValues(), ["폰에서 쓴 줄"]);
});

// ── 근거로 올리기 — 떠날 때 · 일지 만들 때 (ADR-084) ───────────────────────

test("날짜를 옮기면 앞 하루를 근거로 올린다 — 요청 하나, 창을 닫아도 가는 keepalive", async (t) => {
  const api = recorder();
  const view = page(t, api.api);
  timers(t);
  await view.flush();
  view.type(view.dones()[2], "블록으로 길을 만들었다.");
  await view.flush();
  view.type(view.dateInput(), "2026-10-07");
  await view.flush();
  const [sent] = api.only("draft");
  assert.equal(sent.input.date, TODAY, "떠난 날을 올린다");
  assert.equal(sent.input.promote, true);
  assert.deepEqual(sent.options, { keepalive: true });
  assert.deepEqual(
    api.rows().map((r) => [r.name, r.execution]),
    [["오전 실내놀이", "블록으로 길을 만들었다."]],
    "손대지 않은 아홉 줄은 올라가지 않는다",
  );
  assert.equal(view.dateInput().props.value, "2026-10-07", "묻지 않고 옮긴다");
});

test("화면이 사라져도(다른 메뉴 · 창 닫기) 안 올라간 하루를 올린다", async (t) => {
  const api = recorder({ rows: [row({ id: 1 })] });
  const view = page(t, api.api);
  timers(t);
  await view.flush();
  view.type(view.dones()[0], "고친 글");
  await view.flush();
  view.unmount();
  await settle();
  await settle();
  assert.equal(api.only("draft").at(-1).input.promote, true);
  assert.equal(api.rows()[0].execution, "고친 글");
});

test("고친 것이 없으면 떠날 때 아무것도 보내지 않는다", async (t) => {
  const api = recorder({ rows: [row({ id: 1 })] });
  const view = page(t, api.api);
  await view.flush();
  view.type(view.dateInput(), "2026-10-07");
  await view.flush();
  assert.deepEqual(api.only("draft"), []);
});

test("이름 없는 줄이 있으면 떠날 때 올리지 않고 임시본만 둔다 — 다음에 열면 그대로다", async (t) => {
  const api = recorder({ rows: [row({ id: 1 })] });
  const view = page(t, api.api);
  timers(t);
  await view.flush();
  view.button("+ 줄 추가").props.onClick();
  view.render();
  view.type(view.dones()[1], "이름을 안 적은 줄");
  await view.flush();
  view.type(view.dateInput(), "2026-10-07");
  await view.flush();
  const [sent] = api.only("draft");
  assert.equal(sent.input.promote, false);
  assert.equal(api.rows().length, 1, "일과 기록은 그대로다");

  view.type(view.dateInput(), TODAY);
  await view.flush();
  assert.deepEqual(
    view.dones().map((n) => n.props.value),
    [ROW.execution, "이름을 안 적은 줄"],
  );
});

test("지운 줄은 임시본에 표시만 하고, 올릴 때 서버가 지운다", async (t) => {
  const api = recorder({ rows: [row({ id: 1 }), row({ id: 2, name: "바깥놀이" })] });
  const view = page(t, api.api);
  timers(t);
  await view.flush();
  view.rowButton(0, "일과 지우기").props.onClick();
  await pause(t, view);
  assert.deepEqual(view.nameValues(), ["바깥놀이"]);
  assert.deepEqual(api.only("draft")[0].input.removed, [1]);
  assert.equal(api.rows().length, 2, "올리기 전에는 그대로다");

  view.button("오늘 일지 만들기").props.onClick();
  await view.flush();
  assert.deepEqual(
    api.rows().map((r) => r.id),
    [2],
  );
});

// ── 오늘 일지 만들기 (S-J1 수락 기준 3 · 3-1 · 3-2) ────────────────────────

test("올리지 않은 활동실행만으로도 「오늘 일지 만들기」가 켜진다", async (t) => {
  const api = recorder();
  const view = page(t, api.api);
  await view.flush();
  assert.equal(view.button("오늘 일지 만들기"), undefined, "적은 게 없으면 꺼져 있다");
  view.type(view.dones()[0], "블록을 쌓았다");
  await view.flush();
  assert.ok(view.button("오늘 일지 만들기"));
});

test("올린 뒤 실제로 한 것을 적은 줄의 일과 번호로 일지를 만든다", async (t) => {
  const api = recorder({ rows: [row({ id: 1, execution: "" })] });
  const view = page(t, api.api);
  await view.flush();
  view.type(view.dones()[0], "블록을 쌓았다");
  view.button("+ 줄 추가").props.onClick();
  view.render();
  fill(view, 1, "바깥놀이");
  view.render();
  view.type(view.dones()[1], "모래놀이");
  await view.flush();

  view.button("오늘 일지 만들기").props.onClick();
  await view.flush();
  const [sent] = api.only("draft");
  assert.equal(sent.input.promote, true);
  assert.deepEqual(view.journals, [["routine:1", "routine:901"]]);
  assert.equal(api.only("draft").length, 1, "다시 읽고 떠나도 또 올리지 않는다");
});

test("이름 없이 활동실행만 적었으면 그 줄을 짚고 아무것도 보내지 않는다", async (t) => {
  const api = recorder();
  const view = page(t, api.api);
  await view.flush();
  view.button("+ 줄 추가").props.onClick();
  view.render();
  view.type(view.dones()[10], "이름을 안 적었다");
  await view.flush();
  view.button("오늘 일지 만들기").props.onClick();
  await view.flush();
  assert.deepEqual(api.only("draft"), []);
  assert.deepEqual(view.journals, []);
  assert.match(view.text(), /고칠 곳이 1군데 있어요/);
  assert.equal(view.dones()[10].props.value, "이름을 안 적었다");
});

test("올리기가 실패하면 일지를 만들지 않고 적은 글자를 그대로 둔다", async (t) => {
  const api = recorder();
  const view = page(t, api.api);
  await view.flush();
  view.type(view.dones()[0], "블록을 쌓았다");
  await view.flush();
  api.failNext("draft");
  view.button("오늘 일지 만들기").props.onClick();
  await view.flush();
  assert.deepEqual(view.journals, []);
  assert.ok(view.errors().includes("저장하지 못했어요"), view.errors());
  assert.equal(view.dones()[0].props.value, "블록을 쌓았다");
});

test("두 번 눌러도 한 번만 올리고 한 번만 만든다", async (t) => {
  const api = recorder();
  const view = page(t, api.api);
  await view.flush();
  view.type(view.dones()[0], "블록을 쌓았다");
  await view.flush();
  const press = view.button("오늘 일지 만들기").props.onClick;
  press();
  press();
  await view.flush();
  assert.equal(api.only("draft").length, 1);
  assert.equal(view.journals.length, 1);
});

// ── 늦게 온 응답 (기존 보호 장치 회귀) ─────────────────────────────────────

test("날짜를 바꾸면 그 날짜의 하루만 읽는다 — A → B → A 로 돌아와도 섞이지 않는다", async (t) => {
  const api = recorder({
    rows: [
      row({ id: 1, name: "A 의 일과" }),
      row({ id: 2, date: "2026-10-07", name: "B 의 일과" }),
    ],
  });
  const view = page(t, api.api);
  await view.flush();
  assert.deepEqual(view.nameValues(), ["A 의 일과"]);

  view.type(view.dateInput(), "2026-10-07");
  await view.flush();
  assert.deepEqual(view.nameValues(), ["B 의 일과"]);

  view.type(view.dateInput(), TODAY);
  await view.flush();
  assert.deepEqual(view.nameValues(), ["A 의 일과"]);
  assert.deepEqual(
    api.only("day").map((c) => c.date),
    [TODAY, "2026-10-07", TODAY],
  );
});

test("날짜를 비우면 조회하지 않고, 불러오는 중으로 남지도 않는다", async (t) => {
  const api = recorder();
  const view = page(t, api.api);
  await view.flush();
  const before = api.only("day").length;
  view.type(view.dateInput(), "");
  await view.flush();
  assert.equal(api.only("day").length, before);
  assert.equal(view.loading(), false);
  assert.deepEqual(view.empties(), ["날짜를 선택해주세요"]);
});

test("조회 실패는 「없어요」가 아니라 실패로 보여주고 다시 시도할 수 있다", async (t) => {
  const api = recorder({ rows: [row({ id: 1 })] });
  api.failNext("day");
  const view = page(t, api.api);
  await view.flush();
  assert.deepEqual(view.empties(), []);
  assert.ok(view.errors().some((text) => text.includes("일과를 불러오지 못했어요")));

  view.button("다시 시도").props.onClick();
  await view.flush();
  assert.deepEqual(view.nameValues(), ["오전 실내놀이"]);
});

// ── P1-1 · 주 반을 고른 적이 없다 (진짜 settings helper) ────────────────────

test("P1-1 저장된 설정에 주 반이 없으면 어떤 helper 도 첫 반을 고르지 않는다", () => {
  browser({ rooms: [CLASS_A, CLASS_B], primaryClassId: "" });
  const stored = classSettings.loadClassSettings();
  assert.equal(stored.primaryClassId, "", "정규화가 첫 반을 몰래 채우지 않는다");
  assert.equal(classSettings.chosenClassFor(stored), null, "고른 반이 없다");
  // 계획안 · 사이드바 제목처럼 「아무 반이나 하나」로 충분한 곳은 그대로 둔다.
  assert.equal(classSettings.primaryClassFor(stored).id, CLASS_A.id);
  delete globalThis.window;
  delete globalThis.document;
});

test("P1-1 주 반을 고르면 그 반이다", () => {
  browser({ rooms: [CLASS_A, CLASS_B], primaryClassId: CLASS_B.id });
  const stored = classSettings.loadClassSettings();
  assert.equal(classSettings.chosenClassFor(stored).id, CLASS_B.id);
  assert.equal(onboardingApi.classServerId(CLASS_B.id), 7);
  delete globalThis.window;
  delete globalThis.document;
});

// ── P1-2 · 올리기가 끝났을 때 아직 그 화면인가 ──────────────────────────────

/** 「오늘 일지 만들기」를 누르고, 올리는 요청을 붙잡아 둔다. */
async function heldUpload(t) {
  const api = recorder();
  const save = api.api.saveDraft;
  let release = () => {};
  api.api.saveDraft = (input, options) =>
    input.promote && !options?.keepalive
      ? new Promise((resolve) => {
          release = () => resolve(save(input, options));
        })
      : save(input, options);
  const view = page(t, api.api);
  await view.flush();
  view.type(view.dones()[0], "블록을 쌓았다");
  await view.flush();
  view.button("오늘 일지 만들기").props.onClick();
  await view.flush();
  assert.deepEqual(view.journals, [], "올리기가 끝나기 전에는 만들지 않는다");
  return { api, view, release: () => release() };
}

test("P1-2 올리기를 기다리는 사이 화면을 떠나면 올리기는 끝까지 가도 일지는 만들지 않는다", async (t) => {
  const { api, view, release } = await heldUpload(t);
  view.unmount();
  release();
  await settle();
  await settle();
  assert.deepEqual(view.journals, []);
  // 올리기 자체는 끝까지 간다 — 교사가 적은 줄은 서버에 남는다.
  assert.equal(api.rows().length, 1);
});

test("요청을 기다리던 화면을 떠나면 그 뒤에 옛 조회를 보내지 않는다", async (t) => {
  const api = recorder();
  const mutations = createMutationBarrier();
  routineMutationBarriers.set(api.api, mutations);
  let commit;
  void mutations.track(`3|${TODAY}`, new Promise((resolve) => (commit = resolve)));
  const view = page(t, api.api);
  await view.flush();
  assert.deepEqual(api.only("day"), [], "요청이 끝나기 전에는 묻지 않는다");

  view.unmount();
  commit();
  await settle();
  await settle();
  assert.deepEqual(api.only("day"), [], "떠난 화면이 뒤늦게 묻지 않는다");
});

test("지난 날짜의 실패 문구가 다음 날짜 화면에 남지 않는다", async (t) => {
  const api = recorder();
  const view = page(t, api.api);
  timers(t);
  await view.flush();
  api.failNext("draft");
  view.type(view.dones()[0], "블록");
  await pause(t, view);
  assert.match(view.text(), /저장 못 했어요/);

  view.type(view.dateInput(), "2026-10-07");
  await view.flush();
  assert.doesNotMatch(view.text(), /저장 못 했어요/);
});

// ── OLD TASK 2 에서 이어받은 줄 단위 되돌리기 ──────────────────────────────

test("되돌리기는 그 줄만 일과 기록 값으로 돌리고 서버에 묻지 않는다", async (t) => {
  const api = recorder({ rows: [row({ id: 1, name: "등원" }), row({ id: 2, name: "바깥놀이" })] });
  const view = page(t, api.api);
  await view.flush();
  fill(view, 0, "고친 이름");
  view.render();
  fill(view, 1, "이것도 고침");
  view.render();
  assert.deepEqual(view.nameValues(), ["고친 이름", "이것도 고침"]);

  view.rowButton(0, "되돌리기").props.onClick();
  await view.flush();
  assert.deepEqual(view.nameValues(), ["등원", "이것도 고침"]);
  assert.deepEqual(
    api.calls.filter((c) => c.op !== "day"),
    [],
    "되돌리기는 조회가 아니다",
  );
});

// ── 줄 아래 — 계획 후보 · 관찰 · 반영 · 날씨 (ADR-086 · ADR-089) ───────────

test("「활동」 줄의 회색 후보를 누르면 실제로 한 것에 넣고 맞다고 한 활동으로 남긴다", async (t) => {
  const api = recorder({ rows: [row({ id: 1, name: "활동", execution: "" })] });
  const plan = {
    group: ["낙엽 모자이크"],
    special: [],
    all: [{ label: "대·소집단 활동", values: ["낙엽 모자이크"] }],
  };
  const view = page(t, api.api, { extras: { plan, observations: [] } });
  timers(t);
  await view.flush();
  assert.equal(view.dones()[0].props.value, "", "후보는 누르기 전에는 사실이 아니다");

  view.button("낙엽 모자이크 했어요").props.onClick();
  await pause(t, view);
  assert.equal(view.dones()[0].props.value, "낙엽 모자이크");
  assert.equal(view.button("낙엽 모자이크 했어요"), undefined, "넣은 후보는 다시 안 뜬다");
  assert.deepEqual(api.only("draft")[0].input.rows[0].activities, ["낙엽 모자이크"]);
});

test("그 밖의 줄은 「계획 보기」로 골라 넣는다", async (t) => {
  const api = recorder({ rows: [row({ id: 1, execution: "" })] });
  const plan = {
    group: [],
    special: [],
    all: [{ label: "실내 자유놀이", values: ["낙엽 길 만들기"] }],
  };
  const view = page(t, api.api, { extras: { plan, observations: [] } });
  await view.flush();
  assert.match(view.text(), /계획 보기/);
  view.button("낙엽 길 만들기 넣기").props.onClick();
  await view.flush();
  assert.equal(view.dones()[0].props.value, "낙엽 길 만들기");
});

test("그 시간 관찰은 이름 뺀 글로 뜨고, 「넣기」는 실제로 한 것에 붙여 넣는다", async (t) => {
  const api = recorder({ rows: [row({ id: 1, execution: "블록을 쌓았다." })] });
  const observations = [
    { id: 5, context: "실내놀이, 쌓기", text: "○○가 같이 만들자고 함", suspects: [] },
    { id: 6, context: "바깥놀이", text: "다른 줄 관찰", suspects: [] },
  ];
  const view = page(t, api.api, { extras: { plan: null, observations } });
  await view.flush();
  assert.match(view.text(), /○○가 같이 만들자고 함/);
  assert.doesNotMatch(view.text(), /다른 줄 관찰/, "상황이 다른 줄 관찰은 이 줄에 안 뜬다");
  view.rowButton(0, "넣기").props.onClick();
  await view.flush();
  assert.equal(view.dones()[0].props.value, "블록을 쌓았다.\n○○가 같이 만들자고 함");
});

test("어제 지원이 있으면 쪽지가 뜨고, 줄의 「반영」 도장을 눌러 임시본에 남긴다", async (t) => {
  const api = recorder({ rows: [row({ id: 1 })] });
  const view = page(t, api.api, { yesterday: "모래놀이에 물길 재료를 더 준비한다." });
  timers(t);
  await view.flush();
  assert.match(view.text(), /모래놀이에 물길 재료를 더 준비한다/);
  view.rowButton(0, "어제 지원 반영").props.onClick();
  await pause(t, view);
  assert.equal(api.only("draft")[0].input.rows[0].reflected, true);
});

test("비 오는 날 바깥놀이 줄에 「바깥놀이(대체)」 칩 — 누르면 이름이 바뀐다", async (t) => {
  const api = recorder({
    rows: [row({ id: 1, name: "바깥놀이" })],
    weather: { date: TODAY, sky: "비", dust: "보통", source: "auto", indoor_hint: "rain" },
  });
  const view = page(t, api.api);
  await view.flush();
  view.rowButton(0, "바깥놀이(대체)").props.onClick();
  await view.flush();
  assert.deepEqual(view.nameValues(), ["바깥놀이(대체)"]);
});

test("날씨를 누르면 여섯과 「자동으로」가 펼쳐지고, 고르면 서버에 그 반 그날 값으로 둔다", async (t) => {
  const api = recorder({
    weather: { date: TODAY, sky: null, dust: "나쁨", source: "none", indoor_hint: null },
  });
  const view = page(t, api.api);
  await view.flush();
  assert.match(view.text(), /나쁨/, "미세먼지 얼굴 아래 등급 글자");
  view.button("날씨 고르기").props.onClick();
  view.render();
  view.button("흐림").props.onClick();
  await view.flush();
  assert.deepEqual(api.only("weather")[0].choice, { class_id: 3, date: TODAY, sky: "흐림" });
  assert.ok(view.button("날씨 흐림"), "고른 값이 날짜 옆에 선다");
});

test("「기본 일과표로」는 이 하루를 고정 줄로, 「요일만」을 누른 줄은 그 요일 줄로 둔다", async (t) => {
  const api = recorder({
    rows: [
      row({ id: 1, name: "등원" }),
      row({ id: 2, name: "특별활동(체육)", start: "11:00:00", end: "11:30:00" }),
    ],
  });
  const view = page(t, api.api);
  await view.flush();
  view.button("기본 일과표로").props.onClick();
  view.render();
  // 오늘(10/6)은 화요일 — 요일 번호 1.
  view.checkboxes()[1].props.onChange();
  view.render();
  view.button("기본 일과표로 두기").props.onClick();
  await view.flush();
  assert.deepEqual(
    api.only("saveTemplate")[0].rows.map((r) => [r.name, r.weekday]),
    [
      ["등원", undefined],
      ["특별활동(체육)", 1],
    ],
  );
});

// ── P1-3 · 기록 모아보기 → 일과 기록 문맥 전달 ─────────────────────────────

const ROOM_A = {
  id: CLASS_A.id,
  className: "햇살반",
  children: [{ id: "api-child-8", name: "박서준" }],
};
const ROOM_B = {
  id: CLASS_B.id,
  className: "별빛반",
  children: [{ id: "api-child-9", name: "김하늘" }],
};
/** 저장소에 있는 모습. 서버 번호가 없으니 LINKS 에도 없다. */
const CLASS_GHOST = {
  ...EMPTY_CLASS_SETTINGS.classes[0],
  id: "class-local-only",
  className: "달빛반",
};
/** 온보딩에는 있는데 **서버 번호를 아직 모르는** 반 (LINKS 에 없다). */
const ROOM_GHOST = {
  id: "class-local-only",
  className: "달빛반",
  children: [{ id: "c", name: "이달" }],
};

/** 관찰 기록 화면 하나. 여기서 보는 것은 **일과 기록으로 가는 길**뿐이다. */
function recordsPage(
  t,
  { rooms = [ROOM_A], settings = [CLASS_A], primaryClassId = CLASS_A.id } = {},
) {
  browser({ rooms: settings, primaryClassId });
  t.after(() => {
    delete globalThis.window;
    delete globalThis.document;
  });
  const app = host();
  const Page = compile("../components/workspace/RecordsPage.tsx", {
    "react/jsx-runtime": runtime,
    react: app.react,
    "next/link": { default: "link" },
    // 그림들은 제 파일에서 본다. 여기서 보는 것은 길 · 저장이다.
    "@/components/app/Posty": { Posty: "posty" },
    "@/components/app/ChildPicker": { ChildNote: "child-note" },
    "@/components/app/icons": { Icon: "icon" },
    "@/lib/workspace/child-mark": { markFor: () => ({ tone: 0 }) },
    "@/lib/hooks/use-client-state": { useClientState: (read) => app.state(read) },
    "@/lib/hooks/use-unsaved-warning": { useUnsavedWarning: () => {} },
    // 관찰 영역 축은 서버 설정에서 온다. 여기서 보는 것은 길 · 저장이라 기본 축으로 둔다.
    "@/lib/hooks/use-observation-domains": { useObservationDomains: () => OBSERVATION_DOMAINS },
    "@/lib/workspace/domain-look": domainLook,
    "@/lib/onboarding/settings": classSettings,
    "@/lib/workspace/model": {
      today: () => TODAY,
      validDate: (value) => /^\d{4}-\d{2}-\d{2}$/.test(value),
    },
    // 주소를 만드는 쪽도 진짜다 — 반 번호 변환까지 같이 본다.
    "@/lib/workspace/routines-route": routinesRoute,
    // 문서 보관함으로 가는 길도 반 번호를 쓴다 (「이 아이 관찰일지 만들기」).
    "@/lib/api/onboarding": onboardingApi,
    "@/lib/api/client": { isUnauthenticated: () => false, invalidFields: () => [] },
    "@/lib/api/onboarding": onboardingApi,
    "@/lib/api/records": {
      listRecords: async () => [],
      addRecord: async () => ({}),
      editRecord: async () => ({}),
      removeRecord: async () => {},
      dayRoutines: async () => [],
    },
    "@/lib/api/documents": { documentLocalId: (id) => `document:${id}` },
    "@/lib/workspace/record-context": recordContext,
    "./WorkspaceUI": {
      WorkspacePage: "page",
      Empty: "empty",
      Message: "message",
      useClasses: () => rooms,
      ws: {},
    },
    "./WorkspaceViewState": {
      WorkspaceViewState,
      FieldError: "field-error",
      fieldErrorProps: () => ({}),
    },
  }).default;
  const view = app.mount(Page);
  t.after(app.cleanup);
  const find = (type) => all(view.tree()).filter((node) => node?.type === type);
  return {
    flush: view.flush,
    render: view.render,
    selects: () => find("select"),
    dateInput: () => find("input").find((node) => node.props.type === "date"),
    links: () =>
      all(view.tree())
        .filter((node) => node?.props?.href)
        .map((node) => node.props.href),
    text: () =>
      all(view.tree())
        .filter((part) => typeof part === "string")
        .join(" "),
    type: (node, value) => node.props.onChange({ target: { value } }),
    /** 적는 칸은 접혀 있다. 날짜·반을 고르려면 먼저 펼친다. */
    openForm: () => {
      // 적는 칸은 늘 펴져 있다. 여는 단추가 없으므로 그릴 것만 다시 그린다.
      view.render();
    },
  };
}

test("관찰 기록 본문에는 일과 기록으로 가는 길을 두지 않는다 — 사이드바 메뉴가 고른 반을 들고 간다", async (t) => {
  const view = recordsPage(t, {
    rooms: [ROOM_A, ROOM_B, ROOM_GHOST],
    settings: [CLASS_A, CLASS_B, CLASS_GHOST],
    primaryClassId: CLASS_GHOST.id,
  });
  await view.flush();
  // 서버 번호를 모르는 반이어도 주 반(A)으로 들어가는 길이 생기지 않는다.
  assert.deepEqual(
    view.links().filter((href) => href.startsWith("/routines")),
    [],
  );
  assert.ok(view.links().includes("/records/journal"), view.links().join(" , "));
});

test("P1-3 들고 간 주소를 S-J1 이 그대로 읽는다", () => {
  assert.deepEqual(routinesRoute.routinesScope("?date=2026-10-02&class_id=3"), {
    date: "2026-10-02",
    classId: 3,
  });
});

test("P1 고른 반의 서버 번호를 모르면 주소를 만들지 않는다", () => {
  browser({ rooms: [CLASS_A], primaryClassId: CLASS_A.id });
  assert.equal(routinesRoute.routinesPath(CLASS_A.id, TODAY), `/routines?date=${TODAY}&class_id=3`);
  // **번호만 빼고 보내지 않는다.** 그러면 S-J1 이 「안 골랐다」로 읽고 주 반을 연다.
  assert.equal(routinesRoute.routinesPath(ROOM_GHOST.id, TODAY), null);
  // 아무 반도 안 골랐으면 날짜만 들고 가는 게 맞다 — 이건 다른 상태다.
  assert.equal(routinesRoute.routinesPath("", TODAY), `/routines?date=${TODAY}`);
  delete globalThis.window;
  delete globalThis.document;
});

// ── 시간순 정렬과 겹침 ────────────────────────────────────────────────────
// 줄을 끌어서 옮기는 길은 없다. 순서를 정하는 것은 시간 하나뿐이라, 시계를 닫는 순간
// 그 자리에서 다시 줄을 세운다. 같은 시간을 두 일과가 쓰면 세우지 않고 알린다.

/** 그 줄의 시계를 열어 값을 넣고 닫는다. 닫을 때 정렬 · 겹침 검사가 돈다. */
async function setSpan(view, index, from, to) {
  view.rowButton(index, "시계로 시간 고르기").props.onClick();
  view.render();
  const times = () => all(view.cards()[index]).filter((n) => n?.props?.type === "time");
  if (from !== null) view.type(times()[0], from);
  view.render();
  if (to !== null) view.type(times()[1], to);
  view.render();
  view.rowButton(index, "닫기").props.onClick();
  await view.flush();
}

test("시계를 닫으면 그 자리에서 시간순으로 다시 서고, 그 순서로 올린다", async (t) => {
  const api = recorder({
    rows: [
      row({ id: 1, name: "A", position: 0, start: "09:00:00", end: "10:00:00" }),
      row({ id: 2, name: "B", position: 1, start: "11:00:00", end: "12:00:00" }),
      row({ id: 3, name: "C", position: 2, start: "13:00:00", end: "14:00:00" }),
    ],
  });
  const view = page(t, api.api);
  await view.flush();
  assert.deepEqual(view.nameValues(), ["A", "B", "C"]);

  await setSpan(view, 2, "07:00", "08:00");
  assert.deepEqual(view.nameValues(), ["C", "A", "B"], "시계를 닫았는데 자리를 바꾸지 않았다");

  view.unmount();
  await settle();
  assert.deepEqual(
    api
      .only("draft")
      .at(-1)
      .input.rows.map((r) => r.name),
    ["C", "A", "B"],
  );
});

test("시간이 겹치면 줄을 세우지 않고 알리고, 일지를 만들기 전에 그 줄을 짚는다", async (t) => {
  const api = recorder({
    rows: [
      row({ id: 1, name: "앞 일과", position: 0, start: "09:00:00", end: "10:00:00" }),
      row({ id: 2, name: "뒤 일과", position: 1, start: "11:00:00", end: "12:00:00" }),
    ],
  });
  const view = page(t, api.api);
  await view.flush();

  await setSpan(view, 1, "09:30", null);
  assert.ok(view.text().includes("시간이 겹쳐요"), view.text());
  assert.deepEqual(view.nameValues(), ["앞 일과", "뒤 일과"], "겹친 채로 자리를 바꿨다");

  // 겹친 채로 올리지 않는다 — 이번에 시간을 바꾼 줄이라 돌려보낸다.
  view.button("오늘 일지 만들기").props.onClick();
  await view.flush();
  assert.equal(
    api.only("draft").filter((c) => c.input.promote).length,
    0,
    "겹친 시간을 그대로 올렸다",
  );

  // 겹치지 않게 고치면 올라간다.
  await setSpan(view, 1, "10:30", null);
  view.button("오늘 일지 만들기").props.onClick();
  await view.flush();
  assert.equal(api.rows().find((r) => r.id === 2).start, "10:30:00");
});

test("깔아 둔 하루와 겹치는 것은 막지 않는다 — 올라가지 않는 줄이다", async (t) => {
  // 그날도 깔 것도 없다. 표준 하루 열 줄이 깔리고, 교사는 그중 한 줄만 적는다.
  const api = recorder();
  const view = page(t, api.api);
  await view.flush();
  assert.equal(view.cards().length, 10);

  // 「오전 실내놀이」(09:20~10:40)를 앞 줄들과 겹치는 08:00~11:00 으로 늘린다.
  view.type(view.dones()[2], "블록으로 길을 만들었다.");
  await view.flush();
  await setSpan(view, 2, "08:00", "11:00");
  assert.equal(view.text().includes("시간이 겹쳐요"), false, view.text());

  view.button("오늘 일지 만들기").props.onClick();
  await view.flush();
  assert.deepEqual(
    api.rows().map((r) => [r.name, r.start, r.end]),
    [["오전 실내놀이", "08:00:00", "11:00:00"]],
    "손대지 않은 줄과 겹친다고 막았다",
  );
});

// ── 보고 있는 반 · 날짜를 주소에 적어 둔다 (P1-3 scope 동기화) ──────────────

test("주소에 아무것도 없어도 연 반 · 날짜를 주소에 적는다", async (t) => {
  const view = page(t, recorder().api);
  await view.flush();
  assert.equal(view.search(), `?date=${TODAY}&class_id=3`);
});

test("날짜를 바꾸면 주소의 date 도 따라간다", async (t) => {
  const view = page(t, recorder().api, { search: "?date=2026-10-16&class_id=3" });
  await view.flush();
  assert.equal(view.search(), "?date=2026-10-16&class_id=3");

  view.type(view.dateInput(), "2026-10-17");
  await view.flush();
  assert.equal(view.search(), "?date=2026-10-17&class_id=3");
});

test("주소를 고쳐도 그 때문에 서버에 쓰지는 않는다", async (t) => {
  const api = recorder({ rows: [row({ id: 1, name: "A" })] });
  const view = page(t, api.api, { search: "?date=2026-10-16&class_id=3" });
  await view.flush();
  view.type(view.dateInput(), "2026-10-17");
  await view.flush();
  assert.deepEqual(
    api.calls.filter((c) => c.op !== "day").map((c) => c.op),
    [],
    "주소만 바꿨는데 서버에 썼다",
  );
});

test("바꾼 반 · 날짜에 쓰고 떠난 뒤 그 주소로 다시 열면 같은 자리다", async (t) => {
  const api = recorder();
  const classes = [
    { id: 3, name: "햇살반" },
    { id: 4, name: "별빛반" },
  ];
  const first = page(t, api.api, { search: "?date=2026-10-16&class_id=4", classes });
  await first.flush();
  first.type(first.dateInput(), "2026-10-17");
  await first.flush();
  fill(first, 0, "바깥놀이");
  await first.flush();
  const address = first.search();
  first.unmount();
  await settle();
  assert.deepEqual(
    api.rows().map((r) => [r.class_id, r.date, r.name]),
    [[4, "2026-10-17", "바깥놀이"]],
  );

  // 새로고침 = 그 때 주소로 화면을 다시 세우는 것. 옛 반 · 옛 날짜로 돌아가면 안 된다.
  const reloaded = page(t, api.api, { search: address, classes });
  await reloaded.flush();
  assert.equal(reloaded.search(), "?date=2026-10-17&class_id=4", "반 · 날짜가 주소에 남아 있다");
  assert.equal(reloaded.dateInput().props.value, "2026-10-17");
  assert.deepEqual(reloaded.nameValues()[0], "바깥놀이");
});

test("주소의 반을 못 찾으면 주소를 고치지 않는다 — 새로고침해도 주 반이 조용히 열리지 않는다", async (t) => {
  const view = page(t, recorder().api, { search: "?date=2026-10-06&class_id=999" });
  await view.flush();
  assert.equal(view.search(), "?date=2026-10-06&class_id=999");
  assert.ok(view.text().includes("반을 골라주세요"), view.text());
});

// ── 끌어서 옮기기 (AC4) ────────────────────────────────────────────────────

const hrefsOf = (view) =>
  all(view.tree())
    .filter((node) => node?.props?.href)
    .map((node) => node.props.href);

/**
 * 기록 모아보기 화면 하나. 관찰 기록과 일과 기록 조회는 받은 조건을 `calls` 에 남긴다 —
 * 두 조회가 모두 반 · 주를 짚는지 본다 (FR-405 · FR-705).
 */
function quickRecordsPage(
  t,
  {
    rooms = [ROOM_A, ROOM_B],
    // 저장소에 들어 있는 반. 서버 번호를 모르는 반을 넣어 보려면 이걸 바꾼다.
    settings = [CLASS_A, CLASS_B],
    primaryClassId = CLASS_A.id,
    observations = [],
    routineRows = [],
    routineFail = false,
  } = {},
) {
  const calls = [];
  browser({ rooms: settings, primaryClassId });
  t.after(() => {
    delete globalThis.window;
    delete globalThis.document;
  });
  const app = host();
  const Page = compile("../components/workspace/WeeklyRecordsPage.tsx", {
    "react/jsx-runtime": runtime,
    react: app.react,
    "next/link": { default: "link" },
    "./WorkspaceUI": {
      WorkspacePage: "page",
      JournalTabs: "journal-tabs",
      Message: "message",
      Notice: "notice",
      useClasses: () => rooms,
      ws: {},
    },
    "@/components/app/icons": { Icon: "icon" },
    "@/components/app/Posty": { Posty: "posty" },
    // 이번 주 주간 일지 칸은 따로 테스트한다. 여기서는 자리만 둔다.
    "./WeeklyJournalCard": {
      default: "weekly-journal-card",
      WeeklyJournalEditor: "weekly-journal-editor",
      useWeeklyJournal: () => ({
        doc: null,
        sources: [],
        blockedDailies: [],
        busy: false,
        off: false,
        make: () => {},
        leave: () => true,
      }),
    },
    "@/lib/api/records": {
      listRecords: async (classId, period) => {
        calls.push({ op: "observations", classId, ...period });
        return observations.filter((r) => r.classId === classId);
      },
    },
    "@/lib/api/routines": {
      ...routines,
      listRoutines: async (query) => {
        calls.push({ op: "routines", ...query });
        if (routineFail) throw new Error("일과 서버 오류");
        return routineRows.filter((r) => r.class_id === query.class_id);
      },
    },
    "@/lib/api/onboarding": onboardingApi,
    "@/lib/onboarding/settings": classSettings,
    "@/lib/workspace/model": { today: () => TODAY, localTime: () => "09:00" },
    // 주소를 만드는 쪽도 진짜다 — 반 번호 변환까지 같이 본다.
    "@/lib/workspace/routines-route": routinesRoute,
    "@/lib/hooks/use-client-state": { useClientState: (read) => app.state(read) },
    "@/lib/hooks/use-unsaved-warning": { useUnsavedWarning: () => {} },
    // 관찰 영역 축은 서버 설정에서 온다. 여기서 보는 것은 길 · 저장이라 기본 축으로 둔다.
    "@/lib/hooks/use-observation-domains": { useObservationDomains: () => OBSERVATION_DOMAINS },
    "@/lib/workspace/domain-look": domainLook,
  }).default;
  const view = app.mount(Page);
  t.after(app.cleanup);
  const find = (type) => all(view.tree()).filter((node) => node?.type === type);
  return {
    calls,
    flush: view.flush,
    render: view.render,
    links: () => hrefsOf(view),
    classSelect: () => find("select")[0],
    text: () =>
      all(view.tree())
        .filter((part) => typeof part === "string")
        .join(" "),
    dayButton: (day) =>
      find("button").find((node) =>
        all(node.props.children).some((part) => String(part) === String(day)),
      ),
    type: (node, value) => node.props.onChange({ target: { value } }),
  };
}

test("기록 모아보기는 고른 반 · 고른 날짜를 그대로 일과 기록으로 들고 간다", async (t) => {
  const view = quickRecordsPage(t);
  await view.flush();
  // FR-405: 저장된 주 반을 먼저 적용한다.
  assert.ok(view.links().includes(`/routines?date=${TODAY}&class_id=3`), view.links().join(" , "));

  const other = quickRecordsPage(t, { primaryClassId: CLASS_B.id });
  await other.flush();
  assert.ok(
    other.links().includes(`/routines?date=${TODAY}&class_id=7`),
    `고른 반을 잃었다: ${other.links().join(" , ")}`,
  );
});

test("기록 모아보기에서 지난 날짜를 고르면 그 날짜로 일과 기록에 간다 — 오늘로 돌아가지 않는다", async (t) => {
  const view = quickRecordsPage(t);
  await view.flush();
  // TODAY 는 2026-10-06(화)다. 같은 주의 월요일을 고른다.
  view.dayButton(5).props.onClick();
  await view.flush();
  assert.ok(
    view.links().includes("/routines?date=2026-10-05&class_id=3"),
    `고른 날짜를 잃었다: ${view.links().join(" , ")}`,
  );
});

test("기록 모아보기 — 고른 반의 서버 번호를 모르면 주소를 만들지 않고 이유를 보여준다", async (t) => {
  const view = quickRecordsPage(t, {
    rooms: [ROOM_A, ROOM_GHOST],
    settings: [CLASS_A, CLASS_GHOST],
    primaryClassId: ROOM_GHOST.id,
  });
  await view.flush();
  assert.equal(
    view.links().some((href) => href.startsWith("/routines")),
    false,
    "서버 번호를 모르는 반인데 주소를 만들었다",
  );
  assert.ok(view.text().includes("일과 기록으로 갈 수 없어요"), view.text());
});

// ── S-J6 · FR-705 — 관찰 기록과 일과 기록을 같이 본다 ─────────────────────────

/** 관찰 기록 한 줄 (화면 모양). 반은 화면 id 다. */
const observation = (over = {}) => ({
  id: "observation:1",
  classId: CLASS_A.id,
  childName: "박서준",
  date: TODAY,
  domain: "자연탐구",
  fact: "도토리를 바구니에 담았다.",
  createdAt: "2026-10-06T01:00:00Z",
  ...over,
});

test("기록 모아보기는 관찰 기록과 일과 기록을 둘 다 고른 반 · 그 주로 부른다", async (t) => {
  const view = quickRecordsPage(t);
  await view.flush();
  // TODAY(2026-10-06 화)의 주는 10/05(월) ~ 10/11(일)이다. 반 A 는 서버 반 3 이다.
  assert.deepEqual(view.calls, [
    { op: "observations", classId: CLASS_A.id, from: "2026-10-05", to: "2026-10-11" },
    { op: "routines", class_id: 3, from: "2026-10-05", to: "2026-10-11" },
  ]);

  // 사이드바에서 B 반을 고르면 화면을 다시 세운다. 그 화면은 B 반의 그 주를 부른다.
  const other = quickRecordsPage(t, { primaryClassId: CLASS_B.id });
  await other.flush();
  assert.deepEqual(other.calls, [
    { op: "observations", classId: CLASS_B.id, from: "2026-10-05", to: "2026-10-11" },
    { op: "routines", class_id: 7, from: "2026-10-05", to: "2026-10-11" },
  ]);
});

test("기록 모아보기는 그 날의 일과 기록과 관찰 기록을 섞어 보여주고 건수에 둘 다 센다", async (t) => {
  const view = quickRecordsPage(t, {
    observations: [observation()],
    routineRows: [row({ id: 41, class_id: 3, date: TODAY, name: "오전 실내놀이" })],
  });
  await view.flush();
  const text = view.text();
  assert.ok(text.includes("오전 실내놀이"), text);
  assert.ok(text.includes("일과 기록"), text);
  assert.ok(text.includes("도토리를 바구니에 담았다."), text);
  assert.ok(text.includes("관찰 기록"), text);
  // 오늘 칸과 「10월 6일 N건」 둘 다 두 종류를 합쳐 센다.
  assert.ok(text.includes("2건"), text);
});

test("기록 모아보기 — 일과 기록만 실패하면 관찰 기록은 그대로 보이고 무엇이 실패했는지 말한다", async (t) => {
  const view = quickRecordsPage(t, { observations: [observation()], routineFail: true });
  await view.flush();
  const text = view.text();
  assert.ok(text.includes("도토리를 바구니에 담았다."), text);
  assert.ok(text.includes("일과 기록을 불러오지 못했습니다"), text);
});

/**
 * 관찰 기록 서버 하나. **반 없이 묻는 조회는 바로 실패시킨다** — 홈이 기관 전체를
 * 조회하거나 빈 배열로 떨어지는 회귀를 테스트가 조용히 통과시키지 않게 한다 (FR-405).
 */
function recordsServer({ rows = [], suggest = null } = {}) {
  const calls = [];
  let store = rows.map((r) => ({ ...r }));
  return {
    calls,
    only: (op) => calls.filter((c) => c.op === op),
    rows: () => store,
    api: {
      listRecords: async (classId) => {
        calls.push({ op: "list", classId });
        if (!classId) throw new Error("홈이 반을 짚지 않고 조회했다 (FR-405)");
        return store.filter((r) => r.classId === classId);
      },
      // 영역 추천(ADR-082). 기본은 서버 mock 처럼 제안이 없다.
      suggestRecordDomain: async (classId, fact, context) => {
        calls.push({ op: "suggest", classId, fact, context });
        return suggest;
      },
      addRecord: async (record) => {
        calls.push({ op: "add", classId: record.classId });
        const made = {
          ...record,
          id: `obs-${store.length + 1}`,
          childName: "아동 A",
          createdAt: "2026-10-06T00:00:00Z",
        };
        store = [...store, made];
        return made;
      },
    },
  };
}

/** 우리 반 첫 화면 하나. 일과로 가는 길과 **홈이 어느 반을 조회하는가**를 본다. */
function homePage(
  t,
  {
    rooms = [CLASS_A],
    primaryClassId = CLASS_A.id,
    classes = rooms,
    records = recordsServer(),
    search = "",
    routineRows = async () => [],
    ready = true,
  } = {},
) {
  browser({ rooms, primaryClassId, search });
  t.after(() => {
    delete globalThis.window;
    delete globalThis.document;
  });
  const app = host();
  // 서버 반은 늦게 온다. 테스트가 도중에 바꿔 끼울 수 있게 상자로 둔다.
  const box = { classes };
  const Page = compile("../components/dashboard/HomePage.tsx", {
    "react/jsx-runtime": runtime,
    react: app.react,
    "next/link": { default: "link" },
    "@/components/app/AppLayout": { PageContainer: "container" },
    "@/components/app/icons": { Icon: "icon" },
    "@/components/workspace/WorkspaceUI": { useClasses: () => box.classes },
    "@/components/workspace/domain-look": domainLook,
    "@/lib/api/records": records.api,
    "@/lib/api/onboarding": onboardingApi,
    "@/lib/workspace/model": { today: () => TODAY },
    // 대표 반 정책도 주소를 만드는 쪽도 진짜다.
    "@/lib/onboarding/settings": classSettings,
    "@/lib/workspace/routines-route": routinesRoute,
    // 일과는 홈이 따로 읽는다. 기본은 「없음」이라 일과 줄이 아예 안 그려진다.
    "@/lib/api/routines": { listRoutines: () => routineRows(), routineTime: routines.routineTime },
    // 아이 셈과 쪽지 셈은 **진짜**다. 흉내 내면 홈과 고르개가 다른 숫자를 말해도 통과한다.
    "@/lib/workspace/child-mark": childMark,
    "@/lib/workspace/home-blocks": homeBlocks,
    "@/lib/greeting": { koreanDateParts: () => ({ day: "10월 6일", dow: "화요일" }) },
    // 원 · 반이 다 찼는지는 테스트가 정한다. 위 `browser()` 의 반 설정은 원장 · 지역이 비어
    // 진짜 판정으로는 늘 「안 찼다」라, 진짜를 쓰면 홈 시험이 전부 조회를 건너뛴다.
    "@/lib/auth/local-account": { roomReady: () => ready },
    "@/lib/hooks/use-client-state": { useClientState: (read) => app.state(read) },
    "@/lib/hooks/use-unsaved-warning": { useUnsavedWarning: () => {} },
    // 관찰 영역 축은 서버 설정에서 온다. 여기서 보는 것은 길 · 저장이라 기본 축으로 둔다.
    "@/lib/hooks/use-observation-domains": { useObservationDomains: () => OBSERVATION_DOMAINS },
    "@/lib/workspace/domain-look": domainLook,
    "@/lib/hooks/use-dictation": {
      useDictation: () => ({ supported: false, listening: false, toggle: () => {} }),
    },
    // `__esModule` 이 없으면 babel 의 interop 이 모듈 전체를 default 로 한 번 더 감싼다 —
    // 컴포넌트 자리에 객체가 들어가 아무것도 그려지지 않는다.
    "@/components/app/ChildPicker": {
      __esModule: true,
      default: compile("../components/app/ChildPicker.tsx", {
        "react/jsx-runtime": runtime,
        react: app.react,
        "@/lib/workspace/child-mark": childMark,
      }).default,
    },
    "@/components/app/SsampleNote": compile("../components/app/SsampleNote.tsx", {
      "react/jsx-runtime": runtime,
      react: app.react,
    }),
  }).default;
  const view = app.mount(Page);
  t.after(app.cleanup);
  const find = (type) => all(view.tree()).filter((node) => node?.type === type);
  const labelled = (node) => String([node.props.children].flat().join(""));
  return {
    flush: view.flush,
    render: view.render,
    search: () => globalThis.window.location.search,
    records,
    /** 서버 반이 뒤늦게 도착한 상황. 다음 flush 에서 홈이 다시 조회해야 한다. */
    arrive: (next) => {
      box.classes = next;
    },
    links: () => hrefsOf(view),
    /**
     * 「이렇게 남길까요?」의 아이 타일. 아무것도 눌리지 않은 채로 열리므로
     * 교사가 반드시 고른다. `aria-pressed` 를 달고 있는 단추가 아이 타일이다.
     */
    childTiles: () => find("button").filter((node) => "aria-pressed" in node.props),
    chosenChildren: () =>
      find("button")
        .filter((node) => node.props["aria-pressed"] === true)
        .map(deepText),
    /**
     * 저장 단추. 글자가 고른 아이에 따라 바뀌므로(「김하늘 기록으로 남기기」 ·
     * 「3명으로 남기기」) 꼬리말로 찾는다. 아무도 안 고르면 눌리지 않아 undefined 다.
     */
    saveButton: () =>
      find("button").find((node) => labelled(node).endsWith("남기기") && !node.props.disabled),
    /** 이름으로 아이 타일 하나를 집는다. */
    childNamed: (name) =>
      find("button").find((node) => "aria-pressed" in node.props && deepText(node).includes(name)),
    /** 「여럿 고르기」 칸. 켜야 둘 이상 고를 수 있다. */
    multiToggle: () => find("input").find((node) => node.props.type === "checkbox"),
    /** 영역 칩. 하나만 고르는 칸이라 `role="radio"` 다 — 아이 타일(`aria-pressed`)과 섞이지 않는다. */
    domainChip: (name) =>
      find("button").find((node) => node.props.role === "radio" && deepText(node) === name),
    checkedDomains: () =>
      find("button")
        .filter((node) => node.props.role === "radio" && node.props["aria-checked"] === true)
        .map(deepText),
    check: (node, checked) => node.props.onChange({ target: { checked } }),
    factInput: () => find("textarea")[0] ?? find("input").find((n) => n.props?.["aria-label"]),
    button: (label) => find("button").find((n) => labelled(n).includes(label) && !n.props.disabled),
    type: (node, value) => node.props.onChange({ target: { value } }),
    // 「오늘 적은 기록 {N}건」의 N 은 숫자 노드다. 숫자를 같이 모으고 사이를 띄우지 않아야
    // 화면에 실제로 보이는 「오늘 적은 기록 1건」이 된다.
    text: () =>
      all(view.tree())
        .filter((part) => typeof part === "string" || typeof part === "number")
        .join(""),
  };
}

/**
 * 홈에서 한 줄 적고 저장까지. 실제 화면 순서대로 —
 * 적기 → 누구 기록인지 고르기 → **아이 고르기** → 남기기.
 *
 * 아이 칸은 비어 있는 채로 열린다. 고르기 전에는 저장 단추가 눌리지 않는다.
 */
async function homeSave(view, fact) {
  view.type(view.factInput(), fact);
  await view.flush();
  view.button("누구 기록인지 고르기").props.onClick();
  await view.flush();
  await pickFirstChild(view);
  await pickDomain(view);
  view.saveButton().props.onClick();
  await view.flush();
}

/** 영역 칩을 누른다. 기본값이 없어서 고르지 않으면 남기기가 막힌다(ADR-082). */
async function pickDomain(view, name = "사회관계") {
  const chip = view.domainChip(name);
  assert.ok(chip, `영역 칩을 못 찾았다: ${name}`);
  chip.props.onClick();
  await view.flush();
}

test("아이를 고르기 전에는 기록을 남길 수 없다", async (t) => {
  // 첫 아이로 떨어뜨리면 바쁜 교사가 확인하지 않고 눌렀을 때
  // **다른 아이의 기록**이 조용히 저장된다. 영역과 달리 나중에 고치기 어렵다.
  const records = recordsServer();
  const view = homePage(t, { rooms: [CLASS_A], primaryClassId: "", classes: [ROOM_A], records });
  await view.flush();
  view.type(view.factInput(), "블록으로 길을 만들었다");
  await view.flush();
  view.button("누구 기록인지 고르기").props.onClick();
  await view.flush();

  assert.ok(view.childTiles().length, "아이 타일이 그려진다");
  assert.deepEqual(view.chosenChildren(), [], "아이 칸은 비어 있는 채로 열린다");
  assert.equal(view.saveButton(), undefined, "고르기 전에는 눌리지 않는다");

  await pickFirstChild(view);
  await pickDomain(view);
  assert.ok(view.saveButton(), "고르면 눌린다");
  view.saveButton().props.onClick();
  await view.flush();
  assert.equal(records.only("add").length, 1);
});

/** 아이가 셋인 반. 「여럿 고르기」를 보려면 둘 이상이어야 한다. */
const ROOM_MANY = {
  id: CLASS_A.id,
  className: "햇살반",
  children: [
    { id: "api-child-8", name: "박서준" },
    { id: "child-haneul", name: "김하늘" },
    { id: "child-minjae", name: "정민재" },
  ],
};

/** 이름으로 아이 타일을 누른다. 누를 때마다 다시 찾는다 — 누르면 새로 그려진다. */
async function pickChild(view, name) {
  const tile = view.childNamed(name);
  assert.ok(tile, `아이 타일을 못 찾았다: ${name}`);
  tile.props.onClick();
  await view.flush();
}

test("아이를 여럿 고르면 기록이 사람 수만큼 남는다", async (t) => {
  // 「자유놀이 때 하늘·민재가 같이 블록놀이」는 한 장면이지만, 평가 증빙은 아이별로
  // 모여야 한다. 전에는 같은 문장을 세 번 적어야 했다.
  const records = recordsServer();
  const view = homePage(t, {
    rooms: [CLASS_A],
    primaryClassId: "",
    classes: [ROOM_MANY],
    records,
  });
  await view.flush();
  view.type(view.factInput(), "블록으로 길을 만들었다");
  await view.flush();
  view.button("누구 기록인지 고르기").props.onClick();
  await view.flush();

  view.check(view.multiToggle(), true);
  await view.flush();
  await pickChild(view, "김하늘");
  await pickChild(view, "정민재");
  assert.equal(view.chosenChildren().length, 2, "둘 다 눌린 상태로 남는다");

  await pickDomain(view);
  view.saveButton().props.onClick();
  await view.flush();

  const saved = records.rows();
  assert.equal(saved.length, 2);
  assert.deepEqual(
    saved.map((r) => r.childId).sort(),
    ["child-haneul", "child-minjae"],
    "고른 아이마다 한 건씩 남는다",
  );
  // 문장은 둘 다 같다 — 한 장면이니까.
  assert.deepEqual(new Set(saved.map((r) => r.fact)), new Set(["블록으로 길을 만들었다"]));
});

test("기록이 한 건도 없는 반에서는 빈 칸을 칠하지 않는다", async (t) => {
  // 「한 주 넘게 비었다」는 치우침을 가리키는 말이다. 처음 시작한 반은 전원이 비어 있어
  // 열여덟 칸이 전부 노래지는데, 가리킬 치우침이 없는 자리에 경고만 남는다.
  const records = recordsServer();
  const view = homePage(t, {
    rooms: [CLASS_A],
    primaryClassId: "",
    classes: [ROOM_MANY],
    records,
  });
  await view.flush();
  view.type(view.factInput(), "모래를 체에 걸렀다");
  await view.flush();
  view.button("누구 기록인지 고르기").props.onClick();
  await view.flush();
  assert.ok(view.text().includes("한 줄씩 쌓이면"), view.text());

  await pickChild(view, "김하늘");
  await pickDomain(view);
  view.saveButton().props.onClick();
  await view.flush();
  view.type(view.factInput(), "블록으로 길을 만들었다");
  await view.flush();
  view.button("누구 기록인지 고르기").props.onClick();
  await view.flush();
  assert.ok(view.text().includes("연노랑 칸은"), "한 건이라도 쌓이면 빈 칸을 가리킨다");
});

test("여럿 고르기를 끄면 한 명만 남는다", async (t) => {
  // 켠 채로 둘을 골라 두고 껐을 때, 보이지 않는 아이가 같이 저장되면 안 된다.
  const records = recordsServer();
  const view = homePage(t, {
    rooms: [CLASS_A],
    primaryClassId: "",
    classes: [ROOM_MANY],
    records,
  });
  await view.flush();
  view.type(view.factInput(), "모래를 체에 걸렀다");
  await view.flush();
  view.button("누구 기록인지 고르기").props.onClick();
  await view.flush();

  view.check(view.multiToggle(), true);
  await view.flush();
  await pickChild(view, "김하늘");
  await pickChild(view, "정민재");
  view.check(view.multiToggle(), false);
  await view.flush();

  assert.equal(view.chosenChildren().length, 1, "한 명만 남는다");
  await pickDomain(view);
  view.saveButton().props.onClick();
  await view.flush();
  assert.equal(records.rows().length, 1);
});

test("홈 빠른 기록 — 영역은 아무것도 안 고른 채 열리고, 고르기 전에는 남길 수 없다", async (t) => {
  // 첫 영역(신체운동·건강)이 고른 채 저장되면 블록 놀이가 종이의 신체 줄에 들어간다(ADR-082).
  const records = recordsServer();
  const view = homePage(t, { rooms: [CLASS_A], primaryClassId: "", classes: [ROOM_A], records });
  await view.flush();
  view.type(view.factInput(), "블록으로 길을 만들었다");
  await view.flush();
  view.button("누구 기록인지 고르기").props.onClick();
  await view.flush();
  await pickFirstChild(view);

  assert.deepEqual(view.checkedDomains(), [], "영역 칸은 비어 있는 채로 열린다");
  assert.equal(view.saveButton(), undefined, "영역을 고르기 전에는 눌리지 않는다");
  assert.ok(view.text().includes("영역을 골라야 남길 수 있어요"), view.text());

  await pickDomain(view, "사회관계");
  assert.deepEqual(view.checkedDomains(), ["사회관계"]);
  view.saveButton().props.onClick();
  await view.flush();
  assert.equal(records.rows()[0].domain, "사회관계");
});

test("홈 빠른 기록 — AI 제안 영역은 보라 점선일 뿐, 눌러야 고른 것이다", async (t) => {
  const records = recordsServer({ suggest: "자연탐구" });
  const view = homePage(t, { rooms: [CLASS_A], primaryClassId: "", classes: [ROOM_A], records });
  await view.flush();
  view.type(view.factInput(), "  개미가 줄지어 가는 것을 오래 보았다 ");
  await view.flush();
  view.button("누구 기록인지 고르기").props.onClick();
  await view.flush();

  const asked = records.only("suggest");
  assert.equal(asked.length, 1, "적은 글을 들고 한 번 묻는다");
  assert.equal(asked[0].fact, "개미가 줄지어 가는 것을 오래 보았다");
  assert.equal(asked[0].context, "");
  const chip = view.domainChip("자연탐구");
  assert.equal(chip.props["data-suggested"], true);
  assert.equal(chip.props["aria-checked"], false);
  assert.ok(view.text().includes("점선은 AI 제안이에요"));

  await pickFirstChild(view);
  assert.equal(view.saveButton(), undefined, "제안만으로는 남기지 않는다");
  await pickDomain(view, "자연탐구");
  assert.equal(view.domainChip("자연탐구").props["data-suggested"], undefined);
  assert.ok(view.saveButton());
});

/** 아이 격자에서 첫 아이를 고른다. 반을 바꾸면 비워지므로 바꾼 **뒤에** 부른다. */
async function pickFirstChild(view) {
  const tiles = view.childTiles();
  assert.ok(tiles.length, "아이 타일이 없다");
  tiles[0].props.onClick();
  await view.flush();
}

test("우리 반 첫 화면에 오늘 일과로 가는 길이 있다 — 대표 반과 오늘 날짜를 들고 간다", async (t) => {
  const view = homePage(t);
  await view.flush();
  assert.ok(view.text().includes("일과 작성하기"), view.text());
  assert.ok(
    view.links().includes(`/routines?date=${TODAY}&class_id=3`),
    `주소가 틀렸다: ${view.links().join(" , ")}`,
  );
});

test("우리 반 — 대표 반의 서버 번호를 모르면 일과 길을 걸지 않는다", async (t) => {
  const view = homePage(t, { rooms: [ROOM_GHOST], primaryClassId: ROOM_GHOST.id });
  await view.flush();
  assert.equal(
    view.links().some((href) => href.startsWith("/routines")),
    false,
    "서버 번호를 모르는 반인데 주소를 만들었다",
  );
});

// ── 홈 관찰 기록 회귀 (독립 감사 P0) ──────────────────────────────────────
//
// 저장은 201 인데 홈이 0건으로 보였다. 홈이 `listRecords()` 를 인자 없이 불러,
// 주 반을 고른 적 없는 한 반짜리 계정에서 조회가 [] 로 끝났기 때문이다.

test("P0 한 반 계정 — 홈에서 저장하면 오늘 적은 기록 1건이 그 자리에 보인다", async (t) => {
  const records = recordsServer();
  const view = homePage(t, { rooms: [CLASS_A], primaryClassId: "", classes: [ROOM_A], records });
  await view.flush();

  await homeSave(view, "블록 세 개를 쌓고 더 높이 만들래라고 말했다.");

  assert.equal(records.only("add").length, 1, "저장이 가지 않았다");
  assert.equal(records.rows().length, 1, "서버에 남지 않았다");
  // 주 반이 비어 있어도 **보고 있는 반**으로 물어야 한다.
  assert.deepEqual(
    [...new Set(records.only("list").map((c) => c.classId))],
    [ROOM_A.id],
    `조회한 반이 틀렸다: ${JSON.stringify(records.only("list"))}`,
  );
  assert.ok(view.text().includes("오늘 적은 기록 1건"), `홈이 0건으로 보인다: ${view.text()}`);
});

test("P0 한 반 계정 — 새로고침해도 홈에 그대로 있다", async (t) => {
  const records = recordsServer();
  const first = homePage(t, { rooms: [CLASS_A], primaryClassId: "", classes: [ROOM_A], records });
  await first.flush();
  await homeSave(first, "모래를 체에 거르며 굵기를 비교했다.");
  assert.equal(records.rows().length, 1);

  // 새로고침 = 같은 서버 위에 화면을 다시 세우는 것.
  const again = homePage(t, { rooms: [CLASS_A], primaryClassId: "", classes: [ROOM_A], records });
  await again.flush();
  assert.ok(again.text().includes("오늘 적은 기록 1건"), `새로고침 뒤 사라졌다: ${again.text()}`);
});

test("P0 반이 둘 — A 에 적은 기록이 B 를 골랐을 때 보이지 않는다", async (t) => {
  const records = recordsServer();
  const view = homePage(t, {
    rooms: [CLASS_A, CLASS_B],
    primaryClassId: "",
    classes: [ROOM_A, ROOM_B],
    records,
  });
  await view.flush();
  await homeSave(view, "친구에게 블록을 건네며 같이 만들자고 했다.");
  assert.ok(view.text().includes("오늘 적은 기록 1건"), view.text());
  assert.deepEqual(
    records.only("add").map((c) => c.classId),
    [ROOM_A.id],
  );

  // 반은 사이드바에서 바꾼다. 바꾸면 화면을 다시 세우므로 그 다음 홈이 이것이다.
  const onB = homePage(t, {
    rooms: [CLASS_A, CLASS_B],
    primaryClassId: CLASS_B.id,
    classes: [ROOM_A, ROOM_B],
    records,
  });
  await onB.flush();

  assert.ok(onB.text().includes("오늘 적은 기록 0건"), `B 반에 A 반 기록이 보인다: ${onB.text()}`);
  assert.equal(
    records.only("list").at(-1).classId,
    ROOM_B.id,
    "반을 바꿨는데 B 반으로 묻지 않았다",
  );
});

test("P0 서버 반이 늦게 도착하면 붙은 뒤에 다시 조회한다", async (t) => {
  const records = recordsServer({
    rows: [
      {
        id: "obs-0",
        classId: ROOM_A.id,
        date: TODAY,
        domain: "의사소통",
        fact: "먼저 있던 기록",
        childName: "아동 A",
        createdAt: "2026-10-06T00:00:00Z",
      },
    ],
  });
  // 반 목록이 아직 비어 있다.
  const view = homePage(t, { rooms: [CLASS_A], primaryClassId: "", classes: [], records });
  await view.flush();
  assert.equal(records.only("list").length, 0, "반도 없는데 조회를 보냈다 (FR-405)");
  assert.ok(view.text().includes("오늘 적은 기록 0건"), view.text());

  view.arrive([ROOM_A]);
  await view.flush();
  assert.deepEqual(
    records.only("list").map((c) => c.classId),
    [ROOM_A.id],
  );
  assert.ok(
    view.text().includes("오늘 적은 기록 1건"),
    `반이 붙었는데 다시 안 읽었다: ${view.text()}`,
  );
});

test("P0 홈이 세는 건수와 서버에 남은 기록이 같다", async (t) => {
  const records = recordsServer();
  const view = homePage(t, { rooms: [CLASS_A], primaryClassId: "", classes: [ROOM_A], records });
  await view.flush();
  for (const fact of ["물감을 섞어 새 색을 만들었다.", "종이비행기를 접어 날렸다."])
    await homeSave(view, fact);

  const onServer = records.rows().filter((r) => r.date === TODAY && r.classId === ROOM_A.id).length;
  assert.equal(onServer, 2);
  assert.ok(
    view.text().includes(`오늘 적은 기록 ${onServer}건`),
    `건수가 어긋난다: ${view.text()}`,
  );
});

// ── 원 · 반이 빈 메인 ─────────────────────────────────────────────────────
//
// 가입하자마자 메인(`/`)에 들어온다. 원 · 반이 비면 보고 있는 반은 서버 번호가 없는
// 자리표시 반이라 조회가 던진다 — 묻지 않고, 날짜 아래 안내로 온보딩을 가리킨다 (docs/screen-spec.md).
// 서버 번호가 붙은 반은 다르다. 설정에 빈 반 줄 하나가 남아 「안 찼다」여도 그 반 기록은 읽는다.

const ROOM_SETUP_TITLE = "선생님, 우리 반부터 알려 주세요!";

test("원·반이 비면 홈은 기록을 묻지 않고 등록 안내를 띄운다", async (t) => {
  const records = recordsServer();
  // 자리표시 반으로 물으면 실제로 던진다. 물었다면 「불러오지 못했어요」가 떴을 것이다.
  records.api.listRecords = async (classId) => {
    records.calls.push({ op: "list", classId });
    throw new Error("자리표시 반은 서버 번호가 없다");
  };
  // 서버 번호가 없는 반 (LINKS 에 없다) — 가입 직후의 자리표시 반 모습이다.
  const view = homePage(t, {
    rooms: [CLASS_GHOST],
    primaryClassId: "",
    classes: [ROOM_GHOST],
    records,
    ready: false,
  });
  await view.flush();
  assert.equal(records.only("list").length, 0, "원·반이 없는데 조회를 보냈다");
  assert.equal(view.text().includes("기록을 불러오지 못했어요"), false, view.text());
  assert.ok(view.text().includes(ROOM_SETUP_TITLE), view.text());
  assert.ok(view.links().includes("/onboarding"), view.links().join(" "));
});

test("원·반이 덜 찼어도 서버 번호가 붙은 반이면 그 반 기록을 묻는다", async (t) => {
  // 설정에 빈 반 줄을 남긴 교사. 안내는 뜨지만, 이미 쓰던 반의 기록까지 0건으로 보이면 안 된다.
  const records = recordsServer();
  const view = homePage(t, {
    rooms: [CLASS_A],
    primaryClassId: "",
    classes: [ROOM_A],
    records,
    ready: false,
  });
  await view.flush();
  assert.deepEqual([...new Set(records.only("list").map((c) => c.classId))], [ROOM_A.id]);
  assert.ok(view.text().includes(ROOM_SETUP_TITLE), view.text());
});

test("원·반이 차 있으면 등록 안내 없이 보고 있는 반을 묻는다", async (t) => {
  const records = recordsServer();
  const view = homePage(t, { rooms: [CLASS_A], primaryClassId: "", classes: [ROOM_A], records });
  await view.flush();
  assert.equal(view.text().includes(ROOM_SETUP_TITLE), false, view.text());
  assert.deepEqual([...new Set(records.only("list").map((c) => c.classId))], [ROOM_A.id]);
});

test("우리 반 — 오늘 일과에 활동실행이 적혀 있으면 그 자리에서 보육일지로 간다", async (t) => {
  const view = homePage(t, {
    routineRows: async () => [
      { id: 1, date: TODAY, start: "09:20:00", name: "오전 실내놀이", plan: "", execution: "블록" },
    ],
  });
  await view.flush();
  assert.ok(view.text().includes("오전 실내놀이"), view.text());
  assert.ok(
    view.links().includes(`/documents?kind=dailyLog&class_id=3&date=${TODAY}`),
    view.links().join(" "),
  );
});

test("우리 반 — 일과 줄만 있고 활동실행이 비면 일지로 보내지 않는다", async (t) => {
  // S-J1 과 같은 규칙이다. 실행이 비면 일지도 빈다 — 길만 열어 두면 빈 일지가 남는다.
  const view = homePage(t, {
    routineRows: async () => [
      { id: 1, date: TODAY, start: "09:20:00", name: "오전 실내놀이", plan: "쌓기", execution: "" },
    ],
  });
  await view.flush();
  assert.equal(
    view.links().some((href) => href.startsWith("/documents?kind=dailyLog")),
    false,
  );
  assert.ok(view.text().includes("일과를 적으면 만들 수 있어요"), view.text());
});

test("우리 반 — 일과를 못 읽었으면 일과 줄을 그리지 않는다", async (t) => {
  // 못 읽었는데 빈 줄을 그리면 멀쩡히 적어 둔 교사에게 안 적었다고 말하는 셈이다.
  const view = homePage(t, { routineRows: async () => Promise.reject(new Error("끊김")) });
  await view.flush();
  await view.flush();
  assert.equal(view.text().includes("일과 —"), false);
});

test("L 홈의 저장·조회·일과 링크가 고른 B 반으로 함께 바뀐다", async (t) => {
  const records = recordsServer();
  const view = homePage(t, {
    rooms: [CLASS_A, CLASS_B],
    classes: [ROOM_A, ROOM_B],
    records,
  });
  await view.flush();
  await homeSave(view, "A에서만 보이는 사실");

  // 사이드바에서 B 로 바꾼 뒤의 홈. 이름 · 링크 · 조회 · 저장이 한 반을 가리켜야 한다.
  const onB = homePage(t, {
    rooms: [CLASS_A, CLASS_B],
    primaryClassId: CLASS_B.id,
    classes: [ROOM_A, ROOM_B],
    records,
  });
  await onB.flush();
  assert.ok(onB.links().includes(`/routines?date=${TODAY}&class_id=7`));
  assert.equal(onB.text().includes("A에서만 보이는 사실"), false);
  await homeSave(onB, "B에서만 보이는 사실");
  assert.equal(records.only("add").at(-1).classId, ROOM_B.id);
  assert.equal(records.only("list").at(-1).classId, ROOM_B.id);
  assert.ok(onB.text().includes("오늘 적은 기록 1건"));
  assert.ok(onB.text().includes("B에서만 보이는 사실"));
  // 홈은 주소에 반을 적지 않는다. 고른 반은 저장소에 남고 사이드바가 보여 준다.
});

test("L 뒤로 온 B 반 URL은 반 연결이 늦어도 A 반으로 대체하지 않는다", async (t) => {
  const records = recordsServer();
  const view = homePage(t, {
    rooms: [CLASS_A, CLASS_B],
    classes: [ROOM_A],
    records,
    search: "?class_id=7",
  });
  await view.flush();
  assert.equal(records.only("list").length, 0);
  assert.equal(
    view.links().some((href) => href.startsWith("/routines")),
    false,
  );
  view.arrive([ROOM_A, ROOM_B]);
  await view.flush();
  assert.equal(records.only("list").at(-1).classId, ROOM_B.id);
  assert.ok(view.links().includes(`/routines?date=${TODAY}&class_id=7`));
});

// 「L A 반의 느린 응답이 B 반 화면을 덮지 않는다」와 「A 저장 중 B 로 옮겨도…」는
// 화면 안에서 반을 바꿀 수 있을 때의 레이스였다. 반은 사이드바에서만 바꾸고, 바꾸면 화면을
// 통째로 다시 세우므로 옛 반의 늦은 응답이 새 화면에 닿을 길이 없다. 같은 가드를 보는
// 날짜 축 시험은 위에 그대로 있다.

test("기록 모아보기 — 활동실행이 빈 일과는 계획을 실행처럼 띄우지 않는다", async (t) => {
  const view = quickRecordsPage(t, {
    routineRows: [row({ id: 42, class_id: 3, date: TODAY, plan: "자동차 굴리기", execution: "" })],
  });
  await view.flush();
  const text = view.text();
  assert.equal(text.includes("자동차 굴리기"), false, text);
  assert.ok(text.includes("실제로 한 것을 아직 적지 않았습니다."), text);
});

// ── 이번 주 주간 보육일지 칸 ──────────────────────────────────────────
// 주간 일지의 근거는 관찰 기록이 아니다 (api-spec §11). 확정한 일일 보육일지가 기본이고,
// 일일을 쓰지 않는 원만 그 주 일과 기록을 바로 받는다. 고른 쪽이 그대로 서버로 가야 한다.
function journalCard(
  t,
  {
    weeklies = [],
    dailies = [],
    routineRows = [],
    week = { start: "2026-11-02", end: "2026-11-08" },
    create,
  } = {},
) {
  const calls = [];
  const app = host();
  t.after(() => app.cleanup());
  const Card = compile("../components/workspace/WeeklyJournalCard.tsx", {
    "react/jsx-runtime": runtime,
    react: app.react,
    "next/link": { default: "link" },
    "next/navigation": { useRouter: () => ({ push: (href) => calls.push({ op: "push", href }) }) },
    "./WorkspaceUI": { Message: "message", ws: {} },
    "./RoutineDay.module.css": { __esModule: true, default: {} },
    "@/components/app/Posty": { Posty: "posty" },
    "./DailyJournalCard": {
      journalMood: () => ({ pose: "stand", face: "base", tone: "note" }),
    },
    // 편집기 자체는 보관함 테스트가 본다. 여기서는 열렸는지만 본다.
    "./DocumentEditor": { __esModule: true, default: "document-editor" },
    "./use-server-document": {
      useServerDocument: (id) => {
        calls.push({ op: "edit", id });
        return {
          doc: id ? { id, sections: [] } : null,
          status: "ready",
          error: "",
          server: undefined,
        };
      },
    },
    "@/lib/api/onboarding": { classServerId: (id) => (id === "class-1" ? 7 : null) },
    "@/lib/api/routines": { routineLocalId: (id) => `routine-${id}` },
    "@/lib/workspace/routines-route": { routinesPath: (_, date) => `/routines?date=${date}` },
    "@/lib/api/documents": {
      listDocuments: async (query) => {
        calls.push({ op: "list", ...query });
        return query.kind === "weeklyLog" ? weeklies : dailies;
      },
      createDocument: async (input) => {
        calls.push({ op: "create", ...input });
        return create ? create(input) : { id: "doc-99" };
      },
      getDocument: async (id) => {
        calls.push({ op: "get", id });
        return { id, sections: [{ heading: "해석", body: `${id} 의 해석` }] };
      },
    },
  });
  let current;
  // 화면과 같은 짝으로 띄운다 — 머리의 「주간 일지 만들기」와 아래 칸이 한 상태를 본다.
  const view = app.mount(() => {
    const state = Card.useWeeklyJournal({
      classId: "class-1",
      weekStart: week.start,
      weekEnd: week.end,
      routines: routineRows,
    });
    current = state;
    return jsx("div", {
      children: [
        jsx("button", {
          disabled: !!state.doc || state.busy || !state.sources.length,
          onClick: state.make,
          children: "주간 일지 만들기",
        }),
        Card.default({
          state,
          className: "햇살반",
          weekStart: week.start,
          weekEnd: week.end,
        }),
        // 펴 놓은 일지는 오른쪽 칠판 밑에 따로 선다. 화면과 같이 둘 다 띄운다.
        Card.WeeklyJournalEditor({ state }),
      ],
    });
  });
  return { view, calls, state: () => current, text: () => deepText(view.tree()) };
}

/** 머리의 「주간 일지 만들기」. 칸에는 이제 단추가 없다. */
const makeButton = (view) =>
  all(view.tree()).find((n) => n?.type === "button" && deepText(n).includes("주간 일지 만들기"));

const draftWeekly = {
  id: "doc-5",
  start: "2026-11-02",
  end: "2026-11-08",
  status: "draft",
  stale: false,
};

test("이번 주 주간 일지가 이미 있으면 만들기 대신 이어서 쓰기를 준다", async (t) => {
  const card = journalCard(t, { weeklies: [draftWeekly] });
  await card.view.flush();
  assert.ok(card.text().includes("이어서 쓰기"), card.text());
  assert.equal(makeButton(card.view).props.disabled, true);
  assert.equal(
    card.calls.some((c) => c.op === "create"),
    false,
  );
});

test("지난 주 일지는 이번 주 것으로 세지 않는다", async (t) => {
  const card = journalCard(t, {
    weeklies: [{ ...draftWeekly, id: "doc-4", start: "2026-10-26", end: "2026-11-01" }],
  });
  await card.view.flush();
  assert.ok(card.text().includes("아직 만들지 않았어요."), card.text());
});

test("근거를 일과 기록으로 고르면 활동실행이 있는 일과만 그 종류로 보낸다", async (t) => {
  const card = journalCard(t, {
    routineRows: [
      { id: 11, execution: "블록 길을 만들었다." },
      { id: 12, execution: "" },
      { id: 13, execution: "도토리를 모았다." },
    ],
  });
  await card.view.flush();
  const select = all(card.view.tree()).find((n) => n?.type === "select");
  select.props.onChange({ target: { value: "routine" } });
  await card.view.flush();
  makeButton(card.view).props.onClick();
  await card.view.flush();
  const created = card.calls.find((c) => c.op === "create");
  assert.equal(created.sourceKind, "routine");
  assert.deepEqual(created.sourceIds, ["routine-11", "routine-13"]);
  assert.equal(created.start, "2026-11-02");
  assert.equal(created.end, "2026-11-08");
});

test("만든 일지는 문서 보관함으로 보내지 않고 이 화면에서 편집기를 연다", async (t) => {
  const card = journalCard(t, {
    dailies: [{ id: "doc-1", start: "2026-11-03", status: "confirmed", origin: "ai" }],
  });
  await card.view.flush();
  makeButton(card.view).props.onClick();
  await card.view.flush();
  assert.equal(
    card.calls.some((c) => c.op === "push"),
    false,
  );
  assert.ok(
    card.calls.some((c) => c.op === "edit" && c.id === "doc-99"),
    JSON.stringify(card.calls),
  );
  assert.ok(all(card.view.tree()).some((n) => n?.type === "document-editor"));
});

test("근거가 하나도 없으면 만들기를 막고 무엇이 없는지 말한다", async (t) => {
  const card = journalCard(t);
  await card.view.flush();
  assert.equal(makeButton(card.view).props.disabled, true);
  assert.ok(card.text().includes("확정한 일일 보육일지가 없습니다"), card.text());
});

test("초안인 일일 일지는 근거로 세지 않고, 확정하러 갈 길을 준다", async (t) => {
  const card = journalCard(t, {
    dailies: [
      { id: "doc-1", start: "2026-11-03", status: "confirmed", origin: "ai" },
      { id: "doc-2", start: "2026-11-04", status: "draft", origin: "ai" },
    ],
  });
  await card.view.flush();
  makeButton(card.view).props.onClick();
  await card.view.flush();
  // 근거는 확정본 하나뿐이다.
  assert.deepEqual(card.calls.find((c) => c.op === "create").sourceIds, ["doc-1"]);
});

test("확정한 일일 일지가 없고 초안만 있으면 초안이라고 말하고 그날로 보낸다", async (t) => {
  const card = journalCard(t, {
    dailies: [{ id: "doc-2", start: "2026-11-04", status: "draft", origin: "ai" }],
  });
  await card.view.flush();
  assert.equal(makeButton(card.view).props.disabled, true);
  assert.ok(card.text().includes("근거로 쓸 수 없어요"), card.text());
  assert.ok(card.text().includes("초안"), card.text());
  // 그날로 옮기지 않고 이 화면 편집기에서 바로 확정한다.
  const confirmHere = all(card.view.tree()).find(
    (n) => n?.type === "button" && deepText(n).includes("여기서 확정"),
  );
  confirmHere.props.onClick();
  await card.view.flush();
  assert.ok(
    card.calls.some((c) => c.op === "edit" && c.id === "doc-2"),
    JSON.stringify(card.calls),
  );
  assert.ok(all(card.view.tree()).some((n) => n?.type === "document-editor"));
});

test("주간 일지를 펴면 총평 옆에 그 주 확정한 일일 평가를 보여만 준다", async (t) => {
  const card = journalCard(t, {
    weeklies: [draftWeekly],
    dailies: [
      { id: "doc-1", start: "2026-11-03", status: "confirmed", origin: "ai" },
      { id: "doc-2", start: "2026-11-04", status: "draft", origin: "ai" },
    ],
  });
  await card.view.flush();
  const open = all(card.view.tree()).find(
    (n) => n?.type === "button" && deepText(n).includes("이어서 쓰기"),
  );
  open.props.onClick();
  await card.view.flush();
  const text = card.text();
  assert.ok(text.includes("이 주 일일 평가"), text);
  assert.ok(text.includes("doc-1 의 해석"), text);
  assert.equal(text.includes("doc-2 의 해석"), false, "초안 평가는 보여 주지 않는다");
  // 보여 주기만 한다 — 만들기 · 검토로 보내는 요청이 없다.
  assert.deepEqual(
    card.calls.filter((c) => c.op === "get").map((c) => c.id),
    ["doc-1"],
  );
});

// ── 3차 점검 4 · 7 — 주간 · 일일 일지 칸 ─────────────────────────────

const editorOpen = (view) => all(view.tree()).find((n) => n?.type === "document-editor");

test("3차-7 서버가 거절할 일일(올린 서류 · 근거 바뀜 · 초안)은 근거에서 빼고 이유와 고칠 길을 준다", async (t) => {
  const card = journalCard(t, {
    dailies: [
      { id: "doc-1", start: "2026-11-03", status: "confirmed", origin: "ai", stale: false },
      { id: "doc-2", start: "2026-11-04", status: "confirmed", origin: "import", stale: false },
      { id: "doc-3", start: "2026-11-05", status: "confirmed", origin: "ai", stale: true },
      { id: "doc-4", start: "2026-11-06", status: "draft", origin: "ai", stale: false },
    ],
  });
  await card.view.flush();
  makeButton(card.view).props.onClick();
  await card.view.flush();
  assert.deepEqual(card.calls.find((c) => c.op === "create").sourceIds, ["doc-1"]);
  // 만들기 전 화면으로 다시 본다.
  const before = journalCard(t, {
    dailies: [
      { id: "doc-2", start: "2026-11-04", status: "confirmed", origin: "import", stale: false },
      { id: "doc-3", start: "2026-11-05", status: "confirmed", origin: "ai", stale: true },
    ],
  });
  await before.view.flush();
  assert.equal(makeButton(before.view).props.disabled, true);
  const text = before.text();
  assert.ok(text.includes("올린 서류"), text);
  assert.ok(text.includes("근거가 바뀜"), text);
  const links = all(before.view.tree())
    .filter((n) => n?.props?.href)
    .map((n) => n.props.href);
  assert.ok(links.includes("/routines?date=2026-11-04"), links.join(" , "));
  assert.ok(links.includes("/routines?date=2026-11-05"), links.join(" , "));
});

test("3차-4 주를 바꾸면 이전 주 일지 편집기를 닫는다", async (t) => {
  const week = { start: "2026-11-02", end: "2026-11-08" };
  const card = journalCard(t, { weeklies: [draftWeekly], week });
  await card.view.flush();
  card.state().open(draftWeekly.id);
  await card.view.flush();
  assert.ok(editorOpen(card.view), "이번 주 일지를 폈다");

  week.start = "2026-11-09";
  week.end = "2026-11-15";
  await card.view.flush();
  assert.equal(editorOpen(card.view), undefined, "다른 주에는 이전 편집기가 없다");
  assert.equal(card.state().openId, "");
});

test("3차-4 주를 바꾼 뒤 늦게 온 생성 응답은 새 주에 편집기를 열지 않는다", async (t) => {
  const week = { start: "2026-11-02", end: "2026-11-08" };
  let answer;
  const card = journalCard(t, {
    week,
    dailies: [{ id: "doc-1", start: "2026-11-03", status: "confirmed", origin: "ai" }],
    create: () => new Promise((resolve) => (answer = resolve)),
  });
  await card.view.flush();
  makeButton(card.view).props.onClick();
  week.start = "2026-11-09";
  week.end = "2026-11-15";
  await card.view.flush();
  answer({ id: "doc-99" });
  await card.view.flush();
  assert.equal(editorOpen(card.view), undefined);
  assert.equal(card.state().openId, "");
});

test("3차-4 저장 안 한 일지 글이 있으면 주를 옮기기 전에 묻는다", async (t) => {
  const card = journalCard(t, { weeklies: [draftWeekly] });
  await card.view.flush();
  card.state().open(draftWeekly.id);
  await card.view.flush();
  assert.equal(card.state().leave(), true, "고친 것이 없으면 묻지 않는다");
  editorOpen(card.view).props.onDirty(true);
  await card.view.flush();
  const asked = [];
  globalThis.window = { confirm: (q) => (asked.push(q), false) };
  t.after(() => delete globalThis.window);
  assert.equal(card.state().leave(), false, "교사가 취소하면 옮기지 않는다");
  assert.equal(asked.length, 1);
});

function dailyCard(t, { dailies = [], day, create } = {}) {
  const calls = [];
  const app = host();
  t.after(() => app.cleanup());
  const Card = compile("../components/workspace/DailyJournalCard.tsx", {
    "react/jsx-runtime": runtime,
    react: app.react,
    "./WorkspaceUI": { Message: "message", ws: {} },
    "@/components/app/Posty": { Posty: "posty" },
    "./DocumentEditor": { __esModule: true, default: "document-editor" },
    "./use-server-document": {
      useServerDocument: (id) => ({
        doc: id ? { id, sections: [] } : null,
        status: "ready",
        error: "",
        server: undefined,
      }),
    },
    "@/lib/api/onboarding": { classServerId: (id) => (id === "class-1" ? 7 : null) },
    "@/lib/onboarding/settings": { loadClassSettings: () => ({ classes: [{ id: "class-1" }] }) },
    "@/lib/workspace/journal-day": journalDay,
    "@/lib/api/documents": {
      listDocuments: async () => dailies,
      getDocument: async (id) => ({ id, sections: [] }),
      createDocument: async (input) => {
        calls.push({ op: "create", ...input });
        return create ? create(input) : { id: "doc-99" };
      },
    },
  });
  let current;
  const view = app.mount(() => {
    const state = Card.useDailyJournal({ classId: 7, date: day.date });
    current = state;
    return jsx("div", { children: [Card.DailyJournalEditor({ state, day: day.date })] });
  });
  return { view, calls, state: () => current };
}

test("3차-4 날짜를 바꾸면 이전 날 일지 편집기를 닫고, 늦은 생성 응답도 새 날에 열지 않는다", async (t) => {
  const day = { date: "2026-11-03" };
  const made = { id: "doc-1", start: "2026-11-03", status: "draft", origin: "ai" };
  const card = dailyCard(t, { dailies: [made], day });
  await card.view.flush();
  card.state().open(made.id);
  await card.view.flush();
  assert.ok(editorOpen(card.view));
  day.date = "2026-11-04";
  await card.view.flush();
  assert.equal(editorOpen(card.view), undefined);
  assert.equal(card.state().doc, null, "새 날에는 일지가 없다");

  let answer;
  const lateDay = { date: "2026-11-05" };
  const late = dailyCard(t, {
    day: lateDay,
    create: () => new Promise((resolve) => (answer = resolve)),
  });
  await late.view.flush();
  const making = late.state().make(["routine:1"]);
  lateDay.date = "2026-11-06";
  await late.view.flush();
  answer({ id: "doc-77" });
  await making;
  await late.view.flush();
  assert.equal(late.state().openId, "", "만들던 날이 아니면 열지 않는다");
  assert.equal(editorOpen(late.view), undefined);
});
