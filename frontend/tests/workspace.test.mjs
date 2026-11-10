import assert from "node:assert/strict";
import { test } from "node:test";
import { registerHooks } from "node:module";
import { fixtureSession, fixtureKey, fixtureAccount, fixtureEmail } from "./auth-fixture.mjs";
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
const { templatePlan, planPeriod } = await import("../lib/workspace/plans.ts");
const {
  parseWorkspace,
  updateWorkspace,
  readWorkspace,
  moveLegacyImports,
  DROPPED_IMPORTS,
  LEGACY_IMPORTS_MOVED,
} = await import("../lib/workspace/store.ts");
const { API_STORAGE_CONTEXT } = await import("../lib/api/storage-context.ts");
import {
  validateDocument,
  compareEvidence,
  invalidateDependents,
  analyzeText,
  validPeriod,
  assertDocumentUnchanged,
  isSavedDocument,
  childDisplayName,
} from "../lib/workspace/model.ts";

const observation = {
  id: "r1",
  classId: "c1",
  childId: "child1",
  date: "2026-09-11",
  fact: "블록 세 개를 쌓고 더 높이 만들겠다고 말했다.",
};
const source = {
  id: "r1",
  classId: "c1",
  childId: "child1",
  date: observation.date,
  text: observation.fact,
};
function document(overrides = {}) {
  return {
    id: "d1",
    kind: "observation",
    classId: "c1",
    childId: "child1",
    start: "2026-09-11",
    end: "2026-09-11",
    status: "confirmed",
    sources: [source],
    sections: [
      { heading: "사실", body: source.text, sourceIds: [source.id] },
      {
        heading: "해석",
        body: "더 높이 쌓겠다는 발언에서 블록 높이에 관심을 보인 것으로 해석할 수 있다.",
        sourceIds: [source.id],
      },
      {
        heading: "지원",
        body: "다음 자유놀이에 크기가 다른 블록을 제공하고 어떤 받침을 선택하는지 관찰할 예정이다.",
        sourceIds: [source.id],
      },
    ],
    ...overrides,
  };
}
test("fabricated facts and missing sources cannot pass", () => {
  const doc = document();
  assert.deepEqual(validateDocument(doc), []);
  const changed = structuredClone(doc);
  changed.sections[0].body += " 친구를 도와주었다.";
  assert.ok(validateDocument(changed).some((s) => s.includes("정확히 일치")));
  assert.ok(validateDocument({ ...doc, sources: [] }).some((s) => s.includes("원본 기록")));
});
test("empty or generic support and fabricated reference ids are rejected", () => {
  const doc = document();
  doc.sections[2].body = "잘 지원하겠다.";
  assert.ok(validateDocument(doc).some((s) => s.includes("구체적으로")));
  doc.sections[1].sourceIds = ["made-up"];
  assert.ok(validateDocument(doc).some((s) => s.includes("근거 기록")));
});
test("invalid and out-of-period observations are rejected", () => {
  assert.equal(validPeriod("2026-02-30", "2026-03-01"), false);
  assert.equal(validPeriod("2026-09-12", "2026-09-11"), false);
  assert.ok(
    validateDocument(document({ start: "2026-09-12", end: "2026-09-13" })).some((s) =>
      s.includes("기간 밖"),
    ),
  );
});
test("evidence isolates class, child, confirmed status and dates", () => {
  const doc = document();
  const others = [
    document({ id: "ok", kind: "dailyLog" }),
    document({ id: "other-class", classId: "c2", kind: "dailyLog" }),
    document({ id: "other-child", childId: "child2", kind: "dailyLog" }),
    document({ id: "draft", status: "draft", kind: "dailyLog" }),
    document({ id: "old", start: "2026-08-01", end: "2026-08-31", kind: "dailyLog" }),
  ];
  const result = compareEvidence(doc, others, [observation]);
  assert.deepEqual(
    result.matches.map((d) => d.id),
    ["ok"],
  );
  assert.equal(result.linked[0].state, "일치");
});
test("changes in original facts and source-document status trigger re-review", () => {
  assert.equal(
    compareEvidence(document(), [], [{ ...observation, fact: "수정된 관찰" }]).linked[0].state,
    "원본 변경 · 재검토",
  );
  const daily = document({ id: "daily", kind: "dailyLog", status: "draft" });
  const weekly = document({ kind: "weeklyLog", sources: [{ ...source, id: "daily" }] });
  assert.equal(compareEvidence(weekly, [daily], []).linked[0].state, "문서 변경 · 재검토");
});
test("source edits invalidate transitively, including weekly and assessment documents", () => {
  const daily = document({ id: "daily" });
  const weekly = document({ id: "weekly", sources: [{ ...source, id: "daily" }] });
  const assessment = document({ id: "assessment", sources: [{ ...source, id: "weekly" }] });
  const independent = document({ id: "unrelated", sources: [] });
  const result = invalidateDependents([daily, weekly, assessment, independent], "r1");
  assert.deepEqual(
    result.map((d) => d.status),
    ["draft", "draft", "draft", "confirmed"],
  );
});
test("template analysis uses source headings and handles text without headings", () => {
  assert.deepEqual(
    analyzeText("놀이 목표:\n아이의 관심을 살핀다.\n교사 지원:\n자료를 제공한다.").headings,
    ["놀이 목표", "교사 지원"],
  );
  assert.deepEqual(analyzeText("abcdefghijklmnopqrstuvwxyzabcdefghijklmnopqrstuvwxyz").headings, [
    "내용",
  ]);
});
test("annual plans contain twelve months and use the academic year across leap February", () => {
  const period = {
    annual: { year: 2027 },
    monthly: { month: 2 },
    weekly: { month: 9, week: 2 },
    daily: { date: "2027-09-11" },
  };
  const plan = templatePlan("annual", "4", period, "");
  assert.equal(plan.rows.length, 12);
  assert.equal(plan.rows[0].label, "3월");
  assert.equal(plan.rows[11].label, "2월");
  assert.deepEqual(planPeriod("annual", period), { start: "2027-03-01", end: "2028-02-29" });
  assert.deepEqual(planPeriod("weekly", period), { start: "2027-09-08", end: "2027-09-14" });
});
test("corrupted storage is rejected without silently overwriting it", () => {
  assert.throws(() => parseWorkspace('{"version":1,"observations":[]}'));
  assert.throws(() =>
    parseWorkspace('{"version":1,"observations":[],"documents":[{}],"templates":[],"criteria":[]}'),
  );
  let value = '{"bad":true}';
  let wrote = false;
  globalThis.window = {
    sessionStorage: fixtureSession(),
    localStorage: {
      getItem: (key) => (key === fixtureKey ? fixtureAccount : value),
      setItem: () => {
        wrote = true;
      },
    },
    dispatchEvent: () => {},
  };
  assert.throws(() => updateWorkspace((d) => d));
  assert.equal(wrote, false);
  value = null;
  window.localStorage.setItem = (_key, next) => {
    value = next;
  };
  updateWorkspace((data) => ({
    ...data,
    criteria: [{ id: "c", label: "관찰", terms: "관찰", source: "기관 기준" }],
  }));
  assert.equal(readWorkspace().criteria.length, 1);
  window.localStorage.setItem = () => {
    throw new Error("quota");
  };
  assert.throws(() => updateWorkspace((d) => d), /quota/);
  delete globalThis.window;
});
test("a stale editor cannot overwrite changed, invalidated or missing documents", () => {
  const original = document();
  assert.doesNotThrow(() => assertDocumentUnchanged(structuredClone(original), original));
  assert.throws(
    () => assertDocumentUnchanged({ ...original, status: "draft" }, original),
    /다른 작업/,
  );
  assert.throws(
    () => assertDocumentUnchanged({ ...original, sections: [] }, original),
    /다른 작업/,
  );
  assert.throws(() => assertDocumentUnchanged(undefined, original), /다른 작업/);
});
test("imported evidence can be re-confirmed without fabricated observation fields", () => {
  const imported = document({
    origin: "import",
    sources: [],
    sections: [{ heading: "첨부 원문", body: "교사가 직접 작성한 기존 관찰 원문", sourceIds: [] }],
  });
  assert.deepEqual(validateDocument(imported), []);
  assert.ok(validateDocument({ ...imported, childId: "" }).some((s) => s.includes("대상 아동")));
  assert.ok(
    validateDocument({ ...imported, kind: "dailyLog", end: "2026-09-12" }).some((s) =>
      s.includes("같아야"),
    ),
  );
});
test("source ownership, duplicate sections and forged fact references are rejected", () => {
  const doc = document();
  assert.ok(validateDocument({ ...doc, childId: "another" }).some((s) => s.includes("반·아동")));
  assert.ok(
    validateDocument({ ...doc, sections: [...doc.sections, doc.sections[2]] }).some((s) =>
      s.includes("중복"),
    ),
  );
  const altered = structuredClone(doc);
  altered.sections[0].sourceIds = ["unknown"];
  assert.ok(validateDocument(altered).some((s) => s.includes("근거 기록 연결")));
});
test("document schema rejects invalid kinds and statuses", () => {
  const doc = {
    ...document(),
    title: "test",
    className: "test",
    childName: "test",
    origin: "teacher",
    createdAt: "2026-09-11",
    updatedAt: "2026-09-11",
    reviewNote: "",
  };
  assert.equal(isSavedDocument(doc), true);
  assert.equal(isSavedDocument({ ...doc, kind: "garbage" }), false);
  assert.equal(isSavedDocument({ ...doc, status: "passed" }), false);
  const data = {
    version: 1,
    observations: [],
    documents: [doc, { ...doc }],
    templates: [],
    criteria: [],
  };
  assert.throws(() => parseWorkspace(JSON.stringify(data)), /중복/);
});
test("February without a fifth week never duplicates the fourth week", () => {
  const period = {
    annual: { year: 2026 },
    monthly: { month: 2 },
    weekly: { month: 2, week: 5 },
    daily: { date: "2026-02-28" },
  };
  assert.throws(() => planPeriod("weekly", period), /없는 주차/);
  period.weekly.week = 4;
  assert.deepEqual(planPeriod("weekly", period), { start: "2026-02-22", end: "2026-02-28" });
});

