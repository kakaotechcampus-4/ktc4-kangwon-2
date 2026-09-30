/** 관찰 기록 API ↔ 화면 model 변환 (docs/api-spec.md §10). fetch 는 스텁이다. */
import { test } from "node:test";
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

const observations = await import("../lib/api/observations.ts");
const { ApiError, isUnauthenticated, isApiNotFound } = await import("../lib/api/client.ts");
const { statusFor } = await import("../msw/scenarios.ts");

// child_name 은 아동 실명, child_code 는 LLM 에 나가는 대체 코드다.
// 테스트 데이터에는 실제 아동 실명을 쓰지 않는다 (ADR-004).
const DTO = {
  id: 12,
  class_id: 1,
  class_name: "햇살반",
  child_id: 5,
  child_name: "박서준",
  child_code: "민준",
  date: "2026-09-22",
  domain: "자연탐구",
  context: "바깥놀이",
  fact: "화단 앞에 앉아 개미가 줄지어 가는 것을 3분 동안 바라보았다.",
  created_at: "2026-09-22T10:31:00+09:00",
};

test("snake_case 응답을 화면 model 의 camelCase 로 옮긴다", () => {
  const o = observations.toObservation(DTO);

  assert.equal(o.className, "햇살반");
  assert.equal(o.domain, "자연탐구");
  assert.equal(o.context, "바깥놀이");
  assert.equal(o.fact, DTO.fact);
  // date 는 날짜만, created_at 은 시각까지. 서버 문자열을 그대로 쓴다.
  assert.equal(o.date, "2026-09-22");
  assert.equal(o.createdAt, "2026-09-22T10:31:00+09:00");
});

test("실명과 대체 코드를 각각 보존한다", () => {
  const o = observations.toObservation(DTO);

  assert.equal(o.childName, "박서준");
  assert.equal(o.childCode, "민준");
  assert.notEqual(o.childName, o.childCode);
});

test("화면 model 의 칸을 빠짐없이 채운다", () => {
  // 저장 가능 여부가 아니라 반환 모양만 본다.
  const o = observations.toObservation(DTO);

  assert.deepEqual(Object.keys(o).sort(), [
    "childCode",
    "childId",
    "childName",
    "classId",
    "className",
    "context",
    "createdAt",
    "date",
    "domain",
    "fact",
    "id",
    "serverChildId",
    "serverClassId",
    "serverId",
  ]);
  for (const key of [
    "id",
    "classId",
    "className",
    "childId",
    "childName",
    "date",
    "domain",
    "context",
    "fact",
    "createdAt",
  ])
    assert.equal(typeof o[key], "string", key);
});

test("서버 정수 id 를 접두사로 감싸고 그대로 되찾는다", () => {
  const o = observations.toObservation(DTO);

  assert.equal(o.id, "observation:12");
  assert.equal(observations.observationServerId(o.id), 12);
  assert.equal(observations.observationLocalId(7), "observation:7");
  // 원래 정수도 같이 넘긴다 — API 를 다시 부를 때 파싱하지 않아도 된다.
  assert.equal(o.serverId, 12);
  assert.equal(o.serverClassId, 1);
  assert.equal(o.serverChildId, 5);
});

test("서버 id 와 화면 id 의 접두사가 서로 다르다", () => {
  const o = observations.toObservation(DTO);

  assert.equal(o.classId, "server-class:1");
  assert.equal(o.childId, "server-child:5");
  // 온보딩 로컬 id 는 class-1 · child-1 꼴이다.
  assert.notEqual(o.classId, "class-1");
  assert.notEqual(o.childId, "child-5");
  // 관찰 12번과 문서 12번이 같은 문자열이 되지 않는다.
  assert.notEqual(o.id, String(DTO.id));
  assert.notEqual(o.classId, o.childId);
});

test("서버에서 오지 않은 id 는 서버 id 로 오해하지 않는다", () => {
  assert.equal(observations.observationServerId(crypto.randomUUID()), null);
  assert.equal(observations.observationServerId(""), null);
  assert.equal(observations.observationServerId("12"), null);
  assert.equal(observations.observationServerId("document:12"), null);
  assert.equal(observations.observationServerId("observation:"), null);
  assert.equal(observations.observationServerId("observation:0"), null);
  assert.equal(observations.observationServerId("observation: 12 "), null);
  assert.equal(observations.observationServerId("observation:1e3"), null);
  assert.equal(observations.observationServerId("observation:-1"), null);
});

test("Number 가 값을 바꾸는 큰 id 는 거절한다", () => {
  assert.equal(observations.observationServerId("observation:9007199254740991"), 9007199254740991);
  assert.equal(observations.observationServerId("observation:9007199254740993"), null);
  assert.equal(observations.observationServerId("observation:" + "9".repeat(400)), null);
});

test("context 를 자르지 않는다", async () => {
  // 화면 입력은 200자, 서버 컬럼은 50자다. 초과는 서버가 422 로 알린다.
  const long = "가".repeat(200);
  const dto = { ...DTO, context: long };
  assert.equal(observations.toObservation(dto).context.length, 200);

  const calls = [];
  const original = globalThis.fetch;
  globalThis.fetch = async (url, options) => {
    calls.push({ url, options });
    return new Response(JSON.stringify(dto), {
      status: 201,
      headers: { "Content-Type": "application/json" },
    });
  };
  try {
    await observations.createObservation({
      class_id: 1,
      child_id: 5,
      date: "2026-09-22",
      domain: "자연탐구",
      context: long,
      fact: "관찰 내용",
    });
    assert.equal(JSON.parse(calls[0].options.body).context, long);
  } finally {
    globalThis.fetch = original;
  }
});

