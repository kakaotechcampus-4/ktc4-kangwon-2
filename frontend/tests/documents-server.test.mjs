/** 일지 계열 문서 API 경계 (docs/api-spec.md §11). fetch 와 브라우저 저장소는 스텁이다. */
import { test } from "node:test";
import assert from "node:assert/strict";
import { createRequire, registerHooks } from "node:module";
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

const documents = await import("../lib/api/documents.ts");
const { ApiError } = await import("../lib/api/client.ts");
const { API_STORAGE_CONTEXT } = await import("../lib/api/storage-context.ts");

const EMAIL = "fixture@example.com";
const TOKEN = "test-token";
const linksKey = `saessak.apiLinks.v1:${API_STORAGE_CONTEXT}:${encodeURIComponent(EMAIL)}`;
const accountKey = `saessak.demoAccount:${encodeURIComponent(EMAIL)}`;
const LINKS = JSON.stringify({
  classes: { "class-abc": { id: 3, signature: "" } },
  children: { "api-child-8": 8 },
});

const LIST_ITEM = {
  id: 17,
  kind: "observation",
  title: "박서준 관찰일지 (9월)",
  class_id: 3,
  class_name: "햇살반",
  child_id: 8,
  child_name: "박서준",
  start: "2026-09-01",
  end: "2026-09-30",
  status: "DRAFT",
  origin: "AI",
  stale: true,
  generation: { method: "RULE_LLM", rule_id: "r1", rule_version: "1" },
  sources_count: 2,
  created_at: "2026-09-22T10:31:00+09:00",
  updated_at: "2026-09-23T09:00:00+09:00",
};
// 단건 응답에는 sources_count 가 없다.
const BASE = Object.fromEntries(Object.entries(LIST_ITEM).filter(([k]) => k !== "sources_count"));
const DETAIL = {
  ...BASE,
  sections: [
    { heading: "사실", body: "개미를 3분 동안 바라보았다.", source_ids: [12] },
    { heading: "해석", body: "관심 있는 대상을 오래 관찰하는 모습이 보인다.", source_ids: [12] },
    { heading: "지원", body: "돋보기와 관찰 기록지를 바깥놀이에 준비해 둔다.", source_ids: [12] },
  ],
  sources: [
    { id: 12, date: "2026-09-22", text: "개미를 3분 동안 바라보았다.", class_id: 3, child_id: 8 },
  ],
  review_note: "교사 검토 전",
};
const WEEKLY_DETAIL = {
  ...DETAIL,
  id: 21,
  kind: "weeklyLog",
  child_id: null,
  child_name: null,
  sections: DETAIL.sections.map((s) => ({ ...s, source_ids: [5] })),
  sources: [{ id: 5, date: "2026-09-22", text: "일일 일지 사실", class_id: 3, child_id: null }],
};

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
  const { calls, restore } = serve(() => json({ items: [LIST_ITEM] }));
  let list;
  try {
    list = await documents.listDocuments();
  } finally {
    restore();
  }

  assert.equal(calls[0].url, "/api/documents");
  assert.equal(calls[0].method, "GET");
  assert.equal(calls[0].auth, "Bearer " + TOKEN);
  assert.equal(list[0].id, "document:17");
  assert.equal(list[0].serverId, 17);
  assert.equal(list[0].classId, "class-abc");
  assert.equal(list[0].childId, "api-child-8");
  assert.equal(list[0].status, "draft");
  assert.equal(list[0].origin, "ai");
  assert.equal(list[0].stale, true);
  assert.equal(list[0].sourcesCount, 2);
  assert.deepEqual(writes, []);
});

test("목록 조건은 서버 query 로 나간다", async () => {
  browser();
  const { calls, restore } = serve(() => json({ items: [] }));
  try {
    await documents.listDocuments({ kind: "dailyLog", status: "CONFIRMED", class_id: 3 });
  } finally {
    restore();
  }
  assert.equal(calls[0].url, "/api/documents?kind=dailyLog&status=CONFIRMED&class_id=3");
});

test("단건은 sections 와 sources 까지 화면 model 로 옮긴다", async () => {
  browser();
  const { calls, restore } = serve(() => json(DETAIL));
  let doc;
  try {
    doc = await documents.getDocument("document:17");
  } finally {
    restore();
  }

  assert.equal(calls[0].url, "/api/documents/17");
  assert.equal(doc.id, "document:17");
  assert.equal(doc.reviewNote, "교사 검토 전");
  assert.equal(doc.stale, true);
  assert.equal(doc.sections.length, 3);
  // 관찰일지의 근거 id 는 관찰 기록이다.
  assert.deepEqual(doc.sections[0].sourceIds, ["observation:12"]);
  assert.equal(doc.sources[0].id, "observation:12");
  assert.equal(doc.sources[0].classId, "class-abc");
});

test("주간 보육일지의 근거 id 는 문서다", async () => {
  browser();
  const { restore } = serve(() => json(WEEKLY_DETAIL));
  let doc;
  try {
    doc = await documents.getDocument("document:21");
  } finally {
    restore();
  }
  assert.deepEqual(doc.sections[0].sourceIds, ["document:5"]);
  assert.equal(doc.sources[0].id, "document:5");
  // 반 전체 문서는 아동이 없다.
  assert.equal(doc.childId, "");
  assert.equal(doc.childName, "");
});

test("매핑이 없으면 화면 id 를 지어내지 않는다", async () => {
  browser(JSON.stringify({ classes: {}, children: {} }));
  const { restore } = serve(() => json(DETAIL));
  let doc;
  try {
    doc = await documents.getDocument("document:17");
  } finally {
    restore();
  }
  assert.equal(doc.classId, "server-class:3");
  assert.equal(doc.childId, "server-child:8");
  assert.notEqual(doc.classId, "class-3");
});

