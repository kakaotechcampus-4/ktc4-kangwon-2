/**
 * 온보딩 S1·S2·S3 가 실제 API 계층을 타는지 본다 (docs/api-spec.md §1 · §2 · §2-1).
 *
 * 화면 컴포넌트가 아니라 lib/api/onboarding 을 직접 돌린다 — 화면은 이 함수들만 부르고,
 * 여기서 확인할 것은 "어떤 URL 로 무엇을 보내고 응답의 무엇을 쓰는가" 다.
 * id 를 지어내지 않는다는 것을 보이려고 서버가 준 id 로 URL 이 만들어졌는지 직접 대조한다.
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
const { handlers } = await import("../msw/handlers.ts");
const { resetTestData, read } = await import("../msw/data/store.ts");
const { fixtureAccount, fixtureKey, fixtureSession } = await import("./auth-fixture.mjs");
const onboarding = await import("../lib/api/onboarding.ts");

const server = setupServer(...handlers);

/** tests/auth-fixture.mjs 의 계정으로 로그인한 브라우저를 흉내낸다 (msw-p0 과 같은 방식). */
function browser() {
  const values = new Map([[fixtureKey, fixtureAccount]]);
  const storage = {
    getItem: (k) => values.get(k) ?? null,
    setItem: (k, v) => values.set(k, v),
    removeItem: (k) => values.delete(k),
  };
  globalThis.localStorage = storage;
  globalThis.sessionStorage = fixtureSession();
  globalThis.window = { localStorage: storage, sessionStorage, location: { search: "" } };
}

/** 요청 URL·본문을 그대로 모아 둔다. 하드코딩한 id 가 섞이면 여기서 드러난다. */
function recorder() {
  const seen = [];
  const onRequest = async ({ request }) => {
    const clone = request.clone();
    const text = await clone.text();
    seen.push({
      method: request.method,
      path: new URL(request.url).pathname,
      body: text ? JSON.parse(text) : undefined,
    });
  };
  server.events.on("request:start", onRequest);
  return { seen, stop: () => server.events.removeListener("request:start", onRequest) };
}

const SETTINGS = {
  orgName: "새싹어린이집",
  directorName: "김원장",
  regionProvince: "충청북도",
  regionDistrict: "충주시",
  classes: [],
};
const classroom = (over = {}) => ({
  id: "local-class-1",
  className: "햇님반",
  teacherName: "김선생",
  ageGroup: "",
  selectedAges: [3, 5],
  currentChildCount: 18,
  guardianConsent: true,
  childrenSkipped: false,
  children: [],
  ...over,
});

async function start() {
  browser();
  resetTestData();
  server.listen({ onUnhandledRequest: "error" });
  const patched = globalThis.fetch;
  globalThis.fetch = (url, options) => patched(new URL(url, "http://localhost").href, options);
  return () => {
    globalThis.fetch = patched;
    server.resetHandlers();
    server.close();
  };
}

test("S1: 원 생성은 지역 두 칸을 그대로 보내고 응답 id 를 다음 단계에 넘긴다", async () => {
  const stop = await start();
  const rec = recorder();
  try {
    const centerId = await onboarding.syncCenter(SETTINGS);

    const post = rec.seen.find((r) => r.method === "POST" && r.path === "/api/centers");
    assert.ok(post, "POST /api/centers 를 불러야 한다");
    assert.deepEqual(post.body, {
      name: "새싹어린이집",
      director_name: "김원장",
      region_sido: "충청북도",
      region_sigungu: "충주시",
    });
    // 서버가 만든 id 를 그대로 쓴다.
    assert.equal(centerId, read().centers.at(-1).id);
    assert.equal(typeof centerId, "number");
  } finally {
    rec.stop();
    stop();
  }
});

