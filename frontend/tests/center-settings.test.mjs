/**
 * 트렌드봇 끄고 켜기 — 화면이 서버 계약대로 부르는지 (api-spec §3-1 · FR-808).
 *
 * **기본이 꺼짐**인 것과 **보낸 칸만 바뀌는 것**을 지킨다. 전체 교체로 바뀌면
 * 설정이 늘어날 때 다른 토글을 말없이 덮는다.
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { registerHooks } from "node:module";
import { existsSync } from "node:fs";
import { fileURLToPath } from "node:url";

// 라우트 핸들러는 "@/..." 별칭을 쓴다. tsconfig 의 paths 를 여기서 흉내 낸다.
const ROOT = new URL("../", import.meta.url);

registerHooks({
  resolve(spec, ctx, next) {
    if (spec.startsWith("@/")) {
      const base = new URL(spec.slice(2), ROOT);
      for (const candidate of [base.href, base.href + ".ts", base.href + ".tsx"]) {
        if (existsSync(fileURLToPath(candidate))) return { url: candidate, shortCircuit: true };
      }
    }
    if (spec.startsWith(".") && ctx.parentURL) {
      const u = new URL(spec + ".ts", ctx.parentURL);
      if (existsSync(fileURLToPath(u))) return { url: u.href, shortCircuit: true };
    }
    return next(spec, ctx);
  },
});

const { setupServer } = await import("msw/node");
const { http, HttpResponse } = await import("msw");
const { fixtureAccount, fixtureKey, fixtureSession } = await import("./auth-fixture.mjs");
const centers = await import("../lib/api/centers.ts");

const server = setupServer();
server.listen({ onUnhandledRequest: "error" });

const realFetch = globalThis.fetch;
globalThis.fetch = (url, options) => realFetch(new URL(url, "http://localhost").href, options);

function browser() {
  const values = new Map([[fixtureKey, fixtureAccount]]);
  const storage = {
    getItem: (k) => values.get(k) ?? null,
    setItem: (k, v) => values.set(k, v),
    removeItem: (k) => values.delete(k),
  };
  globalThis.localStorage = storage;
  const session = fixtureSession();
  globalThis.sessionStorage = {
    getItem: (k) => session.getItem(k),
    setItem: () => {},
    removeItem: () => {},
  };
  globalThis.window = Object.assign(new EventTarget(), {
    localStorage: storage,
    sessionStorage,
    location: { search: "" },
  });
}

test("설정한 적 없으면 꺼짐으로 읽는다", async () => {
  browser();
  server.use(
    http.get("*/api/centers/:id/settings", () => HttpResponse.json({ trends_enabled: false })),
  );
  assert.deepEqual(await centers.getCenterSettings(3), { trends_enabled: false });
});

test("★ 보낸 칸만 담아 보낸다 — 전체 교체가 아니다", async () => {
  browser();
  let sent;
  server.use(
    http.put("*/api/centers/:id/settings", async ({ request }) => {
      sent = await request.json();
      return HttpResponse.json({ trends_enabled: true });
    }),
  );
  await centers.saveCenterSettings(3, { trends_enabled: true });
  assert.deepEqual(sent, { trends_enabled: true }, "다른 칸을 같이 보내면 안 된다");
});

test("남의 원은 404 로 던진다", async () => {
  browser();
  server.use(
    http.get("*/api/centers/:id/settings", () =>
      HttpResponse.json(
        { error: { code: "NOT_FOUND", message: "원을 찾을 수 없습니다." } },
        { status: 404 },
      ),
    ),
  );
  await assert.rejects(() => centers.getCenterSettings(99));
});

/**
 * **서버에서 막는 것이 진짜 막는 것이다.** 화면 검사는 열어둔 탭이나 주소를 직접
 * 부르는 요청을 못 막고, 트렌드 호출은 유료다. 확인할 수 없으면 거절한다 —
 * 부가 기능이라 꺼진 쪽이 안전하다.
 */
test("★ 트렌드봇이 꺼져 있으면 /api/assistant 가 403", async () => {
  const route = await import("../app/api/assistant/route.ts");
  const previous = process.env.FASTAPI_BASE_URL;
  process.env.FASTAPI_BASE_URL = "http://backend.test";
  server.use(
    http.get("http://backend.test/api/auth/me", () =>
      HttpResponse.json({ id: 1, email: "t@x.kr", center_id: 3 }),
    ),
    http.get("http://backend.test/api/centers/3/settings", () =>
      HttpResponse.json({ trends_enabled: false }),
    ),
  );
  const response = await route.POST(
    new Request("http://localhost/api/assistant", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: "Bearer t",
        Origin: "http://localhost",
        Host: "localhost",
      },
      body: JSON.stringify({ task: "trends", payload: { topic: "놀이", today: "2026-10-17" } }),
    }),
  );
  process.env.FASTAPI_BASE_URL = previous;
  assert.equal(response.status, 403);
});

test("★ 토큰이 없으면 거절한다 — 확인할 수 없으면 꺼진 쪽이다", async () => {
  const route = await import("../app/api/assistant/route.ts");
  const response = await route.POST(
    new Request("http://localhost/api/assistant", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Origin: "http://localhost",
        Host: "localhost",
      },
      body: JSON.stringify({ task: "trends", payload: { topic: "놀이", today: "2026-10-17" } }),
    }),
  );
  assert.equal(response.status, 403);
});