test("생성은 화면 id 를 서버 id 로 바꿔 여섯 칸만 보낸다", async () => {
  const writes = browser();
  const { calls, restore } = serve(() => json(DETAIL, 201));
  try {
    await documents.createDocument({
      kind: "observation",
      classId: "class-abc",
      childId: "api-child-8",
      start: "2026-09-01",
      end: "2026-09-30",
      sourceIds: ["observation:12"],
    });
  } finally {
    restore();
  }

  assert.equal(calls[0].url, "/api/documents");
  assert.equal(calls[0].method, "POST");
  assert.deepEqual(Object.keys(calls[0].body).sort(), [
    "child_id",
    "class_id",
    "end",
    "kind",
    "source_ids",
    "start",
  ]);
  assert.equal(calls[0].body.class_id, 3);
  assert.equal(calls[0].body.child_id, 8);
  assert.deepEqual(calls[0].body.source_ids, [12]);
  assert.deepEqual(writes, []);
});

test("주간 보육일지 생성은 문서 id 를 근거로 보낸다", async () => {
  browser();
  const { calls, restore } = serve(() => json(WEEKLY_DETAIL, 201));
  try {
    await documents.createDocument({
      kind: "weeklyLog",
      classId: "class-abc",
      childId: "",
      start: "2026-09-21",
      end: "2026-09-25",
      sourceIds: ["document:5"],
    });
  } finally {
    restore();
  }
  assert.deepEqual(calls[0].body.source_ids, [5]);
  assert.equal(calls[0].body.child_id, null);
});

test("매핑을 못 찾으면 생성 요청 자체를 보내지 않는다", async () => {
  browser();
  const { calls, restore } = serve(() => json(DETAIL, 201));
  const base = {
    kind: "observation",
    classId: "class-abc",
    childId: "api-child-8",
    start: "2026-09-01",
    end: "2026-09-30",
    sourceIds: ["observation:12"],
  };
  try {
    for (const bad of [
      { ...base, classId: "class-없음" },
      { ...base, childId: "child-없음" },
      { ...base, sourceIds: ["local-uuid"] },
    ])
      await assert.rejects(documents.createDocument(bad), (e) => e.message === documents.UNMAPPED);
  } finally {
    restore();
  }
  assert.equal(calls.length, 0);
});

test("수정은 세 칸만 보내고 근거 id 를 숫자로 되돌린다", async () => {
  browser();
  const { calls, restore } = serve(() => json(DETAIL));
  try {
    await documents.updateDocument("document:17", {
      kind: "observation",
      sections: [
        { heading: "사실", body: "개미를 3분 동안 바라보았다.", sourceIds: ["observation:12"] },
        { heading: "해석", body: "고친 해석", sourceIds: ["observation:12"] },
        { heading: "지원", body: "고친 지원", sourceIds: ["observation:12"] },
      ],
      reviewNote: "교사 검토 전",
      updatedAt: "2026-09-23T09:00:00+09:00",
    });
  } finally {
    restore();
  }

  assert.equal(calls[0].url, "/api/documents/17");
  assert.equal(calls[0].method, "PUT");
  assert.deepEqual(Object.keys(calls[0].body).sort(), ["review_note", "sections", "updated_at"]);
  assert.deepEqual(calls[0].body.sections[0].source_ids, [12]);
  assert.deepEqual(Object.keys(calls[0].body.sections[0]).sort(), [
    "body",
    "heading",
    "source_ids",
  ]);
  assert.equal(calls[0].body.updated_at, "2026-09-23T09:00:00+09:00");
});

test("확정은 교사 확인 세 개를 보낸다", async () => {
  browser();
  const { calls, restore } = serve(() => json({ ...DETAIL, status: "CONFIRMED" }));
  let doc;
  try {
    doc = await documents.confirmDocument("document:17");
  } finally {
    restore();
  }
  assert.equal(calls[0].url, "/api/documents/17/confirm");
  assert.equal(calls[0].method, "POST");
  assert.deepEqual(calls[0].body, {
    checks: { fact: true, interpretation: true, support: true },
  });
  assert.equal(doc.status, "confirmed");
});

test("삭제는 204 를 본문 없이 처리한다", async () => {
  const writes = browser();
  const { calls, restore } = serve(() => new Response(null, { status: 204 }));
  try {
    assert.equal(await documents.deleteDocument("document:17"), undefined);
  } finally {
    restore();
  }
  assert.equal(calls[0].url, "/api/documents/17");
  assert.equal(calls[0].method, "DELETE");
  assert.deepEqual(writes, []);
});

test("서버에서 오지 않은 id 는 요청을 보내지 않는다", async () => {
  browser();
  const { calls, restore } = serve(() => json(DETAIL));
  try {
    for (const id of ["local-uuid", "document:", "document:0", "17", "observation:17"]) {
      await assert.rejects(documents.getDocument(id), (e) => e.message === documents.UNMAPPED);
      await assert.rejects(documents.confirmDocument(id), (e) => e.message === documents.UNMAPPED);
      await assert.rejects(documents.deleteDocument(id), (e) => e.message === documents.UNMAPPED);
    }
  } finally {
    restore();
  }
  assert.equal(calls.length, 0);
});

test("409 세 가지를 갈라 본다", async () => {
  browser();
  for (const [code, check] of [
    ["GATE_BLOCKED", documents.isGateBlocked],
    ["ALREADY_CONFIRMED", documents.isAlreadyConfirmed],
    ["STALE_WRITE", documents.isStaleWrite],
  ]) {
    const { restore } = serve(() => fail(code, 409));
    let caught;
    try {
      await documents.confirmDocument("document:17").catch((e) => (caught = e));
    } finally {
      restore();
    }
    assert.ok(caught instanceof ApiError && caught.status === 409, code);
    assert.equal(check(caught), true, code);
    // 같은 409 라도 서로 다른 것으로 읽혀야 한다.
    const others = [documents.isGateBlocked, documents.isAlreadyConfirmed, documents.isStaleWrite]
      .filter((f) => f !== check)
      .map((f) => f(caught));
    assert.deepEqual(others, [false, false], code);
  }
});

