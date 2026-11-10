/**
 * 상단바 종 — 지나간 클릭이 늦게 끝나도 사용자를 끌고 가지 않는가 (PR #553 리뷰 P2).
 *
 * 알림을 누르면 읽음 POST 를 끝낸 뒤 옮긴다. 그 사이 다른 알림을 누르거나 화면이 바뀌면 먼저 누른
 * 클릭의 이동은 버려야 한다 — 읽음 저장은 끝까지 보낸다. 실제 TSX 를 React 흉내 위에서 돌리고
 * (observation-screens.test.mjs 와 같은 방식) 읽음 응답이 끝나는 순서를 시험이 정한다. 브라우저 E2E 는 아니다.
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { readFileSync } from "node:fs";

const require = createRequire(import.meta.url);
const jsx = (type, props, key) => ({ type, props, key });
const runtime = { jsx, jsxs: jsx, Fragment: "fragment" };
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
  const out = { exports: {} };
  new Function("require", "module", "exports", code)(
    (name) => {
      assert.ok(name in modules, `unhandled import: ${name}`);
      return modules[name];
    },
    out,
    out.exports,
  );
  return out.exports;
}

const all = (node) => {
  if (Array.isArray(node)) return node.flatMap(all);
  if (node === null || node === undefined || typeof node === "boolean") return [];
  return typeof node === "object" ? [node, ...all(node.props?.children)] : [node];
};
const textOf = (node) =>
  all(node)
    .filter((part) => typeof part === "string" || typeof part === "number")
    .join("");

/** React 흉내 — hook 자리를 컴포넌트 경로로 나누고, 함수 컴포넌트를 펼친다. setState 는 다시 그리지 않는다. */
function host() {
  const boxes = new Map();
  const effects = new Map();
  const queue = [];
  let scope = "";
  let ids = 0;
  const box = () => {
    if (!boxes.has(scope)) boxes.set(scope, { slots: [], cursor: 0 });
    return boxes.get(scope);
  };
  const same = (a, b) =>
    !!a && !!b && a.length === b.length && a.every((d, i) => Object.is(d, b[i]));
  const useState = (initial) => {
    const b = box();
    const i = b.cursor++;
    if (!(i in b.slots)) b.slots[i] = typeof initial === "function" ? initial() : initial;
    return [
      b.slots[i],
      (next) => (b.slots[i] = typeof next === "function" ? next(b.slots[i]) : next),
    ];
  };
  const memo = (fn, deps) => {
    const b = box();
    const i = b.cursor++;
    if (!(i in b.slots) || !same(deps, b.slots[i].deps)) b.slots[i] = { value: fn(), deps };
    return b.slots[i].value;
  };
  const useEffect = (fn, deps) => {
    const key = `${scope}#${box().cursor++}`;
    const prev = effects.get(key);
    if (prev && same(deps, prev.deps)) return;
    const next = { deps };
    effects.set(key, next);
    queue.push(() => {
      prev?.cleanup?.();
      next.cleanup = fn();
    });
  };
  const react = {
    useState,
    useEffect,
    useLayoutEffect: useEffect,
    useMemo: memo,
    useCallback: (fn, deps) => memo(() => fn, deps),
    useRef: (current) => useState(() => ({ current }))[0],
    useId: () => useState(() => `:r${ids++}:`)[0],
  };
  const resolve = (node, path) => {
    if (Array.isArray(node)) return node.map((n) => resolve(n, path));
    if (!node || typeof node !== "object") return node;
    if (typeof node.type === "function") {
      const outer = scope;
      scope = `${path}/${node.type.name}#${node.key ?? ""}`;
      box().cursor = 0;
      const out = node.type(node.props);
      const id = scope;
      scope = outer;
      return resolve(out, id);
    }
    return { ...node, props: { ...node.props, children: resolve(node.props?.children, path) } };
  };
  return {
    react,
    mount(Page) {
      let tree;
      const render = () => {
        scope = "";
        box().cursor = 0;
        tree = resolve(Page({}), "");
      };
      render();
      return {
        async flush() {
          for (let i = 0; i < 4; i++) {
            render();
            queue.splice(0).forEach((fn) => fn());
            await new Promise((r) => setImmediate(r));
          }
          render();
        },
        /** 그 글이 든 버튼을 누른다. 이동은 기다리지 않는다 — 읽음 응답은 시험이 끝낸다. */
        click(text) {
          const found = all(tree).find(
            (n) => n?.type === "button" && textOf(n.props.children).includes(text),
          );
          assert.ok(found, `button: ${text}`);
          found.props.onClick({ preventDefault() {}, stopPropagation() {} });
          render();
        },
      };
    },
  };
}

