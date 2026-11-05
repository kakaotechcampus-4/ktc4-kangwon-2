import assert from "node:assert/strict";
import { test } from "node:test";
import { registerHooks } from "node:module";
import { existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
registerHooks({
  resolve(spec, ctx, next) {
    const base = spec.startsWith("@/")
      ? new URL(`../${spec.slice(2)}.ts`, import.meta.url)
      : spec.startsWith(".") && ctx.parentURL
        ? new URL(spec + ".ts", ctx.parentURL)
        : null;
    if (base && existsSync(fileURLToPath(base))) return { url: base.href, shortCircuit: true };
    return next(spec, ctx);
  },
});

function storage() {
  const values = new Map();
  return {
    values,
    getItem: (k) => values.get(k) ?? null,
    setItem: (k, v) => values.set(k, String(v)),
    removeItem: (k) => values.delete(k),
  };
}
const local = storage();
const session = storage();
globalThis.localStorage = local;
let assigned = "";
globalThis.window = {
  localStorage: local,
  sessionStorage: session,
  location: { assign: (u) => (assigned = u) },
};
const sent = [];
globalThis.fetch = async (url, options = {}) => {
  sent.push({ url: String(url), options });
  const json = (body, status = 200) =>
    new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
  if (String(url).includes("/api/auth/kakao/authorize"))
    return json({ url: "https://kauth.kakao.com/oauth/authorize?state=x" });
  if (String(url).endsWith("/api/auth/kakao"))
    return json({
      token: "kakao-token",
      user: { id: 7, email: "Teacher@Example.com", name: "김선생", center_id: 3 },
    });
  return json({ error: { code: "NOT_FOUND", message: "", fields: [] } }, 404);
};

const { newKakaoState, startKakaoLogin, takeKakaoState } = await import("../lib/auth/kakao.ts");
const { verifyKakao, accountName } = await import("../lib/auth/local-account.ts");
const { startDemoSession } = await import("../lib/auth/demo-session.ts");

test("state 는 서버가 받는 모양이고 매번 다르다", () => {
  const a = newKakaoState();
  assert.match(a, /^[A-Za-z0-9_-]{16,128}$/);
  assert.notEqual(a, newKakaoState());
});

test("시작하면 state 를 남기고 서버가 준 카카오 주소로 간다", async () => {
  await startKakaoLogin();
  const state = session.values.get("ssample.kakaoState");
  assert.ok(sent.at(-1).url.endsWith(`state=${state}`));
  assert.equal(assigned, "https://kauth.kakao.com/oauth/authorize?state=x");
  // 돌아온 값이 같으면 통과하고, 한 번 꺼내면 지운다 — 같은 값으로 두 번 못 들어온다.
  assert.equal(takeKakaoState(state), true);
  assert.equal(takeKakaoState(state), false);
});

test("다른 state 로 돌아오면 거부하고 저장한 값도 지운다", async () => {
  await startKakaoLogin();
  assert.equal(takeKakaoState("someone-elses-state-value"), false);
  assert.equal(session.values.has("ssample.kakaoState"), false);
});

test("카카오 로그인은 이메일 로그인과 같은 브라우저 기록을 남긴다", async () => {
  const centerId = await verifyKakao("the-code");
  assert.deepEqual(JSON.parse(sent.at(-1).options.body), { code: "the-code" });
  assert.equal(centerId, 3);
  assert.equal(session.values.get("saessak.authToken"), "kakao-token");
  assert.equal(session.values.get("saessak.accountEmail"), "teacher@example.com");
  assert.equal(startDemoSession(), true);
  assert.equal(accountName(), "김선생");
});
