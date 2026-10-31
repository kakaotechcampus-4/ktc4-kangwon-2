// 놀이 월간 「들어가는 문」: 목록 · 링크 · 만들기 · 실패 문구, 놀이형 판별.
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
const { renderToStaticMarkup } = require("react-dom/server");
const React = require("react");
const Message = ({ children }) => (children ? React.createElement("p", null, children) : null);
const { isPlayAnnual } = load("../lib/monthly/play-entry.ts", {});
const { PlayMonthlyEntryView } = load("../components/workspace/PlayMonthlyEntry.tsx", {
  react: require("react"),
  "next/link": {
    __esModule: true,
    default: ({ href, children }) => require("react").createElement("a", { href }, children),
  },
  "next/navigation": { useRouter: () => ({}) },
  "@/lib/api/client": { ApiError: class {} },
  "@/lib/api/playMonthly": {},
  "./WorkspaceUI": {
    ws: new Proxy({}, { get: (_, k) => k }),
    Message,
    Empty: ({ title }) => require("react").createElement("section", null, title),
  },
});

const item = (o) => ({
  id: 7,
  month: 11,
  status: "DRAFT",
  created_at: "2026-10-28T08:03:46.913156Z",
  ...o,
});
const html = (p) =>
  renderToStaticMarkup(
    PlayMonthlyEntryView({ items: [], month: 12, busy: false, problem: "", onCreate() {}, ...p }),
  );

test("놀이형 판별: 놀이형만 참, 목록 실패(null) · 월별 주제형 · 빈 목록은 기존 화면", () => {
  assert.equal(isPlayAnnual({ items: [{ format: "PLAY_PROJECT" }] }), true);
  assert.equal(isPlayAnnual({ items: [{ format: "MONTHLY_THEME" }] }), false);
  assert.equal(isPlayAnnual({ items: [] }), false);
  assert.equal(isPlayAnnual(null), false);
});

test("목록: 달 · 상태 · 현지 시각 · 열기 링크, 만들기는 기존 월간의 것이 아님", () => {
  const out = html({ items: [item({}), item({ id: 8, month: 10, status: "CONFIRMED" })] });
  assert.match(out, /href="\/plans\/monthly\/play\/7"/);
  assert.match(out, /href="\/plans\/monthly\/play\/8"/);
  assert.match(out, /초안/);
  assert.match(out, /확정됨/);
  assert.match(out, /12월 놀이 중심 계획안 만들기/);
  assert.doesNotMatch(out, /12월 계획안 만들기/);
  const kst = new Date("2026-10-28T08:03:46.913156Z").toLocaleString("ko-KR", {
    dateStyle: "medium",
    timeStyle: "short",
  });
  assert.ok(out.includes(kst));
});

test("빈 목록 안내 · 불러오는 중", () => {
  assert.match(html({}), /아직 없어요/);
  assert.match(html({ items: null }), /불러오는 중/);
});

test("503 문구는 서버 그대로, 만드는 중에는 버튼이 막힘", () => {
  const msg = "지금은 이 반의 놀이 중심 월간계획안을 만들 수 없습니다. 관리자에게 문의해 주세요.";
  assert.ok(html({ problem: msg }).includes(msg));
  assert.match(html({ busy: true }), /<button[^>]*disabled=""[^>]*>만드는 중/);
});

test("이미 있는 달(409 뒤 목록)은 만들기 대신 그 계획안 링크", () => {
  const out = html({
    items: [item({ month: 12, id: 9 })],
    problem: "이 반의 그 달 월간계획안이 이미 있습니다.",
  });
  assert.match(out, /href="\/plans\/monthly\/play\/9"/);
  assert.doesNotMatch(out, /만들기/);
});

