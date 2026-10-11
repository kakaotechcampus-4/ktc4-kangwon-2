/** /compare 선택·재시도·실제 TSX를 실행한다. API 응답 시점은 테스트가 지정한다. */
import { test } from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { readFileSync } from "node:fs";

const { createCompareSelection } = await import("../components/workspace/compare-selection.ts");
const model = await import("../lib/workspace/model.ts");
const tick = () => new Promise((resolve) => setTimeout(resolve, 0));
function deferred() {
  let resolve, reject;
  const promise = new Promise((yes, no) => {
    resolve = yes;
    reject = no;
  });
  return { promise, resolve, reject };
}
const summary = (id, over = {}) => ({
  id: `document:${id}`,
  serverId: id,
  kind: "assessment",
  title: `서버 문서 ${id}`,
  classId: "server-class:31",
  className: "서버 햇살반",
  childId: "server-child:8",
  childName: "서버 아동",
  start: "2026-09-01",
  end: "2026-09-30",
  status: "confirmed",
  origin: "teacher",
  stale: false,
  sourcesCount: 1,
  createdAt: "2026-09-30T10:00:00Z",
  updatedAt: "2026-09-30T10:00:00Z",
  ...over,
});
const detail = (id, over = {}) => ({
  ...summary(id),
  sections: [
    { heading: "사실", body: `문서 ${id} 사실 원문\n다음 줄도 그대로`, sourceIds: [] },
    { heading: "해석", body: `문서 ${id} 해석 원문`, sourceIds: [] },
    { heading: "지원", body: `문서 ${id} 지원 원문`, sourceIds: [] },
  ],
  sources: [],
  reviewNote: "",
  ...over,
});
const relation = (items = [], expectedKinds = ["observation", "dailyLog"]) => ({
  items,
  expectedKinds,
});
const gateway = (over = {}) => ({
  list: async () => [summary(1), summary(2)],
  get: async (id) => detail(Number(id.slice("document:".length))),
  related: async () => relation([summary(9, { kind: "dailyLog" }), summary(7)]),
  ...over,
});

test("확정 목록을 요청하며 loading 뒤 빈 성공은 error와 다르다", async () => {
  const response = deferred();
  const calls = [];
  const selection = createCompareSelection(
    gateway({ list: (query) => (calls.push(query), response.promise) }),
  );
  assert.equal(selection.get().list.status, "loading");
  const pending = selection.loadList();
  assert.deepEqual(calls, [{ status: "CONFIRMED" }]);
  response.resolve([]);
  await pending;
  assert.deepEqual(selection.get().list, { status: "ready", data: [], error: "" });
});

test("관련 문서 정렬·범위·종류는 서버가 준 결과 그대로 유지한다", async () => {
  // 날짜·반·아이·종류가 예상 밖이어도 FE에서 서버의 결정을 다시 계산하지 않는다.
  const items = [
    summary(9, { classId: "server-class:99", childId: "", start: "2026-10-01" }),
    summary(7, { kind: "weeklyLog", start: "2026-09-01", status: "draft" }),
    summary(8, { kind: "dailyLog", stale: true, start: "2026-09-30" }),
  ];
  const selection = createCompareSelection(gateway({ related: async () => relation(items) }));
  await selection.loadList();
  await selection.selectBase("document:1");
  assert.deepEqual(selection.get().related.data.items, items);
  assert.deepEqual(selection.get().related.data.expectedKinds, ["observation", "dailyLog"]);
  await selection.selectRelated("document:7");
  assert.equal(selection.get().comparison.data.id, "document:7");
});

test("기준 상세와 관련 목록은 독립적이며 실패해도 기준 선택·성공한 상세를 보존한다", async () => {
  const related = deferred();
  const selection = createCompareSelection(gateway({ related: () => related.promise }));
  await selection.loadList();
  const pending = selection.selectBase("document:1");
  await tick();
  assert.equal(selection.get().base.status, "ready");
  assert.equal(selection.get().base.data.id, "document:1");
  assert.equal(selection.get().related.status, "loading");
  related.reject(new Error("관련 문서 조회 실패"));
  await pending;
  assert.equal(selection.get().baseId, "document:1");
  assert.equal(selection.get().base.data.id, "document:1");
  assert.equal(selection.get().related.error, "관련 문서 조회 실패");
  assert.equal(selection.get().list.data.length, 2);
});