const APPROVED = {
  id: 12,
  kind: "ACCESS_APPROVED",
  request_id: 5,
  class_id: 3,
  class_name: "해님반",
  requester_name: "가요청",
  created_at: "2026-11-11T01:02:03Z",
  read_at: null,
};
const REQUESTED = {
  id: 13,
  kind: "ACCESS_REQUESTED",
  request_id: 6,
  class_id: 4,
  class_name: "달님반",
  requester_name: "나요청",
  created_at: "2026-11-11T02:02:03Z",
  read_at: null,
};
const A_TEXT = "해님반 열람 요청이 승인됐어요";
const B_TEXT = "나요청 선생님이 달님반 열람을 요청했어요";
const A_HREF = "/documents?foreign=3";
const B_HREF = "/documents?foreign=received";

/** 종 하나를 그린다. 읽음 POST 는 끝내지 않고 쌓아 두어, 시험이 끝나는 순서를 고른다. */
async function bell(pathname = "/") {
  const moves = [];
  const posts = [];
  const route = { pathname };
  globalThis.window = {
    addEventListener() {},
    removeEventListener() {},
    location: { assign: (href) => moves.push(href) },
  };
  globalThis.document = {
    visibilityState: "visible",
    addEventListener() {},
    removeEventListener() {},
  };
  const router = { push: (href) => moves.push(href), replace: (href) => moves.push(href) };
  const { react, mount } = host();
  const { default: NotificationBell } = compile("../components/app/NotificationBell.tsx", {
    "react/jsx-runtime": runtime,
    react,
    "next/link": { __esModule: true, default: "link" },
    "next/navigation": { usePathname: () => route.pathname, useRouter: () => router },
    "@/lib/api/notifications": {
      listNotifications: async () => ({ items: [APPROVED, REQUESTED] }),
      markNotificationsRead: (ids) =>
        new Promise((resolve) => posts.push({ ids, done: () => resolve(undefined) })),
    },
    "@/lib/workspace/model": { localDate: () => "11월 11일", localTime: () => "오전 10:02" },
    "./icons": { Icon: "icon" },
  });
  const view = mount(NotificationBell);
  await view.flush();
  return { view, moves, posts, route };
}

const settle = async () => {
  for (let i = 0; i < 5; i++) await new Promise((r) => setImmediate(r));
};

test("A 를 누르고 B 를 누른 뒤 읽음이 B · A 순으로 끝나면 B 로만 간다", async () => {
  const { view, moves, posts } = await bell();
  view.click(A_TEXT);
  view.click(B_TEXT);
  // 읽음 저장은 두 클릭 모두 보낸다.
  assert.deepEqual(
    posts.map((p) => p.ids),
    [[APPROVED.id], [REQUESTED.id]],
  );

  posts[1].done();
  await settle();
  assert.deepEqual(moves, [B_HREF]);

  // 먼저 누른 A 의 응답이 늦게 와도 A 로 다시 끌고 가지 않는다.
  posts[0].done();
  await settle();
  assert.deepEqual(moves, [B_HREF]);
  assert.ok(!moves.includes(A_HREF));
});

test("A 를 누르고 읽음을 기다리는 동안 화면이 바뀌면 A 로 가지 않는다", async () => {
  const { view, moves, posts, route } = await bell();
  view.click(A_TEXT);
  assert.deepEqual(
    posts.map((p) => p.ids),
    [[APPROVED.id]],
  );

  // 사이드바로 다른 화면에 갔다 — 상단바는 layout 안이라 그대로 남고 pathname 만 바뀐다.
  route.pathname = "/routines";
  await view.flush();

  posts[0].done();
  await settle();
  assert.deepEqual(moves, []);
});