function storedWorkspace(stored) {
  const box = { value: JSON.stringify(stored) };
  globalThis.window = {
    sessionStorage: fixtureSession(),
    localStorage: {
      getItem: (key) => (key === fixtureKey ? fixtureAccount : box.value),
      setItem: (_key, next) => {
        box.value = next;
      },
    },
    dispatchEvent: () => {},
  };
  return box;
}

test("브라우저 저장소에는 본문을 다시 쓰지 않는다 — 계획안 서버 ID 와 설정만 남는다 (ADR-013)", () => {
  const meta = {
    className: "햇살반",
    childName: "",
    createdAt: "2026-09-11T00:00:00.000Z",
    updatedAt: "2026-09-11T00:00:00.000Z",
    reviewNote: "",
  };
  const box = storedWorkspace({
    version: 1,
    templates: [
      {
        id: "t",
        name: "한별찬 양식",
        text: "한별찬",
        headings: [],
        style: "",
        summary: "",
        createdAt: "",
      },
    ],
    criteria: [{ id: "c", label: "관찰", terms: "관찰", source: "기관 기준" }],
    observations: [
      {
        id: "o1",
        classId: "c1",
        className: "햇살반",
        childId: "child-1",
        childName: "한별찬",
        date: "2026-09-11",
        domain: "사회관계",
        context: "자유놀이",
        fact: "한별찬이 블록을 쌓았다.",
        createdAt: "2026-09-11T00:00:00.000Z",
      },
    ],
    documents: [
      { ...document(), ...meta, id: "teacher", title: "한별찬 9월 관찰", origin: "teacher" },
      {
        ...document(),
        ...meta,
        id: "import",
        title: "한별찬 관찰.hwp",
        origin: "import",
        sources: [],
        sections: [{ heading: "첨부 원문", body: "한별찬이 웃었다.", sourceIds: [] }],
      },
      {
        ...document(),
        ...meta,
        id: "plan",
        kind: "annual",
        childId: "",
        title: "2026학년도 연간 보육계획안",
        origin: "ai",
        annualPlanId: 7,
        annualApiSource: "api",
      },
    ],
  });
  // 예전 증빙(IMPORT)은 서버로 옮기기 전까지 저장소에 그대로 둔다(`moveLegacyImports`). 화면에는 주지 않는다.
  const stored = () =>
    JSON.parse(box.value).documents.map((d) => [d.id, d.sections.length, d.title]);
  const waiting = ["import", 1, "한별찬 관찰.hwp"];
  try {
    const data = readWorkspace();
    assert.deepEqual(data.observations, []);
    assert.deepEqual(data.templates, []);
    assert.equal(data.criteria.length, 1);
    assert.deepEqual(
      data.documents.map((d) => [d.id, d.annualPlanId, d.sections.length, d.sources.length]),
      [["plan", 7, 0, 0]],
    );
    assert.deepEqual(stored(), [waiting, ["plan", 0, "2026학년도 연간 보육계획안"]]);
    const bodies = JSON.parse(box.value);
    assert.deepEqual(bodies.observations, []);
    assert.deepEqual(bodies.templates, []);
    // 다시 저장하는 길도 본문을 버린다.
    updateWorkspace((prev) => ({
      ...prev,
      observations: [{ ...data.observations[0], id: "o2", fact: "문솔비가 웃었다." }],
      documents: [
        ...prev.documents,
        { ...document(), ...meta, id: "again", title: "문솔비 관찰", origin: "import" },
      ],
    }));
    assert.equal(box.value.includes("문솔비"), false);
    assert.deepEqual(
      readWorkspace().documents.map((d) => d.id),
      ["plan"],
    );
    // 다시 저장해도 옮기기를 기다리는 증빙은 지우지 않는다.
    assert.deepEqual(
      stored().find((d) => d[0] === "import"),
      waiting,
    );
  } finally {
    delete globalThis.window;
  }
});