test("서버 문서를 브라우저 저장소에 남기지 않는다", async () => {
  const writes = browser();
  const { restore } = serve((n) => (n === 1 ? json({ items: [LIST_ITEM] }) : json(DETAIL)));
  try {
    await documents.listDocuments();
    await documents.getDocument("document:17");
  } finally {
    restore();
  }
  assert.deepEqual(writes, []);
});

// 화면은 JSX 라 이 환경에서 렌더할 수 없다. 아래 둘은 소스로 확인한다.
const read = (name) =>
  readFileSync(new URL(`../components/workspace/${name}`, import.meta.url), "utf8");

test("문서 화면이 §11 문서를 저장소나 AI 로 만들지 않는다", () => {
  const page = read("DocumentsPage.tsx");

  for (const banned of ['requestAI("document"', "requestAI", "useAIStatus", "crypto.randomUUID"])
    assert.equal(page.includes(banned), false, banned);
  for (const used of [
    "listDocuments",
    "getDocument",
    "createDocument",
    "updateDocument",
    "confirmDocument",
    "deleteDocument",
  ])
    assert.equal(page.includes(used), true, used);
  // 계획안과 등록 증빙만 브라우저 저장소에서 읽는다.
  assert.ok(page.includes('d.origin === "import" || !isRecordKind(d.kind)'));
  // 편집기에 올리는 서버 문서는 언제나 지금 고른 문서다.
  assert.ok(page.includes("chosen.detail?.id === active ? chosen.detail : null"));
  assert.ok(page.includes("serverActions = serverCurrent"));
  assert.ok(page.includes("const creation = selection.beginCreation()"));
  assert.ok(page.includes("if (creation.adopt(created))"));
  assert.equal(page.includes("selection.adopt(created)"), false);
  assert.ok(page.includes("if (creation.isCurrent()) setMessage(messageFor(e))"));
});

test("서버 문서는 확정을 되돌리지 못하고 AI 검증을 확정 조건으로 걸지 않는다", () => {
  const editor = read("DocumentEditor.tsx");

  // 확정 해제 API 가 없다 — 서버 문서에는 「문서 수정」 버튼을 두지 않는다.
  assert.ok(editor.includes("!server && ("));
  const open = editor.indexOf("if (server) {");
  const branch = editor.slice(open, editor.indexOf("\n      return;\n    }\n", open));
  assert.ok(branch.length > 0);
  assert.equal(branch.includes("verified"), false);
  // 서버 문서는 backend 와 같은 기준만 본다 — 로컬 휴리스틱을 겹쳐 걸지 않는다.
  assert.ok(branch.includes("serverIssues"));
  assert.equal(branch.includes("validateDocument"), false);
  assert.ok(branch.includes("server.stale"));
  // 서버 문서의 동시성 기준은 updated_at 이다.
  assert.ok(editor.includes("const stale = !server &&"));
});

// ── 선택과 서버 응답 순서 ────────────────────────────────────────────────
const { createSelection, serverIssues, BUSY, MOVED } =
  await import("../components/workspace/document-selection.ts");
const workspaceModel = await import("../lib/workspace/model.ts");
const { validateDocument } = workspaceModel;