test("기준 상세가 실패해도 성공한 관련 목록과 선택은 남는다", async () => {
  const selection = createCompareSelection(
    gateway({
      get: async () => {
        throw new Error("상세 조회 실패");
      },
    }),
  );
  await selection.loadList();
  await selection.selectBase("document:1");
  assert.equal(selection.get().base.status, "error");
  assert.equal(selection.get().baseId, "document:1");
  assert.equal(selection.get().related.status, "ready");
  assert.deepEqual(
    selection.get().related.data.items.map((item) => item.id),
    ["document:9", "document:7"],
  );
});

for (const failOld of [false, true]) {
  test(`A→B→A 선택 뒤 오래된 A의 ${failOld ? "실패" : "성공"} 응답이 새 A를 덮지 않는다`, async () => {
    const baseA = deferred();
    const relatedA = deferred();
    let gets = 0,
      relatedGets = 0;
    const selection = createCompareSelection(
      gateway({
        get: (id) =>
          id === "document:1" && ++gets === 1
            ? baseA.promise
            : Promise.resolve(detail(id === "document:1" ? 1 : 2, { title: "새 상세" })),
        related: (id) =>
          id === "document:1" && ++relatedGets === 1
            ? relatedA.promise
            : Promise.resolve(relation([summary(7)])),
      }),
    );
    await selection.loadList();
    const old = selection.selectBase("document:1");
    await selection.selectBase("document:2");
    await selection.selectBase("document:1");
    const current = selection.get();
    if (failOld) {
      baseA.reject(new Error("이전 A 오류"));
      relatedA.reject(new Error("이전 관련 오류"));
    } else {
      baseA.resolve(detail(1, { title: "오래된 상세" }));
      relatedA.resolve(relation([summary(99)]));
    }
    await old;
    assert.deepEqual(selection.get(), current);
    assert.equal(selection.get().base.data.title, "새 상세");
    assert.equal(selection.get().related.data.items[0].id, "document:7");
  });
}

test("기준을 바꾸면 이전 관련 선택과 원문은 즉시 사라진다", async () => {
  const nextBase = deferred();
  const nextRelated = deferred();
  const selection = createCompareSelection(
    gateway({
      get: (id) =>
        id === "document:2" ? nextBase.promise : Promise.resolve(detail(Number(id.slice(9)))),
      related: (id) =>
        id === "document:2" ? nextRelated.promise : Promise.resolve(relation([summary(9)])),
    }),
  );
  await selection.loadList();
  await selection.selectBase("document:1");
  await selection.selectRelated("document:9");
  const pending = selection.selectBase("document:2");
  assert.equal(selection.get().baseId, "document:2");
  assert.equal(selection.get().base.data, null);
  assert.equal(selection.get().related.data, null);
  assert.equal(selection.get().relatedId, "");
  assert.equal(selection.get().comparison.data, null);
  nextBase.resolve(detail(2));
  nextRelated.resolve(relation());
  await pending;
});

for (const failOld of [false, true]) {
  test(`관련 문서 X→Y 선택 후 오래된 X의 ${failOld ? "실패" : "성공"} 응답을 무시한다`, async () => {
    const oldResponse = deferred();
    const selection = createCompareSelection(
      gateway({
        get: (id) =>
          id === "document:9" ? oldResponse.promise : Promise.resolve(detail(Number(id.slice(9)))),
      }),
    );
    await selection.loadList();
    await selection.selectBase("document:1");
    const old = selection.selectRelated("document:9");
    await selection.selectRelated("document:7");
    const current = selection.get();
    if (failOld) oldResponse.reject(new Error("이전 관련 상세 오류"));
    else oldResponse.resolve(detail(9));
    await old;
    assert.deepEqual(selection.get(), current);
    assert.equal(selection.get().comparison.data.id, "document:7");
  });
}