test("예전 브라우저 증빙은 한 건씩 서버로 올리고, 못 올린 것도 지운 뒤 건수만 남긴다", async (t) => {
  const workspaceKey = "saessak.workspace.v1:" + encodeURIComponent(fixtureEmail);
  const linksKey =
    "saessak.apiLinks.v1:" + API_STORAGE_CONTEXT + ":" + encodeURIComponent(fixtureEmail);
  const legacy = (id, overrides = {}) => ({
    ...document(),
    id,
    title: id + ".hwp",
    className: "햇살반",
    childName: "",
    origin: "import",
    sources: [],
    sections: [{ heading: "첨부 원문", body: "한별찬이 웃었다.", sourceIds: [] }],
    createdAt: "2026-09-11T00:00:00.000Z",
    updatedAt: "2026-09-11T00:00:00.000Z",
    reviewNote: "",
    ...overrides,
  });
  const values = new Map([
    [fixtureKey, fixtureAccount],
    [linksKey, JSON.stringify({ classes: { c1: { id: 3 } }, children: { child1: 11 } })],
    [
      workspaceKey,
      JSON.stringify({
        version: 1,
        observations: [],
        templates: [],
        criteria: [],
        documents: [
          legacy("ok"),
          // 반 단위 문서는 아동 없이 보낸다.
          legacy("daily", { kind: "dailyLog" }),
          // 서버에 없는 반 — 옮기지 못한다.
          legacy("lost", { classId: "c9" }),
        ],
      }),
    ],
  ]);
  const session = fixtureSession();
  globalThis.window = {
    sessionStorage: session,
    localStorage: {
      getItem: (key) => values.get(key) ?? null,
      setItem: (key, value) => values.set(key, value),
      removeItem: (key) => values.delete(key),
    },
  };
  // 반 · 아동 서버 번호는 전역 localStorage 로 읽는다 (onboarding.ts).
  globalThis.localStorage = window.localStorage;
  const sent = [];
  const fetch = globalThis.fetch;
  globalThis.fetch = async (url, options) => {
    const body = JSON.parse(options.body);
    // 올리는 순간 저장소에 남은 증빙 — 이미 올린 것은 빠져 있어야 끊겨도 두 번 올리지 않는다.
    const left = JSON.parse(values.get(workspaceKey)).documents.map((d) => d.id);
    sent.push([body.title, body.class_id, body.child_id, body.body, left]);
    return Response.json(
      {
        id: sent.length,
        kind: body.kind,
        title: body.title,
        class_id: 3,
        child_id: body.child_id,
        start: body.start,
        end: body.end,
        status: "CONFIRMED",
        origin: "IMPORT",
        stale: false,
        sections: [],
        sources: [],
        review_note: "",
        class_note: "",
        generation: {},
        created_at: "",
        updated_at: "",
      },
      { status: 201 },
    );
  };
  t.after(() => {
    globalThis.fetch = fetch;
    delete globalThis.window;
    delete globalThis.localStorage;
  });
  window.dispatchEvent = () => {};
  // 로그인한 채 새 버전을 열면 화면이 저장소를 먼저 읽는다. 읽기 · 저장이 증빙을 지우면 안 된다.
  readWorkspace();
  updateWorkspace((prev) => prev);
  // 로그인 · 화면 진입이 겹쳐 두 번 불러도 한 건은 한 번만 올린다.
  await Promise.all([moveLegacyImports(), moveLegacyImports()]);
  assert.deepEqual(sent, [
    ["ok.hwp", 3, 11, "한별찬이 웃었다.", ["ok", "daily", "lost"]],
    // 반 단위 문서는 아동 없이 보낸다.
    ["daily.hwp", 3, null, "한별찬이 웃었다.", ["daily", "lost"]],
  ]);
  assert.deepEqual(JSON.parse(values.get(workspaceKey)).documents, []);
  assert.equal(values.get(workspaceKey).includes("한별찬"), false);
  assert.equal(session.getItem(DROPPED_IMPORTS), "1");
});

