/** local ↔ server id 매핑과 관찰 기록 변환 경계. 브라우저 저장소는 스텁이다. */
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

const { classServerId, childServerId, classLocalId, childLocalId } =
  await import("../lib/api/onboarding.ts");
const { toLocalObservation } = await import("../lib/api/observation-ids.ts");
const { API_STORAGE_CONTEXT } = await import("../lib/api/storage-context.ts");

const EMAIL = "fixture@example.com";
const OTHER_EMAIL = "other@example.com";
const OTHER_CONTEXT = API_STORAGE_CONTEXT === "backend" ? "development-mock" : "backend";
const TOKEN_KEY = "saessak.authToken";
const SESSION_KEY = "saessak.demoSession";
const EMAIL_KEY = "saessak.accountEmail";

const linksKey = (email, context = API_STORAGE_CONTEXT) =>
  `saessak.apiLinks.v1:${context}:${encodeURIComponent(email)}`;
const accountKey = (email) => `saessak.demoAccount:${encodeURIComponent(email)}`;
const accountRecord = (email) => JSON.stringify({ name: "선생님", email });
const links = (classes, children) => JSON.stringify({ classes, children });

const LINKS = links({ "class-abc": { id: 3, signature: "" } }, { "api-child-8": 8 });

/**
 * 로그인한 브라우저 하나.
 *
 * `spy` 로 저장소 쓰기·지우기를 센다 — 조회가 세션을 건드리는지 여기서 드러난다.
 */
function browser({ email = EMAIL, entries = [], account = true, throwOnRead = false } = {}) {
  const local = new Map(
    account ? [[accountKey(email), accountRecord(email)], ...entries] : entries,
  );
  const session = new Map([
    [SESSION_KEY, "active"],
    [EMAIL_KEY, email],
    [TOKEN_KEY, "test-token"],
  ]);
  const spy = { localSet: 0, localRemove: 0, sessionSet: 0, sessionRemove: 0 };
  const localStorage = {
    getItem: (key) => {
      if (throwOnRead) throw new Error("저장소를 쓸 수 없어요.");
      return local.get(key) ?? null;
    },
    setItem: (key, value) => {
      spy.localSet += 1;
      local.set(key, value);
    },
    removeItem: (key) => {
      spy.localRemove += 1;
      local.delete(key);
    },
  };
  const sessionStorage = {
    getItem: (key) => session.get(key) ?? null,
    setItem: (key, value) => {
      spy.sessionSet += 1;
      session.set(key, value);
    },
    removeItem: (key) => {
      spy.sessionRemove += 1;
      session.delete(key);
    },
  };
  globalThis.localStorage = localStorage;
  globalThis.sessionStorage = sessionStorage;
  globalThis.window = { localStorage, sessionStorage };
  return { spy, session };
}

const signedIn = (entries = [[linksKey(EMAIL), LINKS]]) => browser({ entries });
/** resolver 넷을 한 번씩 부른다. 반환값은 보지 않는다 — 부작용만 보는 테스트가 쓴다. */
function callAll() {
  classServerId("class-abc");
  childServerId("api-child-8");
  classLocalId(3);
  childLocalId(8);
}
const untouched = (spy) =>
  assert.deepEqual(spy, { localSet: 0, localRemove: 0, sessionSet: 0, sessionRemove: 0 });

test("화면 반 id 를 저장된 서버 id 로 바꾼다", () => {
  signedIn();
  assert.equal(classServerId("class-abc"), 3);
});

test("화면 아동 id 를 저장된 서버 id 로 바꾼다", () => {
  signedIn();
  assert.equal(childServerId("api-child-8"), 8);
});

test("서버 반 id 를 화면 id 로 되돌린다", () => {
  signedIn();
  assert.equal(classLocalId(3), "class-abc");
});

test("서버 아동 id 를 화면 id 로 되돌린다", () => {
  signedIn();
  assert.equal(childLocalId(8), "api-child-8");
});

test("매핑에 없으면 null 이다", () => {
  signedIn();
  assert.equal(classServerId("class-zzz"), null);
  assert.equal(childServerId("child-zzz"), null);
  assert.equal(classLocalId(99), null);
  assert.equal(childLocalId(99), null);
});

test("id 문자열에서 숫자를 뽑아내지 않는다", () => {
  signedIn();
  // "class-3" 은 매핑에 없다. 뒤의 3 을 서버 id 로 읽으면 남의 반을 가리킨다.
  assert.equal(classServerId("class-3"), null);
  assert.equal(childServerId("api-child-3"), null);
  assert.equal(classServerId("3"), null);
});

test("저장 내용이 깨져 있어도 값을 지어내지 않는다", () => {
  signedIn([[linksKey(EMAIL), "{"]]);
  assert.equal(classServerId("class-abc"), null);
  assert.equal(classLocalId(3), null);

  signedIn([[linksKey(EMAIL), links({ "class-abc": { id: "3" } }, { "api-child-8": "8" })]]);
  assert.equal(classServerId("class-abc"), null);
  assert.equal(childServerId("api-child-8"), null);
  assert.equal(classLocalId(3), null);
  assert.equal(childLocalId(8), null);
});

test("로그인하지 않았으면 null 이다", () => {
  const { spy } = signedIn();
  globalThis.sessionStorage.removeItem(SESSION_KEY);
  spy.sessionRemove = 0;
  assert.equal(classServerId("class-abc"), null);
  assert.equal(childLocalId(8), null);
});

