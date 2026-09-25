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
const { POST } = await import("../app/api/assistant/route.ts");
const { readLimitedBody, BodyLimitError, validAIInput, matchesSchema } =
  await import("../lib/workspace/api-validation.ts");
const source = {
  id: "r",
  date: "2026-09-11",
  text: "블록을 세 개 쌓고 더 높이 만들겠다고 말했다.",
  classId: "c1",
  childId: "a1",
};
// 브라우저가 보내는 요청을 흉내낸다 — Origin · Host 는 브라우저와 fetch 가 붙이는 값이라
// new Request() 로는 안 생긴다. sameOriginGuard 가 둘을 비교하므로 직접 넣는다.
const request = (body) =>
  new Request("http://localhost:3000/api/assistant", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      origin: "http://localhost:3000",
      host: "localhost:3000",
    },
    body: JSON.stringify(body),
  });
function response(data) {
  return new Response(
    JSON.stringify({
      status: "completed",
      output: [{ content: [{ type: "output_text", text: JSON.stringify(data) }] }],
    }),
    { headers: { "Content-Type": "application/json" } },
  );
}
test("AI input rejects unknown tasks, arrays, wrong dates and mixed children", () => {
  assert.equal(validAIInput("verify", []), false);
  assert.equal(validAIInput("toString", {}), false);
  assert.equal(
    validAIInput("compare", { sources: [source, { ...source, id: "r2", childId: "a2" }] }),
    false,
  );
  assert.equal(
    validAIInput("document", {
      kind: "관찰일지",
      start: "2026-09-11",
      end: "2026-09-11",
      sources: [source, { ...source, id: "r2", classId: "c2" }],
    }),
    false,
  );
  assert.equal(
    validAIInput("document", {
      kind: "일일 보육일지",
      start: "2026-09-11",
      end: "2026-09-12",
      sources: [source],
    }),
    false,
  );
  assert.equal(
    validAIInput("document", {
      kind: "관찰일지",
      start: "2026-09-11",
      end: "2026-09-11",
      sources: [source],
    }),
    true,
  );
});
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
test("model output cannot omit fields, add fields or change types", () => {
  const schema = {
    type: "object",
    properties: { issues: { type: "array", items: { type: "string" } } },
    required: ["issues"],
    additionalProperties: false,
  };
  assert.equal(matchesSchema({ issues: [] }, schema), true);
  assert.equal(matchesSchema({}, schema), false);
  assert.equal(matchesSchema({ issues: "pass" }, schema), false);
  assert.equal(matchesSchema({ issues: [], pass: true }, schema), false);
});
test("API rejects malformed input and oversized bodies before any provider call", async () => {
  assert.equal((await POST(request({ task: "verify", payload: {} }))).status, 400);
  assert.equal(
    (await POST(request({ task: "template", payload: { text: "a".repeat(310000) } }))).status,
    413,
  );
  const cross = new Request("http://localhost:3000/api/assistant", {
    method: "POST",
    headers: { origin: "https://foreign.example", host: "localhost:3000" },
    body: "{}",
  });
  assert.equal((await POST(cross)).status, 403);

  // Origin 은 브라우저만 붙인다. curl·스크립트·다른 서버는 헤더 자체가 없다.
  // "없으면 통과"로 두면 공개 배포된 이 경로로 우리 OpenAI 키를 그냥 쓸 수 있다.
  const headless = new Request("http://localhost:3000/api/assistant", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ task: "template", payload: { text: "안녕" } }),
  });
  assert.equal((await POST(headless)).status, 403, "Origin 이 없는 요청도 막는다");

  // Origin 이 URL 형태가 아니면 파싱이 터진다. 터진 채로 통과시키지 않는다.
  const garbled = new Request("http://localhost:3000/api/assistant", {
    method: "POST",
    headers: { "Content-Type": "application/json", origin: "null", host: "localhost:3000" },
    body: JSON.stringify({ task: "template", payload: { text: "안녕" } }),
  });
  assert.equal((await POST(garbled)).status, 403, "Origin 이 URL 이 아니어도 막는다");
});
test("concurrent body reads cannot bypass the two-request limit", async () => {
  const originalFetch = globalThis.fetch;
  const key = process.env.OPENAI_API_KEY;
  const model = process.env.OPENAI_MODEL;
  process.env.OPENAI_API_KEY = "test-only";
  process.env.OPENAI_MODEL = "test-only";
  const releases = [];
  let calls = 0;
  globalThis.fetch = () => {
    calls++;
    return new Promise((resolve) =>
      releases.push(() =>
        resolve(response({ headings: ["목표"], style: "항목형", summary: "원문 요약" })),
      ),
    );
  };
  try {
    const requests = Array.from({ length: 3 }, () =>
      POST(request({ task: "template", payload: { text: "교사가 작성한 기관 양식 원문입니다." } })),
    );
    const rejected = await Promise.race(requests);
    assert.equal(rejected.status, 429);
    assert.equal(calls, 2);
    releases.forEach((release) => release());
    const results = await Promise.all(requests);
    assert.deepEqual(results.map((r) => r.status).sort(), [200, 200, 429]);
  } finally {
    releases.forEach((release) => release());
    globalThis.fetch = originalFetch;
    if (key === undefined) delete process.env.OPENAI_API_KEY;
    else process.env.OPENAI_API_KEY = key;
    if (model === undefined) delete process.env.OPENAI_MODEL;
    else process.env.OPENAI_MODEL = model;
  }
});
test("hallucinated source ids and malformed provider payloads fail closed", async () => {
  const originalFetch = globalThis.fetch;
  const key = process.env.OPENAI_API_KEY;
  const model = process.env.OPENAI_MODEL;
  process.env.OPENAI_API_KEY = "test-only";
  process.env.OPENAI_MODEL = "test-only";
  try {
    globalThis.fetch = async () =>
      response({
        title: "초안",
        sections: [
          { heading: "해석", body: "근거 없는 해석", sourceIds: ["invented"] },
          { heading: "지원", body: "근거 없는 지원", sourceIds: ["invented"] },
        ],
        notes: [],
      });
    assert.equal(
      (
        await POST(
          request({
            task: "document",
            payload: {
              kind: "관찰일지",
              start: "2026-09-11",
              end: "2026-09-11",
              sources: [source],
            },
          }),
        )
      ).status,
      502,
    );
    globalThis.fetch = async () => response({ headings: 42 });
    assert.equal(
      (await POST(request({ task: "template", payload: { text: "분석할 실제 원문입니다." } })))
        .status,
      502,
    );
    globalThis.fetch = async () =>
      response({
        title: "주간",
        sections: [{ heading: "월요일", body: "하루만 있는 미완성 계획", sourceIds: [] }],
        notes: [],
      });
    assert.equal(
      (
        await POST(
          request({
            task: "plan",
            payload: {
              type: "weekly",
              age: "4",
              memo: "",
              period: { annual: { year: 2026 }, weekly: { month: 9, week: 1 } },
            },
          }),
        )
      ).status,
      502,
    );
  } finally {
    globalThis.fetch = originalFetch;
    if (key === undefined) delete process.env.OPENAI_API_KEY;
    else process.env.OPENAI_API_KEY = key;
    if (model === undefined) delete process.env.OPENAI_MODEL;
    else process.env.OPENAI_MODEL = model;
  }
});