const ROSTER = [{ id: "c1", children: [{ id: "child1", name: "한별찬" }] }];

test("망이 끊기거나 서버가 잠깐 못 받으면 예전 증빙을 지우지 않고 다음에 다시 옮긴다", async (t) => {
  const workspaceKey = "saessak.workspace.v1:" + encodeURIComponent(fixtureEmail);
  const linksKey =
    "saessak.apiLinks.v1:" + API_STORAGE_CONTEXT + ":" + encodeURIComponent(fixtureEmail);
  const legacy = (id) => ({
    ...document(),
    id,
    title: id + ".hwp",
    className: "햇살반",
    childName: "",
    origin: "import",
    sources: [],
    sections: [{ heading: "첨부 원문", body: "한별찬이 웃었다.", sourceIds: [] }],
    createdAt: "2026-09-11T00:00:00.000Z",
    updatedAt: "2026-09-11T00:00:00.000Z",
    reviewNote: "",
  });
  const values = new Map([
    [fixtureKey, fixtureAccount],
    [linksKey, JSON.stringify({ classes: { c1: { id: 3 } }, children: { child1: 11 } })],
    [
      workspaceKey,
      JSON.stringify({
        version: 1,
        observations: [],
        templates: [],
        criteria: [],
        documents: [legacy("a"), legacy("b")],
      }),
    ],
  ]);
  const session = fixtureSession();
  globalThis.window = {
    sessionStorage: session,
    localStorage: {
      getItem: (key) => values.get(key) ?? null,
      setItem: (key, value) => values.set(key, value),
      removeItem: (key) => values.delete(key),
    },
  };
  globalThis.localStorage = window.localStorage;
  const fetch = globalThis.fetch;
  t.after(() => {
    globalThis.fetch = fetch;
    delete globalThis.window;
    delete globalThis.localStorage;
  });
  const left = () => JSON.parse(values.get(workspaceKey)).documents.map((d) => d.id);
  for (const fail of [
    async () => {
      throw new TypeError("Failed to fetch");
    },
    async () => Response.json({ error: { code: "INTERNAL", message: "" } }, { status: 503 }),
  ]) {
    globalThis.fetch = fail;
    await moveLegacyImports();
    assert.deepEqual(left(), ["a", "b"]);
    assert.equal(session.getItem(DROPPED_IMPORTS), null);
  }
});