test("요청 URL 과 메서드가 §10 계약과 같다", async () => {
  const calls = [];
  const original = globalThis.fetch;
  globalThis.fetch = async (url, options) => {
    calls.push({ url, method: options?.method ?? "GET", body: options?.body });
    return new Response("{}", { status: 200, headers: { "Content-Type": "application/json" } });
  };
  try {
    await observations.getObservations();
    await observations.getObservations({
      class_id: 1,
      child_id: 5,
      from: "2026-09-01",
      to: "2026-09-30",
    });
    await observations.updateObservation(12, {
      date: "2026-09-22",
      domain: "자연탐구",
      context: "",
      fact: "고친 내용",
    });
  } finally {
    globalThis.fetch = original;
  }

  assert.equal(calls[0].url, "/api/observations");
  assert.equal(
    calls[1].url,
    "/api/observations?class_id=1&child_id=5&from=2026-09-01&to=2026-09-30",
  );
  assert.equal(calls[2].url, "/api/observations/12");
  assert.equal(calls[2].method, "PUT");
  // PUT 은 네 칸만 보낸다 — class_id · child_id 를 실으면 서버가 422 다.
  assert.deepEqual(Object.keys(JSON.parse(calls[2].body)).sort(), [
    "context",
    "date",
    "domain",
    "fact",
  ]);
});

test("PUT 은 여분 필드가 섞인 객체를 받아도 네 칸만 보낸다", async () => {
  // 타입은 런타임에 없다. 서버 응답 객체를 그대로 되보내는 실수를 재현한다.
  const whole = {
    date: "2026-09-23",
    domain: "사회관계",
    context: "자유놀이",
    fact: "고친 내용",
    id: 12,
    class_id: 1,
    child_id: 5,
    class_name: "햇살반",
    child_name: "박서준",
    child_code: "민준",
    created_at: "2026-09-22T10:31:00+09:00",
  };

  let sent;
  const original = globalThis.fetch;
  globalThis.fetch = async (url, options) => {
    sent = JSON.parse(options.body);
    return new Response("{}", { status: 200, headers: { "Content-Type": "application/json" } });
  };
  try {
    await observations.updateObservation(12, whole);
  } finally {
    globalThis.fetch = original;
  }

  assert.deepEqual(Object.keys(sent).sort(), ["context", "date", "domain", "fact"]);
  assert.deepEqual(sent, {
    date: "2026-09-23",
    domain: "사회관계",
    context: "자유놀이",
    fact: "고친 내용",
  });
});

test("등록은 여분 필드가 섞인 객체를 받아도 여섯 칸만 보낸다", async () => {
  // 서버 응답 객체를 그대로 다시 보내는 실수를 재현한다.
  const whole = { ...DTO, extra: "보내면 안 되는 값" };

  let sent;
  const original = globalThis.fetch;
  globalThis.fetch = async (url, options) => {
    sent = JSON.parse(options.body);
    return new Response(JSON.stringify(DTO), {
      status: 201,
      headers: { "Content-Type": "application/json" },
    });
  };
  try {
    await observations.createObservation(whole);
  } finally {
    globalThis.fetch = original;
  }

  assert.deepEqual(Object.keys(sent).sort(), [
    "child_id",
    "class_id",
    "context",
    "date",
    "domain",
    "fact",
  ]);
  assert.deepEqual(sent, {
    class_id: 1,
    child_id: 5,
    date: "2026-09-22",
    domain: "자연탐구",
    context: "바깥놀이",
    fact: DTO.fact,
  });
});

test("삭제는 204 No Content 를 본문 없이 처리한다", async () => {
  const calls = [];
  const original = globalThis.fetch;
  globalThis.fetch = async (url, options) => {
    calls.push({ url, method: options?.method });
    return new Response(null, { status: 204 });
  };
  try {
    assert.equal(await observations.deleteObservation(12), undefined);
  } finally {
    globalThis.fetch = original;
  }

  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, "/api/observations/12");
  assert.equal(calls[0].method, "DELETE");
});

test("401 UNAUTHENTICATED 를 404 와 갈라 본다", () => {
  const unauth = new ApiError(401, {
    error: { code: "UNAUTHENTICATED", message: "로그인이 필요합니다.", fields: [] },
  });
  const missing = new ApiError(404, {
    error: { code: "NOT_FOUND", message: "대상을 찾을 수 없습니다.", fields: [] },
  });

  assert.equal(isUnauthenticated(unauth), true);
  assert.equal(isApiNotFound(unauth), false);
  assert.equal(isUnauthenticated(missing), false);
  assert.equal(isApiNotFound(missing), true);
  // 코드 없는 401 은 계약 응답이 아니다.
  assert.equal(isUnauthenticated(new ApiError(401, "<html>")), false);
  assert.equal(isUnauthenticated(new Error("network")), false);
});

test("새로 넣은 에러 코드의 status 가 계약 표와 같다", () => {
  assert.equal(statusFor.UNAUTHENTICATED, 401);
  assert.equal(statusFor.ALREADY_CONFIRMED, 409);
});
