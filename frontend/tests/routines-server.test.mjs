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
    confirm: (text) => {
      confirms.push(text);
      return confirm;
    },
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
        effects[index].cleanup = fn();
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
const YESTERDAY = "2026-10-05";

test("AC6: 같은 문서를 바꾼 PUT·DELETE를 합치고 기존 stale은 따로 센다", async (t) => {
  const api = recorder({ rows: [row({ id: 1 }), row({ id: 2 }), row({ id: 3 })] });
  const update = api.api.update;
  api.api.update = async (id, body, options) => {
    assert.deepEqual(options, { includeImpact: true });
    return {
      ...(await update(id, body)),
      review_impact: {
        affected_document_ids: [11, 12],
        newly_stale_document_ids: id === 1 ? [11] : [],
      },
    };
  };
  const remove = api.api.remove;
  api.api.remove = async (id, options) => {
    assert.deepEqual(options, { includeImpact: true });
    await remove(id);
    return { review_impact: { affected_document_ids: [11, 12], newly_stale_document_ids: [] } };
  };
  const view = page(t, api.api);
  await view.flush();
  view.type(view.textareas()[1], "첫 실행 변경");
  view.type(view.textareas()[3], "둘째 실행 변경");
  view.rowButton(2, "줄 지우기").props.onClick();
  await view.flush();
  view.button("저장").props.onClick();
  await view.flush();
  assert.ok(
    view.errors().some((text) => text.includes("보육일지 1건이 다시 검토 대상")),
    view.errors(),
  );
  assert.ok(
    view.errors().some((text) => text.includes("이미 재검토 대상인 보육일지 1건")),
    view.errors(),
  );
});

test("AC6: 부분 저장 실패는 성공 안내 없이 입력·영향 ID를 보존하고 재시도한다", async (t) => {
  const api = recorder({ rows: [row({ id: 1 })] });
  const update = api.api.update;
  api.api.update = async (id, body) => ({
    ...(await update(id, body)),
    review_impact: {
      affected_document_ids: [17],
      newly_stale_document_ids: [17],
    },
  });
  const create = api.api.create;
  let fail = true;
  api.api.create = async (...args) => {
    if (fail) throw new Error("새 줄 저장 실패");
    return create(...args);
  };
  const view = page(t, api.api);
  await view.flush();
  view.type(view.textareas()[1], "먼저 저장된 실행");
  await addNamed(view, "재시도할 새 줄");
  view.button("저장").props.onClick();
  await view.flush();
  assert.ok(view.errors().includes("새 줄 저장 실패"));
  assert.equal(view.text().includes("다시 검토 대상"), false);
  assert.ok(view.nameValues().includes("재시도할 새 줄"));
  fail = false;
  view.button("저장").props.onClick();
  await view.flush();
  assert.equal(api.only("update").length, 1, "성공한 변경을 다시 보내지 않는다");
  assert.ok(
    view.errors().some((text) => text.includes("보육일지 1건이 다시 검토 대상")),
    view.errors(),
  );
});

/**
 * 하루치 서버. **오간 요청을 전부 적어 둔다** — 「저장을 누르기 전에는 아무것도 안 보낸다」는
 * 보낸 게 없다는 것으로만 증명된다.
 */
