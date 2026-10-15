/**
 * 서버에만 있는 반을 목록에 들이는지 본다 (§1-1 초대 · 기기 변경).
 *
 * **왜 이 테스트가 있나.** 반 목록이 브라우저 저장소에서만 나오면, 초대받은 교사와
 * 기기를 바꾼 교사에게 반이 하나도 안 보인다. 서버에는 멀쩡히 있는데도.
 *
 * 그리고 들일 때 **서명을 같이 계산해 넣어야 한다.** 안 넣으면 교사가 나중에 반 정보를
 * 고칠 때 `syncClass` 의 서명 비교가 어긋나서 **같은 반이 서버에 하나 더 만들어진다.**
 * 마지막 테스트가 그 자리를 지킨다.
 */
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

const { setupServer } = await import("msw/node");
const { http, HttpResponse } = await import("msw");
const { fixtureAccount, fixtureKey, fixtureSession } = await import("./auth-fixture.mjs");
const onboarding = await import("../lib/api/onboarding.ts");

const server = setupServer();
server.listen({ onUnhandledRequest: "error" });

// lib/api 는 상대 경로로 부른다. 테스트에는 주소 기준이 없어 붙여 준다.
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
  const sessionValues = new Map(
    ["saessak.demoSession", "saessak.accountEmail"].map((k) => [k, session.getItem(k)]),
  );
  globalThis.sessionStorage = {
    getItem: (k) => sessionValues.get(k) ?? null,
    setItem: (k, v) => sessionValues.set(k, v),
    removeItem: (k) => sessionValues.delete(k),
  };
  globalThis.window = Object.assign(new EventTarget(), {
    localStorage: storage,
    sessionStorage,
    location: { search: "" },
  });
  keys = values.keys();
  return values;
}

/** onboarding.ts 가 쓰는 연결 저장 키. 계정 접두사가 붙는다. */
function linksKey() {
  return [...keys].find((k) => k.includes("apiLinks")) ?? "";
}
let keys = [];

const CLASS = {
  id: 7,
  center_id: 3,
  name: "햇살반",
  school_year: 2026,
  age_min: 3,
  age_max: 5,
  child_count: 18,
  teacher_name: "김선생",
  consent_confirmed_at: "2026-10-01T00:00:00Z",
  created_at: "2026-10-01T00:00:00Z",
};

/** 서버 한 대. 요청을 모아 둬서 반이 또 만들어지는지 볼 수 있다. */
function api({ center_id = 3, classes = [CLASS], children = [] } = {}) {
  const seen = [];
  server.use(
    http.get("*/api/auth/me", () => HttpResponse.json({ id: 1, email: "t@x.kr", center_id })),
    http.get("*/api/centers/:id/classes", () => HttpResponse.json({ items: classes })),
    http.get("*/api/classes/:id/children", () => HttpResponse.json({ items: children })),
    http.post("*/api/centers", () =>
      HttpResponse.json({ id: 3, name: "테스트원" }, { status: 201 }),
    ),
    http.post("*/api/centers/:id/classes", async ({ request }) => {
      seen.push(await request.json());
      return HttpResponse.json({ ...CLASS, id: 99 }, { status: 201 });
    }),
  );
  server.events.removeAllListeners("request:start");
  return seen;
}

test("서버에만 있는 반을 들인다 — 저장소가 비어 있어도 보인다", async () => {
  browser();
  api();
  const adopted = await onboarding.adoptServerClasses([]);
  assert.equal(adopted.length, 1);
  assert.equal(adopted[0].className, "햇살반");
  assert.equal(adopted[0].teacherName, "김선생");
  assert.equal(adopted[0].currentChildCount, 18);
  // 동의는 서버의 consent_confirmed_at 이 정한다 (§2)
  assert.equal(adopted[0].guardianConsent, true);
});

test("연령을 범위 그대로 담는다", async () => {
  browser();
  api({ classes: [{ ...CLASS, age_min: 4, age_max: 5 }] });
  const [adopted] = await onboarding.adoptServerClasses([]);
  assert.deepEqual(adopted.selectedAges, [4, 5]);
});

test("아동 명단도 같이 받아온다", async () => {
  browser();
  api({ children: [{ id: 11, class_id: 7, name: "하린", code: "민준" }] });
  const [adopted] = await onboarding.adoptServerClasses([]);
  assert.equal(adopted.children.length, 1);
  assert.equal(adopted.children[0].name, "하린");
});

test("원이 없는 교사에게는 빈 목록", async () => {
  browser();
  api({ center_id: null });
  assert.deepEqual(await onboarding.adoptServerClasses([]), []);
});

test("이미 로컬에 있는 반은 두 번 들이지 않는다", async () => {
  const values = browser();
  api();
  const first = await onboarding.adoptServerClasses([]);
  assert.equal(first.length, 1);
  // 두 번째 호출은 같은 반을 다시 들이지 않는다 — 화면에 반이 두 개로 보이면 안 된다
  const again = await onboarding.adoptServerClasses(first);
  assert.deepEqual(again, []);
  assert.ok(
    [...values.keys()].some((k) => k.includes("apiLinks")),
    "연결이 저장돼야 한다",
  );
});

test("★ 들인 반의 서명이 syncClass 가 계산하는 것과 같다", async () => {
  browser();
  api();
  const [adopted] = await onboarding.adoptServerClasses([]);
  // 저장된 연결의 서명이 syncClass 의 비교값과 같아야 한다.
  // 다르면 교사가 반 정보를 고칠 때 같은 반이 서버에 하나 더 만들어진다.
  const links = JSON.parse(
    localStorage.getItem([...Object.keys({})].length ? "" : linksKey()) ?? "{}",
  );
  const saved = links.classes?.[adopted.id];
  assert.ok(saved, "연결이 저장돼야 한다");
  assert.equal(saved.id, 7);
  assert.equal(
    saved.signature,
    JSON.stringify({
      name: "햇살반",
      teacher_name: "김선생",
      age_min: 3,
      age_max: 5,
      child_count: 18,
      consent_confirmed: true,
    }),
    "syncClass 가 만드는 payload 와 글자까지 같아야 한다",
  );
});

/**
 * **아직 안 막은 자리 — 알고 두는 것.**
 *
 * `syncCenter` 는 `links.center` 가 없으면 원을 새로 만들고 `links.classes` 를 통째로
 * 비운다("P0 has no center update endpoint"). 초대받은 교사는 `links.center` 가 없다.
 * 그 사람이 `syncClasses` 를 타면 원과 반과 아이가 전부 복제된다.
 *
 * **지금은 닿지 않는다** — `syncClasses` 를 부르는 곳이 온보딩뿐이고, 초대받은 교사는
 * 온보딩을 건너뛴다. 설정 화면은 `saveClassSettings`(브라우저 저장)만 한다.
 *
 * 제대로 막으려면 서버에 원 단건 조회(`GET /api/centers/{id}`)가 있어야 한다 —
 * 그래야 원 정보를 되읽어 `links.center` 의 서명을 복원할 수 있다. 지금은 없다.
 */
test("초대받은 교사에게는 원 연결이 없다 — syncClasses 를 타면 안 되는 상태다", async () => {
  browser();
  api();
  await onboarding.adoptServerClasses([]);
  const links = JSON.parse(localStorage.getItem(linksKey()) ?? "{}");
  assert.equal(links.center, undefined, "원 연결은 만들지 않는다 — 서버에 되읽을 길이 없다");
});
