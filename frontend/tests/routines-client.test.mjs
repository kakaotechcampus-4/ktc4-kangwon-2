/**
 * 일과 기록 클라이언트 — S-J1 이 쓸 손잡이 (api-spec §10-1 · FR-402 · FR-403).
 *
 * **목업을 쓰지 않는다.** 서버가 이미 있어서 바로 잇는다. 여기서는 「어떤 요청을
 * 보내는가」만 본다.
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
const routines = await import("../lib/api/routines.ts");

const server = setupServer();
server.listen({ onUnhandledRequest: "error" });
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
  globalThis.sessionStorage = {
    getItem: (k) => session.getItem(k),
    setItem: () => {},
    removeItem: () => {},
  };
  globalThis.window = Object.assign(new EventTarget(), {
    localStorage: storage,
    sessionStorage,
    location: { search: "" },
  });
}

/** 서버 스키마가 받는 칸. 그 밖이 오면 422 다 (extra="forbid"). */
const PUT_FIELDS = new Set(["date", "position", "start", "end", "name", "plan", "execution"]);
const POST_FIELDS = new Set([...PUT_FIELDS, "class_id"]);

/** **목업을 서버만큼 깐깐하게 둔다.** 느슨하면 연동 때 한꺼번에 터진다 (frontend/CLAUDE.md). */
const reject = (body, allowed) => {
  const extra = Object.keys(body).filter((k) => !allowed.has(k));
  return extra.length
    ? HttpResponse.json(
        { error: { code: "VALIDATION_FAILED", message: "모르는 칸", fields: extra } },
        { status: 422 },
      )
    : null;
};

const row = (over = {}) => ({
  id: 1,
  class_id: 7,
  class_name: "햇살반",
  date: "2026-10-17",
  position: 0,
  start: "09:00",
  end: "09:20",
  name: "등원 및 맞이하기",
  plan: "",
  execution: "현관에서 맞았다.",
  created_at: "2026-10-17T00:00:00Z",
  ...over,
});

test("★ 하루치는 반을 붙여서 부른다 — 안 붙이면 다른 반이 섞인다", async () => {
  browser();
  let seen = "";
  server.use(
    http.get("*/api/routines", ({ request }) => {
      seen = new URL(request.url).search;
      return HttpResponse.json({ items: [row()] });
    }),
  );
  await routines.listRoutinesOfDay(7, "2026-10-17");
  assert.ok(seen.includes("class_id=7"), seen);
  assert.ok(seen.includes("from=2026-10-17") && seen.includes("to=2026-10-17"), seen);
});

test("★ 저장은 지우기를 먼저 한다 — 자리가 겹치지 않게", async () => {
  browser();
  const order = [];
  server.use(
    http.delete("*/api/routines/:id", ({ params }) => {
      order.push("delete" + params.id);
      return new HttpResponse(null, { status: 204 });
    }),
    http.post("*/api/routines", async ({ request }) => {
      const body = await request.json();
      const bad = reject(body, POST_FIELDS);
      if (bad) return bad;
      order.push("post");
      return HttpResponse.json(row({ ...body, id: 9 }), { status: 201 });
    }),
    http.put("*/api/routines/:id", async ({ request, params }) => {
      const body = await request.json();
      const bad = reject(body, PUT_FIELDS);
      if (bad) return bad;
      order.push("put" + params.id);
      return HttpResponse.json(row({ ...body, id: Number(params.id) }));
    }),
  );
  await routines.saveRoutines(
    7,
    [
      { id: 1, date: "2026-10-17", name: "등원" },
      { date: "2026-10-17", name: "오전 실내놀이" },
    ],
    [5],
  );
  assert.deepEqual(order, ["delete5", "put1", "post"]);
});

test("★ 새 줄에만 반을 보낸다 — PUT 에 반을 보내면 서버가 422 로 막는다", async () => {
  browser();
  let put = null;
  let post = null;
  server.use(
    http.put("*/api/routines/:id", async ({ request }) => {
      put = await request.json();
      const bad = reject(put, PUT_FIELDS);
      if (bad) return bad;
      return HttpResponse.json(row());
    }),
    http.post("*/api/routines", async ({ request }) => {
      post = await request.json();
      const bad = reject(post, POST_FIELDS);
      if (bad) return bad;
      return HttpResponse.json(row({ id: 9 }), { status: 201 });
    }),
  );
  await routines.saveRoutines(7, [
    { id: 1, date: "2026-10-17", name: "등원" },
    { date: "2026-10-17", name: "놀이" },
  ]);
  assert.ok(!("class_id" in put), "PUT 에 class_id 가 들어갔다");
  assert.ok(!("id" in put), "PUT 에 id 가 들어갔다 — 서버가 422 로 막는다");
  assert.equal(post.class_id, 7);
});

