/** 관찰 기록 화면이 쓰는 서버 접근 경계. fetch 와 브라우저 저장소는 스텁이다. */
import { test } from "node:test";
import assert from "node:assert/strict";
import { registerHooks } from "node:module";
import { existsSync, readFileSync } from "node:fs";
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

const records = await import("../lib/api/records.ts");
const { ApiError, isUnauthenticated } = await import("../lib/api/client.ts");
const { API_STORAGE_CONTEXT } = await import("../lib/api/storage-context.ts");

const EMAIL = "fixture@example.com";
const TOKEN = "test-token";
const linksKey = `saessak.apiLinks.v1:${API_STORAGE_CONTEXT}:${encodeURIComponent(EMAIL)}`;
const accountKey = `saessak.demoAccount:${encodeURIComponent(EMAIL)}`;
const LINKS = JSON.stringify({
  classes: { "class-abc": { id: 3, signature: "" } },
  children: { "api-child-8": 8 },
});

const DTO = {
  id: 12,
  class_id: 3,
  class_name: "햇살반",
  child_id: 8,
  child_name: "박서준",
  child_code: "민준",
  date: "2026-09-22",
  domain: "자연탐구",
  context: "바깥놀이",
  fact: "화단 앞에 앉아 개미가 줄지어 가는 것을 3분 동안 바라보았다.",
  created_at: "2026-09-22T10:31:00+09:00",
};
const INPUT = {
  date: "2026-09-22",
  domain: "자연탐구",
  context: "바깥놀이",
  fact: DTO.fact,
};

/** 로그인한 브라우저. `writes` 로 저장소 쓰기를 센다. */
function browser(links = LINKS) {
  const values = new Map([
    [accountKey, JSON.stringify({ name: "선생님", email: EMAIL })],
    [linksKey, links],
  ]);
  const writes = [];
  const local = {
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => {
      writes.push(key);
      values.set(key, value);
    },
    removeItem: (key) => values.delete(key),
  };
  const session = new Map([
    ["saessak.demoSession", "active"],
    ["saessak.accountEmail", EMAIL],
    ["saessak.authToken", TOKEN],
  ]);
  const sessionStorage = {
    getItem: (key) => session.get(key) ?? null,
    setItem: (key, value) => session.set(key, value),
    removeItem: (key) => session.delete(key),
  };
  globalThis.localStorage = local;
  globalThis.sessionStorage = sessionStorage;
  globalThis.window = { localStorage: local, sessionStorage };
  return writes;
}

/** 응답을 정해 두고 오간 요청을 모은다. 돌려주는 함수로 원래 fetch 를 되돌린다. */
function serve(reply) {
  const calls = [];
  const original = globalThis.fetch;
  globalThis.fetch = async (url, options = {}) => {
    calls.push({
      url: String(url),
      method: options.method ?? "GET",
      body: options.body ? JSON.parse(options.body) : undefined,
      auth: new Headers(options.headers).get("Authorization"),
    });
    return reply(calls.length);
  };
  return { calls, restore: () => (globalThis.fetch = original) };
}
const json = (body, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
const fail = (code, status) =>
  json({ error: { code, message: "요청을 확인해주세요.", fields: [] } }, status);

test("목록은 서버에서 읽고 화면 id 로 옮긴다", async () => {
  const writes = browser();
  const { calls, restore } = serve(() => json({ items: [DTO] }));
  let list;
  try {
    list = await records.listRecords();
  } finally {
    restore();
  }

  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, "/api/observations");
  assert.equal(calls[0].method, "GET");
  assert.equal(calls[0].auth, "Bearer " + TOKEN);
  assert.equal(list.length, 1);
  assert.equal(list[0].id, "observation:12");
  assert.equal(list[0].classId, "class-abc");
  assert.equal(list[0].childId, "api-child-8");
  assert.equal(list[0].childName, "박서준");
  assert.deepEqual(writes, []);
});

test("기록이 없으면 빈 목록이다", async () => {
  browser();
  const { restore } = serve(() => json({ items: [] }));
  try {
    assert.deepEqual(await records.listRecords(), []);
  } finally {
    restore();
  }
});