test("S1: 생성이 실패하면 id 없이 던진다 — 화면이 다음 단계로 못 넘어간다", async () => {
  const stop = await start();
  try {
    server.use(
      http.post("*/api/centers", () =>
        HttpResponse.json(
          {
            error: {
              code: "VALIDATION_FAILED",
              message: "입력값을 확인해주세요.",
              fields: ["name"],
            },
          },
          { status: 422 },
        ),
      ),
    );
    await assert.rejects(onboarding.syncCenter(SETTINGS), (e) => e.status === 422);
    assert.equal(read().centers.length, 0);
  } finally {
    stop();
  }
});

test("S2: 반 생성은 실제 center_id 로 가고 연령을 범위로 보낸다", async () => {
  const stop = await start();
  const rec = recorder();
  try {
    // center 를 하나 먼저 만들어 두어 id 가 1 이 아니게 한다 — 하드코딩이면 여기서 어긋난다.
    await onboarding.syncCenter({ ...SETTINGS, orgName: "먼저 만든 원" });
    const centerId = await onboarding.syncCenter(SETTINGS);
    const classId = await onboarding.syncClass(SETTINGS, classroom());

    const post = rec.seen.find(
      (r) => r.method === "POST" && r.path === `/api/centers/${centerId}/classes`,
    );
    assert.ok(post, `POST /api/centers/${centerId}/classes 를 불러야 한다`);
    assert.deepEqual(post.body, {
      name: "햇님반",
      teacher_name: "김선생",
      age_min: 3,
      age_max: 5, // 만3·만5 선택 → 범위로 채운다 (§2)
      child_count: 18,
      consent_confirmed: true,
    });
    assert.equal("selected_ages" in post.body, false);
    assert.equal(classId, read().classes.at(-1).id);
    assert.notEqual(classId, centerId);
  } finally {
    rec.stop();
    stop();
  }
});

test("S2: 동의를 안 하면 consent_confirmed 가 false 로 나간다", async () => {
  const stop = await start();
  const rec = recorder();
  try {
    await onboarding.syncCenter(SETTINGS);
    await onboarding.syncClass(SETTINGS, classroom({ guardianConsent: false }));

    const post = rec.seen.findLast((r) => r.method === "POST" && r.path.endsWith("/classes"));
    assert.equal(post.body.consent_confirmed, false);
  } finally {
    rec.stop();
    stop();
  }
});

test("S2: 반 생성이 422 면 던진다 — S3 로 넘어가지 않는다", async () => {
  const stop = await start();
  try {
    await onboarding.syncCenter(SETTINGS);
    server.use(
      http.post("*/api/centers/:id/classes", () =>
        HttpResponse.json(
          {
            error: {
              code: "VALIDATION_FAILED",
              message: "입력값을 확인해주세요.",
              fields: ["age_min"],
            },
          },
          { status: 422 },
        ),
      ),
    );
    await assert.rejects(
      onboarding.syncClass(SETTINGS, classroom({ id: "local-class-422" })),
      (e) => e.status === 422,
    );
    assert.equal(read().classes.length, 0);
  } finally {
    stop();
  }
});

test("S3: 아동은 이름만 보내고 id·code 는 서버 값을 그대로 쓴다", async () => {
  const stop = await start();
  const rec = recorder();
  try {
    await onboarding.syncCenter(SETTINGS);
    const classId = await onboarding.syncClass(SETTINGS, classroom());
    const before = await onboarding.loadServerChildren(classroom());
    assert.deepEqual(before.children, []); // 빈 목록도 정상이다

    const child = await onboarding.addServerChild(classroom(), "이승석");

    const post = rec.seen.findLast((r) => r.method === "POST" && r.path.endsWith("/children"));
    assert.equal(post.path, `/api/classes/${classId}/children`);
    assert.deepEqual(post.body, { name: "이승석" }); // code 를 만들지도 보내지도 않는다
    const stored = read().children.at(-1);
    assert.equal(child.name, stored.name);
    assert.equal(child.code, stored.code); // 서버가 발급한 가명을 그대로 보관한다
    assert.ok(child.code);
    assert.equal(child.id, "api-child-" + stored.id); // Date.now() 임시 id 가 아니다
  } finally {
    rec.stop();
    stop();
  }
});

