/** 일과 기록 API 경계와 일일 보육일지 근거 (docs/api-spec.md §10-1 · §11 · S-J2). fetch 와 브라우저 저장소는 스텁이다. */
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

const sourceApi = await import("../lib/api/routines.ts");
const routines = { ...sourceApi, listRoutines: sourceApi.listDayRoutines };
const documents = await import("../lib/api/documents.ts");
const { API_STORAGE_CONTEXT } = await import("../lib/api/storage-context.ts");

const EMAIL = "fixture@example.com";
const linksKey = `saessak.apiLinks.v1:${API_STORAGE_CONTEXT}:${encodeURIComponent(EMAIL)}`;
const accountKey = `saessak.demoAccount:${encodeURIComponent(EMAIL)}`;

function browser() {
  const values = new Map([
    [accountKey, JSON.stringify({ name: "선생님", email: EMAIL })],
    [
      linksKey,
      JSON.stringify({ classes: { "class-abc": { id: 3, signature: "" } }, children: {} }),
    ],
  ]);
  const local = {
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, value),
    removeItem: (key) => values.delete(key),
  };
  const session = new Map([
    ["saessak.demoSession", "active"],
    ["saessak.accountEmail", EMAIL],
    ["saessak.authToken", "test-token"],
  ]);
  const sessionStorage = {
    getItem: (key) => session.get(key) ?? null,
    setItem: (key, value) => session.set(key, value),
    removeItem: (key) => session.delete(key),
  };
  globalThis.localStorage = local;
  globalThis.sessionStorage = sessionStorage;
  globalThis.window = { localStorage: local, sessionStorage };
}

function serve(body, status = 200) {
  const calls = [];
  const original = globalThis.fetch;
  globalThis.fetch = async (url, options = {}) => {
    calls.push({ url: String(url), body: options.body ? JSON.parse(options.body) : undefined });
    return new Response(JSON.stringify(body), {
      status,
      headers: { "Content-Type": "application/json" },
    });
  };
  return { calls, restore: () => (globalThis.fetch = original) };
}

// 서버가 실제로 내려주는 모양 그대로다 — 시각은 초까지 붙은 "HH:MM:SS".
const ROUTINE = {
  id: 7,
  class_id: 3,
  class_name: "햇살반",
  date: "2026-10-13",
  position: 0,
  start: "09:20:00",
  end: "10:40:00",
  name: "오전 실내놀이",
  plan: "자동차 굴리기",
  execution: "  블록 3개로 길을 만들었다. ",
  created_at: "2026-10-13T01:00:00Z",
};

test("그 반 · 그 날 일과를 서버 id 로 묻고 화면 id 로 돌려준다", async () => {
  browser();
  const { calls, restore } = serve({
    items: [
      ROUTINE,
      { ...ROUTINE, id: 8, start: "11:00:00", end: null, execution: "" },
      { ...ROUTINE, id: 9, start: null, end: null },
    ],
  });
  let items;
  try {
    items = await routines.listRoutines("class-abc", "2026-10-13");
  } finally {
    restore();
  }

  assert.equal(calls[0].url, "/api/routines?class_id=3&from=2026-10-13&to=2026-10-13");
  assert.deepEqual(items[0], {
    id: "routine:7",
    date: "2026-10-13",
    time: "09:20 ~ 10:40",
    name: "오전 실내놀이",
    execution: "블록 3개로 길을 만들었다.",
  });
  // 한쪽만 있거나 없는 시간도 서버 사실 줄과 같은 규칙으로 보인다.
  assert.equal(items[1].time, "11:00 ~");
  assert.equal(items[1].execution, "");
  assert.equal(items[2].time, "");
});

test("기간을 주면 그 주 일과를 한 번에 묻는다 — 일과 근거 주간 보육일지", async () => {
  browser();
  const { calls, restore } = serve({ items: [ROUTINE, { ...ROUTINE, id: 8, date: "2026-10-16" }] });
  let items;
  try {
    items = await routines.listRoutines("class-abc", "2026-10-12", "2026-10-16");
  } finally {
    restore();
  }

  assert.equal(calls[0].url, "/api/routines?class_id=3&from=2026-10-12&to=2026-10-16");
  assert.deepEqual(
    items.map((r) => r.date),
    ["2026-10-13", "2026-10-16"],
  );
});

test("반을 서버 id 로 못 옮기면 묻지 않는다", async () => {
  browser();
  const { calls, restore } = serve({ items: [] });
  try {
    await assert.rejects(routines.listRoutines("class-unknown", "2026-10-13"));
  } finally {
    restore();
  }
  assert.equal(calls.length, 0);
});

test("일일 보육일지는 일과 기록 id 를 고른 순서대로 보내고 아이를 보내지 않는다", async () => {
  browser();
  const detail = {
    id: 30,
    kind: "dailyLog",
    title: "햇살반 일일 보육일지 (10월 13일)",
    class_id: 3,
    class_name: "햇살반",
    child_id: null,
    child_name: null,
    start: "2026-10-13",
    end: "2026-10-13",
    status: "DRAFT",
    origin: "AI",
    stale: false,
    generation: { method: "RULE_LLM", rule_id: "r", rule_version: "1" },
    created_at: "2026-10-13T05:00:00Z",
    updated_at: "2026-10-13T05:00:00Z",
    sections: [
      { heading: "사실", body: "[오전 실내놀이 09:20~10:40] 블록", source_ids: [9, 7] },
      { heading: "해석", body: "길을 이어 만드는 데 관심이 많다.", source_ids: [9, 7] },
      { heading: "지원", body: "내일 경사로 블록을 더 꺼내 둔다.", source_ids: [9, 7] },
    ],
    sources: [
      { id: 9, date: "2026-10-13", text: "[바깥놀이] 모래", class_id: 3, child_id: null },
      { id: 7, date: "2026-10-13", text: "[오전 실내놀이] 블록", class_id: 3, child_id: null },
    ],
    review_note: "",
  };
  const { calls, restore } = serve(detail, 201);
  let created;
  try {
    created = await documents.createDocument({
      kind: "dailyLog",
      classId: "class-abc",
      childId: "",
      start: "2026-10-13",
      end: "2026-10-13",
      sourceIds: ["routine:9", "routine:7"],
    });
  } finally {
    restore();
  }

  assert.deepEqual(calls[0].body.source_ids, [9, 7]);
  assert.equal(calls[0].body.child_id, null);
  // 돌아온 근거도 일과 기록 화면 id 다 — 관찰 기록 id 로 섞이지 않는다.
  assert.deepEqual(
    created.sources.map((s) => s.id),
    ["routine:9", "routine:7"],
  );
});