// ---- 컨테이너: 가짜 react(상태 · effect · ref)로 실제 PlayMonthlyEntry 를 돌린다 ----
class FakeApiError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}
function defer() {
  let resolve, reject;
  const promise = new Promise((a, b) => ((resolve = a), (reject = b)));
  return { promise, resolve, reject };
}
const tick = () => new Promise((r) => setImmediate(r));
function mount({ classId = 7, month = 12, list, create }) {
  const slots = [],
    refs = [],
    effects = [],
    pushes = [],
    created = [];
  let cursor = 0,
    refCursor = 0,
    effCursor = 0,
    tree;
  const fakeReact = {
    useState: (init) => {
      const i = cursor++;
      slots[i] ??= { v: typeof init === "function" ? init() : init };
      slots[i].set ??= (v) => {
        slots[i].v = typeof v === "function" ? v(slots[i].v) : v;
        render();
      };
      return [slots[i].v, slots[i].set];
    },
    useRef: (init) => (refs[refCursor++] ??= { current: init }),
    useEffect: (fn, deps) => {
      const i = effCursor++;
      const e = (effects[i] ??= {});
      if (e.deps && deps && deps.every((d, k) => Object.is(d, e.deps[k]))) return;
      e.deps = deps;
      e.pending = fn;
    },
  };
  const { default: Container } = load("../components/workspace/PlayMonthlyEntry.tsx", {
    react: fakeReact,
    "react/jsx-runtime": {
      jsx: (type, props) => ({ type, props }),
      jsxs: (t, p) => ({ type: t, props: p }),
    },
    "next/link": { __esModule: true, default: () => null },
    "next/navigation": { useRouter: () => ({ push: (h) => pushes.push(h) }) },
    "@/lib/api/client": { ApiError: FakeApiError },
    "@/lib/api/playMonthly": {
      listPlayMonthly: (...a) => list(...a),
      createPlayMonthly: (body) => (created.push(body), create(body)),
    },
    "./WorkspaceUI": { ws: {}, Message: () => null, Empty: () => null },
  });
  function render() {
    cursor = refCursor = effCursor = 0;
    tree = Container({ classId, month });
    effects.forEach((e) => {
      if (e.pending) {
        const fn = e.pending;
        e.pending = null;
        e.cleanup?.();
        e.cleanup = fn();
      }
    });
  }
  render();
  return {
    props: () => tree.props,
    pushes,
    created,
    unmount: () => effects.forEach((e) => e.cleanup?.()),
  };
}
const summary = (o) => ({
  id: 9,
  month: 12,
  status: "DRAFT",
  created_at: "2026-10-28T08:00:00Z",
  ...o,
});

test("컨테이너: 본문 · 201 이동 · 진행 중 두 번째 클릭 무시", async () => {
  const post = defer();
  const m = mount({ list: async () => ({ items: [] }), create: () => post.promise });
  await tick();
  m.props().onCreate();
  m.props().onCreate();
  assert.deepEqual(m.created, [{ class_id: 7, month: 12, emphasized_row_keys: [] }]);
  assert.equal(m.props().busy, true);
  post.resolve({ id: 33 });
  await tick();
  assert.deepEqual(m.pushes, ["/plans/monthly/play/33"]);
});

test("컨테이너: 503 은 서버 문구를 그대로, 이동 없음", async () => {
  const msg = "지금은 이 반의 놀이 중심 월간계획안을 만들 수 없습니다. 관리자에게 문의해 주세요.";
  const m = mount({
    list: async () => ({ items: [] }),
    create: async () => Promise.reject(new FakeApiError(503, msg)),
  });
  await tick();
  m.props().onCreate();
  await tick();
  assert.equal(m.props().problem, msg);
  assert.equal(m.props().busy, false);
  assert.deepEqual(m.pushes, []);
});

test("컨테이너: 409 이미 있음이면 목록을 다시 읽어 그 달 항목이 생긴다", async () => {
  let reads = 0;
  const m = mount({
    list: async () => ({ items: reads++ ? [summary({ id: 9 })] : [] }),
    create: async () => Promise.reject(new FakeApiError(409, "이미 있습니다.")),
  });
  await tick();
  m.props().onCreate();
  await tick();
  await tick();
  assert.equal(reads, 2);
  assert.equal(m.props().items[0].id, 9);
});

test("컨테이너: 응답 전에 언마운트하면 이동 · 상태 변경이 없다(201 도 409 도)", async () => {
  for (const settle of ["ok", "dup"]) {
    const post = defer();
    let reads = 0;
    const m = mount({
      list: async () => (reads++, { items: [] }),
      create: () => post.promise,
    });
    await tick();
    m.props().onCreate();
    m.unmount();
    settle === "ok" ? post.resolve({ id: 33 }) : post.reject(new FakeApiError(409, "이미 있음"));
    await tick();
    await tick();
    assert.deepEqual(m.pushes, []);
    assert.equal(reads, 1, "언마운트 뒤 목록을 다시 읽지 않는다");
    assert.equal(m.props().problem, "");
  }
});
