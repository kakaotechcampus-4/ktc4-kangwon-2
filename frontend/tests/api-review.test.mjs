import assert from "node:assert/strict";
import { test } from "node:test";
import { registerHooks } from "node:module";
import { existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
registerHooks({
  // 상대 경로와 @/ 별칭에 .ts 를 붙여 본다. 목록을 손으로 관리하면 import 를 하나 더할
  // 때마다 여기도 고쳐야 하고, 빠뜨리면 「모듈을 찾을 수 없다」로 끝난다.
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
const { readLimitedBody, BodyLimitError, sameOriginGuard } =
  await import("../lib/workspace/api-validation.ts");
test("streamed requests stop at the byte limit without trusting Content-Length", async () => {
  const request = new Request("http://localhost", {
    method: "POST",
    duplex: "half",
    body: new ReadableStream({
      start(c) {
        c.enqueue(new Uint8Array(10));
        c.enqueue(new Uint8Array(10));
        c.close();
      },
    }),
  });
  await assert.rejects(() => readLimitedBody(request, 15), BodyLimitError);
  const body = await readLimitedBody(
    new Request("http://localhost", { method: "POST", body: "한글" }),
    6,
  );
  assert.equal(new TextDecoder().decode(body), "한글");
});
test("same-origin guard blocks other sites, headless callers and garbled origins", () => {
  const from = (headers) =>
    new Request("http://localhost:3000/api/templates/extract", { method: "POST", headers });
  assert.equal(
    sameOriginGuard(from({ origin: "http://localhost:3000", host: "localhost:3000" })),
    null,
  );
  assert.equal(
    sameOriginGuard(from({ origin: "https://foreign.example", host: "localhost:3000" })).status,
    403,
  );
  // Origin 은 브라우저만 붙인다. curl·스크립트·다른 서버는 헤더 자체가 없다.
  assert.equal(
    sameOriginGuard(from({ host: "localhost:3000" })).status,
    403,
    "Origin 이 없는 요청도 막는다",
  );
  // Origin 이 URL 형태가 아니면 파싱이 터진다. 터진 채로 통과시키지 않는다.
  assert.equal(
    sameOriginGuard(from({ origin: "null", host: "localhost:3000" })).status,
    403,
    "Origin 이 URL 이 아니어도 막는다",
  );
});