function recorder({ rows = [], fail = null } = {}) {
  const calls = [];
  // Pydantic time 응답처럼 HH:mm 입력도 HH:mm:ss 로 저장/돌려준다. 요청 body 는 그대로 기록한다.
  const serverTime = (time) =>
    typeof time === "string" && time.length === 5 ? `${time}:00` : time;
  const stored = (routine) => ({
    ...routine,
    start: serverTime(routine.start),
    end: serverTime(routine.end),
  });
  let store = rows.map(stored);
  let nextId = 900;
  const only = (op) => calls.filter((c) => c.op === op);
  return {
    calls,
    only,
    rows: () => store,
    api: {
      list: async (params) => {
        calls.push({ op: "list", params });
        // 서버가 정하는 순서 그대로 — position · 시작 시간(없으면 뒤) · id (§10-1).
        return {
          items: store
            .filter((r) => r.date === params.from && r.class_id === params.class_id)
            .map((r) => ({ ...r }))
            .sort(
              (a, b) =>
                a.position - b.position ||
                (a.start ?? "99").localeCompare(b.start ?? "99") ||
                a.id - b.id,
            ),
        };
      },
      create: async (class_id, input) => {
        calls.push({ op: "create", class_id, input });
        if (fail === "create") throw new Error("만들지 못했어요");
        const made = stored({ ...ROW, ...input, id: (nextId += 1), class_id });
        store = [...store, made];
        return made;
      },
      update: async (id, input) => {
        calls.push({ op: "update", id, input });
        if (fail === "update") throw new Error("저장하지 못했어요");
        const next = stored({ ...ROW, ...input, id });
        store = store.map((r) => (r.id === id ? next : r));
        return next;
      },
      remove: async (id) => {
        calls.push({ op: "remove", id });
        if (fail === "remove") throw new Error("지우지 못했어요");
        store = store.filter((r) => r.id !== id);
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
  { search = "", classes, rooms = [CLASS_A], primaryClassId = "class-abc", confirm = true } = {},
) {
  const confirms = browser({ rooms, primaryClassId, search, confirm });
  const pushed = [];
  t.after(() => delete globalThis.window);

  const app = host();
  let mutations = routineMutationBarriers.get(api);
  if (!mutations) {
    mutations = createMutationBarrier();
    routineMutationBarriers.set(api, mutations);
  }
  const Page = compile("../components/workspace/RoutinesPage.tsx", {
    "react/jsx-runtime": runtime,
    react: app.react,
    "next/link": { default: "link" },
    "next/navigation": { useRouter: () => ({ push: (href) => pushed.push(href) }) },
    "@/lib/api/auth": { getMe: async () => ({ id: 1, center_id: 42 }) },
    "@/lib/api/classes": {
      getClasses: async () => ({ items: classes ?? [{ id: 3, name: "햇살반" }] }),
    },
    "@/lib/api/client": { isUnauthenticated: () => false },
    "@/lib/api/onboarding": onboardingApi,
    "@/lib/onboarding/settings": classSettings,
    "@/lib/workspace/routines-route": routinesRoute,
    "@/lib/hooks/use-client-state": { useClientState: (read) => app.state(read) },
    // 관찰 영역 축은 서버 설정에서 온다. 여기서 보는 것은 길 · 저장이라 기본 축으로 둔다.
    "@/lib/hooks/use-observation-domains": { useObservationDomains: () => OBSERVATION_DOMAINS },
    "@/lib/api/routines": {
      listRoutines: async (...args) => (await api.list(...args)).items,
      createRoutine: api.create,
      updateRoutine: api.update,
      deleteRoutine: api.remove,
      trackRoutineMutation: mutations.track,
      waitForRoutineScope: mutations.wait,
      routineTime: routines.routineTime,
      routineTimeValue: routines.routineTimeValue,
      sortRoutinesByTime: routines.sortRoutinesByTime,
    },
    "@/lib/workspace/model": {
      today: () => TODAY,
      validDate: (value) => /^\d{4}-\d{2}-\d{2}$/.test(value),
    },
    "./WorkspaceUI": { WorkspacePage: "page", Empty: "empty", Message: "message", ws: {} },
    "./WorkspaceViewState": { WorkspaceViewState },
    "./RoutineTimePicker": compile("../components/workspace/RoutineTimePicker.tsx", {
      "react/jsx-runtime": runtime,
      react: app.react,
      "@/lib/api/routines": routines,
      "./WorkspaceUI": { ws: {} },
    }),
  }).default;

  const view = app.mount(Page);
  t.after(app.cleanup);

  const find = (type) => all(view.tree()).filter((node) => node?.type === type);
  const labelled = (node) => String([node.props.children].flat().join(""));
  return {
    confirms,
    pushed,
    unmount: app.cleanup,
    flush: view.flush,
    render: view.render,
    /** 지금 주소창의 질의. 화면이 적어 둔 반 · 날짜가 여기 보여야 한다. */
    search: () => globalThis.window.location.search,
    classSelect: () => find("select")[0],
    dateInput: () => find("input").find((node) => node.props.type === "date"),
    /** 이름 칸들. 줄 순서 그대로다. */
    names: () => find("input").filter((node) => node.props.maxLength === 50),
    nameValues: () =>
      find("input")
        .filter((n) => n.props.maxLength === 50)
        .map((n) => n.props.value),
    // 기존 사례는 24시간 값으로 지정하고 실제 피커의 세 컨트롤을 조작한다.
    times: () =>
      all(view.tree())
        .filter((n) => n?.props?.role === "group")
        .map((group, index) => ({
          props: {
            value: (() => {
              const selects = all(group).filter((n) => n?.type === "select");
              const toggle = all(group).find((n) => n?.props?.["aria-label"]?.endsWith("AM/PM"));
              return routines.routineTimeFrom12(
                selects[0].props.value,
                selects[1].props.value,
                toggle.props.children,
              );
            })(),
            onChange: ({ target: { value } }) => {
              const controls = () =>
                all(all(view.tree()).filter((n) => n?.props?.role === "group")[index]);
              if (!value) {
                controls()
                  .find((n) => n?.props?.["aria-label"]?.endsWith("시간 지우기"))
                  .props.onClick();
                view.render();
                return;
              }
              const parts = routines.routineTimeParts12(value);
              controls()
                .filter((n) => n?.type === "select")[0]
                .props.onChange({ target: { value: parts.hour } });
              view.render();
              controls()
                .filter((n) => n?.type === "select")[1]
                .props.onChange({ target: { value: parts.minute } });
              view.render();
              const toggle = controls().find((n) => n?.props?.["aria-label"]?.endsWith("AM/PM"));
              if (toggle.props.children !== parts.period) {
                toggle.props.onClick();
                view.render();
              }
            },
          },
        })),
    textareas: () => find("textarea"),
    cards: () => find("article"),
    handles: () => all(view.tree()).filter((node) => node?.props?.draggable !== undefined),
    empties: () => find("empty").map((node) => node.props.title),
    loading: () => all(view.tree()).some((node) => node?.props?.["aria-busy"] === "true"),
    errors: () => find("message").map((node) => String(node.props.children ?? "")),
    text: () =>
      all(view.tree())
        .filter((part) => typeof part === "string")
        .join(" "),
    anyButton: (label) => find("button").find((node) => labelled(node).includes(label)),
    /** 그 줄 안의 버튼. 줄마다 같은 이름의 버튼이 있어 전체에서 찾으면 첫 줄만 눌린다. */
    rowButton: (index, label) =>
      all(find("article")[index]).find(
        (node) => node?.type === "button" && labelled(node).includes(label),
      ),
    button: (label) =>
      find("button").find((node) => labelled(node).includes(label) && !node.props.disabled),
    type: (node, value) => node.props.onChange({ target: { value } }),
  };
}

const fill = (view, index, value) => view.type(view.names()[index], value);

/** 브라우저가 dragstart 에 들려 보내는 것. 담은 값을 그대로 읽을 수 있다. */
const dragEvent = () => {
  const data = {};
  return {
    currentTarget: {
      closest: () => null,
      getBoundingClientRect: () => ({ top: 0, height: 100 }),
      contains: () => false,
    },
    clientX: 0,
    clientY: 0,
    dataTransfer: {
      setData: (type, value) => (data[type] = value),
      getData: (type) => data[type] ?? "",
      data,
    },
  };
};

// ── 주소 · 반 고르기 (S-J1 canonical route) ────────────────────────────────

test("주소의 날짜 · 반으로 연다 — 없으면 오늘과 주 반이다", async (t) => {
  const api = recorder();
  const view = page(t, api.api, {
    search: "?date=2026-10-02&class_id=7",
    classes: [
      { id: 3, name: "햇살반" },
      { id: 7, name: "별빛반" },
    ],
  });
  await view.flush();
  assert.deepEqual(api.only("list").at(-1).params, {
    class_id: 7,
    from: "2026-10-02",
    to: "2026-10-02",
  });
  assert.equal(view.classSelect().props.value, 7);
  assert.equal(view.dateInput().props.value, "2026-10-02");
});

test("주소에 아무것도 없으면 오늘 · 주 반이다", async (t) => {
  const api = recorder();
  const view = page(t, api.api);
  await view.flush();
  assert.deepEqual(api.only("list").at(-1).params, { class_id: 3, from: TODAY, to: TODAY });
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
  assert.deepEqual(api.only("list"), [], "반을 모르면 묻지 않는다");
  assert.deepEqual(view.empties(), ["반을 골라주세요"]);

  view.type(view.classSelect(), "7");
  await view.flush();
  assert.deepEqual(api.only("list").at(-1).params, { class_id: 7, from: TODAY, to: TODAY });
});

test("주소의 반 번호가 목록에 없으면 첫 반으로 조용히 바꾸지 않는다", async (t) => {
  const api = recorder();
  const view = page(t, api.api, { search: "?class_id=99" });
  await view.flush();
  assert.deepEqual(api.only("list"), []);
  assert.deepEqual(view.empties(), ["반을 골라주세요"]);
  assert.match(view.text(), /주소에 적힌 반을 찾을 수 없어요/);
});

// ── 초안 모델 — 저장을 누르기 전에는 아무것도 안 보낸다 (FR-402) ───────────

test("그날 적은 게 없으면 빈 줄 다섯 개를 깐다", async (t) => {
  const api = recorder();
  const view = page(t, api.api);
  await view.flush();
  assert.equal(view.names().length, 5);
  assert.deepEqual(view.nameValues(), ["", "", "", "", ""]);
  assert.equal(view.textareas().length, 10, "줄마다 활동계획 · 활동실행 둘");
  assert.deepEqual(view.empties(), [], "빈 줄을 깔았으니 「없어요」가 아니다");
});

test("이미 적은 줄이 있으면 빈 줄 다섯을 덧붙이지 않는다", async (t) => {
  const api = recorder({ rows: [row({ id: 1 }), row({ id: 2, name: "바깥놀이" })] });
  const view = page(t, api.api);
  await view.flush();
  assert.deepEqual(view.nameValues(), ["오전 실내놀이", "바깥놀이"]);
});

test("「+ 줄 추가」만 눌러서는 서버에 아무것도 가지 않는다", async (t) => {
  const api = recorder();
  const view = page(t, api.api);
  await view.flush();
  view.button("+ 줄 추가").props.onClick();
  view.render();
  view.button("+ 줄 추가").props.onClick();
  await view.flush();
  assert.equal(view.names().length, 7);
  assert.deepEqual(api.only("create"), [], "추가로 POST 하지 않는다");
});

test("「줄 지우기」만 눌러서는 DELETE 하지 않는다 — 저장할 때 지운다", async (t) => {
  const api = recorder({ rows: [row({ id: 1 }), row({ id: 2, name: "바깥놀이" })] });
  const view = page(t, api.api);
  await view.flush();
  view.rowButton(0, "줄 지우기").props.onClick();
  await view.flush();
  assert.deepEqual(view.nameValues(), ["바깥놀이"], "첫 줄이 화면에서 사라진다");
  assert.deepEqual(api.only("remove"), [], "저장 전에는 지우지 않는다");
  assert.equal(api.rows().length, 2, "서버에는 그대로 있다");

  view.button("저장").props.onClick();
  await view.flush();
  assert.deepEqual(
    api.only("remove").map((c) => c.id),
    [1],
  );
  assert.equal(api.rows().length, 1);
});

test("지우고 저장하지 않고 나가면 서버 줄은 그대로다", async (t) => {
  const api = recorder({ rows: [row({ id: 1 })] });
  const view = page(t, api.api);
  await view.flush();
  view.button("줄 지우기").props.onClick();
  await view.flush();
  view.unmount();
  await settle();
  assert.deepEqual(api.only("remove"), []);
  assert.equal(api.rows().length, 1);
});

test("통째로 빈 줄은 보내지 않고, 한 칸이라도 적힌 줄은 버리지 않는다", async (t) => {
  const api = recorder();
  const view = page(t, api.api);
  await view.flush();
  fill(view, 0, "등원");
  view.render();
  view.type(view.times()[2], "10:00"); // 둘째 줄 시작 시간만
  view.render();
  fill(view, 1, "오전 간식");
  await view.flush();

  view.button("저장").props.onClick();
  await view.flush();
  const made = api.only("create");
  assert.equal(made.length, 2, "빈 줄 셋은 보내지 않는다");
  assert.deepEqual(
    made.map((c) => c.input.name),
    ["등원", "오전 간식"],
  );
  assert.equal(made[1].input.start, "10:00", "적은 시간이 같이 간다");
});

test("일곱 줄을 한 번에 — 새 줄은 POST, 고친 줄은 PUT, 지운 줄은 DELETE", async (t) => {
  const api = recorder({ rows: [row({ id: 1, name: "등원" }), row({ id: 2, name: "지울 줄" })] });
  const view = page(t, api.api);
  await view.flush();
  for (let i = 0; i < 6; i += 1) {
    view.button("+ 줄 추가").props.onClick();
    view.render();
  }
  // 둘째(서버) 줄을 지우고, 첫째 줄 이름을 고치고, 새 줄 여섯을 채운다 → 일곱 줄.
  view.names()[1].props.onChange({ target: { value: "지울 줄" } });
  view.render();
  view.rowButton(1, "줄 지우기").props.onClick();
  view.render();
  fill(view, 0, "등원 고침");
  view.render();
  for (let i = 1; i <= 6; i += 1) {
    fill(view, i, `일과 ${i}`);
    view.render();
  }
  assert.equal(view.names().length, 7);

  view.button("저장").props.onClick();
  await view.flush();

  assert.deepEqual(
    api.only("remove").map((c) => c.id),
    [2],
  );
  assert.deepEqual(
    api.only("update").map((c) => c.input.name),
    ["등원 고침"],
  );
  assert.equal(api.only("create").length, 6);
  // 다시 읽어도 그대로다.
  assert.deepEqual(view.nameValues(), [
    "등원 고침",
    "일과 1",
    "일과 2",
    "일과 3",
    "일과 4",
    "일과 5",
    "일과 6",
  ]);
  assert.equal(api.rows().length, 7);
});

test("PUT 은 계약의 일곱 칸을 통째로 보낸다 — class_id 는 넣지 않고 빈 시간은 null 이다", async (t) => {
  const api = recorder({ rows: [row({ id: 1 })] });
  const view = page(t, api.api);
  await view.flush();
  view.type(view.times()[0], "");
  view.render();
  view.type(view.times()[1], "");
  view.render();
  fill(view, 0, "이름 고침");
  await view.flush();

  view.button("저장").props.onClick();
  await view.flush();
  const sent = api.only("update")[0];
  assert.equal(sent.id, 1);
  assert.deepEqual(sent.input, {
    date: TODAY,
    // 순서를 바꾸지 않았으니 **서버가 준 번호 그대로**다 — 0 으로 다시 매기지 않는다.
    position: ROW.position,
    start: null,
    end: null,
    name: "이름 고침",
    plan: ROW.plan,
    execution: ROW.execution,
  });
  assert.equal("class_id" in sent.input, false, "반이 바뀌면 다른 기록이다 — 422 다");
});

// ── 거절 처리 (FR-402 예외) ────────────────────────────────────────────────

const COUNTEREXAMPLES = [
  ["이름만", (view) => fill(view, 0, "등원")],
  ["시작시간만", (view) => view.type(view.times()[0], "09:00")],
  ["끝시간만", (view) => view.type(view.times()[1], "09:30")],
  ["활동계획만", (view) => view.type(view.textareas()[0], "자동차 굴리기")],
  ["활동실행만", (view) => view.type(view.textareas()[1], "블록을 쌓았다")],
  [
    "시간 + 활동실행",
    (view) => {
      view.type(view.times()[0], "09:00");
      view.type(view.textareas()[1], "블록을 쌓았다");
    },
  ],
];

for (const [label, write] of COUNTEREXAMPLES)
  test(`${label} 적은 줄은 조용히 사라지지 않는다`, async (t) => {
    const api = recorder();
    const view = page(t, api.api);
    await view.flush();
    write(view);
    await view.flush();
    view.button("저장").props.onClick();
    await view.flush();

    if (label === "이름만") {
      assert.equal(api.only("create").length, 1, "이름이 있으면 저장된다");
      return;
    }
    assert.deepEqual(api.only("create"), [], "이름이 없으면 아무것도 보내지 않는다");
    assert.ok(view.errors().some((text) => text.includes("일과 이름을 적어 주세요")));
  });

test("활동실행만 적고 이름이 없으면 요청 0 · 그 줄에 안내 · 적은 글자 유지", async (t) => {
  const api = recorder();
  const view = page(t, api.api);
  await view.flush();
  view.type(view.textareas()[1], "블록 3개로 길을 만들었다.");
  await view.flush();

  view.button("저장").props.onClick();
  await view.flush();
  assert.deepEqual(
    api.calls.filter((c) => c.op !== "list"),
    [],
    "아무것도 보내지 않는다",
  );
  assert.ok(view.errors().some((text) => text.includes("일과 이름을 적어 주세요")));
  assert.equal(view.textareas()[1].props.value, "블록 3개로 길을 만들었다.", "적은 글자가 남는다");
});

test("완전히 비운 줄은 저장 요청에서 제외하고 기존 줄 삭제는 명시적인 지우기로만 한다", async (t) => {
  const api = recorder({ rows: [row({ id: 1 })] });
  const view = page(t, api.api);
  await view.flush();
  view.type(view.names()[0], "");
  view.type(view.times()[0], "");
  view.type(view.times()[1], "");
  view.type(view.textareas()[0], "");
  view.type(view.textareas()[1], "");
  await view.flush();
  view.button("저장").props.onClick();
  await view.flush();
  assert.equal(api.calls.filter((call) => call.op !== "list").length, 0);
  assert.equal(api.rows().length, 1);
});

test("끝나는 시간이 시작보다 빠르면 저장을 멈춘다", async (t) => {
  const api = recorder();
  const view = page(t, api.api);
  await view.flush();
  fill(view, 0, "등원");
  view.render();
  view.type(view.times()[0], "10:00");
  view.render();
  view.type(view.times()[1], "09:00");
  await view.flush();

  view.button("저장").props.onClick();
  await view.flush();
  assert.deepEqual(api.only("create"), []);
  assert.ok(view.errors().some((text) => text.includes("끝나는 시간이 시작보다 빨라요")));
});

test("저장이 실패해도 적은 글자를 지우지 않고 다시 누를 수 있다", async (t) => {
  const api = recorder({ fail: "create" });
  const view = page(t, api.api);
  await view.flush();
  fill(view, 0, "등원");
  await view.flush();

  view.button("저장").props.onClick();
  await view.flush();
  assert.equal(view.nameValues()[0], "등원");
  assert.ok(view.errors().some((text) => text.includes("만들지 못했어요")));
  assert.ok(view.button("저장"), "다시 누를 수 있다");
});

test("일부만 성공하면 성공으로 쓰지 않고, 다시 눌러도 같은 줄을 두 번 만들지 않는다", async (t) => {
  let failNext = false;
  const api = recorder();
  const create = api.api.create;
  api.api.create = async (classId, input) => {
    if (failNext && input.name === "둘째") throw new Error("만들지 못했어요");
    return create(classId, input);
  };
  const view = page(t, api.api);
  await view.flush();
  fill(view, 0, "첫째");
  view.render();
  fill(view, 1, "둘째");
  await view.flush();

  failNext = true;
  view.button("저장").props.onClick();
  await view.flush();
  assert.equal(api.rows().length, 1, "첫째만 서버에 들어갔다");
  assert.ok(view.errors().some((text) => text.includes("만들지 못했어요")));
  assert.deepEqual(view.nameValues().slice(0, 2), ["첫째", "둘째"], "초안을 비우지 않는다");

  failNext = false;
  view.button("저장").props.onClick();
  await view.flush();
  assert.equal(api.rows().filter((r) => r.name === "첫째").length, 1, "첫째를 또 만들지 않는다");
  assert.equal(api.rows().filter((r) => r.name === "둘째").length, 1);
});

// ── 끌어서 순서 바꾸기 (S-J1) ──────────────────────────────────────────────

test("C 를 맨 앞으로 끌면 C A B 가 되고, 저장하면 그 순서가 position 으로 간다", async (t) => {
  const api = recorder({
    rows: [
      row({ id: 1, name: "A", position: 0 }),
      row({ id: 2, name: "B", position: 1 }),
      row({ id: 3, name: "C", position: 2 }),
    ],
  });
  const view = page(t, api.api);
  await view.flush();
  assert.deepEqual(view.nameValues(), ["A", "B", "C"]);

  view.handles()[2].props.onDragStart(dragEvent());
  view.render();
  view.cards()[0].props.onDrop({ ...dragEvent(), preventDefault: () => {} });
  view.render();
  assert.deepEqual(view.nameValues(), ["C", "A", "B"]);

  view.button("저장").props.onClick();
  await view.flush();
  assert.ok(api.only("update").length <= 2, "C 와 필요한 경계만 고치면 되는데 전부 보냈다");
  assert.equal(api.only("create").length, 0);
  assert.equal(api.only("remove").length, 0);
  // 실제 GET 의 position · start NULLS LAST · id 정렬을 거쳐야 한다.
  assert.deepEqual(
    (await api.api.list({ class_id: 3, from: TODAY, to: TODAY })).items.map((r) => r.name),
    ["C", "A", "B"],
  );
  assert.deepEqual(view.nameValues(), ["C", "A", "B"]);
});

test("키보드로도 순서를 바꿀 수 있다", async (t) => {
  const api = recorder({ rows: [row({ id: 1, name: "A" }), row({ id: 2, name: "B" })] });
  const view = page(t, api.api);
  await view.flush();
  view.button("↓").props.onClick();
  view.render();
  assert.deepEqual(view.nameValues(), ["B", "A"]);
});

// ── 어제 일과 불러오기 (FR-403) ────────────────────────────────────────────

test("어제 일과는 시간과 이름만 가져오고, 누른다고 저장되지 않는다", async (t) => {
  const api = recorder({
    rows: [
      row({
        id: 11,
        date: YESTERDAY,
        name: "등원",
        start: "09:00:00",
        end: "09:30:00",
        plan: "어제 계획",
        execution: "어제 한 일",
      }),
    ],
  });
  const view = page(t, api.api);
  await view.flush();

  view.button("어제 일과 불러오기").props.onClick();
  await view.flush();

  assert.deepEqual(api.only("list").at(-1).params, {
    class_id: 3,
    from: YESTERDAY,
    to: YESTERDAY,
  });
  assert.deepEqual(view.nameValues(), ["등원"]);
  assert.deepEqual(
    view.times().map((node) => node.props.value),
    ["09:00", "09:30"],
  );
  assert.deepEqual(
    view.textareas().map((node) => node.props.value),
    ["", ""],
    "활동계획 · 활동실행은 비운다 — 어제 한 일을 오늘로 옮기면 위조다",
  );
  assert.deepEqual(
    api.calls.filter((c) => c.op !== "list"),
    [],
    "불러오기는 조회일 뿐이다",
  );
});

test("적던 줄이 있으면 덮어쓰기 전에 묻고, 아니라고 하면 그대로 둔다", async (t) => {
  const api = recorder({ rows: [row({ id: 11, date: YESTERDAY, name: "등원" })] });
  const view = page(t, api.api, { confirm: false });
  await view.flush();
  fill(view, 0, "적던 줄");
  await view.flush();

  view.button("어제 일과 불러오기").props.onClick();
  await view.flush();
  assert.equal(view.confirms.length, 1);
  assert.equal(view.nameValues()[0], "적던 줄");
});

test("어제 기록이 없으면 그렇다고 알린다", async (t) => {
  const api = recorder();
  const view = page(t, api.api);
  await view.flush();
  view.button("어제 일과 불러오기").props.onClick();
  await view.flush();
  assert.ok(view.errors().some((text) => text.includes("어제 적은 일과가 없어요")));
});

// ── 오늘 일지 만들기 (S-J1 수락 기준 3 · 3-1 · 3-2) ────────────────────────

const DAILY_LOG = `/documents?kind=dailyLog&class_id=3&date=${TODAY}`;

test("저장하지 않은 활동실행만으로도 「오늘 일지 만들기」가 켜진다", async (t) => {
  const api = recorder();
  const view = page(t, api.api);
  await view.flush();
  assert.equal(view.button("오늘 일지 만들기"), undefined, "아무것도 안 적었으면 꺼져 있다");

  view.type(view.textareas()[1], "블록을 쌓았다");
  await view.flush();
  assert.ok(view.button("오늘 일지 만들기"), "저장 여부로 판단하지 않는다");
});

test("먼저 저장하고 그 다음에 S-J2 로 간다", async (t) => {
  const api = recorder();
  const view = page(t, api.api);
  await view.flush();
  fill(view, 0, "오전 실내놀이");
  view.render();
  view.type(view.textareas()[1], "블록을 쌓았다");
  await view.flush();

  view.button("오늘 일지 만들기").props.onClick();
  await view.flush();
  assert.equal(api.only("create").length, 1, "저장이 먼저다");
  assert.deepEqual(view.pushed, [DAILY_LOG]);
});

test("저장이 실패하면 S-J2 로 가지 않고 적은 글자를 그대로 둔다", async (t) => {
  const api = recorder({ fail: "create" });
  const view = page(t, api.api);
  await view.flush();
  fill(view, 0, "오전 실내놀이");
  view.render();
  view.type(view.textareas()[1], "블록을 쌓았다");
  await view.flush();

  view.button("오늘 일지 만들기").props.onClick();
  await view.flush();
  assert.deepEqual(view.pushed, [], "이동하지 않는다");
  assert.equal(view.nameValues()[0], "오전 실내놀이");
  assert.equal(view.textareas()[1].props.value, "블록을 쌓았다");
});

test("이름 없이 활동실행만 적었으면 그 줄에서 멈추고 넘어가지 않는다", async (t) => {
  const api = recorder();
  const view = page(t, api.api);
  await view.flush();
  view.type(view.textareas()[1], "블록을 쌓았다");
  await view.flush();

  view.button("오늘 일지 만들기").props.onClick();
  await view.flush();
  assert.deepEqual(view.pushed, []);
  assert.deepEqual(api.only("create"), []);
  assert.ok(view.errors().some((text) => text.includes("일과 이름을 적어 주세요")));
  assert.equal(view.textareas()[1].props.value, "블록을 쌓았다");
});

test("두 번 눌러도 두 번 저장하거나 두 번 넘어가지 않는다", async (t) => {
  const api = recorder();
  const view = page(t, api.api);
  await view.flush();
  fill(view, 0, "오전 실내놀이");
  view.render();
  view.type(view.textareas()[1], "블록을 쌓았다");
  await view.flush();

  const open = view.button("오늘 일지 만들기");
  open.props.onClick();
  open.props.onClick();
  await view.flush();
  assert.equal(api.only("create").length, 1);
  assert.deepEqual(view.pushed, [DAILY_LOG]);
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
    api.only("list").map((c) => c.params.from),
    [TODAY, "2026-10-07", TODAY],
  );
});

test("날짜를 비우면 조회하지 않고, 불러오는 중으로 남지도 않는다", async (t) => {
  const api = recorder();
  const view = page(t, api.api);
  await view.flush();
  const before = api.only("list").length;
  view.type(view.dateInput(), "");
  await view.flush();
  assert.equal(api.only("list").length, before);
  assert.equal(view.loading(), false);
  assert.deepEqual(view.empties(), ["날짜를 선택해주세요"]);
});

test("조회 실패는 「없어요」가 아니라 실패로 보여주고 다시 시도할 수 있다", async (t) => {
  let fail = true;
  const api = recorder({ rows: [row({ id: 1 })] });
  const list = api.api.list;
  api.api.list = async (params) => {
    if (fail) throw new Error("일과를 불러오지 못했어요.");
    return list(params);
  };
  const view = page(t, api.api);
  await view.flush();
  assert.deepEqual(view.empties(), []);
  assert.ok(view.errors().some((text) => text.includes("일과를 불러오지 못했어요")));

  fail = false;
  view.button("다시 시도").props.onClick();
  await view.flush();
  assert.deepEqual(view.nameValues(), ["오전 실내놀이"]);
});

test("저장이 끝난 뒤에 읽는다 — 방금 저장한 줄이 빠진 화면이 되지 않는다", async (t) => {
  const api = recorder();
  const view = page(t, api.api);
  await view.flush();
  fill(view, 0, "등원");
  await view.flush();
  view.button("저장").props.onClick();
  await view.flush();
  assert.deepEqual(view.nameValues(), ["등원"]);
  assert.match(view.text(), /저장했어요/);
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
});

test("P1-1 주 반을 고르면 그 반이다", () => {
  browser({ rooms: [CLASS_A, CLASS_B], primaryClassId: CLASS_B.id });
  const stored = classSettings.loadClassSettings();
  assert.equal(classSettings.chosenClassFor(stored).id, CLASS_B.id);
  assert.equal(onboardingApi.classServerId(CLASS_B.id), 7);
  delete globalThis.window;
});

// ── P1-2 · 저장이 끝났을 때 아직 그 화면인가 ────────────────────────────────

/** 「오늘 일지 만들기」를 누를 수 있는 상태까지 적고, 저장을 붙잡아 둔다. */
async function heldSave(t, { press = "오늘 일지 만들기", ...options } = {}) {
  const api = recorder();
  const create = api.api.create;
  let release = () => {};
  api.api.create = (classId, input) =>
    new Promise((resolve) => {
      release = () => resolve(create(classId, input));
    });
  const view = page(t, api.api, options);
  await view.flush();
  fill(view, 0, "오전 실내놀이");
  view.render();
  view.type(view.textareas()[1], "블록을 쌓았다");
  await view.flush();
  view.button(press).props.onClick();
  await view.flush();
  assert.deepEqual(view.pushed, [], "저장이 끝나기 전에는 넘어가지 않는다");
  return { api, view, release: () => release() };
}

test("P1-2 저장을 기다리는 사이 반을 바꾸면 옛 반 일지로 넘기지 않는다", async (t) => {
  const { view, release } = await heldSave(t, {
    rooms: [CLASS_A, CLASS_B],
    classes: [
      { id: 3, name: "햇살반" },
      { id: 7, name: "별빛반" },
    ],
  });

  view.type(view.classSelect(), "7");
  await view.flush();
  release();
  await settle();
  await view.flush();

  assert.deepEqual(view.pushed, [], "A 반 일지로 넘어가지 않는다");
  assert.equal(view.classSelect().props.value, 7, "B 반 화면 그대로다");
});

test("P1-2 저장을 기다리는 사이 날짜를 바꿔도 옛 날짜 일지로 넘기지 않는다", async (t) => {
  const { view, release } = await heldSave(t);
  view.type(view.dateInput(), "2026-10-07");
  await view.flush();
  release();
  await settle();
  await view.flush();
  assert.deepEqual(view.pushed, []);
  assert.equal(view.dateInput().props.value, "2026-10-07");
});

test("P1-2 저장을 기다리는 사이 화면을 떠나면 저장이 끝나도 넘어가지 않는다", async (t) => {
  const { api, view, release } = await heldSave(t);
  view.unmount();
  release();
  await settle();
  await settle();
  assert.deepEqual(view.pushed, []);
  // 저장 자체는 끝까지 간다 — 교사가 적은 줄은 서버에 남는다.
  assert.equal(api.rows().length, 1);
});

test("저장을 기다리던 화면을 떠나면 그 뒤에 옛 조회를 보내지 않는다", async (t) => {
  const api = recorder();
  const mutations = createMutationBarrier();
  routineMutationBarriers.set(api.api, mutations);
  let commit;
  void mutations.track(`3|${TODAY}`, new Promise((resolve) => (commit = resolve)));
  const view = page(t, api.api);
  await view.flush();
  assert.deepEqual(api.only("list"), [], "저장이 끝나기 전에는 묻지 않는다");

  view.unmount();
  commit();
  await settle();
  await settle();
  assert.deepEqual(api.only("list"), [], "떠난 화면이 뒤늦게 묻지 않는다");
});

// ── P2 · 지난 scope 의 안내가 남지 않는다 ───────────────────────────────────

test("P2 이전 반에서 띄운 줄 안내가 다시 돌아온 화면에 남지 않는다", async (t) => {
  const api = recorder({ rows: [row({ id: 1, name: "등원" })] });
  const view = page(t, api.api, {
    rooms: [CLASS_A, CLASS_B],
    classes: [
      { id: 3, name: "햇살반" },
      { id: 7, name: "별빛반" },
    ],
  });
  await view.flush();
  view.type(view.names()[0], "");
  await view.flush();
  view.button("저장").props.onClick();
  await view.flush();
  assert.ok(view.errors().some((text) => text.includes("일과 이름을 적어 주세요")));

  view.type(view.classSelect(), "7");
  await view.flush();
  view.type(view.classSelect(), "3");
  await view.flush();

  assert.equal(view.nameValues()[0], "등원", "서버 값이 돌아왔다");
  assert.equal(
    view.errors().some((text) => text.includes("일과 이름을 적어 주세요")),
    false,
    "지난 안내가 남아 있다",
  );
});

test("지난 날짜의 실패 문구가 다음 날짜 화면에 남지 않는다", async (t) => {
  const api = recorder({ fail: "create" });
  const view = page(t, api.api);
  await view.flush();
  fill(view, 0, "등원");
  await view.flush();
  view.button("저장").props.onClick();
  await view.flush();
  assert.ok(view.errors().some((text) => text.includes("만들지 못했어요")));

  view.type(view.dateInput(), "2026-10-07");
  await view.flush();
  assert.equal(
    view.errors().some((text) => text.includes("만들지 못했어요")),
    false,
  );
});

// ── P2 · 안 고친 줄은 다시 보내지 않는다 ────────────────────────────────────

test("P2 고치지 않은 줄은 position 이 0 이 아니어도 다시 보내지 않는다", async (t) => {
  const api = recorder({ rows: [row({ id: 1, position: 2 })] });
  const view = page(t, api.api);
  await view.flush();
  view.button("저장").props.onClick();
  await view.flush();
  assert.deepEqual(
    api.calls.filter((c) => c.op !== "list"),
    [],
    "아무것도 안 고쳤는데 PUT 이 나갔다",
  );

  // 빈 줄을 하나 더해도 — 보내지 않을 줄이라 자리도 차지하지 않는다.
  view.button("+ 줄 추가").props.onClick();
  await view.flush();
  view.button("저장").props.onClick();
  await view.flush();
  assert.deepEqual(
    api.calls.filter((c) => c.op !== "list"),
    [],
  );
});

// ── OLD TASK 2 에서 이어받은 줄 단위 되돌리기 ──────────────────────────────

test("되돌리기는 그 줄만 서버 값으로 돌리고 서버에 묻지 않는다", async (t) => {
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
    api.calls.filter((c) => c.op !== "list"),
    [],
    "되돌리기는 조회도 저장도 아니다",
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
/** 온보딩에는 있는데 **서버 번호를 아직 모르는** 반 (LINKS 에 없다). */
const ROOM_GHOST = {
  id: "class-local-only",
  className: "달빛반",
  children: [{ id: "c", name: "이달" }],
};

/** 관찰 기록 화면 하나. 여기서 보는 것은 **일과 기록으로 가는 길**뿐이다. */
function recordsPage(t, { rooms = [ROOM_A] } = {}) {
  browser({ rooms: [CLASS_A], primaryClassId: CLASS_A.id });
  t.after(() => delete globalThis.window);
  const app = host();
  const Page = compile("../components/workspace/RecordsPage.tsx", {
    "react/jsx-runtime": runtime,
    react: app.react,
    "next/link": { default: "link" },
    "@/lib/hooks/use-client-state": { useClientState: (read) => app.state(read) },
    // 관찰 영역 축은 서버 설정에서 온다. 여기서 보는 것은 길 · 저장이라 기본 축으로 둔다.
    "@/lib/hooks/use-observation-domains": { useObservationDomains: () => OBSERVATION_DOMAINS },
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
    },
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
  };
}

test("P1-3 기록 모아보기에서 고른 반 · 날짜를 그대로 일과 기록으로 들고 간다", async (t) => {
  const view = recordsPage(t);
  await view.flush();
  // 아직 반을 안 골랐다 — 날짜만 들고 간다. 아무 반이나 붙이지 않는다.
  assert.ok(view.links().includes(`/routines?date=${TODAY}&class_id=3`), view.links().join(" , "));

  view.type(view.selects()[0], CLASS_A.id);
  view.render();
  view.type(view.dateInput(), "2026-10-02");
  await view.flush();

  assert.ok(
    view.links().includes("/routines?date=2026-10-02&class_id=3"),
    `문맥을 잃었다: ${view.links().join(" , ")}`,
  );
  assert.equal(
    view.links().some((href) => href === "/routines" || href === "/records/routines"),
    false,
    "문맥 없는 옛 주소를 쓰지 않는다",
  );
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
});

test("P1 CASE A — 고른 반의 서버 번호가 있으면 그 반으로 간다", async (t) => {
  const view = recordsPage(t, { rooms: [ROOM_A, ROOM_B, ROOM_GHOST] });
  await view.flush();
  view.type(view.selects()[0], ROOM_B.id);
  view.render();
  view.type(view.dateInput(), "2026-10-06");
  await view.flush();
  assert.ok(
    view.links().includes("/routines?date=2026-10-06&class_id=7"),
    view.links().join(" , "),
  );
});

test("P1 CASE B — 고른 반의 서버 번호가 없으면 다른 반으로 보내지 않는다", async (t) => {
  const view = recordsPage(t, { rooms: [ROOM_A, ROOM_B, ROOM_GHOST] });
  await view.flush();
  view.type(view.selects()[0], ROOM_GHOST.id);
  view.render();
  view.type(view.dateInput(), "2026-10-06");
  await view.flush();

  assert.deepEqual(
    view.links().filter((href) => href.startsWith("/routines")),
    [],
    "주 반(A)으로 들어가는 길을 만들었다",
  );
  assert.match(view.text(), /일과 기록으로 갈 수 없어요/);
  assert.equal(view.dateInput().props.value, "2026-10-06", "고른 날짜는 그대로 둔다");
});

test("P1-2 저장을 기다리는 사이 반을 바꾸면 새 화면에 「저장했어요」를 띄우지 않는다", async (t) => {
  const { api, view, release } = await heldSave(t, {
    press: "저장",
    rooms: [CLASS_A, CLASS_B],
    classes: [
      { id: 3, name: "햇살반" },
      { id: 7, name: "별빛반" },
    ],
  });
  view.type(view.classSelect(), "7");
  await view.flush();
  const asked = api.only("list").length;

  release();
  await settle();
  await view.flush();

  assert.equal(view.text().includes("저장했어요"), false, "B 반 화면에 A 반 결과를 띄웠다");
  assert.equal(api.only("list").length, asked, "B 반을 공연히 다시 읽었다");
  assert.equal(view.classSelect().props.value, 7);
});

// ── P2 · 안 바꾼 순서는 번호를 고쳐 쓰지 않는다 ────────────────────────────

const three = (positions) =>
  recorder({
    rows: ["A", "B", "C"].map((name, i) =>
      row({ id: i + 1, name, position: positions[i], start: null, end: null }),
    ),
  });
const writes = (api) => api.calls.filter((c) => c.op !== "list");

for (const positions of [
  [0, 0, 0],
  [2, 5, 9],
  [5, 5, 5],
])
  test(`P2 서버 번호가 [${positions}] 여도 손대지 않았으면 아무것도 보내지 않는다`, async (t) => {
    const api = three(positions);
    const view = page(t, api.api);
    await view.flush();
    assert.deepEqual(view.nameValues(), ["A", "B", "C"]);

    view.button("저장").props.onClick();
    await view.flush();
    assert.deepEqual(writes(api), [], "건드리지 않은 줄에 PUT 이 나갔다");
  });

test("P2 번호가 겹친 줄에서 한 줄의 글자만 고치면 그 줄만 보낸다", async (t) => {
  const api = three([5, 5, 5]);
  const view = page(t, api.api);
  await view.flush();
  fill(view, 0, "A 고침");
  await view.flush();

  view.button("저장").props.onClick();
  await view.flush();
  assert.deepEqual(
    writes(api).map((c) => [c.op, c.id, c.input.position, c.input.name]),
    [["update", 1, 5, "A 고침"]],
    "번호를 정리하려고 다른 줄까지 보냈다",
  );
});

test("P2 줄을 지워도 남은 줄의 번호를 공연히 고치지 않는다", async (t) => {
  const api = three([0, 0, 0]);
  const view = page(t, api.api);
  await view.flush();
  view.rowButton(1, "줄 지우기").props.onClick();
  await view.flush();

  view.button("저장").props.onClick();
  await view.flush();
  assert.deepEqual(
    writes(api).map((c) => [c.op, c.id]),
    [["remove", 2]],
    "DELETE 하나면 되는데 PUT 까지 보냈다",
  );
  assert.deepEqual(view.nameValues(), ["A", "C"]);
});

test("P2 맨 뒤에 줄을 더해도 기존 줄 번호를 고치지 않는다", async (t) => {
  const api = three([0, 0, 0]);
  const view = page(t, api.api);
  await view.flush();
  view.button("+ 줄 추가").props.onClick();
  view.render();
  fill(view, 3, "D");
  await view.flush();

  view.button("저장").props.onClick();
  await view.flush();
  const sent = writes(api);
  assert.deepEqual(
    sent.map((c) => c.op),
    ["create"],
    "새 줄 하나만 보내야 한다",
  );
  // 겹친 0 뒤에 서는 번호를 준다 — 다시 읽어도 맨 뒤다.
  assert.equal(sent[0].input.position, 1);
  assert.deepEqual(view.nameValues(), ["A", "B", "C", "D"]);
});

test("P2 번호 공간이 없는 중간 삽입은 필요한 경계만 고친다", async (t) => {
  const api = three([0, 0, 0]);
  const view = page(t, api.api);
  await view.flush();
  view.button("+ 줄 추가").props.onClick();
  view.render();
  fill(view, 3, "NEW");
  view.render();
  // 맨 뒤의 새 줄을 둘째 자리로 끌어 온다 → A NEW B C
  view.handles()[3].props.onDragStart(dragEvent());
  view.render();
  view.cards()[1].props.onDrop({ ...dragEvent(), preventDefault: () => {} });
  await view.flush();
  assert.deepEqual(view.nameValues(), ["A", "NEW", "B", "C"]);

  view.button("저장").props.onClick();
  await view.flush();
  assert.equal(api.only("create").length, 1);
  assert.equal(api.only("create")[0].input.name, "NEW");
  assert.equal(api.only("remove").length, 0);
  assert.ok(api.only("update").length <= 2, "A 는 그대로 두고 B/C 경계만 고치면 된다");
  assert.equal(api.only("update").filter((c) => c.id === 1).length, 0, "앞의 A 까지 고쳤다");
  assert.deepEqual(view.nameValues(), ["A", "NEW", "B", "C"], "다시 읽어도 그 순서다");
  assert.deepEqual(
    (await api.api.list({ class_id: 3, from: TODAY, to: TODAY })).items.map((r) => r.name),
    ["A", "NEW", "B", "C"],
  );
});

const addNamed = async (view, name) => {
  const index = view.names().length;
  view.button("+ 줄 추가").props.onClick();
  view.render();
  fill(view, index, name);
  await view.flush();
};
const dragRow = async (view, from, to) => {
  view.handles()[from].props.onDragStart(dragEvent());
  view.render();
  view
    .cards()
    [to].props.onDrop({ ...dragEvent(), clientY: from < to ? 80 : 20, preventDefault: () => {} });
  await view.flush();
};
const reloadedNames = async (api) =>
  (await api.api.list({ class_id: 3, from: TODAY, to: TODAY })).items.map((r) => r.name);

test("P2 중간 삽입 A2/NEW/B5/C9 는 새 줄 POST 하나만 보낸다", async (t) => {
  const api = three([2, 5, 9]);
  const view = page(t, api.api);
  await view.flush();
  await addNamed(view, "NEW");
  view.type(view.textareas()[6], "새 계획");
  view.render();
  view.type(view.textareas()[7], "새 실행");
  await view.flush();
  await dragRow(view, 3, 1);
  assert.deepEqual(view.nameValues(), ["A", "NEW", "B", "C"]);
  assert.deepEqual(writes(api), [], "초안을 옮기는 동안 mutation 이 나갔다");

  view.button("저장").props.onClick();
  await view.flush();
  assert.deepEqual(
    writes(api).map((c) => c.op),
    ["create"],
    "POST 외의 mutation 이 나갔다",
  );
  const created = api.only("create")[0];
  assert.equal(created.class_id, 3);
  assert.ok(created.input.position > 2 && created.input.position < 5);
  assert.deepEqual(created.input, {
    date: TODAY,
    position: created.input.position,
    start: null,
    end: null,
    name: "NEW",
    plan: "새 계획",
    execution: "새 실행",
  });
  for (const id of [1, 2, 3])
    assert.equal(api.only("update").filter((c) => c.id === id).length, 0, `${id} 의 불필요 PUT`);
  assert.deepEqual(
    api
      .rows()
      .filter((r) => r.id <= 3)
      .map((r) => r.position),
    [2, 5, 9],
  );
  assert.deepEqual(await reloadedNames(api), ["A", "NEW", "B", "C"]);

  const fresh = page(t, api.api);
  await fresh.flush();
  assert.deepEqual(fresh.nameValues(), ["A", "NEW", "B", "C"], "새 컴포넌트의 GET 순서");
  const before = writes(api).length;
  fresh.button("저장").props.onClick();
  await fresh.flush();
  assert.equal(writes(api).length, before, "방금 저장한 결과를 다시 PUT 했다");
});

for (const placement of ["append", "middle"])
  test(`P2 ${placement} D POST 실패/E 성공 뒤 retry 는 D POST 하나뿐이다`, async (t) => {
    const api = three([2, 5, 9]);
    const create = api.api.create;
    let failD = true;
    api.api.create = async (class_id, input) => {
      if (input.name === "D" && failD) {
        api.calls.push({ op: "create", class_id, input });
        throw new Error("D 만 만들지 못했어요");
      }
      return create(class_id, input);
    };
    const view = page(t, api.api);
    await view.flush();
    await addNamed(view, "D");
    await addNamed(view, "E");
    view.type(view.textareas()[6], "D 계획");
    view.render();
    view.type(view.textareas()[7], "D 실행");
    view.render();
    view.type(view.textareas()[8], "E 계획");
    view.render();
    view.type(view.textareas()[9], "E 실행");
    await view.flush();
    if (placement === "middle") {
      await dragRow(view, 3, 1);
      await dragRow(view, 4, 2);
    }
    const expected = placement === "middle" ? ["A", "D", "E", "B", "C"] : ["A", "B", "C", "D", "E"];
    const beforeText = view.textareas().map((n) => n.props.value);

    view.button("저장").props.onClick();
    await view.flush();
    assert.deepEqual(
      api.only("create").map((c) => c.input.name),
      ["D", "E"],
    );
    assert.equal(api.only("update").length, 0, "첫 저장부터 unchanged 행을 PUT 했다");
    assert.equal(api.only("remove").length, 0);
    assert.deepEqual(view.nameValues(), expected, "실패가 입력을 지웠다");
    assert.deepEqual(
      view.textareas().map((n) => n.props.value),
      beforeText,
    );
    assert.ok(view.errors().some((text) => text.includes("D 만 만들지 못했어요")));
    assert.equal(view.text().includes("저장했어요"), false);
    const successfulE = api.rows().find((r) => r.name === "E");
    assert.ok(successfulE && successfulE.id > 3, "E 의 server ID 가 없다");

    // E 를 되돌리면 성공한 서버 baseline 으로 돌아와야 한다. id 가 없는 새 줄이면 빈 줄이 된다.
    const eIndex = expected.indexOf("E");
    fill(view, eIndex, "E 임시 수정");
    await view.flush();
    view.rowButton(eIndex, "되돌리기").props.onClick();
    await view.flush();
    assert.equal(
      view.nameValues()[eIndex],
      "E",
      "성공 E 의 id/baseline 을 draft 에 reconcile 하지 않았다",
    );
    assert.deepEqual(
      view.textareas().map((n) => n.props.value),
      beforeText,
    );

    const beforeRetry = api.calls.length;
    failD = false;
    view.button("저장").props.onClick();
    await view.flush();
    const retry = api.calls.slice(beforeRetry).filter((c) => c.op !== "list");
    assert.deepEqual(
      retry.map((c) => c.op),
      ["create"],
      "실패 D 외의 요청을 다시 보냈다",
    );
    assert.equal(retry[0].class_id, 3);
    assert.equal(retry[0].input.name, "D");
    assert.equal(retry[0].input.plan, "D 계획");
    assert.equal(retry[0].input.execution, "D 실행");
    assert.equal(api.only("create").filter((c) => c.input.name === "E").length, 1);
    assert.equal(api.only("update").filter((c) => c.id === successfulE.id).length, 0);
    for (const id of [1, 2, 3])
      assert.equal(api.only("update").filter((c) => c.id === id).length, 0);
    assert.equal(api.rows().filter((r) => r.name === "D").length, 1);
    assert.equal(api.rows().filter((r) => r.name === "E").length, 1);
    assert.equal(api.rows().find((r) => r.name === "E").id, successfulE.id);
    assert.deepEqual(await reloadedNames(api), expected);
    assert.deepEqual(view.nameValues(), expected);
  });

test("P2 간격이 있는 기존 C 를 맨 앞으로 끌면 C 만 position PUT 한다", async (t) => {
  const api = three([2, 5, 9]);
  const view = page(t, api.api);
  await view.flush();
  await dragRow(view, 2, 0);
  view.button("저장").props.onClick();
  await view.flush();
  assert.deepEqual(
    writes(api).map((c) => [c.op, c.id]),
    [["update", 3]],
  );
  assert.ok(api.only("update")[0].input.position < 2);
  assert.deepEqual(
    api
      .rows()
      .filter((r) => r.id !== 3)
      .map((r) => r.position),
    [2, 5],
  );
  assert.deepEqual(await reloadedNames(api), ["C", "A", "B"]);
});

test("P2 중간 간격에 두 새 줄을 넣어도 기존 행 PUT 은 없다", async (t) => {
  const api = three([2, 5, 9]);
  const view = page(t, api.api);
  await view.flush();
  await addNamed(view, "D");
  await addNamed(view, "E");
  await dragRow(view, 3, 1);
  await dragRow(view, 4, 2);
  view.button("저장").props.onClick();
  await view.flush();
  assert.deepEqual(
    writes(api).map((c) => [c.op, c.input.name]),
    [
      ["create", "D"],
      ["create", "E"],
    ],
  );
  const positions = api.only("create").map((c) => c.input.position);
  assert.ok(positions.every((position) => position > 2 && position < 5));
  assert.deepEqual(await reloadedNames(api), ["A", "D", "E", "B", "C"]);
});

for (const fixture of [
  { label: "인접 번호", positions: [2, 3, 9], newStart: "" },
  { label: "같은 번호", positions: [5, 5, 5], newStart: "09:30" },
])
  test(`P2 ${fixture.label} 중간 삽입도 start/id 정렬로 표현되면 기존 PUT 은 없다`, async (t) => {
    const api = recorder({
      rows: ["A", "B", "C"].map((name, i) =>
        row({
          id: i + 1,
          name,
          position: fixture.positions[i],
          start: ["09:00:00", "10:00:00", "11:00:00"][i],
          end: null,
        }),
      ),
    });
    const view = page(t, api.api);
    await view.flush();
    await addNamed(view, "NEW");
    if (fixture.newStart) {
      view.type(view.times()[6], fixture.newStart);
      await view.flush();
    }
    await dragRow(view, 3, 1);
    view.button("저장").props.onClick();
    await view.flush();
    assert.deepEqual(
      writes(api).map((c) => c.op),
      ["create"],
    );
    assert.equal(api.only("create")[0].input.start, fixture.newStart || null);
    assert.deepEqual(
      api
        .rows()
        .filter((r) => r.id <= 3)
        .map((r) => r.position),
      fixture.positions,
    );
    assert.deepEqual(await reloadedNames(api), ["A", "NEW", "B", "C"]);
  });

test("P2 초가 있는 서버 행 사이에 분 입력을 삽입해도 기존 PUT 없이 실제 시간 정렬을 지킨다", async (t) => {
  const api = recorder({
    rows: [
      row({ id: 1, name: "A", position: 2, start: "09:00:30", end: "10:00:30" }),
      row({ id: 2, name: "B", position: 3, start: "09:00:40", end: "10:00:40" }),
    ],
  });
  const view = page(t, api.api);
  await view.flush();
  assert.deepEqual(
    view.times().map((node) => node.props.value),
    ["09:00", "10:00", "09:00", "10:00"],
  );
  await addNamed(view, "NEW");
  view.type(view.times()[4], "09:00");
  await view.flush();
  await dragRow(view, 2, 1);
  assert.deepEqual(view.nameValues(), ["A", "NEW", "B"]);

  view.button("저장").props.onClick();
  await view.flush();
  assert.deepEqual(
    writes(api).map((c) => c.op),
    ["create"],
  );
  assert.deepEqual(api.only("create")[0].input, {
    date: TODAY,
    position: 3,
    start: "09:00",
    end: null,
    name: "NEW",
    plan: "",
    execution: "",
  });
  assert.equal(api.rows().find((r) => r.name === "NEW").start, "09:00:00");
  assert.deepEqual(
    api
      .rows()
      .filter((r) => r.id <= 2)
      .map((r) => [r.id, r.position, r.start, r.end]),
    [
      [1, 2, "09:00:30", "10:00:30"],
      [2, 3, "09:00:40", "10:00:40"],
    ],
  );
  assert.deepEqual(await reloadedNames(api), ["A", "NEW", "B"]);
  assert.deepEqual(view.nameValues(), ["A", "NEW", "B"]);
});

test("P2 다른 칸 수정과 position PUT 은 교사가 고치지 않은 서버의 초를 보존한다", async (t) => {
  const api = recorder({
    rows: [
      row({ id: 1, name: "A", position: 2, start: "09:00:30", end: "09:30:45" }),
      row({ id: 2, name: "B", position: 5, start: "10:00:00", end: "11:00:00" }),
      row({ id: 3, name: "C", position: 9, start: "12:10:15", end: "12:50:45" }),
    ],
  });
  const view = page(t, api.api);
  await view.flush();
  view.type(view.textareas()[0], "A 계획 수정");
  await view.flush();
  view.button("저장").props.onClick();
  await view.flush();
  assert.deepEqual(
    writes(api).map((c) => [c.op, c.id]),
    [["update", 1]],
  );
  const edited = api.only("update")[0].input;
  assert.equal(edited.position, 2);
  assert.equal(edited.plan, "A 계획 수정");
  assert.equal(edited.start, "09:00:30");
  assert.equal(edited.end, "09:30:45");
  assert.equal("class_id" in edited, false);

  const beforeDrag = api.calls.length;
  await dragRow(view, 2, 0);
  view.button("저장").props.onClick();
  await view.flush();
  const reordered = api.calls.slice(beforeDrag).filter((c) => c.op !== "list");
  assert.deepEqual(
    reordered.map((c) => [c.op, c.id]),
    [["update", 3]],
  );
  assert.ok(reordered[0].input.position < 2);
  assert.equal(reordered[0].input.start, "12:10:15");
  assert.equal(reordered[0].input.end, "12:50:45");
  assert.equal("class_id" in reordered[0].input, false);
  assert.deepEqual(await reloadedNames(api), ["C", "A", "B"]);

  const beforeNoop = writes(api).length;
  view.button("저장").props.onClick();
  await view.flush();
  assert.equal(writes(api).length, beforeNoop, "보존된 초를 다음 저장에서 다시 고쳤다");
});

// ── 보고 있는 반 · 날짜를 주소에 적어 둔다 (P1-3 scope 동기화) ──────────────

test("주소에 아무것도 없어도 연 반 · 날짜를 주소에 적는다", async (t) => {
  const view = page(t, recorder().api);
  await view.flush();
  assert.equal(view.search(), `?date=${TODAY}&class_id=3`);
});

test("반을 바꾸면 주소의 class_id 도 따라간다", async (t) => {
  const view = page(t, recorder().api, {
    search: "?date=2026-10-06&class_id=3",
    classes: [
      { id: 3, name: "햇살반" },
      { id: 4, name: "별빛반" },
    ],
  });
  await view.flush();
  assert.equal(view.search(), `?date=${TODAY}&class_id=3`);

  view.type(view.classSelect(), "4");
  await view.flush();
  assert.equal(view.search(), `?date=${TODAY}&class_id=4`);
});

test("날짜를 바꾸면 주소의 date 도 따라간다", async (t) => {
  const view = page(t, recorder().api, { search: "?date=2026-10-16&class_id=3" });
  await view.flush();
  assert.equal(view.search(), "?date=2026-10-16&class_id=3");

  view.type(view.dateInput(), "2026-10-17");
  await view.flush();
  assert.equal(view.search(), "?date=2026-10-17&class_id=3");
});

test("주소를 고쳐도 그 때문에 저장이 일어나지는 않는다", async (t) => {
  const api = recorder({ rows: [row({ id: 1, name: "A" })] });
  const view = page(t, api.api, { search: "?date=2026-10-16&class_id=3" });
  await view.flush();
  view.type(view.dateInput(), "2026-10-17");
  await view.flush();
  assert.deepEqual(
    api.calls.filter((c) => c.op !== "list").map((c) => c.op),
    [],
    "주소만 바꿨는데 서버에 썼다",
  );
});

test("바꾼 반 · 날짜로 저장한 뒤 그 주소로 다시 열면 같은 자리다", async (t) => {
  const api = recorder();
  const first = page(t, api.api, {
    search: "?date=2026-10-16&class_id=3",
    classes: [
      { id: 3, name: "햇살반" },
      { id: 4, name: "별빛반" },
    ],
  });
  await first.flush();
  first.type(first.classSelect(), "4");
  await first.flush();
  first.type(first.dateInput(), "2026-10-17");
  await first.flush();
  fill(first, 0, "바깥놀이");
  await first.flush();
  first.button("저장").props.onClick();
  await first.flush();
  assert.deepEqual(
    api.only("create").map((c) => [c.class_id, c.input.date]),
    [[4, "2026-10-17"]],
  );

  // 새로고침 = 그 때 주소로 화면을 다시 세우는 것. 옛 반 · 옛 날짜로 돌아가면 안 된다.
  const reloaded = page(t, api.api, {
    search: first.search(),
    classes: [
      { id: 3, name: "햇살반" },
      { id: 4, name: "별빛반" },
    ],
  });
  await reloaded.flush();
  assert.equal(reloaded.classSelect().props.value, 4);
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

test("dragstart 는 dataTransfer 에 담는다 — 담지 않으면 Firefox 는 끌기를 시작하지 않는다", async (t) => {
  const view = page(
    t,
    recorder({ rows: [row({ id: 1, name: "A" }), row({ id: 2, name: "B" })] }).api,
  );
  await view.flush();
  const event = dragEvent();
  view.handles()[0].props.onDragStart(event);
  assert.equal(event.dataTransfer.data["text/plain"], "0");
});

test("1번 줄을 4번 자리로 끌면 그 순서로 저장되고 다시 읽어도 그대로다", async (t) => {
  const api = recorder({
    rows: [
      row({ id: 1, name: "A", position: 0 }),
      row({ id: 2, name: "B", position: 1 }),
      row({ id: 3, name: "C", position: 2 }),
      row({ id: 4, name: "D", position: 3 }),
    ],
  });
  const view = page(t, api.api);
  await view.flush();
  await dragRow(view, 0, 3);
  assert.deepEqual(view.nameValues(), ["B", "C", "D", "A"]);

  view.button("저장").props.onClick();
  await view.flush();
  assert.equal(api.only("create").length, 0);
  assert.equal(api.only("remove").length, 0);
  assert.deepEqual(await reloadedNames(api), ["B", "C", "D", "A"]);
  assert.deepEqual(view.nameValues(), ["B", "C", "D", "A"]);
});

// ── S-J1 로 들어오는 길 — 기록 모아보기 · 우리 반 ─────────────────────────

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
  { rooms = [ROOM_A, ROOM_B], observations = [], routineRows = [], routineFail = false } = {},
) {
  const calls = [];
  browser({ rooms: [CLASS_A, CLASS_B], primaryClassId: CLASS_A.id });
  t.after(() => delete globalThis.window);
  const app = host();
  const Page = compile("../components/workspace/QuickRecordsPage.tsx", {
    "react/jsx-runtime": runtime,
    react: app.react,
    "next/link": { default: "link" },
    "./WorkspaceUI": {
      WorkspacePage: "page",
      Message: "message",
      useClasses: () => rooms,
      ws: {},
    },
    "@/components/app/icons": { Icon: "icon" },
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
    // 관찰 영역 축은 서버 설정에서 온다. 여기서 보는 것은 길 · 저장이라 기본 축으로 둔다.
    "@/lib/hooks/use-observation-domains": { useObservationDomains: () => OBSERVATION_DOMAINS },
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

  view.type(view.classSelect(), CLASS_B.id);
  await view.flush();
  assert.ok(
    view.links().includes(`/routines?date=${TODAY}&class_id=7`),
    `고른 반을 잃었다: ${view.links().join(" , ")}`,
  );
});

test("기록 모아보기에서 지난 날짜를 고르면 그 날짜로 일과 기록에 간다 — 오늘로 돌아가지 않는다", async (t) => {
  const view = quickRecordsPage(t);
  await view.flush();
  view.type(view.classSelect(), CLASS_A.id);
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
  const view = quickRecordsPage(t, { rooms: [ROOM_A, ROOM_GHOST] });
  await view.flush();
  view.type(view.classSelect(), ROOM_GHOST.id);
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

  view.type(view.classSelect(), CLASS_B.id);
  await view.flush();
  assert.deepEqual(view.calls.slice(-2), [
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
  assert.ok(text.includes("일과 기록을 불러오지 못했어요"), text);
});

/**
 * 관찰 기록 서버 하나. **반 없이 묻는 조회는 바로 실패시킨다** — 홈이 기관 전체를
 * 조회하거나 빈 배열로 떨어지는 회귀를 테스트가 조용히 통과시키지 않게 한다 (FR-405).
 */
function recordsServer({ rows = [] } = {}) {
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
  } = {},
) {
  browser({ rooms, primaryClassId, search });
  t.after(() => delete globalThis.window);
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
    "@/lib/api/records": records.api,
    "@/lib/api/onboarding": onboardingApi,
    "@/lib/workspace/model": { today: () => TODAY },
    // 대표 반 정책도 주소를 만드는 쪽도 진짜다.
    "@/lib/onboarding/settings": classSettings,
    "@/lib/workspace/routines-route": routinesRoute,
    "@/lib/plan-generator/types": { AGE_LABEL: { age3: "만 3세" } },
    "@/lib/greeting": { formatKoreanDate: () => "10월 6일" },
    "@/lib/hooks/use-client-state": { useClientState: (read) => app.state(read) },
    // 관찰 영역 축은 서버 설정에서 온다. 여기서 보는 것은 길 · 저장이라 기본 축으로 둔다.
    "@/lib/hooks/use-observation-domains": { useObservationDomains: () => OBSERVATION_DOMAINS },
    "@/lib/hooks/use-dictation": {
      useDictation: () => ({ supported: false, listening: false, toggle: () => {} }),
    },
  }).default;
  const view = app.mount(Page);
  t.after(app.cleanup);
  const find = (type) => all(view.tree()).filter((node) => node?.type === type);
  const labelled = (node) => String([node.props.children].flat().join(""));
  return {
    flush: view.flush,
    render: view.render,
    currentClass: () => find("p").find((node) => node.props["aria-label"] === "현재 반"),
    search: () => globalThis.window.location.search,
    records,
    /** 서버 반이 뒤늦게 도착한 상황. 다음 flush 에서 홈이 다시 조회해야 한다. */
    arrive: (next) => {
      box.classes = next;
    },
    links: () => hrefsOf(view),
    classSelect: () => find("select")[0],
    factInput: () => find("textarea")[0] ?? find("input").find((n) => n.props?.["aria-label"]),
    button: (label) => find("button").find((n) => labelled(n).includes(label) && !n.props.disabled),
    type: (node, value) => node.props.onChange({ target: { value } }),
    // 「오늘 기록 {N}건」의 N 은 숫자 노드다. 숫자를 같이 모으고 사이를 띄우지 않아야
    // 화면에 실제로 보이는 「오늘 기록 1건」이 된다.
    text: () =>
      all(view.tree())
        .filter((part) => typeof part === "string" || typeof part === "number")
        .join(""),
  };
}

/** 홈에서 한 줄 적고 저장까지. 실제 화면 순서대로 — 적기 → 기록 남기기 → 이대로 남기기. */
async function homeSave(view, fact) {
  view.type(view.factInput(), fact);
  await view.flush();
  view.button("기록 남기기").props.onClick();
  await view.flush();
  view.button("이대로 남기기").props.onClick();
  await view.flush();
}

test("우리 반 첫 화면에 오늘 일과로 가는 길이 있다 — 대표 반과 오늘 날짜를 들고 간다", async (t) => {
  const view = homePage(t);
  await view.flush();
  assert.ok(view.text().includes("오늘 일과 적기"), view.text());
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

test("P0 한 반 계정 — 홈에서 저장하면 오늘 기록 1건이 그 자리에 보인다", async (t) => {
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
  assert.ok(view.text().includes("오늘 기록 1건"), `홈이 0건으로 보인다: ${view.text()}`);
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
  assert.ok(again.text().includes("오늘 기록 1건"), `새로고침 뒤 사라졌다: ${again.text()}`);
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
  assert.ok(view.text().includes("오늘 기록 1건"), view.text());
  assert.deepEqual(
    records.only("add").map((c) => c.classId),
    [ROOM_A.id],
  );

  // 반 고르개는 「기록 남기기」를 눌러야 나오는 확인 단계 안에 있다 — 실제 화면 순서대로 간다.
  view.type(view.factInput(), "다른 반 기록을 적어 본다.");
  await view.flush();
  view.button("기록 남기기").props.onClick();
  await view.flush();
  view.type(view.classSelect(), ROOM_B.id);
  await view.flush();
  view.button("더 쓸래요").props.onClick();
  await view.flush();

  assert.ok(view.text().includes("오늘 기록 0건"), `B 반에 A 반 기록이 보인다: ${view.text()}`);
  assert.equal(
    records.only("list").at(-1).classId,
    ROOM_B.id,
    "반을 바꿨는데 B 반으로 다시 묻지 않았다",
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
  assert.ok(view.text().includes("오늘 기록 0건"), view.text());

  view.arrive([ROOM_A]);
  await view.flush();
  assert.deepEqual(
    records.only("list").map((c) => c.classId),
    [ROOM_A.id],
  );
  assert.ok(view.text().includes("오늘 기록 1건"), `반이 붙었는데 다시 안 읽었다: ${view.text()}`);
});

test("P0 홈이 세는 건수와 서버에 남은 기록이 같다", async (t) => {
  const records = recordsServer();
  const view = homePage(t, { rooms: [CLASS_A], primaryClassId: "", classes: [ROOM_A], records });
  await view.flush();
  for (const fact of ["물감을 섞어 새 색을 만들었다.", "종이비행기를 접어 날렸다."])
    await homeSave(view, fact);

  const onServer = records.rows().filter((r) => r.date === TODAY && r.classId === ROOM_A.id).length;
  assert.equal(onServer, 2);
  assert.ok(view.text().includes(`오늘 기록 ${onServer}건`), `건수가 어긋난다: ${view.text()}`);
});

test("L 홈의 반 이름·저장·조회·일과 링크가 선택한 B 반으로 함께 바뀐다", async (t) => {
  const records = recordsServer();
  const view = homePage(t, {
    rooms: [CLASS_A, CLASS_B],
    classes: [ROOM_A, ROOM_B],
    records,
  });
  await view.flush();
  await homeSave(view, "A에서만 보이는 사실");
  view.type(view.factInput(), "B에서만 보이는 사실");
  await view.flush();
  view.button("기록 남기기").props.onClick();
  await view.flush();
  view.type(view.classSelect(), ROOM_B.id);
  await view.flush();
  assert.ok(view.currentClass().props.children.includes(ROOM_B.className));
  assert.ok(view.links().includes(`/routines?date=${TODAY}&class_id=7`));
  assert.equal(view.text().includes("A에서만 보이는 사실"), false);
  view.button("이대로 남기기").props.onClick();
  await view.flush();
  assert.equal(records.only("add").at(-1).classId, ROOM_B.id);
  assert.equal(records.only("list").at(-1).classId, ROOM_B.id);
  assert.ok(view.text().includes("오늘 기록 1건"));
  assert.ok(view.text().includes("B에서만 보이는 사실"));
  assert.equal(new URLSearchParams(view.search()).get("class_id"), "7");
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
  assert.ok(view.currentClass().props.children.includes(ROOM_B.className));
  assert.equal(records.only("list").at(-1).classId, ROOM_B.id);
  assert.ok(view.links().includes(`/routines?date=${TODAY}&class_id=7`));
});

test("L A 반의 느린 응답이 B 반 화면과 건수를 덮지 않는다", async (t) => {
  let release;
  const records = recordsServer();
  const list = records.api.listRecords;
  records.api.listRecords = (id) =>
    id === ROOM_A.id
      ? new Promise((resolve) => {
          release = resolve;
        })
      : list(id);
  const view = homePage(t, { rooms: [CLASS_A, CLASS_B], classes: [ROOM_A, ROOM_B], records });
  await view.flush();
  view.type(view.factInput(), "B에 적을 사실");
  await view.flush();
  view.button("기록 남기기").props.onClick();
  await view.flush();
  view.type(view.classSelect(), ROOM_B.id);
  await view.flush();
  release([{ classId: ROOM_A.id, date: TODAY, fact: "늦게 도착한 A 사실" }]);
  await view.flush();
  assert.ok(view.currentClass().props.children.includes(ROOM_B.className));
  assert.ok(view.text().includes("오늘 기록 0건"));
  assert.equal(view.text().includes("늦게 도착한 A 사실"), false);
});

test("L A 저장 중 B로 옮겨도 저장 완료 콜백이 B 목록을 비우지 않는다", async (t) => {
  let release;
  const records = recordsServer({
    rows: [
      {
        id: "obs-b",
        classId: ROOM_B.id,
        date: TODAY,
        childId: ROOM_B.children[0].id,
        fact: "B의 기존 사실",
        domain: "의사소통",
        createdAt: "2026-10-06T00:00:00Z",
      },
    ],
  });
  const add = records.api.addRecord;
  records.api.addRecord = (record) =>
    new Promise((resolve) => {
      release = async () => resolve(await add(record));
    });
  const view = homePage(t, { rooms: [CLASS_A, CLASS_B], classes: [ROOM_A, ROOM_B], records });
  await view.flush();
  view.type(view.factInput(), "A에서 저장을 기다리는 사실");
  await view.flush();
  view.button("기록 남기기").props.onClick();
  await view.flush();
  const pending = view.button("이대로 남기기").props.onClick();
  await view.flush();
  view.type(view.classSelect(), ROOM_B.id);
  await view.flush();
  assert.ok(view.text().includes("B의 기존 사실"));
  release();
  await pending;
  await view.flush();
  assert.ok(view.currentClass().props.children.includes(ROOM_B.className));
  assert.ok(view.text().includes("오늘 기록 1건"));
  assert.ok(view.text().includes("B의 기존 사실"));
  assert.equal(records.only("list").at(-1).classId, ROOM_B.id);
});

test("후속 #2 기존 09:16:25는 다른 칸 수정·저장으로 반올림되지 않는다", async (t) => {
  const api = recorder({ rows: [row({ id: 1, start: "09:16:25", end: "10:21:35" })] });
  const view = page(t, api.api);
  await view.flush();
  assert.deepEqual(
    view.times().map((n) => n.props.value),
    ["09:16", "10:21"],
  );
  view.type(view.textareas()[0], "계획만 수정한다");
  view.render();
  view.button("저장").props.onClick();
  await view.flush();
  assert.equal(api.only("update")[0].input.start, "09:16:25");
  assert.equal(api.only("update")[0].input.end, "10:21:35");
});

test("후속 #5 명시적 시간 정렬과 수동 이동은 저장 전 요청 없이 입력·ID를 보존한다", async (t) => {
  const api = recorder({
    rows: [
      row({ id: 1, name: "늦음", start: "11:00:00", end: "12:00:00", position: 0 }),
      row({ id: 2, name: "빠름", start: "09:00:00", end: "10:00:00", position: 1 }),
      row({ id: 3, name: "동률", start: "09:00:00", end: "10:00:00", position: 2 }),
      row({ id: 4, name: "미입력", start: null, end: null, position: 3 }),
    ],
  });
  const view = page(t, api.api);
  await view.flush();
  assert.deepEqual(view.nameValues(), ["늦음", "빠름", "동률", "미입력"]);
  view.type(view.textareas()[1], "저장 전 실행 수정");
  view.render();
  view.button("시간순 정렬").props.onClick();
  await view.flush();
  assert.deepEqual(view.nameValues(), ["빠름", "동률", "늦음", "미입력"]);
  assert.equal(writes(api).length, 0);
  view.button("저장").props.onClick();
  await view.flush();
  assert.deepEqual(await reloadedNames(api), ["빠름", "동률", "늦음", "미입력"]);
  assert.equal(api.rows().find((r) => r.id === 1).execution, "저장 전 실행 수정");
  await dragRow(view, 0, 2);
  view.button("저장").props.onClick();
  await view.flush();
  assert.deepEqual(await reloadedNames(api), ["동률", "늦음", "빠름", "미입력"]);
});

test("후속 #5 같은 position에서 시각을 고쳐도 현재 카드 순서를 저장한다", async (t) => {
  const api = recorder({
    rows: [
      row({ id: 1, name: "A", position: 0, start: "09:00:00", end: null }),
      row({ id: 2, name: "B", position: 0, start: "10:00:00", end: null }),
    ],
  });
  const view = page(t, api.api);
  await view.flush();
  view.type(view.times()[0], "11:00");
  await view.flush();
  view.button("저장").props.onClick();
  await view.flush();
  assert.deepEqual(await reloadedNames(api), ["A", "B"]);
});

test("후속 #1 drag image는 핸들이 아닌 카드 전체를 사용하고 삽입 위치를 표시한다", async (t) => {
  const api = recorder({ rows: [row({ id: 1 }), row({ id: 2 })] });
  const view = page(t, api.api);
  await view.flush();
  const card = { getBoundingClientRect: () => ({ left: 5, top: 10 }) };
  let image;
  const event = dragEvent();
  event.currentTarget.closest = () => card;
  event.dataTransfer.setDragImage = (element) => {
    image = element;
  };
  view.handles()[0].props.onDragStart(event);
  view.render();
  assert.equal(image, card);
  assert.equal(view.cards()[0].props["data-dragging"], true);
  view.cards()[1].props.onDragOver({ ...dragEvent(), clientY: 80, preventDefault() {} });
  view.render();
  assert.equal(view.cards()[1].props["data-insertion"], "after");
  assert.equal(writes(api).length, 0);
});

test("후속 #5 명시적 정렬도 보존 중인 원본의 초를 비교한다", async (t) => {
  const api = recorder({
    rows: [
      row({ id: 1, name: "늦은 초", position: 0, start: "09:16:40", end: "10:00:00" }),
      row({ id: 2, name: "이른 초", position: 1, start: "09:16:25", end: "10:30:00" }),
    ],
  });
  const view = page(t, api.api);
  await view.flush();
  view.button("시간순 정렬").props.onClick();
  await view.flush();
  assert.deepEqual(view.nameValues(), ["이른 초", "늦은 초"]);
  view.button("저장").props.onClick();
  await view.flush();
  assert.deepEqual(await reloadedNames(api), ["이른 초", "늦은 초"]);
  assert.equal(api.rows().find((r) => r.id === 1).start, "09:16:40");
});

test("기록 모아보기 — 활동실행이 빈 일과는 계획을 실행처럼 띄우지 않는다", async (t) => {
  const view = quickRecordsPage(t, {
    routineRows: [row({ id: 42, class_id: 3, date: TODAY, plan: "자동차 굴리기", execution: "" })],
  });
  await view.flush();
  const text = view.text();
  assert.equal(text.includes("자동차 굴리기"), false, text);
  assert.ok(text.includes("활동실행을 아직 적지 않았어요."), text);
});