/** 응답 시점을 테스트가 직접 정한다. */
function deferred() {
  let resolve, reject;
  const promise = new Promise((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}
const tick = () => new Promise((r) => setTimeout(r, 0));

const SECTIONS = [
  { heading: "사실", body: "개미를 3분 동안 바라보았다.", sourceIds: ["observation:12"] },
  { heading: "해석", body: "관심 있는 대상을 오래 관찰하는 모습이 보인다.", sourceIds: [] },
  {
    heading: "지원",
    body: "지원하겠습니다. 블록 놀이에 넓은 받침을 제공하고 다음 날 쌓기 시도를 기록합니다.",
    sourceIds: [],
  },
];
const doc = (n, over = {}) => ({
  id: `document:${n}`,
  serverId: n,
  kind: "observation",
  title: `문서 ${n}`,
  classId: "class-abc",
  className: "햇살반",
  childId: "api-child-8",
  childName: "박서준",
  start: "2026-09-01",
  end: "2026-09-30",
  status: "draft",
  origin: "ai",
  stale: false,
  sections: SECTIONS,
  sources: [],
  reviewNote: "교사 검토 전",
  createdAt: "t0",
  updatedAt: "t0",
  ...over,
});
const describe = (e) => (e instanceof Error ? e.message : "오류");

test("저장 응답이 늦게 와도 그 사이 고른 문서를 덮지 않는다", async () => {
  const getA = deferred();
  const getB = deferred();
  const put = deferred();
  const calls = [];
  const selection = createSelection(
    {
      get: (id) => {
        calls.push(["get", id]);
        return id === "document:1" ? getA.promise : getB.promise;
      },
      update: (id) => {
        calls.push(["update", id]);
        return put.promise;
      },
      confirm: async () => doc(1),
      remove: async () => {},
    },
    describe,
  );

  selection.select("document:1", 1);
  getA.resolve(doc(1));
  await tick();
  assert.equal(selection.get().detail.id, "document:1");

  const saving = selection.save(SECTIONS, "교사 검토 전");
  await tick();
  // 저장 응답 전에 다른 문서로 옮긴다.
  selection.select("document:2", 2);
  getB.resolve(doc(2));
  await tick();
  assert.equal(selection.get().active, "document:2");
  assert.equal(selection.get().detail.id, "document:2");

  put.resolve(doc(1, { updatedAt: "t1" }));
  await saving;
  await tick();

  // 서버 저장은 그대로 인정하되 화면은 B 그대로여야 한다.
  assert.deepEqual(calls, [
    ["get", "document:1"],
    ["update", "document:1"],
    ["get", "document:2"],
  ]);
  assert.equal(selection.get().active, "document:2");
  assert.equal(selection.get().detail.id, "document:2");
  assert.equal(selection.get().pending, "");
});

test("서버 상세가 늦게 실패해도 그 사이 고른 로컬 문서를 지우지 않는다", async () => {
  const getA = deferred();
  const selection = createSelection(
    {
      get: () => getA.promise,
      update: async () => doc(1),
      confirm: async () => doc(1),
      remove: async () => {},
    },
    describe,
  );

  selection.select("document:1", 1);
  assert.equal(selection.get().status, "loading");
  // 응답 전에 로컬 문서로 옮긴다 (서버 id 가 없다).
  selection.select("local-uuid", null);
  assert.equal(selection.get().status, "ready");

  getA.reject(new Error("불러오지 못했어요."));
  await tick();

  assert.equal(selection.get().active, "local-uuid");
  assert.equal(selection.get().detail, null);
  assert.equal(selection.get().status, "ready");
  assert.equal(selection.get().error, "");
});

test("삭제 중에는 저장·확정·추가 삭제가 실행되지 않는다", async () => {
  const del = deferred();
  const calls = [];
  const selection = createSelection(
    {
      get: async (id) => doc(Number(id.slice("document:".length))),
      update: async () => {
        calls.push("update");
        return doc(1);
      },
      confirm: async () => {
        calls.push("confirm");
        return doc(1);
      },
      remove: (id) => {
        calls.push("remove:" + id);
        return del.promise;
      },
    },
    describe,
  );

  selection.select("document:1", 1);
  await tick();
  const removing = selection.remove();
  await tick();
  assert.equal(selection.get().pending, "document:1");

  await assert.rejects(selection.save(SECTIONS, "메모"), (e) => e.message === BUSY);
  await assert.rejects(selection.saveAndConfirm(SECTIONS, "메모"), (e) => e.message === BUSY);
  await assert.rejects(selection.remove(), (e) => e.message === BUSY);

  // 삭제가 끝나기 전에 다른 문서를 골라도 그 문서가 닫히면 안 된다.
  selection.select("document:2", 2);
  await tick();
  del.resolve();
  await removing;
  await tick();

  assert.deepEqual(calls, ["remove:document:1"]);
  assert.equal(selection.get().active, "document:2");
  assert.equal(selection.get().detail.id, "document:2");
});

test("삭제한 문서를 그대로 보고 있었으면 편집기를 닫는다", async () => {
  const selection = createSelection(
    {
      get: async () => doc(1),
      update: async () => doc(1),
      confirm: async () => doc(1),
      remove: async () => {},
    },
    describe,
  );
  selection.select("document:1", 1);
  await tick();
  await selection.remove();
  assert.equal(selection.get().active, "");
  assert.equal(selection.get().detail, null);
});

test("확정이 실패해도 다음 저장은 방금 받은 updated_at 을 쓴다", async () => {
  const sent = [];
  const selection = createSelection(
    {
      get: async () => doc(1, { updatedAt: "t0" }),
      update: async (id, input) => {
        sent.push(input.updatedAt);
        return doc(1, { updatedAt: "t1" });
      },
      confirm: async () => {
        throw new Error("확정하지 못했어요.");
      },
      remove: async () => {},
    },
    describe,
  );

  selection.select("document:1", 1);
  await tick();
  await assert.rejects(selection.saveAndConfirm(SECTIONS, "교사 검토 전"));
  await selection.save(SECTIONS, "교사 검토 전");

  assert.deepEqual(sent, ["t0", "t1"]);
});

test("구체적인 지원 문장을 서버 확정에서 막지 않는다", () => {
  const sections = SECTIONS;
  // 기존 로컬 규칙은 이 문장을 상투어로 보고 막는다 — 그 동작은 그대로 둔다.
  const localIssues = validateDocument({
    sections,
    sources: [],
    start: "2026-09-01",
    end: "2026-09-30",
    kind: "observation",
    classId: "class-abc",
    childId: "api-child-8",
    origin: "ai",
  });
  assert.ok(localIssues.some((issue) => issue.includes("지원을 구체적으로")));

  // 서버 문서는 backend 와 같은 기준(20자)만 본다.
  assert.deepEqual(serverIssues({ sections }), []);
  assert.deepEqual(
    serverIssues({
      sections: [...sections.slice(0, 2), { heading: "지원", body: "짧다", sourceIds: [] }],
    }),
    ["지원을 20자 이상 작성해주세요."],
  );
});

test("확정 중 다른 문서로 옮기면 그 문서를 확정하지 않는다", async () => {
  const getA = deferred();
  const getB = deferred();
  const put = deferred();
  const calls = [];
  const selection = createSelection(
    {
      get: (id) => {
        calls.push("get " + id);
        return id === "document:1" ? getA.promise : getB.promise;
      },
      update: (id) => {
        calls.push("update " + id);
        return put.promise;
      },
      confirm: async (id) => {
        calls.push("confirm " + id);
        return doc(Number(id.slice("document:".length)));
      },
      remove: async () => {},
    },
    describe,
  );

  selection.select("document:1", 1);
  getA.resolve(doc(1));
  await tick();

  const confirming = selection.saveAndConfirm(SECTIONS, "교사 사실·해석·지원 검토 완료");
  await tick();
  // 확정이 끝나기 전에 다른 문서로 옮긴다.
  selection.select("document:2", 2);
  getB.resolve(doc(2));
  await tick();

  put.resolve(doc(1, { updatedAt: "t1" }));
  await assert.rejects(confirming, (e) => e.message === MOVED);
  await tick();

  // 저장은 A 로 나갔고, 확정은 어떤 문서로도 나가지 않아야 한다.
  assert.deepEqual(calls, ["get document:1", "update document:1", "get document:2"]);
  assert.equal(
    calls.some((c) => c.startsWith("confirm")),
    false,
  );
  assert.equal(selection.get().active, "document:2");
  assert.equal(selection.get().detail.id, "document:2");
  assert.equal(selection.get().pending, "");
});

test("문서를 바꾸지 않으면 저장한 문서를 그대로 확정한다", async () => {
  const calls = [];
  const selection = createSelection(
    {
      get: async () => doc(1),
      update: async (id) => {
        calls.push("update " + id);
        return doc(1, { updatedAt: "t1" });
      },
      confirm: async (id) => {
        calls.push("confirm " + id);
        return doc(1, { status: "confirmed", updatedAt: "t2" });
      },
      remove: async () => {},
    },
    describe,
  );

  selection.select("document:1", 1);
  await tick();
  const confirmed = await selection.saveAndConfirm(SECTIONS, "교사 사실·해석·지원 검토 완료");

  assert.deepEqual(calls, ["update document:1", "confirm document:1"]);
  assert.equal(confirmed.status, "confirmed");
  assert.equal(selection.get().detail.status, "confirmed");
});

test("삭제 중 같은 문서를 다시 골라도 삭제 뒤에는 남지 않는다", async () => {
  const del = deferred();
  const getAgain = deferred();
  let gets = 0;
  const selection = createSelection(
    {
      get: () => {
        gets += 1;
        return gets === 1 ? Promise.resolve(doc(1)) : getAgain.promise;
      },
      update: async () => doc(1),
      confirm: async () => doc(1),
      remove: () => del.promise,
    },
    describe,
  );

  selection.select("document:1", 1);
  await tick();
  const removing = selection.remove();
  await tick();

  // 같은 항목 재클릭은 noop이다. 다른 문서를 거쳐 돌아와 실제 두 번째 GET을 만든다.
  selection.select("local-uuid", null);
  selection.select("document:1", 1);
  assert.equal(gets, 2);
  getAgain.resolve(doc(1));
  await tick();
  assert.equal(selection.get().detail.id, "document:1");

  del.resolve();
  await removing;
  await tick();

  assert.equal(selection.get().active, "");
  assert.equal(selection.get().detail, null);
});

test("삭제한 문서의 늦은 조회 응답이 다시 열지 못한다", async () => {
  const del = deferred();
  const getAgain = deferred();
  let gets = 0;
  const selection = createSelection(
    {
      get: () => {
        gets += 1;
        return gets === 1 ? Promise.resolve(doc(1)) : getAgain.promise;
      },
      update: async () => doc(1),
      confirm: async () => doc(1),
      remove: () => del.promise,
    },
    describe,
  );

  selection.select("document:1", 1);
  await tick();
  const removing = selection.remove();
  await tick();
  // 다른 문서를 거쳐 다시 고른 A의 조회는 아직 끝나지 않았다.
  selection.select("local-uuid", null);
  selection.select("document:1", 1);
  assert.equal(gets, 2);
  await tick();

  del.resolve();
  await removing;
  await tick();
  assert.equal(selection.get().active, "");

  // 삭제가 끝난 뒤에 늦게 도착한 조회 응답.
  getAgain.resolve(doc(1));
  await tick();

  assert.equal(selection.get().active, "");
  assert.equal(selection.get().detail, null);
  assert.equal(selection.get().status, "ready");
});

// 생성은 아직 선택된 서버 id 가 없으므로 mutation 잠금과 별개의 문맥을 쓴다.
function creationFixture() {
  const post = deferred();
  const calls = [];
  const selection = createSelection(
    {
      get: async (id) => {
        calls.push("get " + id);
        return doc(Number(id.slice("document:".length)));
      },
      update: async () => {
        throw new Error("unexpected update");
      },
      confirm: async () => {
        throw new Error("unexpected confirm");
      },
      remove: async () => {
        throw new Error("unexpected delete");
      },
    },
    describe,
  );
  const creation = selection.beginCreation();
  calls.push("post document:3");
  const result = post.promise.then((created) => {
    const adopted = creation.adopt(created);
    // 페이지는 자동 열기 여부와 무관하게 성공한 POST 뒤 목록을 다시 읽는다.
    calls.push("reload list");
    return adopted;
  });
  return { post, calls, selection, creation, result };
}

test("생성 응답 전에 B를 고르면 B를 유지하고 생성 결과는 목록에 반영한다", async () => {
  const { post, calls, selection, result } = creationFixture();
  selection.select("document:2", 2);
  await tick();
  post.resolve(doc(3));
  assert.equal(await result, false);
  assert.equal(selection.get().active, "document:2");
  assert.equal(selection.get().detail.id, "document:2");
  assert.deepEqual(calls, ["post document:3", "get document:2", "reload list"]);
});

test("생성 완료는 편집 중인 B의 detail과 editor key를 교체하지 않는다", async () => {
  const { post, selection, result } = creationFixture();
  selection.select("document:2", 2);
  await tick();
  const before = selection.get();
  // editor 는 sections 를 자체 state 에 두고 key={current.id} 가 바뀔 때 교체된다.
  // 따라서 같은 detail 참조·id·ready 상태를 유지하는지 검증한다.
  const drafts = structuredClone(before.detail.sections);
  drafts[1].body = "B에서 아직 저장하지 않은 해석입니다.";
  post.resolve(doc(3));
  await result;
  assert.strictEqual(selection.get(), before);
  assert.strictEqual(selection.get().detail, before.detail);
  assert.equal(selection.get().active, "document:2");
  assert.equal(selection.get().status, "ready");
  assert.equal(drafts[1].body, "B에서 아직 저장하지 않은 해석입니다.");
  assert.ok(read("DocumentsPage.tsx").includes("key={current.id}"));
});

test("생성 중 문맥이 그대로면 새 문서를 정상적으로 연다", async () => {
  const { post, selection, result } = creationFixture();
  const created = doc(3);
  post.resolve(created);
  assert.equal(await result, true);
  assert.equal(selection.get().active, "document:3");
  assert.strictEqual(selection.get().detail, created);
  assert.equal(selection.get().status, "ready");
});

test("생성 중 local 문서를 고르면 local 선택을 유지한다", async () => {
  const { post, selection, result } = creationFixture();
  selection.select("local-import-uuid", null);
  const before = selection.get();
  post.resolve(doc(3));
  assert.equal(await result, false);
  assert.strictEqual(selection.get(), before);
  assert.equal(selection.get().active, "local-import-uuid");
  assert.equal(selection.get().detail, null);
});

test("이전 생성 실패는 현재 B의 상세 오류로 적용되지 않는다", async () => {
  const { post, selection, creation, result, calls } = creationFixture();
  selection.select("document:2", 2);
  await tick();
  const before = selection.get();
  post.reject(new Error("GENERATION_FAILED"));
  await assert.rejects(result, /GENERATION_FAILED/);
  assert.equal(creation.isCurrent(), false);
  assert.strictEqual(selection.get(), before);
  assert.equal(selection.get().error, "");
  assert.deepEqual(calls, ["post document:3", "get document:2"]);
});

test("생성 중 선택 해제 뒤에는 늦은 생성 응답이 editor를 열지 않는다", async () => {
  const { post, selection, result } = creationFixture();
  selection.select("", null);
  post.resolve(doc(3));
  assert.equal(await result, false);
  assert.equal(selection.get().active, "");
  assert.equal(selection.get().detail, null);
});

test("선택 id가 같아도 화면을 떠나거나 unmount하면 생성 자동 열기는 취소된다", async () => {
  const { post, selection, creation, result } = creationFixture();
  selection.leaveCreation();
  assert.equal(creation.isCurrent(), false);
  post.resolve(doc(3));
  assert.equal(await result, false);
  assert.equal(selection.get().active, "");
  assert.equal(selection.get().detail, null);
  const page = read("DocumentsPage.tsx");
  assert.ok(page.includes("latestList.current += 1;\n      selection.leaveCreation()"));
  assert.ok(page.includes("selection.leaveCreation();\n            setMode("));
});

test("한 생성 문맥은 한 번만 열 수 있고 새 생성은 이전 문맥을 무효화한다", () => {
  const selection = createSelection({}, describe);
  const previous = selection.beginCreation();
  const current = selection.beginCreation();
  assert.equal(previous.adopt(doc(1)), false);
  assert.equal(current.adopt(doc(3)), true);
  assert.equal(current.adopt(doc(2)), false);
  assert.equal(selection.get().active, "document:3");
});

test("같은 ready 문서를 다시 선택해도 detail과 편집기 문맥을 유지하고 GET하지 않는다", async () => {
  let gets = 0;
  const selection = createSelection(
    {
      get: async () => {
        gets += 1;
        return doc(1);
      },
    },
    describe,
  );
  selection.select("document:1", 1);
  await tick();
  const before = selection.get();
  let notifications = 0;
  const unsubscribe = selection.subscribe(() => {
    notifications += 1;
  });
  selection.select("document:1", 1);
  assert.strictEqual(selection.get(), before);
  assert.equal(selection.get().active, "document:1");
  assert.equal(selection.get().detail.id, "document:1");
  assert.equal(selection.get().status, "ready");
  assert.equal(gets, 1);
  assert.equal(notifications, 0);
  unsubscribe();
});

test("첫 상세 조회 중 같은 문서를 더블클릭해도 GET은 한 번만 보낸다", async () => {
  const response = deferred();
  let gets = 0;
  const selection = createSelection(
    {
      get: () => {
        gets += 1;
        return response.promise;
      },
    },
    describe,
  );
  selection.select("document:1", 1);
  const loading = selection.get();
  selection.select("document:1", 1);
  assert.strictEqual(selection.get(), loading);
  assert.equal(gets, 1);
  response.resolve(doc(1));
  await tick();
  assert.equal(selection.get().status, "ready");
  assert.equal(selection.get().detail.id, "document:1");
});

test("같은 문서의 detail 조회가 실패했으면 재선택으로 GET을 재시도한다", async () => {
  let gets = 0;
  const selection = createSelection(
    {
      get: async () => {
        gets += 1;
        if (gets === 1) throw new Error("일시적인 조회 실패");
        return doc(1);
      },
    },
    describe,
  );
  selection.select("document:1", 1);
  await tick();
  assert.equal(selection.get().status, "error");
  selection.select("document:1", 1);
  assert.equal(selection.get().status, "loading");
  await tick();
  assert.equal(gets, 2);
  assert.equal(selection.get().status, "ready");
  assert.equal(selection.get().error, "");
  assert.equal(selection.get().detail.id, "document:1");
});

test("STALE_WRITE 뒤 명시적 reload를 거친 저장은 최신 updated_at을 전송한다", async () => {
  browser();
  const t0 = "2026-09-23T09:00:00+09:00";
  const t1 = "2026-09-23T10:00:00+09:00";
  const { calls, restore } = serve((n) => {
    if (n === 1) return json({ ...DETAIL, updated_at: t0 });
    if (n === 2) return fail("STALE_WRITE", 409);
    return json({ ...DETAIL, updated_at: t1 });
  });
  const selection = createSelection(
    {
      get: documents.getDocument,
      update: documents.updateDocument,
      confirm: documents.confirmDocument,
      remove: documents.deleteDocument,
    },
    describe,
  );
  try {
    selection.select("document:17", 17);
    await tick();
    const original = selection.get().detail;
    await assert.rejects(selection.save(original.sections, "수정"), documents.isStaleWrite);
    assert.strictEqual(selection.get().detail, original);
    assert.equal(calls.length, 2, "409 자체는 자동 GET을 보내지 않는다");
    const latest = await selection.reload();
    assert.equal(latest.updatedAt, t1);
    assert.equal(selection.get().detail.updatedAt, t1);
    await selection.save(latest.sections, "최신 문서 재검토");
    assert.deepEqual(
      calls.map((c) => c.method),
      ["GET", "PUT", "GET", "PUT"],
    );
    assert.ok(calls.every((c) => c.url === "/api/documents/17"));
    assert.equal(calls[1].body.updated_at, t0);
    assert.equal(calls[3].body.updated_at, t1);
  } finally {
    restore();
  }
});

test("reload 중에도 기존 detail을 유지하고 저장·확정·삭제·추가 reload를 막는다", async () => {
  const response = deferred();
  let gets = 0;
  const selection = createSelection(
    {
      get: () => (++gets === 1 ? Promise.resolve(doc(1)) : response.promise),
    },
    describe,
  );
  selection.select("document:1", 1);
  await tick();
  const original = selection.get().detail;
  const reloading = selection.reload();
  assert.strictEqual(selection.get().detail, original);
  assert.equal(selection.get().status, "ready");
  assert.equal(selection.get().pending, "document:1");
  for (const operation of [
    () => selection.save(SECTIONS, "수정"),
    () => selection.saveAndConfirm(SECTIONS, "검토 완료"),
    () => selection.remove(),
    () => selection.reload(),
  ])
    await assert.rejects(operation(), (error) => error.message === BUSY);
  assert.equal(gets, 2);
  response.resolve(doc(1, { updatedAt: "t1" }));
  await reloading;
  assert.equal(selection.get().pending, "");
  assert.equal(selection.get().detail.updatedAt, "t1");
});

test("reload 실패는 ready detail을 유지하고 명시적으로 다시 시도할 수 있다", async () => {
  let gets = 0;
  const selection = createSelection(
    {
      get: async () => {
        gets += 1;
        if (gets === 2) throw new Error("최신 문서 조회 실패");
        return doc(1, { updatedAt: gets === 1 ? "t0" : "t1" });
      },
    },
    describe,
  );
  selection.select("document:1", 1);
  await tick();
  const original = selection.get().detail;
  await assert.rejects(selection.reload(), /최신 문서 조회 실패/);
  assert.strictEqual(selection.get().detail, original);
  assert.equal(selection.get().status, "ready");
  assert.equal(selection.get().pending, "");
  assert.equal((await selection.reload()).updatedAt, "t1");
  assert.equal(gets, 3);
});

test("reload A 응답이 늦게 와도 그 사이 선택한 B를 덮지 않는다", async () => {
  const response = deferred();
  let aGets = 0;
  const selection = createSelection(
    {
      get: (id) => {
        if (id === "document:2") return Promise.resolve(doc(2));
        return ++aGets === 1 ? Promise.resolve(doc(1)) : response.promise;
      },
    },
    describe,
  );
  selection.select("document:1", 1);
  await tick();
  const reloading = selection.reload();
  selection.select("document:2", 2);
  await tick();
  const current = selection.get().detail;
  response.resolve(doc(1, { updatedAt: "t1" }));
  assert.equal(await reloading, null);
  assert.equal(selection.get().active, "document:2");
  assert.strictEqual(selection.get().detail, current);
  assert.equal(selection.get().status, "ready");
  assert.equal(selection.get().pending, "");
});

test("reload A 중 B를 거쳐 A로 돌아와도 이전 reload는 새 상세를 덮지 않는다", async () => {
  const response = deferred();
  let aGets = 0;
  const selection = createSelection(
    {
      get: async (id) => {
        if (id === "document:2") return doc(2);
        aGets += 1;
        if (aGets === 2) return response.promise;
        return doc(1, { updatedAt: aGets === 1 ? "t0" : "t2" });
      },
    },
    describe,
  );
  selection.select("document:1", 1);
  await tick();
  const reloading = selection.reload();
  selection.select("document:2", 2);
  selection.select("document:1", 1);
  await tick();
  assert.equal(aGets, 3);
  assert.equal(selection.get().detail.updatedAt, "t2");
  response.resolve(doc(1, { updatedAt: "t1" }));
  assert.equal(await reloading, null);
  assert.equal(selection.get().active, "document:1");
  assert.equal(selection.get().detail.updatedAt, "t2");
});

// 실제 TSX 이벤트와 state를 실행한다. 브라우저/React renderer E2E는 아니며,
// 선택 이동·unmount는 위 production selection 테스트가 별도로 검증한다.
const require = createRequire(import.meta.url);
const editorCode = require("next/dist/compiled/babel/core").transformSync(
  read("DocumentEditor.tsx"),
  {
    filename: "DocumentEditor.tsx",
    babelrc: false,
    configFile: false,
    presets: [
      [require("next/dist/compiled/babel/preset-env"), { targets: { node: "current" } }],
      [require("next/dist/compiled/babel/preset-react"), { runtime: "automatic" }],
      require("next/dist/compiled/babel/preset-typescript"),
    ],
  },
).code;

function editorHarness(selection) {
  const slots = [];
  let cursor = 0;
  const state = (initial) => {
    const slot = cursor++;
    if (!(slot in slots)) slots[slot] = typeof initial === "function" ? initial() : initial;
    return [
      slots[slot],
      (next) => {
        slots[slot] = typeof next === "function" ? next(slots[slot]) : next;
      },
    ];
  };
  const jsx = (type, props, key) => ({ type, props, key });
  const modules = {
    react: {
      useState: state,
      useRef: (initial) => state(() => ({ current: initial }))[0],
      useEffect: () => {},
    },
    "react/jsx-runtime": { jsx, jsxs: jsx, Fragment: "fragment" },
    "@/lib/workspace/model": workspaceModel,
    "@/lib/workspace/ai-client": {
      requestAI: () => {
        throw new Error("Unexpected AI call");
      },
    },
    "./WorkspaceUI": { ws: {}, Message: "message", AIHint: "ai-hint", useAIStatus: () => false },
    "./document-selection": { serverIssues },
    "@/lib/api/storage-context": { API_STORAGE_CONTEXT },
    "@/lib/api/plans": {},
    "@/lib/api/documents": documents,
  };
  const compiledModule = { exports: {} };
  new Function("require", "module", "exports", editorCode)(
    (name) => {
      assert.ok(name in modules, `unhandled editor import: ${name}`);
      return modules[name];
    },
    compiledModule,
    compiledModule.exports,
  );
  const Editor = compiledModule.exports.default;
  let tree;
  function render() {
    cursor = 0;
    const current = selection.get();
    tree = Editor({
      initial: current.detail,
      onSave: () => {
        throw new Error("Unexpected local save");
      },
      server: {
        stale: current.detail.stale,
        pending: current.pending !== "",
        save: selection.save,
        saveAndConfirm: selection.saveAndConfirm,
        remove: selection.remove,
        reload: selection.reload,
      },
    });
  }
  const all = (node) => {
    if (!node || typeof node !== "object") return [];
    if (Array.isArray(node)) return node.flatMap(all);
    return [node, ...all(node.props?.children)];
  };
  const content = (node) => {
    if (Array.isArray(node)) return node.map(content).join("");
    if (node && typeof node === "object") return content(node.props?.children);
    return typeof node === "string" || typeof node === "number" ? String(node) : "";
  };
  render();
  return {
    render,
    textarea: () =>
      all(tree).find(
        (node) => node.type === "textarea" && node.props["aria-label"] === "해석 내용",
      ),
    button: (label) => all(tree).find((node) => node.type === "button" && content(node) === label),
    checks: () =>
      all(tree).filter((node) => node.type === "input" && node.props.type === "checkbox"),
    text: () => content(tree),
  };
}

test("실제 편집기는 STALE_WRITE와 reload 실패 때 입력을 보존하고 명시적 성공 뒤 최신 문서로 복구한다", async () => {
  let gets = 0;
  let saves = 0;
  const selection = createSelection(
    {
      get: async () => {
        gets += 1;
        if (gets === 2) throw new Error("최신 조회 실패");
        return doc(1, {
          updatedAt: gets === 1 ? "t0" : "t1",
          sections: SECTIONS.map((section) =>
            section.heading === "해석"
              ? { ...section, body: gets === 1 ? "최초 해석 내용" : "서버 최신 해석 내용" }
              : section,
          ),
        });
      },
      update: async (_id, input) => {
        saves += 1;
        if (saves === 1)
          throw new ApiError(409, {
            error: { code: "STALE_WRITE", message: "다른 곳에서 수정됨" },
          });
        assert.equal(input.updatedAt, "t1");
        return doc(1, { ...input, updatedAt: "t2" });
      },
    },
    describe,
  );
  selection.select("document:1", 1);
  await tick();
  const editor = editorHarness(selection);
  editor.textarea().props.onChange({ target: { value: "버리면 안 되는 미저장 입력" } });
  editor.render();
  for (const checkbox of editor.checks()) checkbox.props.onChange({ target: { checked: true } });
  editor.render();
  await editor.button("초안 저장").props.onClick();
  editor.render();
  assert.equal(editor.textarea().props.value, "버리면 안 되는 미저장 입력");
  assert.equal(gets, 1, "STALE_WRITE는 자동으로 재조회하지 않는다");
  assert.ok(editor.button("최신 문서 불러오기"));
  assert.match(editor.text(), /현재.*내용.*(바뀝|바뀌|교체)/);

  await editor.button("최신 문서 불러오기").props.onClick();
  editor.render();
  assert.equal(editor.textarea().props.value, "버리면 안 되는 미저장 입력");
  assert.ok(editor.button("최신 문서 불러오기"), "조회 실패 뒤에도 복구 버튼이 남는다");
  assert.equal(selection.get().detail.updatedAt, "t0");

  await editor.button("최신 문서 불러오기").props.onClick();
  editor.render();
  assert.equal(editor.textarea().props.value, "서버 최신 해석 내용");
  assert.equal(selection.get().detail.updatedAt, "t1");
  assert.equal(editor.button("최신 문서 불러오기"), undefined);
  assert.ok(editor.checks().every((checkbox) => checkbox.props.checked === false));
  editor.textarea().props.onChange({ target: { value: "최신 문서에서 다시 작성한 해석" } });
  editor.render();
  await editor.button("초안 저장").props.onClick();
  editor.render();
  assert.equal(saves, 2);
  assert.equal(selection.get().detail.updatedAt, "t2");
  assert.equal(editor.textarea().props.value, "최신 문서에서 다시 작성한 해석");
  const page = read("DocumentsPage.tsx");
  assert.match(page, /reload:\s*selection\.reload/);
});
