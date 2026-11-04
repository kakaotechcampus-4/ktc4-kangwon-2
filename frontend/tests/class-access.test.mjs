// 같은 원 다른 반 열람 (ADR-059) — 403 두 코드를 교사가 할 일로 갈라 말하고, 승인 · 거절은 status 하나만 보낸다.
import { test } from "node:test";
import assert from "node:assert/strict";
import { registerHooks } from "node:module";
import { existsSync } from "node:fs";
import { fileURLToPath } from "node:url";

// 확장자 없는 `./x` · `@/x` 를 `.ts` 로 잇는다 (documents-server.test.mjs 와 같다).
registerHooks({
  resolve(spec, ctx, next) {
    const base = spec.startsWith("@/") ? new URL("../" + spec.slice(2), import.meta.url) : null;
    const url =
      base ?? (spec.startsWith(".") && ctx.parentURL ? new URL(spec, ctx.parentURL) : null);
    if (url) {
      const ts = new URL(url.href + ".ts");
      if (existsSync(fileURLToPath(ts))) return { url: ts.href, shortCircuit: true };
    }
    return next(spec, ctx);
  },
});

const { ApiError } = await import("../lib/api/client.ts");
const { classAccessMessage, decideRequest } = await import("../lib/api/class-access.ts");

const denied = (code) =>
  new ApiError(403, { error: { code, message: "서버 말", fields: ["class_id"] } });

test("403 두 코드는 다른 말을 한다 — 승인이 없으면 다시 요청, 보기 전용이면 누가 고치나", () => {
  assert.match(classAccessMessage(denied("CLASS_ACCESS_REQUIRED")), /다시 요청/);
  assert.match(classAccessMessage(denied("CLASS_READ_ONLY")), /담임 선생님만/);
  assert.equal(classAccessMessage(denied("NOT_FOUND")), null);
  assert.equal(classAccessMessage(new Error("그냥 오류")), null);
});

test("승인 · 거절 · 취소는 PATCH 에 status 하나만 담는다", async (t) => {
  const sent = [];
  globalThis.fetch = async (url, init) => {
    sent.push({ url: String(url), method: init.method, body: init.body });
    return new Response(JSON.stringify({ id: 5, status: "APPROVED" }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  };
  t.after(() => delete globalThis.fetch);
  await decideRequest(5, "APPROVED");
  assert.equal(sent.length, 1);
  assert.match(sent[0].url, /\/api\/access-requests\/5$/);
  assert.equal(sent[0].method, "PATCH");
  assert.deepEqual(JSON.parse(sent[0].body), { status: "APPROVED" });
});