test("목록 조회 실패는 그대로 올라온다", async () => {
  browser();
  const { restore } = serve(() => fail("NOT_FOUND", 500));
  try {
    await assert.rejects(records.listRecords(), (e) => e instanceof ApiError && e.status === 500);
  } finally {
    restore();
  }
});

test("401 은 로그인 문제로 갈라 볼 수 있다", async () => {
  browser();
  const { restore } = serve(() => fail("UNAUTHENTICATED", 401));
  try {
    await assert.rejects(records.listRecords(), (e) => isUnauthenticated(e));
  } finally {
    restore();
  }
});

test("매핑이 없는 서버 기록은 화면 id 를 지어내지 않는다", async () => {
  browser(JSON.stringify({ classes: {}, children: {} }));
  const { restore } = serve(() => json({ items: [DTO] }));
  let list;
  try {
    list = await records.listRecords();
  } finally {
    restore();
  }

  assert.equal(list[0].classId, "server-class:3");
  assert.equal(list[0].childId, "server-child:8");
  assert.notEqual(list[0].classId, "class-3");
});

test("등록은 화면 id 를 서버 id 로 바꿔 여섯 칸만 보낸다", async () => {
  const writes = browser();
  const { calls, restore } = serve(() => json(DTO, 201));
  let saved;
  try {
    saved = await records.addRecord({ ...INPUT, classId: "class-abc", childId: "api-child-8" });
  } finally {
    restore();
  }

  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, "/api/observations");
  assert.equal(calls[0].method, "POST");
  assert.deepEqual(Object.keys(calls[0].body).sort(), [
    "child_id",
    "class_id",
    "context",
    "date",
    "domain",
    "fact",
  ]);
  assert.equal(calls[0].body.class_id, 3);
  assert.equal(calls[0].body.child_id, 8);
  assert.equal(saved.classId, "class-abc");
  assert.deepEqual(writes, []);
});

test("매핑을 못 찾으면 등록 요청 자체를 보내지 않는다", async () => {
  browser();
  const { calls, restore } = serve(() => json(DTO, 201));
  try {
    await assert.rejects(
      records.addRecord({ ...INPUT, classId: "class-없음", childId: "api-child-8" }),
      (e) => e.message === records.UNMAPPED,
    );
    await assert.rejects(
      records.addRecord({ ...INPUT, classId: "class-abc", childId: "child-없음" }),
      (e) => e.message === records.UNMAPPED,
    );
  } finally {
    restore();
  }
  assert.equal(calls.length, 0);
});

test("수정은 서버 id 로 네 칸만 보낸다", async () => {
  browser();
  const { calls, restore } = serve(() => json(DTO));
  try {
    await records.editRecord("observation:12", { ...INPUT, fact: "고친 내용" });
  } finally {
    restore();
  }

  assert.equal(calls[0].url, "/api/observations/12");
  assert.equal(calls[0].method, "PUT");
  assert.deepEqual(Object.keys(calls[0].body).sort(), ["context", "date", "domain", "fact"]);
});

test("수정은 반·아동을 보내지 않는다", async () => {
  browser();
  const { calls, restore } = serve(() => json(DTO));
  try {
    // 화면 객체를 통째로 넘기는 실수를 재현한다.
    await records.editRecord("observation:12", {
      ...INPUT,
      classId: "class-abc",
      childId: "api-child-8",
      class_id: 3,
      child_id: 8,
      childName: "박서준",
      childCode: "민준",
      serverClassId: 3,
      serverChildId: 8,
    });
  } finally {
    restore();
  }
  assert.deepEqual(Object.keys(calls[0].body).sort(), ["context", "date", "domain", "fact"]);
});

test("서버에서 오지 않은 id 는 수정·삭제 요청을 보내지 않는다", async () => {
  browser();
  const { calls, restore } = serve(() => json(DTO));
  try {
    for (const id of ["local-uuid", "observation:", "observation:0", "12"]) {
      await assert.rejects(records.editRecord(id, INPUT), (e) => e.message === records.UNMAPPED);
      await assert.rejects(records.removeRecord(id), (e) => e.message === records.UNMAPPED);
    }
  } finally {
    restore();
  }
  assert.equal(calls.length, 0);
});