test("S3: 목록은 그 반의 서버 값으로 채운다", async () => {
  const stop = await start();
  try {
    await onboarding.syncCenter(SETTINGS);
    await onboarding.syncClass(SETTINGS, classroom());
    await onboarding.addServerChild(classroom(), "이승석");
    await onboarding.addServerChild(classroom(), "김하나");

    const loaded = await onboarding.loadServerChildren(classroom());

    assert.deepEqual(
      loaded.children.map((c) => c.name),
      ["이승석", "김하나"],
    );
    assert.deepEqual(
      loaded.children.map((c) => c.code),
      read().children.map((c) => c.code),
    );
  } finally {
    stop();
  }
});

test("S3: 삭제는 서버 id 로 부르고, 실패하면 목록에서 지우지 않는다", async () => {
  const stop = await start();
  const rec = recorder();
  try {
    await onboarding.syncCenter(SETTINGS);
    await onboarding.syncClass(SETTINGS, classroom());
    const child = await onboarding.addServerChild(classroom(), "이승석");
    const serverId = read().children.at(-1).id;

    // 실패하면 던진다 — 화면이 성공한 것처럼 지우면 안 된다.
    server.use(
      http.delete("*/api/children/:id", () =>
        HttpResponse.json(
          {
            error: { code: "NOT_FOUND", message: "아동을 찾을 수 없습니다.", fields: ["child_id"] },
          },
          { status: 404 },
        ),
      ),
    );
    await assert.rejects(onboarding.removeServerChild(child.id), (e) => e.status === 404);
    assert.equal(read().children.length, 1);

    server.resetHandlers();
    await onboarding.removeServerChild(child.id);

    const del = rec.seen.findLast((r) => r.method === "DELETE");
    assert.equal(del.path, `/api/children/${serverId}`);
    assert.equal(read().children.length, 0);
    assert.deepEqual((await onboarding.loadServerChildren(classroom())).children, []);
  } finally {
    rec.stop();
    stop();
  }
});

test("S2: 아동이 0명이어도 서버의 동의 시각으로 동의가 복원된다", async () => {
  const stop = await start();
  try {
    const settings = { ...SETTINGS, classes: [classroom()] };
    await onboarding.syncClasses(settings);
    // 아동을 한 명도 넣지 않는다 — 「나중에 입력할래요」로 건너뛴 반이다.
    assert.equal(read().children.length, 0);

    // 새로고침해서 로컬 체크가 비어 있는 상태로 다시 불러온다.
    const reloaded = { ...settings, classes: [classroom({ guardianConsent: false })] };
    const next = await onboarding.loadServerClasses(reloaded);

    assert.equal(next.classes[0].guardianConsent, true);
    assert.ok(read().classes[0].consent_confirmed_at);
  } finally {
    stop();
  }
});

test("S3: 동의 여부를 아동 수로 뒤집지 않는다", async () => {
  const stop = await start();
  try {
    const consented = classroom();
    const notConsented = classroom({
      id: "local-class-2",
      className: "달님반",
      guardianConsent: false,
    });
    const settings = { ...SETTINGS, classes: [consented, notConsented] };
    await onboarding.syncClasses(settings);

    // 동의했지만 아동이 0명 — 예전에는 여기서 false 로 뒤집혔다.
    assert.equal((await onboarding.loadServerChildren(consented)).guardianConsent, true);

    // 동의가 없는 반은 아동이 있어도 true 가 되지 않는다.
    await onboarding.addServerChild(notConsented, "가명아동");
    const loaded = await onboarding.loadServerChildren(notConsented);
    assert.equal(loaded.children.length, 1);
    assert.equal(loaded.guardianConsent, false);
  } finally {
    stop();
  }
});