test("후보에 없는 화면 id는 기준/관련 상세 요청을 보내지 않는다", async () => {
  const calls = [];
  const selection = createCompareSelection(
    gateway({
      get: async (id) => {
        calls.push(id);
        return detail(Number(id.slice(9)));
      },
    }),
  );
  await selection.loadList();
  await selection.selectBase("local-document");
  await selection.selectBase("document:1000");
  assert.deepEqual(calls, []);
  await selection.selectBase("document:1");
  await selection.selectRelated("document:2");
  await selection.selectRelated("local-document");
  assert.deepEqual(calls, ["document:1"]);
  assert.equal(selection.get().relatedId, "");
});

test("재조회 실패는 기존 목록·선택·원문을 보존하고 성공한 재시도만 갱신한다", async () => {
  let fail = false;
  let version = "처음";
  const selection = createCompareSelection(
    gateway({
      list: async () => {
        if (fail) throw new Error("목록 실패");
        return [summary(1)];
      },
      get: async (id) => {
        if (fail) throw new Error("원문 실패");
        return detail(Number(id.slice(9)), { title: version });
      },
      related: async () => {
        if (fail) throw new Error("관련 실패");
        return relation([summary(9)]);
      },
    }),
  );
  await selection.loadList();
  await selection.selectBase("document:1");
  await selection.selectRelated("document:9");
  fail = true;
  await Promise.all([
    selection.loadList(),
    selection.reloadBase(),
    selection.reloadRelated(),
    selection.reloadComparison(),
  ]);
  const state = selection.get();
  assert.equal(state.list.status, "error");
  assert.equal(state.list.data[0].id, "document:1");
  assert.equal(state.baseId, "document:1");
  assert.equal(state.relatedId, "document:9");
  assert.equal(state.base.data.title, "처음");
  assert.equal(state.comparison.data.title, "처음");
  assert.equal(state.related.data.items[0].id, "document:9");
  fail = false;
  version = "최신";
  await Promise.all([
    selection.loadList(),
    selection.reloadBase(),
    selection.reloadRelated(),
    selection.reloadComparison(),
  ]);
  assert.equal(selection.get().base.data.title, "최신");
  assert.equal(selection.get().comparison.data.title, "최신");
  assert.equal(selection.get().baseId, "document:1");
  assert.equal(selection.get().relatedId, "document:9");
});

test("관련 재조회가 선택 후보를 없애면 이전 상세 요청도 무효가 된다", async () => {
  const oldDetail = deferred();
  let refreshed = false;
  const selection = createCompareSelection(
    gateway({
      get: (id) => (id === "document:9" ? oldDetail.promise : Promise.resolve(detail(1))),
      related: async () => relation(refreshed ? [] : [summary(9)]),
    }),
  );
  await selection.loadList();
  await selection.selectBase("document:1");
  const old = selection.selectRelated("document:9");
  refreshed = true;
  await selection.reloadRelated();
  oldDetail.resolve(detail(9));
  await old;
  assert.equal(selection.get().relatedId, "");
  assert.equal(selection.get().comparison.data, null);
  assert.equal(selection.get().related.status, "ready");
});

test("cleanup 뒤 모든 진행 중인 응답은 화면을 갱신하거나 오류를 추가하지 않는다", async () => {
  const base = deferred(),
    related = deferred(),
    list = deferred();
  let initial = true;
  const selection = createCompareSelection(
    gateway({
      list: () => (initial ? Promise.resolve([summary(1)]) : list.promise),
      get: () => base.promise,
      related: () => related.promise,
    }),
  );
  await selection.loadList();
  initial = false;
  const listing = selection.loadList();
  const selected = selection.selectBase("document:1");
  selection.dispose();
  const before = selection.get();
  base.resolve(detail(1));
  related.reject(new Error("언마운트 후 오류"));
  list.resolve([summary(2)]);
  await Promise.all([listing, selected]);
  assert.deepEqual(selection.get(), before);
});

