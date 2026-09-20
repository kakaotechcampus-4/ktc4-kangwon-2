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

  // 3) 제어권 + 실제 interception(health {msw:true})이 모두 확인되면 정상 resolve한다.
  runtime.starting = undefined;
  serviceWorker.controller = { scriptURL: "/mockServiceWorker.js" };
  const originalFetch = globalThis.fetch;
  let probe = null;
  globalThis.fetch = async (input, init) => {
    probe = { url: String(input), init };
    return Response.json({ msw: true });
  };
  try {
    await startMockWorker();
  } finally {
    globalThis.fetch = originalFetch;
  }
  assert.equal(probe.url, "/api/__msw_health");
  assert.equal(probe.init.headers.Accept, "application/json");
  assert.equal(probe.init.cache, "no-store");
  assert.equal(session.get("saessak.msw.controllerReload"), undefined);
});

test("핸들러가 없는 /api 요청만 진단 에러를 내고 나머지는 조용히 통과한다", async () => {
  const { handleUnhandledRequest } = await import("../msw/browser.ts");
  const count = (url) => {
    let errors = 0,
      warnings = 0;
    handleUnhandledRequest(new Request(url), {
      error() {
        errors++;
      },
      warning() {
        warnings++;
      },
    });
    assert.equal(warnings, 0, url + " 는 경고가 아니라 에러로만 구분한다");
    return errors;
  };

  // 실제 Next Route Handler — mock 누락이 아니므로 통과시킨다.
  assert.equal(count("http://localhost/api/assistant"), 0);
  assert.equal(count("http://localhost/api/assistant/"), 0);
  assert.equal(count("http://localhost/api/assistant/stream"), 0);
  assert.equal(count("http://localhost/api/assistant/stream?type=plan"), 0);
  assert.equal(count("http://localhost/api/templates/extract"), 0);
  assert.equal(count("http://localhost/api/templates/extract/"), 0);
  assert.equal(count("http://localhost/api/templates/extract?id=1"), 0);

  // prefix만 닮은 주소는 실제 Route Handler가 아니므로 누락으로 잡는다.
  assert.equal(count("http://localhost/api/assistant-wrong"), 1);
  assert.equal(count("http://localhost/api/assistant123"), 1);
  assert.equal(count("http://localhost/api/assistantXYZ"), 1);
  assert.equal(count("http://localhost/api/templates/extract-wrong"), 1);
  assert.equal(count("http://localhost/api/templates/extractABC"), 1);

  // mock handler 누락 — 개발자가 바로 알 수 있어야 한다.
  assert.equal(count("http://localhost/api/unknown"), 1);
  assert.equal(count("http://localhost/api/centers/not-handled"), 1);
  assert.equal(count("http://localhost/api/classes/foo/not-implemented"), 1);
  assert.equal(count("http://localhost/api/centers/1/classes?page=2"), 1);

  // 페이지·정적 리소스는 MSW 대상이 아니다.
  for (const url of [
    "http://localhost/home",
    "http://localhost/login",
    "http://localhost/onboarding/classes",
    "http://localhost/_next/static/chunk.js",
    "http://localhost/favicon.ico",
    "http://localhost/mockServiceWorker.js",
    "http://localhost/apilike/not-an-api",
  ])
    assert.equal(count(url), 0, url);
});

test("controller가 있어도 health 요청이 MSW를 통과하지 못하면 ready가 아니다", async () => {
  const { startMockWorker, ensureIntercepting, runtime, MSW_HEALTH_PATH } =
    await import("../msw/browser.ts");
  const session = new Map();
  globalThis.sessionStorage = {
    getItem: (k) => session.get(k) ?? null,
    setItem: (k, v) => session.set(k, String(v)),
    removeItem: (k) => session.delete(k),
  };
  globalThis.window = { location: { reload: () => assert.fail("새로고침하지 않는다") } };
  Object.defineProperty(globalThis, "navigator", {
    // 제어권은 정상적으로 확보된 상태로 고정한다.
    value: { serviceWorker: { controller: { scriptURL: "/mockServiceWorker.js" } } },
    configurable: true,
    writable: true,
  });
  const intercepted = (e) => e instanceof Error && /가로채지 못했습니다/.test(e.message);
  const original = globalThis.fetch;
  try {
    // A. handler가 응답한 경우에만 ready: 경로·헤더까지 확인한다.
    const calls = [];
    globalThis.fetch = async (input, init) => {
      calls.push({ url: String(input), init });
      return Response.json({ msw: true });
    };
    runtime.starting = undefined;
    await startMockWorker();
    assert.equal(calls.length, 1);
    assert.equal(calls[0].url, MSW_HEALTH_PATH);
    assert.equal(calls[0].url, "/api/__msw_health");
    assert.equal(calls[0].init.headers.Accept, "application/json");

    // B. controller는 있지만 Next의 HTML 404가 오는 경우 — 이번 수정의 핵심 회귀 테스트.
    globalThis.fetch = async () =>
      new Response(HTML_404, { status: 404, headers: { "Content-Type": "text/html" } });
    runtime.starting = undefined;
    await assert.rejects(startMockWorker(), intercepted);
    assert.equal(runtime.starting, undefined, "실패하면 재시도할 수 있게 되돌린다");
    await assert.rejects(ensureIntercepting(), intercepted);

    // B-2. 200 HTML이어도 SyntaxError가 아니라 readiness 실패로 정리한다.
    globalThis.fetch = async () =>
      new Response("<!DOCTYPE html><html><body>hi</body></html>", {
        status: 200,
        headers: { "Content-Type": "text/html" },
      });
    await assert.rejects(
      ensureIntercepting(),
      (e) => intercepted(e) && !(e instanceof SyntaxError),
    );

    // C. JSON이지만 probe 응답이 아닌 경우.
    for (const body of [{ msw: false }, {}, { msw: "true" }, [], null]) {
      globalThis.fetch = async () => Response.json(body);
      await assert.rejects(ensureIntercepting(), intercepted, JSON.stringify(body));
    }

    // D. Content-Type이 JSON이 아니거나, 서버 오류이거나, fetch 자체가 실패한 경우.
    globalThis.fetch = async () =>
      new Response('{"msw":true}', { headers: { "Content-Type": "text/plain" } });
    await assert.rejects(ensureIntercepting(), intercepted);
    globalThis.fetch = async () => Response.json({ msw: true }, { status: 500 });
    await assert.rejects(ensureIntercepting(), intercepted);
    globalThis.fetch = async () => {
      throw new TypeError("Failed to fetch");
    };
    await assert.rejects(ensureIntercepting(), intercepted);
  } finally {
    globalThis.fetch = original;
    runtime.starting = undefined;
  }
});