test("옮기는 중 계정이 바뀌면 이전 계정의 증빙을 지우지도 다음 계정으로 보내지도 않는다 (#477 하민 점검)", async (t) => {
  const keyOf = (email) => "saessak.workspace.v1:" + encodeURIComponent(email);
  const linksOf = (email) =>
    "saessak.apiLinks.v1:" + API_STORAGE_CONTEXT + ":" + encodeURIComponent(email);
  const other = "other@example.com";
  const legacy = (id) => ({
    ...document(),
    id,
    title: id + ".hwp",
    className: "햇살반",
    childName: "",
    origin: "import",
    sources: [],
    sections: [{ heading: "첨부 원문", body: "한별찬이 웃었다.", sourceIds: [] }],
    createdAt: "2026-09-11T00:00:00.000Z",
    updatedAt: "2026-09-11T00:00:00.000Z",
    reviewNote: "",
  });
  const values = new Map([
    [fixtureKey, fixtureAccount],
    // A 의 햇살반은 서버 3번, B 의 같은 화면 id 는 서버 99번이다.
    [
      linksOf(fixtureEmail),
      JSON.stringify({ classes: { c1: { id: 3 } }, children: { child1: 11 } }),
    ],
    [linksOf(other), JSON.stringify({ classes: { c1: { id: 99 } }, children: { child1: 77 } })],
    [
      keyOf(fixtureEmail),
      JSON.stringify({
        version: 1,
        observations: [],
        templates: [],
        criteria: [],
        documents: [legacy("a"), legacy("b")],
      }),
    ],
  ]);
  const session = fixtureSession();
  const events = [];
  globalThis.window = {
    sessionStorage: session,
    localStorage: {
      getItem: (key) => values.get(key) ?? null,
      setItem: (key, value) => values.set(key, value),
      removeItem: (key) => values.delete(key),
    },
    dispatchEvent: (e) => events.push(e.type),
  };
  globalThis.localStorage = window.localStorage;
  const sent = [];
  const fetch = globalThis.fetch;
  globalThis.fetch = async (url, options) => {
    sent.push(JSON.parse(options.body).class_id);
    // A 의 첫 요청이 서버에 가 있는 동안 로그아웃하고 B 로 들어온다.
    session.setItem("saessak.accountEmail", other);
    return Response.json({ error: { code: "INTERNAL", message: "" } }, { status: 201 });
  };
  t.after(() => {
    globalThis.fetch = fetch;
    delete globalThis.window;
    delete globalThis.localStorage;
  });

  await moveLegacyImports();

  // 첫 요청은 A 의 반(3)으로만 나갔고, B 의 반(99)으로는 한 건도 나가지 않는다.
  assert.deepEqual(sent, [3]);
  // A 의 대기 증빙은 그대로다 — A 로 다시 들어오면 그때 옮긴다.
  assert.deepEqual(
    JSON.parse(values.get(keyOf(fixtureEmail))).documents.map((d) => d.id),
    ["a", "b"],
  );
  assert.equal(values.has(keyOf(other)), false);
  assert.equal(session.getItem(DROPPED_IMPORTS), null);
  assert.deepEqual(events, []);
});

