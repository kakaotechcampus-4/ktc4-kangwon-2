// 같은 원 다른 반 열람 요청 · 승인 API 클라이언트 (docs/api-spec.md §2-2 · ADR-059).
// 실제 서버를 부르지 않는다. 보내는 주소 · 메서드 · 본문과, 거절 봉투를 어떻게 가르는지만 본다.
// 권한 판정 자체는 backend/tests 의 class_access 테스트가 본다.
import { test, afterEach } from "node:test";
import assert from "node:assert/strict";
import { registerHooks } from "node:module";
import { existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
registerHooks({
  resolve(spec, ctx, next) {
    if (spec.startsWith(".") && ctx.parentURL) {
      const u = new URL(spec + ".ts", ctx.parentURL);
      if (existsSync(fileURLToPath(u))) return { url: u.href, shortCircuit: true };
    }
    return next(spec, ctx);
  },
});
const { getArchiveSummary, requestClassAccess, getReceivedRequests, decideAccessRequest } =
  await import("../lib/api/classes.ts");
const { isClassAccessRequired, isClassReadOnly, isStaleWrite, isAlreadyExists } =
  await import("../lib/api/client.ts");

const realFetch = globalThis.fetch;
afterEach(() => {
  globalThis.fetch = realFetch;
});

/** 부른 요청을 적고 정해 둔 응답을 돌려준다. */
function answer(status, body) {
  const calls = [];
  globalThis.fetch = async (path, options = {}) => {
    calls.push({ path, method: options.method ?? "GET", body: options.body });
    return new Response(JSON.stringify(body), {
      status,
      headers: { "Content-Type": "application/json" },
    });
  };
  return calls;
}
const envelope = (code, fields) => ({ error: { code, message: "거절", fields } });

test("요약 · 받은 요청은 GET, 요청은 body 없는 POST, 결정은 status 하나만 담은 PATCH 다", async () => {
  let calls = answer(200, { items: [] });
  await getArchiveSummary(2);
  await getReceivedRequests();
  assert.deepEqual(
    calls.map((c) => [c.method, c.path, c.body]),
    [
      ["GET", "/api/classes/2/archive-summary", undefined],
      ["GET", "/api/access-requests/received", undefined],
    ],
  );

  calls = answer(201, { id: 1, class_id: 2, status: "PENDING" });
  const created = await requestClassAccess(2);
  assert.equal(created.status, "PENDING");
  assert.deepEqual(calls, [
    { path: "/api/classes/2/access-requests", method: "POST", body: undefined },
  ]);

  calls = answer(200, { id: 1, class_id: 2, status: "APPROVED" });
  await decideAccessRequest(1, "APPROVED");
  assert.equal(calls[0].method, "PATCH");
  assert.equal(calls[0].path, "/api/access-requests/1");
  assert.deepEqual(JSON.parse(calls[0].body), { status: "APPROVED" });
});

test("승인 필요 · 열람 전용 · 낡은 쓰기 · 이미 있음을 코드로 가른다 — 상태 코드만 보지 않는다", async () => {
  const caught = async (status, body) => {
    answer(status, body);
    return getArchiveSummary(2).then(
      () => assert.fail("거절이어야 한다"),
      (e) => e,
    );
  };
  const required = await caught(403, envelope("CLASS_ACCESS_REQUIRED", ["class_id"]));
  assert.equal(isClassAccessRequired(required), true);
  assert.equal(isClassReadOnly(required), false);

  const readOnly = await caught(403, envelope("CLASS_READ_ONLY", ["class_id"]));
  assert.equal(isClassReadOnly(readOnly), true);
  assert.equal(isClassAccessRequired(readOnly), false);

  const stale = await caught(409, envelope("STALE_WRITE", ["status"]));
  assert.equal(isStaleWrite(stale), true);
  assert.equal(isAlreadyExists(stale), false);

  const exists = await caught(409, envelope("ALREADY_EXISTS", ["class_id"]));
  assert.equal(isAlreadyExists(exists), true);
  assert.equal(isStaleWrite(exists), false);

  // 다른 403(예: 트렌드 꺼짐)을 승인 필요로 읽지 않는다.
  const other = await caught(403, envelope("TRENDS_DISABLED", []));
  assert.equal(isClassAccessRequired(other), false);
  assert.equal(isClassReadOnly(other), false);
});