test("다른 계정의 매핑을 읽지 않는다", () => {
  browser({ email: OTHER_EMAIL, entries: [[linksKey(EMAIL), LINKS]] });
  assert.equal(classServerId("class-abc"), null);
  assert.equal(classLocalId(3), null);
});

test("API 환경이 다르면 매핑이 섞이지 않는다", () => {
  signedIn([[linksKey(EMAIL, OTHER_CONTEXT), LINKS]]);
  assert.equal(classServerId("class-abc"), null);
  assert.equal(childLocalId(8), null);
});

test("조회는 저장소를 고치지도 네트워크를 타지도 않는다", () => {
  const { spy } = signedIn();
  const original = globalThis.fetch;
  let calls = 0;
  globalThis.fetch = async () => {
    calls += 1;
    throw new Error("resolver 가 네트워크를 타면 안 된다");
  };
  try {
    callAll();
    classServerId("class-zzz");
  } finally {
    globalThis.fetch = original;
  }
  assert.equal(calls, 0);
  untouched(spy);
});

test("계정 기록이 없어도 로그인 상태를 지우지 않는다", () => {
  const { spy, session } = browser({ account: false, entries: [[linksKey(EMAIL), LINKS]] });

  assert.equal(classLocalId(3), null);
  callAll();

  untouched(spy);
  assert.equal(session.get(TOKEN_KEY), "test-token");
  assert.equal(session.get(SESSION_KEY), "active");
  assert.equal(session.get(EMAIL_KEY), EMAIL);
});

test("저장소 읽기가 실패해도 로그인 상태를 지우지 않는다", () => {
  const { spy, session } = browser({ throwOnRead: true });

  assert.equal(classServerId("class-abc"), null);
  callAll();

  untouched(spy);
  assert.equal(session.get(TOKEN_KEY), "test-token");
  assert.equal(session.get(SESSION_KEY), "active");
  assert.equal(session.get(EMAIL_KEY), EMAIL);
});

test("매핑이 배열이면 자리 번호를 화면 id 로 쓰지 않는다", () => {
  signedIn([[linksKey(EMAIL), links([{ id: 3 }], {})]]);
  assert.equal(classLocalId(3), null);
  assert.equal(classServerId("0"), null);

  signedIn([[linksKey(EMAIL), links({}, [8])]]);
  assert.equal(childLocalId(8), null);
  assert.equal(childServerId("0"), null);
});

test("매핑이 문자열이면 length 를 서버 id 로 읽지 않는다", () => {
  signedIn([[linksKey(EMAIL), links("oops", "oops")]]);
  assert.equal(classServerId("length"), null);
  assert.equal(childServerId("length"), null);
  assert.equal(classLocalId(4), null);
  assert.equal(childLocalId(4), null);
});

test("매핑 자리에 null 이나 숫자가 있으면 없는 것으로 본다", () => {
  for (const raw of [links(null, null), links(3, 8), '{"classes":{}}', "{}"]) {
    signedIn([[linksKey(EMAIL), raw]]);
    assert.equal(classServerId("class-abc"), null, raw);
    assert.equal(childServerId("api-child-8"), null, raw);
    assert.equal(classLocalId(3), null, raw);
    assert.equal(childLocalId(8), null, raw);
  }
});

test("prototype 에 있는 property 를 매핑으로 읽지 않는다", () => {
  signedIn([[linksKey(EMAIL), '{"classes":{"__proto__":{"stolen":{"id":3}}},"children":{}}']]);
  assert.equal(classServerId("stolen"), null);
  assert.equal(classServerId("__proto__"), null);
  assert.equal(classLocalId(3), null);

  signedIn();
  assert.equal(classServerId("constructor"), null);
  assert.equal(classServerId("toString"), null);
  assert.equal(childServerId("hasOwnProperty"), null);
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

test("서버 관찰 기록의 반·아동을 화면 id 로 옮긴다", () => {
  signedIn();
  const o = toLocalObservation(DTO);

  assert.equal(o.classId, "class-abc");
  assert.equal(o.childId, "api-child-8");
  // 서버 정수 id 와 나머지 칸은 그대로다.
  assert.equal(o.serverClassId, 3);
  assert.equal(o.serverChildId, 8);
  assert.equal(o.id, "observation:12");
  assert.equal(o.childName, "박서준");
  assert.equal(o.childCode, "민준");
  assert.equal(o.fact, DTO.fact);
});

test("매핑이 없으면 화면 id 를 지어내지 않는다", () => {
  signedIn([[linksKey(EMAIL), links({}, {})]]);
  const o = toLocalObservation(DTO);

  assert.equal(o.classId, "server-class:3");
  assert.equal(o.childId, "server-child:8");
  assert.notEqual(o.classId, "class-3");
  assert.notEqual(o.childId, "child-8");
});

test("매핑이 깨져 있어도 화면 id 를 지어내지 않는다", () => {
  for (const raw of [links([{ id: 3 }], [8]), links("oops", "oops"), "{", links(null, null)]) {
    signedIn([[linksKey(EMAIL), raw]]);
    const o = toLocalObservation(DTO);
    assert.equal(o.classId, "server-class:3", raw);
    assert.equal(o.childId, "server-child:8", raw);
  }
});