test("옮기기가 끝나면 보관함이 목록과 안내를 다시 읽는다 (#477 하민 점검)", async (t) => {
  const workspaceKey = "saessak.workspace.v1:" + encodeURIComponent(fixtureEmail);
  const linksKey =
    "saessak.apiLinks.v1:" + API_STORAGE_CONTEXT + ":" + encodeURIComponent(fixtureEmail);
  const values = new Map([
    [fixtureKey, fixtureAccount],
    [linksKey, JSON.stringify({ classes: { c1: { id: 3 } }, children: { child1: 11 } })],
    [
      workspaceKey,
      JSON.stringify({
        version: 1,
        observations: [],
        templates: [],
        criteria: [],
        documents: [
          {
            ...document(),
            id: "lost",
            classId: "c9",
            title: "lost.hwp",
            className: "햇살반",
            childName: "",
            origin: "import",
            sources: [],
            sections: [{ heading: "첨부 원문", body: "한별찬이 웃었다.", sourceIds: [] }],
            createdAt: "2026-09-11T00:00:00.000Z",
            updatedAt: "2026-09-11T00:00:00.000Z",
            reviewNote: "",
          },
        ],
      }),
    ],
  ]);
  const session = fixtureSession();
  const events = [];
  globalThis.window = {
    sessionStorage: session,
    localStorage: {
      getItem: (key) => values.get(key) ?? null,
      setItem: (key, value) => values.set(key, value),
      removeItem: (key) => values.delete(key),
    },
    // 신호가 울리는 순간 건수가 이미 적혀 있어야 보관함이 읽는다.
    dispatchEvent: (e) => events.push([e.type, session.getItem(DROPPED_IMPORTS)]),
  };
  globalThis.localStorage = window.localStorage;
  t.after(() => {
    delete globalThis.window;
    delete globalThis.localStorage;
  });
  await moveLegacyImports();
  assert.deepEqual(events, [[LEGACY_IMPORTS_MOVED, "1"]]);

  const { readFile } = await import("node:fs/promises");
  const page = await readFile(
    new URL("../components/workspace/DocumentsPage.tsx", import.meta.url),
    "utf8",
  );
  const start = page.indexOf("onLegacyImportsMoved(");
  assert.ok(start > -1, "보관함이 옮기기 완료 신호를 듣는다");
  const handler = page.slice(start, page.indexOf("}),", start));
  assert.match(handler, /readDropped\(\)/);
  assert.match(handler, /reloadList\(\)/);
});