// 기존 documents-server.test.mjs와 같은 Babel 경로를 사용한다. 실제 TSX 이벤트,
// effect commit/cleanup과 외부 store 구독을 실행하며 브라우저 E2E는 아니다.
const require = createRequire(import.meta.url);
function pageHarness(api) {
  const source = readFileSync(
    new URL("../components/workspace/ComparePage.tsx", import.meta.url),
    "utf8",
  );
  const code = require("next/dist/compiled/babel/core").transformSync(source, {
    filename: "ComparePage.tsx",
    babelrc: false,
    configFile: false,
    presets: [
      [require("next/dist/compiled/babel/preset-env"), { targets: { node: "current" } }],
      [require("next/dist/compiled/babel/preset-react"), { runtime: "automatic" }],
      require("next/dist/compiled/babel/preset-typescript"),
    ],
  }).code;
  const slots = [],
    effects = [];
  let cursor = 0,
    dirty = false,
    live = true,
    tree;
  const changed = (before, next) =>
    !before ||
    !next ||
    before.length !== next.length ||
    next.some((value, i) => !Object.is(value, before[i]));
  const useState = (initial) => {
    const index = cursor++;
    if (!(index in slots))
      slots[index] = { value: typeof initial === "function" ? initial() : initial };
    const slot = slots[index];
    slot.set ??= (value) => {
      const next = typeof value === "function" ? value(slot.value) : value;
      if (!Object.is(next, slot.value)) {
        slot.value = next;
        dirty = true;
      }
    };
    return [slot.value, slot.set];
  };
  const useEffect = (run, deps) => {
    const index = cursor++;
    const slot = (slots[index] ??= {});
    if (changed(slot.deps, deps)) {
      slot.deps = deps;
      effects.push(() => {
        slot.cleanup?.();
        slot.cleanup = run();
      });
    }
  };
  const useSyncExternalStore = (subscribe, snapshot) => {
    useEffect(
      () =>
        subscribe(() => {
          dirty = true;
        }),
      [subscribe],
    );
    return snapshot();
  };
  const jsx = (type, props, key) =>
    typeof type === "function" ? type(props) : { type, props, key };
  const modules = {
    react: {
      useState,
      useEffect,
      useSyncExternalStore,
      useRef: (initial) => useState(() => ({ current: initial }))[0],
    },
    "react/jsx-runtime": { jsx, jsxs: jsx, Fragment: "fragment" },
    "next/link": (props) => jsx("a", props),
    "@/lib/workspace/model": model,
    "@/lib/api/documents": {
      listDocuments: api.list,
      getDocument: api.get,
      getRelatedDocuments: api.related,
    },
    "./compare-selection": { createCompareSelection },
    "./WorkspaceUI": {
      ws: {},
      WorkspacePage: (props) => jsx("main", props),
      Empty: ({ title, children }) => jsx("empty", { children: [title, children] }),
      Message: ({ children, error }) =>
        children ? jsx("message", { children, role: error ? "alert" : "status" }) : null,
    },
  };
  const compiledModule = { exports: {} };
  new Function("require", "module", "exports", code)(
    (name) => {
      assert.ok(name in modules, `unhandled ComparePage import: ${name}`);
      return modules[name];
    },
    compiledModule,
    compiledModule.exports,
  );
  const Page = compiledModule.exports.default;
  function render() {
    if (!live) return;
    let count = 0;
    do {
      dirty = false;
      cursor = 0;
      tree = Page();
      while (effects.length) effects.shift()();
      assert.ok(++count < 30, "TSX render should settle");
    } while (dirty);
  }
  const all = (node) =>
    Array.isArray(node)
      ? node.flatMap(all)
      : !node || typeof node !== "object"
        ? []
        : [node, ...all(node.props?.children)];
  const content = (node) =>
    Array.isArray(node)
      ? node.map(content).join("")
      : node && typeof node === "object"
        ? content(node.props?.children)
        : typeof node === "string" || typeof node === "number"
          ? String(node)
          : "";
  render();
  return {
    render,
    text: () => content(tree),
    select(label) {
      const direct = all(tree).find(
        (node) => node.type === "select" && node.props["aria-label"] === label,
      );
      const parent = all(tree).find(
        (node) => node.type === "label" && content(node).includes(label),
      );
      const node = direct ?? all(parent).find((item) => item.type === "select");
      assert.ok(node, `missing select: ${label}`);
      return node;
    },
    buttons: () => all(tree).filter((node) => node.type === "button"),
    button(label, index = 0) {
      const node = all(tree).filter((item) => item.type === "button" && content(item) === label)[
        index
      ];
      assert.ok(node, `missing button: ${label}`);
      return node;
    },
    options(label) {
      return all(this.select(label))
        .filter((item) => item.type === "option")
        .map((item) => item.props.value);
    },
    async settle() {
      await tick();
      render();
    },
    unmount() {
      live = false;
      for (const slot of slots) slot.cleanup?.();
    },
  };
}

