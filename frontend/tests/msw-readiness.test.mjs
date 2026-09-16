import { test } from "node:test";
import assert from "node:assert/strict";
import { registerHooks } from "node:module";
import { existsSync } from "node:fs";
import { fileURLToPath } from "node:url";

// 확장자 없는 상대 import(.ts)와, node에서 실행할 수 없는 msw/browser 스텁을 함께 해결한다.
const WORKER_STUB =
  "data:text/javascript,export const setupWorker=()=>({start:async()=>undefined});";
registerHooks({
  resolve(spec, ctx, next) {
    if (spec === "msw/browser") return { url: WORKER_STUB, shortCircuit: true };
    if (spec.startsWith(".") && ctx.parentURL) {
      const u = new URL(spec + ".ts", ctx.parentURL);
      if (existsSync(fileURLToPath(u))) return { url: u.href, shortCircuit: true };
    }
    return next(spec, ctx);
  },
});

const { apiRequest, ApiError, MswTransportError, isApiNotFound } =
  await import("../lib/api/client.ts");

const HTML_404 = "<!DOCTYPE html><html><body>404: This page could not be found.</body></html>";

test("Next HTML 404는 ApiError가 아니라 MswTransportError로 분리된다", async () => {
  const original = globalThis.fetch;
  try {
    for (const path of ["/api/centers/1/classes", "/api/classes/2/children"]) {
      let calls = 0;
      globalThis.fetch = async () => {
        calls++;
        return new Response(HTML_404, { status: 404, headers: { "Content-Type": "text/html" } });
      };
      await assert.rejects(
        apiRequest(path),
        (e) =>
          e instanceof MswTransportError &&
          !(e instanceof ApiError) &&
          e.status === 404 &&
          e.path === path,
      );
      assert.equal(calls, 1, "재시도 없이 1회만 호출한다");
    }
    // Content-Type이 없어도 본문으로 판별한다.
    globalThis.fetch = async () =>
      new Response("404: This page could not be found.", { status: 404 });
    await assert.rejects(
      apiRequest("/api/classes/2/children"),
      (e) => e instanceof MswTransportError,
    );
  } finally {
    globalThis.fetch = original;
  }
});

test("JSON NOT_FOUND는 기존 ApiError(404)로 유지되고 성공 응답도 그대로다", async () => {
  const original = globalThis.fetch;
  try {
    const body = { error: { code: "NOT_FOUND", message: "대상을 찾을 수 없습니다." } };
    globalThis.fetch = async () => Response.json(body, { status: 404 });
    await assert.rejects(
      apiRequest("/api/classes/2/children"),
      (e) =>
        e instanceof ApiError &&
        !(e instanceof MswTransportError) &&
        e.status === 404 &&
        e.body.error.code === "NOT_FOUND" &&
        isApiNotFound(e),
    );
    globalThis.fetch = async () => Response.json({ items: [], count: 0 });
    assert.deepEqual(await apiRequest("/api/classes/2/children"), { items: [], count: 0 });
  } finally {
    globalThis.fetch = original;
  }
});

test("isApiNotFound는 코드 없는 404를 오래된 연결 정보로 오판하지 않는다", () => {
  assert.equal(isApiNotFound(new ApiError(404, { error: { code: "NOT_FOUND" } })), true);
  assert.equal(isApiNotFound(new ApiError(404, "404: This page could not be found.")), false);
  assert.equal(isApiNotFound(new ApiError(409, { error: { code: "GATE_BLOCKED" } })), false);
  assert.equal(
    isApiNotFound(new MswTransportError(404, "/api/classes/2/children", HTML_404)),
    false,
  );
});