test("★ 자리를 안 주면 적은 순서가 자리가 된다", async () => {
  browser();
  const positions = [];
  server.use(
    http.post("*/api/routines", async ({ request }) => {
      positions.push((await request.json()).position);
      return HttpResponse.json(row({ id: 9 }), { status: 201 });
    }),
  );
  await routines.saveRoutines(7, [
    { date: "2026-10-17", name: "가" },
    { date: "2026-10-17", name: "나" },
    { date: "2026-10-17", name: "다" },
  ]);
  assert.deepEqual(positions, [0, 1, 2]);
});

test("★ 저장 배열을 드래그하면 과거 position 대신 바뀐 순서를 보낸다", async () => {
  browser();
  const sent = [];
  server.use(
    http.put("*/api/routines/:id", async ({ request, params }) => {
      const body = await request.json();
      sent.push([Number(params.id), body.position]);
      return HttpResponse.json(row({ ...body, id: Number(params.id) }));
    }),
  );
  await routines.saveRoutines(7, [
    { id: 3, date: "2026-10-17", name: "다", position: 2 },
    { id: 1, date: "2026-10-17", name: "가", position: 0 },
    { id: 2, date: "2026-10-17", name: "나", position: 1 },
  ]);
  assert.deepEqual(sent, [
    [3, 0],
    [1, 1],
    [2, 2],
  ]);
});

test("★ 어제 불러오기는 시간·이름만 가져온다 — 활동실행을 베끼면 위조다", async () => {
  browser();
  let asked = "";
  server.use(
    http.get("*/api/routines", ({ request }) => {
      asked = new URL(request.url).search;
      return HttpResponse.json({
        items: [row({ plan: "자동차 굴리기", execution: "블록으로 길을 만들었다." })],
      });
    }),
  );
  const copied = await routines.copyFromPreviousDay(7, "2026-10-17");
  assert.ok(asked.includes("from=2026-10-16"), asked);
  assert.deepEqual(copied, [
    {
      date: "2026-10-17",
      position: 0,
      start: "09:00",
      end: "09:20",
      name: "등원 및 맞이하기",
      plan: "",
      execution: "",
    },
  ]);
});

test("★ 저장이 하나라도 실패하면 거기서 멈춘다", async () => {
  browser();
  let posts = 0;
  server.use(
    http.post("*/api/routines", () => {
      posts += 1;
      return HttpResponse.json(
        {
          error: {
            code: "VALIDATION_FAILED",
            message: "일과 이름을 적어주세요.",
            fields: ["name"],
          },
        },
        { status: 422 },
      );
    }),
  );
  await assert.rejects(() =>
    routines.saveRoutines(7, [
      { date: "2026-10-17", name: "" },
      { date: "2026-10-17", name: "놀이" },
    ]),
  );
  assert.equal(posts, 1, "실패했는데 다음 줄을 계속 보냈다");
});

test("★ 하루 전 계산이 시간대에 흔들리지 않는다", async () => {
  const { previousDay } = routines;
  assert.equal(previousDay("2026-10-17"), "2026-10-16");
  assert.equal(previousDay("2026-01-01"), "2025-12-31"); // 해 넘김
  assert.equal(previousDay("2026-03-01"), "2026-02-28");
});
test("12 AM/PM과 5분 피커 값은 API의 24시간제로 정확하게 바뀐다", () => {
  assert.equal(routines.routineTimeFrom12("12", "00", "AM"), "00:00");
  assert.equal(routines.routineTimeFrom12("12", "00", "PM"), "12:00");
  assert.equal(routines.routineTimeFrom12("01", "05", "PM"), "13:05");
  assert.equal(routines.routineTimeFrom12("", "00", "AM"), "");
  assert.deepEqual(routines.routineTimeParts12("09:16"), {
    hour: "09",
    minute: "16",
    period: "AM",
  });
});

test("시간순 정렬은 시작·종료를 비교하고 동률·미입력에서 상대 순서를 유지한다", () => {
  const items = [
    row({ id: 1, start: null, end: null }),
    row({ id: 2, start: "09:00", end: "10:00" }),
    row({ id: 3, start: "08:00", end: null }),
    row({ id: 4, start: "09:00", end: "09:30" }),
    row({ id: 5, start: "09:00:00", end: "10:00:00" }),
    row({ id: 6, start: null, end: null }),
  ];
  assert.deepEqual(
    routines.sortRoutinesByTime(items).map((r) => r.id),
    [3, 4, 2, 5, 1, 6],
  );
  assert.deepEqual(
    items.map((r) => r.id),
    [1, 2, 3, 4, 5, 6],
  );
});