test("삭제는 204 를 본문 없이 처리한다", async () => {
  const writes = browser();
  const { calls, restore } = serve(() => new Response(null, { status: 204 }));
  try {
    assert.equal(await records.removeRecord("observation:12"), undefined);
  } finally {
    restore();
  }

  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, "/api/observations/12");
  assert.equal(calls[0].method, "DELETE");
  assert.deepEqual(writes, []);
});

test("등록·수정·삭제가 실패하면 성공한 척하지 않는다", async () => {
  browser();
  const { restore } = serve(() => fail("VALIDATION_FAILED", 422));
  try {
    for (const run of [
      () => records.addRecord({ ...INPUT, classId: "class-abc", childId: "api-child-8" }),
      () => records.editRecord("observation:12", INPUT),
      () => records.removeRecord("observation:12"),
    ])
      await assert.rejects(run(), (e) => e instanceof ApiError && e.status === 422);
  } finally {
    restore();
  }
});

test("서버 기록을 브라우저 저장소에 남기지 않는다", async () => {
  const writes = browser();
  const { restore } = serve((n) => (n === 1 ? json({ items: [DTO] }) : json(DTO, 201)));
  try {
    await records.listRecords();
    await records.addRecord({ ...INPUT, classId: "class-abc", childId: "api-child-8" });
  } finally {
    restore();
  }
  assert.deepEqual(writes, []);
});

test("화면이 관찰 기록을 localStorage 에서 읽거나 쓰지 않는다", () => {
  const source = readFileSync(
    new URL("../components/workspace/RecordsPage.tsx", import.meta.url),
    "utf8",
  );

  for (const banned of ["useWorkspace", "invalidateDependents", "localStorage", "updateWorkspace"])
    assert.equal(source.includes(banned), false, banned);
  for (const used of ["listRecords", "addRecord", "editRecord", "removeRecord"])
    assert.equal(source.includes(used), true, used);
});

// 화면은 JSX 라 이 테스트 환경에서 렌더할 수 없다. 아래 셋은 소스로 확인한다.
const page = () =>
  readFileSync(new URL("../components/workspace/RecordsPage.tsx", import.meta.url), "utf8");

test("요청 중에는 입력 칸과 버튼이 함께 잠긴다", () => {
  const source = page();
  const open = source.indexOf("<fieldset");
  const close = source.indexOf("</fieldset>");

  assert.ok(open > -1 && close > open, "폼을 감싸는 fieldset 이 있어야 한다");
  assert.match(source.slice(open, source.indexOf(">", open)), /disabled=\{pending\}/);
  // 보낸 뒤에도 고칠 수 있으면 화면과 서버가 어긋난다 — 입력 칸이 잠금 안에 있어야 한다.
  for (const control of ["<textarea", "<select", "<input\n", "수정 취소", "수정 저장"]) {
    const at = source.indexOf(control.replace("\\n", "\n"));
    assert.ok(at > open && at < close, control);
  }
});

test("늦게 온 옛 조회가 최신 목록을 덮지 않는다", () => {
  const source = page();
  // 조회마다 번호를 매기고, 최신 번호일 때만 화면을 바꾼다.
  assert.ok(source.includes("useRef"), "조회 번호를 담을 ref 가 있어야 한다");
  assert.ok(
    (source.match(/mine !== latest\.current/g) ?? []).length >= 4,
    "초기 조회와 재조회 모두 성공·실패 양쪽에서 최신 여부를 봐야 한다",
  );
});

test("연결되지 않은 문서 진입점을 내보내지 않는다", () => {
  const source = page();
  // 문서 화면은 아직 서버 기록을 읽지 못한다.
  assert.equal(source.includes("/documents?record="), false);
  assert.equal(source.includes("문서로 작성"), false);
  assert.equal(source.includes("초안으로 이어갈 수 있어요"), false);
});