test("이미 로그인한 교사도 서비스 화면에 들어오면 예전 증빙을 옮긴다", async () => {
  const { readFile } = await import("node:fs/promises");
  const gate = await readFile(
    new URL("../components/auth/DemoSessionGate.tsx", import.meta.url),
    "utf8",
  );
  // 반 · 아동 서버 번호가 있어야 올릴 수 있다 — 원 · 반이 준비된 뒤에만 부른다.
  assert.match(gate, /roomReady\(\)\)\s*void moveLegacyImports\(\)/);
});

test("저장된 childName이 비어 있어도 서버 명단에서 화면용 이름을 찾는다", () => {
  const stored = { ...document(), childName: "" };
  assert.equal(childDisplayName(ROSTER, stored), "한별찬");
  // 반 전체 문서는 빈 값이라 호출부의 기존 fallback이 그대로 뜬다.
  assert.equal(childDisplayName(ROSTER, { ...stored, childId: "" }), "");
  // 명단에서 못 찾으면 저장된 값으로 떨어진다.
  assert.equal(childDisplayName(ROSTER, { ...stored, classId: "c9" }), "");
  assert.equal(childDisplayName([], { ...stored, childName: "문솔비" }), "문솔비");
});

test("증빙 등록은 아동 이름을 저장된 childName 이 아니라 서버 명단에서 그린다", async () => {
  const { readFile } = await import("node:fs/promises");
  const page = await readFile(
    new URL("../components/workspace/EvidenceImport.tsx", import.meta.url),
    "utf8",
  );
  assert.equal(page.includes("childName"), false);
  assert.ok(page.includes("classroom?.children.map"));
});