test("실제 ComparePage는 목록 loading과 빈 성공을 표시한다", async () => {
  const list = deferred();
  const page = pageHarness(gateway({ list: () => list.promise }));
  assert.match(page.text(), /불러|조회|확인/);
  assert.equal(page.text().includes("비교할 확정 문서가 없어요."), false);
  list.resolve([]);
  await page.settle();
  assert.match(page.text(), /비교할 확정 문서가 없어요\./);
  page.unmount();
});

test("실제 ComparePage의 두 선택은 서버 상세 원문·메타데이터·없는 종류를 표시한다", async () => {
  const calls = [];
  const api = gateway({
    list: async (query) => {
      calls.push(["list", query]);
      return [summary(1)];
    },
    get: async (id) => {
      calls.push(["get", id]);
      return detail(Number(id.slice(9)));
    },
    related: async (id) => {
      calls.push(["related", id]);
      return relation([summary(9, { kind: "dailyLog" })]);
    },
  });
  const page = pageHarness(api);
  await page.settle();
  page.select("기준 확정 문서").props.onChange({ target: { value: "document:1" } });
  await page.settle();
  assert.equal(page.select("기준 확정 문서").props.value, "document:1");
  assert.match(page.text(), /관찰일지/);
  assert.match(page.text(), /아직 없음/);
  assert.match(page.text(), /서버 햇살반/);
  assert.match(page.text(), /서버 아동/);
  assert.match(page.text(), /2026-09-01/);
  assert.ok(page.text().includes("문서 1 사실 원문\n다음 줄도 그대로"));
  page.select("관련 확정 문서").props.onChange({ target: { value: "document:9" } });
  await page.settle();
  for (const heading of ["사실", "해석", "지원"]) {
    assert.ok(page.text().includes(`문서 1 ${heading} 원문`));
    assert.ok(page.text().includes(`문서 9 ${heading} 원문`));
  }
  assert.deepEqual(calls, [
    ["list", { status: "CONFIRMED" }],
    ["get", "document:1"],
    ["related", "document:1"],
    ["get", "document:9"],
  ]);
  assert.ok(page.buttons().every((button) => !/AI|판정|확정/.test(String(button.props.children))));
  page.unmount();
});

test("실제 ComparePage에서 related가 비어도 기준 원문과 아직 없음 안내는 유지된다", async () => {
  const page = pageHarness(gateway({ related: async () => relation() }));
  await page.settle();
  page.select("기준 확정 문서").props.onChange({ target: { value: "document:1" } });
  await page.settle();
  assert.match(page.text(), /아직 관련 문서가 없어요\./);
  assert.match(page.text(), /아직 없음/);
  assert.ok(page.text().includes("문서 1 사실 원문"));
  assert.equal(page.select("기준 확정 문서").props.value, "document:1");
  page.unmount();
});

for (const [status, message] of [
  [401, "다시 로그인해주세요."],
  [500, "서버 조회를 처리하지 못했어요."],
]) {
  test(`실제 ComparePage는 ${status} 목록 실패와 재시도를 표시한다`, async () => {
    let fail = true;
    const page = pageHarness(
      gateway({
        list: async () => {
          if (fail) throw Object.assign(new Error(message), { status });
          return [summary(1)];
        },
      }),
    );
    await page.settle();
    assert.ok(page.text().includes(message));
    assert.equal(page.text().includes("비교할 확정 문서가 없어요."), false);
    fail = false;
    page.button("확정 문서 다시 불러오기").props.onClick();
    await page.settle();
    assert.deepEqual(page.options("기준 확정 문서"), ["", "document:1"]);
    assert.equal(page.text().includes(message), false);
    page.unmount();
  });
}