test("HTML 404에서는 class link를 지우지 않고, JSON NOT_FOUND에서만 정리한다", async () => {
  const store = new Map(),
    session = new Map([
      ["saessak.accountEmail", "teacher@example.com"],
      ["saessak.demoSession", "active"],
    ]);
  const ls = {
    getItem: (k) => store.get(k) ?? null,
    setItem: (k, v) => store.set(k, String(v)),
    removeItem: (k) => store.delete(k),
  };
  const ss = {
    getItem: (k) => session.get(k) ?? null,
    setItem: (k, v) => session.set(k, String(v)),
    removeItem: (k) => session.delete(k),
  };
  globalThis.localStorage = ls;
  globalThis.sessionStorage = ss;
  globalThis.window = Object.assign(new EventTarget(), { localStorage: ls, sessionStorage: ss });
  store.set(
    "saessak.demoAccount:teacher%40example.com",
    JSON.stringify({
      name: "담임",
      email: "teacher@example.com",
      salt: Array.from({ length: 16 }, (_, i) => i),
      hash: "a".repeat(64),
    }),
  );

  const { loadServerChildren } = await import("../lib/api/onboarding.ts");
  const { API_STORAGE_CONTEXT } = await import("../lib/api/storage-context.ts");
  const linkKey = "saessak.apiLinks.v1:" + API_STORAGE_CONTEXT + ":teacher%40example.com";
  const classroom = {
    id: "class-1",
    className: "햇님반",
    ageGroup: "",
    currentChildCount: "",
    teacherName: "담임",
    guardianConsent: true,
    childrenSkipped: false,
    children: [{ id: "local-1", name: "김새싹" }],
  };
  const links = () => ({ classes: { "class-1": { id: 2, signature: "x" } }, children: {} });
  const original = globalThis.fetch;
  try {
    // 1) MSW 미동작(HTML 404): link 유지 + 오류 전파
    store.set(linkKey, JSON.stringify(links()));
    globalThis.fetch = async () =>
      new Response(HTML_404, { status: 404, headers: { "Content-Type": "text/html" } });
    await assert.rejects(loadServerChildren(classroom), (e) => e instanceof MswTransportError);
    assert.equal(
      JSON.parse(store.get(linkKey)).classes["class-1"].id,
      2,
      "HTML 404에서는 link를 지우지 않는다",
    );

    // 2) 실제 JSON NOT_FOUND: link 정리 + 로컬 명단으로 계속 진행
    globalThis.fetch = async () =>
      Response.json(
        { error: { code: "NOT_FOUND", message: "대상을 찾을 수 없습니다." } },
        { status: 404 },
      );
    assert.deepEqual(await loadServerChildren(classroom), classroom);
    assert.equal(
      JSON.parse(store.get(linkKey)).classes["class-1"],
      undefined,
      "JSON NOT_FOUND에서는 오래된 link를 정리한다",
    );
  } finally {
    globalThis.fetch = original;
  }
});

test("서비스워커가 페이지를 제어하지 못하면 startMockWorker()는 실패한다(앱 렌더 금지)", async () => {
  const { startMockWorker, runtime } = await import("../msw/browser.ts");
  const session = new Map();
  const listeners = new Set();
  globalThis.sessionStorage = {
    getItem: (k) => session.get(k) ?? null,
    setItem: (k, v) => session.set(k, String(v)),
    removeItem: (k) => session.delete(k),
  };
  let reloads = 0;
  globalThis.window = {
    location: {
      reload: () => {
        reloads++;
      },
    },
  };
  const serviceWorker = {
    controller: null,
    ready: Promise.resolve({ active: null }),
    addEventListener: (_t, fn) => listeners.add(fn),
    removeEventListener: (_t, fn) => listeners.delete(fn),
  };
  Object.defineProperty(globalThis, "navigator", {
    value: { serviceWorker },
    configurable: true,
    writable: true,
  });

  // 1) 첫 시도: 제어권을 못 얻으면 새로고침 1회만 하고 resolve하지 않는다.
  runtime.starting = undefined;
  const first = startMockWorker();
  const settled = await Promise.race([
    first.then(
      () => "resolved",
      () => "rejected",
    ),
    new Promise((r) => setTimeout(() => r("pending"), 12000)),
  ]);
  assert.equal(settled, "pending", "새로고침 대기 중에는 resolve/reject하지 않는다");
  assert.equal(reloads, 1, "새로고침은 한 번만 시도한다");
  assert.equal(session.get("saessak.msw.controllerReload"), "1");

  // 2) 새로고침 이후에도 제어권이 없으면 성공이 아니라 오류로 끝난다(fail-closed).
  runtime.starting = undefined;
  await assert.rejects(
    startMockWorker(),
    (e) => e instanceof Error && /제어하지 못했습니다/.test(e.message),
  );
  assert.equal(reloads, 1, "무한 새로고침 루프가 없다");

  // 3) 제어권이 있으면 정상 resolve하고 재시도 플래그를 정리한다.
  runtime.starting = undefined;
  serviceWorker.controller = { scriptURL: "/mockServiceWorker.js" };
  await startMockWorker();
  assert.equal(session.get("saessak.msw.controllerReload"), undefined);
});