test("실제 ComparePage의 related 실패와 재시도는 기준 선택·원문을 보존한다", async () => {
  let fail = true;
  const page = pageHarness(
    gateway({
      related: async () => {
        if (fail) throw new Error("관련 목록을 불러오지 못했어요.");
        return relation([summary(9), summary(7)]);
      },
    }),
  );
  await page.settle();
  page.select("기준 확정 문서").props.onChange({ target: { value: "document:1" } });
  await page.settle();
  assert.equal(page.select("기준 확정 문서").props.value, "document:1");
  assert.ok(page.text().includes("문서 1 사실 원문"));
  assert.ok(page.text().includes("관련 목록을 불러오지 못했어요."));
  assert.equal(page.text().includes("아직 관련 문서가 없어요."), false);
  fail = false;
  page.button("관련 목록 다시 불러오기").props.onClick();
  await page.settle();
  assert.equal(page.select("기준 확정 문서").props.value, "document:1");
  assert.deepEqual(page.options("관련 확정 문서"), ["", "document:9", "document:7"]);
  page.unmount();
});

test("실제 ComparePage의 관련 상세 실패 뒤 선택을 유지한 채 같은 문서를 재조회한다", async () => {
  let fail = true;
  const seen = [];
  const page = pageHarness(
    gateway({
      get: async (id) => {
        seen.push(id);
        if (id === "document:9" && fail) throw new Error("관련 원문을 불러오지 못했어요.");
        return detail(Number(id.slice(9)));
      },
    }),
  );
  await page.settle();
  page.select("기준 확정 문서").props.onChange({ target: { value: "document:1" } });
  await page.settle();
  page.select("관련 확정 문서").props.onChange({ target: { value: "document:9" } });
  await page.settle();
  assert.equal(page.select("기준 확정 문서").props.value, "document:1");
  assert.equal(page.select("관련 확정 문서").props.value, "document:9");
  assert.ok(page.text().includes("문서 1 사실 원문"));
  assert.ok(page.text().includes("관련 원문을 불러오지 못했어요."));
  fail = false;
  page.button("관련 문서 다시 불러오기").props.onClick();
  await page.settle();
  assert.ok(page.text().includes("문서 9 사실 원문"));
  assert.deepEqual(seen, ["document:1", "document:9", "document:9"]);
  page.unmount();
});

test("실제 ComparePage는 기준을 이동한 뒤 늦은 상세 성공·related 실패를 무시한다", async () => {
  const oldDetail = deferred(),
    oldRelated = deferred();
  const page = pageHarness(
    gateway({
      get: (id) => (id === "document:1" ? oldDetail.promise : Promise.resolve(detail(2))),
      related: (id) =>
        id === "document:1" ? oldRelated.promise : Promise.resolve(relation([summary(7)])),
    }),
  );
  await page.settle();
  page.select("기준 확정 문서").props.onChange({ target: { value: "document:1" } });
  page.render();
  assert.match(page.text(), /문서 상세를 불러오는 중/);
  assert.match(page.text(), /관련 문서를 찾는 중/);
  page.select("기준 확정 문서").props.onChange({ target: { value: "document:2" } });
  await page.settle();
  oldDetail.resolve(detail(1, { title: "오래된 A 상세" }));
  oldRelated.reject(new Error("오래된 A related 오류"));
  await page.settle();
  assert.equal(page.select("기준 확정 문서").props.value, "document:2");
  assert.ok(page.text().includes("문서 2 사실 원문"));
  assert.equal(page.text().includes("오래된 A 상세"), false);
  assert.equal(page.text().includes("오래된 A related 오류"), false);
  assert.deepEqual(page.options("관련 확정 문서"), ["", "document:7"]);
  page.unmount();
});
